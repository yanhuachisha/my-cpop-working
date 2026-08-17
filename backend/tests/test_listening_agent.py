from app.data_store import get_store
from app.listening_agent import ListeningAgent, ListeningChatRequest, ListeningChatTurn, LyricAnalysisRequest
from app.models import SourceRef


def test_listening_context_has_no_demo_mode(monkeypatch):
    monkeypatch.setattr("app.listening_agent.get_now_playing", lambda: {"title": None, "artist": None, "raw_title": None, "source": "test"})
    context = ListeningAgent(get_store()).context()
    assert context.current.status == "idle"
    assert context.story is None


def test_listening_context_builds_story_for_uncatalogued_track(monkeypatch):
    monkeypatch.setattr("app.listening_agent.get_now_playing", lambda: {
        "title": "一首不在本地曲库的新歌",
        "artist": "新歌手",
        "raw_title": "一首不在本地曲库的新歌 - 新歌手",
        "source": "test",
    })
    monkeypatch.setattr("app.listening_agent.song_introduction", lambda title, artist, album, year: {
        "subtitle": f"《{title}》的独立简介",
        "narrative": f"这是为{artist}的《{title}》生成的内容。",
        "themes": ["新歌"],
        "listening_points": ["听开场", "听推进", "听收束"],
        "story_type": "ai-introduction",
        "facts": [f"演唱：{artist}"],
        "source_urls": [],
    })

    context = ListeningAgent(get_store()).context()

    assert context.current.artist == "新歌手"
    assert context.story is not None
    assert context.story.title == "一首不在本地曲库的新歌"
    assert "独立简介" in context.story.subtitle


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
