from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.daily_context import get_anniversaries, get_computer_context, get_music_news, get_weather
from app.data_store import DataStore
from app.hybrid_recommender import HybridRecommender
from app.listener_memory import (
    listener_summary,
    load_state,
    recent_exposed_recording_ids,
    recent_recording_ids,
    record_recommendation_exposure,
)
from app.models import Artist, Recording, SourceRef
from app.sources import ITUNES_CATALOG_SOURCE, OPEN_DATA_SOURCES, SEED_SOURCE

class TodayPick(BaseModel):
    role: Literal["main", "familiar", "explore"]
    role_label: str
    recording: Recording
    artist: Artist
    score: float
    headline: str
    explanation: str
    signals: dict[str, int]

class TodayExperience(BaseModel):
    today: date
    active_mode: str
    greeting: str
    weather: dict[str, Any]
    computer: dict[str, Any]
    news: list[dict[str, Any]]
    anniversaries: list[dict[str, Any]]
    picks: list[TodayPick]
    profile: dict[str, Any]
    catalog_size: int
    sources: list[SourceRef]

class TodayRecommender:
    def __init__(self, store: DataStore) -> None:
        self.store = store

    def build(self, user_id: str = "demo", session_seed: str | None = None, mode: str = "auto") -> TodayExperience:
        with ThreadPoolExecutor(max_workers=2) as executor:
            weather_future = executor.submit(get_weather)
            news_future = executor.submit(get_music_news)
            weather = weather_future.result()
            news = news_future.result()
        anniversaries = get_anniversaries(self.store)
        computer = get_computer_context()
        state = load_state()
        recent = recent_recording_ids(30) | recent_exposed_recording_ids(14)
        candidates = [item for item in self.store.recordings.values() if item.is_cpop and self.store.get_artist(item.artist_id)]
        recommendation = HybridRecommender(self.store).recommend(
            limit=1,
            mode=mode,
            seed=session_seed or "daily",
            context={"weather": weather, "news": news},
            exclude_ids=recent,
        )
        ranked_item = recommendation["items"][0]
        main = self.store.get_recording(ranked_item["recording"]["id"])
        assert main is not None
        pick = self._present("main", main, weather, news, state, recent)
        pick.score = ranked_item["score"]
        pick.signals = {
            "内容相似": round(ranked_item["breakdown"]["content_similarity"] * 100),
            "BPR排序": round(ranked_item["breakdown"]["bpr_pairwise"] * 100),
            "场景匹配": round(ranked_item["breakdown"]["context"] * 100),
            "探索价值": round(ranked_item["breakdown"]["thompson"] * 100),
        }
        picks = [pick]
        record_recommendation_exposure([pick.recording.id for pick in picks], mode)
        return TodayExperience(
            today=date.today(), active_mode=mode, greeting=self._greeting(weather), weather=weather, computer=computer, news=news,
            anniversaries=anniversaries, picks=picks, profile=listener_summary(state),
            catalog_size=len(candidates),
            sources=[OPEN_DATA_SOURCES[0], ITUNES_CATALOG_SOURCE, OPEN_DATA_SOURCES[2], SEED_SOURCE],
        )

    def _choose(self, ranked: list[Recording], chosen: list[Recording]) -> Recording:
        used_ids = {item.id for item in chosen}
        used_artists = {item.artist_id for item in chosen}
        for item in ranked:
            if item.id not in used_ids and item.artist_id not in used_artists:
                chosen.append(item)
                return item
        for item in ranked:
            if item.id not in used_ids:
                chosen.append(item)
                return item
        return ranked[0]

    def _score(self, item: Recording, weather: dict[str, Any], news: list[dict[str, Any]], state: dict, recent: set[str], seed: str | None, mode: str) -> float:
        artist = self.store.get_artist(item.artist_id)
        personal = .48
        personal += .06 * len(set(item.tags) & {"r&b", "ballad", "chinese-style", "poetic", "cinematic"})
        personal += .06 * len(set(item.moods) & {"late-night", "nostalgic", "bittersweet", "warm", "reflective"})
        like_strength = min(.36, int(state.get("like_counts", {}).get(item.id, 0)) * .06)
        if item.id in state["liked"] or item.id in state["saved"]:
            personal += .22 + like_strength
        context_tokens = set(weather.get("music_moods", []))
        weather_score = min(1.0, .28 + .22 * len(context_tokens & set([*item.tags, *item.moods])))
        news_text = " ".join(article.get("title", "") for article in news)
        news_score = .82 if artist and artist.name and artist.name in news_text else .3
        freshness = .15 if item.id in recent else .92
        if item.id in state["skipped"]:
            freshness -= .35
        mode_tokens = {
            "focus": {"gentle", "r&b", "instrumental", "reflective"},
            "relax": {"warm", "gentle", "intimate", "ballad"},
            "nostalgia": {"nostalgic", "bittersweet", "campus", "chinese-style"},
            "lyrics": {"poetic", "narrative", "ballad", "chinese-style"},
        }.get(mode, set())
        mode_score = 0.35 + .18 * len(mode_tokens & set([item.artist_id, *item.tags, *item.moods]))
        hour = datetime.now().hour
        time_tokens = {"late-night", "intimate", "reflective"} if hour >= 21 or hour < 6 else {"warm", "youthful", "uplifting"}
        time_score = .35 + .16 * len(time_tokens & set([*item.tags, *item.moods]))
        discovery = .72 if item.id.startswith(("mb-", "itunes-")) else .26
        if item.id.startswith("user-") and item.id not in state["liked"] and item.id not in state["saved"]:
            discovery -= .22
        random_score = self._jitter(item.id, seed) * .05
        if seed:
            random_score = self._jitter(item.artist_id, seed) * .17 + self._jitter(item.id, seed) * .03
        return personal * .23 + weather_score * .20 + news_score * .10 + freshness * .14 + min(1.0, mode_score) * .10 + min(1.0, time_score) * .04 + discovery * .14 + random_score

    def _familiar_score(self, item: Recording, state: dict, recent: set[str], seed: str | None) -> float:
        score = .25
        like_strength = min(.4, int(state.get("like_counts", {}).get(item.id, 0)) * .08)
        if item.id.startswith("user-"):
            score += .65
        if item.id in state["liked"] or item.id in state["saved"]:
            score += .55 + like_strength
        score += min(.3, int(state["play_counts"].get(item.id, 0)) * .06)
        if item.id in recent:
            score -= .22
        return score + self._jitter(item.id, seed) * .08

    def _explore_score(self, item: Recording, state: dict, recent: set[str], seed: str | None) -> float:
        score = .72 if item.id.startswith("mb-") else .38
        if item.id in recent or item.id in state["liked"] or item.id in state["saved"]:
            score -= .45
        if item.year and item.year >= 2015:
            score += .12
        score += .08 * len(set(item.tags) & {"r&b", "chinese-style", "ballad", "rock"})
        return score + self._jitter(item.id, seed) * .12

    def _present(self, role: str, item: Recording, weather: dict[str, Any], news: list[dict[str, Any]], state: dict, recent: set[str]) -> TodayPick:
        artist = self.store.get_artist(item.artist_id)
        assert artist is not None
        weather_match = min(98, 38 + 17 * len(set(weather.get("music_moods", [])) & set([*item.tags, *item.moods])))
        personal = min(98, 68 + 4 * len(set(item.tags) & {"r&b", "ballad", "chinese-style"}))
        freshness = 28 if item.id in recent else 94
        news_text = " ".join(article.get("title", "") for article in news)
        news_signal = 85 if artist.name in news_text else 42
        labels = {"main": "今日主推荐", "familiar": "熟悉答案", "explore": "今日探索"}
        headlines = {
            "main": f"{weather.get('condition', '今天')}，让这首歌成为今天的声音。",
            "familiar": "从熟悉的旋律里，找回一点确定感。",
            "explore": "保留你的品味，但向陌生处多走一步。",
        }
        explanation = self._explanation(role, item, artist, weather, recent)
        score = (personal * .4 + weather_match * .25 + freshness * .22 + news_signal * .13) / 100
        return TodayPick(
            role=role, role_label=labels[role], recording=item, artist=artist, score=round(score, 3),
            headline=headlines[role], explanation=explanation,
            signals={"个人偏好": personal, "天气氛围": weather_match, "近期新鲜度": freshness, "今日事件": news_signal},
        )

    def _explanation(self, role: str, item: Recording, artist: Artist, weather: dict[str, Any], recent: set[str]) -> str:
        tags = "、".join([*item.moods[:2], *item.tags[:2]]) or "旋律和情绪"
        if role == "familiar":
            return f"{artist.name}与你的长期偏好更接近；这首歌以{tags}为主要线索，并避开了最近高频重复。"
        if role == "explore":
            return f"它保留了你喜欢的{tags}，但来自更少出现的作品，为今天增加一点新鲜感。"
        repeat_note = "近期没有重复出现" if item.id not in recent else "虽然最近听过，但上下文匹配很高"
        return f"当前天气倾向{weather.get('condition')}，而歌曲的{tags}与之呼应；{repeat_note}。"

    def _greeting(self, weather: dict[str, Any]) -> str:
        hour = datetime.now().hour
        period = "清晨" if hour < 9 else "上午" if hour < 12 else "下午" if hour < 18 else "夜晚"
        city = weather.get("city") or "你所在的城市"
        return f"{city}的{period}，今天适合认真听完一首歌。"

    def _jitter(self, item_id: str, seed: str | None) -> float:
        raw = f"{date.today().isoformat()}:{seed or 'daily'}:{item_id}".encode()
        return int(hashlib.sha1(raw).hexdigest()[:8], 16) / 0xFFFFFFFF
