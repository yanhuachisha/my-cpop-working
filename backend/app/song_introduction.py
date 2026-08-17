from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

import httpx
from langchain_openai import ChatOpenAI
from openai import OpenAIError

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
            headers={"User-Agent": "C-Pop-Atlas/0.3"},
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


def _fallback(title: str, artist: str | None, album: str | None, year: int | None, genre: str | None) -> dict[str, Any]:
    performer = artist or "暂未识别歌手"
    facts = [f"演唱：{performer}"]
    if album:
        facts.append(f"收录：{album}")
    if year:
        facts.append(f"发行：{year} 年")
    if genre:
        facts.append(f"类型：{genre}")
    known = "，".join(facts[1:])
    narrative = f"《{title}》是{performer}演唱的作品"
    narrative += f"，{known}" if known else ""
    narrative += "。这段简介只采用能够核实的目录资料；暂未找到可靠来源的创作背景不会被写成事实。聆听时可以继续关注演唱表达、段落推进和整体声音气质。"
    return {
        "subtitle": f"《{title}》歌曲简介",
        "narrative": narrative,
        "themes": [genre] if genre else [],
        "listening_points": [
            f"先听{performer}如何用第一句为《{title}》定下情绪",
            f"留意《{title}》从主歌进入副歌时，力度和叙述视角怎样变化",
            f"找出最能代表《{title}》气质的一种声音，并观察它何时出现",
        ],
        "facts": facts,
        "story_type": "catalog-introduction",
    }


def _model_introduction(title: str, artist: str | None, facts: dict[str, Any]) -> dict[str, Any] | None:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    prompt = {
        "song": title,
        "artist": artist,
        "verified_catalog_facts": facts,
    }
    try:
        model = ChatOpenAI(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0.2,
            timeout=16,
            max_retries=0,
            max_tokens=500,
        )
        message = model.invoke([
            {
                "role": "system",
                "content": "你是严谨的中文歌曲资料编辑。根据已核实目录事实写歌曲简介。不得编造专辑、年份、词曲作者、获奖、创作背景或人物关系；事实不足时明确说公开资料有限。可以给出克制的听感解读，但要与事实区分。不要输出数据库标签、英文内部字段或完整歌词。只输出 JSON：subtitle、narrative、themes、listening_points。themes 最多3项，listening_points固定3项。",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ])
        content = str(message.content).strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
        parsed = json.loads(content)
        if not isinstance(parsed.get("narrative"), str):
            return None
        return parsed
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, RuntimeError, OpenAIError):
        return None


def song_introduction(title: str, artist: str | None = None, album: str | None = None, year: int | None = None) -> dict[str, Any]:
    key = _cache_key(title, artist)
    with _cache_lock:
        cache = _read_cache()
        if key in cache and cache[key].get("schema_version") == 3:
            return cache[key]
    online = _itunes_metadata(title, artist)
    resolved_artist = str(online.get("artist") or artist or "未知歌手")
    resolved_album = str(online.get("album") or album or "") or None
    resolved_year = online.get("year") or year
    genre = str(online.get("genre") or "") or None
    verified = {"artist": resolved_artist, "album": resolved_album, "year": resolved_year, "genre": genre}
    result = _fallback(title, resolved_artist, resolved_album, resolved_year, genre)
    generated = _model_introduction(title, resolved_artist, verified)
    if generated:
        result.update({
            "subtitle": str(generated.get("subtitle") or result["subtitle"]),
            "narrative": str(generated.get("narrative") or result["narrative"]),
            "themes": [str(item) for item in generated.get("themes", [])[:3]],
            "listening_points": [str(item) for item in generated.get("listening_points", [])[:3]] or result["listening_points"],
            "story_type": "ai-introduction",
        })
    result["source_urls"] = [online["source_url"]] if online.get("source_url") else []
    result["generated_at"] = datetime.now(UTC).isoformat()
    result["schema_version"] = 3
    with _cache_lock:
        cache = _read_cache()
        cache[key] = result
        _write_cache(cache)
    return result
