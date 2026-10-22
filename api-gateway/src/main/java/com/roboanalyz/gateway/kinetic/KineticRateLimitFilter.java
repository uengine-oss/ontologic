package com.roboanalyz.gateway.kinetic;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.net.InetSocketAddress;
import java.security.Principal;

/**
 * 북향 라우트 주체(sub) 단위 레이트 리밋 (계약 §6). 초과 시 429 + {@code {"error":{"code":"rate_limited"}}}.
 * JWT 인증 후의 Principal 이름이 sub 다(JwtAuthenticationToken 기본 동작). 공개 경로(health)는 클라이언트 IP 로 센다.
 */
public class KineticRateLimitFilter implements GatewayFilter {

    private final InMemoryTokenBucketRateLimiter limiter;

    public KineticRateLimitFilter(InMemoryTokenBucketRateLimiter limiter) {
        this.limiter = limiter;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        return exchange.getPrincipal()
                .map(Principal::getName)
                .filter(name -> !name.isEmpty())
                .map(name -> "sub:" + name)
                .defaultIfEmpty("ip:" + clientIp(exchange.getRequest()))
                .flatMap(key -> {
                    InMemoryTokenBucketRateLimiter.Decision d = limiter.tryConsume(key);
                    exchange.getResponse().getHeaders().set("X-RateLimit-Remaining", Long.toString(d.remaining));
                    if (d.allowed) {
                        return chain.filter(exchange);
                    }
                    exchange.getResponse().getHeaders().set("Retry-After", "1");
                    return KineticErrors.write(exchange.getResponse(), HttpStatus.TOO_MANY_REQUESTS,
                            "rate_limited", "too many requests for this subject");
                });
    }

    private static String clientIp(ServerHttpRequest request) {
        InetSocketAddress remote = request.getRemoteAddress();
        return remote == null || remote.getAddress() == null ? "unknown" : remote.getAddress().getHostAddress();
    }
}
