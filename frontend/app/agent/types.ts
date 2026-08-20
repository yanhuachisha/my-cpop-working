export type AgentStatus = { configured: boolean; model?: string };

export type AgentRun = {
  session_id: string;
  answer: string;
  tools_used: string[];
  latency_ms: number;
};

export type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  run?: AgentRun;
};

export type SessionSummary = {
  id: string;
  title: string;
  preview: string;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type SessionDetail = SessionSummary & {
  messages: Array<{
    id: string;
    role: "user" | "assistant";
    content: string;
    tools_used?: string[];
  }>;
};
