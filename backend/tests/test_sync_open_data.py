from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_sync_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "sync_open_data.py"
    spec = importlib.util.spec_from_file_location("sync_open_data", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compact_wikidata_entity_extracts_open_ids():
    sync = load_sync_module()

    compact = sync.compact_entity(
        {
            "id": "Q131285",
            "labels": {"zh": {"value": "周杰伦"}, "en": {"value": "Jay Chou"}},
            "descriptions": {"zh": {"value": "台湾男歌手"}},
            "aliases": {"en": [{"value": "Jie Lun Zhou"}]},
            "claims": {
                "P434": [{"mainsnak": {"datavalue": {"value": "musicbrainz-id"}}}],
                "P1953": [{"mainsnak": {"datavalue": {"value": "842937"}}}],
                "P18": [{"mainsnak": {"datavalue": {"value": "Jay Chou.jpg"}}}],
            },
        }
    )

    assert compact["qid"] == "Q131285"
    assert compact["labels"]["zh"] == "周杰伦"
    assert compact["musicbrainz_artist_id"] == ["musicbrainz-id"]
    assert compact["discogs_artist_id"] == ["842937"]
    assert compact["image"] == ["Jay Chou.jpg"]


def test_compact_musicbrainz_artist_extracts_relations_and_releases():
    sync = load_sync_module()

    compact = sync.compact_musicbrainz_artist(
        {
            "id": "artist-mbid",
            "name": "Jay Chou",
            "sort-name": "Chou, Jay",
            "country": "TW",
            "area": {"name": "Taiwan"},
            "aliases": [{"name": "周杰伦", "locale": "zh", "primary": True}],
            "tags": [{"name": "mandopop", "count": 3}],
            "relations": [
                {"type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q131285"}}
            ],
            "release-groups": [
                {
                    "id": "rg-mbid",
                    "title": "范特西",
                    "first-release-date": "2001-09-14",
                    "primary-type": "Album",
                }
            ],
        }
    )

    assert compact["mbid"] == "artist-mbid"
    assert compact["aliases"][0]["name"] == "周杰伦"
    assert compact["tags"][0]["name"] == "mandopop"
    assert compact["url_relations"][0]["type"] == "wikidata"
    assert compact["release_groups"][0]["title"] == "范特西"


def test_build_musicbrainz_seed_snapshot_uses_mbids_and_candidates(monkeypatch, tmp_path):
    sync = load_sync_module()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "seed_artists.yaml").write_text(
        """
- id: jay-chou
  name: 周杰伦
  mbid: artist-mbid
- id: missing
  name: 缺 MBID
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sync,
        "fetch_musicbrainz_artist",
        lambda mbid: {"id": mbid, "name": "Jay Chou", "release-groups": []},
    )
    monkeypatch.setattr(
        sync,
        "search_musicbrainz_artist",
        lambda name: [{"id": "candidate-mbid", "name": name, "score": 90}],
    )

    snapshot = sync.build_musicbrainz_seed_snapshot(data_dir, request_delay=0)

    assert snapshot["source"] == "MusicBrainz"
    assert snapshot["artist_count"] == 2
    assert snapshot["artists"][0]["musicbrainz"]["mbid"] == "artist-mbid"
    assert snapshot["artists"][1]["candidate_matches"][0]["mbid"] == "candidate-mbid"


def test_build_musicbrainz_seed_snapshot_falls_back_when_mbid_fails(monkeypatch, tmp_path):
    import httpx

    sync = load_sync_module()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "seed_artists.yaml").write_text(
        """
- id: jay-chou
  name: 周杰伦
  mbid: stale-mbid
""".strip(),
        encoding="utf-8",
    )

    def fail_fetch(mbid):
        request = httpx.Request("GET", "https://musicbrainz.org/ws/2/artist/stale-mbid")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(sync, "fetch_musicbrainz_artist", fail_fetch)
    monkeypatch.setattr(
        sync,
        "search_musicbrainz_artist",
        lambda name: [{"id": "fresh-mbid", "name": "Jay Chou", "score": 100}],
    )

    snapshot = sync.build_musicbrainz_seed_snapshot(data_dir, request_delay=0)

    assert snapshot["artists"][0]["musicbrainz"] is None
    assert snapshot["artists"][0]["error"]
    assert snapshot["artists"][0]["candidate_matches"][0]["mbid"] == "fresh-mbid"


def test_compact_listenbrainz_recording_keeps_trend_fields():
    sync = load_sync_module()

    compact = sync.compact_listenbrainz_recording(
        {
            "artist_name": "Jay Chou",
            "artist_mbids": ["artist-mbid"],
            "track_name": "七里香",
            "recording_mbid": "recording-mbid",
            "release_name": "七里香",
            "release_mbid": "release-mbid",
            "listen_count": 1234,
            "user_count": 321,
        }
    )

    assert compact["artist_name"] == "Jay Chou"
    assert compact["recording_name"] == "七里香"
    assert compact["total_listen_count"] == 1234
    assert compact["total_user_count"] == 321


def test_build_listenbrainz_seed_snapshot_uses_seed_mbids(monkeypatch, tmp_path):
    sync = load_sync_module()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "seed_artists.yaml").write_text(
        """
- id: jay-chou
  name: 周杰伦
  mbid: artist-mbid
- id: no-mbid
  name: 无外部 ID 艺人
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sync,
        "fetch_listenbrainz_top_recordings_for_artist",
        lambda artist_mbid: [
            {
                "artist_name": "Jay Chou",
                "recording_name": "七里香",
                "recording_mbid": "recording-mbid",
                "total_listen_count": 1234,
            }
        ],
    )
    monkeypatch.setattr(
        sync,
        "fetch_listenbrainz_sitewide_recordings",
        lambda stats_range, count: {
            "range": stats_range,
            "last_updated": 123456,
            "recordings": [
                {
                    "artist_name": "Jay Chou",
                    "recording_name": "晴天",
                    "listen_count": 99,
                }
            ],
        },
    )

    snapshot = sync.build_listenbrainz_seed_snapshot(data_dir, per_artist_limit=5)

    assert snapshot["source"] == "ListenBrainz popularity API"
    assert snapshot["artist_count"] == 1
    assert snapshot["artists"][0]["id"] == "jay-chou"
    assert snapshot["artists"][0]["recordings"][0]["recording_name"] == "七里香"
    assert snapshot["sitewide"]["recordings"][0]["recording_name"] == "晴天"


def test_write_snapshot_creates_json_file(tmp_path):
    sync = load_sync_module()
    output_path = tmp_path / "snapshots" / "wikidata.json"

    sync.write_snapshot({"source": "Wikidata", "artists": []}, output_path)

    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))["source"] == "Wikidata"
