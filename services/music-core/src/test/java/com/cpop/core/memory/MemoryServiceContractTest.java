package com.cpop.core.memory;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.Transactional;

class MemoryServiceContractTest {
    @Test
    void memoryFourTableWriteIsDeclaredTransactional() throws Exception {
        Method method = MemoryService.class.getMethod(
                "save", String.class, String.class, String.class, String.class, MemoryWriteRequest.class);
        assertThat(method.getAnnotation(Transactional.class)).isNotNull();
    }
}
