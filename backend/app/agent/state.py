from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class TokenUsage(BaseModel):
    limit: int = 32_768
    system: int = 0
    tools: int = 0
    knowledge: int = 0
    memory: int = 0
    summary: int = 0
    recent_history: int = 0
    query: int = 0
    output_reserved: int = 2_048
    safety_margin: int = 1_024
    output_actual: int = 0

    @property
    def input_total(self) -> int:
        return sum(
            (
                self.system,
                self.tools,
                self.knowledge,
                self.memory,
                self.summary,
                self.recent_history,
                self.query,
            )
        )

    @property
    def available_input(self) -> int:
        return max(0, self.limit - self.output_reserved - self.safety_margin)

    @property
    def exceeded(self) -> bool:
        return self.input_total > self.available_input


class ToolCallRecord(BaseModel):
    call_id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "success", "error", "timeout", "denied"] = "pending"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    latency_ms: int | None = None


class Observation(BaseModel):
    call_id: str
    tool: str
    ok: bool
    content: Any = None
    error: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)


class AgentState(BaseModel):
    run_id: str = Field(default_factory=lambda: f"run-{uuid4().hex}")
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    user_id: str
    session_id: str
    tenant_id: str = "default"
    intent: str = "unknown"
    entities: list[dict[str, Any]] = Field(default_factory=list)
    step: int = 0
    max_steps: int = Field(default=8, ge=2, le=12)
    max_tool_calls: int = Field(default=6, ge=1, le=12)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deadline: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(seconds=30))
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    memory_candidates: list[dict[str, Any]] = Field(default_factory=list)
    context_summary: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    degraded_dependencies: list[str] = Field(default_factory=list)
    finalizing: bool = False

    @model_validator(mode="after")
    def validate_deadline(self) -> "AgentState":
        if self.deadline <= self.started_at:
            raise ValueError("deadline must be after started_at")
        if (self.deadline - self.started_at).total_seconds() > 60:
            raise ValueError("deadline cannot exceed 60 seconds")
        return self

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, (self.deadline - datetime.now(UTC)).total_seconds())

    @property
    def can_continue(self) -> bool:
        return (
            not self.finalizing
            and self.step < self.max_steps
            and len(self.tool_calls) < self.max_tool_calls
            and self.remaining_seconds > 0
            and not self.token_usage.exceeded
        )

    def begin_step(self) -> bool:
        if not self.can_continue:
            self.finalizing = True
            return False
        self.step += 1
        return True
