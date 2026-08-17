from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, Field

from app.data_store import get_store

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LIBRARY_PATH = DATA_DIR / "user_library.json"
KUGOU_DIR = Path(os.getenv("APPDATA", "")) / "KuGou8"
_library_lock = RLock()

class LibraryImportRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500_000)
    order: Literal["auto", "title_artist", "artist_title"] = "auto"
    playlist_name: str = "酷狗收藏"


def discover_kugou() -> dict:
    files = []
    for name in ("playlistV3.db", "KGMusicV3.db", "RecentlyMusicV3.db", "KuGou.ini"):
        path = KUGOU_DIR / name
        if path.exists():
            files.append({"name": name, "size": path.stat().st_size, "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat()})
    return {
        "installed": KUGOU_DIR.exists(), "directory": str(KUGOU_DIR) if KUGOU_DIR.exists() else None,
        "files": files, "database_format": "proprietary" if any(item["name"].endswith(".db") for item in files) else "unknown",
        "automatic_read_supported": False,
        "recommended_method": "从酷狗复制或导出歌单文本后导入；系统只保存歌曲名和歌手，不复制音频。",
    }


def _slug(value: str) -> str:
    return hashlib.sha1(value.strip().lower().encode("utf-8")).hexdigest()[:14]


def _repair_mojibake(value: str) -> str:
    text = value.strip()
    try:
        raw = text.encode("latin1")
    except UnicodeEncodeError:
        return text
    original_cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    for encoding in ("utf-8", "gb18030"):
        try:
            decoded = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if len(re.findall(r"[\u3400-\u9fff]", decoded)) > original_cjk:
            return decoded
    return text


def _embedded_csv_fields(value: str) -> list[str]:
    candidate = value.strip()
    if '\",\"' not in candidate:
        return []
    if not candidate.startswith('"'):
        candidate = f'"{candidate}'
    try:
        fields = next(csv.reader(io.StringIO(candidate)))
    except (csv.Error, StopIteration):
        return []
    return [field.strip() for field in fields]


def _normalize_entry(title: str, artist: str) -> tuple[str, str]:
    fields = _embedded_csv_fields(title)
    if len(fields) >= 2:
        title, artist = fields[0], fields[1] or artist
    else:
        fields = _embedded_csv_fields(artist)
        if len(fields) >= 2:
            title, artist = fields[0], fields[1]
    clean_artist = _repair_mojibake(artist).strip().strip('"').strip()
    clean_title = _repair_mojibake(title).strip().strip('"').strip()
    clean_title = re.sub(
        r"\.(mp3|flac|wav|m4a|aac|ogg)$",
        "",
        clean_title,
        flags=re.IGNORECASE,
    ).strip()
    clean_artist = clean_artist or "\u672a\u77e5\u6b4c\u624b"
    artist_prefix = re.compile(
        rf"^{re.escape(clean_artist)}\s*[-\u2014\u2013]\s*",
        flags=re.IGNORECASE,
    )
    clean_title = artist_prefix.sub("", clean_title).strip() or clean_title
    return clean_title, clean_artist


def _split_line(line: str, order: str) -> tuple[str, str] | None:
    cleaned = re.sub(r"^\s*\d+[.、)\]]\s*", "", line.strip())
    if not cleaned:
        return None
    parts = [part.strip() for part in re.split(r"\t|\s+[|｜—–-]\s+", cleaned, maxsplit=1) if part.strip()]
    if len(parts) < 2:
        return cleaned, "未知歌手"
    first, second = parts[0], parts[1]
    if order == "artist_title":
        return second, first
    if order == "title_artist":
        return first, second
    artist_markers = ("乐队", "组合", "合唱团")
    if first.endswith(artist_markers) or len(first) <= 4 < len(second):
        return second, first
    return first, second


def _clean_csv_title(title: str, artist: str) -> str:
    cleaned = re.sub(r"\.(mp3|flac|wav|m4a|aac|ogg)$", "", title.strip(), flags=re.IGNORECASE)
    artist_prefix = re.compile(rf"^{re.escape(artist.strip())}\s*[-—–]\s*", flags=re.IGNORECASE)
    return artist_prefix.sub("", cleaned).strip() or cleaned


def _parse_entries(text: str, order: str) -> list[tuple[str, str]]:
    rows = list(csv.reader(io.StringIO(text)))
    if rows and max((len(row) for row in rows), default=0) >= 2:
        header = [cell.strip().lstrip("\ufeff").casefold() for cell in rows[0]]
        title_names = {"歌名", "歌曲", "歌曲名", "文件名", "title", "song"}
        artist_names = {"歌手", "歌手名", "艺人", "artist", "singer"}
        title_index = next((index for index, value in enumerate(header) if value in title_names), None)
        artist_index = next((index for index, value in enumerate(header) if value in artist_names), None)
        if title_index is not None and artist_index is not None:
            entries = []
            for row in rows[1:]:
                if max(title_index, artist_index) >= len(row):
                    continue
                title, artist = _normalize_entry(row[title_index], row[artist_index])
                if title:
                    entries.append((title, artist or "未知歌手"))
            return entries
    entries = []
    for line in text.splitlines():
        parsed = _split_line(line, order)
        if parsed:
            entries.append(_normalize_entry(*parsed))
    return entries


def _repair_library_payload(payload: dict) -> dict:
    artists = {item["id"]: item for item in payload.get("artists", [])}
    artist_name_votes: dict[str, Counter] = defaultdict(Counter)
    repaired_recordings = 0
    for recording in payload.get("recordings", []):
        artist_id = recording.get("artist_id", "")
        artist = artists.get(artist_id, {})
        old_title = str(recording.get("title") or "")
        old_artist = str(artist.get("name") or "")
        clean_title, clean_artist = _normalize_entry(old_title, old_artist)
        if clean_title and clean_title != old_title:
            recording["title"] = clean_title
            repaired_recordings += 1
        if clean_artist:
            artist_name_votes[artist_id][clean_artist] += 1
    repaired_artists = 0
    for artist_id, votes in artist_name_votes.items():
        artist = artists.get(artist_id)
        if not artist or not votes:
            continue
        clean_name = votes.most_common(1)[0][0]
        if clean_name != artist.get("name"):
            artist["name"] = clean_name
            artist["sort_name"] = clean_name
            repaired_artists += 1
    return {
        "payload": payload,
        "repaired_recordings": repaired_recordings,
        "repaired_artists": repaired_artists,
    }


def repair_library_data() -> dict:
    if not LIBRARY_PATH.exists():
        return {"repaired_recordings": 0, "repaired_artists": 0}
    with _library_lock:
        try:
            payload = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"repaired_recordings": 0, "repaired_artists": 0}
        result = _repair_library_payload(payload)
        LIBRARY_PATH.write_text(
            json.dumps(result["payload"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        get_store.cache_clear()
        return {
            "repaired_recordings": result["repaired_recordings"],
            "repaired_artists": result["repaired_artists"],
        }


def _import_library(request: LibraryImportRequest) -> dict:
    existing = {"artists": [], "releases": [], "recordings": [], "playlists": []}
    if LIBRARY_PATH.exists():
        try:
            existing.update(json.loads(LIBRARY_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    existing = _repair_library_payload(existing)["payload"]
    artists = {item["id"]: item for item in existing.get("artists", [])}
    recordings = {item["id"]: item for item in existing.get("recordings", [])}
    imported_ids = []
    for title, artist_name in _parse_entries(request.text, request.order):
        artist_id = f"user-artist-{_slug(artist_name)}"
        recording_id = f"user-recording-{_slug(f'{artist_name}:{title}')}"
        artists.setdefault(artist_id, {
            "id": artist_id, "name": artist_name, "sort_name": artist_name, "country": "CN", "area": "华语",
            "is_cpop": True, "tags": ["mandopop", "user-library"], "aliases": [], "source_urls": [],
        })
        recordings.setdefault(recording_id, {
            "id": recording_id, "title": title, "artist_id": artist_id, "language": "zh", "is_cpop": True,
            "tags": ["mandopop", "user-library"], "moods": ["familiar"], "source_urls": [],
        })
        imported_ids.append(recording_id)
    playlists = [item for item in existing.get("playlists", []) if item.get("name") != request.playlist_name]
    playlists.append({"name": request.playlist_name, "recording_ids": list(dict.fromkeys(imported_ids)), "updated_at": datetime.now(UTC).isoformat()})
    payload = {"artists": list(artists.values()), "releases": [], "recordings": list(recordings.values()), "playlists": playlists, "updated_at": datetime.now(UTC).isoformat()}
    LIBRARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    get_store.cache_clear()
    return {"imported": len(set(imported_ids)), "total_recordings": len(recordings), "playlist_name": request.playlist_name}


def import_library(request: LibraryImportRequest) -> dict:
    with _library_lock:
        return _import_library(request)


def ensure_library_recording(title: str, artist_name: str | None = None) -> str:
    clean_title = title.strip()
    clean_artist = (artist_name or "未知歌手").strip() or "未知歌手"
    normalized_title = clean_title.casefold()
    normalized_artist = clean_artist.casefold()
    store = get_store()
    for recording in store.search_recordings(clean_title):
        artist = store.get_artist(recording.artist_id)
        if recording.title.strip().casefold() != normalized_title:
            continue
        if artist_name and artist and artist.name.strip().casefold() != normalized_artist:
            continue
        return recording.id

    recording_id = f"user-recording-{_slug(f'{clean_artist}:{clean_title}')}"
    with _library_lock:
        _import_library(LibraryImportRequest(
            text=f"{clean_title} - {clean_artist}",
            order="title_artist",
            playlist_name="酷狗播放记录",
        ))
    return recording_id


def library_status() -> dict:
    if not LIBRARY_PATH.exists():
        return {"recording_count": 0, "artist_count": 0, "playlists": []}
    try:
        payload = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"recording_count": 0, "artist_count": 0, "playlists": []}
    return {"recording_count": len(payload.get("recordings", [])), "artist_count": len(payload.get("artists", [])), "playlists": payload.get("playlists", [])}


def library_collection() -> dict:
    if not LIBRARY_PATH.exists():
        return {"playlists": [], "updated_at": None}
    try:
        payload = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"playlists": [], "updated_at": None}
    artists = {item["id"]: item for item in payload.get("artists", [])}
    recordings = {item["id"]: item for item in payload.get("recordings", [])}
    playlists = []
    for playlist in payload.get("playlists", []):
        songs = []
        for recording_id in playlist.get("recording_ids", []):
            recording = recordings.get(recording_id)
            if not recording:
                continue
            artist = artists.get(recording.get("artist_id"), {})
            songs.append({
                "recording_id": recording_id,
                "title": recording.get("title", "未知歌曲"),
                "artist": artist.get("name", "未知歌手"),
            })
        playlists.append({
            "name": playlist.get("name", "酷狗收藏"),
            "updated_at": playlist.get("updated_at") or payload.get("updated_at"),
            "songs": songs,
        })
    playlists.sort(key=lambda item: item["updated_at"] or "", reverse=True)
    return {"playlists": playlists, "updated_at": payload.get("updated_at")}
