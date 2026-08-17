from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT_DIR / "data"
DEFAULT_SNAPSHOT_DIR = DEFAULT_DATA_DIR / "snapshots"

WIKIDATA_ENTITY_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SOURCE = "https://www.wikidata.org/wiki/Wikidata:Licensing"
MUSICBRAINZ_API_ROOT = "https://musicbrainz.org/ws/2"
MUSICBRAINZ_SOURCE = "https://musicbrainz.org/doc/About/Data_License"
LISTENBRAINZ_API_ROOT = "https://api.listenbrainz.org"
LISTENBRAINZ_SOURCE = "https://listenbrainz.readthedocs.io/en/latest/users/api/popularity.html"
REQUEST_HEADERS = {
    "User-Agent": "C-Pop-Atlas/0.1 open-data-sync (local development; https://github.com/local/cpop-atlas)",
}

OPEN_DATA_JOBS = {
    "musicbrainz": "Fetch MusicBrainz changed entities or import dumps into staging tables.",
    "listenbrainz": "Fetch ListenBrainz incremental dumps for public listening trends.",
    "wikidata": "Refresh Wikidata mappings for C-Pop seed artists.",
    "discogs": "Import monthly Discogs dumps for labels and physical releases.",
}


def load_seed_artists(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / "seed_artists.yaml"
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or []


def fetch_wikidata_entities(qids: list[str]) -> dict[str, Any]:
    if not qids:
        return {}

    response = httpx.get(
        WIKIDATA_ENTITY_URL,
        params={
            "action": "wbgetentities",
            "ids": "|".join(qids),
            "props": "labels|descriptions|aliases|claims",
            "languages": "zh|zh-hans|zh-hant|en",
            "format": "json",
            "origin": "*",
        },
        headers=REQUEST_HEADERS,
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json().get("entities", {})


def fetch_musicbrainz_artist(mbid: str) -> dict[str, Any]:
    response = httpx.get(
        f"{MUSICBRAINZ_API_ROOT}/artist/{mbid}",
        params={
            "fmt": "json",
            "inc": "aliases+tags+url-rels+release-groups",
        },
        headers=REQUEST_HEADERS,
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()


def search_musicbrainz_artist(name: str) -> list[dict[str, Any]]:
    response = httpx.get(
        f"{MUSICBRAINZ_API_ROOT}/artist",
        params={
            "query": f'artist:"{name}"',
            "fmt": "json",
            "limit": 3,
        },
        headers=REQUEST_HEADERS,
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json().get("artists", [])


def search_wikidata_artist(name: str, language: str = "zh") -> list[dict[str, Any]]:
    response = httpx.get(
        WIKIDATA_ENTITY_URL,
        params={
            "action": "wbsearchentities",
            "search": name,
            "language": language,
            "limit": 3,
            "format": "json",
            "origin": "*",
        },
        headers=REQUEST_HEADERS,
        timeout=12.0,
    )
    response.raise_for_status()
    return response.json().get("search", [])


def fetch_listenbrainz_top_recordings_for_artist(artist_mbid: str) -> list[dict[str, Any]]:
    response = httpx.get(
        f"{LISTENBRAINZ_API_ROOT}/1/popularity/top-recordings-for-artist/{artist_mbid}",
        headers=REQUEST_HEADERS,
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_listenbrainz_sitewide_recordings(
    stats_range: str = "this_week",
    count: int = 25,
) -> dict[str, Any]:
    response = httpx.get(
        f"{LISTENBRAINZ_API_ROOT}/1/stats/sitewide/recordings",
        params={"range": stats_range, "count": count},
        headers=REQUEST_HEADERS,
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json().get("payload", {})


def compact_entity(entity: dict[str, Any]) -> dict[str, Any]:
    qid = entity["id"]
    return {
        "qid": qid,
        "url": f"https://www.wikidata.org/wiki/{qid}",
        "labels": _localized_values(entity.get("labels", {})),
        "descriptions": _localized_values(entity.get("descriptions", {})),
        "aliases": _localized_aliases(entity.get("aliases", {})),
        "musicbrainz_artist_id": _claim_values(entity, "P434"),
        "discogs_artist_id": _claim_values(entity, "P1953"),
        "image": _claim_values(entity, "P18")[:1],
    }


def compact_musicbrainz_artist(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "mbid": entity.get("id"),
        "name": entity.get("name"),
        "sort_name": entity.get("sort-name"),
        "country": entity.get("country"),
        "area": (entity.get("area") or {}).get("name"),
        "disambiguation": entity.get("disambiguation"),
        "aliases": [
            {
                "name": alias.get("name"),
                "sort_name": alias.get("sort-name"),
                "locale": alias.get("locale"),
                "primary": alias.get("primary"),
            }
            for alias in entity.get("aliases", [])
        ],
        "tags": [
            {"name": tag.get("name"), "count": tag.get("count", 0)}
            for tag in entity.get("tags", [])
        ],
        "url_relations": [
            {
                "type": relation.get("type"),
                "target": relation.get("url", {}).get("resource"),
            }
            for relation in entity.get("relations", [])
            if relation.get("url", {}).get("resource")
        ],
        "release_groups": [
            {
                "mbid": release_group.get("id"),
                "title": release_group.get("title"),
                "first_release_date": release_group.get("first-release-date"),
                "primary_type": release_group.get("primary-type"),
                "secondary_types": release_group.get("secondary-types", []),
            }
            for release_group in entity.get("release-groups", [])
        ],
    }


def compact_listenbrainz_recording(recording: dict[str, Any]) -> dict[str, Any]:
    return {
        "artist_name": recording.get("artist_name"),
        "artist_mbids": recording.get("artist_mbids", []),
        "recording_name": recording.get("recording_name", recording.get("track_name")),
        "recording_mbid": recording.get("recording_mbid"),
        "release_name": recording.get("release_name"),
        "release_mbid": recording.get("release_mbid"),
        "total_listen_count": recording.get("total_listen_count", recording.get("listen_count")),
        "total_user_count": recording.get("total_user_count", recording.get("user_count")),
        "caa_id": recording.get("caa_id"),
        "caa_release_mbid": recording.get("caa_release_mbid"),
    }


def _localized_values(values: dict[str, Any]) -> dict[str, str]:
    return {
        language: item["value"]
        for language, item in values.items()
        if language in {"zh", "zh-hans", "zh-hant", "en"} and item.get("value")
    }


def _localized_aliases(values: dict[str, Any]) -> dict[str, list[str]]:
    return {
        language: [item["value"] for item in items if item.get("value")]
        for language, items in values.items()
        if language in {"zh", "zh-hans", "zh-hant", "en"}
    }


def _claim_values(entity: dict[str, Any], property_id: str) -> list[str]:
    values = []
    for claim in entity.get("claims", {}).get(property_id, []):
        mainsnak = claim.get("mainsnak", {})
        datavalue = mainsnak.get("datavalue", {})
        value = datavalue.get("value")
        if isinstance(value, str):
            values.append(value)
    return values


def build_musicbrainz_seed_snapshot(
    data_dir: Path,
    limit: int | None = None,
    request_delay: float = 1.1,
) -> dict[str, Any]:
    artists = load_seed_artists(data_dir)
    if limit is not None:
        artists = artists[:limit]

    snapshot_artists = []
    for index, artist in enumerate(artists):
        mbid = artist.get("mbid")
        entity = None
        candidates = []
        error = None
        try:
            if mbid:
                try:
                    entity = compact_musicbrainz_artist(fetch_musicbrainz_artist(mbid))
                except httpx.HTTPStatusError as exc:
                    error = str(exc)
                    candidates = [
                        {
                            "mbid": item.get("id"),
                            "name": item.get("name"),
                            "sort_name": item.get("sort-name"),
                            "country": item.get("country"),
                            "score": item.get("score"),
                        }
                        for item in search_musicbrainz_artist(artist["name"])
                    ]
            else:
                candidates = [
                    {
                        "mbid": item.get("id"),
                        "name": item.get("name"),
                        "sort_name": item.get("sort-name"),
                        "country": item.get("country"),
                        "score": item.get("score"),
                    }
                    for item in search_musicbrainz_artist(artist["name"])
                ]
        except httpx.HTTPError as exc:
            error = str(exc)

        snapshot_artists.append(
            {
                "id": artist["id"],
                "name": artist["name"],
                "current_mbid": mbid,
                "musicbrainz": entity,
                "candidate_matches": candidates,
                "error": error,
            }
        )
        if index < len(artists) - 1 and request_delay > 0:
            time.sleep(request_delay)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "MusicBrainz",
        "license": "CC0 core data",
        "license_url": MUSICBRAINZ_SOURCE,
        "artist_count": len(snapshot_artists),
        "artists": snapshot_artists,
    }


def build_listenbrainz_seed_snapshot(
    data_dir: Path,
    limit: int | None = None,
    per_artist_limit: int = 10,
    stats_range: str = "this_week",
) -> dict[str, Any]:
    artists = [artist for artist in load_seed_artists(data_dir) if artist.get("mbid")]
    if limit is not None:
        artists = artists[:limit]

    snapshot_artists = []
    for artist in artists:
        error = None
        recordings = []
        try:
            raw_recordings = fetch_listenbrainz_top_recordings_for_artist(artist["mbid"])
            recordings = [
                compact_listenbrainz_recording(recording)
                for recording in raw_recordings[:per_artist_limit]
            ]
        except httpx.HTTPError as exc:
            error = str(exc)

        snapshot_artists.append(
            {
                "id": artist["id"],
                "name": artist["name"],
                "artist_mbid": artist["mbid"],
                "recordings": recordings,
                "error": error,
            }
        )

    sitewide_error = None
    sitewide_payload = {}
    try:
        sitewide_payload = fetch_listenbrainz_sitewide_recordings(
            stats_range=stats_range,
            count=max(1, min(per_artist_limit * 2, 100)),
        )
    except httpx.HTTPError as exc:
        sitewide_error = str(exc)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "ListenBrainz popularity API",
        "license": "Open listens and public API data",
        "source_url": LISTENBRAINZ_SOURCE,
        "artist_count": len(snapshot_artists),
        "per_artist_limit": per_artist_limit,
        "artists": snapshot_artists,
        "sitewide": {
            "range": sitewide_payload.get("range", stats_range),
            "last_updated": sitewide_payload.get("last_updated"),
            "recordings": [
                compact_listenbrainz_recording(recording)
                for recording in sitewide_payload.get("recordings", [])
            ],
            "error": sitewide_error,
        },
    }


def build_wikidata_snapshot(data_dir: Path, limit: int | None = None) -> dict[str, Any]:
    artists = load_seed_artists(data_dir)
    if limit is not None:
        artists = artists[:limit]

    qids = [artist["wikidata_qid"] for artist in artists if artist.get("wikidata_qid")]
    entities = fetch_wikidata_entities(qids)

    snapshot_artists = []
    for artist in artists:
        qid = artist.get("wikidata_qid")
        entity = compact_entity(entities[qid]) if qid and qid in entities and not entities[qid].get("missing") else None
        search_candidates = []
        if not qid:
            search_candidates = search_wikidata_artist(artist["name"])
            if not search_candidates and artist.get("sort_name"):
                search_candidates = search_wikidata_artist(artist["sort_name"], language="en")

        snapshot_artists.append(
            {
                "id": artist["id"],
                "name": artist["name"],
                "sort_name": artist.get("sort_name"),
                "current_wikidata_qid": qid,
                "wikidata": entity,
                "candidate_matches": [
                    {
                        "qid": item.get("id"),
                        "label": item.get("label"),
                        "description": item.get("description"),
                        "url": item.get("concepturi"),
                    }
                    for item in search_candidates
                ],
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "Wikidata",
        "license": "CC0",
        "license_url": WIKIDATA_SOURCE,
        "artist_count": len(snapshot_artists),
        "artists": snapshot_artists,
    }


def write_snapshot(snapshot: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=2)
        file.write("\n")


def run_wikidata(args: argparse.Namespace) -> None:
    output_path = args.output or DEFAULT_SNAPSHOT_DIR / "wikidata_seed_artists.json"
    if args.dry_run:
        artists = load_seed_artists(args.data_dir)
        if args.limit is not None:
            artists = artists[: args.limit]
        known_qids = [artist for artist in artists if artist.get("wikidata_qid")]
        missing_qids = [artist for artist in artists if not artist.get("wikidata_qid")]
        print(
            "[dry-run] wikidata: "
            f"{len(artists)} seed artists, "
            f"{len(known_qids)} known QIDs, "
            f"{len(missing_qids)} missing QIDs"
        )
        print(f"[dry-run] would write {output_path}")
        return

    snapshot = build_wikidata_snapshot(args.data_dir, limit=args.limit)

    missing_qids = [
        artist["name"]
        for artist in snapshot["artists"]
        if not artist["current_wikidata_qid"] and artist["candidate_matches"]
    ]
    print(
        "wikidata: "
        f"{snapshot['artist_count']} seed artists, "
        f"{len(missing_qids)} artists have candidate QID matches"
    )
    write_snapshot(snapshot, output_path)
    print(f"wrote {output_path}")


def run_musicbrainz(args: argparse.Namespace) -> None:
    output_path = args.output or DEFAULT_SNAPSHOT_DIR / "musicbrainz_seed_artists.json"
    if args.dry_run:
        artists = load_seed_artists(args.data_dir)
        if args.limit is not None:
            artists = artists[: args.limit]
        known_mbids = [artist for artist in artists if artist.get("mbid")]
        missing_mbids = [artist for artist in artists if not artist.get("mbid")]
        print(
            "[dry-run] musicbrainz: "
            f"{len(artists)} seed artists, "
            f"{len(known_mbids)} known MBIDs, "
            f"{len(missing_mbids)} missing MBIDs"
        )
        print(f"[dry-run] would write {output_path}")
        return

    snapshot = build_musicbrainz_seed_snapshot(
        args.data_dir,
        limit=args.limit,
        request_delay=args.musicbrainz_delay,
    )
    with_errors = [artist for artist in snapshot["artists"] if artist["error"]]
    with_candidates = [
        artist for artist in snapshot["artists"] if not artist["current_mbid"] and artist["candidate_matches"]
    ]
    print(
        "musicbrainz: "
        f"{snapshot['artist_count']} seed artists, "
        f"{len(with_errors)} artists with API errors, "
        f"{len(with_candidates)} missing-MBID artists with candidates"
    )
    write_snapshot(snapshot, output_path)
    print(f"wrote {output_path}")


def run_listenbrainz(args: argparse.Namespace) -> None:
    output_path = args.output or DEFAULT_SNAPSHOT_DIR / "listenbrainz_seed_artist_recordings.json"
    per_artist_limit = max(1, min(args.per_artist_limit, 25))
    if args.dry_run:
        artists = [artist for artist in load_seed_artists(args.data_dir) if artist.get("mbid")]
        if args.limit is not None:
            artists = artists[: args.limit]
        print(
            "[dry-run] listenbrainz: "
            f"{len(artists)} seed artists with MusicBrainz MBIDs, "
            f"top {per_artist_limit} recordings each"
        )
        print(f"[dry-run] would write {output_path}")
        return

    snapshot = build_listenbrainz_seed_snapshot(
        args.data_dir,
        limit=args.limit,
        per_artist_limit=per_artist_limit,
        stats_range=args.listenbrainz_range,
    )
    with_errors = [artist for artist in snapshot["artists"] if artist["error"]]
    print(
        "listenbrainz: "
        f"{snapshot['artist_count']} artists, "
        f"{len(with_errors)} artists with API errors, "
        f"{len(snapshot['sitewide']['recordings'])} sitewide trend recordings"
    )
    write_snapshot(snapshot, output_path)
    print(f"wrote {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="C-Pop Atlas open data sync runner")
    parser.add_argument(
        "--source",
        choices=[*OPEN_DATA_JOBS.keys(), "all"],
        default="all",
        help="Open data source to sync",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory containing seed_*.yaml files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Snapshot output path. Defaults to data/snapshots/<source>_seed_artists.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit seed artists for quick checks",
    )
    parser.add_argument(
        "--per-artist-limit",
        type=int,
        default=10,
        help="Limit ListenBrainz top recordings per artist",
    )
    parser.add_argument(
        "--listenbrainz-range",
        choices=["all_time", "year", "month", "week", "this_week", "today"],
        default="this_week",
        help="ListenBrainz sitewide stats range",
    )
    parser.add_argument(
        "--musicbrainz-delay",
        type=float,
        default=1.1,
        help="Delay between MusicBrainz API requests in seconds",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned jobs without writing data",
    )
    args = parser.parse_args()

    selected = OPEN_DATA_JOBS if args.source == "all" else {args.source: OPEN_DATA_JOBS[args.source]}
    print(f"C-Pop Atlas sync started at {datetime.now(UTC).isoformat()}")
    for source, description in selected.items():
        if source == "musicbrainz":
            run_musicbrainz(args)
            continue
        if source == "wikidata":
            run_wikidata(args)
            continue
        if source == "listenbrainz":
            run_listenbrainz(args)
            continue
        if args.dry_run:
            print(f"[dry-run] {source}: {description}")
        else:
            print(f"[planned] {source}: {description}")
            print("Importer is intentionally staged behind this runner for v1.")


if __name__ == "__main__":
    main()
