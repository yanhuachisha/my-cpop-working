from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.agent.context_budget import ContextItem, TokenBudgetManager
from app.agent.session_store import (
    KEEP_RECENT_MESSAGES,
    STREAM_MAXLEN,
    DeterministicSummaryProvider,
    InMemorySessionStore,
)
from app.agent.state import AgentState
from app.agent.tools import (
    CircuitBreaker,
    RiskLevel,
    ToolExecutionContext,
    ToolExecutor,
    ToolRegistry,
    ToolSchema,
    ToolType,
)


def make_state(max_steps=8, max_tool_calls=6):
    started = datetime.now(UTC)
    return AgentState(
        user_id="user-1",
        session_id="session-1",
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
        started_at=started,
        deadline=started + timedelta(seconds=30),
    )


def test_summary_watermark_never_duplicates_recent_history():
    store = InMemorySessionStore()
    for index in range(20):
        store.append("user-1", "session-1", "user" if index % 2 == 0 else "assistant", f"message-{index}")

    first = store.compact("user-1", "session-1", DeterministicSummaryProvider())
    loaded = store.load("user-1", "session-1", limit=100)

    assert len(loaded.recent_messages) == KEEP_RECENT_MESSAGES
    assert set(first.source_message_ids).isdisjoint({item["id"] for item in loaded.recent_messages})
    assert first.covered_through_id == "12-0"

    for index in range(20, 28):
        store.append("user-1", "session-1", "user" if index % 2 == 0 else "assistant", f"message-{index}")
    second = store.compact("user-1", "session-1", DeterministicSummaryProvider())
    loaded_again = store.load("user-1", "session-1", limit=100)

    assert second.summary_version == 2
    assert len(second.source_message_ids) == len(set(second.source_message_ids))
    assert set(second.source_message_ids).isdisjoint({item["id"] for item in loaded_again.recent_messages})
    assert [item["content"] for item in loaded_again.recent_messages] == [f"message-{index}" for index in range(20, 28)]


def test_session_stream_has_hard_maxlen_protection():
    store = InMemorySessionStore()
    for index in range(STREAM_MAXLEN + 50):
        store.append("user-1", "session-1", "user", str(index))
    messages = store.messages["user-1:session-1"]
    assert len(messages) == STREAM_MAXLEN
    assert messages[0]["content"] == "50"


def test_token_budget_keeps_last_four_turns_and_drops_low_score_retrieval():
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": "历史" * 100} for i in range(20)]
    manager = TokenBudgetManager(limit=3_000)
    plan = manager.assemble(
        system_prompt="系统" * 100,
        tool_prompt="工具" * 100,
        knowledge=[ContextItem(content="知识" * 700, score=score) for score in (1.0, 0.5, 0.1)],
        memories=[ContextItem(content="记忆" * 300, score=1.0)],
        summary="摘要" * 300,
        recent_history=history,
        query="问题",
        output_reserved=300,
        safety_margin=100,
    )
    assert plan.recent_history[-8:] == history[-8:]
    assert plan.usage.input_total <= plan.usage.available_input
    assert [item.score for item in plan.knowledge] == sorted([item.score for item in plan.knowledge], reverse=True)


def test_agent_state_hard_limits_steps_and_deadline():
    state = make_state(max_steps=2)
    assert state.begin_step() is True
    assert state.begin_step() is True
    assert state.begin_step() is False
    assert state.finalizing is True
    with pytest.raises(ValidationError):
        make_state(max_steps=13)


def test_tool_executor_enforces_permission_risk_idempotency_and_call_limit():
    calls = []
    registry = ToolRegistry()
    schema = ToolSchema(
        name="update_preference",
        description="Update a preference through the authoritative service.",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False},
        tool_type=ToolType.WRITE,
        risk_level=RiskLevel.MEDIUM,
        required_permission="preference.write",
    )
    registry.register(schema, lambda args, context: calls.append((args, context.idempotency_key)) or {"saved": True})
    registry.freeze()
    executor = ToolExecutor(registry, max_per_tool=2)
    state = make_state()
    context = ToolExecutionContext("user-1", "default", set(), set(), {})

    denied = executor.execute(state, "update_preference", {"value": "warm"}, context)
    assert denied.ok is False and "permission" in denied.error

    context.permissions.add("preference.write")
    still_denied = executor.execute(state, "update_preference", {"value": "warm"}, context)
    assert still_denied.ok is False and "confirmation" in still_denied.error

    context.confirmed_risks.add("update_preference")
    allowed_state = make_state()
    first = executor.execute(allowed_state, "update_preference", {"value": "warm"}, context)
    second = executor.execute(allowed_state, "update_preference", {"value": "warm"}, context)
    assert first.ok and second.ok
    assert len(calls) == 1
    assert calls[0][1].startswith(f"{allowed_state.run_id}:tool-")


def test_tool_registry_rejects_duplicate_and_invalid_schema():
    registry = ToolRegistry()
    schema = ToolSchema(
        name="read_catalog", description="Read catalog", input_schema={"type": "object"},
        tool_type=ToolType.READ, required_permission="catalog.read",
    )
    registry.register(schema, lambda _args, _context: {})
    with pytest.raises(ValueError):
        registry.register(schema, lambda _args, _context: {})


def test_tool_executor_stops_before_exceeding_total_budget_and_opens_circuit():
    calls = []
    registry = ToolRegistry()
    schema = ToolSchema(
        name="unstable_read",
        description="A failing read tool.",
        input_schema={"type": "object"},
        tool_type=ToolType.READ,
        required_permission="unstable.read",
    )

    def fail(_args, _context):
        calls.append(True)
        raise OSError("dependency unavailable")

    registry.register(schema, fail)
    registry.freeze()
    breaker = CircuitBreaker(failure_threshold=2, reset_seconds=30)
    executor = ToolExecutor(registry, circuit_breaker=breaker)
    context = ToolExecutionContext("user-1", "default", {"unstable.read"}, set(), {})

    for _ in range(2):
        observation = executor.execute(make_state(), "unstable_read", {}, context)
        assert observation.ok is False and "OSError" in observation.error
    blocked = executor.execute(make_state(), "unstable_read", {}, context)
    assert blocked.ok is False and "circuit breaker open" in blocked.error
    assert len(calls) == 2

    limited_state = make_state(max_tool_calls=1)
    assert executor.execute(limited_state, "unknown_tool", {}, context).ok is False
    denied = executor.execute(limited_state, "unknown_tool", {}, context)
    assert denied.ok is False and "budget" in denied.error
    assert len(limited_state.tool_calls) == 1
