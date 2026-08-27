from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.agent.memory import MemoryCandidate, MemoryTriggerPolicy
from app.agent.runtime import PreparedRun, ProductionAgentRuntime
from app.agent.session_store import InMemorySessionStore, SessionContext
from app.agent.state import AgentState


def test_memory_trigger_conditions():
    policy = MemoryTriggerPolicy()
    assert policy.should_extract(user_turn_count=6, token_ratio=0.1, memory_worthy=False, entities=[], query="普通对话")
    assert policy.should_extract(user_turn_count=1, token_ratio=0.75, memory_worthy=False, entities=[], query="普通对话")
    assert policy.should_extract(user_turn_count=1, token_ratio=0.1, memory_worthy=True, entities=[], query="记住我喜欢民谣")
    assert not policy.should_extract(user_turn_count=1, token_ratio=0.1, memory_worthy=False, entities=[], query="普通对话")


def test_memory_candidate_has_stable_key_and_rejects_secrets():
    raw = {
        "subject": "user", "predicate": "prefers", "object": "工作时听民谣",
        "memory_type": "preference", "confidence": 0.9, "source_message_ids": ["1-0"],
    }
    first = MemoryCandidate(**raw)
    second = MemoryCandidate(**{**raw, "object": "工作时听爵士"})
    assert first.memory_key == second.memory_key
    with pytest.raises(ValidationError):
        MemoryCandidate(**{**raw, "object": "password=secret"})


def test_memory_extraction_does_not_duplicate_current_turn():
    class ModelStub:
        extracted_messages = []

        @staticmethod
        def count(_text):
            return 1

        def extract_memory(self, messages):
            self.extracted_messages = messages
            return []

    class MemoryStub:
        @staticmethod
        def audit_turn(**_kwargs):
            return {"status": "committed"}

    store = InMemorySessionStore()
    for index in range(5):
        store.append("user-1", "session-1", "user", f"old-user-{index}")
        store.append("user-1", "session-1", "assistant", f"old-assistant-{index}")

    model = ModelStub()
    runtime = ProductionAgentRuntime(
        model_client=model,
        session_store=store,
        memory_client=MemoryStub(),
    )
    state = AgentState(user_id="user-1", session_id="session-1")
    prepared = PreparedRun(
        state=state,
        session=SessionContext(summary=runtime._empty_summary(), recent_messages=[], token_budget={}),
        trusted_context="",
        original_query="current-user",
        intent_result={"memory_worthy": False},
    )

    runtime.finalize(prepared, "current-assistant")

    contents = [message["content"] for message in model.extracted_messages]
    assert contents.count("current-user") == 1
    assert contents.count("current-assistant") == 1


def test_idle_memory_trigger_uses_redis_stream_timestamp():
    old_timestamp = int((datetime.now(UTC) - timedelta(minutes=31)).timestamp() * 1000)
    session = SessionContext(
        summary=ProductionAgentRuntime._empty_summary(),
        recent_messages=[{"id": f"{old_timestamp}-0", "role": "assistant", "content": "old"}],
        token_budget={},
    )
    assert ProductionAgentRuntime._idle_minutes(session) >= 30
