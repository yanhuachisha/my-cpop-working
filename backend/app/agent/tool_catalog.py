from __future__ import annotations

import os
from typing import Any

import httpx

from app.agent.tools import RiskLevel, ToolExecutionContext, ToolRegistry, ToolSchema, ToolType
from app.data_store import DataStore
from app.music_agent_workflows import (
    query_listener_memory_workflow,
    query_listening_history_workflow,
    recommend_music_workflow,
    search_music_workflow,
)


OBJECT_SCHEMA = {"type": "object", "additionalProperties": False}


class JavaBusinessClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("MUSIC_CORE_URL", "http://localhost:8080")).rstrip("/")

    def post(self, path: str, payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(
                f"{self.base_url}{path}",
                json=payload,
                headers={
                    "X-User-Id": context.user_id,
                    "X-Tenant-Id": context.tenant_id,
                    "X-Permissions": ",".join(sorted(context.permissions)),
                    "Idempotency-Key": context.idempotency_key,
                    "X-Trace-Id": context.trace_id,
                },
            )
            response.raise_for_status()
            return response.json()


def build_tool_registry(store: DataStore, java_client: JavaBusinessClient | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    java = java_client or JavaBusinessClient()
    registry.register(
        ToolSchema(
            name="search_music", description="Search public and local music catalogs.",
            input_schema={**OBJECT_SCHEMA, "properties": {"query": {"type": "string", "minLength": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, "required": ["query"]},
            tool_type=ToolType.READ, required_permission="music.search", timeout=10,
            result_fields=("query", "online", "results", "sources", "errors", "fallback", "local_artists", "local_songs"),
        ),
        lambda args, _ctx: search_music_workflow(store, args["query"], args.get("limit", 8)),
    )
    registry.register(
        ToolSchema(
            name="recommend_music", description="Run the deterministic hybrid recommender.",
            input_schema={**OBJECT_SCHEMA, "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 10}, "mode": {"enum": ["auto", "focus", "relax", "nostalgia", "lyrics"]}}},
            tool_type=ToolType.READ, required_permission="recommendation.read", timeout=10,
            result_fields=("algorithm", "pipeline", "items", "catalog_size", "recall_size"),
        ),
        lambda args, _ctx: recommend_music_workflow(store, args.get("limit", 1), args.get("mode", "auto")),
    )
    registry.register(
        ToolSchema(
            name="query_listener_memory", description="Read the current user's scoped memory.",
            input_schema={**OBJECT_SCHEMA, "properties": {"scope": {"enum": ["recent", "long_term", "combined"]}, "days": {"type": "integer", "minimum": 1, "maximum": 365}}},
            tool_type=ToolType.READ, required_permission="memory.read", timeout=8,
            result_fields=("scope", "recent", "long_term"),
        ),
        lambda args, _ctx: query_listener_memory_workflow(args.get("scope", "combined"), args.get("days", 14)),
    )
    registry.register(
        ToolSchema(
            name="query_listening_history", description="Read authoritative listening history.",
            input_schema={**OBJECT_SCHEMA, "properties": {
                "period": {"enum": ["today", "yesterday", "this_week", "last_week", "this_month", "last_month", "this_year", "last_year", "7d", "30d", "90d", "365d", "all", "custom"]},
                "start_date": {"type": "string"}, "end_date": {"type": "string"},
                "group_by": {"enum": ["day", "track", "artist"]}, "view": {"enum": ["list", "overview"]},
                "top_n": {"type": "integer", "minimum": 1, "maximum": 100},
            }},
            tool_type=ToolType.READ, required_permission="history.read", timeout=8,
            result_fields=(
                "start_date", "end_date", "group_by", "view", "total_seconds",
                "summary", "items", "comparison", "ranking", "trend",
            ),
        ),
        lambda args, _ctx: query_listening_history_workflow(**args),
    )
    for name, path, permission, risk, schema in (
        (
            "add_favorite", "/internal/v1/favorites", "favorite.write", RiskLevel.MEDIUM,
            {**OBJECT_SCHEMA, "properties": {"track_id": {"type": "string", "minLength": 1, "maxLength": 120}}, "required": ["track_id"]},
        ),
        (
            "update_preference", "/internal/v1/preferences", "preference.write", RiskLevel.MEDIUM,
            {**OBJECT_SCHEMA, "properties": {
                "preference_key": {"type": "string", "minLength": 1, "maxLength": 80},
                "value": {"type": "string", "minLength": 1, "maxLength": 500},
            }, "required": ["preference_key", "value"]},
        ),
        (
            "submit_feedback", "/internal/v1/feedback", "feedback.write", RiskLevel.LOW,
            {**OBJECT_SCHEMA, "properties": {
                "message": {"type": "string", "minLength": 1, "maxLength": 1000},
                "rating": {"type": "integer", "minimum": 1, "maximum": 5},
            }, "required": ["message"]},
        ),
    ):
        registry.register(
            ToolSchema(
                name=name, description=f"Authoritative business write: {name}.",
                input_schema=schema, tool_type=ToolType.WRITE,
                risk_level=risk, required_permission=permission, timeout=5,
                result_fields=("action_id", "status"),
            ),
            lambda args, ctx, endpoint=path: java.post(endpoint, args, ctx),
        )
    registry.freeze()
    return registry
