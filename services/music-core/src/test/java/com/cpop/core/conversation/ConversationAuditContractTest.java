package com.cpop.core.conversation;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.Transactional;

class ConversationAuditContractTest {
    @Test
    void completeTurnAuditIsTransactional() throws Exception {
        Method method = ConversationAuditService.class.getMethod(
                "appendTurn", String.class, String.class, String.class,
                ConversationTurnRequest.class);
        assertThat(method.getAnnotation(Transactional.class)).isNotNull();
    }
}
