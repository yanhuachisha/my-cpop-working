# 快速启动指南

## 🚀 启动项目

### 1. 启动后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

后端将运行在: http://localhost:8001  
API 文档: http://localhost:8001/docs

### 2. 启动前端

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:8001"
npm run dev
```

前端将运行在: http://localhost:3000

### Windows 一键本地启动

```powershell
.\scripts\dev-up.ps1
```

默认使用前端 `http://localhost:3000`、后端 `http://localhost:8001`。
如果你的 `8000` 端口有系统残留监听，继续使用 `8001` 即可。

---

## ✨ 新功能使用指南

### 1. 搜索功能
- 在顶部导航栏输入关键词
- 支持同时搜索艺人和歌曲
- 搜索结果显示标签、年份等元信息

### 2. "换一首"功能
- 在首页今日推荐卡片底部
- 点击"换一首"按钮即可刷新推荐
- 每次都会推荐不同的歌曲

### 3. 每日推荐数据质量检查

```powershell
curl "http://localhost:8001/api/daily-pick/diagnostics"
curl "http://localhost:8001/api/daily-pick/diagnostics?live_preview=true"
```

第一个接口快速查看曲库、数据源和推荐是否可用；第二个会真实查询公开试听源，用来确认当前种子曲库的试听覆盖率。

### 4. 交互式图谱
- 访问 http://localhost:3000/graph
- **拖拽**: 点击并拖动节点调整位置
- **缩放**: 鼠标滚轮缩放视图
- **平移**: 空白区域拖动平移画布
- **小地图**: 右下角显示全局视图

### 5. 错误处理
- API 失败时自动重试 3 次
- 显示友好的错误提示
- 提供"重试"按钮

---

## 📂 项目结构变化

### 新增文件

```
frontend/
├── components/                 # 新增组件目录
│   ├── ErrorBoundary.tsx      # 全局错误边界
│   ├── ErrorState.tsx         # 错误状态组件
│   ├── Loading.tsx            # 加载状态组件
│   └── SearchBar.tsx          # 搜索栏组件
├── app/
│   ├── DailyPickContent.tsx   # 首页客户端组件
│   ├── search/                # 搜索页面
│   │   └── page.tsx
│   └── graph/
│       ├── page.tsx           # 图谱页面入口
│       └── GraphContent.tsx   # 图谱客户端组件

backend/
└── app/
    └── recommender.py         # 改进的推荐算法
```

### 修改的文件

- `frontend/lib/api.ts` - 添加错误类型和重试机制
- `frontend/app/layout.tsx` - 集成搜索栏和错误边界
- `frontend/app/page.tsx` - 改为客户端组件
- `frontend/app/globals.css` - 新增样式
- `backend/app/recommender.py` - 算法优化

---

## 🔧 开发指南

### 添加新页面

```typescript
// frontend/app/new-page/page.tsx
export default function NewPage() {
  return (
    <main>
      <section>
        <h1>新页面</h1>
      </section>
    </main>
  );
}
```

### 调用 API

```typescript
import { fetchApiClient } from '@/lib/api';

// 客户端调用
const data = await fetchApiClient<DataType>('/api/endpoint');

// 服务端调用（不缓存）
const data = await fetchApi<DataType>('/api/endpoint', false);
```

### 添加加载状态

```typescript
import { LoadingSpinner } from '@/components/Loading';
import { ErrorState } from '@/components/ErrorState';

if (loading) return <LoadingSpinner />;
if (error) return <ErrorState message={error} retry={loadData} />;
```

---

## 🎨 样式指南

### 使用预定义样式类

```html
<!-- 按钮 -->
<button className="btn-primary">主按钮</button>
<button className="btn-secondary">次按钮</button>

<!-- 卡片 -->
<article className="card">内容</article>
<article className="card interactive">可交互卡片</article>

<!-- 搜索框 -->
<SearchBar placeholder="搜索..." />

<!-- 标签 -->
<span className="tag">标签</span>

<!-- 列表 -->
<div className="list">
  <div className="list-item">列表项</div>
</div>
```

### CSS 变量

```css
:root {
  --bg: #f7f3ed;          /* 背景色 */
  --ink: #191714;         /* 文字色 */
  --muted: #6f675f;       /* 次要文字 */
  --line: #ded6ca;        /* 边框色 */
  --card: #fffaf3;        /* 卡片背景 */
  --accent: #c83f31;      /* 强调色 */
  --accent-2: #146c6c;    /* 强调色2 */
  --accent-3: #7251a4;    /* 强调色3 */
}
```

---

## 📊 推荐算法使用

### 获取推荐

```python
from app.recommender import DailyRecommender
from app.data_store import get_store

recommender = DailyRecommender(get_store())
pick = recommender.pick(user_id="demo")
```

### 查找相似歌曲

```python
similar = recommender.similar_recordings(recording_id="song-id", limit=5)
```

### 解释推荐理由

```python
reasons = recommender.explain(recording, user_id="demo")
```

---

## 🐛 常见问题

### Q: 前端构建失败
A: 确保安装了所有依赖：
```powershell
cd frontend
npm install
```

### Q: 后端启动失败
A: 检查 Python 版本（需要 3.10+）和依赖安装：
```powershell
python --version
pip install -e ".[dev]"
```

### Q: 图谱显示空白
A: 检查后端 API 是否正常运行：
```powershell
curl http://localhost:8001/api/graph
```

### Q: 搜索无结果
A: seed 数据量较小，尝试搜索"周杰伦"或"jay"

---

## 📈 性能优化建议

### 前端
1. 使用 React Query 缓存 API 响应
2. 图片使用 Next.js Image 组件
3. 大列表使用虚拟滚动
4. 启用 PWA 支持

### 后端
1. 迁移到数据库（SQLite/PostgreSQL）
2. 添加 Redis 缓存
3. 使用 FastAPI 后台任务处理耗时操作
4. 添加 API 速率限制

---

## 🔐 环境变量

### 前端 (.env.local)

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001
```

### 后端 (.env)

```bash
CPOP_DATA_DIR=../data
```

---

## 📚 相关资源

- [Next.js 文档](https://nextjs.org/docs)
- [React Flow 文档](https://reactflow.dev/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [改进总结文档](./IMPROVEMENTS.md)

---

## 🎯 下一步建议

1. **数据库迁移** - 使用 SQLite 或 PostgreSQL
2. **Agent 升级** - 集成 LLM 实现真正的对话
3. **数据可视化** - 添加统计看板和趋势图
4. **开放数据接入** - 同步 MusicBrainz 数据

详见 [IMPROVEMENTS.md](./IMPROVEMENTS.md) 的后续改进建议部分。

---

**祝开发愉快！** 🎉
