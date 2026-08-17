'use client';

import { Bot, BrainCircuit, ChartNoAxesCombined, Compass, Heart, Music2, Send, Sparkles } from 'lucide-react';
import { KeyboardEvent, useEffect, useRef, useState } from 'react';
import { fetchApiClient } from '../../lib/api';

type Status = { configured: boolean; model?: string };
type Run = { answer: string; tools_used: string[]; latency_ms: number };
type Message = { id: string; role: 'user' | 'assistant'; content: string; run?: Run };

const SOURCE_LABELS: Record<string, string> = {
  search_music: '歌曲资料',
  kg_neighbors: '音乐关系',
  kg_shortest_path: '作品关联',
  daily_recommendation: '今日推荐',
  hybrid_recommendation: '偏好算法',
  kg_pagerank: '关联音乐人',
  listener_emotion_memory: '情绪记忆',
  weekly_listening_report: '听歌复盘',
};

const QUICK_ACTIONS = [
  { icon: Compass, label: '推荐一首', prompt: '结合今天的天气、时间和我的听歌记录，只推荐一首现在最适合听的歌，并说明理由。' },
  { icon: BrainCircuit, label: '情绪记忆', prompt: '分析我最近 14 天的听歌情绪、循环和切歌行为，告诉我最近处于什么状态。' },
  { icon: ChartNoAxesCombined, label: '本周复盘', prompt: '生成我的本周听歌复盘，概括播放时段、循环歌曲和情绪变化。' },
  { icon: Heart, label: '理解偏爱', prompt: '结合我的收藏和播放记录，分析我最近真正偏爱的歌手、风格与情绪。' },
] as const;

export default function AgentPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fetchApiClient<Status>('/api/agent/status').then(setStatus).catch(() => setStatus({ configured: false }));
  }, []);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, busy]);

  const execute = async (prompt = query) => {
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt || busy) return;
    const userMessage: Message = { id: `user-${Date.now()}`, role: 'user', content: cleanPrompt };
    setMessages((current) => [...current, userMessage]);
    setQuery('');
    setBusy(true);
    setError(null);
    try {
      const run = await fetchApiClient<Run>('/api/agent/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: cleanPrompt,
          max_steps: 8,
          algorithm: 'auto',
          recent_messages: messages.slice(-10).map((message) => ({
            role: message.role,
            content: message.content,
          })),
        }),
      });
      setMessages((current) => [...current, { id: `assistant-${Date.now()}`, role: 'assistant', content: run.answer, run }]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '音乐助理暂时没有回应');
    } finally {
      setBusy(false);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      execute();
    }
  };

  return (
    <main className="music-agent-page">
      <section className="music-agent-shell">
        <aside className="music-agent-sidebar">
          <header>
            <div className="agent-avatar"><Bot size={25} /></div>
            <span><strong>音乐助理</strong><small><i className={status?.configured ? 'online' : ''} />{status?.configured ? `${status.model || 'DeepSeek'} 在线` : '本地模式'}</small></span>
          </header>

          <div className="agent-sidebar-label">让 Agent 帮你</div>
          <div className="agent-command-list">
            {QUICK_ACTIONS.map((action) => { const Icon = action.icon; return <button disabled={busy} key={action.label} onClick={() => execute(action.prompt)} type="button"><Icon size={16} /><span>{action.label}</span></button>; })}
          </div>

          <div className="agent-sidebar-note">
            <Sparkles size={15} />
            <p>你只需要表达想法。搜索、推荐、情绪分析和听歌复盘，由 Agent 自己选择工具完成。</p>
          </div>
        </aside>

        <section className="music-agent-chat">
          <header className="music-agent-chat-header">
            <div><Music2 size={18} /><span><strong>和音乐聊一会儿</strong><small>记得你的收藏、播放和跳过</small></span></div>
            <span className="agent-context-pill"><i />Agent Loop</span>
          </header>

          <div className={`music-agent-thread ${messages.length ? 'has-messages' : ''}`}>
            {!messages.length ? <div className="agent-welcome">
              <div className="agent-orb" data-pointer-reactive data-pointer-strength="0.4"><Bot size={38} /></div>
              <span>私人音乐 Agent</span>
              <h1>今天想从哪首歌开始？</h1>
              <p>问歌、聊歌词、找故事，或者让它读取你的听歌轨迹后主动给出建议。</p>
              <div>{QUICK_ACTIONS.slice(0, 3).map((action) => <button key={action.label} onClick={() => execute(action.prompt)} type="button">{action.label}</button>)}</div>
            </div> : null}

            {messages.map((message) => <article className={`agent-message ${message.role}`} key={message.id}>
              <div className="agent-message-avatar">{message.role === 'assistant' ? <Bot size={17} /> : '你'}</div>
              <div className="agent-message-body"><p>{message.content}</p>{message.run ? <footer><span>{message.run.tools_used.length ? message.run.tools_used.map((tool) => SOURCE_LABELS[tool] || '音乐工具').join(' · ') : '直接回答'}</span><time>{message.run.latency_ms}ms</time></footer> : null}</div>
            </article>)}

            {busy ? <article className="agent-message assistant thinking"><div className="agent-message-avatar"><Bot size={17} /></div><div className="agent-message-body"><div className="agent-thinking-dots"><i /><i /><i /></div><small>正在读取线索并选择工具…</small></div></article> : null}
            <div ref={threadEndRef} />
          </div>

          <div className="music-agent-composer">
            {error ? <p>{error}</p> : null}
            <div><textarea aria-label="给音乐助理发送消息" onChange={(event) => setQuery(event.target.value)} onKeyDown={handleKeyDown} placeholder="比如：为什么我最近总想听慢歌？" rows={1} value={query} /><button disabled={busy || !query.trim()} onClick={() => execute()} type="button" aria-label="发送"><Send size={18} /></button></div>
            <small>Enter 发送 · Shift + Enter 换行 · Agent 会自动调用需要的能力</small>
          </div>
        </section>
      </section>
    </main>
  );
}
