import { Send } from "lucide-react";
import { KeyboardEvent } from "react";

type Props = {
  busy: boolean;
  error: string | null;
  onExecute: () => void | Promise<void>;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onQueryChange: (value: string) => void;
  query: string;
};

export function AgentComposer({ busy, error, onExecute, onKeyDown, onQueryChange, query }: Props) {
  return <div className="music-agent-composer">
    {error ? <p>{error}</p> : null}
    <div><textarea aria-label="给音乐助理发送消息" onChange={(event) => onQueryChange(event.target.value)} onKeyDown={onKeyDown} placeholder="比如：结合播放记录，分析我最近的音乐偏好" rows={1} value={query} /><button disabled={busy || !query.trim()} onClick={() => void onExecute()} type="button" aria-label="发送"><Send size={18} /></button></div>
    <small>Enter 发送 · Shift + Enter 换行 · Agent 会自动调用需要的能力</small>
  </div>;
}
