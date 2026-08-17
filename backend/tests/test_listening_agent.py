import pytest

from app.data_store import get_store
from app.listening_agent import ListeningAgent, ListeningChatRequest, ListeningChatTurn, ListeningStoryRequest, LyricAnalysisRequest
from app.models import SourceRef


@pytest.fixture(autouse=True)
def disable_live_model(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def test_listening_context_has_no_demo_mode(monkeypatch):
    monkeypatch.setattr("app.listening_agent.get_now_playing", lambda: {"title": None, "artist": None, "raw_title": None, "source": "test"})
    context = ListeningAgent(get_store()).context()
    assert context.current.status == "idle"
    assert context.story is None


def test_listening_context_returns_track_before_story_generation(monkeypatch):
    monkeypatch.setattr("app.listening_agent.get_now_playing", lambda: {
        "title": "一首不在本地曲库的新歌",
        "artist": "新歌手",
        "raw_title": "一首不在本地曲库的新歌 - 新歌手",
        "source": "test",
    })
    monkeypatch.setattr("app.listening_agent.cached_song_introduction", lambda title, artist: None)
    monkeypatch.setattr("app.listening_agent.song_introduction", lambda *args: pytest.fail("context must not generate story"))

    context = ListeningAgent(get_store()).context()

    assert context.current.artist == "新歌手"
    assert context.current.title == "一首不在本地曲库的新歌"
    assert context.story is None


def test_listening_story_generates_uncatalogued_track(monkeypatch):
    monkeypatch.setattr("app.listening_agent.song_introduction", lambda title, artist, album, year: {
        "subtitle": f"《{title}》的独立简介",
        "narrative": f"这是为{artist}的《{title}》生成的内容。",
        "themes": ["新歌"],
        "listening_points": ["听开场", "听推进", "听收束"],
        "story_type": "ai-introduction",
        "facts": [f"演唱：{artist}"],
        "source_urls": [],
    })

    story = ListeningAgent(get_store()).story(ListeningStoryRequest(title="一首不在本地曲库的新歌", artist="新歌手"))

    assert story.title == "一首不在本地曲库的新歌"
    assert "独立简介" in story.subtitle


def test_lyric_analysis_uses_user_excerpt_only():
    analysis = ListeningAgent(get_store()).analyze_lyrics(
        LyricAnalysisRequest(excerpt="窗外的雨慢慢落下，我还在想念从前", song_title="示例歌曲")
    )
    assert "自然景物" in analysis.imagery
    assert "怀念" in analysis.emotion
    assert "不存储" in analysis.copyright_note


def test_listening_chat_routes_to_story_tool():
    response = ListeningAgent(get_store()).chat(
        ListeningChatRequest(question="这首歌背后有什么故事？", song_title="以父之名", artist="周杰伦")
    )
    assert "build_song_introduction" in response.tools_used
    assert "声音电影" in response.answer
    assert response.mode == "fallback:rules"


def test_listening_chat_saves_lyric_specimen(monkeypatch):
    saved = {}
    monkeypatch.setattr("app.listening_agent.save_lyric_fragment", lambda request: saved.update(request.model_dump()))
    response = ListeningAgent(get_store()).chat(ListeningChatRequest(
        question="帮我收藏这句话：窗外的雨慢慢落下",
        song_title="示例歌曲",
        artist="示例歌手",
    ))
    assert saved["excerpt"] == "窗外的雨慢慢落下"
    assert "save_lyric_specimen" in response.tools_used


def test_listening_chat_saves_previous_feeling(monkeypatch):
    saved = {}
    monkeypatch.setattr("app.listening_agent.save_music_note", lambda request: saved.update(request.model_dump()))
    response = ListeningAgent(get_store()).chat(ListeningChatRequest(
        question="记下刚才的感受",
        song_title="示例歌曲",
        recent_messages=[ListeningChatTurn(role="user", content="这首歌让我想起放学后的雨。")],
    ))
    assert saved["content"] == "这首歌让我想起放学后的雨。"
    assert "save_music_note" in response.tools_used


def test_listening_chat_routes_to_similar_recommendations():
    response = ListeningAgent(get_store()).chat(ListeningChatRequest(question="推荐类似的歌", song_title="七里香"))
    assert "find_similar_recordings" in response.tools_used


def test_listening_chat_routes_to_verified_web_story(monkeypatch):
    agent = ListeningAgent(get_store())
    monkeypatch.setattr(agent, "_research_song_story", lambda request: (
        "这是基于公开资料整理的歌曲故事。",
        [SourceRef(name="测试来源", url="https://example.com", license="Test")],
    ))
    response = agent.chat(ListeningChatRequest(question="查一下这首歌真实的创作故事", song_title="示例歌曲"))
    assert "search_song_story_web" in response.tools_used
    assert response.sources[0].name == "测试来源"


def test_listening_write_tools_require_explicit_current_intent():
    assert ListeningAgent._has_explicit_save_intent("记下刚才的感受") is True
    assert ListeningAgent._has_explicit_save_intent("帮我收藏这句话") is True
    assert ListeningAgent._has_explicit_save_intent("推荐三首情绪接近的歌") is False


def test_listening_chat_extracts_real_agent_loop(monkeypatch):
    from app import listening_agent

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
                FakeMessage(tool_calls=[{"name": "find_similar_recordings", "args": {}}]),
                FakeMessage(content='{"recommendation":"推荐结果"}', message_type="tool", name="find_similar_recordings"),
                FakeMessage(content="可以接着听三首情绪相近的歌。"),
            ]}

    def fake_create_agent(model, tools, system_prompt, middleware):
        captured["tools"] = [item.name for item in tools]
        captured["system_prompt"] = system_prompt
        captured["middleware"] = middleware
        return FakeAgent()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(listening_agent, "ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr(listening_agent, "create_agent", fake_create_agent)

    response = ListeningAgent(get_store()).chat(ListeningChatRequest(
        question="推荐类似的歌",
        song_title="七里香",
        artist="周杰伦",
        recent_messages=[ListeningChatTurn(role="user", content="我喜欢这种夏天的感觉")],
    ))

    assert response.mode == "langchain:react"
    assert response.tools_used == ["find_similar_recordings"]
    assert response.iterations == 1
    assert "find_similar_recordings" in captured["tools"]
    assert "只围绕此刻正在播放的这一首歌" in captured["system_prompt"]
    assert "细腻" in captured["system_prompt"]
    assert captured["payload"]["messages"][0]["role"] == "user"
