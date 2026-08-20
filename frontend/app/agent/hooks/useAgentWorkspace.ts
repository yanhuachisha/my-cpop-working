import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { fetchApiClient } from "../../../lib/api";
import { AgentMessage, AgentRun, AgentStatus, SessionDetail, SessionSummary } from "../types";

function compactDuplicateMessages(items: AgentMessage[]) {
  const compacted: AgentMessage[] = [];
  for (let index = 0; index < items.length; index += 1) {
    const message = items[index];
    const previous = compacted[compacted.length - 1];
    if (previous?.role === message.role && previous.content.trim() === message.content.trim()) continue;
    const previousUser = compacted.length >= 2 ? compacted[compacted.length - 2] : null;
    const previousAssistant = compacted.length >= 1 ? compacted[compacted.length - 1] : null;
    const nextAssistant = items[index + 1];
    if (message.role === "user" && previousUser?.role === "user" && previousAssistant?.role === "assistant" && nextAssistant?.role === "assistant" && previousUser.content.trim() === message.content.trim()) {
      index += 1;
      continue;
    }
    compacted.push(message);
  }
  return compacted;
}

function formatSessionTime(value: string) {
  const date = new Date(value);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  return date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export function useAgentWorkspace() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);

  useEffect(() => {
    fetchApiClient<AgentStatus>("/api/agent/status").then(setStatus).catch(() => setStatus({ configured: false }));
  }, []);

  const refreshSessions = useCallback(async () => {
    const result = await fetchApiClient<{ sessions: SessionSummary[] }>("/api/agent/sessions", { retries: 1, timeoutMs: 5000 });
    setSessions(result.sessions);
    return result.sessions;
  }, []);

  const openSession = useCallback(async (sessionId: string) => {
    setError(null);
    try {
      const session = await fetchApiClient<SessionDetail>(`/api/agent/sessions/${sessionId}`, { retries: 1, timeoutMs: 5000 });
      setActiveSessionId(session.id);
      setMessages(compactDuplicateMessages(session.messages.map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
        run: message.role === "assistant" ? { session_id: session.id, answer: message.content, tools_used: message.tools_used || [], latency_ms: 0 } : undefined,
      }))));
    } catch {
      setError("这段会话暂时无法读取");
    }
  }, []);

  useEffect(() => {
    refreshSessions().then((items) => items[0] ? openSession(items[0].id) : undefined).catch(() => setError("会话历史暂时无法读取")).finally(() => setSessionsLoading(false));
  }, [openSession, refreshSessions]);

  const execute = async (prompt = query) => {
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt || busyRef.current) return;
    busyRef.current = true;
    setMessages((current) => [...current, { id: `user-${Date.now()}`, role: "user", content: cleanPrompt }]);
    setQuery("");
    setBusy(true);
    setError(null);
    try {
      let sessionId = activeSessionId;
      if (!sessionId) {
        const session = await fetchApiClient<SessionSummary>("/api/agent/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, retries: 1, timeoutMs: 12000, body: JSON.stringify({ title: null }) });
        sessionId = session.id;
        setActiveSessionId(session.id);
      }
      const run = await fetchApiClient<AgentRun>("/api/agent/run", { method: "POST", headers: { "Content-Type": "application/json" }, retries: 1, timeoutMs: 60000, body: JSON.stringify({ query: cleanPrompt, session_id: sessionId, max_steps: 8, algorithm: "auto" }) });
      setMessages((current) => [...current, { id: `assistant-${Date.now()}`, role: "assistant", content: run.answer, run }]);
      setActiveSessionId(run.session_id);
      await refreshSessions();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "音乐助理暂时没有回应");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const createSession = async () => {
    if (busy) return;
    setError(null);
    try {
      const session = await fetchApiClient<SessionSummary>("/api/agent/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, retries: 1, timeoutMs: 12000, body: JSON.stringify({ title: null }) });
      setSessions((current) => [session, ...current]);
      setActiveSessionId(session.id);
      setMessages([]);
      setQuery("");
    } catch {
      setError("新会话创建失败");
    }
  };

  const removeSession = async (sessionId: string) => {
    if (busy) return;
    try {
      await fetchApiClient(`/api/agent/sessions/${sessionId}`, { method: "DELETE", retries: 1 });
      const remaining = sessions.filter((session) => session.id !== sessionId);
      setSessions(remaining);
      if (activeSessionId !== sessionId) return;
      if (remaining[0]) await openSession(remaining[0].id);
      else {
        setActiveSessionId(null);
        setMessages([]);
      }
    } catch {
      setError("会话删除失败");
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void execute();
    }
  };

  return { activeSessionId, busy, createSession, error, execute, formatSessionTime, handleKeyDown, messages, openSession, query, removeSession, sessions, sessionsLoading, setQuery, status };
}
