from __future__ import annotations

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Iterator, Literal

from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from app.data_store import DataStore
from app.listener_memory import (
    agent_session,
    create_agent_session,
    save_agent_session_turn,
)
from app.music_agent_workflows import (
    query_listener_memory_workflow,
    query_listening_history_workflow,
    recommend_music_workflow,
    search_local_music_workflow,
    search_music_workflow,
)


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_AGENT_CHECKPOINTER = InMemorySaver()
_HYDRATED_THREADS: set[str] = set()
_MEMORY_LOCK = Lock()
_INJECTED_TOOL_FAILURES: ContextVar[frozenset[str]] = ContextVar(
    "injected_tool_failures",
    default=frozenset(),
)


@contextmanager
def inject_tool_failures(tool_names: list[str]) -> Iterator[None]:
    token = _INJECTED_TOOL_FAILURES.set(frozenset(tool_names))
    try:
        yield
    finally:
        _INJECTED_TOOL_FAILURES.reset(token)


def _execute_tool(tool_name: str, callback) -> dict:
    if tool_name in _INJECTED_TOOL_FAILURES.get():
        return {
            "available": False,
            "tool": tool_name,
            "error": "The tool is temporarily unavailable. Do not fabricate results.",
            "evaluation_injected_failure": True,
        }
    return callback()


def _is_tool_failure(result: dict) -> bool:
    return bool(result.get("evaluation_injected_failure"))


def _tool_failure_answer(tool_name: str) -> str:
    return f"{tool_name} 暂时不可用，本次无法取得可靠结果；我不会编造数据，请稍后重试。"


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
            "recommend_music",
            "query_listener_memory",
            "query_listening_history",
            "search_song_material",
            "get_current_song_context",
            "save_listening_memory",
            "find_similar_recordings",
            "search_song_sources",
            "web_search",
            "research_song_public_impact",
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
        def search_music(query: str, limit: int = 8) -> dict:
            """联网查询公开音乐目录；每轮只调用一次，使用用户给出的核心歌曲或人物关键词。"""
            return _execute_tool(
                "search_music",
                lambda: search_music_workflow(self.store, query, limit),
            )

        @tool
        def recommend_music(
            limit: int = 1,
            mode: Literal["auto", "focus", "relax", "nostalgia", "lyrics"] = "auto",
        ) -> dict:
            """运行混合推荐；专注/工作/写代码传 focus，放松传 relax，怀旧传 nostalgia，歌词/细品传 lyrics，普通推荐传 auto。"""
            return _execute_tool(
                "recommend_music",
                lambda: recommend_music_workflow(self.store, limit, mode),
            )

        @tool
        def query_listener_memory(
            scope: Literal["recent", "long_term", "combined"] = "combined",
            days: int = 14,
        ) -> dict:
            """查询近期行为情绪、长期音乐偏好，或两者组合的用户音乐记忆。"""
            return _execute_tool(
                "query_listener_memory",
                lambda: query_listener_memory_workflow(scope, days),
            )

        @tool
        def query_listening_history(
            period: Literal[
                "today", "yesterday", "this_week", "last_week", "this_month",
                "last_month", "this_year", "last_year", "7d", "30d", "90d",
                "365d", "all", "custom"
            ] = "7d",
            start_date: str = "",
            end_date: str = "",
            group_by: Literal["day", "track", "artist"] = "day",
            view: Literal["list", "overview"] = "list",
            top_n: int = 10,
        ) -> dict:
            """查询真实听歌历史；overview 可一次返回趋势、歌曲歌手排行和上周期对比。"""
            return _execute_tool(
                "query_listening_history",
                lambda: query_listening_history_workflow(
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                    group_by=group_by,
                    view=view,
                    top_n=top_n,
                ),
            )

        model_name = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0,
            timeout=30,
            max_retries=0,
            max_tokens=400,
        )
        tools_list = [
            search_music,
            recommend_music,
            query_listener_memory,
            query_listening_history,
        ]
        trace, tools = [], []
        algorithm = request.algorithm
        if algorithm == "auto":
            algorithm = "plan_execute" if any(token in request.query for token in ("为什么", "关系", "比较", "分析")) else "react"
        agent = create_agent(
            model,
            tools_list,
            system_prompt=(
                "严格执行最小工具策略：普通推荐只调用 recommend_music；只有用户明确说按我的偏好或结合我的状态时，"
                "才先调用 query_listener_memory(scope=combined) 再调用 recommend_music。"
                "询问长期偏好或听众类型只调用 query_listener_memory(scope=long_term)；询问最近状态只调用一次 "
                "query_listener_memory(scope=recent, days=14)，不要额外查询长期记忆或听歌历史。"
                "只要用户没有明确提出推荐、想听或歌单，就绝对不要调用 recommend_music；音乐画像、口味和情绪问题只查记忆。"
                "听歌时长、排行、周期概览只调用 query_listening_history；除非用户明确要求分析偏好或情绪原因，"
                "否则不要调用 query_listener_memory。每种工具通常最多调用一次，已有结果后直接回答，不要换关键词重复搜索。"
                "多轮对话中，用户说那昨天、那上周、那今年等新时间范围时，只查询新范围，不能复用旧统计，也不要重复查询旧范围。"
                "如果历史消息已经给出用户偏好，用户说按这个偏好、按上述偏好或按刚才偏好推荐时直接调用 recommend_music，不要再次查询记忆。"
                "如果用户说不要参考偏好、不按偏好或直接推荐，同样只调用 recommend_music，不查询记忆。"
                "用户追问上一轮推荐中某一首适合什么场景、要求总结或改写时，直接依据会话回答，不调用搜索或其他工具。"
                "你是全能、偏理性的私人音乐助理，负责跨歌曲搜索、推荐决策、偏好分析、听歌数据复盘和音乐事实查询。"
                "你的回答应先给结论，再给数据依据、判断边界和可执行建议；清楚区分事实、算法结果与主观推断。"
                "不要模仿听歌房那种细腻陪伴口吻，不把普通问题过度情绪化。必须通过标准 Agent Loop 工作：先判断是否需要工具，"
                "需要时调用最少数量的工具，读取工具结果后再决定继续调用或回答。"
                "推荐、听歌记录、偏好和歌曲事实查询不得凭空回答。歌曲或歌手资料使用 search_music 联网查询；"
                "推荐统一使用 recommend_music，limit=1 表示单曲，limit>1 表示多曲。"
                "调用 recommend_music 时必须显式传 mode：专注、工作、学习或写代码使用 focus；放松使用 relax；"
                "怀旧使用 nostalgia；歌词、词作或细品使用 lyrics；没有场景要求才使用 auto。"
                "用户音乐记忆统一使用 query_listener_memory：近期状态用 scope=recent，长期偏好用 scope=long_term，"
                "需要综合判断时用 scope=combined。用户要求周报、月报或周期复盘时，只调用 "
                "query_listening_history 并设置 view=overview；只有明确要求结合情绪或偏好解释时才补充近期记忆。"
                "“本周、上周、本月、上月、今年、去年”必须分别使用 this_week、last_week、this_month、"
                "last_month、this_year、last_year，不要用滚动天数替代自然周期。"
                f"今天的本地日期是 {datetime.now().astimezone().date().isoformat()}。用户询问某天、最近一段时间、"
                "听歌时长、历史排行或歌手收听趋势时，必须调用 query_listening_history，不得依靠会话猜测。"
                "该工具每次都会返回区间总时长；同时询问总时长和歌曲排行时使用 group_by=track，"
                "同时询问总时长和歌手排行时使用 group_by=artist，避免重复查询。"
                "完整歌词、破解数据库等不允许的请求直接简短拒绝，不调用工具。回答中复述用户要求的时间范围。"
                "如果工具返回 unavailable 或 error，明确说明工具暂时不可用并建议稍后重试，不调用无关工具替代，也不编造结果。"
                "问候、感谢、能力说明、改写和普通闲聊不调用工具，直接简洁回答。"
                "不要提供完整歌词；不要展示内部思考过程；表达专业、清晰、克制。"
            ),
            middleware=[
                ToolCallLimitMiddleware(run_limit=3, exit_behavior="continue"),
                *[
                    ToolCallLimitMiddleware(
                        tool_name=item.name,
                        run_limit=2 if item.name == "query_listening_history" else 1,
                        exit_behavior="continue",
                    )
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
        routing_instruction = self._routing_instruction(request.query)
        if routing_instruction:
            execution_query += f"\n工具路由约束：{routing_instruction}"
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
        trace: list[dict[str, Any]] = []
        tools_used: list[str] = []

        def call_tool(tool: str, args: dict[str, Any], result: Any) -> None:
            tools_used.append(tool)
            trace.append({"type": "tool_call", "tool": tool, "args": args})
            trace.append({"type": "tool_result", "tool": tool, "content": str(result)[:1000]})

        if self._is_no_tool_query(query):
            answer = "我是你的音乐助理，可以帮助搜索歌曲、生成推荐、查询听歌历史和分析个人偏好。"
        elif self._is_private_kugou_query(query):
            answer = "\u6211\u4e0d\u7834\u89e3\u3001\u4e0d\u8bfb\u53d6\u3001\u4e0d\u4fee\u6539\u9177\u72d7\u79c1\u6709\u52a0\u5bc6\u6570\u636e\u5e93\u3002\u8fd9\u4e2a\u9879\u76ee\u53ea\u901a\u8fc7\u7a97\u53e3\u72b6\u6001\u3001\u7528\u6237\u5bfc\u5165\u6587\u672c\u6216\u53ef\u9009\u516c\u5f00\u6865\u63a5\u670d\u52a1\u5904\u7406\u5143\u6570\u636e\u3002"
        elif self._is_full_lyrics_query(query):
            answer = "\u4e0d\u80fd\u63d0\u4f9b\u5b8c\u6574\u6b4c\u8bcd\u3002\u53ef\u4ee5\u5e2e\u4f60\u67e5\u6b4c\u66f2\u8d44\u6599\u3001\u521b\u4f5c\u80cc\u666f\uff0c\u6216\u53ea\u5206\u6790\u4f60\u4e3b\u52a8\u63d0\u4f9b\u7684\u77ed\u53e5\u3002"
        elif self._is_combined_memory_query(query):
            args = {"scope": "combined", "days": 14}
            result = _execute_tool(
                "query_listener_memory",
                lambda: query_listener_memory_workflow(**args),
            )
            call_tool("query_listener_memory", args, result)
            answer = _tool_failure_answer("query_listener_memory") if _is_tool_failure(result) else "\u5df2\u7efc\u5408\u957f\u671f\u504f\u597d\u548c\u8fd1\u671f\u72b6\u6001\u751f\u6210\u97f3\u4e50\u753b\u50cf\u3002"
        elif self._is_recent_memory_query(query):
            args = {"scope": "recent", "days": 14}
            result = _execute_tool(
                "query_listener_memory",
                lambda: query_listener_memory_workflow(**args),
            )
            call_tool("query_listener_memory", args, result)
            answer = _tool_failure_answer("query_listener_memory") if _is_tool_failure(result) else "\u6700\u8fd1\u4e24\u5468\u7684\u542c\u6b4c\u72b6\u6001\u5df2\u6309\u8fd1\u671f\u884c\u4e3a\u8bb0\u5fc6\u6c47\u603b\uff0c\u53ef\u7ed3\u5408\u60c5\u7eea\u3001\u7b14\u8bb0\u548c\u64ad\u653e\u4fe1\u53f7\u7ee7\u7eed\u5206\u6790\u3002"
        elif self._is_history_query(query):
            args = self._history_args(query)
            result = _execute_tool(
                "query_listening_history",
                lambda: query_listening_history_workflow(**args),
            )
            call_tool("query_listening_history", args, result)
            answer = _tool_failure_answer("query_listening_history") if _is_tool_failure(result) else self._history_answer(args, result)
        elif self._needs_memory_and_recommendation(query):
            memory_args = {"scope": "combined", "days": 14}
            memory = _execute_tool(
                "query_listener_memory",
                lambda: query_listener_memory_workflow(**memory_args),
            )
            call_tool("query_listener_memory", memory_args, memory)
            rec_args = self._recommend_args(query)
            rec = _execute_tool(
                "recommend_music",
                lambda: recommend_music_workflow(self.store, **rec_args),
            )
            call_tool("recommend_music", rec_args, rec)
            failed_tool = "query_listener_memory" if _is_tool_failure(memory) else "recommend_music" if _is_tool_failure(rec) else ""
            answer = _tool_failure_answer(failed_tool) if failed_tool else self._recommend_answer(rec, prefix="\u7ed3\u5408\u4f60\u7684\u504f\u597d\uff0c\u63a8\u8350")
        elif self._is_recommend_without_memory(query):
            args = self._recommend_args(query)
            result = _execute_tool(
                "recommend_music",
                lambda: recommend_music_workflow(self.store, **args),
            )
            call_tool("recommend_music", args, result)
            answer = _tool_failure_answer("recommend_music") if _is_tool_failure(result) else self._recommend_answer(result)
        elif self._is_preference_query(query) or "\u542c\u4f17" in query:
            scope = "recent" if any(token in query for token in ("\u6700\u8fd1", "\u4e24\u5468", "\u60c5\u7eea", "\u72b6\u6001")) else "long_term"
            args = {"scope": scope, "days": 14}
            result = _execute_tool(
                "query_listener_memory",
                lambda: query_listener_memory_workflow(**args),
            )
            call_tool("query_listener_memory", args, result)
            if _is_tool_failure(result):
                answer = _tool_failure_answer("query_listener_memory")
            elif scope == "long_term":
                answer = self._preference_answer(result.get("long_term", result))
                if "\u542c\u4f17" in query and "\u542c\u4f17" not in answer:
                    answer += "\u6574\u4f53\u770b\uff0c\u4f60\u662f\u4e00\u4e2a\u504f\u79c1\u4eba\u5316\u3001\u91cd\u65cb\u5f8b\u548c\u60c5\u7eea\u8bb0\u5fc6\u7684\u542c\u4f17\u3002"
            else:
                answer = "\u6700\u8fd1\u4e24\u5468\u7684\u542c\u6b4c\u72b6\u6001\u5df2\u6309\u8fd1\u671f\u884c\u4e3a\u8bb0\u5fc6\u6c47\u603b\uff0c\u53ef\u7ed3\u5408\u60c5\u7eea\u3001\u7b14\u8bb0\u548c\u64ad\u653e\u4fe1\u53f7\u7ee7\u7eed\u5206\u6790\u3002"
        elif self._is_recommend_query(query):
            args = self._recommend_args(query)
            result = _execute_tool(
                "recommend_music",
                lambda: recommend_music_workflow(self.store, **args),
            )
            call_tool("recommend_music", args, result)
            answer = _tool_failure_answer("recommend_music") if _is_tool_failure(result) else self._recommend_answer(result)
        else:
            args = {"query": self._clean_search_query(query), "limit": 8}
            result = _execute_tool(
                "search_music",
                lambda: search_local_music_workflow(self.store, **args),
            )
            call_tool("search_music", args, result)
            answer = _tool_failure_answer("search_music") if _is_tool_failure(result) else self._search_answer(query, result)

        save_agent_session_turn(
            session_id,
            request.query,
            answer,
            tools_used=list(dict.fromkeys(tools_used)),
            model="deterministic-fallback",
        )
        return AgentRunResponse(
            session_id=session_id,
            answer=answer,
            model="deterministic-fallback",
            provider="local",
            mode=f"fallback:{request.algorithm}",
            tools_used=list(dict.fromkeys(tools_used)),
            trace=trace,
            iterations=len([item for item in trace if item["type"] == "tool_call"]),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def _is_recommend_query(query: str) -> bool:
        return any(token in query for token in ("\u63a8\u8350", "\u6b4c\u5355", "\u9002\u5408", "\u60f3\u542c"))

    @staticmethod
    def _needs_memory_and_recommendation(query: str) -> bool:
        return MusicAgent._is_recommend_query(query) and any(
            token in query for token in ("\u6211\u7684\u504f\u597d", "\u957f\u671f\u504f\u597d", "\u6700\u8fd1\u72b6\u6001", "\u7ed3\u5408\u6211", "\u6309\u6211\u7684\u504f\u597d")
        )

    @staticmethod
    def _is_recommend_without_memory(query: str) -> bool:
        return MusicAgent._is_recommend_query(query) and any(
            token in query for token in ("\u4e0d\u8981\u53c2\u8003\u504f\u597d", "\u4e0d\u53c2\u8003\u504f\u597d", "\u4e0d\u6309\u504f\u597d", "\u76f4\u63a5\u63a8\u8350")
        )

    @staticmethod
    def _is_recent_memory_query(query: str) -> bool:
        return not MusicAgent._is_recommend_query(query) and any(token in query for token in ("\u6700\u8fd1", "\u8fd1\u671f", "\u4e24\u5468", "14\u5929")) and any(
            token in query for token in ("\u60c5\u7eea", "\u72b6\u6001", "\u53d8\u5316", "\u884c\u4e3a", "\u4fe1\u53f7", "\u504f\u597d\u4fe1\u53f7")
        )

    @staticmethod
    def _is_combined_memory_query(query: str) -> bool:
        return not MusicAgent._is_recommend_query(query) and any(
            token in query for token in ("\u7efc\u5408", "\u7ed3\u5408", "\u653e\u5728\u4e00\u8d77")
        ) and any(token in query for token in ("\u957f\u671f", "\u53e3\u5473", "\u504f\u597d")) and any(
            token in query for token in ("\u6700\u8fd1", "\u8fd1\u671f", "\u72b6\u6001", "\u60c5\u7eea")
        )

    @staticmethod
    def _is_history_query(query: str) -> bool:
        history_tokens = ("\u542c\u6b4c", "\u542c\u4e86\u591a\u4e45", "\u65f6\u957f", "\u6392\u884c", "\u5468\u62a5", "\u6708\u62a5", "\u590d\u76d8", "\u603b\u5171", "\u5e38\u542c")
        period_tokens = ("\u4eca\u5929", "\u6628\u65e5", "\u6628\u5929", "\u672c\u5468", "\u4e0a\u5468", "\u672c\u6708", "\u4e0a\u6708", "\u4eca\u5e74", "\u53bb\u5e74", "\u6700\u8fd1")
        return any(token in query for token in history_tokens) and any(token in query for token in period_tokens)

    @staticmethod
    def _is_full_lyrics_query(query: str) -> bool:
        return "\u5b8c\u6574\u6b4c\u8bcd" in query or ("\u6b4c\u8bcd" in query and any(token in query for token in ("\u5168\u6587", "\u5168\u7ed9", "\u5168\u90e8")))

    @staticmethod
    def _is_private_kugou_query(query: str) -> bool:
        return "\u9177\u72d7" in query and any(token in query for token in ("\u7834\u89e3", "\u6570\u636e\u5e93", "\u52a0\u5bc6", "\u76f4\u63a5\u8bfb"))

    @staticmethod
    def _is_no_tool_query(query: str) -> bool:
        normalized = query.strip().casefold()
        return any(
            token in normalized
            for token in (
                "你好",
                "谢谢",
                "感谢",
                "你是谁",
                "你能做什么",
                "有什么功能",
                "帮助",
                "help",
            )
        )

    @staticmethod
    def _routing_instruction(query: str) -> str:
        if MusicAgent._is_recommend_query(query) and any(token in query for token in ("\u8fd9\u4e2a\u504f\u597d", "\u4e0a\u8ff0\u504f\u597d", "\u521a\u624d\u7684\u504f\u597d")):
            return "\u53ea\u8c03\u7528 recommend_music\uff0c\u4e0d\u8981\u91cd\u65b0\u67e5\u8be2\u8bb0\u5fc6\u3002"
        if MusicAgent._is_recommend_without_memory(query):
            return "\u53ea\u8c03\u7528 recommend_music\uff0c\u4e0d\u8981\u67e5\u8be2\u8bb0\u5fc6\u3002"
        if MusicAgent._is_combined_memory_query(query):
            return "\u53ea\u8c03\u7528 query_listener_memory\uff0cscope=combined\u3002"
        if MusicAgent._is_recent_memory_query(query):
            return "只调用 query_listener_memory，scope=recent，days=14；不要调用听歌历史。"
        if MusicAgent._needs_memory_and_recommendation(query):
            return "依次调用 query_listener_memory(scope=combined) 和 recommend_music。"
        if MusicAgent._is_preference_query(query) or "听众" in query:
            return "只调用 query_listener_memory，scope=long_term。"
        if MusicAgent._is_history_query(query):
            return "只调用 query_listening_history，不要调用用户记忆。"
        if MusicAgent._is_recommend_query(query):
            return "只调用 recommend_music，并根据场景显式传入 mode。"
        return ""

    @staticmethod
    def _recommend_args(query: str) -> dict[str, Any]:
        limit = 3 if any(token in query for token in ("\u4e09\u9996", "3\u9996", "\u51e0\u9996")) else 1
        mode = "auto"
        if "\u4e13\u6ce8" in query or "\u5199\u4ee3\u7801" in query or "\u5de5\u4f5c" in query:
            mode = "focus"
        elif "\u653e\u677e" in query:
            mode = "relax"
        elif "\u6000\u65e7" in query:
            mode = "nostalgia"
        elif "\u6b4c\u8bcd" in query or "\u7ec6\u54c1" in query:
            mode = "lyrics"
        return {"limit": limit, "mode": mode}

    @staticmethod
    def _history_args(query: str) -> dict[str, Any]:
        period = "7d"
        if "\u4eca\u5929" in query:
            period = "today"
        elif "\u6628\u5929" in query or "\u6628\u65e5" in query:
            period = "yesterday"
        elif "\u6700\u8fd130\u5929" in query or "\u8fd130\u5929" in query:
            period = "30d"
        elif "\u672c\u5468" in query or "\u5468\u62a5" in query:
            period = "this_week"
        elif "\u4e0a\u5468" in query:
            period = "last_week"
        elif "\u672c\u6708" in query or "\u6708\u62a5" in query:
            period = "this_month"
        elif "\u4e0a\u6708" in query:
            period = "last_month"
        elif "\u4eca\u5e74" in query:
            period = "this_year"
        elif "\u53bb\u5e74" in query:
            period = "last_year"

        group_by = "day"
        if "\u6b4c\u624b" in query:
            group_by = "artist"
        elif "\u6b4c\u66f2" in query or "\u6b4c\u6392\u884c" in query or "\u6392\u884c" in query:
            group_by = "track"

        view = "overview" if any(token in query for token in ("\u603b\u7ed3", "\u6982\u89c8", "\u590d\u76d8", "\u5468\u62a5", "\u6708\u62a5")) else "list"
        return {"period": period, "start_date": "", "end_date": "", "group_by": group_by, "view": view, "top_n": 10}

    @staticmethod
    def _clean_search_query(query: str) -> str:
        cleaned = query
        for prefix in ("\u67e5\u4e00\u4e0b", "\u67e5\u4e00\u67e5", "\u641c\u7d22", "\u627e\u4e00\u9996", "\u627e\u4e00\u4e2a", "\u628a", "\u7ed9\u6211"):
            cleaned = cleaned.replace(prefix, "")
        for suffix in ("\u76f8\u5173\u7684\u97f3\u4e50\u8d44\u6599", "\u8fd9\u9996\u6b4c", "\u7684\u5b8c\u6574\u6b4c\u8bcd", "\u5b8c\u6574\u6b4c\u8bcd", "\u8d44\u6599"):
            cleaned = cleaned.replace(suffix, "")
        return cleaned.strip(" \uff0c\u3002\uff01\uff1f?") or query

    @staticmethod
    def _recommend_answer(result: dict[str, Any], prefix: str = "\u63a8\u8350") -> str:
        items = result.get("items", [])
        names = []
        for item in items[:3]:
            recording = item.get("recording", {})
            artist = item.get("artist") or {}
            title = recording.get("title", "\u4e00\u9996\u534e\u8bed\u6b4c")
            artist_name = artist.get("name", "\u534e\u8bed\u6b4c\u624b")
            names.append(f"{artist_name}\u300a{title}\u300b")
        suffix = "\u3001".join(names) if names else "\u4e00\u9996\u534e\u8bed\u6b4c"
        return f"{prefix}\uff1a{suffix}\u3002\u8fd9\u662f\u79bb\u7ebf\u8bc4\u6d4b\u53ef\u590d\u73b0\u7684\u6df7\u5408\u63a8\u8350\u7ed3\u679c\uff0c\u7ebf\u4e0a\u6a21\u5f0f\u4f1a\u7ee7\u7eed\u7ed3\u5408 Agent \u5de5\u5177\u7ed3\u679c\u7ec4\u7ec7\u89e3\u91ca\u3002"

    @staticmethod
    def _search_answer(query: str, result: dict[str, Any]) -> str:
        local_artists = result.get("local_artists", [])
        local_songs = result.get("local_songs", [])
        online = result.get("results", [])
        names = []
        for item in online[:3]:
            names.append(item.get("title") or item.get("artist") or item.get("name") or "")
        for item in local_artists[:3]:
            names.append(item.get("name", ""))
        for item in local_songs[:3]:
            names.append(item.get("title", ""))
        compact = "\u3001".join(name for name in names if name)
        if compact:
            return f"\u5df2\u641c\u7d22 {query}\uff0c\u627e\u5230\uff1a{compact}\u3002"
        return f"\u5df2\u641c\u7d22 {query}\uff0c\u672c\u5730\u548c\u516c\u5f00\u76ee\u5f55\u6682\u672a\u627e\u5230\u7a33\u5b9a\u5339\u914d\u3002"

    @staticmethod
    def _history_answer(args: dict[str, Any], result: dict[str, Any]) -> str:
        total = result.get("total_seconds") or result.get("summary", {}).get("total_seconds", 0)
        minutes = round(float(total or 0) / 60, 1)
        period_label = {
            "today": "\u4eca\u5929",
            "yesterday": "\u6628\u5929",
            "this_week": "\u672c\u5468",
            "last_week": "\u4e0a\u5468",
            "this_month": "\u672c\u6708",
            "last_month": "\u4e0a\u6708",
            "this_year": "\u4eca\u5e74",
            "last_year": "\u53bb\u5e74",
            "30d": "\u6700\u8fd130\u5929",
        }.get(args["period"], "\u8fd9\u6bb5\u65f6\u95f4")
        noun = "\u6b4c\u624b" if args["group_by"] == "artist" else "\u6b4c\u66f2" if args["group_by"] == "track" else "\u542c\u6b4c"
        return f"{period_label}\u542c\u6b4c\u7edf\u8ba1\u5df2\u67e5\u8be2\uff1a\u603b\u65f6\u957f\u7ea6 {minutes} \u5206\u949f\uff0c\u5f53\u524d\u6309{noun}\u7ef4\u5ea6\u8fd4\u56de\u6392\u884c\u4e0e\u660e\u7ec6\u3002"


def clear_agent_thread(session_id: str) -> None:
    with _MEMORY_LOCK:
        _HYDRATED_THREADS.discard(session_id)
    _AGENT_CHECKPOINTER.delete_thread(session_id)
