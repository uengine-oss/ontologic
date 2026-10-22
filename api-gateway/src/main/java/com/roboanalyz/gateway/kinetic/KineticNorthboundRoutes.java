package com.roboanalyz.gateway.kinetic;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;

import static org.springframework.cloud.gateway.support.RouteMetadataUtils.RESPONSE_TIMEOUT_ATTR;

/**
 * 북향 라우트 (계약 §6). application.yml 의 기존 라우트(order 0, 마지막이 프론트 catch-all {@code /**})보다
 * 먼저 매칭되도록 음수 order 를 준다.
 *
 * <ul>
 *   <li>{@code /.well-known/oauth-protected-resource[/mcp/kinetic]} → kinetic-action {@code /.well-known/oauth-protected-resource} (공개)</li>
 *   <li>{@code /mcp/kinetic[/**]} → kinetic-action {@code /mcp[/**]} (JWT, 응답 타임아웃 없음 — SSE)</li>
 *   <li>{@code /api/kinetic/**} → 같은 경로 (JWT, 단 GET /api/kinetic/health 공개)</li>
 *   <li>{@code /svc/**} 중 동적 라우트에 없는 시스템 → 404 JSON (/svc 는 내부 헤더 가드를 먼저 통과해야 여기 온다)</li>
 * </ul>
 * Authorization 헤더는 그대로 전달된다 (kinetic-action 이 다시 검증한다).
 */
@Configuration
@ConditionalOnProperty(prefix = "kinetic", name = "enabled", havingValue = "true", matchIfMissing = true)
public class KineticNorthboundRoutes {

    static final int NORTHBOUND_ORDER = -10;
    /** 동적 /svc/<system> 라우트(-10)보다 뒤, 기존 라우트(0)보다 앞. */
    static final int SVC_UNKNOWN_ORDER = -5;

    @Bean
    public InMemoryTokenBucketRateLimiter kineticRateLimiter(KineticProperties props) {
        return new InMemoryTokenBucketRateLimiter(props.getRatePerSec(), props.getRateBurst());
    }

    @Bean
    public RouteLocator kineticNorthboundRouteLocator(RouteLocatorBuilder builder, KineticProperties props,
                                                      InMemoryTokenBucketRateLimiter kineticRateLimiter) {
        final String uri = props.baseUrl();
        final KineticRateLimitFilter rateLimit = new KineticRateLimitFilter(kineticRateLimiter);
        return builder.routes()
                .route("kinetic-protected-resource-metadata", r -> r.order(NORTHBOUND_ORDER)
                        .path("/.well-known/oauth-protected-resource",
                                "/.well-known/oauth-protected-resource/mcp/kinetic")
                        .filters(f -> f.setPath("/.well-known/oauth-protected-resource")
                                .removeRequestHeader("Origin")
                                .removeRequestHeader(SvcInternalGuardFilter.HEADER))
                        .uri(uri))
                // 내부 전용 라우트 원천(§3 '내부 헤더')은 북향으로 열지 않는다.
                .route("kinetic-internal-routes-blocked", r -> r.order(NORTHBOUND_ORDER - 1)
                        .path("/api/kinetic/systems/routes")
                        .filters(f -> f.filter((exchange, chain) -> KineticErrors.write(exchange.getResponse(),
                                HttpStatus.FORBIDDEN, "forbidden", "internal endpoint")))
                        .uri(uri))
                .route("kinetic-mcp", r -> r.order(NORTHBOUND_ORDER)
                        .path("/mcp/kinetic", "/mcp/kinetic/**")
                        .filters(f -> f.filter(rateLimit)
                                .rewritePath("/mcp/kinetic(?<s>.*)", "/mcp${s}")
                                .removeRequestHeader("Origin")
                                .removeRequestHeader(SvcInternalGuardFilter.HEADER))
                        // -1 = 응답 타임아웃 없음: Streamable HTTP/SSE 가 전역 30s 에 끊기지 않게.
                        .metadata(RESPONSE_TIMEOUT_ATTR, -1)
                        .uri(uri))
                .route("kinetic-api", r -> r.order(NORTHBOUND_ORDER)
                        .path("/api/kinetic/**")
                        .filters(f -> f.filter(rateLimit)
                                .removeRequestHeader("Origin")
                                .removeRequestHeader(SvcInternalGuardFilter.HEADER))
                        .metadata(RESPONSE_TIMEOUT_ATTR, props.getApiResponseTimeoutMs())
                        .uri(uri))
                .route("svc-unknown-system", r -> r.order(SVC_UNKNOWN_ORDER)
                        .path("/svc", "/svc/**")
                        .filters(f -> f.filter((exchange, chain) -> KineticErrors.write(exchange.getResponse(),
                                HttpStatus.NOT_FOUND, "not_found", "unknown system")))
                        .uri("no://op"))
                .build();
    }
}
