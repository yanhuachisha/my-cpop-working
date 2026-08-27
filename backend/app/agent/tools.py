from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, replace
from enum import StrEnum
from threading import Lock
from typing import Any, Callable

from jsonschema import Draft202012Validator, ValidationError, validate
from pydantic import BaseModel, Field

from app.agent.state import AgentState, Observation, ToolCallRecord


class ToolType(StrEnum):
    READ = "read"
    WRITE = "write"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolSchema(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    description: str = Field(min_length=1, max_length=500)
    input_schema: dict[str, Any]
    tool_type: ToolType
    risk_level: RiskLevel = RiskLevel.LOW
    timeout: float = Field(default=5.0, gt=0, le=30)
    idempotent: bool = True
    required_permission: str
    result_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    schema: ToolSchema
    handler: Callable[[dict[str, Any], "ToolExecutionContext"], Any]


@dataclass(slots=True)
class ToolExecutionContext:
    user_id: str
    tenant_id: str
    permissions: set[str]
    confirmed_risks: set[str]
    idempotency_store: dict[str, Any]
    idempotency_key: str = ""
    trace_id: str = ""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._frozen = False

    def register(self, schema: ToolSchema, handler: Callable[[dict[str, Any], ToolExecutionContext], Any]) -> None:
        if self._frozen:
            raise RuntimeError("tool registry is frozen")
        if schema.name in self._tools:
            raise ValueError(f"duplicate tool: {schema.name}")
        Draft202012Validator.check_schema(schema.input_schema)
        self._tools[schema.name] = RegisteredTool(schema, handler)

    def freeze(self) -> None:
        self._frozen = True

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as error:
            raise KeyError(f"unknown tool: {name}") from error

    def schemas(self) -> list[ToolSchema]:
        return [item.schema for item in self._tools.values()]


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._failures: Counter[str] = Counter()
        self._opened_until: dict[str, float] = {}
        self._lock = Lock()

    def before_call(self, name: str) -> None:
        with self._lock:
            opened_until = self._opened_until.get(name, 0.0)
            if opened_until > time.monotonic():
                raise RuntimeError(f"circuit breaker open: {name}")
            if opened_until:
                self._opened_until.pop(name, None)
                self._failures[name] = 0

    def success(self, name: str) -> None:
        with self._lock:
            self._failures[name] = 0
            self._opened_until.pop(name, None)

    def failure(self, name: str) -> None:
        with self._lock:
            self._failures[name] += 1
            if self._failures[name] >= self.failure_threshold:
                self._opened_until[name] = time.monotonic() + self.reset_seconds


_SHARED_CIRCUIT_BREAKER = CircuitBreaker()


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        max_per_tool: int = 2,
        observation_limit: int = 4_000,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.registry = registry
        self.max_per_tool = max_per_tool
        self.observation_limit = observation_limit
        self.circuit_breaker = circuit_breaker or _SHARED_CIRCUIT_BREAKER

    def execute(
        self,
        state: AgentState,
        name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> Observation:
        logical = json.dumps({"name": name, "arguments": arguments}, ensure_ascii=False, sort_keys=True)
        call_id = f"tool-{hashlib.sha256(logical.encode()).hexdigest()[:24]}"
        budget_error = self._budget_error(state, name)
        if budget_error:
            state.finalizing = True
            observation = Observation(call_id=call_id, tool=name, ok=False, error=budget_error)
            state.observations.append(observation)
            return observation
        record = ToolCallRecord(call_id=call_id, name=name, args=self._sanitize(arguments))
        state.tool_calls.append(record)
        started = time.perf_counter()
        try:
            tool = self.registry.get(name)
            self._authorize(tool.schema, context)
            validate(instance=arguments, schema=tool.schema.input_schema)
            self.circuit_breaker.before_call(name)
            idempotency_key = f"{state.run_id}:{call_id}"
            invocation_context = replace(context, idempotency_key=idempotency_key)
            if tool.schema.tool_type == ToolType.WRITE and idempotency_key in context.idempotency_store:
                result = context.idempotency_store[idempotency_key]
            else:
                timeout = min(tool.schema.timeout, state.remaining_seconds)
                if timeout <= 0:
                    raise TimeoutError("agent deadline exceeded")
                pool = ThreadPoolExecutor(max_workers=1)
                try:
                    future = pool.submit(tool.handler, arguments, invocation_context)
                    try:
                        result = future.result(timeout=timeout)
                    except FutureTimeoutError as error:
                        future.cancel()
                        raise TimeoutError(f"tool {name} timed out") from error
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)
                if tool.schema.tool_type == ToolType.WRITE:
                    context.idempotency_store[idempotency_key] = result
            self.circuit_breaker.success(name)
            record.status = "success"
            observation = Observation(
                call_id=call_id,
                tool=name,
                ok=True,
                content=self._sanitize_result(result, tool.schema),
            )
        except PermissionError as error:
            record.status = "denied"
            observation = Observation(call_id=call_id, tool=name, ok=False, error=str(error))
        except TimeoutError as error:
            self.circuit_breaker.failure(name)
            record.status = "timeout"
            observation = Observation(call_id=call_id, tool=name, ok=False, error=str(error))
        except (ValidationError, ValueError, KeyError, RuntimeError) as error:
            record.status = "error"
            observation = Observation(call_id=call_id, tool=name, ok=False, error=str(error))
        except Exception as error:
            self.circuit_breaker.failure(name)
            record.status = "error"
            observation = Observation(
                call_id=call_id,
                tool=name,
                ok=False,
                error=f"{type(error).__name__}: {error}",
            )
        record.latency_ms = int((time.perf_counter() - started) * 1000)
        state.observations.append(observation)
        return observation

    def _authorize(self, schema: ToolSchema, context: ToolExecutionContext) -> None:
        if schema.required_permission not in context.permissions:
            raise PermissionError(f"missing permission: {schema.required_permission}")
        if schema.tool_type == ToolType.WRITE and schema.risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH}:
            if schema.name not in context.confirmed_risks:
                raise PermissionError(f"explicit confirmation required for {schema.name}")

    def _budget_error(self, state: AgentState, name: str) -> str | None:
        if state.finalizing or state.remaining_seconds <= 0 or state.token_usage.exceeded:
            return "agent step, token, or deadline budget exhausted"
        if len(state.tool_calls) >= state.max_tool_calls:
            return "tool call budget exceeded"
        counts = Counter(item.name for item in state.tool_calls)
        if counts[name] >= self.max_per_tool:
            return f"per-tool call budget exceeded: {name}"
        return None

    def _sanitize_result(self, value: Any, schema: ToolSchema) -> Any:
        if schema.result_fields and isinstance(value, dict):
            value = {key: value[key] for key in schema.result_fields if key in value}
        return self._sanitize(value)

    def _sanitize(self, value: Any) -> Any:
        raw = json.dumps(value, ensure_ascii=False, default=str)
        raw = re.sub(r"(?i)(api[_-]?key|password|authorization)(\s*[=:]\s*)[^,}\s]+", r"\1\2***", raw)
        if len(raw) > self.observation_limit:
            raw = raw[: self.observation_limit] + "..."
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
