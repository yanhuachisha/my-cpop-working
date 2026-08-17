import json
from datetime import UTC, datetime

from app import listener_memory, music_assistant_features


def test_emotion_memory_reads_skip_and_repeat_signals(monkeypatch, tmp_path):
    state_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)
    state_path.write_text(json.dumps({
        "events": [
            {"recording_id": "jay-chou-qilixiang-song", "action": "play", "at": datetime.now(UTC).isoformat()},
            {"recording_id": "jay-chou-qilixiang-song", "action": "replay", "at": datetime.now(UTC).isoformat()},
            {"recording_id": "jay-chou-qilixiang-song", "action": "skip", "at": datetime.now(UTC).isoformat()},
        ]
    }), encoding="utf-8")

    result = music_assistant_features.emotion_memory()

    assert result["signals"]["plays"] == 2
    assert result["signals"]["skips"] == 1
    assert result["repeat_tracks"][0]["title"] == "七里香"


def test_weekly_report_is_persisted_locally(monkeypatch, tmp_path):
    state_path = tmp_path / "listener_state.json"
    report_dir = tmp_path / "weekly_reports"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)
    monkeypatch.setattr(music_assistant_features, "REPORT_DIR", report_dir)
    state_path.write_text(json.dumps({
        "events": [{
            "recording_id": "jay-chou-qilixiang-song",
            "action": "play",
            "channel": "kugou-auto",
            "listened_seconds": 90,
            "at": datetime.now(UTC).isoformat(),
        }]
    }), encoding="utf-8")

    report = music_assistant_features.weekly_report(force=True)

    assert report["local_only"] is True
    assert report["estimated_minutes"] == 2
    assert report["top_tracks"][0]["title"] == "七里香"
    assert list(report_dir.glob("*.json"))
