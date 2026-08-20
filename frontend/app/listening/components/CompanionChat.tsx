import { Bot, Clock3, ExternalLink, MessageCircleMore, Send, Settings2 } from "lucide-react";
import { KeyboardEvent, ReactNode, useEffect, useRef } from "react";
import { ChatMessage } from "../types";
import { CompanionMarkdown } from "./CompanionMarkdown";

type Props = {
  chatting: boolean;
  currentArtist?: string | null;
  currentTitle?: string | null;
  messages: ChatMessage[];
  question: string;
  quickPrompts: string[];
  restoredConversation: boolean;
  restoredConversationAt: string | null;
  showDetailedTimes: boolean;
  onAsk: (prompt?: string) => void | Promise<void>;
  onQuestionChange: (question: string) => void;
  onOpenSettings: () => void;
  settingsPanel?: ReactNode;
  onToggleTimes: () => void;
};

function formatChatTime(value?: string, detailed = false) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const timePart = parsed.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  return detailed ? `${parsed.toLocaleDateString("zh-CN")} ${timePart}` : timePart;
}

export function CompanionChat({
  chatting,
  currentArtist,
  currentTitle,
  messages,
  question,
  quickPrompts,
  restoredConversation,
  restoredConversationAt,
  showDetailedTimes,
  onAsk,
  onQuestionChange,
  onOpenSettings,
  settingsPanel,
  onToggleTimes,
}: Props) {
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatting, messages]);

  const toggleTimesFromKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onToggleTimes();
  };

  return (
    <aside className="room-agent room-panel">
      <div aria-label="双击可切换对话时间显示" className="companion-head" onDoubleClick={onToggleTimes} onKeyDown={toggleTimesFromKeyboard} role="button" tabIndex={0}>
        <div className="companion-identity"><span><Bot size={18} /></span><div><strong>音乐陪伴</strong><small>{currentTitle ? `${currentTitle}${currentArtist ? ` · ${currentArtist}` : ""}` : "等待一首歌开始"}</small></div></div>
        <div className="companion-head-tools">
          {restoredConversationAt ? <span className="companion-last-chat">上次聊天 {formatChatTime(restoredConversationAt)}</span> : null}
          <button className={`companion-time-toggle${showDetailedTimes ? " active" : ""}`} onClick={(event) => { event.stopPropagation(); onToggleTimes(); }} type="button"><Clock3 size={12} />{showDetailedTimes ? "隐藏时间" : "显示时间"}</button>
          <button aria-label="编辑音乐陪伴提示词" className="companion-settings-button" onClick={(event) => { event.stopPropagation(); onOpenSettings(); }} title="编辑音乐陪伴" type="button"><Settings2 size={15} /></button>
          <div className={`companion-live${restoredConversation ? " restored" : ""}`}><i />{restoredConversation ? "记忆已唤醒" : "正在陪听"}</div>
        </div>
      </div>
      {settingsPanel}
      <div className="companion-messages">
        {messages.map((message, index) => (
          <div className={`companion-turn ${message.role}`} key={`${message.role}-${message.saved_at || index}-${index}`}>
            {message.role === "agent" ? <div className="companion-avatar"><Bot size={14} /></div> : null}
            <div className="companion-copy">
              <span>{message.role === "agent" ? "音乐陪伴" : "你"}</span>
              <div className="companion-bubble">{message.role === "agent" ? <CompanionMarkdown content={message.content} /> : <p>{message.content}</p>}{message.sources?.length ? <div className="agent-message-sources">{message.sources.slice(0, 3).map((source) => <a href={source.url} key={source.url} rel="noreferrer" target="_blank"><ExternalLink size={11} />{source.name}</a>)}</div> : null}</div>
              {message.saved_at ? <time className={`companion-time${showDetailedTimes ? " detailed" : ""}`} dateTime={message.saved_at}>{formatChatTime(message.saved_at, showDetailedTimes)}</time> : null}
            </div>
          </div>
        ))}
        {chatting ? <div className="companion-turn agent"><div className="companion-avatar"><Bot size={14} /></div><div className="companion-copy"><span>音乐陪伴</span><div className="companion-bubble companion-thinking"><i /><i /><i /></div></div></div> : null}
        <div ref={messagesEndRef} />
      </div>
      <div className="companion-actions">{quickPrompts.slice(0, 4).map((prompt) => <button key={prompt} onClick={() => void onAsk(prompt)} type="button">{prompt}</button>)}</div>
      <div className="companion-composer">
        <MessageCircleMore size={17} />
        <textarea aria-label="和音乐陪伴对话" onChange={(event) => onQuestionChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void onAsk(); } }} placeholder="说说你此刻在这首歌里听见了什么……" rows={1} value={question} />
        <button disabled={!question.trim() || chatting} onClick={() => void onAsk()} type="button" aria-label="发送"><Send size={16} /></button>
      </div>
    </aside>
  );
}
