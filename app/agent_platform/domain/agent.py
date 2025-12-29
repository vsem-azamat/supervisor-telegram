from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from app.domain.value_objects import UserId
from pydantic import BaseModel, Field


class ModelProvider(str, Enum):
    OPENROUTER = "openrouter"


class OpenRouterModel(BaseModel):
    id: str
    name: str
    description: str | None = None
    pricing: dict[str, float] = Field(default_factory=dict)
    context_length: int | None = None
    architecture: str | None = None
    modality: str = "text"


class AgentModelConfig(BaseModel):
    provider: ModelProvider
    model_id: str
    model_name: str | None = None
    api_key: str | None = None  # API key will be injected at runtime
    base_url: str | None = None
    max_tokens: int | None = None
    temperature: float = 0.7


class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: UserId
    title: str | None = None
    messages: list[AgentMessage] = Field(default_factory=list)
    agent_config: AgentModelConfig
    system_prompt: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_message(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> AgentMessage:
        """Add message to session and update timestamp."""
        message = AgentMessage(role=role, content=content, metadata=metadata or {})
        self.messages.append(message)
        self.updated_at = datetime.utcnow()
        return message

    def get_conversation_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get conversation history with optional message limit."""
        messages = self.messages[-limit:] if limit else self.messages
        return [{"role": msg.role, "content": msg.content, "timestamp": msg.timestamp.isoformat()} for msg in messages]

    def mark_inactive(self) -> None:
        """Mark session as inactive and update timestamp."""
        self.is_active = False
        self.updated_at = datetime.utcnow()


class AgentToolResult(BaseModel):
    tool_name: str
    success: bool
    result: Any
    error: str | None = None
    execution_time: float | None = None


class AgentResponse(BaseModel):
    session_id: str
    message: str
    tool_results: list[AgentToolResult] = Field(default_factory=list)
    model_used: str
    tokens_used: int | None = None
    execution_time: float | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentMetrics(BaseModel):
    """Metrics for agent service monitoring."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens_used: int = 0
    total_execution_time: float = 0.0
    avg_execution_time: float = 0.0
    tool_usage_count: dict[str, int] = Field(default_factory=dict)
    error_counts: dict[str, int] = Field(default_factory=dict)
    sessions_created: int = 0
    sessions_deleted: int = 0
    active_sessions: int = 0

    def record_request(
        self,
        success: bool,
        execution_time: float,
        tokens_used: int | None = None,
        tools_used: list[str] | None = None,
        error_type: str | None = None,
    ) -> None:
        """Record metrics for a request."""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
            if error_type:
                self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

        self.total_execution_time += execution_time
        self.avg_execution_time = self.total_execution_time / self.total_requests

        if tokens_used:
            self.total_tokens_used += tokens_used

        if tools_used:
            for tool_name in tools_used:
                self.tool_usage_count[tool_name] = self.tool_usage_count.get(tool_name, 0) + 1

    def get_summary(self) -> dict[str, Any]:
        """Get metrics summary."""
        error_rate = (self.failed_requests / self.total_requests * 100) if self.total_requests > 0 else 0
        success_rate = (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0

        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": round(success_rate, 2),
            "error_rate": round(error_rate, 2),
            "total_tokens_used": self.total_tokens_used,
            "avg_tokens_per_request": (
                round(self.total_tokens_used / self.successful_requests, 2) if self.successful_requests > 0 else 0
            ),
            "total_execution_time": round(self.total_execution_time, 2),
            "avg_execution_time": round(self.avg_execution_time, 2),
            "most_used_tools": sorted(self.tool_usage_count.items(), key=lambda x: x[1], reverse=True)[:5],
            "error_breakdown": dict(self.error_counts),
            "sessions_created": self.sessions_created,
            "sessions_deleted": self.sessions_deleted,
            "active_sessions": self.active_sessions,
        }
