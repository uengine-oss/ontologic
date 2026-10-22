package com.roboanalyz.gateway.kinetic;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * 401 응답: RFC 9728 {@code WWW-Authenticate: Bearer resource_metadata="..."} + 계약 오류 JSON.
 * 토큰 없음·서명/만료/issuer/audience 불일치 모두 이 진입점으로 온다.
 * JWKS 를 가져오지 못한 경우(AuthenticationServiceException)는 503 {@code service_unavailable}.
 */
public class KineticAuthenticationEntryPoint implements ServerAuthenticationEntryPoint {

    private final String resourceMetadataUrl;

    public KineticAuthenticationEntryPoint(String resourceMetadataUrl) {
        this.resourceMetadataUrl = resourceMetadataUrl;
    }

    @Override
    public Mono<Void> commence(ServerWebExchange exchange, AuthenticationException ex) {
        ServerHttpResponse response = exchange.getResponse();
        if (ex instanceof AuthenticationServiceException) {
            // 검증 인프라(JWKS) 장애 — 클라이언트 토큰 문제가 아니다.
            return KineticErrors.write(response, HttpStatus.SERVICE_UNAVAILABLE, "service_unavailable",
                    ex.getMessage() != null ? ex.getMessage() : "token verification unavailable");
        }
        StringBuilder challenge = new StringBuilder("Bearer resource_metadata=\"").append(resourceMetadataUrl).append('"');
        boolean hasToken = exchange.getRequest().getHeaders().containsKey(HttpHeaders.AUTHORIZATION);
        if (hasToken) {
            challenge.append(", error=\"invalid_token\"");
        }
        response.getHeaders().set(HttpHeaders.WWW_AUTHENTICATE, challenge.toString());
        String message = hasToken
                ? "invalid bearer token" + (ex != null && ex.getMessage() != null ? ": " + ex.getMessage() : "")
                : "bearer token required";
        return KineticErrors.write(response, HttpStatus.UNAUTHORIZED, "unauthenticated", message);
    }
}
