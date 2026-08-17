from app import playback_tracker as playback_tracker_module
from app.playback_tracker import KugouPlaybackTracker


def _snapshot(title: str, artist: str) -> dict[str, object]:
    return {"title": title, "artist": artist, "is_playing": True}


def test_tracker_records_only_incremental_listening_time(monkeypatch):
    increments = []
    monkeypatch.setattr(
        playback_tracker_module,
        "ensure_library_recording",
        lambda title, artist: f"{artist}-{title}",
    )
    monkeypatch.setattr(
        playback_tracker_module,
        "record_daily_listening",
        lambda **payload: increments.append(payload),
    )
    monkeypatch.setattr(
        playback_tracker_module,
        "record_feedback",
        lambda request: {"total_play_count": 1},
    )
    tracker = KugouPlaybackTracker(threshold_seconds=30, poll_seconds=5)

    tracker.observe(_snapshot("晴天", "周杰伦"), now=0)
    tracker.observe(_snapshot("晴天", "周杰伦"), now=5)
    tracker.observe(_snapshot("晴天", "周杰伦"), now=100)
    tracker.observe(_snapshot("小宇", "张震岳"), now=105)
    tracker.observe(_snapshot("小宇", "张震岳"), now=110)

    assert [item["listened_seconds"] for item in increments] == [5, 15, 5, 5]
    assert [item["recording_id"] for item in increments] == [
        "周杰伦-晴天",
        "周杰伦-晴天",
        "周杰伦-晴天",
        "张震岳-小宇",
    ]


def test_tracker_first_observation_does_not_add_time(monkeypatch):
    increments = []
    monkeypatch.setattr(playback_tracker_module, "ensure_library_recording", lambda *_: "song-a")
    monkeypatch.setattr(
        playback_tracker_module,
        "record_daily_listening",
        lambda **payload: increments.append(payload),
    )
    tracker = KugouPlaybackTracker(threshold_seconds=30, poll_seconds=5)

    tracker.observe(_snapshot("晴天", "周杰伦"), now=10)

    assert increments == []
