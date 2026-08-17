from app import song_introduction


def test_verified_catalog_data_still_gets_song_specific_ai_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(song_introduction, "CACHE_PATH", tmp_path / "song_introductions.json")
    calls = []
    monkeypatch.setattr(song_introduction, "generate_song_portrait", lambda title, artist, album, year, search: calls.append((title, artist, album, year)) or {
        "subtitle": "笑声落下之后",
        "narrative": "它把看似轻松的表面慢慢翻开，让没有说出口的疲惫在旋律里获得重量。情绪并不突然崩塌，而是在一次次克制中显出裂缝。",
        "themes": ["夜色"],
        "listening_points": ["听开场音色", "听副歌推进", "听结尾留白"],
        "verified": {
            "artist": artist,
            "album": "测试专辑",
            "year": 2026,
            "genre": "国语流行",
            "facts": [f"演唱：{artist}", "收录：测试专辑"],
            "source_urls": ["https://example.com/song"],
        },
        "tools_used": ["search_song_material"],
    })

    result = song_introduction.song_introduction("测试歌曲", "测试歌手")

    assert calls[0][0:2] == ("测试歌曲", "测试歌手")
    assert result["subtitle"] == "笑声落下之后"
    assert "公开资料有限" not in result["narrative"]
    assert result["tools_used"] == ["search_song_material"]
    assert result["schema_version"] == 4


def test_only_current_song_introduction_cache_is_retained(monkeypatch, tmp_path):
    cache_path = tmp_path / "song_introductions.json"
    monkeypatch.setattr(song_introduction, "CACHE_PATH", cache_path)
    first_key = song_introduction._cache_key("歌曲甲", "歌手甲")
    second_key = song_introduction._cache_key("歌曲乙", "歌手乙")
    song_introduction._write_cache({first_key: {"title": "甲"}, second_key: {"title": "乙"}})

    song_introduction.retain_current_song_cache("歌曲乙", "歌手乙")

    assert song_introduction._read_cache() == {second_key: {"title": "乙"}}


def test_emotional_fallback_uses_poetic_title_and_no_disclaimer(monkeypatch, tmp_path):
    monkeypatch.setattr(song_introduction, "CACHE_PATH", tmp_path / "song_introductions.json")
    monkeypatch.setattr(song_introduction, "generate_song_portrait", lambda *args: None)

    result = song_introduction.song_introduction("你不是真正的快乐", "五月天")

    assert result["subtitle"] == "微笑底下的裂痕"
    assert "公开资料" not in result["narrative"]
    assert "暂未找到" not in result["narrative"]
