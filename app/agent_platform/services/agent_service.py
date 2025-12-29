import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from app.agent_platform.domain.agent import (
    AgentMetrics,
    AgentModelConfig,
    AgentResponse,
    AgentSession,
    AgentToolResult,
    ModelProvider,
)
from app.agent_platform.domain.agent_models import OPENROUTER_MODELS
from app.agent_platform.domain.repositories import IAgentRepository
from app.core.config import settings
from app.core.logging import BotLogger
from app.domain.prompts import DEFAULT_SYSTEM_PROMPT
from app.domain.repositories import IChatRepository, IMessageRepository, IUserRepository
from app.domain.value_objects import UserId
from mcp import ClientSession
from mcp.client.sse import sse_client
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider


class AgentContext(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    user_id: int
    session_id: str
    mcp_session: ClientSession | None = None
    logger: Any = None


class AgentService:
    def __init__(
        self,
        agent_repository: IAgentRepository,
        chat_repository: IChatRepository,
        user_repository: IUserRepository,
        message_repository: IMessageRepository,
        logger: BotLogger,
    ) -> None:
        self.agent_repository = agent_repository
        self.chat_repository = chat_repository
        self.user_repository = user_repository
        self.message_repository = message_repository
        self.logger = logger

        self._agents: dict[str, Agent[AgentContext]] = {}
        self.metrics = AgentMetrics()

    def _get_api_credentials(self, model_config: AgentModelConfig) -> tuple[str, str | None]:
        """Get API key and base URL for model configuration."""
        if model_config.provider != ModelProvider.OPENROUTER:
            raise ValueError(f"Only OpenRouter provider is supported. Got: {model_config.provider}")

        if not settings.ai_agent.has_openrouter_key():
            raise ValueError(
                "OPENROUTER_API_KEY is not configured in environment variables. Get API key at https://openrouter.ai/keys"
            )

        api_key = settings.ai_agent.openrouter_api_key
        base_url = model_config.base_url or settings.ai_agent.openrouter_base_url or "https://openrouter.ai/api/v1"

        return api_key, base_url

    def _create_agent(self, model_config: AgentModelConfig) -> Agent[AgentContext]:
        """Create PydanticAI agent with specified model configuration."""
        api_key, base_url = self._get_api_credentials(model_config)

        self.logger.logger.debug(
            f"Creating OpenAIModel with model={model_config.model_id}, base_url={base_url}, api_key={api_key[:8]}..."
        )

        # Create explicit AsyncOpenAI client for OpenRouter
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/vsem-azamat/moderator-bot",
                "X-Title": "Moderator Bot Agent",
            },
        )

        provider = OpenAIProvider(openai_client=client)

        model = OpenAIModel(
            model_config.model_id,
            provider=provider,
        )

        system_prompt = DEFAULT_SYSTEM_PROMPT.content

        return Agent(
            model,
            deps_type=AgentContext,
            system_prompt=system_prompt,
            model_settings={
                "temperature": model_config.temperature,
                "max_tokens": model_config.max_tokens or DEFAULT_SYSTEM_PROMPT.max_tokens,
            },
        )

    async def _bind_mcp_tools(self, agent: Agent[AgentContext], mcp_session: ClientSession) -> None:
        """Fetch tools from MCP server and bind them to the agent."""
        self.logger.logger.debug("Fetching tools from MCP server...")
        tools_list = await mcp_session.list_tools()

        for tool in tools_list.tools:
            self.logger.logger.debug(f"Registering MCP tool: {tool.name}")

            # Use a factory to avoid closure issues with loop variables
            def make_tool(t_name: str, t_desc: str) -> Any:
                async def mcp_tool_wrapper(ctx: RunContext[AgentContext], **kwargs: Any) -> str:
                    if not ctx.deps.mcp_session:
                        raise RuntimeError("MCP session not available in context")

                    if ctx.deps.logger:
                        ctx.deps.logger.info(f"Calling MCP tool: {t_name}")

                    result = await ctx.deps.mcp_session.call_tool(t_name, arguments=kwargs)

                    if result.isError:
                        error_msg = next((p.text for p in result.content if hasattr(p, "text")), "Unknown error")
                        if ctx.deps.logger:
                            ctx.deps.logger.warning(f"MCP tool {t_name} failed: {error_msg}")
                        return f"Error: {error_msg}"

                    # Extract text from content
                    text_content = [p.text for p in result.content if hasattr(p, "text")]

                    if not text_content:
                        # Return a fallback message so the LLM knows the tool ran but returned nothing
                        return "Tool executed successfully. No text output returned."

                    return "\n".join(text_content)

                mcp_tool_wrapper.__name__ = t_name
                mcp_tool_wrapper.__doc__ = t_desc or f"MCP tool: {t_name}"
                return mcp_tool_wrapper

            agent.tool(make_tool(tool.name, tool.description or f"MCP tool: {tool.name}"))

    @asynccontextmanager
    async def _mcp_context(self, agent: Agent[AgentContext], session: AgentSession) -> AsyncIterator[AgentContext]:
        """Context manager for MCP session and tool binding."""
        async with (
            sse_client(settings.mcp.url) as (read, write),
            ClientSession(read, write) as mcp_session,
        ):
            await mcp_session.initialize()
            await self._bind_mcp_tools(agent, mcp_session)

            yield AgentContext(
                user_id=session.user_id.value,
                session_id=session.id,
                mcp_session=mcp_session,
                logger=self.logger.logger,
            )

    async def create_session(
        self, user_id: int, model_config: AgentModelConfig, title: str | None = None, system_prompt: str | None = None
    ) -> AgentSession:
        """Create new session with AI agent."""
        session = AgentSession(
            user_id=UserId(user_id), agent_config=model_config, system_prompt=system_prompt, title=title
        )

        saved_session = await self.agent_repository.save_session(session)
        self.metrics.sessions_created += 1
        if saved_session.is_active:
            self.metrics.active_sessions += 1
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

            # Create agent (caching disabled for MCP)
            agent = self._create_agent(session.agent_config)
            session.add_message("user", message)

            async with self._mcp_context(agent, session) as context:
                self.logger.logger.debug("Running agent...")
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

            if hasattr(result, "usage") and result.usage is not None:
                usage = result.usage
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

    async def chat_stream(self, session_id: str, message: str) -> AsyncIterator[str]:
        """
        Stream message to agent and yield response chunks in real-time.

        Yields accumulated text as it arrives from the LLM.
        Updates session after stream completes.
        Records metrics for the streaming request.

        Args:
            session_id: ID of the agent session
            message: User message to send to agent

        Yields:
            str: Accumulated response text (grows with each chunk)

        Raises:
            ValueError: If session not found
            Exception: For other errors during streaming
        """
        start_time = time.time()
        success = False
        tokens_used = None
        tools_used: list[str] = []
        error_type: str | None = None
        response_text = ""

        try:
            session = await self.agent_repository.get_session(session_id)
            if not session:
                error_type = "SessionNotFound"
                raise ValueError(f"Session {session_id} not found")

            # Get API credentials for this model config
            api_key, base_url = self._get_api_credentials(session.agent_config)

            self.logger.logger.info(
                f"Starting streaming run with provider={session.agent_config.provider}, "
                f"model={session.agent_config.model_id}, base_url={base_url}"
            )

            # Create agent (caching disabled for MCP)
            agent = self._create_agent(session.agent_config)
            session.add_message("user", message)

            async with self._mcp_context(agent, session) as context:
                self.logger.logger.debug("Starting streaming run...")
                async with agent.run_stream(user_prompt=message, deps=context) as result:
                    # Stream text chunks
                    full_response = ""

                    # Hybrid approach: use delta=True for responsiveness
                    # This allows users to see tokens as they are generated
                    async for text_chunk in result.stream_text(delta=True):
                        full_response += text_chunk
                        yield full_response

                    # If stream yielded nothing (e.g. tools were called first),
                    # we must explicitly get the final output inside context
                    if not full_response:
                        self.logger.logger.debug("Stream yielded no text, fetching final output...")
                        try:
                            final_output = await result.get_output()
                            if final_output:
                                final_text = str(final_output)
                                full_response = final_text
                                yield full_response
                        except Exception as e:
                            self.logger.logger.warning(f"Failed to get final output: {e}")

                    # Fallback message if absolutely nothing was generated
                    if not full_response:
                        fallback = "I have processed your request."
                        full_response = fallback
                        yield fallback

                    response_text = full_response

                    # After streaming completes, extract metadata
                    self.logger.logger.info(f"Stream completed: {len(response_text)} characters")

                    # Add assistant response to session
                    session.add_message("assistant", response_text)
                    await self.agent_repository.update_session(session)

                    # Extract tool call information
                    tool_results: list[AgentToolResult] = []
                    if hasattr(result, "all_messages"):
                        for msg in result.all_messages():
                            if hasattr(msg, "parts"):
                                for part in msg.parts:
                                    if hasattr(part, "tool_name") and part.tool_name:
                                        tool_name = str(part.tool_name)
                                        tool_result = AgentToolResult(
                                            tool_name=tool_name,
                                            success=not hasattr(part, "error"),
                                            result=getattr(part, "content", None),
                                            error=str(getattr(part, "error", None)) if hasattr(part, "error") else None,
                                        )
                                        tool_results.append(tool_result)
                                        tools_used.append(tool_name)

                    if tool_results:
                        self.logger.logger.info(
                            f"Agent used {len(tool_results)} tools: {[t.tool_name for t in tool_results]}"
                        )
                        for t in tool_results:
                            if t.error:
                                self.logger.logger.warning(f"Tool {t.tool_name} error: {t.error}")
                            else:
                                self.logger.logger.info(
                                    f"Tool {t.tool_name} success on result: {str(t.result)[:100]}..."
                                )

                    # Extract token usage
                    if hasattr(result, "usage") and result.usage is not None:
                        usage = result.usage
                        tokens_used = getattr(usage, "total_tokens", None)

            execution_time = time.time() - start_time
            success = True

            # Record metrics
            self.metrics.record_request(
                success=success, execution_time=execution_time, tokens_used=tokens_used, tools_used=tools_used
            )

            self.logger.logger.info(
                f"Streaming completed for session {session_id}, execution time: {execution_time:.2f}s, "
                f"tokens: {tokens_used or 'N/A'}"
            )

        except Exception as e:
            execution_time = time.time() - start_time
            if not error_type:
                error_type = type(e).__name__

            self.logger.logger.error(
                f"Error during streaming for session {session_id}: {e}",
                exc_info=True,
            )

            # Record metrics for failed request
            self.metrics.record_request(success=False, execution_time=execution_time, error_type=error_type)

            # Re-raise exception so caller can handle it
            raise

    async def delete_session(self, session_id: str) -> bool:
        """Delete session."""
        success = await self.agent_repository.delete_session(session_id)
        if success:
            self.metrics.sessions_deleted += 1
            if self.metrics.active_sessions > 0:
                self.metrics.active_sessions -= 1
            self.logger.logger.info(f"Deleted session {session_id}")
        return success

    async def get_metrics(self) -> dict[str, Any]:
        """Get current service metrics."""
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
