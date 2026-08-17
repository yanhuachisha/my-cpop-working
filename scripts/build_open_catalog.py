from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = "https://musicbrainz.org/ws/2"
HEADERS = {"User-Agent": "C-Pop-Atlas/0.2 local catalog builder"}
EXCLUDED_ARTIST_IDS = {"vincent-fang", "michael-lin", "chung-hsing-min"}
MOOD_BY_TAG = {
    "r&b": ["late-night", "warm"],
    "rock": ["uplifting", "resilient"],
    "ballad": ["reflective", "bittersweet"],
    "chinese-style": ["nostalgic", "elegant"],
    "campus": ["youthful", "warm"],
    "soul": ["intimate", "warm"],
}


def request_json(client: httpx.Client, path: str, params: dict[str, Any]) -> dict[str, Any]:
    last_error: httpx.HTTPError | None = None
    for attempt in range(4):
        try:
            response = client.get(f"{API_ROOT}/{path}", params={**params, "fmt": "json"})
            response.raise_for_status()
            time.sleep(1.1)
            return response.json()
        except httpx.HTTPError as error:
            last_error = error
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def resolve_artist_mbid(client: httpx.Client, artist: dict[str, Any]) -> str | None:
    if artist.get("mbid"):
        return str(artist["mbid"])
    payload = request_json(client, "artist", {"query": f'artist:"{artist["name"]}"', "limit": 5})
    candidates = payload.get("artists", [])
    accepted = [item for item in candidates if int(item.get("score", 0)) >= 90]
    return str(accepted[0]["id"]) if accepted else None


def infer_moods(tags: list[str]) -> list[str]:
    moods: list[str] = []
    for tag in tags:
        moods.extend(MOOD_BY_TAG.get(tag.lower(), []))
    return list(dict.fromkeys(moods))[:4] or ["reflective"]


def build(limit_per_artist: int) -> dict[str, Any]:
    seed_artists = yaml.safe_load((ROOT / "data" / "seed_artists.yaml").read_text(encoding="utf-8")) or []
    discovery_artists = yaml.safe_load((ROOT / "data" / "discovery_artists.yaml").read_text(encoding="utf-8")) or []
    seed_artists.extend(discovery_artists)
    recordings: dict[str, dict[str, Any]] = {}
    resolved: list[dict[str, Any]] = []
    with httpx.Client(headers=HEADERS, timeout=25.0) as client:
        for artist in seed_artists:
            if artist["id"] in EXCLUDED_ARTIST_IDS:
                continue
            try:
                mbid = resolve_artist_mbid(client, artist)
                if not mbid:
                    resolved.append({"artist_id": artist["id"], "status": "unresolved"})
                    continue
                payload = request_json(client, "recording", {
                    "query": f'arid:{mbid} AND status:official',
                    "limit": max(5, min(limit_per_artist, 100)),
                })
                artist_tags = [str(tag).lower() for tag in artist.get("tags", [])]
                tags = list(dict.fromkeys(["mandopop", *artist_tags]))[:6]
                moods = infer_moods(tags)
                count = 0
                for item in payload.get("recordings", []):
                    title = str(item.get("title") or "").strip()
                    recording_mbid = item.get("id")
                    if not title or not recording_mbid:
                        continue
                    first_date = str(item.get("first-release-date") or "")
                    year = int(first_date[:4]) if first_date[:4].isdigit() else None
                    recording_id = f"mb-{recording_mbid}"
                    recordings[recording_id] = {
                        "id": recording_id,
                        "title": title,
                        "artist_id": artist["id"],
                        "year": year,
                        "language": "zh",
                        "is_cpop": True,
                        "tags": tags,
                        "moods": moods,
                        "mbid": recording_mbid,
                        "source_urls": [f"https://musicbrainz.org/recording/{recording_mbid}"],
                    }
                    count += 1
                resolved.append({"artist_id": artist["id"], "mbid": mbid, "recording_count": count, "status": "ok"})
            except (httpx.HTTPError, ValueError) as error:
                resolved.append({"artist_id": artist["id"], "status": "error", "error": str(error)})
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "MusicBrainz",
        "artists": [],
        "releases": [],
        "recordings": list(recordings.values()),
        "sync_report": resolved,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-per-artist", type=int, default=35)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "open_catalog.json")
    args = parser.parse_args()
    catalog = build(args.limit_per_artist)
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        merged = {item["id"]: item for item in previous.get("recordings", [])}
        merged.update({item["id"]: item for item in catalog["recordings"]})
        catalog["recordings"] = list(merged.values())
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(catalog['recordings'])} recordings to {args.output}")


if __name__ == "__main__":
    main()
