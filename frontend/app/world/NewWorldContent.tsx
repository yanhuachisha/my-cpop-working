'use client';

import "../new-world.css";
import "../new-world-overrides.css";
import { CSSProperties, PointerEvent, useEffect, useState } from "react";
import { ErrorState } from "../../components/ErrorState";
import { COPY } from "./constants";
import { GithubSection, HotLinksSection, LearningSection, NewsSection } from "./components/WorldSections";
import { WorldTabs } from "./components/WorldTabs";
import { WorldTransition } from "./components/WorldTransition";
import { useNewWorldData } from "./hooks/useNewWorldData";
import { NewWorldTab } from "./types";

export function NewWorldContent() {
  const { error, load, loading, payload } = useNewWorldData();
  const [traveling, setTraveling] = useState(true);
  const [activeTab, setActiveTab] = useState<NewWorldTab>("github");
  const [transitionStyle, setTransitionStyle] = useState<CSSProperties>({});

  useEffect(() => {
    const timer = window.setTimeout(() => setTraveling(false), 2800);
    return () => window.clearTimeout(timer);
  }, []);

  const handlePointerMove = (event: PointerEvent<HTMLElement>) => {
    const x = event.clientX / window.innerWidth - 0.5;
    const y = event.clientY / window.innerHeight - 0.5;
    setTransitionStyle({ "--portal-x": `${x * 18}deg`, "--portal-y": `${y * -14}deg` } as CSSProperties);
  };

  if (traveling) return <WorldTransition onEnter={() => setTraveling(false)} onPointerMove={handlePointerMove} style={transitionStyle} />;
  if (error && !payload) return <ErrorState message={error || COPY.error} retry={() => void load()} />;

  return <main className="new-world-page"><div className="world-aurora aurora-one" /><div className="world-aurora aurora-two" /><WorldTabs activeTab={activeTab} onChange={setActiveTab} payload={payload} /><div className="world-tab-stage">{activeTab === "github" ? <GithubSection loading={loading} payload={payload} /> : null}{activeTab === "news" ? <NewsSection payload={payload} /> : null}{activeTab === "hot" ? <HotLinksSection payload={payload} /> : null}{activeTab === "learning" ? <LearningSection payload={payload} /> : null}</div></main>;
}
