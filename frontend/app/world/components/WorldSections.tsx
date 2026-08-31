import { ArrowUpRight, BrainCircuit, Flame, Github, Globe2, Newspaper, Sparkles } from "lucide-react";
import { cleanMarkdownText } from "../../../lib/markdown";
import { COPY, formatDate, HOT_SOURCE_ICONS } from "../constants";
import { NewWorldPayload } from "../types";

function HotSourceIcon({ source }: { source: string }) {
  const icon = HOT_SOURCE_ICONS[source] || { fallback: source.slice(0, 1), url: "" };
  return <span className="hot-source-icon"><b>{icon.fallback}</b>{icon.url ? <img alt="" onError={(event) => { event.currentTarget.style.display = "none"; }} src={icon.url} /> : null}</span>;
}

type Props = { loading?: boolean; payload: NewWorldPayload | null };

export function GithubSection({ loading, payload }: Props) {
  return <section className="world-section github-frontier world-tab-panel"><div className="world-section-head"><div><span>01</span><Github size={20} /><h2>{COPY.githubCoordinates}</h2></div><p>{COPY.githubHint}</p></div><div className="github-world-grid">{(payload?.github || []).map((project, index) => <a href={project.url} key={project.name} rel="noreferrer" target="_blank"><div className="repo-orbit"><i /><strong>0{index + 1}</strong></div><span>{cleanMarkdownText(project.language || "OPEN SOURCE")}</span><h3>{cleanMarkdownText(project.name)}</h3><p>{cleanMarkdownText(project.description)}</p><div className="repo-topics">{project.topics.slice(0, 3).map((topic) => <small key={topic}>#{cleanMarkdownText(topic)}</small>)}</div><footer><span><Flame size={14} />{project.stars.toLocaleString()} stars</span><ArrowUpRight size={18} /></footer></a>)}{!loading && !payload?.github.length ? <div className="world-empty">{COPY.githubEmpty}</div> : null}</div></section>;
}

export function NewsSection({ payload }: Props) {
  return <section className="world-section ai-signal world-tab-panel"><div className="world-section-head"><div><span>02</span><Newspaper size={20} /><h2>{COPY.aiSignals}</h2></div><p>{COPY.aiHint}</p></div><div className="ai-signal-list">{(payload?.ai_news || []).map((item, index) => <a href={item.url} key={`${item.source}-${item.title}`} rel="noreferrer" target="_blank"><strong>0{index + 1}</strong><div><span>{cleanMarkdownText(item.source)} {formatDate(item.published_at) ? `· ${formatDate(item.published_at)}` : ""}</span><h3>{cleanMarkdownText(item.title)}</h3><p>{cleanMarkdownText(item.summary)}</p></div><ArrowUpRight size={19} /></a>)}</div></section>;
}

export function HotLinksSection({ payload }: Props) {
  return <section className="world-section hot-links-vault world-tab-panel"><div className="world-section-head"><div><span>03</span><Globe2 size={20} /><h2>{COPY.hotCoordinates}</h2></div><p>{COPY.hotHint}</p></div><div className="hot-link-list">{(payload?.hot_links || []).map((item) => <a href={item.url} key={item.source} rel="noreferrer" target="_blank"><HotSourceIcon source={item.source} /><strong>{cleanMarkdownText(item.source)}</strong><div><h3>{cleanMarkdownText(item.title)}</h3><p>{cleanMarkdownText(item.summary)}</p></div><ArrowUpRight size={18} /></a>)}</div></section>;
}

export function LearningSection({ payload }: Props) {
  return <section className="world-section learning-map world-tab-panel"><div className="world-section-head"><div><span>04</span><BrainCircuit size={20} /><h2>{COPY.learningMap}</h2></div><p>{COPY.learningHint}</p></div><div className="learning-node-list">{(payload?.learning || []).map((item, index) => <a href={item.url} key={`${item.category}-${item.title}`} rel="noreferrer" target="_blank"><span>{cleanMarkdownText(item.category)}</span><div><small>{COPY.knowledgePoint} {String(index + 1).padStart(2, "0")}</small><h3>{cleanMarkdownText(item.title)}</h3><p>{cleanMarkdownText(item.focus)}</p></div><Sparkles size={18} /></a>)}</div></section>;
}
