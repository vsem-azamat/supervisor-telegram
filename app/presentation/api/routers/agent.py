from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.application.services.agent_service import AgentService
from app.core.container import get_container
from app.domain.agent import AgentModelConfig, ModelProvider
from app.presentation.api.auth import get_current_admin_user
from app.presentation.api.schemas.agent import (
    AgentResponseSchema,
    ChatMessageRequest,
    CreateSessionRequest,
    ModelConfigSchema,
    SessionResponse,
)

router = APIRouter()


def get_agent_service() -> AgentService:
    """Get agent service dependency."""
    container = get_container()
    return container.get_agent_service()


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    agent_service: AgentService = Depends(get_agent_service),
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> SessionResponse:
    """Create a new agent session."""
    try:
        # Convert schema to domain model
        model_config = AgentModelConfig(
            provider=request.agent_config.provider,
            model_id=request.agent_config.model_id,
            model_name=request.agent_config.model_name,
            temperature=request.agent_config.temperature,
            max_tokens=request.agent_config.max_tokens,
        )

        # Use authenticated user ID
        user_id = current_user["id"]

        session = await agent_service.create_session(user_id=user_id, model_config=model_config, title=request.title)

        return SessionResponse(
            id=session.id,
            title=session.title,
            agent_config=ModelConfigSchema.from_domain(session.agent_config),
            system_prompt=session.system_prompt,
            created_at=session.created_at,
            updated_at=session.updated_at,
            is_active=session.is_active,
            message_count=len(session.messages),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/sessions")
async def list_sessions(
    agent_service: AgentService = Depends(get_agent_service),
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, list[SessionResponse]]:
    """List all sessions for the current user."""
    try:
        # Use authenticated user ID
        user_id = current_user["id"]

        sessions = await agent_service.get_user_sessions(user_id, limit=20)

        session_responses = [
            SessionResponse(
                id=session.id,
                title=session.title,
                agent_config=ModelConfigSchema.from_domain(session.agent_config),
                system_prompt=session.system_prompt,
                created_at=session.created_at,
                updated_at=session.updated_at,
                is_active=session.is_active,
                message_count=len(session.messages),
            )
            for session in sessions
        ]

        return {"sessions": session_responses}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    agent_service: AgentService = Depends(get_agent_service),
    _current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> SessionResponse:
    """Get a specific session."""
    try:
        session = await agent_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionResponse(
            id=session.id,
            title=session.title,
            agent_config=ModelConfigSchema.from_domain(session.agent_config),
            system_prompt=session.system_prompt,
            created_at=session.created_at,
            updated_at=session.updated_at,
            is_active=session.is_active,
            message_count=len(session.messages),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    agent_service: AgentService = Depends(get_agent_service),
    _current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> list[dict[str, Any]]:
    """Get messages for a specific session."""
    try:
        session = await agent_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Return messages in expected format
        return [
            {
                "id": str(i),
                "session_id": session_id,
                "role": "user" if i % 2 == 0 else "assistant",
                "content": msg.content if hasattr(msg, "content") else str(msg),
                "timestamp": session.created_at,  # Placeholder for now
                "tokens_used": 0,  # Placeholder for now
            }
            for i, msg in enumerate(session.messages)
        ]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/sessions/{session_id}/chat", response_model=AgentResponseSchema)
async def chat_with_agent(
    session_id: str,
    request: ChatMessageRequest,
    agent_service: AgentService = Depends(get_agent_service),
    _current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> AgentResponseSchema:
    """Send a message to the agent and get a response."""
    try:
        response = await agent_service.chat(session_id, request.message)

        return AgentResponseSchema(
            session_id=response.session_id,
            message=response.message,
            model_used=response.model_used,
            tokens_used=response.tokens_used,
            execution_time=response.execution_time,
            timestamp=response.timestamp,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    agent_service: AgentService = Depends(get_agent_service),
    _current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, str]:
    """Delete a session."""
    try:
        success = await agent_service.delete_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"message": "Session deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/models", response_model=list[ModelConfigSchema])
async def list_available_models(
    _current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> list[ModelConfigSchema]:
    """List all available AI models."""
    # Return only OpenRouter models for UI
    return [
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="anthropic/claude-sonnet-4.5",
            model_name="Claude Sonnet 4.5",
            temperature=0.7,
            max_tokens=8000,
            description="Latest Claude model with enhanced capabilities",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="openai/gpt-5",
            model_name="GPT-5",
            temperature=0.7,
            max_tokens=8000,
            description="OpenAI's latest flagship model",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="openai/gpt-5-mini",
            model_name="GPT-5 Mini",
            temperature=0.7,
            max_tokens=4000,
            description="Fast and cost-effective GPT-5 variant",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="openai/gpt-5-chat",
            model_name="GPT-5 Chat",
            temperature=0.7,
            max_tokens=8000,
            description="GPT-5 optimized for conversational tasks",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="openai/gpt-oss-20b",
            model_name="GPT OSS 20B",
            temperature=0.7,
            max_tokens=4000,
            description="Open source 20B parameter model",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="x-ai/grok-4-fast",
            model_name="Grok 4 Fast",
            temperature=0.7,
            max_tokens=4000,
            description="X.AI's fast and efficient Grok model",
        ),
    ]


@router.get("/models/{provider}", response_model=list[ModelConfigSchema])
async def list_models_by_provider(
    provider: ModelProvider, _current_user: dict[str, Any] = Depends(get_current_admin_user)
) -> list[ModelConfigSchema]:
    """List available AI models for a specific provider."""
    # Support for multiple providers (extensible for future)
    # Currently only OpenRouter models are exposed in UI

    openai_models = [
        # OpenAI provider kept for potential future use
        ModelConfigSchema(
            provider=ModelProvider.OPENAI,
            model_id="gpt-4o-mini",
            model_name="GPT-4o Mini",
            temperature=0.7,
            max_tokens=2000,
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENAI,
            model_id="gpt-4o",
            model_name="GPT-4o",
            temperature=0.7,
            max_tokens=4000,
        ),
    ]

    openrouter_models = [
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="anthropic/claude-sonnet-4.5",
            model_name="Claude Sonnet 4.5",
            temperature=0.7,
            max_tokens=8000,
            description="Latest Claude model with enhanced capabilities",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="anthropic/claude-3-5-sonnet",
            model_name="Claude 3.5 Sonnet",
            temperature=0.7,
            max_tokens=4000,
            description="Excellent balance of intelligence and speed",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="openai/gpt-5",
            model_name="GPT-5",
            temperature=0.7,
            max_tokens=8000,
            description="OpenAI's latest flagship model",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="openai/gpt-5-mini",
            model_name="GPT-5 Mini",
            temperature=0.7,
            max_tokens=4000,
            description="Fast and cost-effective GPT-5 variant",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="openai/gpt-5-chat",
            model_name="GPT-5 Chat",
            temperature=0.7,
            max_tokens=8000,
            description="GPT-5 optimized for conversational tasks",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="openai/gpt-oss-20b",
            model_name="GPT OSS 20B",
            temperature=0.7,
            max_tokens=4000,
            description="Open source 20B parameter model",
        ),
        ModelConfigSchema(
            provider=ModelProvider.OPENROUTER,
            model_id="x-ai/grok-4-fast",
            model_name="Grok 4 Fast",
            temperature=0.7,
            max_tokens=4000,
            description="X.AI's fast and efficient Grok model",
        ),
    ]

    all_models = openai_models + openrouter_models

    # Filter models by provider
    return [model for model in all_models if model.provider == provider]
