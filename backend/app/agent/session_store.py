from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol


STREAM_MAXLEN = 256
COMPACT_AT = 192
KEEP_RECENT_MESSAGES = 8


@dataclass(slots=True)
class ConversationSummary:
    content: str = ""
    covered_from_id: str | None = None
    covered_through_id: str | None = None
    summary_version: int = 0
    source_message_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SessionContext:
    summary: ConversationSummary
    recent_messages: list[dict[str, str]]
    token_budget: dict[str, int]


class SummaryProvider(Protocol):
    def summarize(self, previous: str, messages: list[dict[str, str]]) -> str: ...


class DeterministicSummaryProvider:
    def summarize(self, previous: str, messages: list[dict[str, str]]) -> str:
        additions = " ".join(
            f"{item['role']}: {item['content']}" for item in messages if item.get("content")
        )
        return " ".join(part for part in (previous.strip(), additions.strip()) if part)[-8_000:]


class InMemorySessionStore:
    """Redis-compatible behavior for tests and degraded local development."""

    def __init__(self) -> None:
        self.messages: dict[str, list[dict[str, str]]] = {}
        self.summaries: dict[str, ConversationSummary] = {}
        self.budgets: dict[str, dict[str, int]] = {}
        self.sequence = 0

    def append(self, user_id: str, session_id: str, role: str, content: str) -> str:
        self.sequence += 1
        message_id = f"{self.sequence}-0"
        key = self._key(user_id, session_id)
        stream = self.messages.setdefault(key, [])
        stream.append({"id": message_id, "role": role, "content": content})
        self.messages[key] = stream[-STREAM_MAXLEN:]
        return message_id

    def load(self, user_id: str, session_id: str, limit: int = 24) -> SessionContext:
        key = self._key(user_id, session_id)
        summary = self.summaries.get(key, ConversationSummary())
        recent = self._after(self.messages.get(key, []), summary.covered_through_id)
        return SessionContext(summary, recent[-limit:], dict(self.budgets.get(key, {})))

    def compact(self, user_id: str, session_id: str, provider: SummaryProvider) -> ConversationSummary:
        key = self._key(user_id, session_id)
        current = self.summaries.get(key, ConversationSummary())
        uncovered = self._after(self.messages.get(key, []), current.covered_through_id)
        candidates = uncovered[:-KEEP_RECENT_MESSAGES]
        if not candidates:
            return current
        summary = ConversationSummary(
            content=provider.summarize(current.content, candidates),
            covered_from_id=current.covered_from_id or candidates[0]["id"],
            covered_through_id=candidates[-1]["id"],
            summary_version=current.summary_version + 1,
            source_message_ids=[*current.source_message_ids, *[item["id"] for item in candidates]],
        )
        self.summaries[key] = summary
        return summary

    def update_budget(self, user_id: str, session_id: str, budget: dict[str, int]) -> None:
        self.budgets[self._key(user_id, session_id)] = dict(budget)

    @staticmethod
    def _after(messages: list[dict[str, str]], watermark: str | None) -> list[dict[str, str]]:
        if not watermark:
            return list(messages)
        return [item for item in messages if InMemorySessionStore._id(item["id"]) > InMemorySessionStore._id(watermark)]

    @staticmethod
    def _id(value: str) -> tuple[int, int]:
        left, right = value.split("-", 1)
        return int(left), int(right)

    @staticmethod
    def _key(user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"


class RedisSessionStore:
    def __init__(self, client: Any) -> None:
        self.client = client

    @classmethod
    def from_env(cls) -> "RedisSessionStore":
        import redis

        return cls(redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True))

    def append(self, user_id: str, session_id: str, role: str, content: str) -> str:
        return self.client.xadd(
            self._messages(user_id, session_id),
            {"role": role, "content": content},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )

    def load(self, user_id: str, session_id: str, limit: int = 24) -> SessionContext:
        summary_data = self.client.hgetall(self._summary(user_id, session_id))
        summary = self._decode_summary(summary_data)
        minimum = f"({summary.covered_through_id}" if summary.covered_through_id else "-"
        rows = self.client.xrange(self._messages(user_id, session_id), min=minimum, max="+")
        recent = [{"id": row_id, "role": data["role"], "content": data["content"]} for row_id, data in rows]
        budget = {key: int(value) for key, value in self.client.hgetall(self._budget(user_id, session_id)).items()}
        return SessionContext(summary, recent[-limit:], budget)

    def compact(self, user_id: str, session_id: str, provider: SummaryProvider) -> ConversationSummary:
        from redis.exceptions import WatchError

        summary_key = self._summary(user_id, session_id)
        for _attempt in range(3):
            context = self.load(user_id, session_id, limit=STREAM_MAXLEN)
            candidates = context.recent_messages[:-KEEP_RECENT_MESSAGES]
            if not candidates:
                return context.summary
            updated = ConversationSummary(
                content=provider.summarize(context.summary.content, candidates),
                covered_from_id=context.summary.covered_from_id or candidates[0]["id"],
                covered_through_id=candidates[-1]["id"],
                summary_version=context.summary.summary_version + 1,
                source_message_ids=[*context.summary.source_message_ids, *[item["id"] for item in candidates]],
            )
            with self.client.pipeline() as pipe:
                try:
                    pipe.watch(summary_key)
                    current_version = int(pipe.hget(summary_key, "summary_version") or 0)
                    if current_version != context.summary.summary_version:
                        pipe.unwatch()
                        continue
                    pipe.multi()
                    pipe.hset(
                        summary_key,
                        mapping={
                            "content": updated.content,
                            "covered_from_id": updated.covered_from_id or "",
                            "covered_through_id": updated.covered_through_id or "",
                            "summary_version": updated.summary_version,
                            "source_message_ids": json.dumps(updated.source_message_ids),
                        },
                    )
                    pipe.execute()
                    return updated
                except WatchError:
                    continue
        raise RuntimeError("summary compaction conflicted after 3 retries")

    def update_budget(self, user_id: str, session_id: str, budget: dict[str, int]) -> None:
        self.client.hset(self._budget(user_id, session_id), mapping=budget)

    @staticmethod
    def _decode_summary(data: dict[str, str]) -> ConversationSummary:
        if not data:
            return ConversationSummary()
        return ConversationSummary(
            content=data.get("content", ""),
            covered_from_id=data.get("covered_from_id") or None,
            covered_through_id=data.get("covered_through_id") or None,
            summary_version=int(data.get("summary_version", 0)),
            source_message_ids=json.loads(data.get("source_message_ids", "[]")),
        )

    @staticmethod
    def _base(user_id: str, session_id: str) -> str:
        return f"agent:session:{user_id}:{session_id}"

    def _messages(self, user_id: str, session_id: str) -> str:
        return f"{self._base(user_id, session_id)}:messages"

    def _summary(self, user_id: str, session_id: str) -> str:
        return f"{self._base(user_id, session_id)}:summary"

    def _budget(self, user_id: str, session_id: str) -> str:
        return f"{self._base(user_id, session_id)}:budget"
