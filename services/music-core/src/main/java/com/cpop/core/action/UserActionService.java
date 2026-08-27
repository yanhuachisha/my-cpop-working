package com.cpop.core.action;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserActionService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public UserActionService(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Transactional
    public Map<String, Object> write(String actionType, String tenantId, String userId,
                                     String idempotencyKey, String traceId, Map<String, Object> payload) {
        var replay = jdbc.query("SELECT action_id FROM user_action WHERE idempotency_key=?",
                (rs, row) -> rs.getString(1), idempotencyKey).stream().findFirst();
        if (replay.isPresent()) return Map.of("action_id", replay.get(), "status", "idempotent_replay");
        String actionId = UUID.randomUUID().toString();
        try {
            jdbc.update("""
                    INSERT INTO user_action(action_id, tenant_id, user_id, action_type, payload,
                      idempotency_key, trace_id)
                    VALUES (?, ?, ?, ?, CAST(? AS JSON), ?, ?)
                    """, actionId, tenantId, userId, actionType,
                    mapper.writeValueAsString(payload), idempotencyKey, traceId);
        } catch (JsonProcessingException error) {
            throw new IllegalArgumentException("invalid action payload", error);
        }
        return Map.of("action_id", actionId, "status", "committed");
    }
}
