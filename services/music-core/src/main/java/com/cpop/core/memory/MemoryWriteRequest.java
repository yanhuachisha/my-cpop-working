package com.cpop.core.memory;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.List;

public record MemoryWriteRequest(
        @JsonProperty("memory_key") @NotBlank @Size(max = 64) String memoryKey,
        @NotBlank @Size(max = 200) String subject,
        @NotBlank @Size(max = 100) String predicate,
        @NotBlank @Size(max = 1000) String object,
        @JsonProperty("memory_type") @NotBlank String memoryType,
        @DecimalMin("0") @DecimalMax("1") double confidence,
        List<String> entities,
        @JsonProperty("source_message_ids") @NotEmpty List<String> sourceMessageIds,
        @JsonProperty("valid_from") Instant validFrom,
        @JsonProperty("expires_at") Instant expiresAt) {
}
