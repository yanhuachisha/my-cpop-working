from app.agent.retrieval import ElasticsearchHybridRetriever, RetrievalScope


class FakeModel:
    def embed(self, texts):
        return [[0.0] * 1024 for _ in texts]


class FakeElasticsearch:
    def __init__(self):
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        channel = "knn" if "knn" in kwargs else "bm25"
        kind = "memory" if kwargs["index"] == "agent_memory_current" else "knowledge"
        return {"hits": {"hits": [{
            "_id": f"{kind}-{channel}",
            "_source": {"title": kind, "content": f"{kind} {channel}", "authority": 0.8},
        }]}}


def flatten_terms(value):
    if isinstance(value, dict):
        return [*value.keys(), *[item for child in value.values() for item in flatten_terms(child)]]
    if isinstance(value, list):
        return [item for child in value for item in flatten_terms(child)]
    return []


def test_permissions_are_hard_filters_before_bm25_knn_and_rrf():
    client = FakeElasticsearch()
    retriever = ElasticsearchHybridRetriever(client, FakeModel())
    result = retriever.retrieve(
        "周杰伦的音乐偏好",
        RetrievalScope("tenant-a", "user-a", frozenset({"knowledge.read"})),
        include_knowledge=True,
        include_memory=True,
        limit=10,
    )

    assert len(client.calls) == 4
    for call in client.calls:
        if "knn" in call:
            filters = call["knn"]["filter"]
        else:
            filters = call["query"]["bool"]["filter"]
        terms = flatten_terms(filters)
        assert "tenant_id" in terms
        if call["index"] == "agent_memory_current":
            assert "user_id" in terms
        else:
            assert {
                "required_permission", "visibility", "owner_user_id",
                "acl_user_ids", "acl_permissions",
            }.issubset(terms)
    assert len(result.knowledge) == 2
    assert len(result.memories) == 2


def test_rrf_combines_channels_without_using_permission_as_score():
    retriever = ElasticsearchHybridRetriever(FakeElasticsearch(), FakeModel(), rrf_k=60)
    fused = retriever._rrf([
        {"id": "same", "rank": 1, "weight": 1.0, "channel": "bm25", "authority": 0.5, "content": "x", "kind": "knowledge"},
        {"id": "same", "rank": 2, "weight": 1.0, "channel": "knn", "authority": 0.5, "content": "x", "kind": "knowledge"},
    ])
    assert fused["same"]["rrf_score"] == 1 / 61 + 1 / 62
    assert "permission" not in fused["same"]
