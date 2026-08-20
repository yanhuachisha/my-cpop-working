from __future__ import annotations

import json
import os
import re
import time
from typing import Literal

import httpx
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.data_store import DataStore
from app.kugou import get_now_playing
from app.listener_memory import (
    listening_conversation,
    load_state,
    save_listening_conversation_turn,
)
from app.listening_companion_workflows import (
    find_similar_recordings_workflow,
    get_current_song_context_workflow,
    research_song_public_impact_workflow,
    save_listening_memory_workflow,
    search_song_sources_workflow,
    web_search_workflow,
)
from app.listening_preferences import (
    CORE_LISTENING_COMPANION_PROMPT,
    build_listening_companion_prompt,
    get_listening_companion_core_prompt,
    get_listening_companion_prompt,
    save_listening_companion_core_prompt,
    save_listening_companion_prompt,
)
from app.models import SourceRef
from app.recommender import DailyRecommender
from app.song_introduction import cached_song_introduction, retain_current_song_cache, song_introduction
from app.sources import OPEN_DATA_SOURCES, SEED_SOURCE


class LyricAnalysisRequest(BaseModel):
    excerpt: str = Field(min_length=1, max_length=500)
    song_title: str | None = None
    artist: str | None = None


class LyricAnalysis(BaseModel):
    summary: str
    imagery: list[str]
    emotion: list[str]
    craft: list[str]
    listening_questions: list[str]
    copyright_note: str


class ListeningChatTurn(BaseModel):
    role: Literal["agent", "user"]
    content: str = Field(min_length=1, max_length=1000)


class ListeningChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    song_title: str | None = None
    artist: str | None = None
    lyric_excerpt: str | None = Field(default=None, max_length=500)
    recent_messages: list[ListeningChatTurn] = Field(default_factory=list, max_length=8)
    client_message_id: str | None = Field(default=None, max_length=80)


class ListeningStoryRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    artist: str | None = Field(default=None, max_length=120)
    album: str | None = Field(default=None, max_length=200)
    year: int | None = Field(default=None, ge=1900, le=2100)


class ListeningChatResponse(BaseModel):
    answer: str
    tools_used: list[str]
    suggestions: list[str]
    sources: list[SourceRef]
    mode: str = "fallback"
    trace: list[dict] = Field(default_factory=list)
    iterations: int = 0
    latency_ms: int = 0


class ListeningPromptUpdate(BaseModel):
    core_prompt: str | None = Field(default=None, max_length=6000)
    custom_prompt: str = Field(default="", max_length=2000)


class ListeningPromptSettings(BaseModel):
    default_core_prompt: str
    core_prompt: str
    custom_prompt: str
    effective_prompt: str
    editable_scope: str


class TrackState(BaseModel):
    status: Literal["live", "idle"]
    available: bool
    recording_id: str | None = None
    like_count: int = 0
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    year: int | None = None
    raw_title: str | None = None
    source: str


class SongStory(BaseModel):
    title: str
    subtitle: str
    narrative: str
    themes: list[str]
    listening_points: list[str]
    story_type: str
    facts: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)


class ListenerProfile(BaseModel):
    favorite_artist: str
    listener_type: str
    preferences: list[str]


class ListeningContextResponse(BaseModel):
    current: TrackState
    story: SongStory | None = None
    quick_prompts: list[str]
    profile: ListenerProfile
    sources: list[SourceRef]


SONG_GUIDES = {
    "七里香": {
        "recording_id": "jay-chou-qilixiang-song",
        "artist": "周杰伦",
        "album": "七里香",
        "year": 2004,
        "subtitle": "夏日气味、青春记忆与克制的浪漫",
        "narrative": "这首歌适合从“感官记忆”进入：风、雨、植物与季节把爱情写成可以闻见、看见的场景。旋律并不急着宣泄，而是让回忆在细节里慢慢变得清晰。",
        "themes": ["夏日", "青春", "气味记忆", "含蓄浪漫"],
        "listening_points": ["留意歌词如何用自然景物代替直接告白", "听主歌到副歌时情绪如何由叙述转为展开", "观察旋律中的轻盈感与怀旧感如何同时存在"],
    },
    "东风破": {
        "recording_id": "jay-chou-dongfengpo",
        "artist": "周杰伦",
        "album": "叶惠美",
        "year": 2003,
        "subtitle": "古典意象进入现代流行结构",
        "narrative": "它的魅力来自时间错位：古典化的词语、旧物与离愁，被放进现代流行旋律里。听感既熟悉又遥远，像从今天回望一个已经模糊的故事。",
        "themes": ["中国风", "离别", "旧时光", "含蓄叙事"],
        "listening_points": ["留意旧物与空间意象如何推动叙事", "比较主歌的克制与副歌的舒展", "听传统音色和现代节奏之间的融合"],
    },
    "以父之名": {
        "recording_id": "jay-chou-yifuzhiming",
        "artist": "周杰伦",
        "album": "叶惠美",
        "year": 2003,
        "subtitle": "宗教意象、罪与救赎的电影化叙事",
        "narrative": "这首歌更像一段声音电影。环境声、角色感和暗色旋律共同建立世界观，歌词不是平铺直叙，而是在仪式、罪感和命运之间制造张力。",
        "themes": ["电影感", "宗教意象", "命运", "暗黑叙事"],
        "listening_points": ["先听环境声如何建立场景", "留意说唱段落的角色感与视角变化", "感受副歌旋律如何把紧张感转化为宿命感"],
    },
    "简单爱": {
        "recording_id": "jay-chou-simple-love",
        "artist": "周杰伦",
        "album": "范特西",
        "year": 2001,
        "subtitle": "直白愿望里保留的青春质感",
        "narrative": "它没有复杂的故事机关，而是把喜欢一个人的愿望写得自然、轻松。真正耐听的地方，是旋律、节奏和口语化表达共同保留了年轻时的笨拙与真诚。",
        "themes": ["青春", "校园", "直白浪漫", "轻松感"],
        "listening_points": ["留意口语化歌词带来的亲近感", "听节奏如何让情歌保持轻盈", "感受简单愿望背后的真诚与不设防"],
    },
}


class ListeningAgent:
    def __init__(self, store: DataStore) -> None:
        self.store = store
        self.recommender = DailyRecommender(store)

    @staticmethod
    def prompt_settings() -> ListeningPromptSettings:
        core_prompt = get_listening_companion_core_prompt() or CORE_LISTENING_COMPANION_PROMPT
        custom_prompt = get_listening_companion_prompt()
        return ListeningPromptSettings(
            default_core_prompt=CORE_LISTENING_COMPANION_PROMPT,
            core_prompt=core_prompt,
            custom_prompt=custom_prompt,
            effective_prompt=build_listening_companion_prompt(custom_prompt, core_prompt),
            editable_scope="基础提示词和陪伴偏好都可修改；运行约束仍由系统保留，避免 Agent Loop 和工具边界失效。",
        )

    @staticmethod
    def update_prompt_settings(request: ListeningPromptUpdate) -> ListeningPromptSettings:
        if request.core_prompt is not None:
            save_listening_companion_core_prompt(request.core_prompt)
        save_listening_companion_prompt(request.custom_prompt)
        return ListeningAgent.prompt_settings()

    def context(self) -> ListeningContextResponse:
        now_playing = get_now_playing()
        live_title = now_playing.get("title")
        title = str(live_title or "").strip() or None
        retain_current_song_cache(title, now_playing.get("artist"))
        status: Literal["live", "idle"] = "live" if live_title else "idle"
        guide = self._guide_for(title)
        recording = self._recording_for(title, guide, now_playing.get("artist"))
        state = load_state()
        artist = self.store.get_artist(recording.artist_id) if recording else None
        release = self.store.get_release(recording.release_id) if recording else None
        current_recording_id = recording.id if recording else (str(guide["recording_id"]) if guide else None)

        current = TrackState(
            status=status,
            available=bool(live_title),
            recording_id=current_recording_id,
            like_count=int(state.get("like_counts", {}).get(current_recording_id, 0)) if current_recording_id else 0,
            title=(guide and self._guide_title(guide)) or title,
            artist=(guide and str(guide["artist"])) or (artist.name if artist else now_playing.get("artist")),
            album=(guide and str(guide["album"])) or (release.title if release else None),
            year=(guide and int(guide["year"])) or (recording.year if recording else None),
            raw_title=now_playing.get("raw_title"),
            source=str(now_playing.get("source") or "windows-window-title"),
        )
        story = self._story_for(current, cached_only=True)
        return ListeningContextResponse(
            current=current,
            story=story,
            quick_prompts=self._quick_prompts(current),
            profile=ListenerProfile(
                favorite_artist="根据播放记录生成",
                listener_type="沉浸式听众",
                preferences=["歌词理解", "歌曲简介", "听感记录"],
            ),
            sources=[*OPEN_DATA_SOURCES[:3], SEED_SOURCE],
        )

    def story(self, request: ListeningStoryRequest) -> SongStory:
        current = TrackState(
            status="live",
            available=True,
            title=request.title,
            artist=request.artist,
            album=request.album,
            year=request.year,
            raw_title=None,
            source="listening-story-request",
        )
        return self._story_for(current, cached_only=False)

    def analyze_lyrics(self, request: LyricAnalysisRequest) -> LyricAnalysis:
        excerpt = request.excerpt.strip()
        imagery = self._detect_groups(excerpt, {
            "自然景物": "风雨雪云月海花草树叶",
            "时间与记忆": "年岁昔曾记忆从前后来等待",
            "空间与距离": "窗街巷城远近天涯路桥",
            "颜色与光线": "黑白红蓝光影暗亮黄昏夜",
            "古典意象": "东风琵琶琴酒笛月楼阁江南",
        })
        emotion = self._detect_groups(excerpt, {
            "怀念": "想念怀念回忆从前曾经",
            "离别": "离开告别远走分手再见",
            "孤独": "孤独一个人寂寞安静无人",
            "温柔": "温柔微笑陪伴拥抱喜欢爱",
            "宿命感": "命运注定罪救赎永远轮回",
        })
        line_count = len([line for line in excerpt.splitlines() if line.strip()])
        craft = ["意象驱动表达" if imagery else "以直接叙述为主"]
        if line_count > 1:
            craft.append(f"通过 {line_count} 行形成停顿和递进")
        if any(mark in excerpt for mark in "，。！？；"):
            craft.append("标点制造了接近呼吸节奏的停顿")
        if len(set(excerpt)) < len(excerpt) * 0.65:
            craft.append("重复用词强化了记忆点")
        summary = self._analysis_summary(excerpt, imagery, emotion, request.song_title)
        return LyricAnalysis(
            summary=summary,
            imagery=imagery or ["暂未识别出明确具象意象"],
            emotion=emotion or ["情绪较含蓄，需要结合上下文判断"],
            craft=craft,
            listening_questions=[
                "这句话是在描述事实，还是在隐藏真正的情绪？",
                "如果去掉旋律，这句话仍然会让你停下来吗？",
                "它与整首歌最核心的画面有什么联系？",
            ],
            copyright_note="仅分析你主动提供的短句，不存储或补全完整歌词。",
        )

    def chat(self, request: ListeningChatRequest) -> ListeningChatResponse:
        persist_conversation = self._is_current_song(request.song_title, request.artist)
        if not os.getenv("DEEPSEEK_API_KEY"):
            return self._fallback_chat(request, persist_conversation, use_ai=False)
        try:
            return self._langchain_chat(request, persist_conversation)
        except (GraphRecursionError, OpenAIError, httpx.HTTPError, ValueError, TypeError, KeyError):
            return self._fallback_chat(request, persist_conversation, use_ai=False)

    def _langchain_chat(self, request: ListeningChatRequest, persist_conversation: bool) -> ListeningChatResponse:
        started = time.perf_counter()
        research_sources: list[SourceRef] = []

        @tool
        def get_current_song_context() -> dict:
            """读取当前歌曲身份与已有缓存，不触发新的模型生成。"""
            return get_current_song_context_workflow(request.song_title, request.artist)

        @tool
        def save_listening_memory(
            memory_type: Literal["lyric_specimen", "music_note"],
        ) -> dict:
            """在用户明确要求时，把其原文保存为歌词标本或音乐笔记。"""
            if not self._has_explicit_save_intent(request.question):
                return {"saved": False, "message": "当前消息没有明确要求保存，未执行写入。"}
            if memory_type == "lyric_specimen":
                content = self._explicit_content(request.question) or (request.lyric_excerpt or "").strip()
            else:
                content = self._explicit_content(request.question) or self._previous_user_feeling(request)
            if not content:
                return {"saved": False, "message": "用户还没有提供可保存的原文。"}
            return save_listening_memory_workflow(
                memory_type,
                content,
                request.song_title,
                request.artist,
            )

        @tool
        def find_similar_recordings() -> dict:
            """根据当前歌曲的风格、情绪、年代与曲库关系推荐相似歌曲。"""
            return {"recommendation": self._similar_answer(request.song_title)}

        @tool
        def search_song_sources() -> dict:
            """联网检索当前歌曲的可追溯公开资料，只返回来源和原始事实。"""
            result = search_song_sources_workflow(request.song_title, request.artist)
            research_sources.extend(SourceRef.model_validate(source) for source in result["sources"])
            return result

        @tool
        def web_search(query: str) -> dict:
            """搜索网页并读取前几条网页正文；用于歌曲故事、创作背景、采访、乐评和其他现有资料不足的问题。"""
            result = web_search_workflow(
                query,
                song_title=request.song_title,
                artist=request.artist,
            )
            research_sources.extend(SourceRef.model_validate(source) for source in result["sources"])
            return result

        @tool
        def research_song_public_impact() -> dict:
            """联网研究当前歌曲当年的热度、传播、奖项、销量和公众影响力线索。"""
            result = research_song_public_impact_workflow(
                request.song_title,
                request.artist,
                request.question,
            )
            research_sources.extend(SourceRef.model_validate(source) for source in result["sources"])
            return result

        tools_list = [
            get_current_song_context,
            save_listening_memory,
            find_similar_recordings,
            search_song_sources,
            web_search,
            research_song_public_impact,
        ]
        model = ChatOpenAI(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0.35,
            timeout=10,
            max_retries=0,
            max_tokens=900,
        )
        agent = create_agent(
            model,
            tools_list,
            system_prompt=build_listening_companion_prompt(),
            middleware=[
                ToolCallLimitMiddleware(run_limit=1, exit_behavior="end"),
                *[
                    ToolCallLimitMiddleware(tool_name=item.name, run_limit=1, exit_behavior="end")
                    for item in tools_list
                ],
            ],
        )
        history = [
            {"role": "assistant" if item.role == "agent" else "user", "content": item.content}
            for item in request.recent_messages[-8:]
        ]
        current_context = {
            "song": request.song_title,
            "artist": request.artist,
            "lyric_excerpt": request.lyric_excerpt,
            "question": request.question,
        }
        result = agent.invoke(
            {"messages": [*history, {"role": "user", "content": json.dumps(current_context, ensure_ascii=False)}]},
            config={"recursion_limit": 6},
        )
        trace, tools_used = [], []
        for message in result["messages"]:
            for call in getattr(message, "tool_calls", []) or []:
                tools_used.append(call["name"])
                trace.append({"type": "tool_call", "tool": call["name"], "args": call.get("args", {})})
            if getattr(message, "type", "") == "tool":
                trace.append({
                    "type": "tool_result",
                    "tool": getattr(message, "name", "tool"),
                    "content": str(message.content)[:1000],
                })
        answer = str(result["messages"][-1].content)
        if persist_conversation and request.song_title:
            save_listening_conversation_turn(
                request.song_title,
                request.artist,
                request.question.strip(),
                answer,
                request.client_message_id,
            )
        return ListeningChatResponse(
            answer=answer,
            tools_used=list(dict.fromkeys(tools_used)),
            suggestions=["帮我收藏这句话", "记下刚才的感受", "推荐类似的歌", "查一下这首歌真实的创作故事"],
            sources=research_sources or [*OPEN_DATA_SOURCES[:2], SEED_SOURCE],
            mode="langchain:react",
            trace=trace,
            iterations=len([item for item in trace if item["type"] == "tool_call"]),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def _fallback_chat(
        self,
        request: ListeningChatRequest,
        persist_conversation: bool,
        use_ai: bool = True,
    ) -> ListeningChatResponse:
        started = time.perf_counter()
        question = request.question.strip()
        guide = self._guide_for(request.song_title)
        tools_used: list[str] = []
        sources: list[SourceRef] = []

        if self._matches(question, "收藏这句话", "收藏这句", "保存这句话", "保存这句", "歌词标本"):
            excerpt = self._explicit_content(question) or (request.lyric_excerpt or "").strip()
            if excerpt:
                save_listening_memory_workflow(
                    "lyric_specimen",
                    excerpt,
                    request.song_title,
                    request.artist,
                )
                tools_used.append("save_listening_memory")
                answer = f"已经把“{excerpt[:70]}”收藏到歌词标本馆，并保留了当前歌曲和收藏时间。"
            else:
                answer = "可以。请先在左侧写下那句歌词，或者直接对我说“帮我收藏这句话：歌词内容”。"
        elif self._matches(question, "记下刚才的感受", "记录刚才的感受", "保存音乐笔记", "记一条音乐笔记"):
            content = self._explicit_content(question) or self._previous_user_feeling(request)
            if content:
                save_listening_memory_workflow(
                    "music_note",
                    content,
                    request.song_title,
                    request.artist,
                )
                tools_used.append("save_listening_memory")
                answer = f"已经把这段感受记进音乐笔记：“{content[:90]}”"
            else:
                answer = "你想记下哪种感受？可以直接说“记下刚才的感受：此刻想到的话”，我会连同当前歌曲和时间一起保存。"
        elif request.lyric_excerpt and any(word in question for word in ("歌词", "这句", "意象", "隐喻")):
            analysis = self.analyze_lyrics(LyricAnalysisRequest(
                excerpt=request.lyric_excerpt,
                song_title=request.song_title,
                artist=request.artist,
            ))
            answer = f"{analysis.summary} 可以重点从“{'、'.join(analysis.imagery[:2])}”和“{'、'.join(analysis.emotion[:2])}”两个方向继续听。"
        elif self._is_public_impact_query(question):
            result = research_song_public_impact_workflow(
                request.song_title,
                request.artist,
                question,
            )
            facts = [str(item) for item in result["facts"]]
            sources.extend(SourceRef.model_validate(source) for source in result["sources"])
            tools_used.append("research_song_public_impact")
            answer = self._public_impact_fallback_answer(request, facts)
        elif self._requires_web_search(question) or (self._needs_web_search(question) and not guide):
            query = " ".join(part for part in (request.artist, request.song_title, question) if part)
            result = web_search_workflow(query, request.song_title, request.artist)
            facts = [str(item) for item in result["facts"]]
            sources.extend(SourceRef.model_validate(source) for source in result["sources"])
            tools_used.append("web_search")
            answer = self._web_search_fallback_answer(request, facts, bool(result.get("documents")))
        elif any(word in question for word in ("推荐", "相似", "下一首")):
            tools_used.append("find_similar_recordings")
            answer = self._similar_answer(request.song_title)
        elif any(word in question for word in ("故事", "背景", "简介", "介绍", "资料", "特别", "为什么")):
            answer = str(guide["narrative"]) if guide else self._generic_chat_story(request)
        elif use_ai:
            ai_answer = self._ai_companion_answer(request, guide)
            if ai_answer:
                tools_used.append("deepseek_companion_response")
                answer = ai_answer
            else:
                answer = self._default_answer(request, guide)
        else:
            answer = self._default_answer(request, guide)

        if persist_conversation and request.song_title:
            save_listening_conversation_turn(
                request.song_title,
                request.artist,
                question,
                answer,
                request.client_message_id,
            )

        return ListeningChatResponse(
            answer=answer,
            tools_used=tools_used,
            suggestions=["帮我收藏这句话", "记下刚才的感受", "推荐类似的歌", "查一下这首歌真实的创作故事"],
            sources=sources or [*OPEN_DATA_SOURCES[:2], SEED_SOURCE],
            mode="fallback:rules",
            trace=[{"type": "tool_call", "tool": tool_name, "args": {}} for tool_name in tools_used],
            iterations=len(tools_used),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def conversation(self, song_title: str, artist: str | None = None) -> dict[str, object]:
        return {
            "song_title": song_title,
            "artist": artist,
            "messages": listening_conversation(song_title, artist),
        }

    def _is_current_song(self, song_title: str | None, artist: str | None) -> bool:
        if not song_title:
            return False
        snapshot = get_now_playing()
        if self._normalize(str(snapshot.get("title") or "")) != self._normalize(song_title):
            return False
        live_artist = self._normalize(str(snapshot.get("artist") or ""))
        requested_artist = self._normalize(artist)
        return not live_artist or not requested_artist or live_artist == requested_artist

    def _matches(self, question: str, *phrases: str) -> bool:
        return any(phrase in question for phrase in phrases)

    def _explicit_content(self, question: str) -> str:
        match = re.search(r"[：:]\s*(.+)$", question, re.S)
        return match.group(1).strip() if match else ""

    def _previous_user_feeling(self, request: ListeningChatRequest) -> str:
        for message in reversed(request.recent_messages):
            content = message.content.strip()
            if message.role == "user" and content and not self._matches(content, "记下", "记录", "保存"):
                return content
        return ""

    @staticmethod
    def _has_explicit_save_intent(question: str) -> bool:
        return any(token in question for token in ("收藏", "保存", "记下", "记录", "记一笔", "写进笔记"))

    @staticmethod
    def _is_public_impact_query(question: str) -> bool:
        return any(
            token in question
            for token in (
                "多火",
                "火吗",
                "火不火",
                "当年",
                "热度",
                "销量",
                "榜单",
                "奖项",
                "拿奖",
                "传唱",
                "影响力",
                "为什么火",
                "红到",
                "爆火",
                "流行",
            )
        )

    @staticmethod
    def _needs_web_search(question: str) -> bool:
        return any(
            token in question
            for token in (
                "故事",
                "创作",
                "背景",
                "背后",
                "真实",
                "资料",
                "来源",
                "采访",
                "乐评",
                "发行",
                "写的是什么",
                "讲的是什么",
                "查一下",
                "联网查",
            )
        )

    @staticmethod
    def _requires_web_search(question: str) -> bool:
        return any(
            token in question
            for token in (
                "查一下",
                "联网查",
                "真实",
                "资料",
                "来源",
                "采访",
                "乐评",
                "写的是什么",
                "讲的是什么",
            )
        )

    def _web_search_fallback_answer(
        self,
        request: ListeningChatRequest,
        facts: list[str],
        read_pages: bool,
    ) -> str:
        title = request.song_title or "这首歌"
        if facts:
            evidence = "\n".join(f"{index + 1}. {fact}" for index, fact in enumerate(facts[:4]))
            note = "我读了搜索结果和可访问网页正文后，先把能落地的线索摆出来。"
        else:
            evidence = "1. 暂时没有检索到足够可靠的公开网页资料。"
            note = "这次网页搜索没有拿到足够可靠的信息，我不硬编创作故事。"
        boundary = "已读取网页正文。" if read_pages else "目前主要依据搜索摘要，证据强度有限。"
        return (
            f"## 《{title}》可以先这样理解\n\n"
            f"{note}{boundary}\n\n"
            "### 可核实线索\n"
            f"{evidence}\n\n"
            "### 听这一遍\n"
            "如果资料没有直接说明作者本意，我会把事实和听感分开：事实留给来源，情绪留给这首歌本身。"
        )

    def _public_impact_fallback_answer(
        self,
        request: ListeningChatRequest,
        facts: list[str],
    ) -> str:
        title = request.song_title or "这首歌"
        artist = request.artist
        heading = f"《{title}》当年到底有多火"
        intro = f"我先查公开资料。关于{artist + '的' if artist else ''}《{title}》，可靠资料里如果没有明确销量、榜单或奖项数字，我不会硬编。"
        if facts:
            evidence = "\n".join(f"{index + 1}. {fact}" for index, fact in enumerate(facts[:4]))
        else:
            evidence = "1. 暂时没有检索到足够可靠的公开资料。"
        return (
            f"## {heading}\n\n"
            f"{intro}\n\n"
            "### 可核实线索\n"
            f"{evidence}\n\n"
            "### 我的判断\n"
            "如果资料缺少硬数字，只能把它放回当时的传播环境里看：专辑、歌手组合、旋律记忆点、KTV/校园/电台和网络二次传播，都会共同决定一首歌是不是真的留下来。"
        )

    def _ai_companion_answer(self, request: ListeningChatRequest, guide: dict[str, object] | None) -> str | None:
        context = {
            "song": request.song_title,
            "artist": request.artist,
            "question": request.question,
            "lyric_excerpt": request.lyric_excerpt,
            "known_guide": {
                "narrative": guide.get("narrative"),
                "listening_points": guide.get("listening_points"),
            } if guide else None,
        }
        return self._invoke_ai(
            build_listening_companion_prompt(),
            context,
        )

    def _invoke_ai(self, system_prompt: str, payload: dict[str, object]) -> str | None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return None
        try:
            model = ChatOpenAI(
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                api_key=api_key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                temperature=0.35,
                timeout=8,
                max_retries=0,
                max_tokens=420,
            )
            response = model.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ])
            content = response.content
            return content.strip() if isinstance(content, str) and content.strip() else None
        except (OpenAIError, httpx.HTTPError, ValueError, TypeError, KeyError):
            return None

    def _guide_for(self, title: str | None) -> dict[str, object] | None:
        normalized = self._normalize(title)
        if not normalized:
            return None
        for guide_title, guide in SONG_GUIDES.items():
            if self._normalize(guide_title) in normalized or normalized in self._normalize(guide_title):
                return {**guide, "title": guide_title}
        return None

    def _guide_title(self, guide: dict[str, object]) -> str:
        return str(guide.get("title") or "")

    def _recording_for(self, title: str | None, guide: dict[str, object] | None, artist: str | None = None):
        if guide:
            recording = self.store.get_recording(str(guide["recording_id"]))
            if recording:
                return recording
        matches = self.store.search_recordings(title or "") if title else []
        title_key = self._normalize(title)
        artist_key = self._normalize(artist)
        for candidate in matches:
            if self._normalize(candidate.title) != title_key:
                continue
            if artist_key:
                candidate_artist = self.store.get_artist(candidate.artist_id)
                candidate_artist_key = self._normalize(candidate_artist.name if candidate_artist else None)
                if candidate_artist_key != artist_key:
                    continue
            return candidate
        return None

    def _story_for(self, current: TrackState, cached_only: bool) -> SongStory | None:
        if not current.title:
            return None
        introduction = (
            cached_song_introduction(current.title, current.artist)
            if cached_only
            else song_introduction(current.title, current.artist, current.album, current.year)
        )
        if not introduction:
            return None
        return SongStory(
            title=current.title,
            subtitle=str(introduction["subtitle"]),
            narrative=str(introduction["narrative"]),
            themes=list(introduction["themes"]),
            listening_points=list(introduction["listening_points"]),
            story_type=str(introduction["story_type"]),
            facts=list(introduction.get("facts", [])),
            source_urls=list(introduction.get("source_urls", [])),
        )

    def _quick_prompts(self, current: TrackState) -> list[str]:
        return [
            "帮我收藏这句话",
            "记下刚才的感受",
            "推荐类似的歌",
            "查一下这首歌真实的创作故事",
        ]

    def _similar_answer(self, title: str | None) -> str:
        guide = self._guide_for(title)
        recording = self._recording_for(title, guide)
        if not recording:
            return "我还没有在本地曲库里匹配到这首歌。你可以告诉我更完整的歌名和歌手，我再从风格、情绪和叙事方式三个维度推荐。"
        result = find_similar_recordings_workflow(self.recommender, recording.id, limit=3)
        names = [
            self._display_title(str(item["recording_id"]), str(item["title"]))
            for item in result["items"]
        ]
        return f"可以接着听：{'、'.join(names)}。这些作品在风格标签、情绪或年代气质上与当前歌曲有交集。"

    def _display_title(self, recording_id: str, fallback: str) -> str:
        for title, guide in SONG_GUIDES.items():
            if guide["recording_id"] == recording_id:
                return title
        return fallback

    def _generic_chat_story(self, request: ListeningChatRequest) -> str:
        song = request.song_title or "当前歌曲"
        introduction = song_introduction(song, request.artist)
        return str(introduction["narrative"])

    def _default_answer(self, request: ListeningChatRequest, guide: dict[str, object] | None) -> str:
        if guide:
            points = list(guide["listening_points"])
            return f"听《{self._guide_title(guide)}》时，我建议先关注：{points[0]}；然后再注意{points[1]}。"
        return "我会先读取当前歌曲，再结合已核实的目录资料、歌词短句和听歌记录回答。你可以问歌曲简介、歌词意象、编曲听感或下一首推荐。"

    def _analysis_summary(self, excerpt: str, imagery: list[str], emotion: list[str], song_title: str | None) -> str:
        subject = f"《{song_title}》里的这段文字" if song_title else "这段歌词"
        if imagery and emotion:
            return f"{subject}没有直接说透情绪，而是借助{imagery[0]}承载{emotion[0]}，因此听起来更有余味。"
        if imagery:
            return f"{subject}更依赖画面而不是结论，核心入口是{imagery[0]}。"
        if emotion:
            return f"{subject}的情绪指向{emotion[0]}，表达方式相对直接。"
        return f"{subject}的信息比较克制，建议结合上一句、下一句以及旋律落点一起理解。"

    def _detect_groups(self, text: str, groups: dict[str, str]) -> list[str]:
        return [label for label, characters in groups.items() if any(char in text for char in characters)]

    def _normalize(self, value: str | None) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]", "", (value or "").lower())
