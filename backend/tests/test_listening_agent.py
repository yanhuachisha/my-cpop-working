import pytest
from langgraph.errors import GraphRecursionError

from app.data_store import get_store
from app.listening_agent import ListeningAgent, ListeningChatRequest, ListeningChatTurn, ListeningStoryRequest, LyricAnalysisRequest


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


def test_listening_chat_answers_cached_story_without_fake_tool_trace():
    response = ListeningAgent(get_store()).chat(
        ListeningChatRequest(question="这首歌背后有什么故事？", song_title="以父之名", artist="周杰伦")
    )
    assert response.tools_used == []
    assert "声音电影" in response.answer
    assert response.mode == "fallback:rules"


def test_listening_chat_asks_for_excerpt_when_lyric_analysis_has_no_excerpt():
    response = ListeningAgent(get_store()).chat(ListeningChatRequest(
        question="分析一下这首歌的主歌歌词",
        song_title="示例歌曲",
    ))

    assert "把主歌中你最在意的几句贴给我" in response.answer
    assert "我会先读取当前歌曲" not in response.answer


def test_listening_chat_fallback_responds_to_feeling_without_system_copy():
    response = ListeningAgent(get_store()).chat(ListeningChatRequest(
        question="这个歌太夸了",
        song_title="素颜",
        artist="许嵩, 何曼婷",
    ))

    assert "我会先读取当前歌曲" not in response.answer
    assert "最“夸”的地方" in response.answer
    assert response.sources == []


def test_listening_chat_rejects_placeholder_model_answer(monkeypatch):
    agent = ListeningAgent(get_store())
    monkeypatch.setattr(
        agent,
        "_invoke_ai",
        lambda *_: "我这边好像只收到一串占位符，没有看到具体的歌曲信息呢。",
    )

    answer = agent._ai_companion_answer(
        ListeningChatRequest(question="这个歌太夸了", song_title="素颜", artist="许嵩"),
        None,
    )

    assert answer is None


def test_listening_chat_analyzes_excerpt_from_lyric_analysis_query():
    response = ListeningAgent(get_store()).chat(ListeningChatRequest(
        question="分析一下这首歌的主歌歌词",
        song_title="示例歌曲",
        lyric_excerpt="窗外的雨慢慢落下，我还在想念从前",
    ))

    assert "示例歌曲" in response.answer
    assert "自然景物" in response.answer


def test_listening_chat_saves_lyric_specimen(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "app.listening_agent.save_listening_memory_workflow",
        lambda memory_type, content, song_title, artist: saved.update({
            "memory_type": memory_type,
            "content": content,
            "song_title": song_title,
            "artist": artist,
        }) or {"saved": True},
    )
    response = ListeningAgent(get_store()).chat(ListeningChatRequest(
        question="帮我收藏这句话：窗外的雨慢慢落下",
        song_title="示例歌曲",
        artist="示例歌手",
    ))
    assert saved["memory_type"] == "lyric_specimen"
    assert saved["content"] == "窗外的雨慢慢落下"
    assert "save_listening_memory" in response.tools_used


def test_listening_chat_saves_previous_feeling(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "app.listening_agent.save_listening_memory_workflow",
        lambda memory_type, content, song_title, artist: saved.update({
            "memory_type": memory_type,
            "content": content,
            "song_title": song_title,
            "artist": artist,
        }) or {"saved": True},
    )
    response = ListeningAgent(get_store()).chat(ListeningChatRequest(
        question="记下刚才的感受",
        song_title="示例歌曲",
        recent_messages=[ListeningChatTurn(role="user", content="这首歌让我想起放学后的雨。")],
    ))
    assert saved["content"] == "这首歌让我想起放学后的雨。"
    assert saved["memory_type"] == "music_note"
    assert "save_listening_memory" in response.tools_used


def test_listening_chat_routes_to_similar_recommendations():
    response = ListeningAgent(get_store()).chat(ListeningChatRequest(question="推荐类似的歌", song_title="七里香"))
    assert "find_similar_recordings" in response.tools_used


def test_listening_chat_routes_to_verified_web_story(monkeypatch):
    monkeypatch.setattr("app.listening_agent.web_search_workflow", lambda query, song_title, artist: {
        "available": True,
        "facts": ["这是基于网页搜索和正文读取到的歌曲事实。"],
        "sources": [{"name": "测试来源", "url": "https://example.com", "license": "Test"}],
        "documents": [{"title": "测试网页", "url": "https://example.com", "text": "正文"}],
        "errors": [],
    })
    response = ListeningAgent(get_store()).chat(
        ListeningChatRequest(question="查一下这首歌真实的创作故事", song_title="示例歌曲")
    )
    assert "web_search" in response.tools_used
    assert "可核实线索" in response.answer
    assert response.sources[0].name == "测试来源"


def test_listening_chat_routes_public_impact_research(monkeypatch):
    monkeypatch.setattr("app.listening_agent.research_song_public_impact_workflow", lambda title, artist, question: {
        "available": True,
        "facts": [
            "测试资料：发行于 2003 年。",
            "测试资料：获得多个公开讨论中的传播线索。",
        ],
        "sources": [{"name": "测试百科", "url": "https://example.com/impact", "license": "Test"}],
        "search_queries": [],
        "answer_guidance": [],
        "errors": [],
    })
    response = ListeningAgent(get_store()).chat(
        ListeningChatRequest(question="布拉格广场当年有多火", song_title="布拉格广场", artist="蔡依林")
    )
    assert response.tools_used == ["research_song_public_impact"]
    assert "## 《布拉格广场》当年到底有多火" in response.answer
    assert "可核实线索" in response.answer
    assert response.sources[0].name == "测试百科"


def test_listening_write_tools_require_explicit_current_intent():
    assert ListeningAgent._has_explicit_save_intent("记下刚才的感受") is True
    assert ListeningAgent._has_explicit_save_intent("帮我收藏这句话") is True
    assert ListeningAgent._has_explicit_save_intent("推荐三首情绪接近的歌") is False


def test_conversation_is_saved_for_the_current_song_even_when_paused(monkeypatch):
    saved = []
    monkeypatch.setattr("app.listening_agent.get_now_playing", lambda: {
        "is_playing": False,
        "title": "七里香",
        "artist": "周杰伦",
    })
    monkeypatch.setattr("app.listening_agent.save_listening_conversation_turn", lambda *args: saved.append(args))

    ListeningAgent(get_store()).chat(ListeningChatRequest(
        question="推荐类似的歌",
        song_title="七里香",
        artist="周杰伦",
    ))

    assert saved and saved[0][:2] == ("七里香", "周杰伦")


def test_conversation_is_not_saved_after_song_changes(monkeypatch):
    saved = []
    monkeypatch.setattr("app.listening_agent.get_now_playing", lambda: {
        "is_playing": True,
        "title": "晴天",
        "artist": "周杰伦",
    })
    monkeypatch.setattr("app.listening_agent.save_listening_conversation_turn", lambda *args: saved.append(args))

    ListeningAgent(get_store()).chat(ListeningChatRequest(
        question="推荐类似的歌",
        song_title="七里香",
        artist="周杰伦",
    ))

    assert saved == []


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
    assert "get_current_song_context" in captured["tools"]
    assert "save_listening_memory" in captured["tools"]
    assert "search_song_sources" in captured["tools"]
    assert "web_search" in captured["tools"]
    assert "research_song_public_impact" in captured["tools"]
    assert "save_lyric_specimen" not in captured["tools"]
    assert "save_current_feeling" not in captured["tools"]
    assert "analyze_lyric_excerpt" not in captured["tools"]
    assert "search_song_story_web" not in captured["tools"]
    assert "只围绕此刻正在播放的这一首歌" in captured["system_prompt"]
    assert "细腻" in captured["system_prompt"]
    assert captured["payload"]["messages"][0]["role"] == "user"


def test_listening_chat_falls_back_when_agent_loop_reaches_recursion_limit(monkeypatch):
    agent = ListeningAgent(get_store())

    def raise_recursion(*args):
        raise GraphRecursionError("loop")

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(agent, "_is_current_song", lambda *args: False)
    monkeypatch.setattr(agent, "_langchain_chat", raise_recursion)
    monkeypatch.setattr(agent, "_fallback_chat", lambda *args, **kwargs: "fallback")

    response = agent.chat(ListeningChatRequest(question="鎴戞兂鍚繖棣栨瓕", song_title="澶╁ぉ榛戯紝"))

    assert response == "fallback"
