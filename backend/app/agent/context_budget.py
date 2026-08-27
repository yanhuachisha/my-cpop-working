from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.agent.state import TokenUsage


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class ConservativeTokenCounter:
    """Offline fallback; production delegates to the model-service tokenizer."""

    def count(self, text: str) -> int:
        ascii_count = sum(ord(char) < 128 for char in text)
        non_ascii_count = len(text) - ascii_count
        return max(1, non_ascii_count + (ascii_count + 3) // 4) if text else 0


@dataclass(slots=True)
class ContextItem:
    content: str
    score: float = 0.0
    item_id: str = ""
    tokens: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ContextPlan:
    system_prompt: str
    tool_prompt: str
    knowledge: list[ContextItem]
    memories: list[ContextItem]
    summary: str
    recent_history: list[dict[str, str]]
    query: str
    usage: TokenUsage


class TokenBudgetManager:
    def __init__(self, counter: TokenCounter | None = None, limit: int = 32_768) -> None:
        self.counter = counter or ConservativeTokenCounter()
        self.limit = limit

    def assemble(
        self,
        *,
        system_prompt: str,
        tool_prompt: str,
        knowledge: list[ContextItem],
        memories: list[ContextItem],
        summary: str,
        recent_history: list[dict[str, str]],
        query: str,
        output_reserved: int = 2_048,
        safety_margin: int = 1_024,
    ) -> ContextPlan:
        usage = TokenUsage(
            limit=self.limit,
            output_reserved=output_reserved,
            safety_margin=safety_margin,
        )
        usage.system = min(self.counter.count(system_prompt), 3_072)
        usage.tools = min(self.counter.count(tool_prompt), 1_024)
        usage.query = self.counter.count(query)

        selected_knowledge = self._take_ranked(knowledge, 8_000)
        usage.knowledge = sum(item.tokens for item in selected_knowledge)
        selected_memories = self._take_ranked(memories, 4_000)
        usage.memory = sum(item.tokens for item in selected_memories)

        summary_tokens = self.counter.count(summary)
        history_with_tokens = [
            ({**message}, self.counter.count(str(message.get("content", ""))))
            for message in recent_history
        ]
        mandatory_tail = history_with_tokens[-8:]  # four user/assistant turns
        optional_history = history_with_tokens[:-8]
        fixed = usage.input_total + min(summary_tokens, 2_048)
        history_budget = max(0, usage.available_input - fixed)
        mandatory_tokens = sum(tokens for _, tokens in mandatory_tail)
        selected_optional: list[tuple[dict[str, str], int]] = []
        remaining = max(0, history_budget - mandatory_tokens)
        for item in reversed(optional_history):
            if item[1] > remaining:
                continue
            selected_optional.append(item)
            remaining -= item[1]
        selected_optional.reverse()
        selected_history = [item for item, _ in [*selected_optional, *mandatory_tail]]
        usage.recent_history = sum(tokens for _, tokens in [*selected_optional, *mandatory_tail])
        usage.summary = min(summary_tokens, max(0, usage.available_input - usage.input_total))

        while usage.exceeded and selected_knowledge:
            removed = selected_knowledge.pop()
            usage.knowledge -= removed.tokens
        while usage.exceeded and selected_memories:
            removed = selected_memories.pop()
            usage.memory -= removed.tokens

        return ContextPlan(
            system_prompt=system_prompt,
            tool_prompt=tool_prompt,
            knowledge=selected_knowledge,
            memories=selected_memories,
            summary=summary if usage.summary == summary_tokens else self._truncate(summary, usage.summary),
            recent_history=selected_history,
            query=query,
            usage=usage,
        )

    def _take_ranked(self, items: list[ContextItem], budget: int) -> list[ContextItem]:
        selected: list[ContextItem] = []
        used = 0
        for item in sorted(items, key=lambda value: value.score, reverse=True):
            item.tokens = item.tokens or self.counter.count(item.content)
            if used + item.tokens > budget:
                continue
            selected.append(item)
            used += item.tokens
        return selected

    def _truncate(self, text: str, tokens: int) -> str:
        if tokens <= 0:
            return ""
        ratio = min(1.0, tokens / max(1, self.counter.count(text)))
        return text[: max(1, int(len(text) * ratio))]
