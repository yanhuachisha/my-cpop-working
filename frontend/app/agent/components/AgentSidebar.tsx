import { Bot, MessageSquareText, Plus, Sparkles, Trash2 } from "lucide-react";
import { AgentStatus, SessionSummary } from "../types";

type Props = {
  activeSessionId: string | null;
  busy: boolean;
  formatSessionTime: (value: string) => string;
  onCreateSession: () => void | Promise<void>;
  onOpenSession: (id: string) => void | Promise<void>;
  onRemoveSession: (id: string) => void | Promise<void>;
  sessions: SessionSummary[];
  sessionsLoading: boolean;
  status: AgentStatus | null;
};

export function AgentSidebar({ activeSessionId, busy, formatSessionTime, onCreateSession, onOpenSession, onRemoveSession, sessions, sessionsLoading, status }: Props) {
  return (
    <aside className="music-agent-sidebar">
      <header><div className="agent-avatar"><Bot size={25} /></div><span><strong>音乐助理</strong><small><i className={status?.configured ? "online" : ""} />{status?.configured ? `${status.model || "DeepSeek"} 在线` : "本地模式"}</small></span></header>
      <button className="agent-session-new" disabled={busy} onClick={() => void onCreateSession()} type="button"><Plus size={16} /><span>新对话</span></button>
      <div className="agent-sidebar-label">会话历史</div>
      <div className="agent-session-list">
        {sessionsLoading ? <div className="agent-session-empty">正在读取记忆…</div> : null}
        {!sessionsLoading && !sessions.length ? <div className="agent-session-empty"><MessageSquareText size={20} /><span>还没有保存的对话</span></div> : null}
        {sessions.map((session) => <div className={`agent-session-item${activeSessionId === session.id ? " active" : ""}`} key={session.id}>
          <button disabled={busy} onClick={() => void onOpenSession(session.id)} type="button"><strong>{session.title}</strong><span>{session.preview || "等待第一句话"}</span><small>{formatSessionTime(session.updated_at)} · {session.message_count} 条</small></button>
          <button aria-label={`删除会话 ${session.title}`} className="agent-session-delete" disabled={busy} onClick={() => void onRemoveSession(session.id)} type="button"><Trash2 size={13} /></button>
        </div>)}
      </div>
      <div className="agent-sidebar-note"><Sparkles size={15} /><p>每段会话独立记忆；播放、跳过与红心偏好作为长期记忆，由 Agent 按需读取。</p></div>
    </aside>
  );
}
