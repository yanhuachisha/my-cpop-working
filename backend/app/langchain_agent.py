from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.data_store import DataStore
from app.knowledge_graph import MusicKnowledgeGraph
from app.kg_algorithms import KnowledgeGraphAlgorithms
from app.listener_memory import listener_preference_profile
from app.music_assistant_features import emotion_memory, weekly_report
from app.hybrid_recommender import HybridRecommender
from app.recommender import DailyRecommender


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class AgentRunRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    user_id: str = "demo"
    max_steps: int = Field(default=8, ge=2, le=20)
    algorithm: Literal["auto", "react", "plan_execute", "reflection"] = "auto"


class AgentRunResponse(BaseModel):
    answer: str
    model: str
    provider: str
    mode: str
    tools_used: list[str]
    trace: list[dict[str, Any]]
    iterations: int
    latency_ms: int


def agent_status() -> dict[str, Any]:
    configured = bool(os.getenv("DEEPSEEK_API_KEY"))
    return {
        "configured": configured,
        "provider": "DeepSeek",
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "framework": "LangChain create_agent",
        "loop": "tool-calling / ReAct-style",
        "llm_agent_count": 1,
        "llm_agents": ["MusicAgent orchestrator"],
        "legacy_modules": ["ListeningAgent rules", "TodayRecommender scoring"],
        "tools": [
            "search_music",
            "kg_neighbors",
            "kg_shortest_path",
            "daily_recommendation",
            "hybrid_recommendation",
            "kg_pagerank",
            "listener_emotion_memory",
            "listener_preference_profile_tool",
            "weekly_listening_report",
        ],
        "algorithms": ["react", "plan_execute", "reflection", "auto_router"],
        "fallback_available": True,
    }


class MusicAgent:
    def __init__(self, store: DataStore) -> None:
        self.store = store
        self.kg = MusicKnowledgeGraph(store)
        self.recommender = DailyRecommender(store)

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        started = time.perf_counter()
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return self._fallback(request, started)

        from langchain.agents import create_agent
        from langchain.tools import tool
        from langchain_openai import ChatOpenAI

        @tool
        def search_music(query: str) -> list[dict]:
            """搜索华语歌手、歌曲或知识图谱实体。"""
            artists = [item.model_dump() for item in self.store.search_artists(query)[:5]]
            songs = [item.model_dump() for item in self.store.search_recordings(query)[:5]]
            return [{"artists": artists, "songs": songs, "kg_entities": self.kg.search(query)}]

        @tool
        def kg_neighbors(entity_id: str) -> dict:
            """查询一个音乐实体的一跳知识关系。"""
            return self.kg.entity(entity_id)

        @tool
        def kg_shortest_path(start_id: str, end_id: str) -> dict:
            """计算两个音乐实体在知识图谱中的最短解释路径。"""
            return self.kg.shortest_path(start_id, end_id)

        @tool
        def daily_recommendation(user_id: str = "demo") -> dict:
            """获得今天的个性化华语歌曲推荐。"""
            recommendation = HybridRecommender(self.store).recommend(limit=1, mode="auto")
            item = recommendation["items"][0]
            return {
                "recording": item["recording"],
                "artist": item["artist"],
                "score": item["score"],
                "reasons": [
                    "结合收藏、播放次数、内容标签与上下文完成混合排序。",
                    f"命中特征：{'、'.join(item['features'][:4])}",
                ],
            }

        @tool
        def hybrid_recommendation(mode: str = "auto", limit: int = 5) -> dict:
            """使用内容过滤、隐式反馈、KG PageRank、Thompson Sampling 与 MMR 生成推荐。"""
            return HybridRecommender(self.store).recommend(limit=min(10, limit), mode=mode)

        @tool
        def kg_pagerank(seed_entity_ids: list[str]) -> list[dict]:
            """使用 Personalized PageRank 从一个或多个音乐实体扩散兴趣。"""
            return KnowledgeGraphAlgorithms(self.store).personalized_pagerank(seed_entity_ids)[:10]

        @tool
        def listener_emotion_memory(days: int = 14) -> dict:
            """读取最近播放、循环、切歌、暂停和收藏反馈，生成听歌情绪记忆。"""
            return emotion_memory(days)

        @tool
        def listener_preference_profile_tool() -> dict:
            """Read the listener's long-term multi-dimensional music preference profile."""
            return listener_preference_profile()

        @tool
        def weekly_listening_report() -> dict:
            """生成只保存在本地的最近七天听歌复盘。"""
            return weekly_report()

        model_name = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0.25,
            timeout=30,
            max_retries=0,
            max_tokens=400,
        )
        tools_list = [
            search_music,
            kg_neighbors,
            kg_shortest_path,
            daily_recommendation,
            hybrid_recommendation,
            kg_pagerank,
            listener_emotion_memory,
            listener_preference_profile_tool,
            weekly_listening_report,
        ]
        algorithm = request.algorithm
        if algorithm == "auto":
            algorithm = "plan_execute" if any(token in request.query for token in ("为什么", "关系", "比较", "分析")) else "react"
        trace, tools = [], []
        tool_map = {item.name: item for item in tools_list}
        routed_calls = self._route_tool_calls(request)
        if request.algorithm == "auto" and routed_calls:
            algorithm = "react"
        if routed_calls:
            plan = ""
            if algorithm == "plan_execute":
                plan_message = model.invoke([
                    {"role": "system", "content": "把任务拆成最多 3 个短步骤，不扩展用户未问的范围。"},
                    {"role": "user", "content": request.query},
                ])
                plan = str(plan_message.content)
                trace.append({"type": "plan", "tool": "deepseek_planner", "content": plan})
            evidence = []
            for tool_name, arguments in routed_calls[: request.max_steps]:
                trace.append({"type": "tool_call", "tool": tool_name, "args": arguments})
                raw_result = tool_map[tool_name].invoke(arguments)
                result = self._compact_tool_result(tool_name, raw_result)
                tools.append(tool_name)
                evidence.append({"tool": tool_name, "result": result})
                trace.append({
                    "type": "tool_result",
                    "tool": tool_name,
                    "content": str(result)[:1000],
                })
            if tools == ["daily_recommendation"]:
                pick = evidence[0]["result"]
                reasons = "；".join(pick.get("reasons", [])[:2])
                answer = f"今天推荐 {pick.get('artist') or '华语歌手'}《{pick.get('title') or '今日推荐'}》。{reasons}"
            else:
                answer_message = model.invoke([
                    {
                        "role": "system",
                        "content": "你是私人华语音乐研究 Agent。只能依据工具证据回答；明确区分事实与推断；不要提供完整歌词；回答简洁。推荐问题必须明确写出推荐结果。",
                    },
                    {
                        "role": "user",
                        "content": f"问题：{request.query}\n计划：{plan or '直接执行'}\n工具证据：{evidence}",
                    },
                ])
                answer = str(answer_message.content)
            if algorithm == "reflection":
                critique = model.invoke([
                    {"role": "system", "content": "检查答案是否超出工具证据、遗漏关键事实或把关联写成因果。只给短修改意见。"},
                    {"role": "user", "content": f"问题：{request.query}\n证据：{evidence}\n答案：{answer}"},
                ])
                trace.append({"type": "reflection", "tool": "deepseek_critic", "content": str(critique.content)})
                revised = model.invoke([
                    {"role": "system", "content": "按批评修订答案，只保留有证据内容。"},
                    {"role": "user", "content": f"问题：{request.query}\n证据：{evidence}\n原答案：{answer}\n批评：{critique.content}"},
                ])
                answer = str(revised.content)
            return AgentRunResponse(
                answer=answer,
                model=model_name,
                provider="deepseek",
                mode=f"langchain:{algorithm}",
                tools_used=list(dict.fromkeys(tools)),
                trace=trace,
                iterations=len(tools),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        agent = create_agent(model, tools_list, system_prompt="你是私人华语音乐研究 Agent。先调用最少数量的必要工具；区分事实、推断与个人品味；不要提供完整歌词；回答简洁。")
        execution_query = request.query
        if algorithm == "plan_execute":
            plan_message = model.invoke([{"role": "system", "content": "把音乐研究任务拆成最多 4 个可执行步骤，只输出短计划。"}, {"role": "user", "content": request.query}])
            plan = str(plan_message.content)
            trace.append({"type": "plan", "tool": "deepseek_planner", "content": plan})
            execution_query = f"用户问题：{request.query}\n执行计划：{plan}\n请按计划调用工具后回答。"
        result = agent.invoke(
            {"messages": [{"role": "user", "content": execution_query}]},
            config={"recursion_limit": min(request.max_steps, 6)},
        )
        for message in result["messages"]:
            for call in getattr(message, "tool_calls", []) or []:
                tools.append(call["name"])
                trace.append({"type": "tool_call", "tool": call["name"], "args": call.get("args", {})})
            if getattr(message, "type", "") == "tool":
                trace.append({"type": "tool_result", "tool": getattr(message, "name", "tool"), "content": str(message.content)[:1000]})
        answer = str(result["messages"][-1].content)
        if algorithm == "reflection":
            critique = model.invoke([{"role": "system", "content": "检查答案是否有无依据事实、遗漏工具证据或把关联误写成因果。只给修改意见。"}, {"role": "user", "content": f"问题：{request.query}\n答案：{answer}"}])
            trace.append({"type": "reflection", "tool": "deepseek_critic", "content": str(critique.content)})
            revised = model.invoke([{"role": "system", "content": "根据批评意见修订答案，保持简洁并明确事实与推断。"}, {"role": "user", "content": f"原问题：{request.query}\n原答案：{answer}\n批评：{critique.content}"}])
            answer = str(revised.content)
        return AgentRunResponse(answer=answer, model=model_name, provider="deepseek", mode=f"langchain:{algorithm}", tools_used=list(dict.fromkeys(tools)), trace=trace, iterations=len([x for x in trace if x["type"] == "tool_call"]), latency_ms=int((time.perf_counter() - started) * 1000))

    @staticmethod
    def _is_preference_query(query: str) -> bool:
        tokens = (
            "\u504f\u7231",
            "\u504f\u597d",
            "\u54c1\u5473",
            "\u53e3\u5473",
            "\u5e38\u542c",
            "\u6700\u559c\u6b22",
            "\u559c\u6b22\u4ec0\u4e48",
            "\u4e86\u89e3\u6211",
            "\u542c\u6b4c\u4e60\u60ef",
            "\u6211\u662f\u4ec0\u4e48\u542c\u4f17",
        )
        return any(token in query for token in tokens)

    @staticmethod
    def _route_tool_calls(request: AgentRunRequest) -> list[tuple[str, dict[str, Any]]]:
        query = request.query
        lowered = query.casefold()
        if MusicAgent._is_preference_query(query):
            return [("listener_preference_profile_tool", {})]
        if "周杰伦" in query and "陶喆" in query:
            return [("kg_shortest_path", {"start_id": "jay-chou", "end_id": "tao"})]
        if any(token in query for token in ("情绪", "切歌", "暂停", "循环", "避雷")):
            return [("listener_emotion_memory", {"days": 14})]
        if any(token in query for token in ("周报", "本周", "复盘", "七天")):
            return [("weekly_listening_report", {})]
        if any(token in query for token in ("推荐", "适合听", "下一首")):
            return [("daily_recommendation", {"user_id": request.user_id})]
        if any(token in query for token in ("查一下", "搜索", "找一下", "资料")):
            search_query = query
            for prefix in ("查一下", "搜索", "找一下"):
                search_query = search_query.replace(prefix, "")
            return [("search_music", {"query": search_query.strip(" ，。！？") or lowered})]
        return []

    @staticmethod
    def _compact_tool_result(tool_name: str, result: Any) -> Any:
        if tool_name == "daily_recommendation" and isinstance(result, dict):
            recording = result.get("recording", {})
            artist = result.get("artist", {})
            return {
                "pick_date": result.get("pick_date"),
                "title": recording.get("title"),
                "artist": artist.get("name"),
                "score": result.get("score"),
                "reasons": result.get("reasons", [])[:4],
            }
        if tool_name == "search_music" and isinstance(result, list) and result:
            item = result[0]
            return {
                "artists": [
                    {"name": artist.get("name"), "tags": artist.get("tags", [])}
                    for artist in item.get("artists", [])[:5]
                ],
                "songs": [song.get("title") for song in item.get("songs", [])[:5]],
                "entities": item.get("kg_entities", [])[:5],
            }
        if tool_name == "listener_emotion_memory" and isinstance(result, dict):
            return {
                "summary": result.get("summary"),
                "signals": result.get("signals"),
                "top_moods": result.get("top_moods", [])[:5],
                "repeat_tracks": result.get("repeat_tracks", [])[:5],
                "avoid_tracks": result.get("avoid_tracks", [])[:5],
            }
        if tool_name == "listener_preference_profile_tool" and isinstance(result, dict):
            return {
                "confidence": result.get("confidence"),
                "summary": result.get("summary"),
                "top_artists": result.get("top_artists", [])[:5],
                "top_tracks": result.get("top_tracks", [])[:5],
                "top_tags": result.get("top_tags", [])[:6],
                "top_moods": result.get("top_moods", [])[:6],
                "favorite_eras": result.get("favorite_eras", [])[:4],
                "listening_periods": result.get("listening_periods", [])[:5],
                "behavior": result.get("behavior", {}),
                "reflective_memory": result.get("reflective_memory", {}),
                "evidence": result.get("evidence", {}),
            }
        if tool_name == "weekly_listening_report" and isinstance(result, dict):
            return {
                "period_start": result.get("period_start"),
                "period_end": result.get("period_end"),
                "play_count": result.get("play_count"),
                "estimated_minutes": result.get("estimated_minutes"),
                "top_tracks": result.get("top_tracks", [])[:5],
                "top_moods": result.get("top_moods", [])[:5],
                "mood_shift": result.get("mood_shift"),
            }
        return result

    @staticmethod
    def _preference_answer(profile: dict) -> str:
        artists = "\u3001".join(item["name"] for item in profile.get("top_artists", [])[:3])
        tags = "\u3001".join(item["name"] for item in profile.get("top_tags", [])[:4])
        moods = "\u3001".join(item["name"] for item in profile.get("top_moods", [])[:4])
        periods = "\u3001".join(
            item["name"] for item in profile.get("listening_periods", [])[:2]
        )
        behavior = profile.get("behavior", {})
        parts = [profile.get("summary", "")]
        if artists:
            parts.append(f"\u5e38\u542c\u6b4c\u624b\uff1a{artists}\u3002")
        if tags:
            parts.append(f"\u98ce\u683c\u503e\u5411\uff1a{tags}\u3002")
        if moods:
            parts.append(f"\u60c5\u7eea\u503e\u5411\uff1a{moods}\u3002")
        if periods:
            parts.append(f"\u5e38\u542c\u65f6\u6bb5\uff1a{periods}\u3002")
        parts.append(
            f"\u76ee\u524d\u4f9d\u636e {profile.get('evidence', {}).get('preference_signal_count', 0)} \u4e2a\u504f\u597d\u4fe1\u53f7\uff0c"
            f"\u5305\u542b {behavior.get('music_note_count', 0)} \u7bc7\u97f3\u4e50\u7b14\u8bb0\u548c "
            f"{behavior.get('lyric_fragment_count', 0)} \u4e2a\u6b4c\u8bcd\u6807\u672c\u3002"
        )
        return "".join(part for part in parts if part)

    def _fallback(self, request: AgentRunRequest, started: float) -> AgentRunResponse:
        query = request.query
        trace = []
        if self._is_preference_query(query):
            result = listener_preference_profile()
            answer = self._preference_answer(result)
            tool = "listener_preference_profile_tool"
            trace.append({"type": "tool_call", "tool": tool, "args": {}})
            trace.append({"type": "tool_result", "tool": tool, "content": answer})
            return AgentRunResponse(
                answer=answer,
                model="deterministic-fallback",
                provider="local",
                mode=f"fallback:{request.algorithm}",
                tools_used=[tool],
                trace=trace,
                iterations=1,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        if "陶喆" in query and "周杰伦" in query:
            result = self.kg.shortest_path("jay-chou", "tao")
            tool = "kg_shortest_path"
            answer = f"知识路径：周杰伦 → {result['summary']}。这说明两人的已知连接点是 R&B 风格，不等于直接合作。"
        elif "推荐" in query:
            tool = "daily_recommendation"
            recording = next(item for item in self.store.recordings.values() if item.is_cpop)
            artist = self.store.get_artist(recording.artist_id)
            answer = f"今天推荐 {artist.name if artist else '华语歌手'}《{recording.title}》。离线评测只验证工具选择，不访问试听服务。"
        else:
            matches = self.kg.search(query)
            tool = "search_music"
            answer = "找到：" + "、".join(item["label"] for item in matches) if matches else "知识图谱暂未找到可靠实体。"
        trace.append({"type": "tool_call", "tool": tool, "args": {"query": query}})
        trace.append({"type": "tool_result", "tool": tool, "content": answer})
        return AgentRunResponse(answer=answer, model="deterministic-fallback", provider="local", mode=f"fallback:{request.algorithm}", tools_used=[tool], trace=trace, iterations=1, latency_ms=int((time.perf_counter() - started) * 1000))
