package com.cpop.core.memory;

import jakarta.validation.Valid;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/internal/v1/memories")
public class MemoryController {
    private final MemoryService service;

    public MemoryController(MemoryService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public MemoryWriteResponse save(
            @RequestHeader("X-User-Id") String userId,
            @RequestHeader(value = "X-Tenant-Id", defaultValue = "default") String tenantId,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestHeader(value = "X-Trace-Id", defaultValue = "") String traceId,
            @RequestHeader(value = "X-Permissions", defaultValue = "") String permissions,
            @Valid @RequestBody MemoryWriteRequest request) {
        Set<String> granted = Arrays.stream(permissions.split(","))
                .map(String::trim).filter(value -> !value.isBlank()).collect(Collectors.toSet());
        if (!granted.contains("memory.write")) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "memory.write permission required");
        }
        return service.save(tenantId, userId, idempotencyKey, traceId, request);
    }
}
