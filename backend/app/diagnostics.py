from __future__ import annotations

import json
from pathlib import Path

from app.data_store import DataStore
from app.models import RecommendationDiagnostics
from app.preview import attach_preview_urls
from app.sources import OPEN_DATA_SOURCES, PREVIEW_SOURCE, SEED_SOURCE


def build_recommendation_diagnostics(
    store: DataStore,
    live_preview: bool = False,
) -> RecommendationDiagnostics:
    cpop_artists = [artist for artist in store.artists.values() if artist.is_cpop]
    cpop_recordings = [recording for recording in store.recordings.values() if recording.is_cpop]

    if live_preview:
        attach_preview_urls(cpop_recordings, store.artists)

    preview_available = [recording for recording in cpop_recordings if recording.preview_url]
    preview_missing = [
        f"{store.artists[recording.artist_id].name} - {recording.title}"
        for recording in cpop_recordings
        if not recording.preview_url
    ]
    preview_coverage = len(preview_available) / len(cpop_recordings) if cpop_recordings else 0.0

    sources = [*OPEN_DATA_SOURCES, SEED_SOURCE, PREVIEW_SOURCE]
    snapshot_summary = _load_snapshot_summary(store.data_dir)

    return RecommendationDiagnostics(
        artist_count=len(store.artists),
        cpop_artist_count=len(cpop_artists),
        release_count=len(store.releases),
        recording_count=len(store.recordings),
        cpop_recording_count=len(cpop_recordings),
        daily_pick_ready=bool(cpop_recordings),
        preview_checked=live_preview,
        preview_available_count=len(preview_available),
        preview_coverage=round(preview_coverage, 4),
        preview_missing=preview_missing,
        wikidata_snapshot_artist_count=snapshot_summary["wikidata_artist_count"],
        musicbrainz_snapshot_artist_count=snapshot_summary["musicbrainz_artist_count"],
        musicbrainz_snapshot_error_count=snapshot_summary["musicbrainz_error_count"],
        listenbrainz_sitewide_trend_count=snapshot_summary["listenbrainz_sitewide_trend_count"],
        snapshot_files=snapshot_summary["snapshot_files"],
        source_count=len(sources),
        sources=sources,
    )


def _load_snapshot_summary(data_dir: Path) -> dict[str, int | list[str] | None]:
    snapshot_dir = data_dir / "snapshots"
    summary: dict[str, int | list[str] | None] = {
        "wikidata_artist_count": None,
        "musicbrainz_artist_count": None,
        "musicbrainz_error_count": None,
        "listenbrainz_sitewide_trend_count": None,
        "snapshot_files": [],
    }
    if not snapshot_dir.exists():
        return summary

    snapshot_files = sorted(path.name for path in snapshot_dir.glob("*.json"))
    summary["snapshot_files"] = snapshot_files

    wikidata = _read_json(snapshot_dir / "wikidata_seed_artists.json")
    if wikidata:
        summary["wikidata_artist_count"] = wikidata.get("artist_count")

    musicbrainz = _read_json(snapshot_dir / "musicbrainz_seed_artists.json")
    if musicbrainz:
        artists = musicbrainz.get("artists") or []
        summary["musicbrainz_artist_count"] = musicbrainz.get("artist_count")
        summary["musicbrainz_error_count"] = len([artist for artist in artists if artist.get("error")])

    listenbrainz = _read_json(snapshot_dir / "listenbrainz_seed_artist_recordings.json")
    if listenbrainz:
        sitewide = listenbrainz.get("sitewide") or {}
        summary["listenbrainz_sitewide_trend_count"] = len(sitewide.get("recordings") or [])

    return summary


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return None
