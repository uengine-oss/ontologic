package com.roboanalyz.gateway.kinetic;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.cloud.gateway.filter.factory.RetryGatewayFilterFactory;
import org.springframework.cloud.gateway.support.HasRouteId;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;

import java.util.Collections;
import java.util.List;

/**
 * 필터 {@code KineticRetry(retries)} — 계약 §5 "Retry(GET/멱등 키 있는 POST 2회, 5xx·연결 오류)".
 *
 * <p>내장 Retry 필터를 두 벌 만든다: GET 전용, GET+POST. 요청이 POST 이고 {@code Idempotency-Key} 헤더가 있을
 * 때만 두 번째를 쓴다. POST 재시도가 안전한 근거는 kinetic-action 이 대상별로
 * {@code Idempotency-Key: <plan_id>:<target_key>} 를 보내고 하위 서비스가 그 키로 중복을 걸러야 한다는 계약이다.
 * 키 없는 POST 는 재시도하지 않는다. 내장 Retry 는 routeId 로 본문 캐싱을 켜므로 재시도 때 본문이 다시 간다.
 */
public class KineticRetryGatewayFilterFactory
        extends AbstractGatewayFilterFactory<KineticRetryGatewayFilterFactory.Config> {

    public static final String IDEMPOTENCY_KEY = "Idempotency-Key";

    public static class Config implements HasRouteId {
        private int retries = 2;
        private String routeId;

        public int getRetries() { return retries; }
        public void setRetries(int retries) { this.retries = retries; }

        @Override
        public void setRouteId(String routeId) { this.routeId = routeId; }

        @Override
        public String getRouteId() { return routeId; }
    }

    private final RetryGatewayFilterFactory retryFactory;

    public KineticRetryGatewayFilterFactory(RetryGatewayFilterFactory retryFactory) {
        super(Config.class);
        this.retryFactory = retryFactory;
    }

    @Override
    public List<String> shortcutFieldOrder() {
        return Collections.singletonList("retries");
    }

    @Override
    public GatewayFilter apply(Config config) {
        final GatewayFilter getOnly = retryFactory.apply(config.getRouteId(), retryConfig(config, HttpMethod.GET));
        final GatewayFilter getAndPost = retryFactory.apply(config.getRouteId(),
                retryConfig(config, HttpMethod.GET, HttpMethod.POST));
        return (exchange, chain) -> {
            boolean idempotentPost = HttpMethod.POST.equals(exchange.getRequest().getMethod())
                    && exchange.getRequest().getHeaders().containsKey(IDEMPOTENCY_KEY);
            return (idempotentPost ? getAndPost : getOnly).filter(exchange, chain);
        };
    }

    private static RetryGatewayFilterFactory.RetryConfig retryConfig(Config config, HttpMethod... methods) {
        RetryGatewayFilterFactory.RetryConfig rc = new RetryGatewayFilterFactory.RetryConfig();
        rc.setRetries(config.getRetries());
        rc.setSeries(HttpStatus.Series.SERVER_ERROR);
        rc.setMethods(methods);
        // exceptions 기본값: IOException, TimeoutException (연결 오류·타임아웃)
        return rc;
    }
}
