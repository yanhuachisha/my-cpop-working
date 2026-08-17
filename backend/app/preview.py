from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

import httpx

from app.models import Artist, Recording

DEEZER_SEARCH_URL = "https://api.deezer.com/search"
REQUEST_TIMEOUT = httpx.Timeout(2.5, connect=1.0)
TITLE_ALIASES = {
    "jay-chou-dongfengpo": ["東風破"],
    "jay-chou-yifuzhiming": ["In The Name of Father", "以父之名"],
    "tao-ordinary-friend": ["Regular Friends", "普通朋友"],
    "stefanie-dark-day": ["The Dark Day", "Cloudy Day", "天黑黑"],
}


def _candidate_queries(recording: Recording, artist: Artist) -> list[str]:
    ascii_aliases = [alias for alias in artist.aliases if alias.isascii()]
    best_artist_name = next((name for name in [*ascii_aliases, artist.sort_name, artist.name] if name), "")
    title_candidates = [recording.title, *TITLE_ALIASES.get(recording.id, [])]
    queries = title_candidates[:]
    if best_artist_name:
        queries.extend(f"{best_artist_name} {title}" for title in title_candidates)
    return list(dict.fromkeys(queries))


@lru_cache(maxsize=512)
def resolve_preview_url(recording_id: str, recording_title: str, artist_name: str, aliases: str) -> str | None:
    if os.getenv("CPOP_DISABLE_PREVIEW_LOOKUP") == "1":
        return None

    artist = Artist(
        id=recording_id,
        name=artist_name,
        aliases=[alias for alias in aliases.split("|") if alias],
    )
    recording = Recording(id=recording_id, title=recording_title, artist_id=recording_id)

    for query in _candidate_queries(recording, artist):
        try:
            response = httpx.get(DEEZER_SEARCH_URL, params={"q": query}, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            continue

        for item in payload.get("data", []):
            preview = item.get("preview")
            title = item.get("title") or item.get("title_short") or ""
            item_artist = (item.get("artist") or {}).get("name", "")
            title_aliases = TITLE_ALIASES.get(recording_id, [])
            if preview and _title_matches(recording_title, title, title_aliases) and _artist_matches(artist, item_artist):
                return preview
    return None


def _title_matches(expected: str, actual: str, aliases: list[str] | None = None) -> bool:
    expected_values = [expected, *(aliases or [])]
    actual_norm = _normalize_title(actual)
    for value in expected_values:
        expected_norm = _normalize_title(value)
        if expected_norm and (expected_norm in actual_norm or actual_norm in expected_norm):
            return True

    expected_hanzi = {char for value in expected_values for char in value if "\u4e00" <= char <= "\u9fff"}
    actual_hanzi = {char for char in actual if "\u4e00" <= char <= "\u9fff"}
    if not expected_hanzi:
        return False
    return len(expected_hanzi & actual_hanzi) >= min(2, len(expected_hanzi))


def _normalize_title(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _artist_matches(expected: Artist, actual: str) -> bool:
    actual_norm = _normalize_title(actual)
    names = [expected.name, expected.sort_name or "", *expected.aliases]
    for name in names:
        expected_norm = _normalize_title(name)
        if expected_norm and (expected_norm in actual_norm or actual_norm in expected_norm):
            return True
    expected_hanzi = {char for name in names for char in name if "\u4e00" <= char <= "\u9fff"}
    actual_hanzi = {char for char in actual if "\u4e00" <= char <= "\u9fff"}
    return bool(expected_hanzi and expected_hanzi & actual_hanzi)


def attach_preview_url(recording: Recording, artist: Artist | None) -> Recording:
    if recording.preview_url or artist is None:
        return recording
    preview_url = resolve_preview_url(
        recording.id,
        recording.title,
        artist.name,
        "|".join(artist.aliases[:2]),
    )
    if preview_url:
        recording.preview_url = preview_url
    return recording


def attach_preview_urls(recordings: list[Recording], artist_lookup: dict[str, Artist]) -> list[Recording]:
    unresolved = [recording for recording in recordings if not recording.preview_url]
    if not unresolved:
        return recordings

    with ThreadPoolExecutor(max_workers=min(8, len(unresolved))) as executor:
        futures = {
            executor.submit(attach_preview_url, recording, artist_lookup.get(recording.artist_id)): recording
            for recording in unresolved
        }
        for future in as_completed(futures):
            future.result()
    return recordings
