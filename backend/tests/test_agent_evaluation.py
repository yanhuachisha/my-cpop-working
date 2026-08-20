import pytest
from fastapi.testclient import TestClient

from app import langchain_agent, listener_memory
from app.agent_evaluation import _run_case, evaluate_agent, load_eval_cases
from app.data_store import get_store
from app.langchain_agent import AgentRunResponse, MusicAgent
from app.main import app


@pytest.fixture(autouse=True)
def isolate_eval_state(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(listener_memory, "STATE_PATH", tmp_path / "listener_state.json")
    langchain_agent._HYDRATED_THREADS.clear()


def test_agent_benchmark_dataset_is_structured():
    full_cases = load_eval_cases("full")
    smoke_cases = load_eval_cases("smoke")

    assert len(full_cases) == 125
    assert len(smoke_cases) == 10
    category_counts = {
        category: sum(case["category"] == category for case in full_cases)
        for category in {case["category"] for case in full_cases}
    }
    assert category_counts == {
        "recommendation": 20,
        "music_search": 15,
        "listening_history": 15,
        "memory": 15,
        "multi_turn": 15,
        "tool_failure": 15,
        "safety": 20,
        "no_tool": 10,
    }
    assert sum(bool(case.get("recent_messages")) for case in full_cases) == 15
    assert sum(bool(case.get("inject_tool_failures")) for case in full_cases) == 15
    assert any(case["expected_args"] for case in full_cases)


def test_offline_agent_smoke_benchmark_is_reproducible():
    report = evaluate_agent(MusicAgent(get_store()), suite="smoke")

    assert report["case_count"] == 10
    assert report["pass_rate"] == 1.0
    assert report["metrics"]["tool_recall"] == 1.0
    assert report["metrics"]["arg_accuracy"] == 1.0
    assert report["failed_count"] == 0


def test_agent_history_case_scores_tool_arguments():
    report = evaluate_agent(MusicAgent(get_store()), suite="history", max_cases=1)
    case = report["cases"][0]

    assert case["passed"] is True
    assert case["tools_used"] == ["query_listening_history"]
    assert case["tool_calls"][0]["args"]["period"] == "today"
    assert case["scores"]["arg_accuracy"] == 1.0


def test_agent_evaluation_api_accepts_suite_and_algorithm():
    response = TestClient(app).get("/api/agent/evaluate?suite=smoke&algorithm=auto")

    assert response.status_code == 200
    payload = response.json()
    assert payload["suite"] == "smoke"
    assert payload["case_count"] == 10
    assert payload["pass_rate"] == 1.0


def test_agent_evaluation_rejects_unexpected_extra_tools():
    class ExtraToolAgent:
        def run(self, _request):
            return AgentRunResponse(
                session_id="eval-extra-tool",
                answer="推荐一首歌。",
                model="test",
                provider="test",
                mode="test",
                tools_used=["recommend_music", "search_music"],
                trace=[
                    {"type": "tool_call", "tool": "recommend_music", "args": {"limit": 1, "mode": "auto"}},
                    {"type": "tool_call", "tool": "search_music", "args": {"query": "歌", "limit": 8}},
                ],
                iterations=2,
                latency_ms=1,
            )

    result = _run_case(
        ExtraToolAgent(),
        {
            "id": "extra_tool",
            "category": "trajectory",
            "query": "推荐一首歌",
            "expected_tools": ["recommend_music"],
            "expected_args": [{"tool": "recommend_music", "args": {"limit": 1, "mode": "auto"}}],
            "required_terms": ["推荐"],
            "forbidden_terms": [],
            "forbidden_tools": [],
            "max_iterations": 2,
            "max_latency_ms": 1000,
        },
        algorithm="auto",
    )

    assert result["scores"]["tool_precision"] == 0.5
    assert result["passed"] is False
    assert "tool_precision" in result["failure_reasons"]
