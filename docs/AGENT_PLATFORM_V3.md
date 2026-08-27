# Agent Platform V3

## 请求链路

```text
HTTP Request
  -> Qwen3-0.6B intent/entities
  -> Redis Stream summary + recent history + token counters
  -> BGE-M3 1024d query embedding
  -> Elasticsearch BM25 and KNN with pre-retrieval ACL filters
  -> weighted RRF -> authority/freshness -> MMR
  -> 32K token budget assembly
  -> DeepSeek ReAct and ToolExecutor
  -> answer + Redis append + MySQL conversation audit
  -> conditional Qwen memory extraction
  -> Java/MySQL memory transaction and outbox
  -> Debezium Embedded -> RabbitMQ aggregate bucket
  -> BGE-M3 projector -> ES external-version projection
```

MySQL is the source of truth. Redis contains disposable short-term session state. Elasticsearch contains rebuildable retrieval projections only.

酷狗集成属于桌面适配层：桌面启动器可开启窗口检测、播放追踪和可选元数据桥接；Docker API 默认设置 `KUGOU_DESKTOP_INTEGRATION=false`，保持无头、跨平台和可水平扩展。桌面采集到的播放事件通过导入/API 进入服务侧，不能让容器反向控制用户桌面播放器。

## 会话与预算不变量

- Stream key: `agent:session:{user}:{session}:messages`, written with `MAXLEN ~ 256`.
- Compression starts at 192 messages. The newest eight messages, normally four user/assistant turns, are never summarized.
- Summary stores `covered_from_id`, `covered_through_id`, `summary_version`, and source IDs.
- Recent history starts exclusively after `covered_through_id`; one message cannot appear in both sections.
- Redis summary updates use `WATCH + MULTI/EXEC` version CAS, so concurrent compactors cannot overwrite a newer watermark.
- Default context limit is 32K. It reserves 2K output and 1K safety tokens, with separate system/tool, knowledge, memory, summary, history, and query accounting.

## Agent 与工具边界

`AgentState` owns `run_id`, `trace_id`, `step`, `max_steps`, tool calls, observations, token usage, start time, and deadline. `max_steps` defaults to 8 and has a hard limit of 12; the request deadline defaults to 30 seconds and has a hard limit of 60 seconds.

Every tool is frozen in `ToolRegistry` with a JSON schema, read/write type, risk, timeout, idempotency, permission, and result-field allowlist. `ToolExecutor` performs budget checks, authorization, schema validation, confirmation, deadline-aware timeout, shared circuit breaking, idempotency, redaction, truncation, and structured audit observations.

The API derives execution authority from headers, not model output:

```text
X-User-Id: user-1
X-Tenant-Id: tenant-1
X-Permissions: music.search,favorite.write
X-Confirmed-Tools: add_favorite
```

Medium/high-risk writes require both permission and `X-Confirmed-Tools`. Write handlers call Spring Boot and commit MySQL; the model never writes the database directly.

## 检索与记忆安全

Both BM25 and KNN DSL contain the same hard filters. Knowledge access requires tenant match, required permission, and one of public/tenant/owner/user ACL/permission ACL. Memory access requires exact tenant and user match. Unauthorized hits therefore never enter RRF, reranking, traces, or citations; permission is not a ranking feature.

Memory writes commit `agent_memory`, `memory_version`, `memory_source_relation`, and `outbox_event` in one Java transaction. A conflict creates a new version and deactivates the old version without deleting audit history. Debezium publishes by a stable aggregate bucket. The projector uses Elasticsearch `version_type=external`, so duplicate and out-of-order versions are acknowledged without replacing newer state.

## 本地启动

Windows Maven Wrapper uses `C:\Users\super\Desktop\jdk-17.0.12` when `JAVA_HOME` is absent:

```powershell
.\mvnw.cmd test
```

Lite starts the application and data infrastructure with deterministic model degradation. Full starts Qwen3-0.6B, BGE-M3, CDC, RAG initialization, and the memory projector. The first full start downloads model weights into the persistent Hugging Face cache.

```powershell
docker compose --profile lite up --build
docker compose --profile full up --build
docker compose --profile full --profile observability up --build
```

Endpoints:

- Web: `http://localhost:3000`
- API readiness: `http://localhost:8000/ready`
- Music Core readiness: `http://localhost:8080/actuator/health/readiness`
- Model readiness: `http://localhost:8010/ready`
- RabbitMQ: `http://localhost:15672`
- Grafana: `http://localhost:3002`

## 示例 RAG 文档

`data/rag/mandopop-wikipedia-zh.md` 是从中文维基百科固定修订版下载的代表性中文音乐文档。来源清单记录修订号、许可证、下载时间和内容哈希；`mandopop-wikipedia-zh.ingest.json` 可直接提交到管理端摄取接口。

```powershell
.\scripts\download_sample_rag.ps1
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/admin/rag/ingest `
  -ContentType application/json `
  -InFile .\data\rag\mandopop-wikipedia-zh.ingest.json
```

## 回归命令

```powershell
Set-Location backend
pytest -q
ruff check app tests
Set-Location ..
.\mvnw.cmd test
docker compose --profile full --profile observability config --quiet
```
