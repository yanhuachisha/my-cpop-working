from __future__ import annotations

from app.langchain_agent import AgentRunRequest, MusicAgent


EVAL_CASES = [
    {"id": "kg-path", "query": "周杰伦和陶喆为什么会被联系在一起？", "expected_tools": ["kg_shortest_path"], "required_terms": ["R&B"]},
    {"id": "daily", "query": "给我推荐一首今天适合听的华语歌", "expected_tools": ["daily_recommendation"], "required_terms": ["推荐"]},
    {"id": "entity", "query": "查一下方文山", "expected_tools": ["search_music"], "required_terms": ["方文山"]},
]


def evaluate_agent(agent: MusicAgent) -> dict:
    results = []
    for case in EVAL_CASES:
        run = agent.run(AgentRunRequest(query=case["query"], max_steps=6))
        tool_score = len(set(case["expected_tools"]) & set(run.tools_used)) / len(case["expected_tools"])
        grounding_score = sum(term.casefold() in run.answer.casefold() for term in case["required_terms"]) / len(case["required_terms"])
        results.append({"id": case["id"], "query": case["query"], "tool_score": tool_score, "grounding_score": grounding_score, "iterations": run.iterations, "latency_ms": run.latency_ms, "passed": tool_score == 1 and grounding_score == 1})
    return {"cases": results, "pass_rate": sum(item["passed"] for item in results) / len(results), "metrics": ["tool_selection", "answer_grounding", "iterations", "latency_ms"]}
