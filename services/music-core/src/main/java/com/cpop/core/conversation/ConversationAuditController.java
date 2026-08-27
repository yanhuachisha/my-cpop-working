package com.cpop.core.conversation;

import jakarta.validation.Valid;
import java.util.Arrays;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/internal/v1/conversations")
public class ConversationAuditController {
    private final ConversationAuditService service;

    public ConversationAuditController(ConversationAuditService service) {
        this.service = service;
    }

    @PostMapping("/turns")
    Map<String, Object> appendTurn(
            @RequestHeader("X-User-Id") String userId,
            @RequestHeader(value = "X-Tenant-Id", defaultValue = "default") String tenantId,
            @RequestHeader(value = "X-Permissions", defaultValue = "") String permissions,
            @RequestHeader(value = "X-Trace-Id", defaultValue = "") String traceId,
            @Valid @RequestBody ConversationTurnRequest request) {
        boolean allowed = Arrays.stream(permissions.split(","))
                .map(String::trim)
                .anyMatch("conversation.write"::equals);
        if (!allowed) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "conversation.write permission required");
        }
        return service.appendTurn(tenantId, userId, traceId, request);
    }
}
