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
