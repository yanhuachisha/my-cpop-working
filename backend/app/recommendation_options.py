from __future__ import annotations

from collections import Counter

from app.data_store import DataStore
from app.models import RecommendationOptionItem, RecommendationOptions

TAG_LABELS = {
    "r&b": "R&B",
    "chinese-style": "中国风",
    "rock": "摇滚",
    "campus": "校园",
    "ballad": "抒情",
    "band": "乐团",
    "indie": "独立",
}

MOOD_LABELS = {
    "late-night": "深夜",
    "warm": "温暖",
    "youthful": "青春",
    "dramatic": "戏剧感",
    "bittersweet": "苦甜",
    "nostalgic": "怀旧",
    "gentle": "轻柔",
}

PREFERRED_TAG_ORDER = ["r&b", "chinese-style", "rock", "campus", "ballad", "band", "indie"]
PREFERRED_MOOD_ORDER = ["late-night", "warm", "youthful", "dramatic", "bittersweet", "nostalgic", "gentle"]


def build_recommendation_options(store: DataStore, limit: int = 8) -> RecommendationOptions:
    recordings = [recording for recording in store.recordings.values() if recording.is_cpop]
    tag_counter: Counter[str] = Counter()
    mood_counter: Counter[str] = Counter()
    for recording in recordings:
        tag_counter.update(recording.tags)
        mood_counter.update(recording.moods)

    return RecommendationOptions(
        tags=_rank_options(tag_counter, TAG_LABELS, PREFERRED_TAG_ORDER, limit),
        moods=_rank_options(mood_counter, MOOD_LABELS, PREFERRED_MOOD_ORDER, limit),
    )


def _rank_options(
    counter: Counter[str],
    labels: dict[str, str],
    preferred_order: list[str],
    limit: int,
) -> list[RecommendationOptionItem]:
    preferred = [value for value in preferred_order if value in counter]
    remaining = sorted(
        [value for value in counter if value not in preferred],
        key=lambda value: (-counter[value], value),
    )
    values = [*preferred, *remaining][:limit]
    return [
        RecommendationOptionItem(
            value=value,
            label=labels.get(value, value),
            count=counter[value],
        )
        for value in values
    ]
