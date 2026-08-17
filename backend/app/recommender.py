from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date, timedelta

from app.data_store import DataStore
from app.models import DailyPick, Recording, ScoreBreakdownItem
from app.preview import attach_preview_urls
from app.sources import OPEN_DATA_SOURCES, PREVIEW_SOURCE, SEED_SOURCE

DEFAULT_WEIGHTS = {
    "personal_preference": 0.30,
    "content_match": 0.22,
    "playability": 0.18,
    "freshness": 0.12,
    "cpop_relevance": 0.10,
    "diversity": 0.05,
    "exploration": 0.03,
}

ROTATION_EPOCH = date(2026, 1, 1)

USER_PROFILES = {
    "demo": {
        "favorite_tags": {"r&b", "mandopop", "ballad", "chinese-style"},
        "favorite_moods": {"nostalgic", "late-night", "bittersweet", "warm"},
        "favorite_artists": set(),
        "history": [],
    }
}


class DailyRecommender:
    def __init__(self, store: DataStore) -> None:
        self.store = store

    def pick(
        self,
        user_id: str | None = None,
        today: date | None = None,
        seed: str | None = None,
        tag: str | None = None,
        mood: str | None = None,
    ) -> DailyPick:
        user_id = user_id or "anonymous"
        today = today or date.today()
        candidates = [recording for recording in self.store.recordings.values() if recording.is_cpop]
        if not candidates:
            raise ValueError("No C-Pop recordings available")
        candidates = self._preferred_candidates(candidates, tag=tag, mood=mood)

        ranked = sorted(
            candidates,
            key=lambda recording: self._score(
                recording,
                user_id,
                today,
                seed,
                include_playability=False,
                tag=tag,
                mood=mood,
            ),
            reverse=True,
        )
        attach_preview_urls(ranked, self.store.artists)
        reranked = sorted(
            ranked,
            key=lambda recording: self._score(recording, user_id, today, seed, tag=tag, mood=mood),
            reverse=True,
        )
        chosen = self._respect_rotation_limits(reranked, today, user_id, seed)
        score = self._score(chosen, user_id, today, seed, tag=tag, mood=mood)
        artist = self.store.artists[chosen.artist_id]
        release = self.store.get_release(chosen.release_id)
        similar = self.similar_recordings(chosen.id, limit=3)
        attach_preview_urls(similar, self.store.artists)

        sources = [*OPEN_DATA_SOURCES[:2], SEED_SOURCE]
        if chosen.preview_url:
            sources.append(PREVIEW_SOURCE)

        return DailyPick(
            pick_date=today,
            user_id=user_id,
            recording=chosen,
            artist=artist,
            release=release,
            score=round(score, 4),
            score_breakdown=self.score_breakdown(chosen, user_id, today, seed, tag=tag, mood=mood),
            reasons=self.explain(chosen, user_id, tag=tag, mood=mood),
            similar_recordings=similar,
            sources=sources,
        )

    def similar_recordings(self, recording_id: str, limit: int = 5) -> list[Recording]:
        base = self.store.recordings[recording_id]
        ranked = sorted(
            [
                recording
                for recording in self.store.recordings.values()
                if recording.id != recording_id and recording.is_cpop
            ],
            key=lambda recording: self._similarity(base, recording),
            reverse=True,
        )
        return ranked[:limit]

    def explain(
        self,
        recording: Recording,
        user_id: str | None = None,
        tag: str | None = None,
        mood: str | None = None,
    ) -> list[str]:
        artist = self.store.artists[recording.artist_id]
        profile = self._profile_for(user_id or "", tag=tag, mood=mood)
        reasons = [
            f"{artist.name} 属于华语核心艺人池，地区、语言或标签命中华语识别规则。",
        ]

        if recording.tags:
            reasons.append(f"风格标签：{'、'.join(recording.tags[:3])}，适合做细分推荐。")
        if recording.moods:
            reasons.append(f"情绪氛围：{'、'.join(recording.moods[:3])}，适合按心情解释推荐。")
        if recording.preview_url:
            reasons.append("已匹配到公开 30 秒试听片段，可以直接试听。")

        if profile:
            matched_tags = sorted(set(recording.tags) & profile.get("favorite_tags", set()))
            matched_moods = sorted(set(recording.moods) & profile.get("favorite_moods", set()))
            if matched_tags:
                reasons.append(f"命中你的偏好风格：{'、'.join(matched_tags[:2])}。")
            if matched_moods:
                reasons.append(f"命中你的偏好情绪：{'、'.join(matched_moods[:2])}。")
        if tag and tag in recording.tags:
            reasons.append(f"这首歌命中了你临时选择的风格：{tag}。")
        if mood and mood in recording.moods:
            reasons.append(f"这首歌命中了你临时选择的情绪：{mood}。")

        if recording.year:
            reasons.append(self._era_reason(recording.year))
        return reasons[:5]

    def score_breakdown(
        self,
        recording: Recording,
        user_id: str,
        today: date,
        seed: str | None,
        tag: str | None = None,
        mood: str | None = None,
    ) -> list[ScoreBreakdownItem]:
        artist = self.store.artists[recording.artist_id]
        profile = self._profile_for(user_id, tag=tag, mood=mood)
        raw_scores = {
            "personal_preference": self._personal_score(recording, artist, profile),
            "content_match": self._content_score(recording),
            "playability": 1.0 if recording.preview_url else 0.0,
            "freshness": self._freshness_score(recording),
            "cpop_relevance": 1.0 if recording.is_cpop and artist.is_cpop else 0.4,
            "diversity": self._diversity_score(recording, profile),
            "exploration": self._exploration_score(recording, user_id, today, seed),
        }
        labels = {
            "personal_preference": "个人偏好",
            "content_match": "风格内容",
            "playability": "可试听",
            "freshness": "年代新鲜度",
            "cpop_relevance": "华语相关性",
            "diversity": "多样性",
            "exploration": "探索随机性",
        }
        return [
            ScoreBreakdownItem(
                key=key,
                label=labels[key],
                raw_score=round(raw_scores[key], 4),
                weight=weight,
                weighted_score=round(raw_scores[key] * weight, 4),
            )
            for key, weight in DEFAULT_WEIGHTS.items()
        ]

    def _score(
        self,
        recording: Recording,
        user_id: str,
        today: date,
        seed: str | None,
        include_playability: bool = True,
        tag: str | None = None,
        mood: str | None = None,
    ) -> float:
        artist = self.store.artists.get(recording.artist_id)
        if not artist:
            return 0.0

        profile = self._profile_for(user_id, tag=tag, mood=mood)
        playability = 1.0 if recording.preview_url and include_playability else 0.0
        return (
            self._personal_score(recording, artist, profile) * DEFAULT_WEIGHTS["personal_preference"]
            + self._content_score(recording) * DEFAULT_WEIGHTS["content_match"]
            + playability * DEFAULT_WEIGHTS["playability"]
            + self._freshness_score(recording) * DEFAULT_WEIGHTS["freshness"]
            + (1.0 if recording.is_cpop and artist.is_cpop else 0.4) * DEFAULT_WEIGHTS["cpop_relevance"]
            + self._diversity_score(recording, profile) * DEFAULT_WEIGHTS["diversity"]
            + self._exploration_score(recording, user_id, today, seed) * DEFAULT_WEIGHTS["exploration"]
        )

    def _respect_rotation_limits(
        self,
        ranked: list[Recording],
        today: date,
        user_id: str,
        seed: str | None = None,
    ) -> Recording:
        if user_id not in {"demo", "anonymous"}:
            return ranked[0]

        rotation_base = self._interleaved_by_artist(ranked)
        return self._choose_with_rotation_history(rotation_base, today, user_id, seed) or ranked[0]

    def _choose_with_rotation_history(
        self,
        candidates: list[Recording],
        today: date,
        user_id: str,
        seed: str | None,
    ) -> Recording | None:
        if not candidates:
            return None

        artist_count = len({recording.artist_id for recording in candidates})
        recording_window = min(30, max(0, len(candidates) - 1), max(0, artist_count - 1))
        artist_window = min(7, max(0, artist_count - 1))
        history_recording_ids: list[str] = []
        history_artist_ids: list[str] = []
        start_day = ROTATION_EPOCH if today >= ROTATION_EPOCH else today - timedelta(days=max(recording_window, artist_window))

        total_days = (today - start_day).days
        for offset in range(total_days + 1):
            day = start_day + timedelta(days=offset)
            day_seed = seed if day == today else None
            ordered = self._rotated_order(candidates, day, user_id, day_seed)
            recent_recording_ids = (
                set(history_recording_ids[-recording_window:]) if recording_window else set()
            )
            recent_artist_ids = set(history_artist_ids[-artist_window:]) if artist_window else set()
            choice = self._first_eligible(ordered, recent_recording_ids, recent_artist_ids)
            history_recording_ids.append(choice.id)
            history_artist_ids.append(choice.artist_id)
        return candidates and self.store.recordings.get(history_recording_ids[-1])

    def _first_eligible(
        self,
        ordered: list[Recording],
        recent_recording_ids: set[str],
        recent_artist_ids: set[str],
    ) -> Recording:
        eligible = [
            recording
            for recording in ordered
            if recording.id not in recent_recording_ids and recording.artist_id not in recent_artist_ids
        ]
        if eligible:
            return eligible[0]

        eligible = [recording for recording in ordered if recording.artist_id not in recent_artist_ids]
        if eligible:
            return eligible[0]

        eligible = [recording for recording in ordered if recording.id not in recent_recording_ids]
        return (eligible or ordered)[0]

    def _interleaved_by_artist(self, ranked: list[Recording]) -> list[Recording]:
        grouped: dict[str, list[Recording]] = {}
        for recording in ranked:
            grouped.setdefault(recording.artist_id, []).append(recording)

        artist_order = sorted(
            grouped,
            key=lambda artist_id: ranked.index(grouped[artist_id][0]),
        )
        interleaved: list[Recording] = []
        while artist_order:
            next_artist_order = []
            for artist_id in artist_order:
                artist_recordings = grouped[artist_id]
                if artist_recordings:
                    interleaved.append(artist_recordings.pop(0))
                if artist_recordings:
                    next_artist_order.append(artist_id)
            artist_order = next_artist_order
        return interleaved

    def _rotated_order(
        self,
        ranked: list[Recording],
        today: date,
        user_id: str,
        seed: str | None,
    ) -> list[Recording]:
        if not ranked:
            return []
        if seed:
            offset = int(self._stable_random(user_id, today.isoformat(), seed, "rotation") * len(ranked))
        else:
            offset = today.toordinal() % len(ranked)
        return ranked[offset:] + ranked[:offset]

    def _personal_score(self, recording: Recording, artist, profile: dict) -> float:
        if not profile:
            return 0.5
        score = 0.0
        if artist.id in profile.get("favorite_artists", set()):
            score += 0.35
        score += 0.40 * self._set_overlap(recording.tags, profile.get("favorite_tags", set()))
        score += 0.25 * self._set_overlap(recording.moods, profile.get("favorite_moods", set()))
        return min(1.0, score)

    def _preferred_candidates(
        self,
        candidates: list[Recording],
        tag: str | None = None,
        mood: str | None = None,
    ) -> list[Recording]:
        if not tag and not mood:
            return candidates

        def matches(recording: Recording) -> bool:
            tag_ok = not tag or tag in recording.tags
            mood_ok = not mood or mood in recording.moods
            return tag_ok and mood_ok

        preferred = [recording for recording in candidates if matches(recording)]
        return preferred or candidates

    def _profile_for(self, user_id: str, tag: str | None = None, mood: str | None = None) -> dict:
        base = USER_PROFILES.get(user_id, {})
        profile = {
            "favorite_tags": set(base.get("favorite_tags", set())),
            "favorite_moods": set(base.get("favorite_moods", set())),
            "favorite_artists": set(base.get("favorite_artists", set())),
            "history": list(base.get("history", [])),
        }
        if tag:
            profile["favorite_tags"].add(tag)
        if mood:
            profile["favorite_moods"].add(mood)
        return profile

    def _content_score(self, recording: Recording) -> float:
        return min(1.0, len(recording.tags) / 5) * 0.65 + min(1.0, len(recording.moods) / 3) * 0.35

    def _freshness_score(self, recording: Recording) -> float:
        if recording.year is None:
            return 0.4
        if recording.year >= 2020:
            return 1.0
        if recording.year >= 2015:
            return 0.85
        if recording.year >= 2008:
            return 0.75
        if recording.year >= 2000:
            return 0.70
        if recording.year >= 1990:
            return 0.60
        return 0.50

    def _diversity_score(self, recording: Recording, profile: dict) -> float:
        history = profile.get("history", []) if profile else []
        if not history:
            return 1.0
        tag_counter = Counter()
        for recording_id in history[-10:]:
            history_recording = self.store.recordings.get(recording_id)
            if history_recording:
                tag_counter.update(history_recording.tags)
        overlap = sum(tag_counter.get(tag, 0) for tag in recording.tags)
        return 1.0 - min(1.0, overlap / 20)

    def _exploration_score(self, recording: Recording, user_id: str, today: date, seed: str | None) -> float:
        salt = seed or "default"
        return self._stable_random(recording.id, user_id, salt)

    def _similarity(self, left: Recording, right: Recording) -> float:
        tag_score = self._set_overlap(left.tags, right.tags)
        mood_score = self._set_overlap(left.moods, right.moods)
        era_score = 1.0 - min(abs((left.year or 0) - (right.year or 0)), 20) / 20
        return tag_score * 0.55 + mood_score * 0.25 + era_score * 0.20

    def _era_reason(self, year: int) -> str:
        if year >= 2020:
            return f"{year} 年新作，适合作为近年华语流行入口。"
        if year >= 2010:
            return f"{year} 年作品，连接流媒体时代的华语流行。"
        if year >= 2000:
            return f"{year} 年作品，来自千禧年前后的华语黄金期。"
        return f"{year} 年经典作品，适合作为华语乐坛脉络回听。"

    def _set_overlap(self, values, target) -> float:
        if not values or not target:
            return 0.0
        left = set(values)
        right = set(target)
        return len(left & right) / len(left | right)

    def _stable_random(self, *parts: str) -> float:
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return int(digest[:8], 16) / 0xFFFFFFFF
