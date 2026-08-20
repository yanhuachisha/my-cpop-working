from datetime import date

from app import new_world


def test_daily_rotations_return_requested_counts():
    today = date(2026, 8, 16)
    assert len(new_world._hot_links(today)) == len(new_world.HOT_SOURCES)
    assert len(new_world._learning(today)) == 10
    assert {item["category"] for item in new_world._learning(today)}


def test_learning_links_are_study_resources():
    assert not any(new_world._is_research_link(point[3]) for point in new_world.LEARNING_POINTS)


def test_cache_ignores_old_research_learning_links(monkeypatch, tmp_path):
    cache_path = tmp_path / "new_world.json"
    monkeypatch.setattr(new_world, "CACHE_PATH", cache_path)
    cache_path.write_text(
        """{"date":"2026-08-16","hot_links":[{"source":"x"}],"learning":[{"url":"https://arxiv.org/abs/1706.03762"}]}""",
        encoding="utf-8",
    )

    assert new_world._cached(date(2026, 8, 16)) is None


def test_feed_parser_reads_rss_items():
    payload = b"""<?xml version='1.0'?><rss><channel><item><title>New AI model</title><link>https://example.com/model</link><description>Agent research</description><pubDate>Sun, 16 Aug 2026 08:00:00 GMT</pubDate></item></channel></rss>"""
    items = new_world._parse_feed(payload, "Example", 2)
    assert items[0]["title"] == "New AI model"
    assert items[0]["url"] == "https://example.com/model"
    assert items[0]["score"] > 20


def test_wikipedia_hot_link_points_to_real_article():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "items": [
                    {
                        "articles": [
                            {"article": "Wikipedia:首页", "views": 100000, "rank": 1},
                            {"article": "Special:Search", "views": 90000, "rank": 2},
                            {"article": "周杰伦", "views": 12345, "rank": 3},
                        ]
                    }
                ]
            }

    class FakeClient:
        def __init__(self):
            self.urls = []

        def get(self, url):
            self.urls.append(url)
            return FakeResponse()

    client = FakeClient()
    item = new_world._wikipedia_hot_link(date(2026, 8, 19), client)

    assert client.urls == [
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/zh.wikipedia.org/all-access/2026/08/18"
    ]
    assert item["source"] == "Wikipedia"
    assert item["title"] == "维基百科热读：周杰伦"
    assert item["url"] == "https://zh.wikipedia.org/wiki/%E5%91%A8%E6%9D%B0%E4%BC%A6"
    assert "浏览" in item["summary"]


def test_daily_new_world_uses_daily_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "new_world.json"
    monkeypatch.setattr(new_world, "CACHE_PATH", cache_path)
    monkeypatch.setattr(new_world, "_github_projects", lambda client, today: [{"name": "repo"}])
    monkeypatch.setattr(new_world, "_ai_news", lambda client: [{"title": "news"}])
    first = new_world.daily_new_world(force=True)
    second = new_world.daily_new_world()
    assert first == second
    assert cache_path.exists()
