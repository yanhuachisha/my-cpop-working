from app.data_store import get_store
from app.hybrid_recommender import HybridRecommender
from app.kg_algorithms import KnowledgeGraphAlgorithms
from app.recommender import USER_PROFILES


def test_hybrid_recommender_combines_resume_grade_algorithms():
    payload = HybridRecommender(get_store()).recommend(limit=5, seed="test")
    assert payload["algorithm"] == "two-stage-multi-recall-bpr-itemcf-kg-mmr-thompson"
    assert len(payload["items"]) == 5
    assert set(payload["items"][0]["breakdown"]) == {
        "content_similarity", "itemcf", "bpr_pairwise", "kg_pagerank",
        "context", "popularity", "freshness", "thompson", "artist_exploration",
    }
    assert payload["items"][0]["recall_channels"]
    assert len({item["recording"]["id"] for item in payload["items"]}) == 5


def test_recommendation_evaluation_reports_diversity():
    metrics = HybridRecommender(get_store()).evaluate(limit=5)
    assert 0 <= metrics["intra_list_diversity"] <= 1
    assert metrics["artist_coverage"] >= 1


def test_kg_algorithms_support_pagerank_and_link_prediction():
    algorithms = KnowledgeGraphAlgorithms(get_store())
    ranks = algorithms.personalized_pagerank(["jay-chou"])
    predictions = algorithms.adamic_adar(5)
    assert ranks
    assert predictions
    assert algorithms.stats()["node_count"] >= 10


def test_default_profile_has_no_fixed_artist_preference():
    assert USER_PROFILES["demo"]["favorite_artists"] == set()


def test_pagerank_without_valid_seed_uses_neutral_teleport():
    algorithms = KnowledgeGraphAlgorithms(get_store())
    ranks = algorithms.personalized_pagerank(["missing-artist"])
    assert len(ranks) == algorithms.stats()["node_count"]
