from __future__ import annotations

import json
import os
import re
import time
from typing import Literal
from urllib.parse import quote_plus

import httpx
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.data_store import DataStore
from app.kugou import get_now_playing
from app.listener_memory import (
    LyricFragmentRequest,
    MusicNoteRequest,
    listening_conversation,
    save_listening_conversation_turn,
    save_lyric_fragment,
    save_music_note,
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


class TrackState(BaseModel):
    status: Literal["live", "idle"]
    available: bool
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

    def context(self) -> ListeningContextResponse:
        now_playing = get_now_playing()
        live_title = now_playing.get("title")
        title = str(live_title or "").strip() or None
        retain_current_song_cache(title, now_playing.get("artist"))
        status: Literal["live", "idle"] = "live" if live_title else "idle"
        guide = self._guide_for(title)
        recording = self._recording_for(title, guide, now_playing.get("artist"))
        artist = self.store.get_artist(recording.artist_id) if recording else None
        release = self.store.get_release(recording.release_id) if recording else None

        current = TrackState(
            status=status,
            available=bool(live_title),
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
        if not os.getenv("DEEPSEEK_API_KEY"):
            return self._fallback_chat(request)
        return self._langchain_chat(request)

    def _langchain_chat(self, request: ListeningChatRequest) -> ListeningChatResponse:
        started = time.perf_counter()
        research_sources: list[SourceRef] = []

        @tool
        def get_current_song_context() -> dict:
            """读取当前歌曲的情绪画像、可核实资料与聆听提示。"""
            if not request.song_title:
                return {"available": False, "message": "当前没有识别到歌曲。"}
            introduction = song_introduction(request.song_title, request.artist)
            return {
                "available": True,
                "song": request.song_title,
                "artist": request.artist,
                "portrait": introduction.get("narrative"),
                "themes": introduction.get("themes", []),
                "listening_points": introduction.get("listening_points", []),
                "facts": introduction.get("facts", []),
            }

        @tool
        def save_lyric_specimen(excerpt: str = "") -> dict:
            """把用户明确提供的一句歌词保存到歌词标本馆。"""
            if not self._has_explicit_save_intent(request.question):
                return {"saved": False, "message": "当前消息没有明确要求保存，未执行写入。"}
            content = excerpt.strip() or (request.lyric_excerpt or "").strip()
            if not content:
                return {"saved": False, "message": "用户还没有提供要收藏的歌词短句。"}
            fragment = save_lyric_fragment(LyricFragmentRequest(
                excerpt=content,
                song_title=request.song_title,
                artist=request.artist,
                note="通过音乐陪伴收藏",
            ))
            return {"saved": True, "excerpt": content[:100], "saved_at": fragment.get("saved_at")}

        @tool
        def save_current_feeling(content: str = "") -> dict:
            """把用户刚才表达的听歌感受保存为音乐笔记。"""
            if not self._has_explicit_save_intent(request.question):
                return {"saved": False, "message": "当前消息没有明确要求记录，未执行写入。"}
            feeling = content.strip() or self._previous_user_feeling(request)
            if not feeling:
                return {"saved": False, "message": "用户还没有表达可保存的感受。"}
            note = save_music_note(MusicNoteRequest(
                content=feeling,
                prompt="通过音乐陪伴记录此刻感受",
                song_title=request.song_title,
                artist=request.artist,
            ))
            return {"saved": True, "content": feeling[:120], "saved_at": note.get("saved_at")}

        @tool
        def find_similar_recordings() -> dict:
            """根据当前歌曲的风格、情绪、年代与曲库关系推荐相似歌曲。"""
            return {"recommendation": self._similar_answer(request.song_title)}

        @tool
        def analyze_lyric_excerpt(excerpt: str = "") -> dict:
            """分析用户提供的歌词短句中的意象、情绪与表达方式。"""
            content = excerpt.strip() or (request.lyric_excerpt or "").strip()
            if not content:
                return {"available": False, "message": "用户还没有提供歌词短句。"}
            analysis = self.analyze_lyrics(LyricAnalysisRequest(
                excerpt=content,
                song_title=request.song_title,
                artist=request.artist,
            ))
            return analysis.model_dump()

        @tool
        def search_song_story_web() -> dict:
            """联网检索当前歌曲真实的发行与创作资料，并返回来源。"""
            answer, sources = self._research_song_story(request)
            research_sources.extend(sources)
            return {"answer": answer, "sources": [source.model_dump() for source in sources]}

        tools_list = [
            get_current_song_context,
            save_lyric_specimen,
            save_current_feeling,
            find_similar_recordings,
            analyze_lyric_excerpt,
            search_song_story_web,
        ]
        model = ChatOpenAI(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0.35,
            timeout=30,
            max_retries=0,
            max_tokens=520,
        )
        agent = create_agent(
            model,
            tools_list,
            system_prompt=(
                "你是听歌房里的音乐陪伴者，只围绕此刻正在播放的这一首歌，陪用户细腻地听、感受和品味。"
                "优先回应用户听见的画面、情绪、声音细节和私人联想，可以提出最多一个温和的问题帮助用户继续听下去。"
                "不要像全能音乐助理一样做宽泛的数据报告、账户总结或理性长分析；事实与感受要分开，不能替用户断言情绪。"
                "必须通过标准 Agent Loop 工作："
                "先理解用户意图，需要保存、推荐、歌词分析、歌曲资料或联网故事时必须调用对应工具，"
                "读取工具 observation 后再回答；必要时可以继续调用下一个工具。"
                "保存歌词或音乐笔记属于写操作，只能在当前这条用户消息明确要求收藏、保存、记下或记录时调用；"
                "不能因为历史消息里出现了感受就自动保存。通常只调用 1 到 2 个必要工具。"
                "普通情绪交流可以直接回应，但涉及事实不得猜测。不要暴露工具名、内部步骤或思考过程，"
                "不要补全歌词，回答自然、细腻、克制、有陪伴感，通常控制在 220 字以内。"
            ),
            middleware=[
                ToolCallLimitMiddleware(run_limit=4, exit_behavior="continue"),
                *[
                    ToolCallLimitMiddleware(tool_name=item.name, run_limit=1, exit_behavior="continue")
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
            config={"recursion_limit": 24},
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
        if request.song_title:
            save_listening_conversation_turn(request.song_title, request.artist, request.question.strip(), answer)
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

    def _fallback_chat(self, request: ListeningChatRequest) -> ListeningChatResponse:
        started = time.perf_counter()
        question = request.question.strip()
        guide = self._guide_for(request.song_title)
        tools_used = ["get_now_playing"]
        sources: list[SourceRef] = []

        if self._matches(question, "收藏这句话", "收藏这句", "保存这句话", "保存这句", "歌词标本"):
            excerpt = self._explicit_content(question) or (request.lyric_excerpt or "").strip()
            if excerpt:
                save_lyric_fragment(LyricFragmentRequest(
                    excerpt=excerpt,
                    song_title=request.song_title,
                    artist=request.artist,
                    note="通过音乐陪伴收藏",
                ))
                tools_used.append("save_lyric_specimen")
                answer = f"已经把“{excerpt[:70]}”收藏到歌词标本馆，并保留了当前歌曲和收藏时间。"
            else:
                answer = "可以。请先在左侧写下那句歌词，或者直接对我说“帮我收藏这句话：歌词内容”。"
        elif self._matches(question, "记下刚才的感受", "记录刚才的感受", "保存音乐笔记", "记一条音乐笔记"):
            content = self._explicit_content(question) or self._previous_user_feeling(request)
            if content:
                save_music_note(MusicNoteRequest(
                    content=content,
                    prompt="通过音乐陪伴记录此刻感受",
                    song_title=request.song_title,
                    artist=request.artist,
                ))
                tools_used.append("save_music_note")
                answer = f"已经把这段感受记进音乐笔记：“{content[:90]}”"
            else:
                answer = "你想记下哪种感受？可以直接说“记下刚才的感受：此刻想到的话”，我会连同当前歌曲和时间一起保存。"
        elif request.lyric_excerpt and any(word in question for word in ("歌词", "这句", "意象", "隐喻")):
            analysis = self.analyze_lyrics(LyricAnalysisRequest(
                excerpt=request.lyric_excerpt,
                song_title=request.song_title,
                artist=request.artist,
            ))
            tools_used.append("analyze_lyric_excerpt")
            answer = f"{analysis.summary} 可以重点从“{'、'.join(analysis.imagery[:2])}”和“{'、'.join(analysis.emotion[:2])}”两个方向继续听。"
        elif self._matches(question, "真实的创作故事", "真实创作故事", "查一下", "资料来源", "联网查", "真实背景"):
            answer, research_sources = self._research_song_story(request)
            tools_used.extend(["search_song_story_web", "summarize_verified_sources"])
            sources.extend(research_sources)
        elif any(word in question for word in ("推荐", "相似", "下一首")):
            tools_used.append("find_similar_recordings")
            answer = self._similar_answer(request.song_title)
        elif any(word in question for word in ("故事", "背景", "简介", "介绍", "资料", "特别", "为什么")):
            tools_used.append("build_song_introduction")
            answer = str(guide["narrative"]) if guide else self._generic_chat_story(request)
        else:
            ai_answer = self._ai_companion_answer(request, guide)
            if ai_answer:
                tools_used.append("deepseek_companion_response")
                answer = ai_answer
            else:
                answer = self._default_answer(request, guide)

        if request.song_title:
            save_listening_conversation_turn(request.song_title, request.artist, question, answer)

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

    def _research_song_story(self, request: ListeningChatRequest) -> tuple[str, list[SourceRef]]:
        title = request.song_title or "当前歌曲"
        query = " ".join(part for part in (request.artist, title) if part)
        facts: list[str] = []
        sources: list[SourceRef] = []
        try:
            response = httpx.get(
                "https://zh.wikipedia.org/w/api.php",
                params={
                    "action": "query", "generator": "search", "gsrsearch": query,
                    "gsrlimit": 3, "prop": "extracts|info", "exintro": 1,
                    "explaintext": 1, "inprop": "url", "format": "json", "origin": "*",
                },
                headers={"User-Agent": "C-Pop-Atlas/0.3 song-research"},
                timeout=8.0,
            )
            response.raise_for_status()
            pages = list(response.json().get("query", {}).get("pages", {}).values())
            for page in pages[:2]:
                extract = re.sub(r"\s+", " ", str(page.get("extract") or "")).strip()
                if extract:
                    facts.append(f"维基百科《{page.get('title', '')}》：{extract[:700]}")
                if page.get("fullurl"):
                    sources.append(SourceRef(name=f"维基百科：{page.get('title', title)}", url=page["fullurl"], license="CC BY-SA"))
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            pass
        try:
            response = httpx.get(
                "https://musicbrainz.org/ws/2/recording/",
                params={"query": f'recording:"{title}" AND artist:"{request.artist or ""}"', "fmt": "json", "limit": 3},
                headers={"User-Agent": "C-Pop-Atlas/0.3 local-listening-companion"},
                timeout=8.0,
            )
            response.raise_for_status()
            recordings = response.json().get("recordings", [])
            if recordings:
                item = recordings[0]
                releases = [release.get("title") for release in item.get("releases", [])[:3] if release.get("title")]
                facts.append(f"MusicBrainz：匹配到录音《{item.get('title', title)}》，首次发行日期 {item.get('first-release-date') or '未标注'}，相关发行版本：{'、'.join(releases) or '未标注'}。")
                sources.append(SourceRef(name="MusicBrainz recording search", url=f"https://musicbrainz.org/search?query={quote_plus(query)}&type=recording&method=indexed", license="CC0 core data"))
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            pass
        if not facts:
            introduction = song_introduction(title, request.artist)
            return f"暂时没有检索到足够可靠的公开资料。当前只能确认：{introduction['narrative']}", sources
        fallback = "\n\n".join(facts[:3])
        answer = self._invoke_ai(
            "你是严谨的中文歌曲资料编辑。只根据给定检索结果回答，不得编造创作人、采访、年份或幕后故事。资料不足时明确说明。回答控制在 260 字内，并区分已核实事实与合理听感。",
            {"song": title, "artist": request.artist, "question": request.question, "retrieved_facts": facts},
        )
        return answer or fallback, sources

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
            "你是听歌房里的中文音乐陪伴者，只围绕此刻正在播放的这一首歌。回应应细腻、克制、有听感，关注声音、画面、情绪和用户自己的联想；不要做宽泛的数据报告，不替用户断言感受。不要假装知道未提供的事实，不自称 Agent，不展示思考过程。若用户给出歌词短句，可以讨论其画面、情绪和写法，但不要补全歌词。回答控制在 220 字以内。",
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
                timeout=18,
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
        similar = self.recommender.similar_recordings(recording.id, limit=3)
        names = [self._display_title(item.id, item.title) for item in similar]
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
