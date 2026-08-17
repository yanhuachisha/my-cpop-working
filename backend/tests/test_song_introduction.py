from app import song_introduction


def test_verified_catalog_data_still_gets_song_specific_ai_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(song_introduction, "CACHE_PATH", tmp_path / "song_introductions.json")
    monkeypatch.setattr(song_introduction, "_itunes_metadata", lambda title, artist: {
        "artist": artist,
        "album": "测试专辑",
        "year": 2026,
        "genre": "国语流行",
        "source_url": "https://example.com/song",
    })
    calls = []
    monkeypatch.setattr(song_introduction, "_model_introduction", lambda title, artist, facts: calls.append((title, artist, facts)) or {
        "subtitle": "只属于这首歌的标题",
        "narrative": "只属于这首歌的简介。",
        "themes": ["夜色"],
        "listening_points": ["听开场音色", "听副歌推进", "听结尾留白"],
    })

    result = song_introduction.song_introduction("测试歌曲", "测试歌手")

    assert calls[0][0:2] == ("测试歌曲", "测试歌手")
    assert result["narrative"] == "只属于这首歌的简介。"
    assert result["schema_version"] == 3


def test_only_current_song_introduction_cache_is_retained(monkeypatch, tmp_path):
    cache_path = tmp_path / "song_introductions.json"
    monkeypatch.setattr(song_introduction, "CACHE_PATH", cache_path)
    first_key = song_introduction._cache_key("歌曲甲", "歌手甲")
    second_key = song_introduction._cache_key("歌曲乙", "歌手乙")
    song_introduction._write_cache({first_key: {"title": "甲"}, second_key: {"title": "乙"}})

    song_introduction.retain_current_song_cache("歌曲乙", "歌手乙")

    assert song_introduction._read_cache() == {second_key: {"title": "乙"}}
