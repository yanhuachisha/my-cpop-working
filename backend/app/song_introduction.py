from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.song_portrait_agent import generate_song_portrait

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CACHE_PATH = DATA_DIR / "song_introductions.json"
_cache_lock = RLock()


def _normalize(value: str | None) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", (value or "").casefold())


def _cache_key(title: str, artist: str | None) -> str:
    raw = f"{_normalize(title)}:{_normalize(artist)}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _read_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(payload: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def retain_current_song_cache(title: str | None, artist: str | None) -> None:
    with _cache_lock:
        cache = _read_cache()
        key = _cache_key(title, artist) if title else None
        retained = {key: cache[key]} if key and key in cache else {}
        if retained != cache:
            _write_cache(retained)


def _itunes_metadata(title: str, artist: str | None) -> dict[str, Any]:
    try:
        response = httpx.get(
            "https://itunes.apple.com/search",
            params={"term": f"{artist or ''} {title}".strip(), "country": "CN", "media": "music", "entity": "song", "limit": 12},
            headers={"User-Agent": "My-CPop-Working/0.4 song-material-tool"},
            timeout=5.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return {}
    title_key = _normalize(title)
    artist_key = _normalize(artist)
    if not title_key:
        return {}
    candidates = []
    for item in response.json().get("results", []):
        item_title = _normalize(item.get("trackName"))
        item_artist = _normalize(item.get("artistName"))
        title_match = item_title == title_key or title_key in item_title or item_title in title_key
        artist_match = not artist_key or artist_key in item_artist or item_artist in artist_key
        if title_match and artist_match:
            candidates.append(item)
    if not candidates:
        return {}
    item = candidates[0]
    release_date = str(item.get("releaseDate") or "")
    return {
        "artist": item.get("artistName"),
        "album": item.get("collectionName"),
        "year": int(release_date[:4]) if release_date[:4].isdigit() else None,
        "genre": item.get("primaryGenreName"),
        "source_url": item.get("trackViewUrl") or item.get("collectionViewUrl"),
    }


def _musicbrainz_metadata(title: str, artist: str | None) -> dict[str, Any]:
    query = f'recording:"{title}" AND artist:"{artist or ""}"'
    try:
        response = httpx.get(
            "https://musicbrainz.org/ws/2/recording/",
            params={"query": query, "fmt": "json", "limit": 5},
            headers={"User-Agent": "My-CPop-Working/0.4 song-material-tool"},
            timeout=7.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return {}
    title_key = _normalize(title)
    artist_key = _normalize(artist)
    for item in response.json().get("recordings", []):
        if _normalize(item.get("title")) != title_key:
            continue
        credit = " ".join(
            str(entry.get("name") or "")
            for entry in item.get("artist-credit", [])
            if isinstance(entry, dict)
        )
        if artist_key and _normalize(credit) != artist_key:
            continue
        releases = [release for release in item.get("releases", []) if release.get("title")]
        first_release = str(item.get("first-release-date") or "")
        return {
            "artist": credit or artist,
            "album": releases[0]["title"] if releases else None,
            "year": int(first_release[:4]) if first_release[:4].isdigit() else None,
            "source_url": f"https://musicbrainz.org/search?query={quote_plus(query)}&type=recording&method=indexed",
        }
    return {}


def _search_song_material(
    title: str,
    artist: str | None,
    album: str | None,
    year: int | None,
) -> dict[str, Any]:
    itunes = _itunes_metadata(title, artist)
    musicbrainz = _musicbrainz_metadata(title, artist)
    resolved_artist = str(itunes.get("artist") or musicbrainz.get("artist") or artist or "") or None
    resolved_album = str(itunes.get("album") or musicbrainz.get("album") or album or "") or None
    resolved_year = itunes.get("year") or musicbrainz.get("year") or year
    genre = str(itunes.get("genre") or "") or None
    facts = []
    if resolved_artist:
        facts.append(f"演唱：{resolved_artist}")
    if resolved_album:
        facts.append(f"收录：{resolved_album}")
    if resolved_year:
        facts.append(f"发行：{resolved_year} 年")
    if genre:
        facts.append(f"类型：{genre}")
    source_urls = list(dict.fromkeys(
        url for url in (itunes.get("source_url"), musicbrainz.get("source_url")) if url
    ))
    return {
        "artist": resolved_artist,
        "album": resolved_album,
        "year": resolved_year,
        "genre": genre,
        "facts": facts,
        "source_urls": source_urls,
    }


def _fallback(title: str, artist: str | None, album: str | None, year: int | None, genre: str | None) -> dict[str, Any]:
    performer = artist or "这位演唱者"
    facts = [f"演唱：{artist}"] if artist else []
    if album:
        facts.append(f"收录：{album}")
    if year:
        facts.append(f"发行：{year} 年")
    if genre:
        facts.append(f"类型：{genre}")
    return {
        "subtitle": _poetic_subtitle(title),
        "narrative": _emotional_fallback(title, performer),
        "themes": [genre] if genre else [],
        "listening_points": [
            f"先听{performer}如何用第一句为《{title}》定下情绪",
            f"留意《{title}》从主歌进入副歌时，力度和叙述视角怎样变化",
            f"找出最能代表《{title}》气质的一种声音，并观察它何时出现",
        ],
        "facts": facts,
        "story_type": "emotional-fallback",
    }


def _poetic_subtitle(title: str) -> str:
    normalized = title.casefold()
    if "不是真正的快乐" in title:
        return "微笑底下的裂痕"
    if "monster" in normalized or "怪物" in title:
        return "与心里的怪物对视"
    if "快乐" in title or "微笑" in title:
        return "笑意背后的暗潮"
    if "雨" in title:
        return "雨声里的旧回音"
    if "夜" in title:
        return "夜色没有说完"
    if "爱" in title or "love" in normalized:
        return "靠近之前的犹豫"
    return "情绪拐弯的地方"


def _emotional_fallback(title: str, performer: str) -> str:
    normalized = title.casefold()
    if "不是真正的快乐" in title:
        return "它写的不是失去快乐，而是一个人已经习惯把难过藏进正常表情里。越平静的段落，越像在压住快要浮上来的情绪；等旋律真正抬高时，才听见那份努力维持的体面正在松动。"
    if "monster" in normalized or "怪物" in title:
        return "它更像一次对内心阴影的凝视：害怕、孤独和自我怀疑被放到眼前，却没有急着给出答案。声音向前推进时，那些无法命名的情绪也慢慢获得轮廓，像终于承认脆弱本身并不可耻。"
    return f"《{title}》像一段迟迟没有说完的心事。{performer}的声音一次次靠近情绪的边缘：表面仍然克制，里面却有某种感受正在变重，直到旋律替人承认那一部分一直被藏起来的自己。"


def _clean_narrative(value: str, fallback: str) -> str:
    cleaned = re.sub(
        r"[^。！？]*(?:公开资料|资料有限|此处不作展开|暂未找到|无法确认|不做推测)[^。！？]*[。！？]?",
        "",
        value,
    ).strip()
    return cleaned if len(cleaned) >= 35 else fallback


def _valid_subtitle(value: str, title: str) -> bool:
    text = value.strip().strip("《》‘’“”")
    return 4 <= len(text) <= 14 and title not in text and not any(
        word in text for word in ("歌曲简介", "演唱", "专辑", "发行", "现场版")
    )


def song_introduction(title: str, artist: str | None = None, album: str | None = None, year: int | None = None) -> dict[str, Any]:
    key = _cache_key(title, artist)
    with _cache_lock:
        cache = _read_cache()
        if key in cache and cache[key].get("schema_version") == 4:
            return cache[key]
    result = _fallback(title, artist, album, year, None)
    generated = generate_song_portrait(title, artist, album, year, _search_song_material)
    if generated:
        verified = generated.get("verified", {})
        resolved_artist = verified.get("artist") or artist
        resolved_album = verified.get("album") or album
        resolved_year = verified.get("year") or year
        genre = verified.get("genre")
        fallback = _fallback(title, resolved_artist, resolved_album, resolved_year, genre)
        subtitle = str(generated.get("subtitle") or "").strip()
        result.update({
            "subtitle": subtitle if _valid_subtitle(subtitle, title) else fallback["subtitle"],
            "narrative": _clean_narrative(str(generated.get("narrative") or ""), fallback["narrative"]),
            "themes": [str(item) for item in generated.get("themes", [])[:3]],
            "listening_points": [str(item) for item in generated.get("listening_points", [])[:3]] or fallback["listening_points"],
            "facts": list(verified.get("facts", [])),
            "source_urls": list(verified.get("source_urls", [])),
            "tools_used": list(generated.get("tools_used", [])),
            "story_type": "langchain-agent-portrait",
        })
    result.setdefault("source_urls", [])
    result.setdefault("tools_used", [])
    result["generated_at"] = datetime.now(UTC).isoformat()
    result["schema_version"] = 4
    with _cache_lock:
        cache = _read_cache()
        cache[key] = result
        _write_cache(cache)
    return result
