from __future__ import annotations

from html import unescape
import os
import re
from typing import Literal
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

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
USER_AGENT = "My-C-Pop-Working/0.5 web-search-tool (+https://github.com/yanhuachisha/my-cpop-working)"


def _clean_text(value: str, limit: int = 1200) -> str:
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", value, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _page_title(html: str, fallback: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if not match:
        return fallback
    return _clean_text(match.group(1), 120) or fallback


def _duckduckgo_url(raw_url: str) -> str:
    parsed = urlparse(unescape(raw_url))
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return unescape(raw_url)


def _dedupe_sources(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped = []
    seen_urls = set()
    for source in sources:
        url = source.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(source)
    return deduped


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


def web_search_workflow(
    query: str,
    song_title: str | None = None,
    artist: str | None = None,
    max_results: int = 5,
    client: httpx.Client | None = None,
) -> dict[str, object]:
    """Search the web, fetch top pages, and return grounded facts plus sources."""
    clean_query = query.strip()
    if not clean_query:
        clean_query = " ".join(part for part in (artist, song_title, "歌曲 故事 创作 背景") if part)
    limit = max(1, min(max_results, 8))
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(10.0, connect=4.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    should_close = client is None
    errors: list[str] = []
    search_results: list[dict[str, str]] = []
    documents: list[dict[str, str]] = []

    try:
        brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
        if brave_key:
            response = active_client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": clean_query, "count": limit, "safesearch": "moderate", "text_decorations": False},
                headers={"Accept": "application/json", "X-Subscription-Token": brave_key, "User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            for item in response.json().get("web", {}).get("results", [])[:limit]:
                url = str(item.get("url") or "").strip()
                title = _clean_text(str(item.get("title") or ""), 140)
                snippet = _clean_text(str(item.get("description") or ""), 280)
                if url and title:
                    search_results.append({"title": title, "url": url, "snippet": snippet, "source": "Brave Search"})
        else:
            response = active_client.get("https://duckduckgo.com/html/", params={"q": clean_query})
            response.raise_for_status()
            html = response.text
            pattern = re.compile(
                r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>[\s\S]{0,900}?'
                r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                flags=re.I,
            )
            for raw_url, raw_title, raw_snippet in pattern.findall(html)[:limit]:
                url = _duckduckgo_url(raw_url)
                title = _clean_text(raw_title, 140)
                snippet = _clean_text(raw_snippet, 280)
                if url and title:
                    search_results.append({"title": title, "url": url, "snippet": snippet, "source": "DuckDuckGo"})
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
        errors.append(f"web search: {type(error).__name__}")

    try:
        response = active_client.get(
            "https://zh.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": clean_query,
                "srlimit": min(3, limit),
                "format": "json",
                "origin": "*",
            },
        )
        response.raise_for_status()
        for item in response.json().get("query", {}).get("search", [])[:3]:
            page_title = str(item.get("title") or "").strip()
            snippet = _clean_text(str(item.get("snippet") or ""), 260)
            if page_title:
                search_results.append({
                    "title": page_title,
                    "url": f"https://zh.wikipedia.org/wiki/{quote_plus(page_title)}",
                    "snippet": snippet,
                    "source": "Wikipedia Search",
                })
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
        errors.append(f"wikipedia supplement: {type(error).__name__}")

    deduped_results = _dedupe_sources(search_results)[:limit]
    for result in deduped_results[: min(3, limit)]:
        try:
            response = active_client.get(result["url"])
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type and not response.text:
                continue
            text = _clean_text(response.text, 1600)
            if not text:
                continue
            documents.append({
                "title": _page_title(response.text, result["title"]),
                "url": result["url"],
                "snippet": result.get("snippet", ""),
                "text": text,
            })
        except (httpx.HTTPError, ValueError, TypeError) as error:
            errors.append(f"read page {result['url']}: {type(error).__name__}")

    facts = []
    for index, document in enumerate(documents, 1):
        snippet = document.get("snippet") or document["text"]
        facts.append(f"{index}. {document['title']}：{_clean_text(snippet, 360)}")
    if not facts:
        facts = [
            f"{index}. {item['title']}：{item.get('snippet') or item['url']}"
            for index, item in enumerate(deduped_results[:limit], 1)
        ]

    if should_close:
        active_client.close()

    sources = [
        {"name": item["title"], "url": item["url"], "license": item.get("source", "public web")}
        for item in deduped_results[:limit]
    ]
    return {
        "available": bool(deduped_results or documents),
        "query": clean_query,
        "song": song_title,
        "artist": artist,
        "results": deduped_results,
        "documents": documents,
        "facts": facts[:limit],
        "sources": sources,
        "answer_guidance": [
            "必须先基于 documents/facts 回答，不能把未检索到的传闻写成事实。",
            "如果只有搜索摘要没有正文，要明确说证据有限。",
            "先给一句结论，再分点写可核实线索，最后写听感或情绪理解。",
        ],
        "errors": errors,
    }


def research_song_public_impact_workflow(
    song_title: str | None,
    artist: str | None,
    question: str = "",
) -> dict[str, object]:
    """Collect public evidence for popularity, awards, circulation and cultural impact."""
    base = search_song_sources_workflow(song_title, artist)
    title = str(base["song"])
    artist_name = artist or ""
    facts = [str(item) for item in base["facts"]]
    sources = [dict(source) for source in base["sources"]]
    errors = [str(error) for error in base["errors"]]

    search_queries = [
        " ".join(part for part in (artist_name, title, "当年 有多火") if part),
        " ".join(part for part in (artist_name, title, "销量 奖项 榜单") if part),
        " ".join(part for part in (artist_name, title, "传唱度 影响力") if part),
        " ".join(part for part in (artist_name, title, "专辑 发行") if part),
    ]
    for query in search_queries[:3]:
        try:
            response = httpx.get(
                "https://zh.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 4,
                    "format": "json",
                    "origin": "*",
                },
                headers={"User-Agent": "My-C-Pop-Working/0.4 song-impact-workflow"},
                timeout=8.0,
            )
            response.raise_for_status()
            for item in response.json().get("query", {}).get("search", [])[:3]:
                snippet = re.sub(r"<[^>]+>|\s+", " ", str(item.get("snippet") or "")).strip()
                page_title = str(item.get("title") or "").strip()
                if not page_title or not snippet:
                    continue
                facts.append(f"维基百科搜索《{page_title}》：{snippet}")
                sources.append({
                    "name": f"维基百科搜索：{page_title}",
                    "url": f"https://zh.wikipedia.org/wiki/{quote_plus(page_title)}",
                    "license": "CC BY-SA",
                })
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            errors.append(f"Wikipedia search: {type(error).__name__}")

    try:
        response = httpx.get(
            "https://itunes.apple.com/search",
            params={
                "term": " ".join(part for part in (artist_name, title) if part),
                "country": "CN",
                "media": "music",
                "entity": "song",
                "limit": 5,
            },
            headers={"User-Agent": "My-C-Pop-Working/0.4 song-impact-workflow"},
            timeout=8.0,
        )
        response.raise_for_status()
        for item in response.json().get("results", [])[:3]:
            track = item.get("trackName")
            artist_value = item.get("artistName")
            if not track or not artist_value:
                continue
            facts.append(
                "iTunes Search："
                f"《{track}》- {artist_value}，专辑《{item.get('collectionName') or '未标注'}》，"
                f"发行时间 {str(item.get('releaseDate') or '未标注')[:10]}，"
                f"流派 {item.get('primaryGenreName') or '未标注'}。"
            )
            url = item.get("trackViewUrl") or item.get("collectionViewUrl")
            if url:
                sources.append({
                    "name": f"Apple Music：{track}",
                    "url": url,
                    "license": "Apple public catalog metadata",
                })
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
        errors.append(f"iTunes: {type(error).__name__}")

    deduped_sources = []
    seen_urls = set()
    for source in sources:
        url = source.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped_sources.append(source)

    return {
        "available": bool(facts),
        "song": title,
        "artist": artist,
        "question": question,
        "facts": facts[:12],
        "sources": deduped_sources[:8],
        "search_queries": search_queries,
        "answer_guidance": [
            "优先回答用户问的热度或影响力，不要只讲创作背景。",
            "把已核实事实、合理推断和听感判断分开。",
            "如果没有销量、榜单或奖项数字，明确说明没有查到可靠数字，不要编造。",
            "可以用年代传播、KTV/校园/电台/网络梗等文化线索解释传唱度，但要标注为推断。",
        ],
        "errors": errors,
    }
