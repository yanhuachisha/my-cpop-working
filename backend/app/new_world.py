from __future__ import annotations

import json
import os
import re
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import Lock
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx

CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "new_world_cache.json"
USER_AGENT = "C-Pop-Atlas/0.1 local-learning-dashboard"
LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")
_generation_lock = Lock()

AI_FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml", 4),
    ("Google", "https://blog.google/rss/", 3),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml", 2),
]

AI_TERMS = {
    "ai", "artificial intelligence", "model", "llm", "agent", "reasoning", "research",
    "gemini", "openai", "machine learning", "deep learning", "transformer", "robotics",
}

HOT_SOURCES = [
    ("Wikipedia", "维基百科今日热读", "查看中文维基百科最近一天浏览量最高的词条。", "https://pageviews.wmcloud.org/topviews/?project=zh.wikipedia.org&platform=all-access&date=latest&excludes="),
    ("CSDN", "CSDN 今日热榜", "浏览开发者社区当前最受关注的技术文章。", "https://blog.csdn.net/rank/list/total"),
    ("LINUX.DO", "LINUX.DO 今日热门", "查看社区最近一天讨论最集中的技术话题。", "https://linux.do/top?period=daily"),
    ("博客园", "博客园热门文章", "浏览博客园当前阅读量较高的开发文章。", "https://www.cnblogs.com/aggsite/topviews"),
    ("V2EX", "V2EX 今日热议", "看看程序员与独立开发者今天在讨论什么。", "https://www.v2ex.com/?tab=hot"),
    ("掘金", "掘金文章热榜", "聚合前端、后端、AI 与工程实践的热门内容。", "https://juejin.cn/hot/articles"),
    ("知乎", "知乎热榜", "快速观察今天更广泛的公共议题与知识讨论。", "https://www.zhihu.com/hot"),
    ("Hacker News", "Hacker News 热门", "追踪全球开发者、创业与计算机科学社区的重要讨论。", "https://news.ycombinator.com/"),
]

HISTORY_STORIES = [
    ("-44", "Julius Caesar and the Ides of March", "A political assassination changed Rome's path from republic toward empire.", "https://en.wikipedia.org/wiki/Assassination_of_Julius_Caesar"),
    ("105", "Cai Lun and papermaking", "The spread of practical papermaking reshaped administration, education, and memory.", "https://en.wikipedia.org/wiki/Cai_Lun"),
    ("618", "The Tang dynasty begins", "A dynasty opened an unusually connected age of trade, poetry, religion, and urban life.", "https://en.wikipedia.org/wiki/Tang_dynasty"),
    ("1215", "Magna Carta is sealed", "A failed peace agreement became a lasting symbol of limits on political power.", "https://en.wikipedia.org/wiki/Magna_Carta"),
    ("1271", "Kublai Khan founds the Yuan dynasty", "Mongol rule connected China with a vast Eurasian network of people and goods.", "https://en.wikipedia.org/wiki/Yuan_dynasty"),
    ("1453", "Constantinople falls", "The Ottoman capture ended the Byzantine Empire and redirected regional power and trade.", "https://en.wikipedia.org/wiki/Fall_of_Constantinople"),
    ("1492", "The Columbian exchange begins", "Plants, animals, diseases, and people crossed oceans with enormous human consequences.", "https://en.wikipedia.org/wiki/Columbian_exchange"),
    ("1517", "The Protestant Reformation", "A dispute over church practice transformed European religion, politics, and literacy.", "https://en.wikipedia.org/wiki/Reformation"),
    ("1600", "The East India Company is chartered", "A trading corporation grew into a political and military power across South Asia.", "https://en.wikipedia.org/wiki/East_India_Company"),
    ("1687", "Newton publishes Principia", "A mathematical framework united motion on Earth with motion in the heavens.", "https://en.wikipedia.org/wiki/Philosophi%C3%A6_Naturalis_Principia_Mathematica"),
    ("1760s", "The Industrial Revolution accelerates", "Mechanized production changed work, cities, energy use, and global inequality.", "https://en.wikipedia.org/wiki/Industrial_Revolution"),
    ("1776", "The American Declaration of Independence", "Its universal language coexisted with slavery and a long struggle over who counted.", "https://en.wikipedia.org/wiki/United_States_Declaration_of_Independence"),
    ("1789", "The French Revolution", "Monarchy, citizenship, violence, and rights were remade in a decade of upheaval.", "https://en.wikipedia.org/wiki/French_Revolution"),
    ("1804", "The Haitian Revolution succeeds", "Enslaved people defeated colonial armies and founded the first Black republic.", "https://en.wikipedia.org/wiki/Haitian_Revolution"),
    ("1868", "The Meiji Restoration", "Japan centralized power and industrialized rapidly while transforming social institutions.", "https://en.wikipedia.org/wiki/Meiji_Restoration"),
    ("1884", "The Berlin Conference", "European powers formalized rules for colonizing Africa without African representation.", "https://en.wikipedia.org/wiki/Berlin_Conference"),
    ("1911", "The Xinhai Revolution", "Revolution ended China's imperial system and began a difficult republican transition.", "https://en.wikipedia.org/wiki/1911_Revolution"),
    ("1914", "The First World War begins", "Alliance systems, nationalism, and industrial warfare produced catastrophe across continents.", "https://en.wikipedia.org/wiki/World_War_I"),
    ("1917", "The Russian Revolution", "War and social crisis brought the Bolsheviks to power and reshaped global politics.", "https://en.wikipedia.org/wiki/Russian_Revolution"),
    ("1930", "The Salt March", "Gandhi turned an everyday commodity into a mass challenge to British colonial rule.", "https://en.wikipedia.org/wiki/Salt_March"),
    ("1945", "The United Nations is founded", "States built a new institution for security, diplomacy, development, and human rights.", "https://en.wikipedia.org/wiki/United_Nations"),
    ("1947", "The partition of India", "Independence arrived with displacement, communal violence, and two new states.", "https://en.wikipedia.org/wiki/Partition_of_India"),
    ("1957", "Sputnik enters orbit", "A small satellite began the space age and intensified scientific competition.", "https://en.wikipedia.org/wiki/Sputnik_1"),
    ("1960", "The Year of Africa", "Seventeen African countries declared independence in a major wave of decolonization.", "https://en.wikipedia.org/wiki/Year_of_Africa"),
    ("1969", "Apollo 11 lands on the Moon", "A geopolitical competition produced an enduring achievement in engineering and exploration.", "https://en.wikipedia.org/wiki/Apollo_11"),
    ("1971", "The first email is sent", "A simple network experiment helped define communication for the internet age.", "https://en.wikipedia.org/wiki/History_of_email"),
    ("1989", "The Berlin Wall opens", "Peaceful pressure and political change fractured a symbol of Cold War division.", "https://en.wikipedia.org/wiki/Fall_of_the_Berlin_Wall"),
    ("1991", "The World Wide Web becomes public", "Open standards made the internet navigable through linked documents and browsers.", "https://en.wikipedia.org/wiki/History_of_the_World_Wide_Web"),
    ("1994", "South Africa's first multiracial election", "Apartheid formally gave way to democratic government under Nelson Mandela.", "https://en.wikipedia.org/wiki/1994_South_African_general_election"),
    ("2012", "CRISPR becomes a gene-editing tool", "A bacterial defense mechanism became a precise and controversial biotechnology platform.", "https://en.wikipedia.org/wiki/CRISPR_gene_editing"),
]

LEARNING_POINTS = [
    ("LLM", "Transformer attention", "Explain Q, K, V, masking, and why attention scales quadratically.", "https://arxiv.org/abs/1706.03762"),
    ("LLM", "Tokenization", "Compare BPE, WordPiece, and SentencePiece; explain token boundaries in Chinese.", "https://huggingface.co/docs/transformers/tokenizer_summary"),
    ("LLM", "Positional encoding", "Know sinusoidal encoding, RoPE, context length, and extrapolation limits.", "https://arxiv.org/abs/2104.09864"),
    ("LLM", "Pretraining objectives", "Contrast causal language modeling, masked modeling, and sequence-to-sequence learning.", "https://huggingface.co/docs/transformers/tasks/language_modeling"),
    ("LLM", "SFT, RLHF, and DPO", "Explain alignment pipeline, preference data, reward models, and DPO's objective.", "https://arxiv.org/abs/2305.18290"),
    ("LLM", "LoRA and PEFT", "Know low-rank adapters, trainable parameter count, merging, and deployment tradeoffs.", "https://arxiv.org/abs/2106.09685"),
    ("LLM", "RAG evaluation", "Separate retrieval recall, context relevance, faithfulness, and answer usefulness.", "https://arxiv.org/abs/2005.11401"),
    ("Python", "Asyncio concurrency", "Explain event loops, tasks, cancellation, timeouts, and when async does not help.", "https://docs.python.org/3/library/asyncio.html"),
    ("Python", "Generators and iterators", "Implement iterator protocol; explain yield, lazy evaluation, and memory behavior.", "https://docs.python.org/3/howto/functional.html#iterators"),
    ("Python", "Decorators and descriptors", "Understand function wrapping, property, class methods, and descriptor lookup.", "https://docs.python.org/3/howto/descriptor.html"),
    ("Python", "Type hints and Pydantic", "Use generics, protocols, validation models, and distinguish static from runtime checks.", "https://docs.python.org/3/library/typing.html"),
    ("Python", "GIL and multiprocessing", "Explain CPU-bound versus I/O-bound workloads and process communication costs.", "https://docs.python.org/3/library/multiprocessing.html"),
    ("Java", "JVM memory model", "Know heap, stacks, metaspace, visibility, ordering, and happens-before.", "https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html"),
    ("Java", "Concurrent collections", "Compare ConcurrentHashMap, CopyOnWriteArrayList, locks, and atomic variables.", "https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html"),
    ("Java", "Garbage collection", "Explain reachability, generations, pauses, throughput, and basic G1/ZGC tradeoffs.", "https://docs.oracle.com/en/java/javase/21/gctuning/"),
    ("Java", "Spring dependency injection", "Explain bean lifecycle, scopes, proxies, circular dependencies, and testability.", "https://docs.spring.io/spring-framework/reference/core/beans.html"),
    ("Java", "Transactions", "Know isolation levels, propagation, rollback behavior, and distributed transaction limits.", "https://docs.spring.io/spring-framework/reference/data-access/transaction.html"),
    ("Agent", "ReAct loop", "Describe thought-action-observation control, tool selection, stopping, and loop protection.", "https://arxiv.org/abs/2210.03629"),
    ("Agent", "Tool calling", "Design strict schemas, validation, retries, idempotency, and permission boundaries.", "https://python.langchain.com/docs/concepts/tool_calling/"),
    ("Agent", "Agent memory", "Separate working, episodic, semantic, and user-profile memory; define retention policy.", "https://langchain-ai.github.io/langgraph/concepts/memory/"),
    ("Agent", "Planning algorithms", "Compare plan-and-execute, ReAct, reflection, tree search, and task decomposition.", "https://arxiv.org/abs/2305.10601"),
    ("Agent", "Agent evaluation", "Measure task success, tool accuracy, trajectory quality, cost, latency, and safety.", "https://arxiv.org/abs/2308.03688"),
    ("Agent", "LangGraph state machines", "Model state, nodes, conditional edges, checkpoints, interrupts, and recovery.", "https://langchain-ai.github.io/langgraph/concepts/low_level/"),
    ("Interview", "Design an enterprise RAG system", "Cover ingestion, chunking, hybrid retrieval, reranking, ACLs, evaluation, and observability.", "https://arxiv.org/abs/2312.10997"),
    ("Interview", "Design a reliable coding agent", "Cover sandboxing, repository context, planning, patches, tests, rollback, and human approval.", "https://arxiv.org/abs/2405.15793"),
]


def _write_cache(payload: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CACHE_PATH)


def _cached(today: date) -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return payload if payload.get("date") == today.isoformat() and payload.get("hot_links") else None
    except (OSError, json.JSONDecodeError):
        return None


def _github_projects(client: httpx.Client, today: date) -> list[dict]:
    since = today - timedelta(days=45)
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = client.get(
        "https://api.github.com/search/repositories",
        params={
            "q": f"created:>={since.isoformat()} stars:>50",
            "sort": "stars",
            "order": "desc",
            "per_page": 24,
        },
        headers=headers,
    )
    response.raise_for_status()
    candidates = [
        {
            "name": item["full_name"],
            "description": item.get("description") or "No description yet.",
            "url": item["html_url"],
            "stars": item.get("stargazers_count", 0),
            "language": item.get("language"),
            "topics": item.get("topics", [])[:4],
            "created_at": item.get("created_at"),
        }
        for item in response.json().get("items", [])[:24]
    ]
    start = (today.toordinal() * 3) % max(1, len(candidates))
    return [candidates[(start + offset * 5) % len(candidates)] for offset in range(min(3, len(candidates)))]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node: ElementTree.Element, names: set[str]) -> str:
    for child in node.iter():
        if child is node:
            continue
        if _local_name(child.tag) in names and child.text:
            return re.sub(r"\s+", " ", child.text).strip()
    return ""


def _entry_link(node: ElementTree.Element) -> str:
    for child in node.iter():
        if _local_name(child.tag) != "link":
            continue
        if child.attrib.get("href"):
            return child.attrib["href"]
        if child.text:
            return child.text.strip()
    return ""


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None


def _parse_feed(content: bytes, source: str, weight: int) -> list[dict]:
    root = ElementTree.fromstring(content)
    entries = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    result = []
    for node in entries[:20]:
        title = _child_text(node, {"title"})
        url = _entry_link(node)
        if not title or not url:
            continue
        summary = _child_text(node, {"description", "summary", "content"})
        summary = re.sub(r"<[^>]+>", " ", summary)
        summary = re.sub(r"\s+", " ", summary).strip()[:240]
        published_raw = _child_text(node, {"pubdate", "published", "updated"})
        published = _parse_date(published_raw)
        keyword_score = sum(term in f"{title} {summary}".lower() for term in AI_TERMS)
        result.append({
            "title": title,
            "url": url,
            "source": source,
            "summary": summary,
            "published_at": published.isoformat() if published else published_raw,
            "score": weight * 10 + keyword_score,
            "published_sort": published.timestamp() if published else 0,
        })
    return result


def _ai_news(client: httpx.Client) -> list[dict]:
    candidates = []
    for source, url, weight in AI_FEEDS:
        try:
            response = client.get(url)
            response.raise_for_status()
            candidates.extend(_parse_feed(response.content, source, weight))
        except (httpx.HTTPError, ElementTree.ParseError):
            continue
    candidates.sort(key=lambda item: (item["score"], item["published_sort"]), reverse=True)
    selected = []
    source_counts: dict[str, int] = {}
    seen = set()
    today = datetime.now(LOCAL_TIMEZONE).date()
    if candidates:
        offset = today.toordinal() % len(candidates)
        candidates = candidates[offset:] + candidates[:offset]
    for item in candidates:
        key = re.sub(r"\W+", "", item["title"].lower())
        if key in seen or source_counts.get(item["source"], 0) >= 2:
            continue
        seen.add(key)
        source_counts[item["source"]] = source_counts.get(item["source"], 0) + 1
        selected.append({key: value for key, value in item.items() if key not in {"score", "published_sort"}})
        if len(selected) == 5:
            return selected
    return selected


def _localize_chinese(payload: dict) -> dict:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return payload
    targets = {
        "github": [
            {"index": index, "description": item["description"]}
            for index, item in enumerate(payload["github"])
        ],
        "ai_news": [
            {"index": index, "title": item["title"], "summary": item["summary"]}
            for index, item in enumerate(payload["ai_news"])
        ],
        "learning": [
            {"index": index, "category": item["category"], "title": item["title"], "focus": item["focus"]}
            for index, item in enumerate(payload["learning"])
        ],
    }
    try:
        response = httpx.post(
            f"{os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                "messages": [
                    {"role": "system", "content": "把 JSON 中所有英文展示文本翻译成自然、简洁、准确的简体中文。技术名词可保留英文。只返回结构完全相同的 JSON，不要解释。"},
                    {"role": "user", "content": json.dumps(targets, ensure_ascii=False)},
                ],
                "temperature": 0.1,
                "max_tokens": 5000,
            },
            timeout=50,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
        translated = json.loads(content)
        for section, fields in {
            "github": ("description",),
            "ai_news": ("title", "summary"),
            "learning": ("category", "title", "focus"),
        }.items():
            for item in translated.get(section, []):
                index = item.get("index")
                if not isinstance(index, int) or index >= len(payload[section]):
                    continue
                for field in fields:
                    if item.get(field):
                        payload[section][index][field] = item[field]
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return payload
    return payload


def _rotating(items: list[tuple], count: int, today: date) -> list[tuple]:
    start = today.toordinal() % len(items)
    return [items[(start + index) % len(items)] for index in range(count)]


def _hot_links(today: date) -> list[dict]:
    return [
        {"source": source, "title": title, "summary": summary, "url": url}
        for source, title, summary, url in _rotating(HOT_SOURCES, len(HOT_SOURCES), today)
    ]


def _learning(today: date) -> list[dict]:
    return [
        {"category": category, "title": title, "focus": focus, "url": url}
        for category, title, focus, url in _rotating(LEARNING_POINTS, 10, today)
    ]


def daily_new_world(force: bool = False) -> dict:
    today = datetime.now(LOCAL_TIMEZONE).date()
    if not force and (cached := _cached(today)):
        return cached
    with _generation_lock:
        if not force and (cached := _cached(today)):
            return cached
        with httpx.Client(timeout=14.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            try:
                github = _github_projects(client, today)
            except httpx.HTTPError:
                github = []
            news = _ai_news(client)
        payload = {
            "date": today.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "github": github,
            "ai_news": news,
            "hot_links": _hot_links(today),
            "learning": _learning(today),
            "sources": [
                {"name": "GitHub REST API", "url": "https://docs.github.com/en/rest/search/search"},
                {"name": "OpenAI News", "url": "https://openai.com/news/"},
                {"name": "Google Blog", "url": "https://blog.google/technology/ai/"},
                {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog"},
            ],
        }
        payload = _localize_chinese(payload)
        _write_cache(payload)
        return payload
