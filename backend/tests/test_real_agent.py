from app.agent_evaluation import evaluate_agent
from app.data_store import get_store
from app.langchain_agent import AgentRunRequest, MusicAgent, agent_status


def test_agent_fallback_keeps_tool_trace(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = MusicAgent(get_store()).run(AgentRunRequest(query="给我推荐一首今天适合听的华语歌"))
    assert result.mode.startswith("fallback")
    assert result.tools_used == ["daily_recommendation"]
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
                FakeMessage(tool_calls=[{"name": "listener_preference_profile_tool", "args": {}}]),
                FakeMessage(content='{"summary":"偏好画像"}', message_type="tool", name="listener_preference_profile_tool"),
                FakeMessage(content="你最近更偏爱温暖、熟悉的华语歌。"),
            ]}

    def fake_create_agent(model, tools, system_prompt, middleware):
        captured["tools"] = [item.name for item in tools]
        captured["system_prompt"] = system_prompt
        captured["middleware"] = middleware
        return FakeAgent()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr(langchain.agents, "create_agent", fake_create_agent)

    response = MusicAgent(get_store()).run(AgentRunRequest(
        query="你了解我的音乐偏好吗？",
        recent_messages=[{"role": "user", "content": "我工作时喜欢听歌。"}],
    ))

    assert response.mode == "langchain:react"
    assert response.tools_used == ["listener_preference_profile_tool"]
    assert response.iterations == 1
    assert "listener_preference_profile_tool" in captured["tools"]
    assert not any(name.startswith("kg_") for name in captured["tools"])
    assert captured["payload"]["messages"][0]["content"] == "我工作时喜欢听歌。"
