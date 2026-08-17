'use client';

import {
  Bot,
  ChevronRight,
  Clock3,
  Disc3,
  ExternalLink,
  Headphones,
  LoaderCircle,
  MessageCircleMore,
  Music2,
  RefreshCw,
  Send,
  Trophy,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchApiClient } from "../../lib/api";

type TrackState = {
  status: "live" | "idle";
  available: boolean;
  title: string | null;
  artist: string | null;
  album: string | null;
  year: number | null;
  source: string;
};

type SongStory = {
  title: string;
  subtitle: string;
  narrative: string;
  themes: string[];
  listening_points: string[];
  story_type: string;
  facts: string[];
  source_urls: string[];
};

type ListeningContext = {
  current: TrackState;
  story: SongStory | null;
  quick_prompts: string[];
  profile: {
    favorite_artist: string;
    listener_type: string;
    preferences: string[];
  };
};

type ChatSource = { name: string; url: string };
type ChatMessage = { role: "agent" | "user"; content: string; tools?: string[]; sources?: ChatSource[]; saved_at?: string };
type ListeningRankItem = {
  recording_id: string;
  title: string;
  artist: string;
  seconds: number;
  formatted_duration: string;
  last_listened_at: string | null;
};
type TodayListeningStats = {
  date: string;
  total_seconds: number;
  formatted_duration: string;
  track_count: number;
  ranking: ListeningRankItem[];
};

export default function ListeningRoomPage() {
  const activeTrackKey = useRef<string | null>(null);
  const detectedTrackKey = useRef("idle");
  const storyLoadingKey = useRef<string | null>(null);
  const lockedStory = useRef<{ trackKey: string; story: SongStory } | null>(null);
  const contextLoading = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const [context, setContext] = useState<ListeningContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [storyLoading, setStoryLoading] = useState(false);
  const [opening, setOpening] = useState(false);
  const [question, setQuestion] = useState("");
  const [chatting, setChatting] = useState(false);
  const [showIntro, setShowIntro] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [restoredConversation, setRestoredConversation] = useState(false);
  const [todayStats, setTodayStats] = useState<TodayListeningStats | null>(null);
  const [showTodayRanking, setShowTodayRanking] = useState(false);

  const loadStory = useCallback(async (track: TrackState, trackKey: string) => {
    if (!track.title || storyLoadingKey.current === trackKey || lockedStory.current?.trackKey === trackKey) return;
    storyLoadingKey.current = trackKey;
    setStoryLoading(true);
    try {
      const story = await fetchApiClient<SongStory>("/api/listening/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: track.title, artist: track.artist, album: track.album, year: track.year }),
        retries: 0,
        timeoutMs: 70000,
      });
      if (detectedTrackKey.current !== trackKey) return;
      lockedStory.current = { trackKey, story };
      setContext((currentContext) => currentContext ? { ...currentContext, story } : currentContext);
    } catch {
    } finally {
      if (storyLoadingKey.current === trackKey) storyLoadingKey.current = null;
      if (detectedTrackKey.current === trackKey) setStoryLoading(false);
    }
  }, []);

  const loadContext = useCallback(async () => {
    if (contextLoading.current) return;
    contextLoading.current = true;
    try {
      const nextContext = await fetchApiClient<ListeningContext>("/api/listening/context", { retries: 0, timeoutMs: 5000 });
      const trackKey = nextContext.current.title ? `${nextContext.current.title}::${nextContext.current.artist || ""}` : "idle";
      const trackChanged = detectedTrackKey.current !== trackKey;
      if (trackChanged) {
        lockedStory.current = null;
        storyLoadingKey.current = null;
        setStoryLoading(false);
      }
      detectedTrackKey.current = trackKey;
      if (nextContext.story && !lockedStory.current) lockedStory.current = { trackKey, story: nextContext.story };
      const stableStory = lockedStory.current?.trackKey === trackKey ? lockedStory.current.story : nextContext.story;
      setContext({ ...nextContext, story: stableStory });
      if (nextContext.current.title && !stableStory) void loadStory(nextContext.current, trackKey);
      if (!nextContext.current.title) setStoryLoading(false);
    } catch {
    } finally {
      contextLoading.current = false;
      setLoading(false);
    }
  }, [loadStory]);

  useEffect(() => {
    loadContext();
    const timer = window.setInterval(() => loadContext(), 1000);
    return () => window.clearInterval(timer);
  }, [loadContext]);

  const loadTodayStats = useCallback(async () => {
    try {
      const stats = await fetchApiClient<TodayListeningStats>("/api/listening/today-stats", { retries: 1, timeoutMs: 5000 });
      setTodayStats(stats);
    } catch {
    }
  }, []);

  useEffect(() => {
    void loadTodayStats();
    const timer = window.setInterval(() => void loadTodayStats(), 10000);
    return () => window.clearInterval(timer);
  }, [loadTodayStats]);

  useEffect(() => {
    const timer = window.setTimeout(() => setShowIntro(false), 2200);
    return () => window.clearTimeout(timer);
  }, []);

  const current = context?.current;
  const statusText = current?.status === "live" ? "酷狗实时同步" : "等待酷狗播放";
  const displayTitle = current?.title || "让音乐开始流动";
  const displayArtist = current?.artist || "打开酷狗并播放一首歌";

  useEffect(() => {
    const trackKey = current?.title ? `${current.title}::${current.artist || ""}` : "idle";
    if (activeTrackKey.current === trackKey) return;
    activeTrackKey.current = trackKey;
    setRestoredConversation(false);
    const welcome: ChatMessage = {
      role: "agent",
      content: current?.title
        ? `正在陪你听《${current.title}》${current.artist ? `，演唱是${current.artist}` : ""}。你此刻听到什么，都可以直接告诉我。`
        : "等你在酷狗播放一首歌，我会跟随当前歌曲开始陪听。",
    };
    setMessages([welcome]);
    if (!current?.title) return;
    const requestedTrackKey = trackKey;
    const query = new URLSearchParams({ song_title: current.title });
    if (current.artist) query.set("artist", current.artist);
    fetchApiClient<{ messages: ChatMessage[] }>(`/api/listening/conversation?${query.toString()}`, { retries: 2, timeoutMs: 12000 })
      .then((saved) => {
        if (activeTrackKey.current === requestedTrackKey && saved.messages.length) {
          setMessages(saved.messages);
          setRestoredConversation(true);
        }
      })
      .catch(() => undefined);
  }, [current?.artist, current?.title]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatting, messages]);
  const openKugou = async () => {
    setOpening(true);
    try {
      await fetchApiClient("/api/kugou/open", { method: "POST" });
      window.setTimeout(() => loadContext(), 1200);
    } finally {
      setOpening(false);
    }
  };

  const askAgent = async (prompt = question) => {
    const nextQuestion = prompt.trim();
    if (!nextQuestion || chatting) return;
    setQuestion("");
    setMessages((items) => [...items, { role: "user", content: nextQuestion }]);
    setChatting(true);
    try {
      const result = await fetchApiClient<{ answer: string; tools_used: string[]; sources: ChatSource[] }>("/api/listening/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: nextQuestion,
          song_title: current?.title,
          artist: current?.artist,
          recent_messages: messages.slice(-8).map(({ role, content }) => ({ role, content })),
        }),
      });
      setMessages((items) => [...items, { role: "agent", content: result.answer, tools: result.tools_used, sources: result.sources }]);
    } catch {
      setMessages((items) => [...items, { role: "agent", content: "音乐陪伴暂时没有回应，请确认服务仍在运行。" }]);
    } finally {
      setChatting(false);
    }
  };

  const vinylClass = useMemo(() => `room-vinyl${current?.status === "live" ? " spinning" : ""}`, [current?.status]);

  return (
    <main className="listening-room-page">
      <section className={`room-heading ${showIntro ? "is-visible" : "is-hidden"}`}>
        <div>
          <p className="atlas-eyebrow"><span />LISTENING ROOM</p>
          <h1>听见歌里，<em>没有说完的话。</em></h1>
        </div>
      </section>

      <section className="room-grid">
        <section className="room-listening-main room-panel">
        <aside className="room-now-playing">
          <div className="room-panel-label"><Headphones size={16} /><span>NOW PLAYING</span><i className={current?.status === "live" ? "online" : ""} /></div>
          <div className="room-vinyl-stage">
            <div className="room-orbit" />
            <div className={vinylClass}><div><Music2 size={23} /></div></div>
            <div className="room-needle" />
          </div>
          <div className="room-track-copy">
            <span className="room-status">{statusText}</span>
            <h2>{loading ? "正在连接…" : displayTitle}</h2>
            <p>{displayArtist}{current?.album ? ` · ${current.album}` : ""}{current?.year ? ` · ${current.year}` : ""}</p>
          </div>
          <div className="room-equalizer" aria-hidden="true">{Array.from({ length: 22 }).map((_, index) => <i key={index} style={{ animationDelay: `${index * 55}ms` }} />)}</div>
          <div className="room-player-actions">
            <button className="room-primary-button" disabled={opening} onClick={openKugou} type="button"><ExternalLink size={16} />{opening ? "正在打开" : "打开酷狗"}</button>
            <button className="room-icon-button" onClick={() => loadContext()} type="button" aria-label="刷新当前歌曲"><RefreshCw size={17} /></button>
          </div>
          <button className="room-today-card" onClick={() => setShowTodayRanking(true)} type="button">
            <span className="room-today-icon"><Clock3 size={16} /></span>
            <span className="room-today-copy">
              <small>今日听歌时间</small>
              <strong>{todayStats?.formatted_duration || "0 秒"}</strong>
            </span>
            <span className="room-today-rank"><Trophy size={13} />{todayStats?.track_count || 0} 首<ChevronRight size={14} /></span>
          </button>
        </aside>

        <section className="room-content">
          <div className="story-view">
            {context?.story ? (
              <>
                <div className="story-intro-label"><span>情绪画像</span><small>EMOTIONAL PORTRAIT</small></div>
                <h2>{context.story.subtitle}</h2>
                <p className="story-narrative">{context.story.narrative}</p>
                {context.story.facts.length ? <div className="story-facts">{context.story.facts.map((fact) => <span key={fact}>{fact}</span>)}</div> : null}
                {context.story.source_urls.length ? <div className="story-sources">{context.story.source_urls.map((url) => <a href={url} key={url} rel="noreferrer" target="_blank"><ExternalLink size={13} />查看资料来源</a>)}</div> : null}
                <div className="listening-points">
                  <h3>这一遍，可以这样听</h3>
                  {context.story.listening_points.map((point, index) => <div key={point}><span>0{index + 1}</span><p>{point}</p></div>)}
                </div>
              </>
            ) : current?.title && storyLoading ? (
              <div className="room-empty"><LoaderCircle className="spin-icon" size={38} /><h2>歌曲已经同步</h2><p>正在补全这首歌的情绪画像，不影响继续识别下一首。</p></div>
            ) : (
              <div className="room-empty"><Disc3 size={42} /><h2>等待一首歌进入房间</h2><p>播放歌曲后，音乐陪伴会和你一起慢慢听懂它。</p></div>
            )}
          </div>
        </section>
        </section>

        <aside className="room-agent room-panel">
          <div className="companion-head">
            <div className="companion-identity"><span><Bot size={18} /></span><div><strong>音乐陪伴</strong><small>{current?.title ? `${displayTitle}${current.artist ? ` · ${current.artist}` : ""}` : "等待一首歌开始"}</small></div></div>
            <div className={`companion-live${restoredConversation ? " restored" : ""}`}><i />{restoredConversation ? "记忆已唤醒" : "正在陪听"}</div>
          </div>
          <div className="companion-messages">
            {messages.map((message, index) => (
              <div className={`companion-turn ${message.role}`} key={`${message.role}-${index}`}>
                {message.role === "agent" ? <div className="companion-avatar"><Bot size={14} /></div> : null}
                <div className="companion-copy">
                  <span>{message.role === "agent" ? "音乐陪伴" : "你"}</span>
                  <div className="companion-bubble"><p>{message.content}</p>{message.sources?.length ? <div className="agent-message-sources">{message.sources.slice(0, 3).map((source) => <a href={source.url} key={source.url} rel="noreferrer" target="_blank"><ExternalLink size={11} />{source.name}</a>)}</div> : null}</div>
                </div>
              </div>
            ))}
            {chatting ? <div className="companion-turn agent"><div className="companion-avatar"><Bot size={14} /></div><div className="companion-copy"><span>音乐陪伴</span><div className="companion-bubble companion-thinking"><i /><i /><i /></div></div></div> : null}
            <div ref={messagesEndRef} />
          </div>
          <div className="companion-actions">
            {(context?.quick_prompts || []).slice(0, 4).map((prompt) => <button key={prompt} onClick={() => askAgent(prompt)} type="button">{prompt}</button>)}
          </div>
          <div className="companion-composer">
            <MessageCircleMore size={17} />
            <textarea aria-label="和音乐陪伴对话" onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); askAgent(); } }} placeholder="说说你此刻在这首歌里听见了什么……" rows={1} value={question} />
            <button disabled={!question.trim() || chatting} onClick={() => askAgent()} type="button" aria-label="发送"><Send size={16} /></button>
          </div>
        </aside>
      </section>
      {showTodayRanking ? (
        <div className="today-ranking-overlay" onClick={() => setShowTodayRanking(false)} role="presentation">
          <section aria-labelledby="today-ranking-title" aria-modal="true" className="today-ranking-dialog" onClick={(event) => event.stopPropagation()} role="dialog">
            <header>
              <div><span><Trophy size={18} /></span><div><small>TODAY&apos;S LISTENING</small><h2 id="today-ranking-title">今日听歌排行</h2></div></div>
              <button aria-label="关闭今日听歌排行" onClick={() => setShowTodayRanking(false)} type="button"><X size={18} /></button>
            </header>
            <div className="today-ranking-summary"><Clock3 size={17} /><span>今天已经听了</span><strong>{todayStats?.formatted_duration || "0 秒"}</strong><small>{todayStats?.track_count || 0} 首歌</small></div>
            <div className="today-ranking-list">
              {todayStats?.ranking.length ? todayStats.ranking.map((item, index) => (
                <article key={item.recording_id}>
                  <span className={`today-ranking-number rank-${index + 1}`}>{String(index + 1).padStart(2, "0")}</span>
                  <div><strong>{item.title}</strong><small>{item.artist}</small></div>
                  <time>{item.formatted_duration}</time>
                </article>
              )) : <div className="today-ranking-empty"><Disc3 size={30} /><p>今天的第一首歌还没开始。</p></div>}
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
