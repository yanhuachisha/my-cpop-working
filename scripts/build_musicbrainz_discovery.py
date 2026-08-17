from __future__ import annotations

import argparse
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = "https://musicbrainz.org/ws/2/recording"
HEADERS = {"User-Agent": "C-Pop-Atlas/0.4 music discovery catalog"}
LANGUAGE_CONFIG = {
    "cmn": {"country": "China", "area": "China", "tags": ["mandopop", "chinese pop"]},
    "yue": {"country": "Hong Kong", "area": "Hong Kong", "tags": ["cantopop", "chinese pop"]},
    "nan": {"country": "Taiwan", "area": "Taiwan", "tags": ["taiwan pop", "chinese pop"]},
}
DATE_RANGES = [
    ("1980-01-01", "1999-12-31"),
    ("2000-01-01", "2009-12-31"),
    ("2010-01-01", "2019-12-31"),
    ("2020-01-01", "2026-12-31"),
]


def has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def request_page(client: httpx.Client, query: str, offset: int, delay: float) -> dict[str, Any]:
    last_error: httpx.HTTPError | None = None
    for attempt in range(4):
        try:
            response = client.get(API_ROOT, params={"query": query, "fmt": "json", "limit": 100, "offset": offset})
            response.raise_for_status()
            time.sleep(delay)
            return response.json()
        except httpx.HTTPError as error:
            last_error = error
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def compact_recording(item: dict[str, Any], language: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    artist_credit = item.get("artist-credit") or []
    artist_data = (artist_credit[0].get("artist") if artist_credit else None) or {}
    recording_mbid = str(item.get("id") or "")
    artist_mbid = str(artist_data.get("id") or "")
    title = str(item.get("title") or "").strip()
    artist_name = str(artist_data.get("name") or artist_credit[0].get("name") if artist_credit else "").strip()
    if not recording_mbid or not artist_mbid or not title or not artist_name:
        return None
    aliases = [str(alias.get("name") or "").strip() for alias in artist_data.get("aliases", [])]
    config = LANGUAGE_CONFIG[language]
    first_date = str(item.get("first-release-date") or "")
    year = int(first_date[:4]) if first_date[:4].isdigit() else None
    artist_id = f"mb-artist-{artist_mbid}"
    artist = {
        "id": artist_id,
        "name": artist_name,
        "sort_name": artist_data.get("sort-name") or artist_name,
        "country": config["country"],
        "area": config["area"],
        "is_cpop": True,
        "mbid": artist_mbid,
        "tags": config["tags"],
        "aliases": [alias for alias in aliases if alias][:8],
        "source_urls": [f"https://musicbrainz.org/artist/{artist_mbid}"],
    }
    recording = {
        "id": f"mb-{recording_mbid}",
        "title": title,
        "artist_id": artist_id,
        "year": year,
        "language": language,
        "is_cpop": True,
        "tags": config["tags"],
        "moods": ["reflective"],
        "mbid": recording_mbid,
        "source_urls": [f"https://musicbrainz.org/recording/{recording_mbid}"],
    }
    return artist, recording


def build(target: int, pages_per_query: int, delay: float, start_page: int = 0) -> dict[str, Any]:
    artists: dict[str, dict[str, Any]] = {}
    recordings: dict[str, dict[str, Any]] = {}
    reports = []
    with httpx.Client(headers=HEADERS, timeout=30.0) as client:
        for language in LANGUAGE_CONFIG:
            for start, end in DATE_RANGES:
                query = f"lang:{language} AND status:official AND firstreleasedate:[{start} TO {end}]"
                accepted = 0
                for page in range(start_page, start_page + pages_per_query):
                    if len(recordings) >= target:
                        break
                    try:
                        payload = request_page(client, query, page * 100, delay)
                    except httpx.HTTPError as error:
                        reports.append({"language": language, "range": [start, end], "status": "error", "error": str(error)})
                        break
                    for item in payload.get("recordings", []):
                        compacted = compact_recording(item, language)
                        if not compacted:
                            continue
                        artist, recording = compacted
                        artists.setdefault(artist["id"], artist)
                        recordings.setdefault(recording["id"], recording)
                        accepted += 1
                reports.append({"language": language, "range": [start, end], "status": "ok", "accepted": accepted})
                if len(recordings) >= target:
                    break
            if len(recordings) >= target:
                break
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "MusicBrainz language and date discovery",
        "license": "CC0 core data",
        "artists": list(artists.values()),
        "releases": [],
        "recordings": list(recordings.values()),
        "sync_report": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=9000)
    parser.add_argument("--pages-per-query", type=int, default=9)
    parser.add_argument("--delay", type=float, default=1.05)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "musicbrainz_discovery.json")
    parser.add_argument("--cursor", type=Path, default=ROOT / "data" / "musicbrainz_discovery.cursor")
    args = parser.parse_args()
    try:
        start_page = max(0, int(args.cursor.read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        start_page = 0
    catalog = build(max(100, args.target), max(1, args.pages_per_query), max(1.0, args.delay), start_page)
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        artists = {item["id"]: item for item in previous.get("artists", [])}
        recordings = {item["id"]: item for item in previous.get("recordings", [])}
        artists.update({item["id"]: item for item in catalog["artists"]})
        recordings.update({item["id"]: item for item in catalog["recordings"]})
        catalog["artists"] = list(artists.values())
        catalog["recordings"] = list(recordings.values())
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    args.cursor.write_text(str(start_page + max(1, args.pages_per_query)), encoding="utf-8")
    print(f"wrote {len(catalog['recordings'])} MusicBrainz discovery recordings to {args.output}")


if __name__ == "__main__":
    main()
