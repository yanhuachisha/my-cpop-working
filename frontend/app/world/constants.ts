import { CSSProperties } from "react";
import { NewWorldPayload } from "./types";

export const HOT_SOURCE_ICONS: Record<string, { fallback: string; url: string }> = {
  Wikipedia: { fallback: "W", url: "https://zh.wikipedia.org/static/favicon/wikipedia.ico" },
  CSDN: { fallback: "C", url: "https://g.csdnimg.cn/static/logo/favicon32.ico" },
  "LINUX.DO": { fallback: "L", url: "https://linux.do/favicon.ico" },
  博客园: { fallback: "园", url: "https://assets.cnblogs.com/favicon.ico" },
  V2EX: { fallback: "V2", url: "https://www.v2ex.com/static/icon-192.png" },
  掘金: { fallback: "掘", url: "https://lf3-cdn-tos.bytescm.com/obj/static/xitu_juejin_web//static/favicons/favicon-32x32.png" },
  知乎: { fallback: "知", url: "https://static.zhihu.com/heifetz/favicon.ico" },
  "Hacker News": { fallback: "Y", url: "https://news.ycombinator.com/favicon.ico" },
};

export const COPY = {
  traveling: "正在穿越",
  leaving: "正在离开已知世界",
  aligning: "今天的代码、AI、历史与学习线索，正在对齐。",
  enter: "直接进入",
  error: "新世界情报暂时无法到达。",
  github: "GitHub 热门",
  news: "AI 新闻",
  hot: "每日热榜",
  learning: "今日学习",
  projects: "个项目",
  highlights: "条重点",
  sites: "个站点",
  points: "个知识点",
  githubCoordinates: "GitHub 热门坐标",
  githubHint: "今日值得关注的 3 个项目",
  githubEmpty: "GitHub 今日暂未返回项目，稍后刷新。",
  aiSignals: "AI 重要信号",
  aiHint: "5 条重要消息，只留重点",
  hotCoordinates: "今日网络热榜",
  hotHint: "一次打开不同社区的当日热点",
  learningMap: "今日学习地图",
  learningHint: "10 个学习知识点",
  knowledgePoint: "知识点",
} as const;

export const STAR_STREAKS = Array.from({ length: 56 }, (_, index) => ({
  "--angle": `${index * 6.43}deg`,
  "--delay": `${(index % 8) * -0.11}s`,
  "--length": `${110 + (index % 6) * 28}px`,
} as CSSProperties));

export function normalizePayload(payload: Partial<NewWorldPayload>): NewWorldPayload {
  return { date: payload.date || new Date().toISOString().slice(0, 10), generated_at: payload.generated_at || new Date().toISOString(), github: Array.isArray(payload.github) ? payload.github : [], ai_news: Array.isArray(payload.ai_news) ? payload.ai_news : [], hot_links: Array.isArray(payload.hot_links) ? payload.hot_links : [], learning: Array.isArray(payload.learning) ? payload.learning : [] };
}

export function formatDate(value?: string | null) {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value.slice(0, 10) : parsed.toLocaleDateString("zh-CN");
}
