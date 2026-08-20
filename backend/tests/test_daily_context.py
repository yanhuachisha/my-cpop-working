import httpx

from app import daily_context


def test_music_news_filters_sina_and_marks_video(monkeypatch):
    daily_context._news_cache.value = None
    daily_context._news_cache.expires_at = 0
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
      <item>
        <title>华语歌手新舞台视频上线</title>
        <link>https://video.example.com/music</link>
        <pubDate>Mon, 17 Aug 2026 12:00:00 GMT</pubDate>
        <source>腾讯视频</source>
      </item>
      <item>
        <title>华语乐坛新歌观察</title>
        <link>https://k.sina.com.cn/music</link>
        <pubDate>Mon, 17 Aug 2026 13:00:00 GMT</pubDate>
        <source>新浪网</source>
      </item>
      <item>
        <title>独立音乐人发布新专辑</title>
        <link>https://music.example.com/article</link>
        <pubDate>Mon, 17 Aug 2026 14:00:00 GMT</pubDate>
        <source>音乐先声</source>
      </item>
    </channel></rss>
    """

    class FakeResponse:
        text = rss

        def raise_for_status(self):
            return None

    monkeypatch.setattr(daily_context.httpx, "get", lambda *_, **__: FakeResponse())

    news = daily_context.get_music_news(limit=6)

    assert [item["publisher"] for item in news] == ["腾讯视频", "音乐先声"]
    assert [item["content_type"] for item in news] == ["video", "text"]


def test_weather_uses_default_location_when_ip_services_fail(monkeypatch):
    daily_context._weather_cache.value = None
    daily_context._weather_cache.expires_at = 0
    monkeypatch.setenv("WEATHER_CITY", "测试城市")
    monkeypatch.setenv("WEATHER_LATITUDE", "30.0")
    monkeypatch.setenv("WEATHER_LONGITUDE", "120.0")

    def fake_get(url, params=None, **kwargs):
        request = httpx.Request("GET", url)
        if "open-meteo.com" in url:
            assert params["latitude"] == 30.0
            assert params["longitude"] == 120.0

            class WeatherResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {
                        "current": {
                            "weather_code": 1,
                            "temperature_2m": 24,
                            "apparent_temperature": 25,
                            "relative_humidity_2m": 60,
                            "wind_speed_10m": 5,
                            "is_day": 1,
                        }
                    }

            return WeatherResponse()
        raise httpx.ConnectError("ip service unavailable", request=request)

    monkeypatch.setattr(daily_context.httpx, "get", fake_get)

    weather = daily_context.get_weather()

    assert weather["available"] is True
    assert weather["city"] == "测试城市"
    assert weather["temperature"] == 24
    assert weather["source"] == "Open-Meteo + fallback-default-location"


def test_music_news_deduplicates_same_item(monkeypatch):
    daily_context._news_cache.value = None
    daily_context._news_cache.expires_at = 0
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
      <item>
        <title>华语歌手新舞台视频上线</title>
        <link>https://video.example.com/music</link>
        <pubDate>Mon, 17 Aug 2026 12:00:00 GMT</pubDate>
        <source>腾讯视频</source>
      </item>
      <item>
        <title>华语歌手新舞台视频上线</title>
        <link>https://video.example.com/music</link>
        <pubDate>Mon, 17 Aug 2026 12:30:00 GMT</pubDate>
        <source>腾讯视频</source>
      </item>
      <item>
        <title>独立音乐人发布新专辑</title>
        <link>https://music.example.com/article</link>
        <pubDate>Mon, 17 Aug 2026 14:00:00 GMT</pubDate>
        <source>音乐先锋</source>
      </item>
    </channel></rss>
    """

    class FakeResponse:
        text = rss

        def raise_for_status(self):
            return None

    monkeypatch.setattr(daily_context.httpx, "get", lambda *_, **__: FakeResponse())

    news = daily_context.get_music_news(limit=6)

    assert [item["title"] for item in news] == ["华语歌手新舞台视频上线", "独立音乐人发布新专辑"]


def test_music_news_deduplicates_same_event_with_rewritten_titles(monkeypatch):
    daily_context._news_cache.value = None
    daily_context._news_cache.expires_at = 0
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
      <item>
        <title>「因乐心动」第七年：TMEA依旧最懂乐迷 - DoNews</title>
        <link>https://example.com/tmea-one</link>
        <source>DoNews</source>
      </item>
      <item>
        <title>第七届TMEA盛典落幕：「Tap to Music 因乐心动」留下年度记忆 - SmartHey</title>
        <link>https://example.com/tmea-two</link>
        <source>SmartHey</source>
      </item>
      <item>
        <title>独立音乐人发布全新专辑</title>
        <link>https://example.com/new-album</link>
        <source>音乐先锋</source>
      </item>
    </channel></rss>
    """

    class FakeResponse:
        text = rss

        def raise_for_status(self):
            return None

    monkeypatch.setattr(daily_context.httpx, "get", lambda *_, **__: FakeResponse())

    news = daily_context.get_music_news(limit=6)

    assert len(news) == 2
    assert news[0]["story_key"] in {"tmea", "因乐心动"}
    assert news[1]["title"] == "独立音乐人发布全新专辑"
