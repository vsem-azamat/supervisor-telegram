import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from app.application.services.agent_tools import AgentTools, ChatInfo
from app.application.services.api_key_manager import with_api_key
from app.core.config import settings
from app.core.logging import BotLogger
from app.domain.agent import AgentMetrics, AgentModelConfig, AgentResponse, AgentSession, AgentToolResult, ModelProvider
from app.domain.agent_models import OPENROUTER_MODELS
from app.domain.prompts import DEFAULT_SYSTEM_PROMPT
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
        self.metrics = AgentMetrics()

    def _get_api_credentials(self, model_config: AgentModelConfig) -> tuple[str, str | None]:
        """Get API key and base URL for model configuration."""
        api_key = None
        base_url = model_config.base_url

        if model_config.provider == ModelProvider.OPENAI:
            if not settings.ai_agent.has_openai_key():
                raise ValueError(
                    "OPENAI_API_KEY is not configured in environment variables. Get API key at https://platform.openai.com/api-keys"
                )
            api_key = settings.ai_agent.openai_api_key
            if not base_url and settings.ai_agent.openai_base_url:
                base_url = settings.ai_agent.openai_base_url
        elif model_config.provider == ModelProvider.OPENROUTER:
            if not settings.ai_agent.has_openrouter_key():
                raise ValueError(
                    "OPENROUTER_API_KEY is not configured in environment variables. Get API key at https://openrouter.ai/keys"
                )
            api_key = settings.ai_agent.openrouter_api_key
            # OpenRouter uses OpenAI-compatible API
            if not base_url:
                base_url = settings.ai_agent.openrouter_base_url or "https://openrouter.ai/api/v1"
        else:
            raise ValueError(f"Unsupported provider: {model_config.provider}")

        return api_key, base_url

    def _create_agent(self, model_config: AgentModelConfig) -> Agent[AgentContext]:
        """Create PydanticAI agent with specified model configuration."""

        # For OpenRouter, we need to use 'openai:' prefix to tell PydanticAI
        # to use OpenAI-compatible client with custom base URL
        if model_config.provider == ModelProvider.OPENROUTER:
            model = f"openai:{model_config.model_id}"
        else:
            # For OpenAI, use model_id directly
            model = model_config.model_id

        # Don't set environment variables here - use context manager during runtime

        # Get system prompt from centralized registry
        system_prompt = DEFAULT_SYSTEM_PROMPT.content

        agent = Agent(
            model,
            deps_type=AgentContext,
            system_prompt=system_prompt,
            model_settings={
                "temperature": model_config.temperature,
                "max_tokens": model_config.max_tokens or DEFAULT_SYSTEM_PROMPT.max_tokens,
            },
        )

        @agent.tool
        async def get_all_chats(ctx: RunContext[AgentContext]) -> list[ChatInfo]:
            """Get list of all managed chats with basic information."""
            return await ctx.deps.tools.get_all_chats()

        @agent.tool
        async def get_chat_details(ctx: RunContext[AgentContext], chat_id: int) -> ChatInfo | None:
            """
            Get detailed information about a specific chat by ID.

            Use this to review current chat configuration before making changes.
            Returns ChatInfo with all settings or None if chat not found.
            """
            return await ctx.deps.tools.get_chat_details(chat_id)

        @agent.tool
        async def update_chat_settings(
            ctx: RunContext[AgentContext],
            chat_id: int,
            title: str | None = None,
            welcome_text: str | None = None,
            welcome_enabled: bool | None = None,
            auto_delete_time: int | None = None,
        ) -> dict[str, Any]:
            """
            Update chat settings such as welcome message, auto-delete timer, etc.

            Parameters:
            - chat_id: Telegram chat ID (required)
            - title: New chat title (optional)
            - welcome_text: Welcome message for new members (optional)
            - welcome_enabled: Enable/disable welcome messages (optional)
            - auto_delete_time: Seconds before auto-deleting welcome message, 0 to disable (optional)

            Returns dict with success status, updated_fields list, and error message if failed.
            Always check the 'success' field in the result before reporting to user.
            """
            return await ctx.deps.tools.update_chat_settings(
                chat_id, title, welcome_text, welcome_enabled, auto_delete_time
            )

        @agent.tool
        async def get_chat_statistics(ctx: RunContext[AgentContext]) -> dict[str, Any]:
            """
            Get general statistics across all managed chats.

            Returns counts for total chats, forum vs regular chats, chats with welcome messages,
            chats with captcha enabled, and total blocked users.
            Check 'success' field in result to verify operation completed successfully.
            """
            return await ctx.deps.tools.get_chat_statistics()

        @agent.tool
        async def search_chats(ctx: RunContext[AgentContext], query: str) -> list[ChatInfo]:
            """
            Search chats by title or description (case-insensitive).

            Useful for quickly finding specific chats when managing many communities.
            Returns list of matching ChatInfo objects, empty list if no matches found.
            """
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
        self.metrics.sessions_created += 1
        self.logger.logger.info(f"Created new session {saved_session.id} for user {user_id}")

        return saved_session

    async def get_session(self, session_id: str) -> AgentSession | None:
        """Get session by ID."""
        return await self.agent_repository.get_session(session_id)

    async def get_user_sessions(self, user_id: int, limit: int = 20) -> list[AgentSession]:
        """Get user sessions."""
        return await self.agent_repository.get_user_sessions(user_id, limit)

    @asynccontextmanager
    async def session_context(self, session_id: str) -> AsyncIterator[AgentSession]:
        """
        Context manager for agent sessions with automatic save.

        Usage:
            async with agent_service.session_context(session_id) as session:
                session.add_message("user", "Hello")
                # Session is automatically saved on exit

        Raises:
            ValueError: If session not found
        """
        session = await self.agent_repository.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        try:
            yield session
        finally:
            # Always save session, even if exception occurred
            await self.agent_repository.update_session(session)
            self.logger.logger.debug(f"Auto-saved session {session_id}")

    async def chat(self, session_id: str, message: str) -> AgentResponse:
        """Send message to agent and get response."""
        start_time = time.time()
        success = False
        tokens_used = None
        tools_used: list[str] = []
        error_type: str | None = None

        try:
            session = await self.agent_repository.get_session(session_id)
            if not session:
                error_type = "SessionNotFound"
                raise ValueError(f"Session {session_id} not found")

            # Get API credentials for this model config FIRST
            api_key, base_url = self._get_api_credentials(session.agent_config)

            self.logger.logger.info(
                f"Running agent with provider={session.agent_config.provider}, "
                f"model={session.agent_config.model_id}, base_url={base_url}"
            )

            # Set API credentials BEFORE creating agent
            # This ensures PydanticAI reads correct environment when creating OpenAI client
            with with_api_key(api_key, base_url):
                # Create or get cached agent INSIDE context with correct env vars
                agent_key = f"{session.agent_config.provider}_{session.agent_config.model_id}"
                if agent_key not in self._agents:
                    self.logger.logger.debug(f"Creating new agent for {agent_key}")
                    self._agents[agent_key] = self._create_agent(session.agent_config)

                agent = self._agents[agent_key]
                session.add_message("user", message)

                # Run agent with correct environment
                context = AgentContext(user_id=session.user_id.value, session_id=session_id, tools=self.tools)
                self.logger.logger.debug("API key set, running agent...")
                result = await agent.run(user_prompt=message, deps=context)
            response_text = result.output
            self.logger.logger.info(f"Agent response received: {len(response_text)} characters")

            session.add_message("assistant", response_text)
            await self.agent_repository.update_session(session)

            # Extract tool call information from PydanticAI result
            tool_results: list[AgentToolResult] = []
            if hasattr(result, "all_messages"):
                for msg in result.all_messages():
                    if hasattr(msg, "parts"):
                        for part in msg.parts:
                            if hasattr(part, "tool_name") and part.tool_name:
                                # Track each tool call
                                tool_name = str(part.tool_name)  # Ensure it's a string
                                tool_result = AgentToolResult(
                                    tool_name=tool_name,
                                    success=not hasattr(part, "error"),
                                    result=getattr(part, "content", None),
                                    error=str(getattr(part, "error", None)) if hasattr(part, "error") else None,
                                )
                                tool_results.append(tool_result)
                                tools_used.append(tool_name)

            if tool_results:
                self.logger.logger.info(f"Agent used {len(tool_results)} tools: {[t.tool_name for t in tool_results]}")

            execution_time = time.time() - start_time

            if hasattr(result, "usage"):
                usage = getattr(result, "usage", None)
                if hasattr(usage, "get") and not callable(usage):
                    tokens_used = usage.get("total_tokens", None)
                elif hasattr(usage, "total_tokens"):
                    tokens_used = getattr(usage, "total_tokens", None)

            success = True
            response = AgentResponse(
                session_id=session_id,
                message=response_text,
                tool_results=tool_results,
                model_used=f"{session.agent_config.provider}:{session.agent_config.model_id}",
                tokens_used=tokens_used,
                execution_time=execution_time,
            )

            # Record metrics
            self.metrics.record_request(
                success=success, execution_time=execution_time, tokens_used=tokens_used, tools_used=tools_used
            )

            self.logger.logger.info(
                f"Processed request for session {session_id}, execution time: {execution_time:.2f}s, "
                f"tokens: {tokens_used or 'N/A'}"
            )
            return response

        except Exception as e:
            execution_time = time.time() - start_time
            if not error_type:
                error_type = type(e).__name__

            self.logger.logger.error(
                f"Error processing request for session {session_id}: {e}",
                exc_info=True,  # Include full traceback
            )

            # Record metrics for failed request
            self.metrics.record_request(success=False, execution_time=execution_time, error_type=error_type)

            # Get more detailed error message
            error_details = str(e)
            if hasattr(e, "__cause__") and e.__cause__:
                error_details += f" (Cause: {e.__cause__})"

            return AgentResponse(
                session_id=session_id,
                message=f"An error occurred while processing the request: {error_details}",
                model_used="error",
                execution_time=execution_time,
            )

    async def delete_session(self, session_id: str) -> bool:
        """Delete session."""
        success = await self.agent_repository.delete_session(session_id)
        if success:
            self.metrics.sessions_deleted += 1
            self.logger.logger.info(f"Deleted session {session_id}")
        return success

    async def get_metrics(self) -> dict[str, Any]:
        """Get current service metrics."""
        # Update active sessions count
        try:
            # This is a simplified approach - in production, you'd query the repository
            self.metrics.active_sessions = len(
                [s for s in await self.agent_repository.get_user_sessions(0, limit=1000) if s.is_active]
            )
        except Exception as e:
            self.logger.logger.warning(f"Could not update active sessions count: {e}")

        return self.metrics.get_summary()

    def reset_metrics(self) -> None:
        """Reset metrics to zero. Useful for testing or periodic resets."""
        self.metrics = AgentMetrics()
        self.logger.logger.info("Agent service metrics reset")

    async def get_available_openrouter_models(self) -> list[dict[str, Any]]:
        """Get list of available OpenRouter models."""
        return [
            {
                "id": model.id,
                "name": model.name,
                "description": model.description,
                "context_length": model.context_length,
            }
            for model in OPENROUTER_MODELS
        ]
