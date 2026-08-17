from app.agent_evaluation import evaluate_agent
from app.data_store import get_store
from app.knowledge_graph import MusicKnowledgeGraph
from app.langchain_agent import AgentRunRequest, MusicAgent, agent_status


def test_kg_shortest_path_is_explainable():
    result = MusicKnowledgeGraph(get_store()).shortest_path("jay-chou", "tao")
    assert result["found"] is True
    assert "r&b" in result["summary"].lower()


def test_agent_fallback_keeps_tool_trace(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = MusicAgent(get_store()).run(AgentRunRequest(query="周杰伦和陶喆为什么会被联系在一起？"))
    assert result.mode.startswith("fallback")
    assert result.tools_used == ["kg_shortest_path"]
    assert result.trace[0]["type"] == "tool_call"


def test_offline_agent_evaluation_is_reproducible(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = evaluate_agent(MusicAgent(get_store()))
    assert result["pass_rate"] == 1.0


def test_agent_status_exposes_deepseek_configuration(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    assert agent_status()["configured"] is True
    assert agent_status()["provider"] == "DeepSeek"
    assert agent_status()["model"] == "deepseek-v4-flash"
    assert agent_status()["llm_agent_count"] == 2
    assert "search_song_material" in agent_status()["tools"]
