'use client';

import "../listening-notes.css";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchApiClient } from "../../lib/api";
import { CompanionChat } from "./components/CompanionChat";
import { CompanionSettingsPanel } from "./components/CompanionSettingsPanel";
import { NowPlayingPanel } from "./components/NowPlayingPanel";
import { SongStoryPanel } from "./components/SongStoryPanel";
import { TodayRankingDialog } from "./components/TodayRankingDialog";
import { ChatMessage, ChatSource, ListeningContext, ListeningPromptSettings, SongStory, TodayListeningStats, TrackState } from "./types";
import "./listening-room.css";

function createClientMessageId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `listening-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowIso() {
  return new Date().toISOString();
}

export default function ListeningRoomPage() {
  const activeTrackKey = useRef<string | null>(null);
  const detectedTrackKey = useRef("idle");
  const storyLoadingKey = useRef<string | null>(null);
  const lockedStory = useRef<{ trackKey: string; story: SongStory } | null>(null);
  const contextLoading = useRef(false);
  const [context, setContext] = useState<ListeningContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [storyLoading, setStoryLoading] = useState(false);
  const [opening, setOpening] = useState(false);
  const [question, setQuestion] = useState("");
  const [chatting, setChatting] = useState(false);
  const [showIntro, setShowIntro] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [restoredConversation, setRestoredConversation] = useState(false);
  const [restoredConversationAt, setRestoredConversationAt] = useState<string | null>(null);
  const [showDetailedTimes, setShowDetailedTimes] = useState(false);
  const [todayStats, setTodayStats] = useState<TodayListeningStats | null>(null);
  const [showTodayRanking, setShowTodayRanking] = useState(false);
  const [liking, setLiking] = useState(false);
  const [showCompanionSettings, setShowCompanionSettings] = useState(false);
  const [promptSettings, setPromptSettings] = useState<ListeningPromptSettings | null>(null);
  const [corePromptDraft, setCorePromptDraft] = useState("");
  const [promptDraft, setPromptDraft] = useState("");
  const [promptSettingsLoading, setPromptSettingsLoading] = useState(false);
  const [promptSettingsSaving, setPromptSettingsSaving] = useState(false);
  const [promptSettingsError, setPromptSettingsError] = useState<string | null>(null);

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
    void loadContext();
    const timer = window.setInterval(() => void loadContext(), 1000);
    return () => window.clearInterval(timer);
  }, [loadContext]);

  const loadTodayStats = useCallback(async () => {
    try {
      setTodayStats(await fetchApiClient<TodayListeningStats>("/api/listening/today-stats", { retries: 1, timeoutMs: 5000 }));
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
  const displayTitle = current?.title || "让音乐开始流动";
  const displayArtist = current?.artist || "打开酷狗并播放一首歌";

  useEffect(() => {
    const trackKey = current?.title ? `${current.title}::${current.artist || ""}` : "idle";
    if (activeTrackKey.current === trackKey) return;
    activeTrackKey.current = trackKey;
    setRestoredConversation(false);
    setRestoredConversationAt(null);
    const welcome: ChatMessage = {
      role: "agent",
      saved_at: nowIso(),
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
        if (activeTrackKey.current !== requestedTrackKey || !saved.messages.length) return;
        setMessages(saved.messages);
        setRestoredConversation(true);
        setRestoredConversationAt(saved.messages.reduce((latest, message) => {
          if (!message.saved_at) return latest;
          if (!latest) return message.saved_at;
          return new Date(message.saved_at).getTime() > new Date(latest).getTime() ? message.saved_at : latest;
        }, null as string | null));
      })
      .catch(() => undefined);
  }, [current?.artist, current?.title]);

  const openKugou = async () => {
    setOpening(true);
    try {
      await fetchApiClient("/api/kugou/open", { method: "POST" });
      window.setTimeout(() => void loadContext(), 1200);
    } finally {
      setOpening(false);
    }
  };

  const likeCurrentSong = async () => {
    if (!current?.recording_id || liking) return;
    setLiking(true);
    try {
      await fetchApiClient("/api/listener/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recording_id: current.recording_id, action: "like", channel: "listening" }),
      });
      await loadContext();
    } catch {
      // The server count remains authoritative when the request fails.
    } finally {
      setLiking(false);
    }
  };

  const openCompanionSettings = async () => {
    setShowCompanionSettings(true);
    setPromptSettingsError(null);
    if (promptSettings) return;
    setPromptSettingsLoading(true);
    try {
      const settings = await fetchApiClient<ListeningPromptSettings>("/api/listening/settings", { retries: 1, timeoutMs: 8000 });
      setPromptSettings(settings);
      setCorePromptDraft(settings.core_prompt);
      setPromptDraft(settings.custom_prompt);
    } catch {
      setPromptSettingsError("陪伴设置暂时无法读取，请确认后端已重启。设置面板会保留，不会自动消失。");
    } finally {
      setPromptSettingsLoading(false);
    }
  };

  const saveCompanionSettings = async () => {
    setPromptSettingsSaving(true);
    setPromptSettingsError(null);
    try {
      const settings = await fetchApiClient<ListeningPromptSettings>("/api/listening/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ core_prompt: corePromptDraft, custom_prompt: promptDraft }),
        retries: 1,
        timeoutMs: 8000,
      });
      setPromptSettings(settings);
      setCorePromptDraft(settings.core_prompt);
      setPromptDraft(settings.custom_prompt);
      setShowCompanionSettings(false);
    } catch {
      setPromptSettingsError("保存失败，请确认后端已重启后再试。");
    } finally {
      setPromptSettingsSaving(false);
    }
  };

  const askAgent = async (prompt = question) => {
    const nextQuestion = prompt.trim();
    if (!nextQuestion || chatting) return;
    const clientMessageId = createClientMessageId();
    setQuestion("");
    setMessages((items) => [...items, { role: "user", content: nextQuestion, saved_at: nowIso() }]);
    setChatting(true);
    try {
      const result = await fetchApiClient<{ answer: string; tools_used: string[]; sources: ChatSource[] }>("/api/listening/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        retries: 1,
        timeoutMs: 45000,
        body: JSON.stringify({
          question: nextQuestion,
          song_title: current?.title,
          artist: current?.artist,
          client_message_id: clientMessageId,
          recent_messages: messages.slice(-8).map(({ role, content }) => ({ role, content })),
        }),
      });
      setMessages((items) => [...items, { role: "agent", content: result.answer, tools: result.tools_used, sources: result.sources, saved_at: nowIso() }]);
    } catch {
      setMessages((items) => [...items, { role: "agent", content: "音乐陪伴暂时没有回应，请确认服务仍在运行。", saved_at: nowIso() }]);
    } finally {
      setChatting(false);
    }
  };

  const currentLikeCount = current?.like_count || 0;

  return (
    <main className="listening-room-page">
      <section className={`room-heading ${showIntro ? "is-visible" : "is-hidden"}`}>
        <div><p className="atlas-eyebrow"><span />LISTENING ROOM</p><h1>听见歌里，<em>没有说完的话。</em></h1></div>
      </section>

      <section className="room-grid">
        <section className="room-listening-main room-panel">
          <NowPlayingPanel
            current={current}
            displayArtist={displayArtist}
            displayTitle={displayTitle}
            likeCount={currentLikeCount}
            liking={liking}
            loading={loading}
            opening={opening}
            todayStats={todayStats}
            onLike={() => void likeCurrentSong()}
            onOpenKugou={() => void openKugou()}
            onRefresh={() => void loadContext()}
            onShowRanking={() => setShowTodayRanking(true)}
          />
          <SongStoryPanel hasCurrentTrack={Boolean(current?.title)} loading={storyLoading} story={context?.story} />
        </section>

        <CompanionChat
          chatting={chatting}
          currentArtist={current?.artist}
          currentTitle={current?.title}
          messages={messages}
          question={question}
          quickPrompts={context?.quick_prompts || []}
          restoredConversation={restoredConversation}
          restoredConversationAt={restoredConversationAt}
          showDetailedTimes={showDetailedTimes}
          onAsk={askAgent}
          onOpenSettings={() => void openCompanionSettings()}
          onQuestionChange={setQuestion}
          onToggleTimes={() => setShowDetailedTimes((value) => !value)}
          settingsPanel={showCompanionSettings ? (
            <CompanionSettingsPanel
              corePrompt={promptSettings?.core_prompt || ""}
              customPrompt={promptDraft}
              defaultCorePrompt={promptSettings?.default_core_prompt || ""}
              editableScope={promptSettings?.editable_scope || ""}
              error={promptSettingsError}
              loading={promptSettingsLoading}
              onChange={setPromptDraft}
              onCoreChange={setCorePromptDraft}
              onClose={() => setShowCompanionSettings(false)}
              onReset={() => { setCorePromptDraft(promptSettings?.default_core_prompt || ""); setPromptDraft(""); }}
              onRetry={() => void openCompanionSettings()}
              onSave={() => void saveCompanionSettings()}
              saving={promptSettingsSaving}
            />
          ) : null}
        />
      </section>

      {showTodayRanking ? <TodayRankingDialog onClose={() => setShowTodayRanking(false)} stats={todayStats} /> : null}
    </main>
  );
}
