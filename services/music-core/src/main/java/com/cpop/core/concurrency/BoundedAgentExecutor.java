package com.cpop.core.concurrency;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.ReentrantLock;
import org.springframework.stereotype.Component;

@Component
public class BoundedAgentExecutor {
    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(
            4, 8, 30, TimeUnit.SECONDS, new ArrayBlockingQueue<>(128),
            new ThreadPoolExecutor.CallerRunsPolicy());
    private final ReentrantLock metricsLock = new ReentrantLock();
    private final AtomicLong completed = new AtomicLong();
    private volatile boolean accepting = true;
    private long submitted;

    public void execute(Runnable task) {
        if (!accepting) throw new IllegalStateException("executor is shutting down");
        incrementSubmitted();
        String traceId = TraceContext.get();
        executor.execute(() -> {
            TraceContext.set(traceId);
            try {
                task.run();
                completed.incrementAndGet();
            } finally {
                TraceContext.clear();
            }
        });
    }

    private synchronized void incrementSubmitted() { submitted++; }

    public long[] snapshot() {
        metricsLock.lock();
        try {
            return new long[]{submitted, completed.get(), executor.getQueue().size()};
        } finally {
            metricsLock.unlock();
        }
    }

    @PreDestroy
    public void shutdown() throws InterruptedException {
        accepting = false;
        executor.shutdown();
        if (!executor.awaitTermination(10, TimeUnit.SECONDS)) executor.shutdownNow();
    }
}
