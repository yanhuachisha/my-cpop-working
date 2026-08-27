package com.cpop.core.action;

import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/internal/v1")
public class UserActionController {
    private final UserActionService service;

    public UserActionController(UserActionService service) {
        this.service = service;
    }

    @PostMapping("/favorites")
    Map<String, Object> favorite(@RequestHeader("X-User-Id") String userId,
            @RequestHeader(value = "X-Tenant-Id", defaultValue = "default") String tenantId,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestHeader(value = "X-Trace-Id", defaultValue = "") String traceId,
            @RequestHeader(value = "X-Permissions", defaultValue = "") String permissions,
            @RequestBody Map<String, Object> body) {
        authorize(permissions, "favorite.write");
        return service.write("favorite", tenantId, userId, idempotencyKey, traceId, body);
    }

    @PostMapping("/preferences")
    Map<String, Object> preference(@RequestHeader("X-User-Id") String userId,
            @RequestHeader(value = "X-Tenant-Id", defaultValue = "default") String tenantId,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestHeader(value = "X-Trace-Id", defaultValue = "") String traceId,
            @RequestHeader(value = "X-Permissions", defaultValue = "") String permissions,
            @RequestBody Map<String, Object> body) {
        authorize(permissions, "preference.write");
        return service.write("preference", tenantId, userId, idempotencyKey, traceId, body);
    }

    @PostMapping("/feedback")
    Map<String, Object> feedback(@RequestHeader("X-User-Id") String userId,
            @RequestHeader(value = "X-Tenant-Id", defaultValue = "default") String tenantId,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestHeader(value = "X-Trace-Id", defaultValue = "") String traceId,
            @RequestHeader(value = "X-Permissions", defaultValue = "") String permissions,
            @RequestBody Map<String, Object> body) {
        authorize(permissions, "feedback.write");
        return service.write("feedback", tenantId, userId, idempotencyKey, traceId, body);
    }

    private static void authorize(String raw, String required) {
        Set<String> permissions = Arrays.stream(raw.split(",")).map(String::trim)
                .filter(value -> !value.isBlank()).collect(Collectors.toSet());
        if (!permissions.contains(required)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, required + " permission required");
        }
    }
}
