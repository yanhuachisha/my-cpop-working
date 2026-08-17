from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from openai import OpenAIError


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def generate_song_portrait(
    title: str,
    artist: str | None,
    album: str | None,
    year: int | None,
    search_material: Callable[[str, str | None, str | None, int | None], dict[str, Any]],
) -> dict[str, Any] | None:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    retrieved: dict[str, Any] = {}

    @tool
    def search_song_material(song_title: str, artist_name: str = "") -> dict[str, Any]:
        """检索当前歌曲可核实的歌手、专辑、年份、流派与来源，只返回找到的字段。"""
        material = search_material(song_title, artist_name or artist, album, year)
        retrieved.clear()
        retrieved.update(material)
        return material

    model = ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.55,
        timeout=24,
        max_retries=0,
        max_tokens=650,
    )
    system_prompt = (
        "你是歌曲情绪画像 Agent，不是百科编辑。第一步必须调用 search_song_material，且只调用一次。"
        "检索结果仅用于避免写错歌手、专辑和年份；正文重点是歌曲呈现的情绪矛盾、心理动作、画面与听感。"
        "subtitle 必须是 4 到 12 个中文字符的有感觉短句，像‘微笑底下的裂痕’，不能写歌名、歌手、年份、专辑或‘歌曲简介’。"
        "narrative 写 2 到 3 句、90 到 180 个中文字符，不用百科式开场，不罗列客观资料，不编造词曲作者、幕后故事或获奖。"
        "不要引用、补全或改写任何歌词原句，只描述听感、情绪与表达方式。"
        "资料没找到就直接省略，绝对不要写‘公开资料有限’‘此处不作展开’‘暂未找到’等免责声明。"
        "listening_points 必须是针对这首歌的 3 个具体聆听入口，themes 为 2 到 3 个短词。"
        "最终只输出 JSON：subtitle、narrative、themes、listening_points。"
    )
    request = {
        "song": title,
        "artist_hint": artist,
        "album_hint": album,
        "year_hint": year,
        "task": "先检索，再写一张有文学感但不过度编造的歌曲情绪画像。",
    }
    try:
        agent = create_agent(
            model,
            [search_song_material],
            system_prompt=system_prompt,
            middleware=[
                ToolCallLimitMiddleware(
                    tool_name="search_song_material",
                    run_limit=1,
                    exit_behavior="continue",
                )
            ],
        )
        result = agent.invoke(
            {"messages": [{"role": "user", "content": json.dumps(request, ensure_ascii=False)}]},
            config={"recursion_limit": 12},
        )
        tools_used = [
            call["name"]
            for message in result["messages"]
            for call in (getattr(message, "tool_calls", []) or [])
        ]
        if "search_song_material" not in tools_used:
            return None
        content = str(result["messages"][-1].content).strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
        parsed = json.loads(content)
        if not all(isinstance(parsed.get(key), expected) for key, expected in {
            "subtitle": str,
            "narrative": str,
            "themes": list,
            "listening_points": list,
        }.items()):
            return None
        return {
            **parsed,
            "verified": retrieved,
            "tools_used": list(dict.fromkeys(tools_used)),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, RuntimeError, OpenAIError):
        return None
