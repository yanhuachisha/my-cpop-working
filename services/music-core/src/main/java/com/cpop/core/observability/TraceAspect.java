package com.cpop.core.observability;

import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.TimeUnit;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    private final MeterRegistry registry;

    public TraceAspect(MeterRegistry registry) {
        this.registry = registry;
    }

    @Around("within(com.cpop.core..*Service)")
    public Object measure(ProceedingJoinPoint joinPoint) throws Throwable {
        long started = System.nanoTime();
        try {
            return joinPoint.proceed();
        } finally {
            registry.timer("music_core_service_latency", "method", joinPoint.getSignature().getName())
                    .record(System.nanoTime() - started, TimeUnit.NANOSECONDS);
        }
    }
}
