from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.agent import AgentModelConfig, ModelProvider


class ModelConfigSchema(BaseModel):
    provider: ModelProvider
    model_id: str
    model_name: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    description: str | None = None

    @classmethod
    def from_domain(cls, model_config: AgentModelConfig) -> "ModelConfigSchema":
        """Convert from domain AgentModelConfig to schema."""
        return cls(
            provider=model_config.provider,
            model_id=model_config.model_id,
            model_name=model_config.model_name,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,
        )


class CreateSessionRequest(BaseModel):
    agent_config: ModelConfigSchema
    title: str | None = None


class ChatMessageRequest(BaseModel):
    message: str


class SessionResponse(BaseModel):
    id: str
    title: str | None = None
    agent_config: ModelConfigSchema
    system_prompt: str | None = None
    created_at: datetime
    updated_at: datetime
    is_active: bool
    message_count: int = Field(default=0)


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    timestamp: datetime
    tokens_used: int | None = None


class AgentResponseSchema(BaseModel):
    session_id: str
    message: str
    model_used: str
    tokens_used: int | None = None
    execution_time: float | None = None
    timestamp: datetime


class ChatResponse(BaseModel):
    session_id: str
    message: str
    model_used: str
    tokens_used: int | None = None
    execution_time: float | None = None
    timestamp: datetime


class AvailableModelResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    context_length: int | None = None
    provider: ModelProvider


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int


class AgentMetricsSchema(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    error_rate: float
    total_tokens_used: int
    avg_tokens_per_request: float
    total_execution_time: float
    avg_execution_time: float
    most_used_tools: list[tuple[str, int]]
    error_breakdown: dict[str, int]
    sessions_created: int
    sessions_deleted: int
    active_sessions: int


class MetricsResponse(BaseModel):
    metrics: AgentMetricsSchema
    status: str = "ok"


class StatusMessageResponse(BaseModel):
    message: str
    status: str | None = None
