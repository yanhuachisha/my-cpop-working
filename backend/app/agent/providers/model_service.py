from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx

from app.agent.context_budget import ConservativeTokenCounter


class ModelServiceClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = (base_url or os.getenv("MODEL_SERVICE_URL", "http://localhost:8010")).rstrip("/")
        self.timeout = timeout

    def classify_intent(self, query: str, recent_messages: list[dict[str, str]] | None = None) -> dict[str, Any]:
        payload = {"query": query, "recent_messages": recent_messages or []}
        try:
            return self._post("/v1/intent/classify", payload)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return self._fallback_intent(query)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            result = self._post("/v1/embeddings", {"texts": texts})
            vectors = result["data"]
            if len(vectors) != len(texts) or any(len(item["embedding"]) != 1024 for item in vectors):
                raise ValueError("model service returned invalid BGE-M3 dimensions")
            return [item["embedding"] for item in vectors]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return [self._hash_embedding(text) for text in texts]

    def extract_memory(self, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        try:
            return list(self._post("/v1/memory/extract", {"messages": messages}).get("memories", []))
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return []

    def summarize(self, previous: str, messages: list[dict[str, str]]) -> str:
        try:
            return str(self._post("/v1/summarize", {"previous": previous, "messages": messages})["summary"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            additions = " ".join(f"{item['role']}: {item['content']}" for item in messages)
            return " ".join((previous, additions)).strip()[-8_000:]

    def count(self, text: str) -> int:
        try:
            return int(self._post("/v1/tokenize", {"text": text})["tokens"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return ConservativeTokenCounter().count(text)

    def health(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.base_url}/health")
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError):
            return {"status": "degraded", "service": "model-service"}

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _fallback_intent(query: str) -> dict[str, Any]:
        intent = "chat"
        needs_rag = False
        needs_memory = False
        if any(token in query for token in ("推荐", "歌单", "想听")):
            intent = "recommendation"
        elif any(token in query for token in ("听了多久", "听歌历史", "排行", "周报")):
            intent = "listening_history"
        elif any(token in query for token in ("偏好", "记得我", "了解我")):
            intent, needs_memory = "preference_query", True
        elif any(token in query for token in ("为什么", "资料", "知识", "解释")):
            intent, needs_rag = "rag_qa", True
        return {
            "intent": intent,
            "confidence": 0.5,
            "entities": [],
            "slots": {},
            "needs_rag": needs_rag,
            "needs_memory": needs_memory,
            "needs_tool": intent not in {"chat", "rag_qa"},
            "memory_worthy": any(token in query for token in ("我喜欢", "我不喜欢", "记住")),
            "risk_level": "low",
            "degraded": True,
        }

    @staticmethod
    def _hash_embedding(text: str) -> list[float]:
        vector = [0.0] * 1024
        for index, token in enumerate(text):
            digest = hashlib.sha256(f"{index}:{token}".encode()).digest()
            position = int.from_bytes(digest[:4], "big") % len(vector)
            vector[position] += -1.0 if digest[4] & 1 else 1.0
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]
