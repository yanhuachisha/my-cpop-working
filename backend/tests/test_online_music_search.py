import httpx

from app.online_music_search import search_online_music


def test_online_music_search_merges_and_deduplicates_sources():
    def handler(request: httpx.Request) -> httpx.Response:
        if "itunes.apple.com" in str(request.url):
            return httpx.Response(200, json={
                "results": [{
                    "trackId": 1,
                    "trackName": "晴天",
                    "artistName": "周杰伦",
                    "collectionName": "叶惠美",
                    "releaseDate": "2003-07-31T00:00:00Z",
                    "primaryGenreName": "Mandopop",
                    "previewUrl": "https://audio.example/preview.m4a",
                    "trackViewUrl": "https://music.example/song/1",
                }]
            })
        return httpx.Response(200, json={
            "recordings": [
                {
                    "id": "mb-1",
                    "title": "晴天",
                    "artist-credit": [{"name": "周杰伦"}],
                    "first-release-date": "2003-07-31",
                    "releases": [{"title": "叶惠美"}],
                    "score": 100,
                },
                {
                    "id": "mb-2",
                    "title": "七里香",
                    "artist-credit": [{"name": "周杰伦"}],
                    "first-release-date": "2004-08-03",
                    "releases": [{"title": "七里香"}],
                    "score": 98,
                },
            ]
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search_online_music("周杰伦", client=client)

    assert result["online"] is True
    assert len(result["results"]) == 2
    assert result["results"][0]["source"] == "Apple iTunes Search API"
    assert result["results"][1]["source"] == "MusicBrainz"
    assert len(result["sources"]) == 2


def test_online_music_search_reports_network_failures():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search_online_music("陶喆", client=client)

    assert result["online"] is False
    assert result["results"] == []
    assert len(result["errors"]) == 2
