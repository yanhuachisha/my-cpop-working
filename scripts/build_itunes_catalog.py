from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {"vincent-fang", "michael-lin", "chung-hsing-min"}
MOODS = {
    "r&b": ["late-night", "warm"], "rock": ["uplifting", "resilient"],
    "ballad": ["reflective", "bittersweet"], "chinese-style": ["nostalgic", "elegant"],
    "campus": ["youthful", "warm"], "soul": ["intimate", "warm"],
}


def normalize(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", value.lower())


def infer_moods(tags: list[str]) -> list[str]:
    values: list[str] = []
    for tag in tags:
        values.extend(MOODS.get(tag.lower(), []))
    return list(dict.fromkeys(values))[:4] or ["reflective"]


def main() -> None:
    artists = yaml.safe_load((ROOT / "data" / "seed_artists.yaml").read_text(encoding="utf-8")) or []
    artists.extend(yaml.safe_load((ROOT / "data" / "discovery_artists.yaml").read_text(encoding="utf-8")) or [])
    recordings = {}
    report = []
    with httpx.Client(timeout=18.0, headers={"User-Agent": "C-Pop-Atlas/0.2"}) as client:
        for artist in artists:
            if artist["id"] in EXCLUDED:
                continue
            response = client.get("https://itunes.apple.com/search", params={
                "term": artist["name"], "country": "CN", "media": "music", "entity": "song",
                "attribute": "artistTerm", "limit": 100,
            })
            response.raise_for_status()
            aliases = [artist["name"], *artist.get("aliases", [])]
            accepted_names = [normalize(value) for value in aliases if value]
            count = 0
            tags = list(dict.fromkeys(["mandopop", *[str(tag).lower() for tag in artist.get("tags", [])]]))[:6]
            for item in response.json().get("results", []):
                item_artist = str(item.get("artistName") or "")
                if not any(name and (name in normalize(item_artist) or normalize(item_artist) in name) for name in accepted_names):
                    continue
                title = str(item.get("trackName") or "").strip()
                track_id = item.get("trackId")
                if not title or not track_id:
                    continue
                release_date = str(item.get("releaseDate") or "")
                year = int(release_date[:4]) if release_date[:4].isdigit() else None
                recording_id = f"itunes-{track_id}"
                recordings[recording_id] = {
                    "id": recording_id, "title": title, "artist_id": artist["id"], "year": year,
                    "language": "zh", "is_cpop": True, "tags": tags, "moods": infer_moods(tags),
                    "preview_url": item.get("previewUrl"),
                    "source_urls": [value for value in [item.get("trackViewUrl"), item.get("collectionViewUrl")] if value],
                }
                count += 1
            report.append({"artist_id": artist["id"], "recording_count": count})
    output = ROOT / "data" / "itunes_catalog.json"
    output.write_text(json.dumps({
        "generated_at": datetime.now(UTC).isoformat(), "source": "Apple iTunes Search API",
        "artists": [], "releases": [], "recordings": list(recordings.values()), "sync_report": report,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(recordings)} recordings to {output}")


if __name__ == "__main__":
    main()
