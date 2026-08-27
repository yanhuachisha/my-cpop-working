package com.cpop.core.concurrency;

import java.time.Duration;
import java.util.Collections;
import java.util.UUID;
import org.springframework.data.redis.connection.ReturnType;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
public class RedisConcurrencyGuard {
    private static final DefaultRedisScript<Long> UNLOCK = new DefaultRedisScript<>("""
            if redis.call('get', KEYS[1]) == ARGV[1] then
              return redis.call('del', KEYS[1])
            end
            return 0
            """, Long.class);
    private static final DefaultRedisScript<Long> SLIDING_WINDOW = new DefaultRedisScript<>("""
            local key, now, window, limit, member = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3]), ARGV[4]
            redis.call('zremrangebyscore', key, 0, now-window)
            if redis.call('zcard', key) >= limit then return 0 end
            redis.call('zadd', key, now, member)
            redis.call('pexpire', key, window)
            return 1
            """, Long.class);
    private final StringRedisTemplate redis;

    public RedisConcurrencyGuard(StringRedisTemplate redis) { this.redis = redis; }

    public String tryLock(String key, Duration ttl) {
        String token = UUID.randomUUID().toString();
        Boolean acquired = redis.opsForValue().setIfAbsent(key, token, ttl);
        return Boolean.TRUE.equals(acquired) ? token : null;
    }

    public boolean unlock(String key, String token) {
        return Long.valueOf(1).equals(redis.execute(UNLOCK, Collections.singletonList(key), token));
    }

    public boolean allow(String key, long nowMillis, Duration window, int limit) {
        Long result = redis.execute(SLIDING_WINDOW, Collections.singletonList(key),
                Long.toString(nowMillis), Long.toString(window.toMillis()), Integer.toString(limit), UUID.randomUUID().toString());
        return Long.valueOf(1).equals(result);
    }
}
