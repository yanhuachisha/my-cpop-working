import os
from pathlib import Path

import httpx
import pytest
import yaml


@pytest.mark.skipif(
    os.getenv("CPOP_RUN_LIVE_MUSICBRAINZ_TESTS") != "1",
    reason="set CPOP_RUN_LIVE_MUSICBRAINZ_TESTS=1 to verify live MusicBrainz seed MBIDs",
)
def test_live_seed_artist_musicbrainz_mbids_resolve():
    repo_root = Path(__file__).resolve().parents[2]
    seed_artists_path = repo_root / "data" / "seed_artists.yaml"
    artists = yaml.safe_load(seed_artists_path.read_text(encoding="utf-8"))
    artists_with_mbid = [artist for artist in artists if artist.get("mbid")]

    assert artists_with_mbid

    failures = []
    with httpx.Client(
        headers={"User-Agent": "C-Pop-Atlas/0.1 live-test (local development)"},
        timeout=20.0,
    ) as client:
        for artist in artists_with_mbid:
            response = client.get(
                f"https://musicbrainz.org/ws/2/artist/{artist['mbid']}",
                params={"fmt": "json"},
            )
            if response.status_code != 200:
                failures.append(f"{artist['id']} {artist['mbid']} -> {response.status_code}")

    assert failures == []
