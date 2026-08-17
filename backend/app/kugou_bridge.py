from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx


DEFAULT_BRIDGE_URL = "http://127.0.0.1:9191"
REFERENCE_REPOSITORY = "https://github.com/Yu9191/KuGou"


def _base_url() -> str:
    value = os.getenv("KUGOU_BRIDGE_URL", DEFAULT_BRIDGE_URL).strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return DEFAULT_BRIDGE_URL
    if parsed.username or parsed.password:
        return DEFAULT_BRIDGE_URL
    return value


def _attribution() -> dict[str, str]:
    return {
        "name": "Yu9191/KuGou",
        "repository": REFERENCE_REPOSITORY,
        "license": "MIT",
        "role": "可选的第三方酷狗搜索元数据桥接服务",
    }


def bridge_status() -> dict[str, object]:
    base_url = _base_url()
    configured = bool(os.getenv("KUGOU_BRIDGE_URL", "").strip())
    try:
        response = httpx.get(f"{base_url}/health", timeout=2.5)
        response.raise_for_status()
        payload = response.json()
        available = bool(payload.get("status") == "ok" or payload.get("ok", True))
        message = "酷狗元数据桥已连接，可以搜索并补全歌单信息。"
    except (httpx.HTTPError, ValueError, TypeError):
        available = False
        message = "未检测到可选桥接服务；本地播放检测和文本导入不受影响。"
    return {
        "available": available,
        "configured": configured,
        "base_url": base_url,
        "capabilities": ["search-metadata"] if available else [],
        "blocked_capabilities": ["account-favorites", "audio-proxy", "full-lyrics"],
        "message": message,
        "attribution": _attribution(),
    }


def search_bridge(query: str, page: int = 1) -> dict[str, object]:
    base_url = _base_url()
    try:
        response = httpx.get(
            f"{base_url}/api/search",
            params={"keyword": query, "page": page},
            timeout=6.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as error:
        return {
            "ok": False,
            "query": query,
            "songs": [],
            "message": f"桥接服务暂不可用：{type(error).__name__}",
            "attribution": _attribution(),
        }

    songs = []
    if payload.get("ok"):
        for item in payload.get("songs", [])[:20]:
            songs.append({
                "title": str(item.get("fileName") or "").strip(),
                "artist": str(item.get("singerName") or "未知歌手").strip(),
                "album": str(item.get("albumName") or "").strip() or None,
                "hash": str(item.get("hash") or "").strip() or None,
                "duration_seconds": int(item.get("duration") or 0),
            })
    return {
        "ok": bool(payload.get("ok")),
        "query": query,
        "total": int(payload.get("total") or len(songs)),
        "songs": songs,
        "message": "仅返回歌名、歌手、专辑和时长，不代理音频或完整歌词。",
        "attribution": _attribution(),
    }
