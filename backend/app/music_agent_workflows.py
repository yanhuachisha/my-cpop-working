from __future__ import annotations

from typing import Any, Literal

from app.data_store import DataStore
from app.hybrid_recommender import HybridRecommender
from app.listener_memory import listener_preference_profile
from app.listening_history import (
    query_listening_history,
    resolve_history_period,
)
from app.music_assistant_features import emotion_memory
from app.online_music_search import search_online_music


RecommendationMode = Literal["auto", "focus", "relax", "nostalgia", "lyrics"]
MemoryScope = Literal["recent", "long_term", "combined"]
HistoryPeriod = Literal[
    "today", "yesterday", "this_week", "last_week", "this_month",
    "last_month", "this_year", "last_year", "7d", "30d", "90d",
    "365d", "all", "custom",
]
HistoryGroup = Literal["day", "track", "artist"]
HistoryView = Literal["list", "overview"]


def search_music_workflow(store: DataStore, query: str, limit: int = 8) -> dict[str, Any]:
    """Aggregate public music sources, then deterministically fall back to local data."""
    result_limit = max(1, min(limit, 20))
    online_result = search_online_music(query, result_limit)
    if online_result["results"]:
        return online_result
    return {
        **online_result,
        "fallback": "local_catalog",
        "local_artists": [
            item.model_dump() for item in store.search_artists(query)[:result_limit]
        ],
        "local_songs": [
            item.model_dump() for item in store.search_recordings(query)[:result_limit]
        ],
    }


def recommend_music_workflow(
    store: DataStore,
    limit: int = 1,
    mode: RecommendationMode = "auto",
) -> dict[str, Any]:
    """Run the deterministic recommendation pipeline selected by Agent parameters."""
    return HybridRecommender(store).recommend(
        limit=max(1, min(limit, 10)),
        mode=mode,
    )


def query_listener_memory_workflow(
    scope: MemoryScope = "combined",
    days: int = 14,
) -> dict[str, Any]:
    """Compose recent behavioral signals and long-term preference memory."""
    memory: dict[str, Any] = {"scope": scope}
    if scope in {"recent", "combined"}:
        memory["recent"] = emotion_memory(max(1, min(days, 365)))
    if scope in {"long_term", "combined"}:
        memory["long_term"] = listener_preference_profile()
    return memory


def query_listening_history_workflow(
    period: HistoryPeriod = "7d",
    start_date: str = "",
    end_date: str = "",
    group_by: HistoryGroup = "day",
    view: HistoryView = "list",
    top_n: int = 10,
) -> dict[str, Any]:
    """Resolve natural periods and query objective listening statistics."""
    resolved_start, resolved_end = resolve_history_period(
        period,
        start_date or None,
        end_date or None,
    )
    return query_listening_history(
        start_date=resolved_start,
        end_date=resolved_end,
        group_by=group_by,
        view=view,
        top_n=top_n,
    )
