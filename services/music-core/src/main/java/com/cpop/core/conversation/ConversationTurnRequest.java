package com.cpop.core.conversation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

public record ConversationTurnRequest(
        @NotBlank @Size(max = 80) String sessionId,
        @NotBlank @Size(max = 100) String userMessageId,
        @NotBlank String userContent,
        @PositiveOrZero int userTokens,
        @NotBlank @Size(max = 100) String assistantMessageId,
        @NotBlank String assistantContent,
        @PositiveOrZero int assistantTokens) {}
