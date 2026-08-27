package com.cpop.core.memory;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class MemoryControllerTest {
    @Test
    void rejectsWriteWithoutPermissionBeforeServiceExecution() {
        MemoryController controller = new MemoryController(mock(MemoryService.class));
        MemoryWriteRequest request = new MemoryWriteRequest(
                "a".repeat(64), "user", "prefers", "warm music", "preference",
                0.9, List.of(), List.of("message-1"), null, null);
        assertThatThrownBy(() -> controller.save("user-1", "default", "idem-1", "trace-1", "", request))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("memory.write");
    }
}
