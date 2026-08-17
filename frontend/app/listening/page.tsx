'use client';

import {
  BookOpenText,
  Bot,
  ChevronRight,
  Disc3,
  ExternalLink,
  Headphones,
  LoaderCircle,
  MessageCircleMore,
  Music2,
  RefreshCw,
  Send,
  Sparkles,
  WandSparkles,
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

type LyricAnalysis = {
  summary: string;
  imagery: string[];
  emotion: string[];
  craft: string[];
  listening_questions: string[];
  copyright_note: string;
};

type ChatSource = { name: string; url: string };
type ChatMessage = { role: "agent" | "user"; content: string; tools?: string[]; sources?: ChatSource[]; saved_at?: string };

export default function ListeningRoomPage() {
  const activeTrackKey = useRef<string | null>(null);
  const detectedTrackKey = useRef("idle");
  const storyLoadingKey = useRef<string | null>(null);
  const contextLoading = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const [context, setContext] = useState<ListeningContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [storyLoading, setStoryLoading] = useState(false);
  const [opening, setOpening] = useState(false);
  const [activePanel, setActivePanel] = useState<"story" | "lyrics">("story");
  const [excerpt, setExcerpt] = useState("");
  const [analysis, setAnalysis] = useState<LyricAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [lyricSaved, setLyricSaved] = useState(false);
  const [question, setQuestion] = useState("");
  const [chatting, setChatting] = useState(false);
  const [showIntro, setShowIntro] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const loadStory = useCallback(async (track: TrackState, trackKey: string) => {
    if (!track.title || storyLoadingKey.current === trackKey) return;
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
      detectedTrackKey.current = trackKey;
      setContext(nextContext);
      if (nextContext.current.title && !nextContext.story) void loadStory(nextContext.current, trackKey);
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
    setExcerpt("");
    setAnalysis(null);
    setLyricSaved(false);
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
        if (activeTrackKey.current === requestedTrackKey && saved.messages.length) setMessages(saved.messages);
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

  const analyzeExcerpt = async () => {
    if (!excerpt.trim()) return;
    setAnalyzing(true);
    try {
      const result = await fetchApiClient<LyricAnalysis>("/api/listening/analyze-lyrics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ excerpt, song_title: current?.title, artist: current?.artist }),
      });
      setAnalysis(result);
    } finally {
      setAnalyzing(false);
    }
  };

  const saveLyric = async () => {
    if (!excerpt.trim()) return;
    await fetchApiClient("/api/listener/lyrics", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ excerpt, song_title: current?.title, artist: current?.artist, note: analysis?.summary }),
    });
    setLyricSaved(true);
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
          lyric_excerpt: excerpt || undefined,
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
        </aside>

        <section className="room-content">
          <div className="room-tabs">
            <button className={activePanel === "story" ? "active" : ""} onClick={() => setActivePanel("story")} type="button"><BookOpenText size={16} />歌曲简介</button>
            <button className={activePanel === "lyrics" ? "active" : ""} onClick={() => setActivePanel("lyrics")} type="button"><WandSparkles size={16} />品味歌词</button>
          </div>

          {activePanel === "story" ? (
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
          ) : (
            <div className="lyrics-view">
              <span className="story-type">LYRIC READING</span>
              <h2>放进一句让你停下来的歌词。</h2>
              <p>我们只分析你主动提供的短句，不补全或存储完整歌词。</p>
              <textarea maxLength={500} onChange={(event) => { setExcerpt(event.target.value); setLyricSaved(false); }} placeholder="例如：写下一句你正在反复琢磨的歌词……" value={excerpt} />
              <div className="lyrics-actions"><span>{excerpt.length}/500</span><button disabled={!excerpt.trim() || analyzing} onClick={analyzeExcerpt} type="button">{analyzing ? <LoaderCircle className="spin-icon" size={16} /> : <Sparkles size={16} />}开始品读</button></div>
              {analysis ? (
                <div className="analysis-card">
                  <h3>{analysis.summary}</h3>
                  <div className="analysis-columns">
                    <div><span>画面</span>{analysis.imagery.map((item) => <p key={item}>{item}</p>)}</div>
                    <div><span>情绪</span>{analysis.emotion.map((item) => <p key={item}>{item}</p>)}</div>
                    <div><span>写法</span>{analysis.craft.map((item) => <p key={item}>{item}</p>)}</div>
                  </div>
                  <div className="analysis-save-row"><small>{analysis.copyright_note}</small><button className={lyricSaved ? "saved" : ""} onClick={saveLyric} type="button">{lyricSaved ? "\u5df2\u6536\u85cf\u5230\u6807\u672c\u9986" : "\u6536\u85cf\u8fd9\u53e5"}</button></div>
                </div>
              ) : null}
            </div>
          )}
        </section>
        </section>

        <aside className="room-agent room-panel">
          <div className="agent-head"><div><Bot size={19} /><span>音乐陪伴</span></div><i /></div>
          <div className="agent-context"><span>正在陪你听</span><strong>{displayTitle}</strong><p>{current?.artist ? `${current.artist} · 对话只属于这一首歌` : "播放后开始一段新的对话"}</p></div>
          <div className="agent-messages">
            {messages.map((message, index) => (
              <div className={`agent-message ${message.role}`} key={`${message.role}-${index}`}>
                <div className="agent-message-avatar">{message.role === "agent" ? <Bot size={15} /> : "你"}</div>
                <div className="agent-message-column">
                  <span className="agent-message-author">{message.role === "agent" ? "音乐陪伴" : "你"}</span>
                  <div className="agent-message-bubble"><p>{message.content}</p>{message.sources?.length ? <div className="agent-message-sources">{message.sources.slice(0, 3).map((source) => <a href={source.url} key={source.url} rel="noreferrer" target="_blank"><ExternalLink size={11} />{source.name}</a>)}</div> : null}</div>
                </div>
              </div>
            ))}
            {chatting ? <div className="agent-message agent"><div className="agent-message-avatar"><Bot size={15} /></div><div className="agent-message-column"><span className="agent-message-author">音乐陪伴</span><div className="agent-message-bubble agent-thinking"><i /><i /><i /></div></div></div> : null}
            <div ref={messagesEndRef} />
          </div>
          <div className="quick-prompts">
            {(context?.quick_prompts || []).slice(0, 4).map((prompt) => <button key={prompt} onClick={() => askAgent(prompt)} type="button">{prompt}<ChevronRight size={13} /></button>)}
          </div>
          <div className="agent-input">
            <MessageCircleMore size={17} />
            <input onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") askAgent(); }} placeholder="说说你此刻在这首歌里听见了什么……" value={question} />
            <button disabled={!question.trim() || chatting} onClick={() => askAgent()} type="button"><Send size={15} /></button>
          </div>
        </aside>
      </section>
    </main>
  );
}
