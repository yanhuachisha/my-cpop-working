package com.cpop.core.conversation;

import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConversationAuditService {
    private final JdbcTemplate jdbc;

    public ConversationAuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public Map<String, Object> appendTurn(
            String tenantId, String userId, String traceId, ConversationTurnRequest request) {
        jdbc.update("""
                INSERT INTO agent_session(id, tenant_id, user_id, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                ON DUPLICATE KEY UPDATE updated_at=CURRENT_TIMESTAMP(6)
                """, request.sessionId(), tenantId, userId);
        Integer owned = jdbc.queryForObject("""
                SELECT COUNT(*) FROM agent_session WHERE id=? AND tenant_id=? AND user_id=?
                """, Integer.class, request.sessionId(), tenantId, userId);
        if (owned == null || owned != 1) {
            throw new IllegalArgumentException("session does not belong to the current tenant and user");
        }
        appendMessage(
                request.userMessageId(), request.sessionId(), "user",
                request.userContent(), request.userTokens(), traceId);
        appendMessage(
                request.assistantMessageId(), request.sessionId(), "assistant",
                request.assistantContent(), request.assistantTokens(), traceId);
        return Map.of("session_id", request.sessionId(), "status", "committed");
    }

    private void appendMessage(
            String id, String sessionId, String role, String content, int tokenCount, String traceId) {
        jdbc.update("""
                INSERT INTO agent_message(id, session_id, role, content, token_count, trace_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP(6))
                ON DUPLICATE KEY UPDATE id=id
                """, id, sessionId, role, content, tokenCount, traceId);
    }
}
