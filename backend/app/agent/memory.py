from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, field_validator


class MemoryCandidate(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    predicate: str = Field(min_length=1, max_length=100)
    object: str = Field(min_length=1, max_length=1000)
    memory_type: Literal["preference", "constraint", "relationship", "business_fact"]
    confidence: float = Field(ge=0, le=1)
    entities: list[str] = Field(default_factory=list, max_length=20)
    source_message_ids: list[str] = Field(default_factory=list, min_length=1)
    valid_from: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("object")
    @classmethod
    def reject_secrets(cls, value: str) -> str:
        lowered = value.casefold()
        if any(token in lowered for token in ("api_key", "password", "authorization:", "身份证")):
            raise ValueError("memory candidate contains restricted data")
        return value.strip()

    @property
    def memory_key(self) -> str:
        identity = "|".join((self.subject.casefold(), self.predicate.casefold()))
        return hashlib.sha256(identity.encode()).hexdigest()


class MemoryTriggerPolicy:
    def should_extract(
        self,
        *,
        user_turn_count: int,
        token_ratio: float,
        memory_worthy: bool,
        entities: list[dict[str, Any]],
        query: str,
        idle_minutes: float = 0,
    ) -> bool:
        return any(
            (
                user_turn_count > 0 and user_turn_count % 6 == 0,
                token_ratio >= 0.75,
                memory_worthy,
                bool(entities) and any(token in query for token in ("喜欢", "不喜欢", "需要", "不要", "是")),
                "记住" in query,
                idle_minutes >= 30,
            )
        )


class MemoryAuthorityClient:
    """All durable memory writes go through Java/MySQL; Python never writes memory ES directly."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("MUSIC_CORE_URL", "http://localhost:8080")).rstrip("/")

    def save(self, candidate: MemoryCandidate, *, user_id: str, tenant_id: str, idempotency_key: str, trace_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(
                f"{self.base_url}/internal/v1/memories",
                json={**candidate.model_dump(mode="json"), "memory_key": candidate.memory_key},
                headers={
                    "X-User-Id": user_id,
                    "X-Tenant-Id": tenant_id,
                    "Idempotency-Key": idempotency_key,
                    "X-Trace-Id": trace_id,
                    "X-Permissions": "memory.write",
                },
            )
            response.raise_for_status()
            return response.json()

    def audit_turn(
        self,
        *,
        user_id: str,
        tenant_id: str,
        session_id: str,
        user_message_id: str,
        user_content: str,
        user_tokens: int,
        assistant_message_id: str,
        assistant_content: str,
        assistant_tokens: int,
        trace_id: str,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(
                f"{self.base_url}/internal/v1/conversations/turns",
                json={
                    "session_id": session_id,
                    "user_message_id": user_message_id,
                    "user_content": user_content,
                    "user_tokens": user_tokens,
                    "assistant_message_id": assistant_message_id,
                    "assistant_content": assistant_content,
                    "assistant_tokens": assistant_tokens,
                },
                headers={
                    "X-User-Id": user_id,
                    "X-Tenant-Id": tenant_id,
                    "X-Permissions": "conversation.write",
                    "X-Trace-Id": trace_id,
                },
            )
            response.raise_for_status()
            return response.json()


def memory_saved_at() -> str:
    return datetime.now(UTC).isoformat()
