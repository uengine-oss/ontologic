package com.roboanalyz.gateway.kinetic;

import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicLong;

import static org.assertj.core.api.Assertions.assertThat;

class InMemoryTokenBucketRateLimiterTest {

    @Test
    void burstThenRefill() {
        AtomicLong now = new AtomicLong(0);
        InMemoryTokenBucketRateLimiter rl = new InMemoryTokenBucketRateLimiter(10, 20, now::get);
        for (int i = 0; i < 20; i++) {
            assertThat(rl.tryConsume("a").allowed).isTrue();
        }
        assertThat(rl.tryConsume("a").allowed).isFalse();
        assertThat(rl.tryConsume("b").allowed).isTrue();
        now.addAndGet(100_000_000L); // 0.1s → 토큰 1개
        assertThat(rl.tryConsume("a").allowed).isTrue();
        assertThat(rl.tryConsume("a").allowed).isFalse();
        now.addAndGet(10_000_000_000L); // 10s → 가득 (20 상한)
        int allowed = 0;
        while (rl.tryConsume("a").allowed) {
            allowed++;
        }
        assertThat(allowed).isEqualTo(20);
    }
}
