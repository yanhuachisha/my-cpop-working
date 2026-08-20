'use client';

import "../music-companion.css";
import "./agent-readable.css";
import { AgentComposer } from "./components/AgentComposer";
import { AgentSidebar } from "./components/AgentSidebar";
import { AgentChatHeader, AgentThread } from "./components/AgentThread";
import { useAgentWorkspace } from "./hooks/useAgentWorkspace";

export default function AgentPage() {
  const workspace = useAgentWorkspace();

  return (
    <main className="music-agent-page">
      <section className="music-agent-shell">
        <AgentSidebar
          activeSessionId={workspace.activeSessionId}
          busy={workspace.busy}
          formatSessionTime={workspace.formatSessionTime}
          onCreateSession={workspace.createSession}
          onOpenSession={workspace.openSession}
          onRemoveSession={workspace.removeSession}
          sessions={workspace.sessions}
          sessionsLoading={workspace.sessionsLoading}
          status={workspace.status}
        />
        <section className="music-agent-chat">
          <AgentChatHeader />
          <AgentThread busy={workspace.busy} messages={workspace.messages} onExecute={workspace.execute} />
          <AgentComposer busy={workspace.busy} error={workspace.error} onExecute={workspace.execute} onKeyDown={workspace.handleKeyDown} onQueryChange={workspace.setQuery} query={workspace.query} />
        </section>
      </section>
    </main>
  );
}
