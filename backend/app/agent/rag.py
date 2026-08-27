from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from app.agent.providers.model_service import ModelServiceClient
from app.agent.retrieval import ElasticsearchHybridRetriever, RetrievalScope


INDEX_DEFINITIONS = {
    "rag_knowledge": {
        "alias": "rag_knowledge_current",
        "properties": {
            "document_id": {"type": "keyword"},
            "chunk_id": {"type": "keyword"},
            "tenant_id": {"type": "keyword"},
            "owner_user_id": {"type": "keyword"},
            "visibility": {"type": "keyword"},
            "required_permission": {"type": "keyword"},
            "acl_user_ids": {"type": "keyword"},
            "acl_permissions": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "standard"},
            "section": {"type": "text", "analyzer": "standard"},
            "content": {"type": "text", "analyzer": "standard"},
            "source_url": {"type": "keyword", "index": False},
            "content_hash": {"type": "keyword"},
            "authority": {"type": "float"},
            "updated_at": {"type": "date"},
            "embedding": {"type": "dense_vector", "dims": 1024, "index": True, "similarity": "cosine", "index_options": {"type": "hnsw", "m": 16, "ef_construction": 100}},
        },
    },
    "agent_memory": {
        "alias": "agent_memory_current",
        "properties": {
            "memory_id": {"type": "keyword"},
            "memory_key": {"type": "keyword"},
            "memory_type": {"type": "keyword"},
            "tenant_id": {"type": "keyword"},
            "user_id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "standard"},
            "content": {"type": "text", "analyzer": "standard"},
            "authority": {"type": "float"},
            "aggregate_version": {"type": "long"},
            "embedding": {"type": "dense_vector", "dims": 1024, "index": True, "similarity": "cosine", "index_options": {"type": "hnsw", "m": 16, "ef_construction": 100}},
        },
    },
    "music_catalog": {
        "alias": "music_catalog_current",
        "properties": {
            "tenant_id": {"type": "keyword"},
            "visibility": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "standard"},
            "content": {"type": "text", "analyzer": "standard"},
            "artist": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "embedding": {"type": "dense_vector", "dims": 1024, "index": True, "similarity": "cosine"},
        },
    },
}


class RagDocument(BaseModel):
    document_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=200_000)
    source_url: HttpUrl | None = None
    section: str = ""
    tenant_id: str = "default"
    owner_user_id: str = ""
    visibility: Literal["public", "private", "tenant"] = "public"
    required_permission: str = "knowledge.read"
    acl_user_ids: list[str] = Field(default_factory=list, max_length=200)
    acl_permissions: list[str] = Field(default_factory=list, max_length=50)
    authority: float = Field(default=0.5, ge=0, le=1)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RagIngestRequest(BaseModel):
    documents: list[RagDocument] = Field(min_length=1, max_length=100)


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    user_id: str = "demo"
    tenant_id: str = "default"
    limit: int = Field(default=5, ge=1, le=20)


class SearchIndexManager:
    def __init__(self, client: Any) -> None:
        self.client = client

    @classmethod
    def from_env(cls) -> "SearchIndexManager":
        from elasticsearch import Elasticsearch

        return cls(Elasticsearch(os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")))

    def initialize(self) -> dict[str, str]:
        result = {}
        for base, definition in INDEX_DEFINITIONS.items():
            alias = definition["alias"]
            if self.client.indices.exists_alias(name=alias):
                result[base] = alias
                continue
            index = f"{base}_v1"
            if not self.client.indices.exists(index=index):
                self.client.indices.create(index=index, mappings={"dynamic": "strict", "properties": definition["properties"]})
            self.client.indices.put_alias(index=index, name=alias)
            result[base] = index
        return result


class RagService:
    def __init__(self, index_manager: SearchIndexManager | None = None, model_client: ModelServiceClient | None = None) -> None:
        self.index_manager = index_manager or SearchIndexManager.from_env()
        self.model_client = model_client or ModelServiceClient()

    def ingest(self, request: RagIngestRequest) -> dict[str, Any]:
        self.index_manager.initialize()
        chunks = [chunk for document in request.documents for chunk in self._chunks(document)]
        vectors = self.model_client.embed([item["content"] for item in chunks])
        operations = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            operations.extend(({"index": {"_index": "rag_knowledge_current", "_id": chunk["chunk_id"]}}, {**chunk, "embedding": vector}))
        response = self.index_manager.client.bulk(operations=operations, refresh="wait_for")
        return {"documents": len(request.documents), "chunks": len(chunks), "errors": bool(response.get("errors"))}

    def search(self, request: RagSearchRequest) -> dict[str, Any]:
        retriever = ElasticsearchHybridRetriever(self.index_manager.client, self.model_client)
        result = retriever.retrieve(
            request.query,
            RetrievalScope(request.tenant_id, request.user_id, frozenset({"knowledge.read"})),
            include_knowledge=True,
            include_memory=True,
            limit=request.limit,
        )
        return {
            "query": request.query,
            "knowledge": [item.metadata for item in result.knowledge],
            "memories": [item.metadata for item in result.memories],
            "citations": result.citations,
            "degraded": result.degraded,
        }

    @staticmethod
    def _chunks(document: RagDocument, size: int = 500, overlap: int = 80) -> list[dict[str, Any]]:
        content = " ".join(document.content.split())
        if not content:
            return []
        chunks = []
        start = 0
        index = 0
        while start < len(content):
            end = min(len(content), start + size)
            if end < len(content):
                boundary = max(content.rfind("。", start, end), content.rfind("\n", start, end))
                if boundary > start + size // 2:
                    end = boundary + 1
            text = content[start:end]
            chunk_id = hashlib.sha256(f"{document.document_id}:{index}:{text}".encode()).hexdigest()
            chunks.append({
                "document_id": document.document_id,
                "chunk_id": chunk_id,
                "tenant_id": document.tenant_id,
                "owner_user_id": document.owner_user_id,
                "visibility": document.visibility,
                "required_permission": document.required_permission,
                "acl_user_ids": document.acl_user_ids,
                "acl_permissions": document.acl_permissions,
                "title": document.title,
                "section": document.section,
                "content": text,
                "source_url": str(document.source_url or ""),
                "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                "authority": document.authority,
                "updated_at": document.updated_at.isoformat(),
            })
            if end >= len(content):
                break
            start = max(start + 1, end - overlap)
            index += 1
        return chunks
