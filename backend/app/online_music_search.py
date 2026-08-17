from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import httpx


ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
MUSICBRAINZ_SEARCH_URL = "https://musicbrainz.org/ws/2/recording/"
USER_AGENT = "My-C-Pop-Working/0.1 (local personal music agent)"


def _itunes_results(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    results = []
    for item in payload.get("results", [])[:limit]:
        if not item.get("trackName") or not item.get("artistName"):
            continue
        results.append({
            "source": "Apple iTunes Search API",
            "source_id": str(item.get("trackId") or ""),
            "title": item["trackName"],
            "artist": item["artistName"],
            "album": item.get("collectionName"),
            "release_date": item.get("releaseDate"),
            "genre": item.get("primaryGenreName"),
            "preview_url": item.get("previewUrl"),
            "artwork_url": item.get("artworkUrl100"),
            "url": item.get("trackViewUrl") or item.get("collectionViewUrl"),
        })
    return results


def _musicbrainz_artist(item: dict[str, Any]) -> str:
    credits = []
    for credit in item.get("artist-credit", []):
        if isinstance(credit, str):
            credits.append(credit)
        elif isinstance(credit, dict) and credit.get("name"):
            credits.append(str(credit["name"]))
            if credit.get("joinphrase"):
                credits.append(str(credit["joinphrase"]))
    return "".join(credits).strip()


def _musicbrainz_results(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    results = []
    for item in payload.get("recordings", [])[:limit]:
        title = str(item.get("title") or "").strip()
        artist = _musicbrainz_artist(item)
        if not title or not artist:
            continue
        releases = [release for release in item.get("releases", []) if release.get("title")]
        recording_id = str(item.get("id") or "")
        results.append({
            "source": "MusicBrainz",
            "source_id": recording_id,
            "title": title,
            "artist": artist,
            "album": releases[0]["title"] if releases else None,
            "release_date": item.get("first-release-date"),
            "genre": None,
            "preview_url": None,
            "artwork_url": None,
            "url": f"https://musicbrainz.org/recording/{recording_id}" if recording_id else None,
            "score": item.get("score"),
        })
    return results


def _deduplicate(results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    deduplicated = []
    seen = set()
    for item in results:
        key = (str(item.get("title") or "").casefold(), str(item.get("artist") or "").casefold())
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(item)
        if len(deduplicated) >= limit:
            break
    return deduplicated


def search_online_music(
    query: str,
    limit: int = 8,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    clean_query = query.strip()
    if not clean_query:
        return {"query": query, "results": [], "sources": [], "errors": ["empty query"]}
    result_limit = max(1, min(int(limit), 20))
    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(7.0, connect=3.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    results: list[dict[str, Any]] = []
    sources = []
    errors = []
    try:
        try:
            response = active_client.get(
                ITUNES_SEARCH_URL,
                params={
                    "term": clean_query,
                    "country": "CN",
                    "media": "music",
                    "entity": "song",
                    "limit": result_limit,
                },
            )
            response.raise_for_status()
            results.extend(_itunes_results(response.json(), result_limit))
            sources.append({
                "name": "Apple iTunes Search API",
                "url": f"https://music.apple.com/cn/search?term={quote_plus(clean_query)}",
            })
        except (httpx.HTTPError, ValueError, TypeError) as error:
            errors.append(f"iTunes: {type(error).__name__}")

        try:
            response = active_client.get(
                MUSICBRAINZ_SEARCH_URL,
                params={"query": clean_query, "fmt": "json", "limit": result_limit},
            )
            response.raise_for_status()
            results.extend(_musicbrainz_results(response.json(), result_limit))
            sources.append({
                "name": "MusicBrainz",
                "url": (
                    "https://musicbrainz.org/search?query="
                    f"{quote_plus(clean_query)}&type=recording&method=indexed"
                ),
            })
        except (httpx.HTTPError, ValueError, TypeError) as error:
            errors.append(f"MusicBrainz: {type(error).__name__}")
    finally:
        if owns_client:
            active_client.close()
    return {
        "query": clean_query,
        "online": bool(results),
        "results": _deduplicate(results, result_limit),
        "sources": sources,
        "errors": errors,
    }
