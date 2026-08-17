from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from app.data_store import DataStore
from app.listener_memory import (
    agent_session,
    create_agent_session,
    listener_preference_profile,
    save_agent_session_turn,
)
from app.music_assistant_features import emotion_memory, weekly_report
from app.hybrid_recommender import HybridRecommender


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_AGENT_CHECKPOINTER = InMemorySaver()
_HYDRATED_THREADS: set[str] = set()
_MEMORY_LOCK = Lock()


class AgentRunRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, max_length=80)
    user_id: str = "demo"
    max_steps: int = Field(default=8, ge=2, le=20)
    algorithm: Literal["auto", "react", "plan_execute", "reflection"] = "auto"
    recent_messages: list[dict[str, str]] = Field(default_factory=list, max_length=12)


class AgentSessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=60)


class AgentRunResponse(BaseModel):
    session_id: str
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
        "memory": {
            "short_term": "LangGraph InMemorySaver + thread_id",
            "durable_sessions": "data/listener_state.json",
            "long_term_profile": "listener preference profile",
        },
        "llm_agent_count": 3,
        "llm_agents": ["MusicAgent orchestrator", "ListeningCompanionAgent", "SongPortraitAgent"],
        "legacy_modules": ["ListeningAgent rules", "TodayRecommender scoring"],
        "tools": [
            "search_music",
            "daily_recommendation",
            "hybrid_recommendation",
            "listener_emotion_memory",
            "listener_preference_profile_tool",
            "weekly_listening_report",
            "search_song_material",
            "get_current_song_context",
            "save_lyric_specimen",
            "save_current_feeling",
            "find_similar_recordings",
            "analyze_lyric_excerpt",
            "search_song_story_web",
        ],
        "algorithms": ["react", "plan_execute", "reflection", "auto_router"],
        "fallback_available": True,
    }


class MusicAgent:
    def __init__(self, store: DataStore) -> None:
        self.store = store

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        started = time.perf_counter()
        session_id = request.session_id or create_agent_session()["id"]
        persisted_session = agent_session(session_id)
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return self._fallback(request, started, session_id)

        from langchain.agents import create_agent
        from langchain.agents.middleware import ToolCallLimitMiddleware
        from langchain.tools import tool
        from langchain_openai import ChatOpenAI

        @tool
        def search_music(query: str) -> list[dict]:
            """搜索本地华语曲库中的歌手和歌曲。"""
            artists = [item.model_dump() for item in self.store.search_artists(query)[:5]]
            songs = [item.model_dump() for item in self.store.search_recordings(query)[:5]]
            return [{"artists": artists, "songs": songs}]

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
            daily_recommendation,
            hybrid_recommendation,
            listener_emotion_memory,
            listener_preference_profile_tool,
            weekly_listening_report,
        ]
        trace, tools = [], []
        algorithm = request.algorithm
        if algorithm == "auto":
            algorithm = "plan_execute" if any(token in request.query for token in ("为什么", "关系", "比较", "分析")) else "react"
        agent = create_agent(
            model,
            tools_list,
            system_prompt=(
                "你是全能、偏理性的私人音乐助理，负责跨歌曲搜索、推荐决策、偏好分析、听歌数据复盘和音乐事实查询。"
                "你的回答应先给结论，再给数据依据、判断边界和可执行建议；清楚区分事实、算法结果与主观推断。"
                "不要模仿听歌房那种细腻陪伴口吻，不把普通问题过度情绪化。必须通过标准 Agent Loop 工作：先判断是否需要工具，"
                "需要时调用最少数量的工具，读取工具结果后再决定继续调用或回答。"
                "推荐、听歌记录、偏好和曲库事实查询不得凭空回答。"
                "通常只调用 1 到 2 个工具：询问偏好只读偏好画像；询问近期状态才读情绪记忆；"
                "只有用户明确要周报时才调用周报；单曲推荐和多曲推荐不得同时调用。"
                "不要提供完整歌词；不要展示内部思考过程；表达专业、清晰、克制。"
            ),
            middleware=[
                ToolCallLimitMiddleware(run_limit=3, exit_behavior="continue"),
                *[
                    ToolCallLimitMiddleware(tool_name=item.name, run_limit=1, exit_behavior="continue")
                    for item in tools_list
                ],
            ],
            checkpointer=_AGENT_CHECKPOINTER,
        )
        execution_query = request.query
        if algorithm == "plan_execute":
            plan_message = model.invoke([{"role": "system", "content": "把音乐研究任务拆成最多 4 个可执行步骤，只输出短计划。"}, {"role": "user", "content": request.query}])
            plan = str(plan_message.content)
            trace.append({"type": "plan", "tool": "deepseek_planner", "content": plan})
            execution_query = f"用户问题：{request.query}\n执行计划：{plan}\n请按计划调用工具后回答。"
        with _MEMORY_LOCK:
            should_hydrate = session_id not in _HYDRATED_THREADS
        persisted_messages = (persisted_session or {}).get("messages", [])
        history_source = persisted_messages[-20:] if persisted_messages else request.recent_messages[-12:]
        history = []
        if should_hydrate:
            history = [
                {"role": item.get("role"), "content": item.get("content")}
                for item in history_source
                if item.get("role") in {"user", "assistant"} and item.get("content")
            ]
        result = agent.invoke(
            {"messages": [*history, {"role": "user", "content": execution_query}]},
            config={
                "recursion_limit": min(64, max(12, request.max_steps * 3 + 4)),
                "configurable": {"thread_id": session_id},
            },
        )
        with _MEMORY_LOCK:
            _HYDRATED_THREADS.add(session_id)
        result_messages = result["messages"]
        turn_start = 0
        for index in range(len(result_messages) - 1, -1, -1):
            message = result_messages[index]
            if getattr(message, "type", "") == "human" and str(message.content) == execution_query:
                turn_start = index
                break
        for message in result_messages[turn_start:]:
            for call in getattr(message, "tool_calls", []) or []:
                tools.append(call["name"])
                trace.append({"type": "tool_call", "tool": call["name"], "args": call.get("args", {})})
            if getattr(message, "type", "") == "tool":
                trace.append({"type": "tool_result", "tool": getattr(message, "name", "tool"), "content": str(message.content)[:1000]})
        answer = str(result_messages[-1].content)
        if algorithm == "reflection":
            critique = model.invoke([{"role": "system", "content": "检查答案是否有无依据事实、遗漏工具证据或把关联误写成因果。只给修改意见。"}, {"role": "user", "content": f"问题：{request.query}\n答案：{answer}"}])
            trace.append({"type": "reflection", "tool": "deepseek_critic", "content": str(critique.content)})
            revised = model.invoke([{"role": "system", "content": "根据批评意见修订答案，保持简洁并明确事实与推断。"}, {"role": "user", "content": f"原问题：{request.query}\n原答案：{answer}\n批评：{critique.content}"}])
            answer = str(revised.content)
        unique_tools = list(dict.fromkeys(tools))
        save_agent_session_turn(
            session_id,
            request.query,
            answer,
            tools_used=unique_tools,
            model=model_name,
        )
        return AgentRunResponse(session_id=session_id, answer=answer, model=model_name, provider="deepseek", mode=f"langchain:{algorithm}", tools_used=unique_tools, trace=trace, iterations=len([x for x in trace if x["type"] == "tool_call"]), latency_ms=int((time.perf_counter() - started) * 1000))

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

    def _fallback(
        self,
        request: AgentRunRequest,
        started: float,
        session_id: str,
    ) -> AgentRunResponse:
        query = request.query
        trace = []
        if self._is_preference_query(query):
            result = listener_preference_profile()
            answer = self._preference_answer(result)
            tool = "listener_preference_profile_tool"
            trace.append({"type": "tool_call", "tool": tool, "args": {}})
            trace.append({"type": "tool_result", "tool": tool, "content": answer})
            save_agent_session_turn(
                session_id,
                request.query,
                answer,
                tools_used=[tool],
                model="deterministic-fallback",
            )
            return AgentRunResponse(
                session_id=session_id,
                answer=answer,
                model="deterministic-fallback",
                provider="local",
                mode=f"fallback:{request.algorithm}",
                tools_used=[tool],
                trace=trace,
                iterations=1,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        if "推荐" in query:
            tool = "daily_recommendation"
            recording = next(item for item in self.store.recordings.values() if item.is_cpop)
            artist = self.store.get_artist(recording.artist_id)
            answer = f"今天推荐 {artist.name if artist else '华语歌手'}《{recording.title}》。离线评测只验证工具选择，不访问试听服务。"
        else:
            tool = "search_music"
            search_query = query
            for prefix in ("查一下", "搜索", "找一下"):
                search_query = search_query.replace(prefix, "")
            artists = self.store.search_artists(search_query.strip(" ，。！？"))[:5]
            songs = self.store.search_recordings(search_query.strip(" ，。！？"))[:5]
            names = [item.name for item in artists] + [item.title for item in songs]
            answer = "本地曲库找到：" + "、".join(names) if names else "本地曲库暂未找到匹配内容。"
        trace.append({"type": "tool_call", "tool": tool, "args": {"query": query}})
        trace.append({"type": "tool_result", "tool": tool, "content": answer})
        save_agent_session_turn(
            session_id,
            request.query,
            answer,
            tools_used=[tool],
            model="deterministic-fallback",
        )
        return AgentRunResponse(session_id=session_id, answer=answer, model="deterministic-fallback", provider="local", mode=f"fallback:{request.algorithm}", tools_used=[tool], trace=trace, iterations=1, latency_ms=int((time.perf_counter() - started) * 1000))


def clear_agent_thread(session_id: str) -> None:
    with _MEMORY_LOCK:
        _HYDRATED_THREADS.discard(session_id)
    _AGENT_CHECKPOINTER.delete_thread(session_id)
