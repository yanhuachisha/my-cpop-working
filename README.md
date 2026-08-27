# My C-Pop Working

一个面向中文音乐场景的 AI 音乐工作台，也是一个可用于面试演示的 Agent 全链路项目。

项目把音乐推荐、听歌记录、酷狗桌面播放状态、RAG 知识库和多轮 Agent 对话整合到同一个系统中。核心目标不是做一个简单的聊天页面，而是展示一套可解释、可观测、可恢复的生产化 Agent 架构。

![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=nextdotjs)
![React](https://img.shields.io/badge/React-19-149eca?logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![Java](https://img.shields.io/badge/Java-17-ED8B00?logo=openjdk&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-3776ab?logo=python&logoColor=white)
![CI](https://img.shields.io/badge/CI-pytest%20%7C%20ruff%20%7C%20Maven%20%7C%20Next.js-2ea44a)

## 1. 先跑起来

### 1.1 最低要求

Docker 是推荐入口。使用者不需要单独安装 Java、Maven、Python 或 Node.js。

- Windows/macOS：Docker Desktop（Windows 建议启用 WSL2）
- Linux：Docker Engine 24+ 和 Docker Compose Plugin
- Git
- Lite 模式建议 4 GB 内存
- Full 模式建议 8 GB 起步、16 GB 更舒适，至少 15 GB 可用磁盘

### 1.2 克隆并配置

```bash
git clone https://github.com/<owner>/<repository>.git
cd <repository>
```

Linux/macOS：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
notepad .env
```

至少配置一个自己的 DeepSeek Key：

```env
DEEPSEEK_API_KEY=your_api_key
```

没有 Key 时项目仍可启动，Agent 会使用确定性降级逻辑，但最终回答能力会受限。

### 1.3 Lite 模式：日常体验

Lite 会启动 MySQL、Redis、Elasticsearch、RabbitMQ、Java Music Core、FastAPI 和 Next.js 前端，不启动本地模型服务，适合第一次体验和低配置机器：

```bash
docker compose --profile lite up --build
```

访问：<http://localhost:3000>

### 1.4 Full 模式：面试演示

Full 会在 Lite 基础上启动 Qwen3-0.6B、BGE-M3、RAG 初始化、CDC Worker 和长期记忆 Projector：

```bash
docker compose --profile full up --build
```

需要监控面板时：

```bash
docker compose --profile full --profile observability up --build
```

首次启动会从 Hugging Face 下载：

- `Qwen/Qwen3-0.6B`：意图识别、摘要、记忆抽取
- `BAAI/bge-m3`：RAG 和长期记忆向量化，1024 维

模型缓存保存在 Docker volume `model-cache` 中，后续启动不会重复下载。CPU 可以运行，但模型预热较慢；检测到 CUDA 时模型服务会自动使用加速环境。

默认地址：

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| Web | <http://localhost:3000> | 用户界面 |
| API | <http://localhost:8000> | 后端接口 |
| API 文档 | <http://localhost:8000/docs> | Swagger/OpenAPI |
| RabbitMQ | <http://localhost:15672> | 用户 `cpop`，密码 `cpop` |
| Grafana | <http://localhost:3002> | observability profile |

停止服务：

```bash
docker compose --profile full --profile observability down
```

只有确定要删除数据库、Redis、ES、RabbitMQ 和模型缓存时，才使用 `down -v`。

## 2. Windows 桌面模式（酷狗联动）

桌面模式是 Windows 本地适配器，适合你自己的电脑使用：

1. 双击桌面上的 `My-C-Pop-Working.exe`。
2. 启动本地 Web（3000）和 API（8001）。
3. 检测酷狗窗口标题和播放状态，按阈值记录听歌时长。

桌面模式不会破解、读取或修改酷狗私有数据库，只读取公开的窗口状态。Docker 容器固定使用 `KUGOU_DESKTOP_INTEGRATION=false`，不会访问宿主机窗口系统。

仓库默认忽略 `*.exe`，所以 `git clone` 不会自动得到启动器。需要构建时，在 Windows 执行：

```powershell
.\scripts\build-launcher.ps1
```

该脚本会生成 `My-C-Pop-Working.exe` 并复制到当前用户桌面。向其他 Windows 用户分发时，建议将 EXE 放在 GitHub Releases，并同时提供完整项目目录；服务器和团队环境请使用 Docker，不要分发桌面 EXE。

## 3. Agent 全链路

请求从 API 进入后的主要流程：

```text
用户请求
  -> Qwen3-0.6B 意图识别
  -> Redis 读取短期会话、Summary 和 Token Budget
  -> BGE-M3 生成 Query 向量
  -> Elasticsearch BM25 + KNN-ANN
  -> ACL hard filter 后执行 RRF 融合
  -> 召回 RAG 知识与长期记忆
  -> Token Budget 组装上下文并预留输出空间
  -> DeepSeek 生成回答或调用工具
  -> Redis 追加本轮消息
  -> 按条件执行 Memory Extraction
  -> MySQL 事务落库，经 CDC 投影到 ES
```

### 3.1 Agent 状态和执行边界

每次运行都有独立 `run_id` 和 `trace_id`。状态至少包含：

```text
run_id, trace_id, user_id, session_id, intent, entities,
step, max_steps, tool_calls, observations, token_usage,
started_at, deadline, retrieved_chunks, memory_candidates,
context_summary, citations, degraded_dependencies
```

- `max_steps` 默认 8，请求可配置 2～12，服务端硬上限 12。
- 默认 deadline 30 秒，硬上限 60 秒；每次模型和工具调用前都会检查剩余时间。
- 工具总调用数默认最多 6 次，同一工具默认最多 2 次。
- 达到步数、时间或 Token Budget 上限后进入 `finalize`，不再执行工具。
- 每次工具调用记录 `call_id`、参数摘要、状态、耗时和结构化 observation，便于面试时展示轨迹。

### 3.2 Summary 与 Recent History 去重

Redis 使用 Stream 保存原始消息，并设置最终保护长度：

```text
agent:session:{user}:{session}:messages   MAXLEN ~ 256
agent:session:{user}:{session}:budget
agent:session:{user}:{session}:summary
```

Summary 带有 `covered_from_id`、`covered_through_id`、`summary_version` 和来源消息 ID。摘要只覆盖较旧消息，最近 4 轮原始对话永远保留在 Recent History；加载 Recent History 时从 `covered_through_id +` 开始读取，因此同一条消息不会同时出现在 Summary 和 Recent History 中。

Stream 达到约 192 条消息时提前压缩，`XADD MAXLEN ~ 256` 作为最后保护。完整会话审计由 MySQL 保存，不依赖 Redis 永久保留。

默认 Token Budget 为 32K，优先保留安全提示、当前 Query 和最近 4 轮；超限时依次删除低分召回、压缩旧历史、缩短摘要。

### 3.3 Tool Calling

工具由三个组件管理，Agent 不直接调用业务函数：

- `ToolRegistry`：启动时注册并冻结工具，检查名称冲突和 schema。
- `ToolSchema`：描述名称、输入 JSON Schema、读写类型、风险等级、超时、幂等性和所需权限。
- `ToolExecutor`：负责鉴权、参数校验、风险确认、超时、幂等、熔断、执行和审计。

READ 工具包括 `search_music`、`get_history`、`query_catalog`、`retrieve_memory`；WRITE 工具包括 `add_favorite`、`update_preference`、`submit_feedback`、`save_memory`。

WRITE 工具固定经过：

```text
权限验证 -> JSON Schema 校验 -> 风险策略 -> 幂等键
-> Java API -> MySQL 事务 -> 审计 observation
```

权限在 BM25 和 KNN 召回阶段使用 hard filter，未授权文档不会进入候选集、RRF、重排、trace 或 citation，绝不把权限当作重排特征。

### 3.4 长期记忆和 CDC

记忆抽取满足以下条件之一时触发：每 6 轮、新业务实体或稳定偏好出现、Token 使用达到 75%、空闲 30 分钟，或用户明确要求“记住”。

```text
Memory Candidate
  -> Schema / Privacy / Conflict Validation
  -> MySQL 事务：memory + memory_version + source_relation + outbox
  -> COMMIT
  -> Debezium Embedded
  -> RabbitMQ
  -> BGE-M3 Memory Projector
  -> ES agent_memory_current
```

MySQL 是唯一权威数据源，ES 只是可重建的检索投影。Projector 通过 `aggregate_id` 路由、消费者幂等和 `aggregate_version` 检查处理重复或乱序事件，避免旧事件覆盖新状态。

## 4. 项目结构

```text
backend/                 FastAPI、Agent、工具、RAG、测试
frontend/                Next.js 16 + React 19 Web UI
services/music-core/     Java 17 Spring Boot 权威业务服务
services/cdc-worker/     Debezium Embedded CDC
services/memory-projector/长期记忆消息消费和 ES 投影
model-service/           Qwen3-0.6B + BGE-M3 模型服务
data/rag/                示例 RAG 文档和 ingest 文件
infra/mysql/init/        MySQL 初始化表结构
docker-compose.yml       lite/full/observability 部署编排
launcher/                Windows 酷狗桌面启动器
scripts/                 启动、索引、数据同步和评测脚本
```

## 5. 环境变量

完整模板见 `.env.example`。常用配置：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com

# Docker 对外端口，容器内部端口不变
WEB_PORT_FORWARD=3000
API_PORT_FORWARD=8000
MYSQL_PORT_FORWARD=3306
REDIS_PORT_FORWARD=6379
ELASTICSEARCH_PORT_FORWARD=9200
RABBITMQ_PORT_FORWARD=5672
```

如果宿主机端口被占用，可在 `.env` 中改成例如 `API_PORT_FORWARD=18000`，然后访问 `http://localhost:18000`。

不要把 `.env`、API Key、真实用户数据或模型缓存提交到 GitHub。生产环境还应修改 MySQL、Redis 和 RabbitMQ 的默认密码，并将 Key 交给 GitHub Actions Secrets 或部署平台的 Secret 管理器。

## 6. API 入口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 服务健康检查 |
| POST | `/api/agent/query` | Agent 自然语言问答 |
| POST | `/api/agent/run` | Agent 执行入口 |
| GET | `/api/agent/status` | Agent、模型和工具状态 |
| GET | `/api/agent/evaluate?suite=smoke&algorithm=auto` | Agent 评测 |
| GET | `/api/recommendations/hybrid` | 混合推荐 |
| GET | `/api/listening/today-stats` | 今日听歌统计 |
| GET | `/api/agent/weekly-report` | 周报生成 |
| GET | `/api/kugou/bridge/status` | 酷狗桥接状态 |
| GET | `/api/catalog/stats` | 曲库统计 |
| POST | `/api/library/import` | 导入歌单元数据 |

启动 API 后可通过 <http://localhost:8000/docs> 查看完整 OpenAPI 文档。

## 7. 本地开发（不使用 Docker）

本地 Java 服务使用 JDK 17。Windows 可显式指定：

```powershell
$env:JAVA_HOME = "C:\Users\super\Desktop\jdk-17.0.12"
```

后端：

```powershell
cd backend
pip install -e ".[dev]"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

前端：

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:8001"
npm run dev -- --hostname 0.0.0.0 --port 3000
```

Java 服务：

```powershell
cd services/music-core
..\..\mvnw.cmd test
```

## 8. 测试和验收

Python 测试：

```powershell
cd backend
pytest -q
ruff check .
```

Java 测试：

```powershell
cd services/music-core
..\..\mvnw.cmd test
cd ..\cdc-worker
..\..\mvnw.cmd test
cd ..\memory-projector
..\..\mvnw.cmd test
```

Agent 离线评测：

```powershell
python scripts/run_agent_eval.py --suite smoke --algorithm auto
python scripts/run_agent_eval.py --suite full --algorithm auto
```

配置真实 LLM Key 后可运行在线评测：

```powershell
python scripts/run_agent_eval.py --suite full --algorithm auto --live
```

CI 会在 push 和 pull request 中执行 Python 测试、ruff、Java 17 Maven 构建、前端构建和 Compose 配置检查。

## 9. 数据来源和合规边界

项目优先使用 MusicBrainz、Wikidata、ListenBrainz、iTunes Search、Deezer 公共接口和仓库内的示例 RAG 文档。项目不保存完整歌词、不保存音频文件、不代理音频、不读取个人 Apple Music 私有数据，也不破解酷狗私有数据库。

## 10. 面试演示建议

推荐先用 Lite 模式确认页面和 API 正常，再切换 Full 模式演示：

1. 查看 Agent `run_id`、`step`、`max_steps`、工具调用和 token 使用量。
2. 展示 BM25 + KNN + ACL hard filter + RRF 的检索链路。
3. 连续对话，说明 Summary watermark 如何避免 Summary 与 Recent History 重复。
4. 调用写工具，展示权限、参数校验、风险确认、幂等键和 MySQL 事务。
5. 触发记忆抽取，展示 MySQL outbox、RabbitMQ 消息和 ES 长期记忆投影。
6. 在 Grafana 中查看延迟、错误、降级依赖和 Agent 轨迹。

更多架构细节见 [`docs/AGENT_PLATFORM_V3.md`](docs/AGENT_PLATFORM_V3.md)，部署注意事项见 [`DEPLOYMENT.md`](DEPLOYMENT.md)。
