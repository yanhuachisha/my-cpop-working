from __future__ import annotations

import importlib.util
from pathlib import Path


def load_builder():
    path = Path(__file__).resolve().parents[2] / "scripts" / "build_musicbrainz_discovery.py"
    spec = importlib.util.spec_from_file_location("build_musicbrainz_discovery", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compact_recording_builds_dynamic_artist_and_recording():
    builder = load_builder()
    result = builder.compact_recording({
        "id": "recording-mbid",
        "title": "新的华语歌",
        "first-release-date": "2026-01-03",
        "artist-credit": [{
            "name": "示例歌手",
            "artist": {"id": "artist-mbid", "name": "示例歌手", "sort-name": "示例歌手", "aliases": []},
        }],
    }, "cmn")
    assert result is not None
    artist, recording = result
    assert artist["id"] == "mb-artist-artist-mbid"
    assert recording["artist_id"] == artist["id"]
    assert recording["year"] == 2026


def test_compact_recording_accepts_language_confirmed_romanized_titles():
    builder = load_builder()
    result = builder.compact_recording({
        "id": "recording-mbid",
        "title": "International Song",
        "artist-credit": [{"artist": {"id": "artist-mbid", "name": "International Artist", "aliases": []}}],
    }, "cmn")
    assert result is not None
    _, recording = result
    assert recording["language"] == "cmn"
