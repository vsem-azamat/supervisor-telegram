from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.application.services.agent_service import AgentService
from app.core.container import get_container
from app.domain.agent import AgentModelConfig, ModelProvider, OpenRouterModel
from app.domain.agent_models import OPENAI_MODELS, OPENROUTER_MODELS
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


def _convert_model_to_schema(
    model: "OpenRouterModel", provider: ModelProvider, default_temp: float = 0.7
) -> ModelConfigSchema:
    """Convert OpenRouterModel to ModelConfigSchema with default settings."""
    # Determine max_tokens based on context_length
    max_tokens = 8000 if model.context_length and model.context_length >= 100000 else 4000

    return ModelConfigSchema(
        provider=provider,
        model_id=model.id,
        model_name=model.name,
        temperature=default_temp,
        max_tokens=max_tokens,
        description=model.description,
    )


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
    return [_convert_model_to_schema(model, ModelProvider.OPENROUTER) for model in OPENROUTER_MODELS]


@router.get("/models/{provider}", response_model=list[ModelConfigSchema])
async def list_models_by_provider(
    provider: ModelProvider, _current_user: dict[str, Any] = Depends(get_current_admin_user)
) -> list[ModelConfigSchema]:
    """List available AI models for a specific provider."""
    # Support for multiple providers (extensible for future)
    if provider == ModelProvider.OPENAI:
        return [_convert_model_to_schema(model, ModelProvider.OPENAI) for model in OPENAI_MODELS]
    # provider == ModelProvider.OPENROUTER
    return [_convert_model_to_schema(model, ModelProvider.OPENROUTER) for model in OPENROUTER_MODELS]
