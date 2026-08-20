from __future__ import annotations

import ctypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
import email.utils
import os
import platform
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.data_store import DataStore

WEATHER_CODES = {
    0: ("晴朗", "clear"), 1: ("大致晴朗", "clear"), 2: ("多云", "cloudy"), 3: ("阴天", "overcast"),
    45: ("有雾", "fog"), 48: ("雾凇", "fog"), 51: ("毛毛雨", "drizzle"), 53: ("小雨", "rain"),
    55: ("较强细雨", "rain"), 61: ("小雨", "rain"), 63: ("中雨", "rain"), 65: ("大雨", "storm"),
    71: ("小雪", "snow"), 73: ("中雪", "snow"), 75: ("大雪", "snow"), 80: ("阵雨", "rain"),
    81: ("较强阵雨", "storm"), 82: ("强阵雨", "storm"), 95: ("雷雨", "storm"), 96: ("雷雨冰雹", "storm"),
}

WEATHER_MOODS = {
    "clear": ["sunny", "youthful", "warm"], "cloudy": ["gentle", "reflective"],
    "overcast": ["late-night", "bittersweet", "reflective"], "fog": ["dreamy", "cinematic"],
    "drizzle": ["nostalgic", "gentle", "poetic"], "rain": ["late-night", "bittersweet", "narrative"],
    "storm": ["dramatic", "dark", "rock"], "snow": ["warm", "intimate", "nostalgic"],
}

@dataclass
class TimedCache:
    value: Any = None
    expires_at: float = 0

_weather_cache = TimedCache()
_news_cache = TimedCache()


NEWS_ANCHOR_STOPWORDS = {"music", "news", "video", "live", "official"}


def _normalize_news_title(value: str) -> str:
    without_publisher = re.sub(r"\s+-\s+[^-]{2,40}$", "", value.strip())
    return re.sub(r"[\W_]+", "", without_publisher.casefold())


def _news_title_anchors(value: str) -> set[str]:
    without_publisher = re.sub(r"\s+-\s+[^-]{2,40}$", "", value.strip())
    quoted = re.findall(r"[《「『“\"]([^》」』”\"]{4,36})[》」』”\"]", without_publisher)
    latin = re.findall(r"[a-zA-Z][a-zA-Z0-9]{3,}", without_publisher.casefold())
    return {
        normalized
        for item in [*quoted, *latin]
        if (normalized := _normalize_news_title(item)) and normalized not in NEWS_ANCHOR_STOPWORDS
    }


def _same_news_event(
    title: str,
    url: str,
    anchors: set[str],
    previous_title: str,
    previous_url: str,
    previous_anchors: set[str],
) -> bool:
    if url == previous_url or title == previous_title:
        return True
    if anchors & previous_anchors:
        return True
    return SequenceMatcher(None, title, previous_title).ratio() >= 0.72


def _dedupe_music_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: list[tuple[str, str, set[str]]] = []
    deduped: list[dict[str, Any]] = []
    for item in items:
        title = _normalize_news_title(str(item.get("title", "")))
        url = re.sub(r"/+$", "", str(item.get("url", ""))).strip().casefold()
        if not title and not url:
            continue
        anchors = _news_title_anchors(str(item.get("title", "")))
        if any(
            _same_news_event(title, url, anchors, previous_title, previous_url, previous_anchors)
            for previous_title, previous_url, previous_anchors in seen
        ):
            continue
        seen.append((title, url, anchors))
        deduped.append({**item, "story_key": sorted(anchors)[0] if anchors else title})
    return deduped

BLOCKED_MUSIC_NEWS_PUBLISHERS = ("新浪", "Sina", "sina.com.cn")
VIDEO_MUSIC_NEWS_HINTS = ("视频", "MV", "舞台", "演唱会", "现场", "直播", "短片", "首唱", "开唱", "综艺")
MUSIC_NEWS_QUERIES = (
    "华语乐坛 OR 华语音乐 when:3d",
    "华语新歌 OR 华语歌手 when:3d",
    "华语 MV OR 华语演唱会 OR 华语现场 when:3d",
    "华语音乐节 OR 华语专辑 OR 华语乐评 when:3d",
    "内地歌手 OR 台湾音乐 OR 香港音乐 when:3d",
)


def _safe_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = httpx.get(url, params=params, timeout=3.5, headers={"User-Agent": "C-Pop-Atlas/0.2"})
    response.raise_for_status()
    return response.json()



def _location_from_ipwho() -> dict[str, Any] | None:
    value = _safe_json("https://ipwho.is/")
    if value.get("success", True) and value.get("latitude") is not None:
        value["source"] = "ipwho.is"
        return value
    return None


def _location_from_ipapi() -> dict[str, Any] | None:
    value = _safe_json("https://ipapi.co/json/")
    if value.get("latitude") is None:
        return None
    return {
        "success": True, "latitude": value.get("latitude"), "longitude": value.get("longitude"),
        "city": value.get("city"), "region": value.get("region"), "country": value.get("country_name"),
        "source": "ipapi.co",
    }


def _location_from_ip_api() -> dict[str, Any] | None:
    value = _safe_json("http://ip-api.com/json/")
    if value.get("status") != "success" or value.get("lat") is None:
        return None
    return {
        "success": True, "latitude": value.get("lat"), "longitude": value.get("lon"),
        "city": value.get("city"), "region": value.get("regionName"), "country": value.get("country"),
        "source": "ip-api.com",
    }


def _ip_location() -> dict[str, Any]:
    providers = (_location_from_ipwho, _location_from_ipapi, _location_from_ip_api)
    executor = ThreadPoolExecutor(max_workers=len(providers))
    try:
        futures = [executor.submit(provider) for provider in providers]
        for future in as_completed(futures):
            try:
                value = future.result()
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                continue
            if value:
                return value
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return {
        "success": True,
        "latitude": os.getenv("WEATHER_LATITUDE", "31.2304"),
        "longitude": os.getenv("WEATHER_LONGITUDE", "121.4737"),
        "city": os.getenv("WEATHER_CITY", "上海"),
        "region": os.getenv("WEATHER_REGION", ""),
        "country": os.getenv("WEATHER_COUNTRY", "中国"),
        "source": "fallback-default-location",
    }

def get_weather() -> dict[str, Any]:
    now = time.time()
    if _weather_cache.value and _weather_cache.expires_at > now:
        return _weather_cache.value
    try:
        location = _ip_location()
        if not location.get("success", True):
            raise ValueError("IP location unavailable")
        latitude = float(location["latitude"])
        longitude = float(location["longitude"])
        weather = _safe_json(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": latitude, "longitude": longitude,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
        )
        current = weather.get("current", {})
        code = int(current.get("weather_code", -1))
        label, kind = WEATHER_CODES.get(code, ("天气变化中", "cloudy"))
        value = {
            "available": True,
            "city": location.get("city") or location.get("region") or "你所在的城市",
            "region": location.get("region"),
            "temperature": round(float(current.get("temperature_2m", 0))),
            "apparent_temperature": round(float(current.get("apparent_temperature", 0))),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "is_day": bool(current.get("is_day", 1)),
            "condition": label,
            "kind": kind,
            "music_moods": WEATHER_MOODS.get(kind, []),
            "source": f"Open-Meteo + {location.get('source', 'IP location')}",
        }
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        value = {
            "available": False, "city": "本地", "temperature": None, "apparent_temperature": None,
            "humidity": None, "wind_speed": None, "is_day": True, "condition": "天气服务暂不可用",
            "kind": "cloudy", "music_moods": ["reflective", "warm"], "source": "fallback",
        }
    _weather_cache.value, _weather_cache.expires_at = value, now + 1200
    return value


def _fetch_music_news_query(query_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    query = quote_plus(query_text)
    url = f"https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    try:
        response = httpx.get(url, timeout=4.5, headers={"User-Agent": "C-Pop-Atlas/0.2"})
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except (httpx.HTTPError, ET.ParseError, TypeError, ValueError):
        return items
    for item in root.findall("./channel/item")[:24]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = item.findtext("pubDate") or ""
        source = item.find("source")
        publisher = source.text.strip() if source is not None and source.text else "新闻来源"
        source_text = f"{title} {link} {publisher}"
        if any(blocked.casefold() in source_text.casefold() for blocked in BLOCKED_MUSIC_NEWS_PUBLISHERS):
            continue
        if title and link:
            parsed = email.utils.parsedate_to_datetime(published) if published else None
            content_type = "video" if any(hint.casefold() in source_text.casefold() for hint in VIDEO_MUSIC_NEWS_HINTS) else "text"
            items.append({
                "title": title,
                "url": link,
                "publisher": publisher,
                "published_at": parsed.isoformat() if parsed else None,
                "content_type": content_type,
            })
    return items


def get_music_news(limit: int = 10) -> list[dict[str, Any]]:
    now = time.time()
    if _news_cache.value and _news_cache.expires_at > now:
        return _news_cache.value[:limit]
    with ThreadPoolExecutor(max_workers=len(MUSIC_NEWS_QUERIES)) as executor:
        batches = executor.map(_fetch_music_news_query, MUSIC_NEWS_QUERIES)
        items = [item for batch in batches for item in batch]
    items = _dedupe_music_news(items)
    _news_cache.value, _news_cache.expires_at = items, now + 1200
    return items[:limit]



def get_computer_context() -> dict[str, Any]:
    hour = datetime.now().hour
    period = "late-night" if hour >= 22 or hour < 6 else "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    idle_seconds = None
    if platform.system() == "Windows":
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            idle_seconds = max(0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000)
    activity = "active" if idle_seconds is None or idle_seconds < 60 else "paused" if idle_seconds < 600 else "away"
    labels = {"active": "\u6b63\u5728\u4f7f\u7528\u7535\u8111", "paused": "\u77ed\u6682\u4f11\u606f", "away": "\u6682\u65f6\u79bb\u5f00"}
    return {"activity": activity, "label": labels[activity], "idle_seconds": round(idle_seconds) if idle_seconds is not None else None, "period": period}

def get_anniversaries(store: DataStore, today: date | None = None, limit: int = 4) -> list[dict[str, Any]]:
    today = today or date.today()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for release in store.releases.values():
        try:
            released = datetime.strptime(release.release_date[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        this_year = released.replace(year=today.year)
        distance = abs((this_year - today).days)
        distance = min(distance, abs(distance - 365))
        if distance <= 14:
            artist = store.get_artist(release.artist_id)
            candidates.append((distance, {
                "title": release.title, "artist": artist.name if artist else "华语音乐人",
                "release_date": released.isoformat(), "years": max(0, today.year - released.year), "distance_days": distance,
            }))
    return [item for _, item in sorted(candidates, key=lambda pair: pair[0])[:limit]]
