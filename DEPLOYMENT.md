# GitHub 部署指南

## 1. 发布前检查

- 不要提交 `.env`、API Key、数据库密码或模型缓存。
- `git status --ignored` 确认 `.env` 和构建产物被忽略。
- 重新生成所有曾经在本地日志、聊天记录或截图中出现过的密钥。
- 在 GitHub Actions 的 Secrets 中配置 `DEEPSEEK_API_KEY`，不要写入 workflow 文件。

## 2. Lite 模式

Lite 模式适合普通用户和低配置机器，启动 MySQL、Redis、Elasticsearch、RabbitMQ、Java Music Core、FastAPI 和 Next.js，但模型服务不参与启动，Agent 使用 DeepSeek 或确定性降级。

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
cp .env.example .env
docker compose --profile lite up --build
```

打开 `http://localhost:3000`。

## 3. Full 模式

Full 模式用于面试演示完整链路。除 Lite 服务外，还启动模型服务、RAG 索引初始化、Debezium Embedded CDC 和长期记忆 Projector。

```bash
docker compose --profile full up --build
```

首次启动会从 Hugging Face 下载 `Qwen/Qwen3-0.6B` 和 `BAAI/bge-m3`。模型缓存由 `model-cache` volume 持久化；删除该 volume 会触发重新下载。

## 4. 端口冲突

在 `.env` 中覆盖宿主机端口，容器内部端口无需修改：

```env
WEB_PORT_FORWARD=13000
API_PORT_FORWARD=18000
MYSQL_PORT_FORWARD=13306
REDIS_PORT_FORWARD=16379
ELASTICSEARCH_PORT_FORWARD=19200
RABBITMQ_PORT_FORWARD=15673
```

## 5. Windows 桌面应用

桌面应用是 Windows 本地适配器，不放进 Docker：

- 双击 `My-C-Pop-Working.exe` 启动本地 API/Web，并在独立桌面窗口中打开应用；窗口关闭后，启动器会清理本轮启动的子进程。
- 如果 WebView2 不可用，会自动回退到独立的 Edge/Chrome 应用窗口，生命周期规则不变。
- 设置 `KUGOU_DESKTOP_INTEGRATION=true` 开启窗口检测和播放追踪。
- Docker 中固定为 `false`，避免容器访问宿主机窗口系统。

正式生产环境应将桌面采集器产生的播放事件通过幂等 HTTP API 发送到服务端，再由 Java/MySQL 作为权威写入；不要让容器直接读取酷狗私有数据库。

## 6. 停止和清理

```bash
docker compose --profile full --profile observability down
# 仅在确认要删除数据库、Redis、ES、RabbitMQ 和模型缓存时执行：
docker compose --profile full --profile observability down -v
```

## 7. 桌面 EXE 的分发边界

仓库默认忽略 `*.exe`，因此 GitHub clone 不会自动得到桌面启动器。桌面启动器依赖 Windows 的酷狗窗口、Python 和 Node.js，主要面向个人电脑；需要重新生成时，在 Windows 上执行：

```powershell
.\scripts\build-launcher.ps1
```

脚本会使用 `C:\ide\anaconda\python.exe`（可通过参数覆盖），生成 `My-C-Pop-Working.exe` 并同步到当前用户桌面。向他人分发时，建议把 EXE 放在 GitHub Releases，并要求其旁边存在完整项目目录，或设置：

```powershell
$env:CPOP_PROJECT_ROOT = "D:\apps\cpop-atlas"
```

如果目标是服务器、Linux、云主机或团队共享环境，不要分发桌面 EXE，直接使用 Docker profile。
