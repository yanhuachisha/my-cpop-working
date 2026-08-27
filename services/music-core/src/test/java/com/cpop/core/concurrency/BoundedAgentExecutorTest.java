package com.cpop.core.concurrency;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class BoundedAgentExecutorTest {
    @Test
    void propagatesAndClearsThreadLocalTrace() throws Exception {
        BoundedAgentExecutor executor = new BoundedAgentExecutor();
        CountDownLatch completed = new CountDownLatch(1);
        AtomicReference<String> observed = new AtomicReference<>();
        TraceContext.set("trace-123");
        executor.execute(() -> {
            observed.set(TraceContext.get());
            completed.countDown();
        });
        TraceContext.clear();
        assertThat(completed.await(3, TimeUnit.SECONDS)).isTrue();
        assertThat(observed.get()).isEqualTo("trace-123");
        assertThat(executor.snapshot()[0]).isEqualTo(1);
        executor.shutdown();
    }
}
