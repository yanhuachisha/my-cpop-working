# My C-Pop Working

一个面向电脑工作场景的华语音乐陪伴 Agent。它连接本地酷狗播放状态，结合天气、华语音乐新闻、听歌记忆和推荐算法，在你工作、学习或独处时提供歌曲推荐、歌曲解读与音乐陪伴。

## 当前能力

- 今日声景：`GET /api/today`，返回主推荐、熟悉答案、今日探索三路结果。
- 情境推荐：支持专注、放松、怀旧、歌词等模式，并展示天气、新闻、时间和个人偏好信号。
- 防重复：同时记录播放历史与推荐曝光历史；当天结果保持稳定，后续日期避开近 14 天已展示作品。
- 听众记忆：支持喜欢、收藏、跳过、想听，以及歌词短句标本。
- Listening Room：读取酷狗当前播放状态，提供歌曲故事、短句分析和上下文 Agent 对话。
- 我的收藏：检测本机酷狗目录，支持 TXT、CSV 或粘贴歌单导入；只保存歌曲元数据。
- 可选酷狗桥：可连接 `Yu9191/KuGou` 本地服务，用于搜索并补全歌曲元数据；不代理音频和完整歌词。
- 曲库：自动合并项目种子、MusicBrainz、Apple iTunes Search API 和用户导入数据，当前约 1150 首。
- 兼容旧版每日推荐：`GET /api/daily-pick?user_id=demo`
- 试听按钮：使用 Deezer public preview URL，不下载、不缓存音频。
- 推荐解释：返回文字理由和结构化 `score_breakdown`。
- 数据质量诊断：查看种子曲库、试听覆盖、开放数据 snapshot。
- 开放数据同步：Wikidata seed artist snapshot、ListenBrainz trend snapshot。
- 新世界：聚合热门 GitHub 项目、AI 新闻、技术社区热榜与学习知识点。
- 前端页面：首页、搜索、歌曲页、听歌房、音乐助理、收藏和新世界。

## 数据源

项目优先使用开放数据和公开 API：

- MusicBrainz：音乐主数据，核心数据 CC0。
- Apple iTunes Search API：补充公开返回的曲目与艺人目录元数据。
- Wikidata：艺人知识图谱和外部 ID，CC0。
- ListenBrainz：开放听歌趋势和 public stats。
- Discogs：发行、厂牌、实体版本 dumps。
- Deezer public preview API：仅用于公开 30 秒试听 URL。

项目不保存完整歌词、不保存音频文件，也不破解或修改酷狗私有数据库。Apple 数据仅来自公开 iTunes Search API 返回的目录元数据，不读取个人 Apple Music 数据。

### 可选酷狗元数据桥

项目可以连接 MIT 许可的 `Yu9191/KuGou` 服务。推荐使用项目内的一键脚本安装并启动：

```powershell
.\scripts\kugou-bridge.ps1 -Action start
```

查看或停止服务：

```powershell
.\scripts\kugou-bridge.ps1 -Action status
.\scripts\kugou-bridge.ps1 -Action stop
```

默认探测 `http://127.0.0.1:9191`，也可以通过 `KUGOU_BRIDGE_URL` 修改地址。当前只启用搜索元数据能力；该服务没有账号收藏歌单接口，因此不能替代酷狗收藏文本导入。第三方接口可能随酷狗服务变化而失效，使用前请自行确认相关服务条款。

## 本地启动

### Windows 一键启动 EXE

项目根目录提供 `C-Pop-Atlas.exe`。双击后会启动前端、后端、已安装的酷狗元数据桥，打开酷狗音乐并在浏览器中打开项目。重新构建启动器：

```powershell
.\scripts\build-launcher.ps1
```

酷狗播放满 30 秒后会自动记录一次播放；同一首连续播放不会被后台轮询重复累计。收藏同步不读取或破解酷狗的私有加密数据库：在酷狗“我的收藏”列表中全选并复制，然后进入网页“我的收藏”，点击“从剪贴板一键同步”。

Windows 推荐一键启动：

```powershell
.\scripts\dev-up.ps1
```

默认地址：

- Web: http://localhost:3000
- API: http://localhost:8001
- API Docs: http://localhost:8001/docs

手动启动：

```powershell
cd backend
pip install -e ".[dev]"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:8001"
npm run dev -- --hostname 0.0.0.0 --port 3000
```

## Docker

```powershell
.\scripts\docker-up.ps1
```

只检查 Docker/Compose 配置：

```powershell
.\scripts\docker-check.ps1
```

默认 Docker 只跑 Web + API，使用 seed 数据即可打开项目。需要 PostgreSQL + pgvector：

```powershell
.\scripts\docker-up.ps1 -WithDb
```

## 关键 API

- `GET /health`
- `GET /api/today?mode=auto`
- `POST /api/listener/feedback`
- `GET /api/listener/profile`
- `GET|POST /api/listener/lyrics`
- `GET /api/library/kugou/discover`
- `GET /api/kugou/bridge/status`
- `GET /api/kugou/bridge/search?q=周杰伦`
- `GET /api/library/status`
- `POST /api/library/import`
- `GET /api/catalog/stats`
- `GET /api/daily-pick?user_id=demo`
- `GET /api/daily-pick/diagnostics`
- `GET /api/daily-pick/diagnostics?live_preview=true`
- `GET /api/recordings/{recording_id}`
- `GET /api/graph`
- `POST /api/agent/query`
- `GET /api/agent/status`
- `POST /api/agent/run`
- `GET /api/agent/evaluate`

## 真实 Agent 架构

当前有 **3 个真正由大模型驱动的 Agent**：`MusicAgent orchestrator` 负责音乐问答、推荐与工具编排；`ListeningCompanionAgent` 负责听歌房右侧的收藏、笔记、相似推荐、歌词分析和联网资料对话；`SongPortraitAgent` 负责歌曲资料检索与情绪画像。三个 Agent 都使用 LangChain `create_agent` 执行“模型判断 → 工具调用 → observation 回填 → 继续决策或回答”的真实循环。`TodayRecommender` 等推荐模块仍是确定性业务模块，不把普通函数虚报为 Agent。

复制 `.env.example` 为 `.env`，然后填写 DeepSeek API Key：

```powershell
DEEPSEEK_API_KEY=在这里填写你的_API_Key
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

Agent Loop：用户问题 → DeepSeek 判断是否调用工具 → 执行工具 → 工具结果回填模型 → 模型继续调用或生成最终答案。服务端通过 `recursion_limit` 和 `max_steps` 控制最大循环次数，并返回完整 `trace`、工具列表、迭代数和延迟。

当前工具：

- `search_music`：搜索本地曲库中的歌曲与歌手。
- `daily_recommendation` / `hybrid_recommendation`：调用现有个性化推荐算法。
- `listener_preference_profile_tool`：读取长期多维音乐偏好画像。
- `listener_emotion_memory` / `weekly_listening_report`：读取近期情绪记忆与听歌复盘。
- `get_current_song_context` / `find_similar_recordings`：理解当前歌曲并推荐相似作品。
- `save_lyric_specimen` / `save_current_feeling`：仅在用户明确要求时持久化歌词标本或音乐笔记。
- `analyze_lyric_excerpt` / `search_song_story_web`：分析用户提供的歌词短句或检索真实创作资料。
- `search_song_material`：检索歌曲可核实的歌手、专辑、年份、流派与来源，再生成情绪化歌曲画像；没有找到的事实不会显示。

Agent 评测使用固定问题集，当前指标包括：工具选择准确率、答案关键词落地率、循环步数和延迟。执行：

```powershell
Invoke-RestMethod http://localhost:8001/api/agent/evaluate
```

未填写 API Key 时使用可复现的本地 fallback，方便 CI 测试；填写 Key 后才进入真实 DeepSeek + LangChain 循环。

## 开放数据同步

生成 Wikidata 种子艺人快照：

```powershell
python scripts\sync_open_data.py --source wikidata
```

生成 ListenBrainz 趋势快照：

```powershell
python scripts\sync_open_data.py --source listenbrainz --per-artist-limit 10
```

输出目录：

```text
data/snapshots/
```

这些 snapshot 用于人工审查和扩展 seed 数据，不会自动覆盖主数据。

## 验收命令

```powershell
pytest backend\tests -q
ruff check backend scripts
cd frontend
npm run build
```

真实检查试听覆盖：

```powershell
$env:CPOP_RUN_LIVE_PREVIEW_TESTS="1"
pytest backend\tests\test_preview_live.py -q
```

真实检查 seed MusicBrainz MBID：

```powershell
$env:CPOP_RUN_LIVE_MUSICBRAINZ_TESTS="1"
pytest backend\tests\test_musicbrainz_live.py -q
```

公开试听覆盖会随第三方临时 URL 变化；试听不可用时，推荐与故事功能仍可正常使用。

GitHub Actions 已配置：

- `CI`：自动运行后端测试、Ruff 和前端 build。
- `Sync open music data`：每日执行开放数据同步 dry-run，也支持手动触发。

## 当前状态

这是一个可运行的本地音乐陪伴 Agent：今日声景、天气与新闻情境、三路推荐、曝光去重、听众反馈、Listening Room、歌词标本和酷狗歌单文本导入均已接通。酷狗收藏自动同步仍受其本地私有数据库格式限制，目前采用用户可控的文本导入方案。

更详细的需求验收、证据和剩余限制见 [docs/project-status.md](docs/project-status.md)。
