package com.roboanalyz.gateway.kinetic;

import org.springframework.cloud.gateway.filter.ratelimit.RateLimiter;
import reactor.core.publisher.Mono;

import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.LongSupplier;

/**
 * 인메모리 토큰 버킷 RateLimiter (Redis 불필요). 키 = 주체(sub).
 * 게이트웨이 인스턴스마다 따로 센다 — 여러 인스턴스로 늘리면 실제 한도는 인스턴스 수배가 된다.
 */
public class InMemoryTokenBucketRateLimiter implements RateLimiter<InMemoryTokenBucketRateLimiter.Config> {

    public static class Config {
        private double replenishRate;
        private long burstCapacity;

        public Config() {
        }

        public Config(double replenishRate, long burstCapacity) {
            this.replenishRate = replenishRate;
            this.burstCapacity = burstCapacity;
        }

        public double getReplenishRate() { return replenishRate; }
        public void setReplenishRate(double replenishRate) { this.replenishRate = replenishRate; }
        public long getBurstCapacity() { return burstCapacity; }
        public void setBurstCapacity(long burstCapacity) { this.burstCapacity = burstCapacity; }
    }

    private static final int MAX_BUCKETS = 100_000;
    private static final long IDLE_EVICT_NANOS = 10L * 60 * 1_000_000_000L;

    private final Config defaultConfig;
    private final Map<String, Config> config = new HashMap<>();
    private final ConcurrentHashMap<String, Bucket> buckets = new ConcurrentHashMap<>();
    private final LongSupplier nanoClock;

    public InMemoryTokenBucketRateLimiter(double ratePerSec, long burst) {
        this(ratePerSec, burst, System::nanoTime);
    }

    InMemoryTokenBucketRateLimiter(double ratePerSec, long burst, LongSupplier nanoClock) {
        this.defaultConfig = new Config(ratePerSec, Math.max(1, burst));
        this.nanoClock = nanoClock;
    }

    /** 동기 판정: 토큰 1개 소비 시도. */
    public Decision tryConsume(String key) {
        Config c = defaultConfig;
        long now = nanoClock.getAsLong();
        if (buckets.size() > MAX_BUCKETS) {
            evictIdle(now);
        }
        Bucket b = buckets.computeIfAbsent(key, k -> new Bucket(c.burstCapacity, now));
        return b.consume(now, c.replenishRate, c.burstCapacity);
    }

    private void evictIdle(long now) {
        for (Iterator<Map.Entry<String, Bucket>> it = buckets.entrySet().iterator(); it.hasNext(); ) {
            if (now - it.next().getValue().lastTouched > IDLE_EVICT_NANOS) {
                it.remove();
            }
        }
    }

    @Override
    public Mono<Response> isAllowed(String routeId, String id) {
        Decision d = tryConsume(id);
        Map<String, String> headers = new HashMap<>();
        headers.put("X-RateLimit-Remaining", Long.toString(d.remaining));
        headers.put("X-RateLimit-Burst-Capacity", Long.toString(defaultConfig.burstCapacity));
        return Mono.just(new Response(d.allowed, headers));
    }

    @Override
    public Map<String, Config> getConfig() {
        return config;
    }

    @Override
    public Class<Config> getConfigClass() {
        return Config.class;
    }

    @Override
    public Config newConfig() {
        return new Config(defaultConfig.replenishRate, defaultConfig.burstCapacity);
    }

    public Config getDefaultConfig() {
        return defaultConfig;
    }

    Map<String, Bucket> buckets() {
        return Collections.unmodifiableMap(buckets);
    }

    public static final class Decision {
        public final boolean allowed;
        public final long remaining;

        Decision(boolean allowed, long remaining) {
            this.allowed = allowed;
            this.remaining = remaining;
        }
    }

    static final class Bucket {
        private double tokens;
        private long lastRefill;
        volatile long lastTouched;

        Bucket(long capacity, long now) {
            this.tokens = capacity;
            this.lastRefill = now;
            this.lastTouched = now;
        }

        synchronized Decision consume(long now, double ratePerSec, long capacity) {
            long elapsed = now - lastRefill;
            if (elapsed > 0) {
                tokens = Math.min(capacity, tokens + elapsed / 1_000_000_000.0 * ratePerSec);
                lastRefill = now;
            }
            lastTouched = now;
            if (tokens >= 1.0) {
                tokens -= 1.0;
                return new Decision(true, (long) Math.floor(tokens));
            }
            return new Decision(false, 0);
        }
    }
}
