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


def test_daily_new_world_uses_daily_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "new_world.json"
    monkeypatch.setattr(new_world, "CACHE_PATH", cache_path)
    monkeypatch.setattr(new_world, "_github_projects", lambda client, today: [{"name": "repo"}])
    monkeypatch.setattr(new_world, "_ai_news", lambda client: [{"title": "news"}])
    first = new_world.daily_new_world(force=True)
    second = new_world.daily_new_world()
    assert first == second
    assert cache_path.exists()
