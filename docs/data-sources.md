# 数据源与许可证

本项目只使用开放数据、公开 API 和用户自行授权的数据。

## MusicBrainz

- 用途：artist、recording、release、work、relation、tag、external id。
- License：核心数据 CC0。
- 文档：https://musicbrainz.org/doc/About/Data_License
- API：https://musicbrainz.org/doc/MusicBrainz_API
- 同步：
  ```powershell
  python scripts\sync_open_data.py --source musicbrainz
  ```
  该命令会生成 `data/snapshots/musicbrainz_seed_artists.json`，用于审查种子艺人的 MusicBrainz MBID、别名、标签、URL 关系和 release group。若 seed 中已有 MBID 失效，会 fallback 到名称搜索并记录候选。

## ListenBrainz

- 用途：开放听歌行为、趋势、推荐候选、用户授权后的听歌画像。
- License：公开 listen 数据和 dumps 以官方说明为准，项目只消费开放 dumps/API。
- 数据：https://listenbrainz.org/data/
- API：https://listenbrainz.readthedocs.io/
- 同步：
  ```powershell
  python scripts\sync_open_data.py --source listenbrainz --per-artist-limit 10
  ```
  该命令会优先尝试按 MusicBrainz Artist MBID 获取种子艺人的热门作品，并生成 `data/snapshots/listenbrainz_seed_artist_recordings.json`。如果 ListenBrainz popularity API 因服务端高负载暂时不可用，脚本仍会保存 sitewide recordings stats 作为开放趋势快照。

## Wikidata

- 用途：人物、地区、语言、国籍、出生地、奖项、外部 ID 对齐。
- License：CC0。
- 文档：https://www.wikidata.org/wiki/Wikidata:Licensing
- SPARQL：https://query.wikidata.org/
- 同步：
  ```powershell
  python scripts\sync_open_data.py --source wikidata
  ```
  该命令会生成 `data/snapshots/wikidata_seed_artists.json`，用于人工审查 QID、别名、MusicBrainz/Discogs 外部 ID，不会直接覆盖 `seed_artists.yaml`。

## Discogs

- 用途：实体发行、厂牌、版本、发行地区。
- License：monthly data dumps 为 CC0。
- 数据：https://data.discogs.com/
- API：https://www.discogs.com/developers

## 禁止范围

- 不抓取或保存完整歌词。
- 不保存音频或 MV 文件。
- 不依赖私有、逆向或违反 ToS 的音乐平台接口。

## 试听与社媒

### Deezer public preview API

- 用途：为每日推荐和相似歌曲补 30 秒试听片段。
- 约束：只使用 `preview` URL，不下载、不缓存音频文件；匹配必须校验歌名。
- 文档：https://developers.deezer.com/api/search

### Instagram Graph API

- 用途：周杰伦专题展示最新 Instagram 媒体。
- 约束：需要 `JAY_INSTAGRAM_USER_ID` 和 `INSTAGRAM_ACCESS_TOKEN`；未配置时只展示官方主页入口。
- 文档：https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media
