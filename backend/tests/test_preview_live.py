import os
from pathlib import Path

import pytest

from app.data_store import DataStore
from app.preview import attach_preview_urls, resolve_preview_url


@pytest.mark.skipif(
    os.getenv("CPOP_RUN_LIVE_PREVIEW_TESTS") != "1",
    reason="set CPOP_RUN_LIVE_PREVIEW_TESTS=1 to verify live Deezer preview coverage",
)
def test_live_seed_preview_coverage(monkeypatch):
    monkeypatch.delenv("CPOP_DISABLE_PREVIEW_LOOKUP", raising=False)
    resolve_preview_url.cache_clear()

    repo_root = Path(__file__).resolve().parents[2]
    store = DataStore(repo_root / "data")
    recordings = [recording for recording in store.recordings.values() if recording.is_cpop]

    attach_preview_urls(recordings, store.artists)
    missing = [
        f"{store.artists[recording.artist_id].name} - {recording.title}"
        for recording in recordings
        if not recording.preview_url
    ]

    assert len(recordings) >= 14
    assert not missing
