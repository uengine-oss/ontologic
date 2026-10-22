package com.roboanalyz.gateway.kinetic;

import org.springframework.cloud.gateway.handler.predicate.AbstractRoutePredicateFactory;
import org.springframework.web.server.ServerWebExchange;

import java.util.function.Predicate;

/**
 * 라우트 술어 {@code KineticInternal}: X-Kinetic-Internal == KINETIC_INTERNAL_SECRET.
 * Header 술어에 비밀을 정규식으로 넣으면 /actuator/gateway/routes 에 비밀이 노출되므로 별도 술어로 둔다.
 * (SvcInternalGuardFilter 가 라우팅 전에 같은 검사를 하므로 이것은 다중 방어다.)
 */
public class KineticInternalRoutePredicateFactory
        extends AbstractRoutePredicateFactory<KineticInternalRoutePredicateFactory.Config> {

    public static class Config {
    }

    private final KineticProperties props;

    public KineticInternalRoutePredicateFactory(KineticProperties props) {
        super(Config.class);
        this.props = props;
    }

    @Override
    public Predicate<ServerWebExchange> apply(Config config) {
        return exchange -> SvcInternalGuardFilter.secretMatches(props.getInternalSecret(),
                exchange.getRequest().getHeaders().getFirst(SvcInternalGuardFilter.HEADER));
    }
}
