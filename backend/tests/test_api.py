from fastapi.testclient import TestClient
import os
from datetime import date, timedelta

os.environ["CPOP_DISABLE_PREVIEW_LOOKUP"] = "1"

from app.main import app
from app.data_store import get_store
from app.recommender import PREVIEW_CANDIDATE_LIMIT, DailyRecommender

client = TestClient(app)


def test_daily_pick_returns_explainable_song():
    response = client.get("/api/daily-pick?user_id=demo")
    assert response.status_code == 200
    payload = response.json()
    assert payload["recording"]["is_cpop"] is True
    assert len(payload["reasons"]) >= 2
    assert payload["sources"]
    assert len(payload["score_breakdown"]) == 7
    weighted_total = round(sum(item["weighted_score"] for item in payload["score_breakdown"]), 4)
    assert abs(weighted_total - payload["score"]) <= 0.001


def test_daily_pick_includes_preview_when_lookup_matches(monkeypatch):
    from app import preview

    preview.resolve_preview_url.cache_clear()
    lookups = []

    def fake_resolve(recording_id: str, *_):
        lookups.append(recording_id)
        return f"https://preview.local/{recording_id}.mp3"

    monkeypatch.setattr(preview, "resolve_preview_url", fake_resolve)

    response = client.get("/api/daily-pick?user_id=demo&seed=preview-test")
    assert response.status_code == 200
    payload = response.json()

    assert payload["recording"]["preview_url"].startswith("https://")
    assert any(item["key"] == "playability" and item["raw_score"] == 1.0 for item in payload["score_breakdown"])
    assert any("试听" in reason for reason in payload["reasons"])
    assert any(source["name"] == "Deezer public preview API" for source in payload["sources"])
    assert all(recording["preview_url"] for recording in payload["similar_recordings"])
    assert len(lookups) <= PREVIEW_CANDIDATE_LIMIT + 3


def test_daily_pick_rotation_avoids_stale_repetition():
    recommender = DailyRecommender(get_store())
    start = date(2026, 8, 16)
    picks = [
        recommender.pick(user_id="demo", today=start + timedelta(days=offset))
        for offset in range(14)
    ]
    recording_ids = [pick.recording.id for pick in picks]
    artist_ids = [pick.artist.id for pick in picks]

    assert len(set(recording_ids)) >= 10
    assert len(set(artist_ids)) >= 10
    assert all(recording_ids[index] != recording_ids[index - 1] for index in range(1, len(picks)))
    assert all(artist_ids[index] != artist_ids[index - 1] for index in range(1, len(picks)))
    assert max(
        sum(1 for artist_id in artist_ids[index : index + 7] if artist_id == "jay-chou")
        for index in range(0, len(artist_ids) - 6)
    ) <= 1


def test_daily_pick_accepts_temporary_tag_and_mood_preferences():
    tag_response = client.get("/api/daily-pick?user_id=demo&tag=rock")
    assert tag_response.status_code == 200
    tag_payload = tag_response.json()
    assert "rock" in tag_payload["recording"]["tags"]
    assert any("rock" in reason for reason in tag_payload["reasons"])

    mood_response = client.get("/api/daily-pick?user_id=demo&mood=late-night")
    assert mood_response.status_code == 200
    mood_payload = mood_response.json()
    assert "late-night" in mood_payload["recording"]["moods"]
    assert any("late-night" in reason for reason in mood_payload["reasons"])


def test_daily_pick_options_are_derived_from_seed_data():
    response = client.get("/api/daily-pick/options")
    assert response.status_code == 200
    payload = response.json()

    tags = {item["value"]: item for item in payload["tags"]}
    moods = {item["value"]: item for item in payload["moods"]}

    assert tags["rock"]["label"] == "摇滚"
    assert tags["r&b"]["count"] >= 1
    assert moods["late-night"]["label"] == "深夜"
    assert moods["warm"]["count"] >= 1


def test_daily_pick_diagnostics_reports_data_quality():
    response = client.get("/api/daily-pick/diagnostics")
    assert response.status_code == 200
    payload = response.json()

    assert payload["daily_pick_ready"] is True
    assert payload["preview_checked"] is False
    assert payload["cpop_artist_count"] >= 10
    assert payload["cpop_recording_count"] >= 14
    assert payload["source_count"] >= 6
    assert any(source["name"] == "MusicBrainz" for source in payload["sources"])
    assert any(source["name"] == "Deezer public preview API" for source in payload["sources"])
    assert "wikidata_seed_artists.json" in payload["snapshot_files"]
    assert payload["wikidata_snapshot_artist_count"] >= 1
    assert "musicbrainz_seed_artists.json" in payload["snapshot_files"]
    assert payload["musicbrainz_snapshot_artist_count"] >= 1


def test_daily_pick_diagnostics_can_check_preview_coverage(monkeypatch):
    from app import preview

    preview.resolve_preview_url.cache_clear()

    def fake_resolve(recording_id: str, *_):
        return f"https://preview.local/{recording_id}.mp3"

    monkeypatch.setattr(preview, "resolve_preview_url", fake_resolve)

    response = client.get("/api/daily-pick/diagnostics?live_preview=true")
    assert response.status_code == 200
    payload = response.json()

    assert payload["preview_checked"] is True
    assert payload["preview_available_count"] == payload["cpop_recording_count"]
    assert payload["preview_coverage"] == 1.0
    assert payload["preview_missing"] == []


def test_agent_uses_sources_and_no_full_lyrics():
    response = client.post("/api/agent/query", json={"query": "推荐一首像七里香的歌", "user_id": "demo"})
    assert response.status_code == 200
    payload = response.json()
    assert "get_daily_pick" in payload["tools_used"]
    assert payload["sources"]
    assert "完整歌词" not in payload["answer"]
