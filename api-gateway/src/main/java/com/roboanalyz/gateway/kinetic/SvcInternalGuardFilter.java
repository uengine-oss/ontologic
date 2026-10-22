package com.roboanalyz.gateway.kinetic;

import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * {@code /svc/**} 내부 헤더 가드 (계약 §5). 라우팅 전에 {@code X-Kinetic-Internal} 이 KINETIC_INTERNAL_SECRET 과
 * 같은지 본다. 없거나 다르면 403 {@code {"error":{"code":"forbidden"}}} — 알 수 없는 시스템도 똑같이 403 이라
 * 어떤 시스템이 등록돼 있는지 새지 않는다. 비밀이 설정되지 않았으면 /svc/** 는 모두 거부(fail closed).
 * 키네틱 활성 여부와 무관하게 항상 동작한다.
 */
public class SvcInternalGuardFilter implements WebFilter, Ordered {

    public static final String HEADER = "X-Kinetic-Internal";
    /** Spring Security 체인(-100)·CORS 보다 먼저. */
    public static final int ORDER = -200;

    private final KineticProperties props;

    public SvcInternalGuardFilter(KineticProperties props) {
        this.props = props;
    }

    public static boolean isSvcPath(String path) {
        return path.equals("/svc") || path.startsWith("/svc/");
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String path = exchange.getRequest().getPath().pathWithinApplication().value();
        if (!isSvcPath(path)) {
            return chain.filter(exchange);
        }
        if (!secretMatches(props.getInternalSecret(), exchange.getRequest().getHeaders().getFirst(HEADER))) {
            return KineticErrors.write(exchange.getResponse(), HttpStatus.FORBIDDEN, "forbidden", null);
        }
        return chain.filter(exchange);
    }

    static boolean secretMatches(String expected, String presented) {
        if (expected == null || expected.isEmpty() || presented == null) {
            return false;
        }
        return MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8),
                presented.getBytes(StandardCharsets.UTF_8));
    }

    @Override
    public int getOrder() {
        return ORDER;
    }
}
