from __future__ import annotations

import re
from typing import Literal
from urllib.parse import quote_plus

import httpx

from app.listener_memory import (
    LyricFragmentRequest,
    MusicNoteRequest,
    save_lyric_fragment,
    save_music_note,
)
from app.models import SourceRef
from app.recommender import DailyRecommender
from app.song_introduction import cached_song_introduction


ListeningMemoryType = Literal["lyric_specimen", "music_note"]


def get_current_song_context_workflow(
    song_title: str | None,
    artist: str | None,
) -> dict[str, object]:
    """Read current track identity and cached material without generating new AI content."""
    if not song_title:
        return {"available": False, "message": "当前没有识别到歌曲。"}
    introduction = cached_song_introduction(song_title, artist)
    return {
        "available": True,
        "song": song_title,
        "artist": artist,
        "cached_material_available": introduction is not None,
        "portrait": introduction.get("narrative") if introduction else None,
        "themes": introduction.get("themes", []) if introduction else [],
        "listening_points": introduction.get("listening_points", []) if introduction else [],
        "facts": introduction.get("facts", []) if introduction else [],
    }


def save_listening_memory_workflow(
    memory_type: ListeningMemoryType,
    content: str,
    song_title: str | None,
    artist: str | None,
) -> dict[str, object]:
    """Persist exact user-provided text as a lyric specimen or music note."""
    clean_content = content.strip()
    if not clean_content:
        return {"saved": False, "message": "没有找到可保存的用户原文。"}
    if memory_type == "lyric_specimen":
        fragment = save_lyric_fragment(LyricFragmentRequest(
            excerpt=clean_content,
            song_title=song_title,
            artist=artist,
            note="通过音乐陪伴收藏",
        ))
        return {
            "saved": True,
            "memory_type": memory_type,
            "content": clean_content[:100],
            "saved_at": fragment.get("saved_at"),
        }
    note = save_music_note(MusicNoteRequest(
        content=clean_content,
        prompt="通过音乐陪伴记录此刻感受",
        song_title=song_title,
        artist=artist,
    ))
    return {
        "saved": True,
        "memory_type": memory_type,
        "content": clean_content[:120],
        "saved_at": note.get("saved_at"),
    }


def find_similar_recordings_workflow(
    recommender: DailyRecommender,
    recording_id: str,
    limit: int = 3,
) -> dict[str, object]:
    """Rank similar local recordings with the deterministic similarity algorithm."""
    recordings = recommender.similar_recordings(recording_id, limit=max(1, min(limit, 10)))
    return {
        "recording_id": recording_id,
        "items": [
            {
                "recording_id": item.id,
                "title": item.title,
                "artist_id": item.artist_id,
                "year": item.year,
                "tags": item.tags,
                "moods": item.moods,
            }
            for item in recordings
        ],
    }


def search_song_sources_workflow(
    song_title: str | None,
    artist: str | None,
) -> dict[str, object]:
    """Retrieve attributable song sources without model-generated synthesis."""
    title = song_title or "当前歌曲"
    query = " ".join(part for part in (artist, title) if part)
    facts: list[str] = []
    sources: list[SourceRef] = []
    errors: list[str] = []
    try:
        response = httpx.get(
            "https://zh.wikipedia.org/w/api.php",
            params={
                "action": "query", "generator": "search", "gsrsearch": query,
                "gsrlimit": 3, "prop": "extracts|info", "exintro": 1,
                "explaintext": 1, "inprop": "url", "format": "json", "origin": "*",
            },
            headers={"User-Agent": "My-C-Pop-Working/0.4 song-source-workflow"},
            timeout=8.0,
        )
        response.raise_for_status()
        pages = list(response.json().get("query", {}).get("pages", {}).values())
        for page in pages[:2]:
            extract = re.sub(r"\s+", " ", str(page.get("extract") or "")).strip()
            if extract:
                facts.append(f"维基百科《{page.get('title', '')}》：{extract[:700]}")
            if page.get("fullurl"):
                sources.append(SourceRef(
                    name=f"维基百科：{page.get('title', title)}",
                    url=page["fullurl"],
                    license="CC BY-SA",
                ))
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
        errors.append(f"Wikipedia: {type(error).__name__}")
    try:
        response = httpx.get(
            "https://musicbrainz.org/ws/2/recording/",
            params={"query": f'recording:"{title}" AND artist:"{artist or ""}"', "fmt": "json", "limit": 3},
            headers={"User-Agent": "My-C-Pop-Working/0.4 song-source-workflow"},
            timeout=8.0,
        )
        response.raise_for_status()
        recordings = response.json().get("recordings", [])
        if recordings:
            item = recordings[0]
            releases = [
                release.get("title") for release in item.get("releases", [])[:3]
                if release.get("title")
            ]
            facts.append(
                f"MusicBrainz：匹配到录音《{item.get('title', title)}》，首次发行日期 "
                f"{item.get('first-release-date') or '未标注'}，相关发行版本："
                f"{'、'.join(releases) or '未标注'}。"
            )
            sources.append(SourceRef(
                name="MusicBrainz recording search",
                url=f"https://musicbrainz.org/search?query={quote_plus(query)}&type=recording&method=indexed",
                license="CC0 core data",
            ))
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
        errors.append(f"MusicBrainz: {type(error).__name__}")
    return {
        "available": bool(facts),
        "song": title,
        "artist": artist,
        "facts": facts,
        "sources": [source.model_dump() for source in sources],
        "errors": errors,
    }
