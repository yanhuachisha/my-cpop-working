import json
from datetime import date, datetime

import pytest

from app import listening_history


@pytest.fixture
def isolated_history(monkeypatch, tmp_path):
    database_path = tmp_path / "listening_history.db"
    legacy_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listening_history, "DB_PATH", database_path)
    monkeypatch.setattr(listening_history, "LEGACY_STATE_PATH", legacy_path)
    listening_history._initialized_paths.clear()
    return database_path, legacy_path


def test_sqlite_history_aggregates_days_tracks_and_artists(isolated_history):
    database_path, _ = isolated_history
    previous_day = datetime.fromisoformat("2026-08-14T10:00:00+08:00")
    first_day = datetime.fromisoformat("2026-08-16T10:00:00+08:00")
    second_day = datetime.fromisoformat("2026-08-17T10:00:00+08:00")

    listening_history.record_daily_listening("song-c", "普通朋友", "陶喆", 100, previous_day)
    listening_history.record_daily_listening("song-a", "晴天", "周杰伦", 120, first_day)
    listening_history.record_daily_listening("song-b", "小宇", "张震岳", 60, first_day)
    listening_history.record_daily_listening("song-a", "晴天", "周杰伦", 30, second_day)

    daily = listening_history.query_listening_history(
        "2026-08-16", "2026-08-17", group_by="day"
    )
    tracks = listening_history.query_listening_history(
        "2026-08-16", "2026-08-17", group_by="track"
    )
    artists = listening_history.query_listening_history(
        "2026-08-16", "2026-08-17", group_by="artist"
    )
    overview = listening_history.query_listening_history(
        "2026-08-16",
        "2026-08-17",
        group_by="day",
        view="overview",
        top_n=3,
    )

    assert database_path.exists()
    assert daily["total_seconds"] == 210
    assert daily["active_days"] == 2
    assert daily["track_count"] == 2
    assert tracks["items"][0]["recording_id"] == "song-a"
    assert tracks["items"][0]["seconds"] == 150
    assert artists["items"][0]["artist"] == "周杰伦"
    assert artists["items"][0]["seconds"] == 150
    assert len(overview["overview"]["daily_trend"]) == 2
    assert overview["overview"]["top_tracks"][0]["recording_id"] == "song-a"
    assert overview["overview"]["top_artists"][0]["artist"] == "周杰伦"
    assert overview["overview"]["repeat_tracks"][0]["recording_id"] == "song-a"
    assert overview["overview"]["previous_period"]["total_seconds"] == 100
    assert overview["overview"]["comparison"]["listening_time_change"] == 1.1

    listening_history._initialized_paths.clear()
    restored = listening_history.query_listening_history(
        "2026-08-16", "2026-08-17", group_by="track"
    )
    assert restored["total_seconds"] == 210


def test_legacy_json_is_migrated_only_once(isolated_history):
    _, legacy_path = isolated_history
    legacy_path.write_text(
        json.dumps({
            "daily_listening": {
                "2026-08-15": {
                    "total_seconds": 95,
                    "tracks": {
                        "song-a": {
                            "title": "晴天",
                            "artist": "周杰伦",
                            "seconds": 95,
                            "last_listened_at": "2026-08-15T12:00:00+08:00",
                        }
                    },
                }
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    listening_history.initialize_listening_history()
    listening_history._initialized_paths.clear()
    listening_history.initialize_listening_history()
    result = listening_history.query_listening_history(
        "2026-08-15", "2026-08-15", group_by="track"
    )

    assert result["total_seconds"] == 95
    assert len(result["items"]) == 1


def test_history_period_resolver_supports_relative_ranges():
    current = date(2026, 8, 17)

    assert listening_history.resolve_history_period("today", today=current) == (
        "2026-08-17",
        "2026-08-17",
    )
    assert listening_history.resolve_history_period("yesterday", today=current) == (
        "2026-08-16",
        "2026-08-16",
    )
    assert listening_history.resolve_history_period("7d", today=current) == (
        "2026-08-11",
        "2026-08-17",
    )
    assert listening_history.resolve_history_period("this_week", today=current) == (
        "2026-08-17",
        "2026-08-17",
    )
    assert listening_history.resolve_history_period("last_week", today=current) == (
        "2026-08-10",
        "2026-08-16",
    )
    assert listening_history.resolve_history_period("this_month", today=current) == (
        "2026-08-01",
        "2026-08-17",
    )
    assert listening_history.resolve_history_period("last_month", today=current) == (
        "2026-07-01",
        "2026-07-31",
    )


def test_custom_history_range_rejects_reverse_dates():
    with pytest.raises(ValueError, match="start_date"):
        listening_history.resolve_history_period(
            "custom",
            start_date="2026-08-17",
            end_date="2026-08-16",
        )
