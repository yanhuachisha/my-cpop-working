"use client";

import {
  ArrowUpRight,
  BrainCircuit,
  Flame,
  Github,
  Globe2,
  Newspaper,
  Orbit,
  Sparkles,
} from "lucide-react";
import { CSSProperties, useCallback, useEffect, useRef, useState } from "react";
import { ErrorState } from "../../components/ErrorState";
import { fetchApiClient } from "../../lib/api";

type GithubProject = {
  name: string;
  description: string;
  url: string;
  stars: number;
  language?: string | null;
  topics: string[];
  created_at?: string | null;
};

type AiNews = {
  title: string;
  url: string;
  source: string;
  summary: string;
  published_at?: string | null;
};

type HotLink = { source: string; title: string; summary: string; url: string };
type LearningPoint = { category: string; title: string; focus: string; url: string };
type NewWorldTab = "github" | "news" | "hot" | "learning";
type NewWorldPayload = {
  date: string;
  generated_at: string;
  github: GithubProject[];
  ai_news: AiNews[];
  hot_links: HotLink[];
  learning: LearningPoint[];
};

const HOT_SOURCE_ICONS: Record<string, { fallback: string; url: string }> = {
  Wikipedia: { fallback: "W", url: "https://zh.wikipedia.org/static/favicon/wikipedia.ico" },
  CSDN: { fallback: "C", url: "https://g.csdnimg.cn/static/logo/favicon32.ico" },
  "LINUX.DO": { fallback: "L", url: "https://linux.do/favicon.ico" },
  "\u535a\u5ba2\u56ed": { fallback: "\u56ed", url: "https://assets.cnblogs.com/favicon.ico" },
  V2EX: { fallback: "V2", url: "https://www.v2ex.com/static/icon-192.png" },
  "\u6398\u91d1": { fallback: "\u6398", url: "https://lf3-cdn-tos.bytescm.com/obj/static/xitu_juejin_web//static/favicons/favicon-32x32.png" },
  "\u77e5\u4e4e": { fallback: "\u77e5", url: "https://static.zhihu.com/heifetz/favicon.ico" },
  "Hacker News": { fallback: "Y", url: "https://news.ycombinator.com/favicon.ico" },
};

function HotSourceIcon({ source }: { source: string }) {
  const icon = HOT_SOURCE_ICONS[source] || { fallback: source.slice(0, 1), url: "" };
  return <span className="hot-source-icon"><b>{icon.fallback}</b>{icon.url ? <img alt="" onError={(event) => { event.currentTarget.style.display = "none"; }} src={icon.url} /> : null}</span>;
}

function normalizePayload(payload: Partial<NewWorldPayload>): NewWorldPayload {
  return {
    date: payload.date || new Date().toISOString().slice(0, 10),
    generated_at: payload.generated_at || new Date().toISOString(),
    github: Array.isArray(payload.github) ? payload.github : [],
    ai_news: Array.isArray(payload.ai_news) ? payload.ai_news : [],
    hot_links: Array.isArray(payload.hot_links) ? payload.hot_links : [],
    learning: Array.isArray(payload.learning) ? payload.learning : [],
  };
}

const COPY = {
  traveling: "\u6b63\u5728\u7a7f\u8d8a",
  leaving: "\u6b63\u5728\u79bb\u5f00\u5df2\u77e5\u4e16\u754c",
  aligning: "\u4eca\u5929\u7684\u4ee3\u7801\u3001AI\u3001\u5386\u53f2\u4e0e\u5b66\u4e60\u7ebf\u7d22\uff0c\u6b63\u5728\u5bf9\u9f50\u3002",
  enter: "\u76f4\u63a5\u8fdb\u5165",
  error: "\u65b0\u4e16\u754c\u60c5\u62a5\u6682\u65f6\u65e0\u6cd5\u5230\u8fbe\u3002",
  github: "GitHub \u70ed\u95e8",
  news: "AI \u65b0\u95fb",
  hot: "\u6bcf\u65e5\u70ed\u699c",
  learning: "\u4eca\u65e5\u5b66\u4e60",
  projects: "\u4e2a\u9879\u76ee",
  highlights: "\u6761\u91cd\u70b9",
  sites: "\u4e2a\u7ad9\u70b9",
  points: "\u4e2a\u77e5\u8bc6\u70b9",
  githubCoordinates: "GitHub \u70ed\u95e8\u5750\u6807",
  githubHint: "\u4eca\u65e5\u503c\u5f97\u5173\u6ce8\u7684 3 \u4e2a\u9879\u76ee",
  githubEmpty: "GitHub \u4eca\u65e5\u6682\u672a\u8fd4\u56de\u9879\u76ee\uff0c\u7a0d\u540e\u5237\u65b0\u3002",
  aiSignals: "AI \u91cd\u8981\u4fe1\u53f7",
  aiHint: "5 \u6761\u91cd\u8981\u6d88\u606f\uff0c\u53ea\u7559\u91cd\u70b9",
  hotCoordinates: "\u4eca\u65e5\u7f51\u7edc\u70ed\u699c",
  hotHint: "\u4e00\u6b21\u6253\u5f00\u4e0d\u540c\u793e\u533a\u7684\u5f53\u65e5\u70ed\u70b9",
  learningMap: "\u4eca\u65e5\u5b66\u4e60\u5730\u56fe",
  learningHint: "10 \u4e2a\u5b66\u4e60\u77e5\u8bc6\u70b9",
  knowledgePoint: "\u77e5\u8bc6\u70b9",
};

const STAR_STREAKS = Array.from({ length: 56 }, (_, index) => ({
  "--angle": `${index * 6.43}deg`,
  "--delay": `${(index % 8) * -0.11}s`,
  "--length": `${110 + (index % 6) * 28}px`,
} as CSSProperties));

function formatDate(value?: string | null) {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value.slice(0, 10) : parsed.toLocaleDateString("zh-CN");
}

export function NewWorldContent() {
  const [payload, setPayload] = useState<NewWorldPayload | null>(null);
  const [traveling, setTraveling] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<NewWorldTab>("github");
  const [transitionStyle, setTransitionStyle] = useState<CSSProperties>({});
  const initialLoadStarted = useRef(false);

  const load = useCallback(async (force = false) => {
    setLoading(true);
    setError("");
    try {
      const nextPayload = await fetchApiClient<Partial<NewWorldPayload>>(
        `/api/new-world${force ? "?force=true" : ""}`,
        { retries: 1, timeoutMs: 70000 },
      );
      setPayload(normalizePayload(nextPayload));
    } catch {
      setError(COPY.error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!initialLoadStarted.current) {
      initialLoadStarted.current = true;
      load();
    }
    const timer = window.setTimeout(() => setTraveling(false), 2800);
    return () => window.clearTimeout(timer);
  }, [load]);

  if (traveling) {
    return (
      <main
        className="world-transition"
        onPointerMove={(event) => {
          const x = event.clientX / window.innerWidth - 0.5;
          const y = event.clientY / window.innerHeight - 0.5;
          setTransitionStyle({ "--portal-x": `${x * 18}deg`, "--portal-y": `${y * -14}deg` } as CSSProperties);
        }}
        style={transitionStyle}
      >
        <div className="world-space-grid" />
        <div className="world-nebula" />
        <div className="world-depth-tunnel">{Array.from({ length: 9 }, (_, index) => <i key={index} style={{ "--depth": index } as CSSProperties} />)}</div>
        <div className="warp-stars">{STAR_STREAKS.map((style, index) => <i key={index} style={style} />)}</div>
        <div className="world-fragments">{Array.from({ length: 12 }, (_, index) => <i key={index} style={{ "--fragment": index, "--fragment-size": `${10 + index % 4 * 5}px`, "--fragment-left": `${8 + index * 7}%`, "--fragment-top": `${12 + index % 5 * 16}%` } as CSSProperties} />)}</div>
        <div className="world-portal"><span /><span /><span /><b /><div><Orbit size={34} /><strong>{COPY.traveling}</strong><small>{COPY.leaving}</small></div></div>
        <p>{COPY.aligning}</p>
        <button onClick={() => setTraveling(false)} type="button">{COPY.enter}</button>
      </main>
    );
  }

  if (error && !payload) return <ErrorState message={error} retry={() => load()} />;

  return (
    <main className="new-world-page">
      <div className="world-aurora aurora-one" />
      <div className="world-aurora aurora-two" />
      <nav aria-label="New world categories" className="world-tabs">
        <button aria-selected={activeTab === "github"} className={activeTab === "github" ? "active" : ""} onClick={() => setActiveTab("github")} role="tab" type="button"><Github size={20} /><span><strong>{COPY.github}</strong><small>{payload?.github.length || 3} {COPY.projects}</small></span></button>
        <button aria-selected={activeTab === "news"} className={activeTab === "news" ? "active" : ""} onClick={() => setActiveTab("news")} role="tab" type="button"><Newspaper size={20} /><span><strong>{COPY.news}</strong><small>{payload?.ai_news.length || 5} {COPY.highlights}</small></span></button>
        <button aria-selected={activeTab === "hot"} className={activeTab === "hot" ? "active" : ""} onClick={() => setActiveTab("hot")} role="tab" type="button"><Globe2 size={20} /><span><strong>{COPY.hot}</strong><small>{payload?.hot_links.length || 8} {COPY.sites}</small></span></button>
        <button aria-selected={activeTab === "learning"} className={activeTab === "learning" ? "active" : ""} onClick={() => setActiveTab("learning")} role="tab" type="button"><BrainCircuit size={20} /><span><strong>{COPY.learning}</strong><small>{payload?.learning.length || 10} {COPY.points}</small></span></button>
      </nav>

      <div className="world-tab-stage">
        {activeTab === "github" ? <section className="world-section github-frontier world-tab-panel">
          <div className="world-section-head"><div><span>01</span><Github size={20} /><h2>{COPY.githubCoordinates}</h2></div><p>{COPY.githubHint}</p></div>
          <div className="github-world-grid">
            {(payload?.github || []).map((project, index) => <a href={project.url} key={project.name} rel="noreferrer" target="_blank"><div className="repo-orbit"><i /><strong>0{index + 1}</strong></div><span>{project.language || "OPEN SOURCE"}</span><h3>{project.name}</h3><p>{project.description}</p><div className="repo-topics">{project.topics.slice(0, 3).map((topic) => <small key={topic}>#{topic}</small>)}</div><footer><span><Flame size={14} />{project.stars.toLocaleString()} stars</span><ArrowUpRight size={18} /></footer></a>)}
            {!loading && !payload?.github.length ? <div className="world-empty">{COPY.githubEmpty}</div> : null}
          </div>
        </section> : null}

        {activeTab === "news" ? <section className="world-section ai-signal world-tab-panel">
          <div className="world-section-head"><div><span>02</span><Newspaper size={20} /><h2>{COPY.aiSignals}</h2></div><p>{COPY.aiHint}</p></div>
          <div className="ai-signal-list">{(payload?.ai_news || []).map((item, index) => <a href={item.url} key={`${item.source}-${item.title}`} rel="noreferrer" target="_blank"><strong>0{index + 1}</strong><div><span>{item.source} {formatDate(item.published_at) ? `\u00b7 ${formatDate(item.published_at)}` : ""}</span><h3>{item.title}</h3><p>{item.summary}</p></div><ArrowUpRight size={19} /></a>)}</div>
        </section> : null}

        {activeTab === "hot" ? <section className="world-section hot-links-vault world-tab-panel">
          <div className="world-section-head"><div><span>03</span><Globe2 size={20} /><h2>{COPY.hotCoordinates}</h2></div><p>{COPY.hotHint}</p></div>
          <div className="hot-link-list">{(payload?.hot_links || []).map((item) => <a href={item.url} key={item.source} rel="noreferrer" target="_blank"><HotSourceIcon source={item.source} /><strong>{item.source}</strong><div><h3>{item.title}</h3><p>{item.summary}</p></div><ArrowUpRight size={18} /></a>)}</div>
        </section> : null}

        {activeTab === "learning" ? <section className="world-section learning-map world-tab-panel">
          <div className="world-section-head"><div><span>04</span><BrainCircuit size={20} /><h2>{COPY.learningMap}</h2></div><p>{COPY.learningHint}</p></div>
          <div className="learning-node-list">{(payload?.learning || []).map((item, index) => <a href={item.url} key={`${item.category}-${item.title}`} rel="noreferrer" target="_blank"><span>{item.category}</span><div><small>{COPY.knowledgePoint} {String(index + 1).padStart(2, "0")}</small><h3>{item.title}</h3><p>{item.focus}</p></div><Sparkles size={18} /></a>)}</div>
        </section> : null}
      </div>
    </main>
  );
}
