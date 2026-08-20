import json
from datetime import UTC, datetime

from app import listener_memory
from app.data_store import get_store
from app.langchain_agent import AgentRunRequest, MusicAgent
from app.listening_agent import ListeningAgent, ListeningPromptUpdate
from app.listening_preferences import CORE_LISTENING_COMPANION_PROMPT


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
            "like_counts": {"jay-chou-qilixiang-song": 3},
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
    assert profile["behavior"]["like_actions"] == 3
    assert profile["behavior"]["music_note_count"] == 1
    assert profile["behavior"]["lyric_fragment_count"] == 1
    assert profile["top_tracks"][0]["likes"] == 3
    assert profile["listening_periods"]


def test_music_agent_answers_preference_question_from_local_memory(monkeypatch, tmp_path):
    state_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    _write_preference_state(state_path)

    response = MusicAgent(get_store()).run(
        AgentRunRequest(query="\u4f60\u4e86\u89e3\u6211\u7684\u97f3\u4e50\u504f\u597d\u5417\uff1f")
    )

    assert response.tools_used == ["query_listener_memory"]
    assert "\u5468\u6770\u4f26" in response.answer
    assert "\u5e38\u542c\u6b4c\u624b" in response.answer


def test_listening_companion_prompt_is_persisted_and_keeps_core_constraints(monkeypatch, tmp_path):
    state_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)

    settings = ListeningAgent.update_prompt_settings(
        ListeningPromptUpdate(custom_prompt="更关注编曲，回答短一些。")
    )

    assert settings.custom_prompt == "更关注编曲，回答短一些。"
    assert settings.core_prompt == CORE_LISTENING_COMPANION_PROMPT
    assert "更关注编曲" in settings.effective_prompt
    assert "必须通过标准 Agent Loop 工作" in settings.effective_prompt
    assert listener_memory.get_listening_companion_prompt() == "更关注编曲，回答短一些。"


def test_empty_listening_companion_prompt_restores_core(monkeypatch, tmp_path):
    state_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)

    settings = ListeningAgent.update_prompt_settings(ListeningPromptUpdate(custom_prompt=""))

    assert settings.custom_prompt == ""
    assert settings.effective_prompt.startswith(settings.core_prompt)
    assert "运行约束" in settings.effective_prompt


def test_listening_companion_core_prompt_is_editable_and_persisted(monkeypatch, tmp_path):
    state_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)

    settings = ListeningAgent.update_prompt_settings(ListeningPromptUpdate(
        core_prompt="你是一个更克制的音乐陪伴者，优先回应当前歌曲的声音细节。",
        custom_prompt="少提问。",
    ))

    assert settings.core_prompt.startswith("你是一个更克制的音乐陪伴者")
    assert "少提问" in settings.effective_prompt
    assert "运行约束" in settings.effective_prompt
    assert listener_memory.get_listening_companion_core_prompt() == settings.core_prompt
