package com.cpop.core.memory;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MemoryService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public MemoryService(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public MemoryWriteResponse save(String tenantId, String userId, String idempotencyKey,
                                    String traceId, MemoryWriteRequest request) {
        Optional<MemoryWriteResponse> existing = findIdempotent(idempotencyKey);
        if (existing.isPresent()) return existing.get();
        validatePrivacy(request.object());

        String proposedId = UUID.randomUUID().toString();
        jdbc.update("""
                INSERT INTO agent_memory(id, tenant_id, user_id, memory_key, memory_type, active_version)
                VALUES (?, ?, ?, ?, ?, 0)
                ON DUPLICATE KEY UPDATE updated_at = updated_at
                """, proposedId, tenantId, userId, request.memoryKey(), request.memoryType());
        MemoryRow memory = jdbc.queryForObject("""
                SELECT id, active_version FROM agent_memory
                WHERE tenant_id=? AND user_id=? AND memory_key=? FOR UPDATE
                """, MemoryService::memoryRow, tenantId, userId, request.memoryKey());
        if (memory == null) throw new IllegalStateException("memory row unavailable");
        int version = memory.activeVersion() + 1;
        jdbc.update("UPDATE memory_version SET active=FALSE WHERE memory_id=? AND active=TRUE", memory.id());
        jdbc.update("""
                INSERT INTO memory_version(memory_id, version, subject, predicate, object_value,
                  confidence, valid_from, expires_at, active, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE, ?)
                """, memory.id(), version, request.subject(), request.predicate(), request.object(),
                request.confidence(), request.validFrom(), request.expiresAt(), traceId);
        for (String sourceId : request.sourceMessageIds()) {
            jdbc.update("INSERT INTO memory_source_relation(memory_id, version, source_message_id) VALUES (?, ?, ?)",
                    memory.id(), version, sourceId);
        }
        jdbc.update("UPDATE agent_memory SET active_version=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", version, memory.id());
        String payload = payload(tenantId, userId, memory.id(), version, request);
        jdbc.update("""
                INSERT INTO outbox_event(id, aggregate_type, aggregate_id, aggregate_version,
                  event_type, payload, trace_id, occurred_at)
                VALUES (?, 'MEMORY', ?, ?, 'agent.memory.updated.v1', CAST(? AS JSON), ?, ?)
                """, UUID.randomUUID().toString(), memory.id(), version, payload, traceId, Instant.now());
        try {
            jdbc.update("INSERT INTO idempotency_record(idempotency_key, resource_id, resource_version) VALUES (?, ?, ?)",
                    idempotencyKey, memory.id(), version);
        } catch (DuplicateKeyException ignored) {
            return findIdempotent(idempotencyKey).orElseThrow();
        }
        return new MemoryWriteResponse(memory.id(), version, "committed");
    }

    private Optional<MemoryWriteResponse> findIdempotent(String key) {
        return jdbc.query("SELECT resource_id, resource_version FROM idempotency_record WHERE idempotency_key=?",
                (rs, row) -> new MemoryWriteResponse(rs.getString(1), rs.getInt(2), "idempotent_replay"), key)
                .stream().findFirst();
    }

    private String payload(String tenantId, String userId, String memoryId, int version,
                           MemoryWriteRequest request) {
        try {
            return mapper.writeValueAsString(Map.of(
                    "memory_id", memoryId, "version", version, "tenant_id", tenantId,
                    "user_id", userId, "memory_key", request.memoryKey(),
                    "memory_type", request.memoryType(), "subject", request.subject(),
                    "predicate", request.predicate(), "content", request.object(),
                    "authority", 1.0));
        } catch (JsonProcessingException error) {
            throw new IllegalArgumentException("memory payload is not serializable", error);
        }
    }

    private static void validatePrivacy(String value) {
        String lower = value.toLowerCase();
        if (lower.contains("api_key") || lower.contains("password") || lower.contains("authorization:")) {
            throw new IllegalArgumentException("restricted data cannot be persisted as memory");
        }
    }

    private static MemoryRow memoryRow(ResultSet rs, int rowNum) throws SQLException {
        return new MemoryRow(rs.getString("id"), rs.getInt("active_version"));
    }

    private record MemoryRow(String id, int activeVersion) {}
}
