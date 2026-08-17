import json
from datetime import UTC, datetime

from app import listener_memory
from app.data_store import get_store
from app.langchain_agent import AgentRunRequest, MusicAgent


def _write_preference_state(path):
    now = datetime.now(UTC).isoformat()
    path.write_text(
        json.dumps({
            "events": [
                {"recording_id": "jay-chou-qilixiang-song", "action": "play", "at": now, "listened_seconds": 220},
                {"recording_id": "jay-chou-qilixiang-song", "action": "replay", "at": now, "listened_seconds": 230},
                {"recording_id": "jay-chou-dongfengpo", "action": "play", "at": now, "listened_seconds": 180},
                {"recording_id": "tao-ordinary-friend", "action": "play", "at": now, "listened_seconds": 35},
                {"recording_id": "tao-ordinary-friend", "action": "skip", "at": now, "listened_seconds": 35},
            ],
            "liked": ["jay-chou-qilixiang-song"],
            "saved": ["jay-chou-dongfengpo"],
            "skipped": ["tao-ordinary-friend"],
            "play_counts": {
                "jay-chou-qilixiang-song": 4,
                "jay-chou-dongfengpo": 2,
                "tao-ordinary-friend": 1,
            },
            "music_notes": [{
                "id": "note-1",
                "content": "memory",
                "prompt": "scene",
                "song_title": "\u4e03\u91cc\u9999",
                "artist": "\u5468\u6770\u4f26",
                "saved_at": now,
            }],
            "lyric_fragments": [{
                "id": "lyric-1",
                "excerpt": "sample",
                "song_title": "\u4e1c\u98ce\u7834",
                "artist": "\u5468\u6770\u4f26",
                "saved_at": now,
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_preference_profile_combines_behavior_content_and_reflection(monkeypatch, tmp_path):
    state_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)
    _write_preference_state(state_path)

    profile = listener_memory.listener_preference_profile()

    assert profile["top_artists"][0]["name"] == "\u5468\u6770\u4f26"
    assert profile["top_tracks"][0]["title"] == "\u4e03\u91cc\u9999"
    assert {item["name"] for item in profile["top_tags"]} >= {"mandopop", "ballad"}
    assert profile["favorite_eras"][0]["name"] == "2000\u5e74\u4ee3"
    assert profile["behavior"]["replay_actions"] == 1
    assert profile["behavior"]["skip_actions"] == 1
    assert profile["behavior"]["music_note_count"] == 1
    assert profile["behavior"]["lyric_fragment_count"] == 1
    assert profile["listening_periods"]


def test_music_agent_answers_preference_question_from_local_memory(monkeypatch, tmp_path):
    state_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    _write_preference_state(state_path)

    response = MusicAgent(get_store()).run(
        AgentRunRequest(query="\u4f60\u4e86\u89e3\u6211\u7684\u97f3\u4e50\u504f\u597d\u5417\uff1f")
    )

    assert response.tools_used == ["listener_preference_profile_tool"]
    assert "\u5468\u6770\u4f26" in response.answer
    assert "\u5e38\u542c\u6b4c\u624b" in response.answer
