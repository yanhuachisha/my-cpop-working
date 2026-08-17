from fastapi.testclient import TestClient

from app.kugou import KugouSearchRequest, _is_kugou_process_path, _parse_window_title, search_kugou
from app.playback_tracker import KugouPlaybackTracker
from app.main import app


client = TestClient(app)


def test_parse_kugou_window_title():
    assert _parse_window_title("\u5468\u6770\u4f26 - \u4e03\u91cc\u9999 - \u9177\u72d7\u97f3\u4e50") == ("\u4e03\u91cc\u9999", "\u5468\u6770\u4f26")


def test_parse_kugou_window_without_artist():
    assert _parse_window_title("\u9177\u72d7\u97f3\u4e50") == (None, None)


def test_kugou_process_filter_rejects_browser_titles():
    assert _is_kugou_process_path(r"C:\Program Files\KuGou\KuGou.exe") is True
    assert _is_kugou_process_path(r"C:\Program Files\Google\Chrome\chrome.exe") is False
    assert _is_kugou_process_path(r"C:\Program Files\nodejs\node.exe") is False


def test_kugou_search_api(monkeypatch):
    monkeypatch.setattr(
        "app.main.search_kugou",
        lambda request: {
            "opened": True,
            "searched": True,
            "query": f"{request.artist} {request.title}",
            "direct_play": False,
            "message": "ok",
        },
    )
    response = client.post("/api/kugou/search", json={"title": "七里香", "artist": "周杰伦"})
    assert response.status_code == 200
    assert response.json()["query"] == "周杰伦 七里香"


def test_kugou_search_opens_player_and_copies_query(monkeypatch):
    copied = []
    monkeypatch.setattr("app.kugou._set_clipboard_text", copied.append)
    monkeypatch.setattr(
        "app.kugou.open_kugou",
        lambda: {"opened": True, "message": "ok"},
    )

    payload = search_kugou(KugouSearchRequest(title="七里香", artist="周杰伦"))

    assert copied == ["周杰伦 七里香"]
    assert payload["opened"] is True
    assert payload["copied"] is True
    assert payload["searched"] is False


def test_playback_tracker_counts_each_continuous_play_once(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "app.playback_tracker.ensure_library_recording",
        lambda title, artist: "recording-1",
    )
    monkeypatch.setattr(
        "app.playback_tracker.record_feedback",
        lambda request: recorded.append(request) or {"total_play_count": len(recorded)},
    )
    tracker = KugouPlaybackTracker(threshold_seconds=30, poll_seconds=5)
    playing = {"is_playing": True, "title": "七里香", "artist": "周杰伦"}

    assert tracker.observe(playing, now=0) is False
    assert tracker.observe(playing, now=29) is False
    assert tracker.observe(playing, now=30) is True
    assert tracker.observe(playing, now=90) is False
    assert recorded[0].channel == "kugou-auto"

    tracker.observe({"is_playing": False}, now=100)
    assert tracker.observe(playing, now=101) is False
    assert tracker.observe(playing, now=131) is True
    assert [request.action for request in recorded] == ["play", "pause", "play"]
    assert recorded[1].listened_seconds == 100


def test_kugou_bridge_search_normalizes_metadata(monkeypatch):
    from app import kugou_bridge

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "ok": True,
                "total": 1,
                "songs": [{
                    "fileName": "七里香",
                    "singerName": "周杰伦",
                    "albumName": "七里香",
                    "hash": "HASH",
                    "duration": 299,
                }],
            }

    def fake_get(url, params, timeout):
        assert url.endswith("/api/search")
        assert params == {"keyword": "周杰伦", "page": 1}
        assert timeout == 6.0
        return FakeResponse()

    monkeypatch.setattr(kugou_bridge.httpx, "get", fake_get)
    payload = kugou_bridge.search_bridge("周杰伦")
    assert payload["ok"] is True
    assert payload["songs"][0]["title"] == "七里香"
    assert payload["songs"][0]["duration_seconds"] == 299
    assert "primaryUrl" not in payload["songs"][0]


def test_kugou_bridge_api_keeps_unavailable_service_non_fatal(monkeypatch):
    monkeypatch.setattr("app.main.bridge_status", lambda: {
        "available": False,
        "configured": False,
        "base_url": "http://127.0.0.1:9191",
        "capabilities": [],
        "blocked_capabilities": ["audio-proxy", "full-lyrics"],
        "message": "optional",
        "attribution": {"name": "Yu9191/KuGou", "repository": "repo", "license": "MIT", "role": "bridge"},
    })
    response = client.get("/api/kugou/bridge/status")
    assert response.status_code == 200
    assert response.json()["available"] is False
