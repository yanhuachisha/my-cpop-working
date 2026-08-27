package com.cpop.core.concurrency;

public final class TraceContext {
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private TraceContext() {}

    public static void set(String traceId) { CURRENT.set(traceId); }
    public static String get() { return CURRENT.get(); }
    public static void clear() { CURRENT.remove(); }
}
