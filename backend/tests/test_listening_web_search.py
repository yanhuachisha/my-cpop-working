import httpx

from app.listening_companion_workflows import web_search_workflow


def test_web_search_workflow_searches_and_reads_pages(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "duckduckgo.com/html" in url:
            return httpx.Response(
                200,
                text=(
                    '<a class="result__a" href="https://example.com/story">歌曲故事</a>'
                    '<a class="result__snippet">采访提到这首歌写的是离别后的回望。</a>'
                ),
                headers={"content-type": "text/html"},
            )
        if "zh.wikipedia.org" in url:
            return httpx.Response(200, json={"query": {"search": []}})
        if "example.com/story" in url:
            return httpx.Response(
                200,
                text="<html><title>歌曲故事页</title><body>这首歌的创作背景来自一次公开采访。</body></html>",
                headers={"content-type": "text/html"},
            )
        raise AssertionError(f"unexpected request: {url}")

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        result = web_search_workflow("歌曲 创作故事", "示例歌曲", "示例歌手", client=client)

    assert result["available"] is True
    assert result["documents"][0]["title"] == "歌曲故事页"
    assert "离别后的回望" in result["facts"][0]
    assert result["sources"][0]["url"] == "https://example.com/story"
