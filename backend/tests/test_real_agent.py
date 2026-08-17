import pytest

from app import langchain_agent, listener_memory
from app.agent_evaluation import evaluate_agent
from app.data_store import get_store
from app.langchain_agent import AgentRunRequest, MusicAgent, agent_status


@pytest.fixture(autouse=True)
def isolate_agent_memory(monkeypatch, tmp_path):
    monkeypatch.setattr(listener_memory, "STATE_PATH", tmp_path / "listener_state.json")
    langchain_agent._HYDRATED_THREADS.clear()


def test_agent_fallback_keeps_tool_trace(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = MusicAgent(get_store()).run(AgentRunRequest(query="给我推荐一首今天适合听的华语歌"))
    assert result.mode.startswith("fallback")
    assert result.tools_used == ["recommend_music"]
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
    assert agent_status()["llm_agent_count"] == 3
    assert "search_song_material" in agent_status()["tools"]
    assert "save_listening_memory" in agent_status()["tools"]
    assert "search_song_sources" in agent_status()["tools"]
    assert "analyze_lyric_excerpt" not in agent_status()["tools"]
    assert "search_song_story_web" not in agent_status()["tools"]


def test_music_assistant_uses_real_langchain_loop(monkeypatch):
    import langchain.agents
    import langchain_openai

    captured = {}

    class FakeMessage:
        def __init__(self, content="", message_type="ai", name=None, tool_calls=None):
            self.content = content
            self.type = message_type
            self.name = name
            self.tool_calls = tool_calls or []

    class FakeAgent:
        def invoke(self, payload, config):
            captured["payload"] = payload
            captured["config"] = config
            return {"messages": [
                FakeMessage(tool_calls=[{"name": "query_listener_memory", "args": {"scope": "long_term"}}]),
                FakeMessage(content='{"summary":"偏好画像"}', message_type="tool", name="query_listener_memory"),
                FakeMessage(content="你最近更偏爱温暖、熟悉的华语歌。"),
            ]}

    def fake_create_agent(model, tools, system_prompt, middleware, checkpointer):
        captured["tools"] = [item.name for item in tools]
        captured["system_prompt"] = system_prompt
        captured["middleware"] = middleware
        captured["checkpointer"] = checkpointer
        return FakeAgent()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr(langchain.agents, "create_agent", fake_create_agent)

    response = MusicAgent(get_store()).run(AgentRunRequest(
        query="你了解我的音乐偏好吗？",
        recent_messages=[{"role": "user", "content": "我工作时喜欢听歌。"}],
    ))

    assert response.mode == "langchain:react"
    assert response.tools_used == ["query_listener_memory"]
    assert response.iterations == 1
    assert "recommend_music" in captured["tools"]
    assert "query_listener_memory" in captured["tools"]
    assert "query_listening_history" in captured["tools"]
    assert "daily_recommendation" not in captured["tools"]
    assert "hybrid_recommendation" not in captured["tools"]
    assert "listener_emotion_memory" not in captured["tools"]
    assert "listener_preference_profile_tool" not in captured["tools"]
    assert "weekly_listening_report" not in captured["tools"]
    assert "全能、偏理性" in captured["system_prompt"]
    assert "先给结论" in captured["system_prompt"]
    assert captured["payload"]["messages"][0]["content"] == "我工作时喜欢听歌。"
    assert captured["config"]["configurable"]["thread_id"] == response.session_id
    assert captured["checkpointer"] is langchain_agent._AGENT_CHECKPOINTER
    saved = listener_memory.agent_session(response.session_id)
    assert [message["role"] for message in saved["messages"]] == ["user", "assistant"]
