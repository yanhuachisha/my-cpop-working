import { BrainCircuit, Github, Globe2, Newspaper } from "lucide-react";
import { COPY } from "../constants";
import { NewWorldPayload, NewWorldTab } from "../types";

type Props = { activeTab: NewWorldTab; onChange: (tab: NewWorldTab) => void; payload: NewWorldPayload | null };

export function WorldTabs({ activeTab, onChange, payload }: Props) {
  const tabs = [
    { id: "github" as const, icon: Github, label: COPY.github, count: payload?.github.length || 3, suffix: COPY.projects },
    { id: "news" as const, icon: Newspaper, label: COPY.news, count: payload?.ai_news.length || 5, suffix: COPY.highlights },
    { id: "hot" as const, icon: Globe2, label: COPY.hot, count: payload?.hot_links.length || 8, suffix: COPY.sites },
    { id: "learning" as const, icon: BrainCircuit, label: COPY.learning, count: payload?.learning.length || 10, suffix: COPY.points },
  ];
  return <nav aria-label="New world categories" className="world-tabs">{tabs.map(({ id, icon: Icon, label, count, suffix }) => <button aria-selected={activeTab === id} className={activeTab === id ? "active" : ""} key={id} onClick={() => onChange(id)} role="tab" type="button"><Icon size={20} /><span><strong>{label}</strong><small>{count} {suffix}</small></span></button>)}</nav>;
}
