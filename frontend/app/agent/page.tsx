'use client';

import { Bot, BrainCircuit, ChartNoAxesCombined, Compass, Heart, MessageSquareText, Music2, Plus, Send, Sparkles, Trash2 } from 'lucide-react';
import { KeyboardEvent, ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { fetchApiClient } from '../../lib/api';

type Status = { configured: boolean; model?: string };
type Run = { session_id: string; answer: string; tools_used: string[]; latency_ms: number };
type Message = { id: string; role: 'user' | 'assistant'; content: string; run?: Run };
type SessionSummary = { id: string; title: string; preview: string; message_count: number; created_at: string; updated_at: string };
type SessionDetail = SessionSummary & { messages: Array<{ id: string; role: 'user' | 'assistant'; content: string; tools_used?: string[] }> };

const SOURCE_LABELS: Record<string, string> = {
  search_music: '联网音乐搜索',
  recommend_music: '个性化推荐',
  query_listener_memory: '用户音乐记忆',
  query_listening_history: '听歌历史',
  // 兼容升级前保存的历史会话。
  daily_recommendation: '今日推荐',
  hybrid_recommendation: '偏好算法',
  listener_emotion_memory: '情绪记忆',
  listener_preference_profile_tool: '长期偏好',
  weekly_listening_report: '听歌复盘',
};

const QUICK_ACTIONS = [
  { icon: Compass, label: '推荐一首', prompt: '结合今天的天气、时间和我的听歌记录，只推荐一首现在最适合听的歌，并说明理由。' },
  { icon: BrainCircuit, label: '情绪记忆', prompt: '分析我最近 14 天的听歌情绪、循环和切歌行为，告诉我最近处于什么状态。' },
  { icon: ChartNoAxesCombined, label: '本周复盘', prompt: '生成我的本周听歌复盘，概括播放时段、循环歌曲和情绪变化。' },
  { icon: Heart, label: '理解偏爱', prompt: '结合我的收藏和播放记录，分析我最近真正偏爱的歌手、风格与情绪。' },
] as const;

function normalizeAnswer(content: string) {
  let normalized = content.trim();
  if (!normalized) return '';
  if (!normalized.includes('\n') && normalized.includes('\\n')) normalized = normalized.replaceAll('\\n', '\n');
  if (normalized.startsWith('```') && normalized.endsWith('```')) {
    normalized = normalized.replace(/^```(?:markdown|md|text|json)?\s*/i, '').replace(/\s*```$/, '');
  }
  if ((normalized.startsWith('{') && normalized.endsWith('}')) || (normalized.startsWith('"') && normalized.endsWith('"'))) {
    try {
      const parsed = JSON.parse(normalized) as string | Record<string, unknown>;
      if (typeof parsed === 'string') return parsed.trim();
      const answer = parsed.answer || parsed.content || parsed.output || parsed.final_answer || parsed.message;
      if (typeof answer === 'string') return answer.trim();
    } catch {
    }
  }
  return normalized;
}

function renderInline(text: string): ReactNode[] {
  const tokens = text.split(/(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)]+\))/g);
  return tokens.filter(Boolean).map((token, index) => {
    const link = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
    if (link) return <a href={link[2]} key={`${token}-${index}`} rel="noreferrer" target="_blank">{link[1]}</a>;
    if (token.startsWith('**') && token.endsWith('**')) return <strong key={`${token}-${index}`}>{token.slice(2, -2)}</strong>;
    if (token.startsWith('`') && token.endsWith('`')) return <code key={`${token}-${index}`}>{token.slice(1, -1)}</code>;
    return token;
  });
}

function AgentAnswer({ content }: { content: string }) {
  const lines = normalizeAnswer(content).split('\n');
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const Heading = heading[1].length === 1 ? 'h2' : 'h3';
      blocks.push(<Heading key={`heading-${index}`}>{renderInline(heading[2])}</Heading>);
      index += 1;
      continue;
    }
    if (
      line.includes('|')
      && index + 1 < lines.length
      && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1])
    ) {
      const splitRow = (value: string) => value.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim());
      const headers = splitRow(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(splitRow(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="agent-answer-table-wrap" key={`table-${index}`}>
          <table><thead><tr>{headers.map((header, headerIndex) => <th key={`${header}-${headerIndex}`}>{renderInline(header)}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={`row-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${cell}-${cellIndex}`}>{renderInline(cell)}</td>)}</tr>)}</tbody></table>
        </div>,
      );
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, '').trim());
        index += 1;
      }
      blocks.push(<ul key={`list-${index}`}>{items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{renderInline(item)}</li>)}</ul>);
      continue;
    }
    if (/^\d+[.)]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+[.)]\s+/, '').trim());
        index += 1;
      }
      blocks.push(<ol key={`ordered-${index}`}>{items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{renderInline(item)}</li>)}</ol>);
      continue;
    }
    if (line.startsWith('>')) {
      blocks.push(<blockquote key={`quote-${index}`}>{renderInline(line.replace(/^>\s?/, ''))}</blockquote>);
      index += 1;
      continue;
    }
    const paragraph = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,3})\s+|^\s*[-*]\s+|^\s*\d+[.)]\s+|^>/.test(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={`paragraph-${index}`}>{paragraph.map((item, itemIndex) => <span key={`${item}-${itemIndex}`}>{renderInline(item)}{itemIndex < paragraph.length - 1 ? <br /> : null}</span>)}</p>);
  }
  return <div className="agent-answer">{blocks}</div>;
}

export default function AgentPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fetchApiClient<Status>('/api/agent/status').then(setStatus).catch(() => setStatus({ configured: false }));
  }, []);

  const refreshSessions = useCallback(async () => {
    const result = await fetchApiClient<{ sessions: SessionSummary[] }>('/api/agent/sessions', { retries: 1, timeoutMs: 5000 });
    setSessions(result.sessions);
    return result.sessions;
  }, []);

  const openSession = useCallback(async (sessionId: string) => {
    setError(null);
    try {
      const session = await fetchApiClient<SessionDetail>(`/api/agent/sessions/${sessionId}`, { retries: 1, timeoutMs: 5000 });
      setActiveSessionId(session.id);
      setMessages(session.messages.map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
        run: message.role === 'assistant' ? {
          session_id: session.id,
          answer: message.content,
          tools_used: message.tools_used || [],
          latency_ms: 0,
        } : undefined,
      })));
    } catch {
      setError('这段会话暂时无法读取');
    }
  }, []);

  useEffect(() => {
    refreshSessions()
      .then((items) => items[0] ? openSession(items[0].id) : undefined)
      .catch(() => setError('会话历史暂时无法读取'))
      .finally(() => setSessionsLoading(false));
  }, [openSession, refreshSessions]);

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
      let sessionId = activeSessionId;
      if (!sessionId) {
        const session = await fetchApiClient<SessionSummary>('/api/agent/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: null }),
        });
        sessionId = session.id;
        setActiveSessionId(session.id);
      }
      const run = await fetchApiClient<Run>('/api/agent/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: cleanPrompt,
          session_id: sessionId,
          max_steps: 8,
          algorithm: 'auto',
        }),
      });
      setMessages((current) => [...current, { id: `assistant-${Date.now()}`, role: 'assistant', content: run.answer, run }]);
      setActiveSessionId(run.session_id);
      await refreshSessions();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '音乐助理暂时没有回应');
    } finally {
      setBusy(false);
    }
  };

  const createSession = async () => {
    if (busy) return;
    setError(null);
    try {
      const session = await fetchApiClient<SessionSummary>('/api/agent/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: null }),
      });
      setSessions((current) => [session, ...current]);
      setActiveSessionId(session.id);
      setMessages([]);
      setQuery('');
    } catch {
      setError('新会话创建失败');
    }
  };

  const removeSession = async (sessionId: string) => {
    if (busy) return;
    try {
      await fetchApiClient(`/api/agent/sessions/${sessionId}`, { method: 'DELETE', retries: 1 });
      const remaining = sessions.filter((session) => session.id !== sessionId);
      setSessions(remaining);
      if (activeSessionId === sessionId) {
        if (remaining[0]) await openSession(remaining[0].id);
        else {
          setActiveSessionId(null);
          setMessages([]);
        }
      }
    } catch {
      setError('会话删除失败');
    }
  };

  const formatSessionTime = (value: string) => {
    const date = new Date(value);
    const today = new Date();
    if (date.toDateString() === today.toDateString()) return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
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

          <button className="agent-session-new" disabled={busy} onClick={createSession} type="button"><Plus size={16} /><span>新对话</span></button>
          <div className="agent-sidebar-label">会话历史</div>
          <div className="agent-session-list">
            {sessionsLoading ? <div className="agent-session-empty">正在读取记忆…</div> : null}
            {!sessionsLoading && !sessions.length ? <div className="agent-session-empty"><MessageSquareText size={20} /><span>还没有保存的对话</span></div> : null}
            {sessions.map((session) => <div className={`agent-session-item${activeSessionId === session.id ? ' active' : ''}`} key={session.id}>
              <button disabled={busy} onClick={() => openSession(session.id)} type="button"><strong>{session.title}</strong><span>{session.preview || '等待第一句话'}</span><small>{formatSessionTime(session.updated_at)} · {session.message_count} 条</small></button>
              <button aria-label={`删除会话 ${session.title}`} className="agent-session-delete" disabled={busy} onClick={() => removeSession(session.id)} type="button"><Trash2 size={13} /></button>
            </div>)}
          </div>

          <div className="agent-sidebar-note">
            <Sparkles size={15} />
            <p>每段会话独立记忆；收藏、播放与偏好画像作为长期记忆，由 Agent 按需读取。</p>
          </div>
        </aside>

        <section className="music-agent-chat">
          <header className="music-agent-chat-header">
            <div><Music2 size={18} /><span><strong>和音乐聊一会儿</strong><small>记得你的收藏、播放和跳过</small></span></div>
            <span className="agent-context-pill"><i />会话记忆已连接</span>
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
              <div className="agent-message-body">{message.role === 'assistant' ? <AgentAnswer content={message.content} /> : <p>{message.content}</p>}{message.run ? <footer><span>{message.run.tools_used.length ? message.run.tools_used.map((tool) => SOURCE_LABELS[tool] || '音乐工具').join(' · ') : '直接回答'}</span><time>{message.run.latency_ms ? `${message.run.latency_ms}ms` : '已保存'}</time></footer> : null}</div>
            </article>)}

            {busy ? <article className="agent-message assistant thinking"><div className="agent-message-avatar"><Bot size={17} /></div><div className="agent-message-body"><div className="agent-thinking-dots"><i /><i /><i /></div><small>正在读取线索并选择工具…</small></div></article> : null}
            <div ref={threadEndRef} />
          </div>

          <div className="music-agent-composer">
            {error ? <p>{error}</p> : null}
            <div><textarea aria-label="给音乐助理发送消息" onChange={(event) => setQuery(event.target.value)} onKeyDown={handleKeyDown} placeholder="比如：结合播放记录，分析我最近的音乐偏好" rows={1} value={query} /><button disabled={busy || !query.trim()} onClick={() => execute()} type="button" aria-label="发送"><Send size={18} /></button></div>
            <small>Enter 发送 · Shift + Enter 换行 · Agent 会自动调用需要的能力</small>
          </div>
        </section>
      </section>
    </main>
  );
}
