from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.agent.context_budget import TokenBudgetManager
from app.agent.memory import MemoryAuthorityClient, MemoryCandidate, MemoryTriggerPolicy
from app.agent.providers.model_service import ModelServiceClient
from app.agent.retrieval import ElasticsearchHybridRetriever, RetrievalBundle, RetrievalScope
from app.agent.session_store import COMPACT_AT, InMemorySessionStore, RedisSessionStore, SessionContext
from app.agent.state import AgentState


@dataclass(slots=True)
class PreparedRun:
    state: AgentState
    session: SessionContext
    trusted_context: str
    original_query: str
    intent_result: dict[str, Any]


class ProductionAgentRuntime:
    def __init__(
        self,
        *,
        model_client: ModelServiceClient | None = None,
        session_store: Any | None = None,
        retriever: ElasticsearchHybridRetriever | None = None,
        memory_client: MemoryAuthorityClient | None = None,
    ) -> None:
        self.model_client = model_client or ModelServiceClient()
        self.session_store = session_store or self._session_store()
        self.retriever = retriever
        self.memory_client = memory_client or MemoryAuthorityClient()
        self.trigger_policy = MemoryTriggerPolicy()

    @classmethod
    def enabled(cls) -> bool:
        return os.getenv("AGENT_PLATFORM_ENABLED", "false").casefold() in {"1", "true", "yes"}

    def prepare(
        self,
        *,
        query: str,
        user_id: str,
        session_id: str,
        tenant_id: str,
        max_steps: int,
        timeout_ms: int,
    ) -> PreparedRun:
        started_at = datetime.now(UTC)
        state = AgentState(
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_id,
            max_steps=max_steps,
            started_at=started_at,
            deadline=started_at + timedelta(milliseconds=min(timeout_ms, 60_000)),
        )
        try:
            session = self.session_store.load(user_id, session_id, limit=24)
        except Exception:
            state.degraded_dependencies.append("redis")
            session = SessionContext(summary=self._empty_summary(), recent_messages=[], token_budget={})
        intent = self.model_client.classify_intent(query, session.recent_messages)
        state.intent = str(intent.get("intent", "unknown"))
        state.entities = list(intent.get("entities", []))
        if intent.get("degraded"):
            state.degraded_dependencies.append("qwen3-0.6b")

        bundle = RetrievalBundle([], [], [], [])
        if intent.get("needs_rag") or intent.get("needs_memory"):
            try:
                retriever = self.retriever or ElasticsearchHybridRetriever.from_env()
                bundle = retriever.retrieve(
                    query,
                    RetrievalScope(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        permissions=frozenset({"knowledge.read"}),
                    ),
                    include_knowledge=bool(intent.get("needs_rag")),
                    include_memory=True,
                )
            except Exception:
                bundle.degraded.append("elasticsearch")
        state.degraded_dependencies.extend(bundle.degraded)
        state.retrieved_chunks = [item.metadata for item in [*bundle.knowledge, *bundle.memories]]
        state.citations = bundle.citations

        budget = TokenBudgetManager(counter=self.model_client).assemble(
            system_prompt="你是可信的华语音乐业务 Agent。事实回答必须依据检索证据并返回引用。",
            tool_prompt="工具调用必须遵守权限、风险、幂等、步骤和 deadline 约束。",
            knowledge=bundle.knowledge,
            memories=bundle.memories,
            summary=session.summary.content,
            recent_history=session.recent_messages,
            query=query,
        )
        state.token_usage = budget.usage
        state.context_summary = budget.summary
        trusted_context = self._render_context(budget)
        state.degraded_dependencies = list(dict.fromkeys(state.degraded_dependencies))
        return PreparedRun(state, session, trusted_context, query, intent)

    def finalize(self, prepared: PreparedRun, answer: str) -> None:
        state = prepared.state
        try:
            self.session_store.append(state.user_id, state.session_id, "user", prepared.original_query)
            self.session_store.append(state.user_id, state.session_id, "assistant", answer)
            state.token_usage.output_actual = self.model_client.count(answer)
            try:
                self.memory_client.audit_turn(
                    user_id=state.user_id,
                    tenant_id=state.tenant_id,
                    session_id=state.session_id,
                    user_message_id=f"{state.run_id}:user",
                    user_content=prepared.original_query,
                    user_tokens=state.token_usage.query,
                    assistant_message_id=f"{state.run_id}:assistant",
                    assistant_content=answer,
                    assistant_tokens=state.token_usage.output_actual,
                    trace_id=state.trace_id,
                )
            except Exception:
                state.degraded_dependencies.append("mysql-audit")
            self.session_store.update_budget(
                state.user_id,
                state.session_id,
                {key: int(value) for key, value in state.token_usage.model_dump().items()},
            )
            refreshed = self.session_store.load(state.user_id, state.session_id, limit=256)
            token_ratio = (state.token_usage.input_total + state.token_usage.output_actual) / state.token_usage.limit
            if len(refreshed.recent_messages) >= COMPACT_AT or token_ratio >= 0.75:
                self.session_store.compact(state.user_id, state.session_id, self.model_client)
            user_turns = sum(item.get("role") == "user" for item in refreshed.recent_messages)
            if self.trigger_policy.should_extract(
                user_turn_count=user_turns,
                token_ratio=token_ratio,
                memory_worthy=bool(prepared.intent_result.get("memory_worthy")),
                entities=state.entities,
                query=prepared.original_query,
                idle_minutes=self._idle_minutes(prepared.session),
            ):
                extraction_messages = refreshed.recent_messages[-10:]
                candidates = self.model_client.extract_memory(extraction_messages)
                state.memory_candidates = candidates
                for index, raw in enumerate(candidates):
                    candidate = MemoryCandidate.model_validate(raw)
                    self.memory_client.save(
                        candidate,
                        user_id=state.user_id,
                        tenant_id=state.tenant_id,
                        idempotency_key=f"{state.run_id}:memory:{index}",
                        trace_id=state.trace_id,
                    )
        except Exception:
            state.degraded_dependencies.append("memory-persistence")
            state.degraded_dependencies = list(dict.fromkeys(state.degraded_dependencies))

    @staticmethod
    def _render_context(plan: Any) -> str:
        sections = []
        if plan.summary:
            sections.append(f"会话摘要（不含后面的最近原文）：\n{plan.summary}")
        if plan.knowledge:
            sections.append("RAG 知识：\n" + "\n".join(f"[{item.item_id}] {item.content}" for item in plan.knowledge))
        if plan.memories:
            sections.append("用户长期记忆：\n" + "\n".join(f"[{item.item_id}] {item.content}" for item in plan.memories))
        if plan.recent_history:
            sections.append("最近原始对话：\n" + "\n".join(f"{item['role']}: {item['content']}" for item in plan.recent_history))
        return "\n\n".join(sections)

    @staticmethod
    def _session_store() -> Any:
        try:
            store = RedisSessionStore.from_env()
            store.client.ping()
            return store
        except Exception:
            return InMemorySessionStore()

    @staticmethod
    def _idle_minutes(session: SessionContext) -> float:
        if not session.recent_messages:
            return 0.0
        try:
            timestamp_ms = int(session.recent_messages[-1]["id"].split("-", 1)[0])
        except (KeyError, TypeError, ValueError):
            return 0.0
        if timestamp_ms < 1_000_000_000_000:
            return 0.0
        last_activity = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
        return max(0.0, (datetime.now(UTC) - last_activity).total_seconds() / 60)

    @staticmethod
    def _empty_summary():
        from app.agent.session_store import ConversationSummary

        return ConversationSummary()
