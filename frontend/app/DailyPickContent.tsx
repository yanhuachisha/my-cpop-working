'use client';

import {
  Bookmark,
  CloudRain,
  Compass,
  ExternalLink,
  Music2,
  Newspaper,
  RefreshCw,
  Sparkles,
  SunMedium,
  Waves,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ErrorState } from "../components/ErrorState";
import { LoadingSpinner } from "../components/Loading";
import { Recording, Artist, fetchApiClient } from "../lib/api";

type TodayPick = {
  role: "main" | "familiar" | "explore";
  role_label: string;
  recording: Recording;
  artist: Artist;
  score: number;
  headline: string;
  explanation: string;
  signals: Record<string, number>;
};

type TodayExperience = {
  today: string;
  active_mode: string;
  greeting: string;
  weather: {
    available: boolean;
    city: string;
    temperature: number | null;
    apparent_temperature?: number | null;
    condition: string;
    kind: string;
    humidity?: number | null;
    is_day: boolean;
  };
  computer: { activity: string; label: string; idle_seconds: number | null; period: string };
  news: { title: string; url: string; publisher: string; published_at?: string | null }[];
  anniversaries: { title: string; artist: string; release_date: string; years: number; distance_days: number }[];
  picks: TodayPick[];
  profile: { listener_type: string; favorite_artist: string; event_count: number; liked_count: number; saved_count: number };
  catalog_size: number;
};

export function DailyPickContent() {
  const initialLoadStarted = useRef(false);
  const [experience, setExperience] = useState<TodayExperience | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, string>>({});
  const [openingId, setOpeningId] = useState<string | null>(null);

  const loadToday = async (explore = false) => {
    setLoading(true);
    setError(null);
    try {
      const seed = explore ? `&seed=${Math.random().toString(36).slice(2)}` : "";
      setExperience(await fetchApiClient<TodayExperience>(`/api/today?user_id=demo&mode=auto${seed}`, {
        retries: 2,
        timeoutMs: 30000,
      }));
    } catch (requestError) {
      const aborted = requestError instanceof DOMException && requestError.name === "AbortError";
      setError(aborted ? "首页数据准备时间较长，请稍后重试" : "今日声景暂时没有连接成功");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    window.localStorage.removeItem("atlas-today-mode");
    loadToday();
  }, []);

  const sendFeedback = async (recordingId: string, action: "like" | "save" | "skip" | "play") => {
    setFeedback((value) => ({ ...value, [recordingId]: action }));
    try {
      await fetchApiClient("/api/listener/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recording_id: recordingId, action, channel: "today" }),
      });
    } catch {
      setFeedback((value) => ({ ...value, [recordingId]: "" }));
    }
  };

  const listenNow = async (pick: TodayPick) => {
    setOpeningId(pick.recording.id);
    try {
      await sendFeedback(pick.recording.id, "play");
      await fetchApiClient("/api/kugou/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: pick.recording.title, artist: pick.artist.name }),
      });
    } catch {} finally {
      setOpeningId(null);
    }
  };

  if (loading) return <LoadingSpinner />;
  if (error || !experience) return <ErrorState message={error || "无法加载今日推荐"} retry={loadToday} />;

  const mainPick = experience.picks[0];
  const WeatherIcon = experience.weather.kind === "clear" ? SunMedium : experience.weather.kind.includes("rain") || experience.weather.kind === "storm" ? CloudRain : Waves;

  if (!mainPick) return <ErrorState message="今天还没有找到合适的歌曲" retry={loadToday} />;

  return (
    <main className="sonic-home">
      <section className="daily-split-stage" data-pointer-reactive data-pointer-strength="0.35">
        <div className="sonic-glow glow-one" /><div className="sonic-glow glow-two" />
        <div className="daily-left-panel">
          <div className="sonic-discovery-label"><span><Compass size={14} />每日发现</span><small>DAILY DISCOVERY</small></div>
          <div className="daily-weather-card">
            <div><WeatherIcon size={34} /><span>{experience.weather.city}</span></div>
            <strong>{experience.weather.temperature ?? "—"}<sup>°</sup></strong>
            <p>{experience.weather.condition} · 体感 {experience.weather.apparent_temperature ?? "—"}°</p>
            <small>湿度 {experience.weather.humidity ?? "—"}% · {experience.computer.label}</small>
          </div>
          <div className="daily-song-card">
            <span>今天只认真推荐一首</span>
            <h1>{mainPick.recording.title}</h1>
            <h2>{mainPick.artist.name}</h2>
            <p>{mainPick.headline}</p>
            <div className="sonic-actions"><button className={openingId === mainPick.recording.id ? "is-playing" : ""} disabled={openingId === mainPick.recording.id} onClick={() => listenNow(mainPick)} type="button"><Music2 size={18} />{openingId === mainPick.recording.id ? "正在打开酷狗" : "现在就听"}</button><button className={feedback[mainPick.recording.id] === "save" ? "is-playing" : ""} onClick={() => sendFeedback(mainPick.recording.id, "save")} type="button"><Bookmark size={17} />收藏</button><Link href="/agent"><Sparkles size={17} />聊聊这首歌</Link><button className="daily-swap-button" onClick={() => loadToday(true)} title="换一首" type="button"><RefreshCw size={17} />换一首</button></div>
          </div>
        </div>
        <aside className="daily-news-panel">
          <header><div><Newspaper size={20} /><span><strong>今日华语乐坛</strong><small>每天更新的音乐新闻</small></span></div><time>{experience.today}</time></header>
          <div className="daily-news-list">{experience.news.slice(0, 6).map((article, index) => <a href={article.url} key={article.url} rel="noreferrer" target="_blank"><i>{String(index + 1).padStart(2, "0")}</i><span><strong>{article.title}</strong><small>{article.publisher}</small></span><ExternalLink size={15} /></a>)}</div>
          {!experience.news.length ? <div className="daily-news-empty">今天的新闻源暂时没有返回内容，稍后再来看看。</div> : null}
        </aside>
      </section>
    </main>
  );
}
