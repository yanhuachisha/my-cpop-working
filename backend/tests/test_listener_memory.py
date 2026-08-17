from datetime import datetime

from app import listener_memory
from app.listener_memory import FeedbackRequest


def test_favorite_recording_keeps_first_saved_time(monkeypatch, tmp_path):
    monkeypatch.setattr(listener_memory, "STATE_PATH", tmp_path / "listener_state.json")
    request = FeedbackRequest(recording_id="jay-chou-qilixiang-song", action="like", channel="today")

    listener_memory.record_feedback(request)
    first_saved_at = listener_memory.favorite_recordings()[0]["saved_at"]
    listener_memory.record_feedback(request)
    favorite = listener_memory.favorite_recordings()[0]

    assert favorite["title"] == "七里香"
    assert favorite["artist"] == "周杰伦"
    assert favorite["saved_at"] == first_saved_at


def test_listening_conversation_is_persisted_per_song(monkeypatch, tmp_path):
    monkeypatch.setattr(listener_memory, "STATE_PATH", tmp_path / "listener_state.json")

    listener_memory.save_listening_conversation_turn("歌曲甲", "歌手甲", "你听到了什么？", "我听到了一点克制。")

    messages = listener_memory.listening_conversation("歌曲甲", "歌手甲")
    assert [message["role"] for message in messages] == ["user", "agent"]
    assert listener_memory.listening_conversation("歌曲乙", "歌手甲") == []


def test_daily_listening_is_persisted_and_ranked(monkeypatch, tmp_path):
    state_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)
    listened_at = datetime.fromisoformat("2026-08-17T10:00:00+08:00")

    listener_memory.record_daily_listening("song-a", "晴天", "周杰伦", 35, listened_at)
    listener_memory.record_daily_listening("song-b", "小宇", "张震岳", 80, listened_at)
    listener_memory.record_daily_listening("song-a", "晴天", "周杰伦", 30, listened_at)

    stats = listener_memory.today_listening_stats(listened_at)

    assert state_path.exists()
    assert stats["total_seconds"] == 145
    assert stats["formatted_duration"] == "2 分钟"
    assert stats["track_count"] == 2
    assert [item["recording_id"] for item in stats["ranking"]] == ["song-b", "song-a"]
    assert stats["ranking"][0]["formatted_duration"] == "1 分钟"


def test_daily_listening_uses_separate_date_buckets(monkeypatch, tmp_path):
    monkeypatch.setattr(listener_memory, "STATE_PATH", tmp_path / "listener_state.json")
    first_day = datetime.fromisoformat("2026-08-16T23:59:00+08:00")
    second_day = datetime.fromisoformat("2026-08-17T00:01:00+08:00")

    listener_memory.record_daily_listening("song-a", "晴天", "周杰伦", 40, first_day)
    listener_memory.record_daily_listening("song-a", "晴天", "周杰伦", 25, second_day)

    assert listener_memory.today_listening_stats(first_day)["total_seconds"] == 40
    assert listener_memory.today_listening_stats(second_day)["total_seconds"] == 25


def test_agent_sessions_keep_independent_persistent_history(monkeypatch, tmp_path):
    monkeypatch.setattr(listener_memory, "STATE_PATH", tmp_path / "listener_state.json")
    first = listener_memory.create_agent_session()
    second = listener_memory.create_agent_session("工作歌单")

    listener_memory.save_agent_session_turn(
        first["id"],
        "我工作时喜欢听什么？",
        "你最近更常听节奏稳定的华语歌。",
        tools_used=["listener_preference_profile_tool"],
        model="deepseek-v4-flash",
    )
    listener_memory.save_agent_session_turn(
        second["id"],
        "推荐一首歌",
        "今天推荐《晴天》。",
        tools_used=["daily_recommendation"],
        model="deepseek-v4-flash",
    )

    first_session = listener_memory.agent_session(first["id"])
    second_session = listener_memory.agent_session(second["id"])
    assert first_session["title"].startswith("我工作时喜欢听什么")
    assert first_session["messages"][1]["tools_used"] == ["listener_preference_profile_tool"]
    assert second_session["title"] == "工作歌单"
    assert len(listener_memory.agent_sessions()) == 2
    assert listener_memory.delete_agent_session(first["id"]) is True
    assert listener_memory.agent_session(first["id"]) is None
