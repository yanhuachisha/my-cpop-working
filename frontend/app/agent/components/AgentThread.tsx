import { Bot, Music2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { QUICK_ACTIONS, SOURCE_LABELS } from "../constants";
import { AgentAnswer } from "./AgentAnswer";
import { AgentMessage } from "../types";

type Props = {
  busy: boolean;
  messages: AgentMessage[];
  onExecute: (prompt?: string) => void | Promise<void>;
};

export function AgentThread({ busy, messages, onExecute }: Props) {
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [busy, messages]);

  return (
    <div className={`music-agent-thread ${messages.length ? "has-messages" : ""}`}>
      {!messages.length ? <div className="agent-welcome"><div className="agent-orb" data-pointer-reactive data-pointer-strength="0.4"><Bot size={38} /></div><span>私人音乐 Agent</span><h1>今天想从哪首歌开始？</h1><p>问歌、聊歌词、找故事，或者让它读取你的听歌轨迹后主动给出建议。</p><div>{QUICK_ACTIONS.slice(0, 3).map((action) => <button key={action.label} onClick={() => void onExecute(action.prompt)} type="button">{action.label}</button>)}</div></div> : null}
      {messages.map((message) => <article className={`agent-message ${message.role}`} key={message.id}>
        <div className="agent-message-avatar">{message.role === "assistant" ? <Bot size={17} /> : "你"}</div>
        <div className="agent-message-body">{message.role === "assistant" ? <AgentAnswer content={message.content} /> : <p>{message.content}</p>}{message.run ? <footer><span>{message.run.tools_used.length ? message.run.tools_used.map((tool) => SOURCE_LABELS[tool] || "音乐工具").join(" · ") : "直接回答"}</span><time>{message.run.latency_ms ? `${message.run.latency_ms}ms` : "已保存"}</time></footer> : null}</div>
      </article>)}
      {busy ? <article className="agent-message assistant thinking"><div className="agent-message-avatar"><Bot size={17} /></div><div className="agent-message-body"><div className="agent-thinking-dots"><i /><i /><i /></div><small>正在读取线索并选择工具…</small></div></article> : null}
      <div ref={threadEndRef} />
    </div>
  );
}

export function AgentChatHeader() {
  return <header className="music-agent-chat-header"><div><Music2 size={18} /><span><strong>和音乐聊一会儿</strong><small>记得你的播放、跳过和红心</small></span></div><span className="agent-context-pill"><i />会话记忆已连接</span></header>;
}
