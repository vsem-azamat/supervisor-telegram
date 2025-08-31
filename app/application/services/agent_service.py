import time
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from app.application.services.agent_tools import AgentTools, ChatInfo
from app.application.services.api_key_manager import with_api_key
from app.core.config import settings
from app.core.logging import BotLogger
from app.domain.agent import AgentModelConfig, AgentResponse, AgentSession, AgentToolResult, ModelProvider
from app.domain.repositories import IAgentRepository, IChatRepository, IUserRepository
from app.domain.value_objects import UserId


class AgentContext(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    user_id: int
    session_id: str
    tools: AgentTools


class AgentService:
    def __init__(
        self,
        agent_repository: IAgentRepository,
        chat_repository: IChatRepository,
        user_repository: IUserRepository,
        logger: BotLogger,
    ) -> None:
        self.agent_repository = agent_repository
        self.chat_repository = chat_repository
        self.user_repository = user_repository
        self.logger = logger

        self.tools = AgentTools(chat_repository, user_repository, logger)
        self._agents: dict[str, Agent[AgentContext]] = {}

    def _get_api_credentials(self, model_config: AgentModelConfig) -> tuple[str, str | None]:
        """Get API key and base URL for model configuration."""
        api_key = None
        base_url = model_config.base_url

        if model_config.provider == ModelProvider.OPENAI:
            if not settings.ai_agent.has_openai_key():
                raise ValueError(
                    "OPENAI_API_KEY не настроен в переменных окружения. Получите ключ на https://platform.openai.com/api-keys"
                )
            api_key = settings.ai_agent.openai_api_key
            if not base_url and settings.ai_agent.openai_base_url:
                base_url = settings.ai_agent.openai_base_url
        elif model_config.provider == ModelProvider.OPENROUTER:
            if not settings.ai_agent.has_openrouter_key():
                raise ValueError(
                    "OPENROUTER_API_KEY не настроен в переменных окружения. Получите ключ на https://openrouter.ai/keys"
                )
            api_key = settings.ai_agent.openrouter_api_key
            if not base_url:
                base_url = settings.ai_agent.openrouter_base_url
        else:
            raise ValueError(f"Неподдерживаемый провайдер: {model_config.provider}")

        return api_key, base_url

    def _create_agent(self, model_config: AgentModelConfig) -> Agent[AgentContext]:
        """Create PydanticAI agent with specified model configuration."""

        if model_config.provider == ModelProvider.OPENAI:
            model = model_config.model_id
        elif model_config.provider == ModelProvider.OPENROUTER:
            model = f"openai:{model_config.model_id}"
        else:
            raise ValueError(f"Неподдерживаемый провайдер: {model_config.provider}")

        # Don't set environment variables here - use context manager during runtime

        system_prompt = """
Ты - AI помощник для управления Telegram чатами и каналами модераторского бота.
Твоя цель - помочь администраторам эффективно управлять сообществами.

Основные возможности:
- Получение списка всех чатов и их детальной информации
- Обновление описаний чатов и настроек приветствий
- Поиск чатов по названию или описанию
- Анализ статистики по чатам и пользователям

Всегда отвечай на русском языке профессионально и конструктивно.
При выполнении операций всегда сообщай о результате.
Если произошла ошибка, объясни что пошло не так и предложи альтернативы.
"""

        agent = Agent(
            model,
            deps_type=AgentContext,
            system_prompt=system_prompt,
            model_settings={
                "temperature": model_config.temperature,
                "max_tokens": model_config.max_tokens or 2000,
            },
        )

        @agent.tool
        async def get_all_chats(ctx: RunContext[AgentContext]) -> list[ChatInfo]:
            """Get list of all managed chats with basic information."""
            return await ctx.deps.tools.get_all_chats()

        @agent.tool
        async def get_chat_details(ctx: RunContext[AgentContext], chat_id: int) -> ChatInfo | None:
            """Get detailed information about specific chat by ID."""
            return await ctx.deps.tools.get_chat_details(chat_id)

        @agent.tool
        async def update_chat_description(ctx: RunContext[AgentContext], chat_id: int, description: str) -> bool:
            """Update chat description. Returns True if successful."""
            return await ctx.deps.tools.update_chat_description(chat_id, description)

        @agent.tool
        async def update_chat_settings(
            ctx: RunContext[AgentContext],
            chat_id: int,
            title: str | None = None,
            welcome_text: str | None = None,
            welcome_enabled: bool | None = None,
            auto_delete_time: int | None = None,
        ) -> bool:
            """Update chat settings (description, welcome, auto-delete). Returns True if successful."""
            return await ctx.deps.tools.update_chat_settings(
                chat_id, title, welcome_text, welcome_enabled, auto_delete_time
            )

        @agent.tool
        async def get_chat_statistics(ctx: RunContext[AgentContext]) -> dict[str, Any]:
            """Get general statistics for all chats."""
            return await ctx.deps.tools.get_chat_statistics()

        @agent.tool
        async def search_chats(ctx: RunContext[AgentContext], query: str) -> list[ChatInfo]:
            """Find chats by title or description."""
            return await ctx.deps.tools.search_chats(query)

        return agent

    async def create_session(
        self, user_id: int, model_config: AgentModelConfig, title: str | None = None, system_prompt: str | None = None
    ) -> AgentSession:
        """Create new session with AI agent."""
        session = AgentSession(
            user_id=UserId(user_id), agent_config=model_config, system_prompt=system_prompt, title=title
        )

        saved_session = await self.agent_repository.save_session(session)
        self.logger.logger.info(f"Создана новая сессия {saved_session.id} для пользователя {user_id}")

        return saved_session

    async def get_session(self, session_id: str) -> AgentSession | None:
        """Get session by ID."""
        return await self.agent_repository.get_session(session_id)

    async def get_user_sessions(self, user_id: int, limit: int = 20) -> list[AgentSession]:
        """Get user sessions."""
        return await self.agent_repository.get_user_sessions(user_id, limit)

    async def chat(self, session_id: str, message: str) -> AgentResponse:
        """Send message to agent and get response."""
        start_time = time.time()

        try:
            session = await self.agent_repository.get_session(session_id)
            if not session:
                raise ValueError(f"Сессия {session_id} не найдена")

            agent_key = f"{session.agent_config.provider}_{session.agent_config.model_id}"
            if agent_key not in self._agents:
                self._agents[agent_key] = self._create_agent(session.agent_config)

            agent = self._agents[agent_key]
            session.add_message("user", message)

            # Get API credentials for this model config
            api_key, base_url = self._get_api_credentials(session.agent_config)

            # Use context manager to safely set API credentials
            context = AgentContext(user_id=session.user_id.value, session_id=session_id, tools=self.tools)
            with with_api_key(api_key, base_url):
                result = await agent.run(user_prompt=message, deps=context)
            response_text = result.output

            session.add_message("assistant", response_text)
            await self.agent_repository.update_session(session)

            tool_results: list[AgentToolResult] = []
            execution_time = time.time() - start_time

            tokens_used = None
            if hasattr(result, "usage"):
                usage = getattr(result, "usage", None)
                if hasattr(usage, "get") and not callable(usage):
                    tokens_used = usage.get("total_tokens", None)
                elif hasattr(usage, "total_tokens"):
                    tokens_used = getattr(usage, "total_tokens", None)

            response = AgentResponse(
                session_id=session_id,
                message=response_text,
                tool_results=tool_results,
                model_used=f"{session.agent_config.provider}:{session.agent_config.model_id}",
                tokens_used=tokens_used,
                execution_time=execution_time,
            )

            self.logger.logger.info(
                f"Обработан запрос для сессии {session_id}, время выполнения: {execution_time:.2f}с"
            )
            return response

        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.logger.error(f"Ошибка при обработке запроса для сессии {session_id}: {e}")

            return AgentResponse(
                session_id=session_id,
                message=f"Произошла ошибка при обработке запроса: {str(e)}",
                model_used="error",
                execution_time=execution_time,
            )

    async def delete_session(self, session_id: str) -> bool:
        """Delete session."""
        success = await self.agent_repository.delete_session(session_id)
        if success:
            self.logger.logger.info(f"Удалена сессия {session_id}")
        return success

    async def get_available_openrouter_models(self) -> list[dict[str, Any]]:
        """Get list of available OpenRouter models."""
        return [
            {
                "id": "anthropic/claude-3.5-sonnet",
                "name": "Claude 3.5 Sonnet",
                "description": "Лучший баланс интеллекта и скорости от Anthropic",
                "context_length": 200000,
            },
            {
                "id": "openai/gpt-4o",
                "name": "GPT-4o",
                "description": "Новейшая модель OpenAI с мультимодальными возможностями",
                "context_length": 128000,
            },
            {
                "id": "google/gemini-pro-1.5",
                "name": "Gemini Pro 1.5",
                "description": "Продвинутая модель Google с большим контекстом",
                "context_length": 1000000,
            },
            {
                "id": "meta-llama/llama-3.1-70b-instruct",
                "name": "Llama 3.1 70B",
                "description": "Открытая модель Meta с высокой производительностью",
                "context_length": 131072,
            },
            {
                "id": "mistralai/mixtral-8x7b-instruct",
                "name": "Mixtral 8x7B",
                "description": "Эффективная модель смеси экспертов от Mistral AI",
                "context_length": 32768,
            },
        ]
