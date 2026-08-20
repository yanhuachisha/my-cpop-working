from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.langchain_agent import AgentRunRequest, AgentRunResponse, MusicAgent, inject_tool_failures


DEFAULT_DATASET_PATH = Path(__file__).resolve().parent / "evals" / "agent_benchmark.jsonl"
METRIC_NAMES = [
    "tool_recall",
    "tool_precision",
    "arg_accuracy",
    "grounding_score",
    "safety_score",
    "trajectory_score",
    "latency_score",
]


def load_eval_cases(
    suite: str = "smoke",
    dataset_path: str | Path = DEFAULT_DATASET_PATH,
) -> list[dict[str, Any]]:
    path = Path(dataset_path)
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            case = json.loads(stripped)
            suites = set(case.get("suites", []))
            if suite == "all" or suite in suites:
                case.setdefault("category", "general")
                case.setdefault("expected_tools", [])
                case.setdefault("expected_args", [])
                case.setdefault("forbidden_tools", [])
                case.setdefault("required_terms", [])
                case.setdefault("required_any_terms", [])
                case.setdefault("forbidden_terms", [])
                case["_line_no"] = line_no
                cases.append(case)
    if not cases:
        raise ValueError(f"No eval cases found for suite={suite!r} in {path}")
    return cases


def evaluate_agent(
    agent: MusicAgent,
    suite: str = "smoke",
    dataset_path: str | Path = DEFAULT_DATASET_PATH,
    algorithm: str = "auto",
    max_cases: int | None = None,
) -> dict[str, Any]:
    cases = load_eval_cases(suite=suite, dataset_path=dataset_path)
    if max_cases is not None:
        cases = cases[:max(1, max_cases)]
    results = [_run_case(agent, case, algorithm=algorithm) for case in cases]
    return _summarize(results, suite=suite, dataset_path=dataset_path, algorithm=algorithm)


def _run_case(agent: MusicAgent, case: dict[str, Any], algorithm: str) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        request = AgentRunRequest(
            query=case["query"],
            max_steps=case.get("max_steps", 8),
            algorithm=case.get("algorithm", algorithm),
            recent_messages=case.get("recent_messages", []),
        )
        with inject_tool_failures(case.get("inject_tool_failures", [])):
            run = agent.run(request)
        scores = _score_case(case, run)
        passed = all(
            [
                scores["tool_recall"] >= 1.0,
                scores["tool_precision"] >= 1.0,
                scores["arg_accuracy"] >= 1.0,
                scores["grounding_score"] >= 1.0,
                scores["safety_score"] >= 1.0,
                scores["trajectory_score"] >= 1.0,
                scores["latency_score"] >= 1.0,
            ]
        )
        return {
            **_case_header(case),
            "started_at": started_at,
            "query": case["query"],
            "answer": run.answer,
            "model": run.model,
            "provider": run.provider,
            "mode": run.mode,
            "tools_used": run.tools_used,
            "tool_calls": _tool_calls(run.trace),
            "iterations": run.iterations,
            "latency_ms": run.latency_ms,
            "scores": scores,
            "passed": passed,
            "failure_reasons": _failure_reasons(case, run, scores),
            "error": None,
        }
    except Exception as error:
        return {
            **_case_header(case),
            "started_at": started_at,
            "query": case.get("query", ""),
            "answer": "",
            "model": "",
            "provider": "",
            "mode": "",
            "tools_used": [],
            "tool_calls": [],
            "iterations": 0,
            "latency_ms": 0,
            "scores": {name: 0.0 for name in METRIC_NAMES},
            "passed": False,
            "failure_reasons": ["exception"],
            "error": f"{type(error).__name__}: {error}",
        }


def _case_header(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["id"],
        "category": case["category"],
        "suites": case.get("suites", []),
    }


def _score_case(case: dict[str, Any], run: AgentRunResponse) -> dict[str, float]:
    expected_tools = list(case.get("expected_tools", []))
    forbidden_tools = set(case.get("forbidden_tools", []))
    used_tools = list(run.tools_used)
    used_set = set(used_tools)

    if expected_tools:
        matched = len(set(expected_tools) & used_set)
        tool_recall = matched / len(set(expected_tools))
        tool_precision = matched / max(1, len(used_set))
    else:
        tool_recall = 1.0 if not used_set else 0.0
        tool_precision = 1.0 if not used_set else 0.0

    forbidden_hit = bool(forbidden_tools & used_set)
    arg_accuracy = _arg_accuracy(case.get("expected_args", []), run.trace)
    required_score = _term_score(run.answer, case.get("required_terms", []), should_exist=True)
    required_any = case.get("required_any_terms", [])
    required_any_score = (
        1.0
        if not required_any or any(term.casefold() in run.answer.casefold() for term in required_any)
        else 0.0
    )
    grounding_score = min(required_score, required_any_score)
    safety_score = _term_score(run.answer, case.get("forbidden_terms", []), should_exist=False)
    trajectory_score = _trajectory_score(case, run, forbidden_hit)
    latency_score = 1.0 if run.latency_ms <= _latency_budget(case, run) else 0.0

    return {
        "tool_recall": round(tool_recall, 4),
        "tool_precision": round(tool_precision, 4),
        "arg_accuracy": round(arg_accuracy, 4),
        "grounding_score": round(grounding_score, 4),
        "safety_score": round(safety_score, 4),
        "trajectory_score": round(trajectory_score, 4),
        "latency_score": round(latency_score, 4),
    }


def _arg_accuracy(expected_args: list[dict[str, Any]], trace: list[dict[str, Any]]) -> float:
    if not expected_args:
        return 1.0
    calls = _tool_calls(trace)
    matched = 0
    for expected in expected_args:
        expected_tool = expected["tool"]
        expected_subset = expected.get("args", {})
        for call in calls:
            if call["tool"] != expected_tool:
                continue
            if _contains_args(call.get("args", {}), expected_subset):
                matched += 1
                break
    return matched / len(expected_args)


def _contains_args(actual: dict[str, Any], expected_subset: dict[str, Any]) -> bool:
    for key, expected_value in expected_subset.items():
        if key not in actual:
            return False
        actual_value = actual[key]
        if isinstance(expected_value, dict) and "$contains" in expected_value:
            if str(expected_value["$contains"]).casefold() not in str(actual_value).casefold():
                return False
            continue
        if isinstance(expected_value, int) and isinstance(actual_value, str):
            try:
                actual_value = int(actual_value)
            except ValueError:
                pass
        if actual_value != expected_value:
            return False
    return True


def _term_score(text: str, terms: list[str], should_exist: bool) -> float:
    if not terms:
        return 1.0
    lowered = text.casefold()
    if should_exist:
        return sum(term.casefold() in lowered for term in terms) / len(terms)
    return 1.0 if all(term.casefold() not in lowered for term in terms) else 0.0


def _trajectory_score(case: dict[str, Any], run: AgentRunResponse, forbidden_hit: bool) -> float:
    if forbidden_hit:
        return 0.0
    max_iterations = case.get("max_iterations")
    if max_iterations is not None and run.iterations > max_iterations:
        return 0.0
    expected_tools = case.get("expected_tools", [])
    if expected_tools:
        called = [call["tool"] for call in _tool_calls(run.trace)]
        if not _is_subsequence(expected_tools, called):
            return 0.0
    return 1.0


def _latency_budget(case: dict[str, Any], run: AgentRunResponse) -> int:
    if run.provider == "deepseek":
        return int(case.get("max_live_latency_ms", 25_000))
    return int(case.get("max_latency_ms", 60_000))


def _is_subsequence(expected: list[str], actual: list[str]) -> bool:
    position = 0
    for item in actual:
        if position < len(expected) and item == expected[position]:
            position += 1
    return position == len(expected)


def _tool_calls(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"tool": item.get("tool", ""), "args": item.get("args", {}) or {}}
        for item in trace
        if item.get("type") == "tool_call"
    ]


def _failure_reasons(
    case: dict[str, Any],
    run: AgentRunResponse,
    scores: dict[str, float],
) -> list[str]:
    reasons = [name for name, value in scores.items() if value < 1.0]
    forbidden = sorted(set(case.get("forbidden_tools", [])) & set(run.tools_used))
    if forbidden:
        reasons.append(f"forbidden_tools:{','.join(forbidden)}")
    if run.iterations > case.get("max_iterations", 999):
        reasons.append("too_many_iterations")
    if run.latency_ms > _latency_budget(case, run):
        reasons.append("latency_budget_exceeded")
    return reasons


def _summarize(
    results: list[dict[str, Any]],
    suite: str,
    dataset_path: str | Path,
    algorithm: str,
) -> dict[str, Any]:
    passed_count = sum(item["passed"] for item in results)
    by_category: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_category.setdefault(result["category"], []).append(result)

    metrics = {
        name: round(statistics.fmean(item["scores"][name] for item in results), 4)
        for name in METRIC_NAMES
    }
    latencies = [item["latency_ms"] for item in results if item["latency_ms"] >= 0]
    summary = {
        "suite": suite,
        "algorithm": algorithm,
        "dataset_path": str(Path(dataset_path)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "pass_rate": round(passed_count / max(1, len(results)), 4),
        "metrics": metrics,
        "latency": {
            "avg_ms": round(statistics.fmean(latencies), 2) if latencies else 0,
            "max_ms": max(latencies, default=0),
        },
        "categories": {
            category: {
                "case_count": len(items),
                "pass_rate": round(sum(item["passed"] for item in items) / len(items), 4),
                "metrics": {
                    name: round(statistics.fmean(item["scores"][name] for item in items), 4)
                    for name in METRIC_NAMES
                },
            }
            for category, items in sorted(by_category.items())
        },
    }
    return {
        **summary,
        "metric_definitions": {
            "tool_recall": "Expected tool coverage.",
            "tool_precision": "Share of used tools that were expected.",
            "arg_accuracy": "Expected tool argument subset match.",
            "grounding_score": "Required answer terms present.",
            "safety_score": "Forbidden answer terms absent.",
            "trajectory_score": "Forbidden tools absent, iteration budget respected, order valid.",
            "latency_score": "Case latency is within max_latency_ms.",
        },
        "cases": results,
    }
