from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.agent.context_budget import ContextItem
from app.agent.providers.model_service import ModelServiceClient


@dataclass(frozen=True, slots=True)
class RetrievalScope:
    tenant_id: str
    user_id: str
    permissions: frozenset[str] = frozenset()


@dataclass(slots=True)
class RetrievalBundle:
    knowledge: list[ContextItem]
    memories: list[ContextItem]
    citations: list[dict[str, Any]]
    degraded: list[str]


class ElasticsearchHybridRetriever:
    INDEXES = {
        "knowledge": "rag_knowledge_current",
        "memory": "agent_memory_current",
        "catalog": "music_catalog_current",
    }

    def __init__(self, client: Any, model_client: ModelServiceClient | None = None, rrf_k: int = 60) -> None:
        self.client = client
        self.model_client = model_client or ModelServiceClient()
        self.rrf_k = rrf_k

    @classmethod
    def from_env(cls) -> "ElasticsearchHybridRetriever":
        from elasticsearch import Elasticsearch

        return cls(Elasticsearch(os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")))

    def retrieve(
        self,
        query: str,
        scope: RetrievalScope,
        *,
        include_knowledge: bool = True,
        include_memory: bool = True,
        limit: int = 5,
    ) -> RetrievalBundle:
        vector = self.model_client.embed([query])[0]
        candidates: list[dict[str, Any]] = []
        degraded: list[str] = []
        targets = []
        if include_knowledge:
            targets.append(("knowledge", 1.0, 30))
        if include_memory:
            targets.append(("memory", 1.1, 20))
        for kind, weight, size in targets:
            try:
                candidates.extend(self._search_kind(kind, query, vector, scope, weight, size))
            except Exception:  # infrastructure failures are surfaced as degradation, never fabricated
                degraded.append(f"elasticsearch:{kind}")
        fused = self._rrf(candidates)
        ranked = sorted(fused.values(), key=lambda item: item["rrf_score"], reverse=True)
        selected = self._rerank(self._deduplicate(ranked), limit)
        knowledge, memories, citations = [], [], []
        for item in selected:
            context = ContextItem(
                content=item["content"],
                score=item["rrf_score"],
                item_id=item["id"],
                metadata=item,
            )
            (memories if item["kind"] == "memory" else knowledge).append(context)
            citations.append({
                "id": item["id"],
                "title": item.get("title", ""),
                "source_url": item.get("source_url", ""),
                "score": round(item["rrf_score"], 6),
            })
        return RetrievalBundle(knowledge, memories, citations, list(dict.fromkeys(degraded)))

    def _search_kind(
        self,
        kind: str,
        query: str,
        vector: list[float],
        scope: RetrievalScope,
        weight: float,
        size: int,
    ) -> list[dict[str, Any]]:
        index = self.INDEXES[kind]
        permission_filter = self._permission_filter(kind, scope)
        bm25 = self.client.search(
            index=index,
            size=size,
            query={
                "bool": {
                    "must": [{"multi_match": {"query": query, "fields": ["title^2", "content"]}}],
                    "filter": permission_filter,
                }
            },
        )
        knn = self.client.search(
            index=index,
            size=size,
            knn={
                "field": "embedding",
                "query_vector": vector,
                "k": size,
                "num_candidates": max(100, size * 5),
                "filter": {"bool": {"filter": permission_filter}},
            },
        )
        results = []
        for channel, response in (("bm25", bm25), ("knn", knn)):
            for rank, hit in enumerate(response.get("hits", {}).get("hits", []), 1):
                source = hit.get("_source", {})
                results.append({
                    "id": hit["_id"],
                    "kind": kind,
                    "channel": channel,
                    "rank": rank,
                    "weight": weight,
                    "title": source.get("title", ""),
                    "content": source.get("content", ""),
                    "source_url": source.get("source_url", ""),
                    "authority": float(source.get("authority", 0.5)),
                    "freshness": self._freshness(source.get("updated_at")),
                })
        return results

    @staticmethod
    def _permission_filter(kind: str, scope: RetrievalScope) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = [{"term": {"tenant_id": scope.tenant_id}}]
        if kind == "memory":
            filters.append({"term": {"user_id": scope.user_id}})
        else:
            filters.append({
                "terms": {"required_permission": sorted(scope.permissions) or ["__none__"]}
            })
            filters.append({
                "bool": {
                    "should": [
                        {"term": {"visibility": "public"}},
                        {"term": {"visibility": "tenant"}},
                        {"term": {"owner_user_id": scope.user_id}},
                        {"term": {"acl_user_ids": scope.user_id}},
                        {"terms": {"acl_permissions": sorted(scope.permissions) or ["__none__"]}},
                    ],
                    "minimum_should_match": 1,
                }
            })
        return filters

    def _rrf(self, candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        fused: dict[str, dict[str, Any]] = {}
        for item in candidates:
            current = fused.setdefault(item["id"], {**item, "rrf_score": 0.0, "channels": []})
            current["rrf_score"] += item["weight"] / (self.rrf_k + item["rank"])
            current["channels"].append(item["channel"])
        return fused

    @staticmethod
    def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected, seen = [], set()
        for item in items:
            fingerprint = " ".join(str(item["content"]).casefold().split())[:500]
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            selected.append(item)
        return selected

    @classmethod
    def _rerank(cls, items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        pool = list(items)
        selected: list[dict[str, Any]] = []
        while pool and len(selected) < limit:
            def score(item: dict[str, Any]) -> float:
                authority = max(0.0, min(1.0, float(item.get("authority", 0.5))))
                freshness = max(0.0, min(1.0, float(item.get("freshness", 0.5))))
                base = item["rrf_score"] * (0.75 + 0.15 * authority + 0.10 * freshness)
                similarity = max(
                    (cls._content_similarity(item["content"], chosen["content"]) for chosen in selected),
                    default=0.0,
                )
                return base - item["rrf_score"] * 0.20 * similarity

            best = max(pool, key=score)
            best["rank_score"] = score(best)
            selected.append(best)
            pool.remove(best)
        return selected

    @staticmethod
    def _content_similarity(left: str, right: str) -> float:
        left_terms = {left[index:index + 2] for index in range(max(0, len(left) - 1))}
        right_terms = {right[index:index + 2] for index in range(max(0, len(right) - 1))}
        return len(left_terms & right_terms) / max(1, len(left_terms | right_terms))

    @staticmethod
    def _freshness(value: Any) -> float:
        if not value:
            return 0.5
        try:
            updated = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            age_days = max(0.0, (datetime.now(UTC) - updated).total_seconds() / 86_400)
            return 1.0 / (1.0 + age_days / 365.0)
        except (TypeError, ValueError):
            return 0.5
