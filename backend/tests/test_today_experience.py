import json
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.data_store import get_store
from app.main import app
from app.library_import import _normalize_entry, _parse_entries, _split_line
from app.listener_memory import recent_exposed_recording_ids, record_recommendation_exposure
from app.today_recommender import TodayRecommender


client = TestClient(app)


def test_open_catalog_expands_candidate_pool():
    get_store.cache_clear()
    assert len(get_store().recordings) >= 80


def test_today_recommendations_are_distinct(monkeypatch, tmp_path):
    from app import listener_memory

    monkeypatch.setattr(listener_memory, "STATE_PATH", tmp_path / "listener_state.json")
    monkeypatch.setattr("app.today_recommender.get_weather", lambda: {
        "available": True, "city": "Shanghai", "condition": "rain", "kind": "rain",
        "music_moods": ["late-night", "bittersweet"], "temperature": 24, "is_day": False,
    })
    monkeypatch.setattr("app.today_recommender.get_music_news", lambda: [])
    experience = TodayRecommender(get_store()).build(session_seed="test")
    assert len(experience.picks) == 1
    assert any(source.name == "Apple iTunes Search API" for source in experience.sources)


def test_today_recommendation_is_stable_for_the_whole_day(monkeypatch, tmp_path):
    from app import listener_memory, today_recommender

    monkeypatch.setattr(listener_memory, "STATE_PATH", tmp_path / "listener_state.json")
    monkeypatch.setattr(today_recommender, "get_weather", lambda: {
        "available": True, "city": "Shanghai", "condition": "晴",
        "kind": "clear", "music_moods": ["warm"], "temperature": 29, "is_day": True,
    })
    monkeypatch.setattr(today_recommender, "get_music_news", lambda: [])

    recommender = TodayRecommender(get_store())
    first = recommender.build(session_seed="morning").picks[0].recording.id
    second = recommender.build(session_seed="evening").picks[0].recording.id
    assert first == second


def test_recommendation_exposure_is_stable_today_and_avoids_previous_days(monkeypatch, tmp_path):
    from app import listener_memory

    state_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)
    record_recommendation_exposure(["song-today"], mode="auto")
    assert recent_exposed_recording_ids() == set()

    state = listener_memory.load_state()
    state["events"][0]["shown_on"] = (date.today() - timedelta(days=1)).isoformat()
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert recent_exposed_recording_ids() == {"song-today"}


def test_today_avoids_previous_day_exposures(monkeypatch, tmp_path):
    from app import listener_memory, today_recommender

    state_path = tmp_path / "listener_state.json"
    monkeypatch.setattr(listener_memory, "STATE_PATH", state_path)
    monkeypatch.setattr(today_recommender, "get_weather", lambda: {
        "available": True,
        "city": "Shanghai",
        "condition": "晴",
        "kind": "clear",
        "music_moods": ["warm"],
        "temperature": 29,
        "is_day": True,
    })
    monkeypatch.setattr(today_recommender, "get_music_news", lambda: [])

    recommender = TodayRecommender(get_store())
    first = recommender.build(session_seed="dedupe")
    first_ids = {pick.recording.id for pick in first.picks}
    state = listener_memory.load_state()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    for event in state["events"]:
        event["shown_on"] = yesterday
    state_path.write_text(json.dumps(state), encoding="utf-8")

    second = recommender.build(session_seed="dedupe")
    assert first_ids.isdisjoint({pick.recording.id for pick in second.picks})


def test_kugou_text_parser_supports_common_export_lines():
    assert _split_line("七里香 - 周杰伦", "title_artist") == ("七里香", "周杰伦")
    assert _split_line("周杰伦\t七里香", "artist_title") == ("七里香", "周杰伦")


def test_today_lyrics_and_library_api(monkeypatch, tmp_path):
    from app import library_import, listener_memory, today_recommender

    monkeypatch.setattr(listener_memory, "STATE_PATH", tmp_path / "listener_state.json")
    monkeypatch.setattr(library_import, "LIBRARY_PATH", tmp_path / "user_library.json")
    monkeypatch.setattr(today_recommender, "get_weather", lambda: {
        "available": True,
        "city": "Hangzhou",
        "condition": "多云",
        "kind": "cloud",
        "music_moods": ["warm"],
        "temperature": 27,
        "is_day": True,
    })
    monkeypatch.setattr(today_recommender, "get_music_news", lambda: [])

    today_response = client.get("/api/today?seed=api-test&mode=lyrics")
    assert today_response.status_code == 200
    assert len(today_response.json()["picks"]) == 1

    lyric_response = client.post("/api/listener/lyrics", json={
        "excerpt": "最美的不是下雨天",
        "song_title": "不能说的秘密",
        "artist": "周杰伦",
        "note": "喜欢它的画面感",
    })
    assert lyric_response.status_code == 200
    assert client.get("/api/listener/lyrics").json()[0]["song_title"] == "不能说的秘密"

    note_response = client.post("/api/listener/notes", json={
        "content": "这一遍最先听见的是雨声里的怀念。",
        "prompt": "这首歌让你想起了什么？",
        "song_title": "七里香",
        "artist": "周杰伦",
        "album": "七里香",
    })
    assert note_response.status_code == 200
    saved_notes = client.get("/api/listener/notes").json()
    assert saved_notes[0]["song_title"] == "七里香"
    assert "雨声" in saved_notes[0]["content"]

    import_response = client.post("/api/library/import", json={
        "text": "七里香 - 周杰伦\n小情歌 - 苏打绿",
        "order": "title_artist",
        "playlist_name": "我的酷狗收藏",
    })
    assert import_response.status_code == 200
    collection = client.get("/api/library/collection").json()
    assert collection["playlists"][0]["name"] == "我的酷狗收藏"
    assert collection["playlists"][0]["songs"][0]["title"] == "七里香"
    assert import_response.status_code == 200
    assert import_response.json()["imported"] == 2
    assert library_import.LIBRARY_PATH.exists()


def test_library_parser_supports_kugou_csv_export():
    text = '"title","artist","album","duration"\n"Jay Chou - Qilixiang.mp3","Jay Chou","Qilixiang","4:59"'
    assert _parse_entries(text, "auto") == [("Qilixiang", "Jay Chou")]


def test_library_parser_repairs_embedded_csv_and_mojibake():
    title = "\u7231 \u90fd\u662f\u5bf9\u7684"
    artist = "\u80e1\u590f"
    album = "\u80e1 \u7231\u590f"
    broken_title = title.encode("utf-8").decode("latin1")
    broken_artist = artist.encode("utf-8").decode("latin1")
    broken_album = album.encode("utf-8").decode("latin1")
    pasted = f'{broken_title}.mp3","{broken_artist}","{broken_album}","4:20"'

    assert _normalize_entry(pasted, broken_artist) == (title, artist)


def test_library_parser_repairs_gbk_mojibake():
    title = "\u6800\u5b50\u82b1\u53c8\u5f00"
    artist = "\u5218\u60dc\u541b"
    broken_title = title.encode("gbk").decode("latin1")
    broken_artist = artist.encode("gbk").decode("latin1")

    assert _normalize_entry(f'{broken_title}.mp3","{broken_artist}","album","4:28"', broken_artist) == (title, artist)


def test_library_parser_repairs_embedded_csv_in_artist_field():
    title = "\u7bc7\u7ae0"
    artist = "\u5f20\u97f6\u6db5\u3001\u738b\u8d6b\u91ce"
    embedded = f'{title}.mp3","{artist}","{title}","4:08"'

    assert _normalize_entry(artist, embedded) == (title, artist)
