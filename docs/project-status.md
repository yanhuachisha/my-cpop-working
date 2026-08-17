# C-Pop Atlas 当前状态与验收证据

更新时间：2026-08-16

这份文档把产品需求、当前实现和可验证证据放在一起，避免把“计划中的能力”误写成“已经完成的能力”。

## 已完成

### 今日声景 Agent

- 默认请求：`GET /api/today`
- 综合 IP 天气、华语音乐新闻、音乐纪念日、时间、电脑活跃状态和听众反馈。
- 同时生成“今日主推荐、熟悉答案、今日探索”，并保证三首歌曲和艺人互不重复。
- 支持专注、放松、怀旧、歌词等场景模式。
- 记录播放与推荐曝光；当天刷新保持稳定，跨天避开近 14 天已展示作品。
- 推荐卡展示结构化信号与自然语言解释，不再固定返回单一歌曲。

### 个人音乐空间

- Listening Room 展示酷狗当前播放状态，并提供歌曲故事、歌词短句分析和上下文对话。
- “我的收藏”检测本机酷狗目录，支持 TXT、CSV、粘贴文本导入收藏歌单。
- 可选连接 `Yu9191/KuGou` 本地服务，用于检索歌名、歌手、专辑和时长，并一键加入待导入列表。
- 酷狗数据库属于私有格式，项目不破解数据库、不复制音频，也不要求下载歌曲到本地。
- 第三方桥没有账号收藏接口，项目明确禁用音频代理和完整歌词能力。
- 歌词标本馆只保存用户主动提供的短句和笔记，不补全或保存完整歌词。

验收：

```powershell
pytest backend\tests -q
```

### 试听

- 使用 Deezer public preview API 的公开 30 秒 URL。
- 不下载、不保存音频。
- 歌名和艺人匹配后才挂载 preview URL。
- 当前 seed 曲库可用 live 测试验证试听覆盖率。

验收：

```powershell
$env:CPOP_RUN_LIVE_PREVIEW_TESTS="1"
pytest backend\tests\test_preview_live.py -q
```

### 开放数据

- Wikidata snapshot：艺人 QID、别名、描述、MusicBrainz/Discogs 外部 ID。
- ListenBrainz snapshot：种子艺人热门作品尝试和 sitewide 趋势 fallback。
- snapshot 不直接覆盖人工维护的 seed 主数据。
- 主数据层额外合并 Apple iTunes Search API 目录和用户导入曲库，当前候选约 1150 首。

验收：

```powershell
python scripts\sync_open_data.py --source all --dry-run
python scripts\sync_open_data.py --source wikidata
python scripts\sync_open_data.py --source listenbrainz
```

真实检查 seed 中 MusicBrainz MBID 是否仍可解析：

```powershell
$env:CPOP_RUN_LIVE_MUSICBRAINZ_TESTS="1"
pytest backend\tests\test_musicbrainz_live.py -q
```

### 周杰伦专题

- 专辑时间线、作品试听、关系图谱和 Agent 报告。
- Instagram 使用官方 Graph API。
- 配置 token 后前端展示媒体卡片；未配置 token 时展示主页入口和状态说明。

### 工程交付

- 本地前后端：Web `3000`，API `8001`。
- Docker Compose：Web + API 默认启动，数据库通过 profile 选择。
- GitHub Actions：
  - CI：后端测试、Ruff、前端 build。
  - Sync：开放数据同步 dry-run，可定时或手动触发。

## 当前限制

- 华语新闻来自公开 RSS，受源站更新频率和网络状态影响；失败时会降级为空列表。
- ListenBrainz artist popularity API 可能因服务端负载暂时不可用，脚本会保存 sitewide 趋势作为 fallback。
- Instagram 最新媒体需要用户自己的 `JAY_INSTAGRAM_USER_ID` 和 `INSTAGRAM_ACCESS_TOKEN`；没有凭据时不能验证真实账号媒体。
- Deezer preview URL 是外部临时资源，失效时推荐仍返回，但试听按钮会提示暂不可用。
- PostgreSQL/pgvector schema 已准备，当前 MVP 主流程仍使用 seed 文件。
- 酷狗收藏尚不能从私有数据库全自动读取，目前需要复制或导出歌单文本后导入。

## 下一阶段

1. 增加可配置的华语新闻源与事件可信度排序。
2. 在用户授权且格式可识别的前提下，探索更顺滑的酷狗歌单导出助手。
3. 将反馈记忆升级为可解释的长期口味画像和月度听歌回顾。
4. 配置正式 Instagram Graph API 后做真实媒体回归测试。
