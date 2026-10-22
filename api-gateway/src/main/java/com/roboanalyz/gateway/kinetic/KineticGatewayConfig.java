package com.roboanalyz.gateway.kinetic;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.ReactiveResilience4JCircuitBreakerFactory;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.gateway.filter.factory.RetryGatewayFilterFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

import java.time.Duration;

/** 남향(/svc/**) 구성 요소 빈. */
@Configuration
public class KineticGatewayConfig {

    @Bean
    public EnvLookup kineticEnvLookup() {
        return EnvLookup.system();
    }

    @Bean
    public SvcInternalGuardFilter svcInternalGuardFilter(KineticProperties props) {
        return new SvcInternalGuardFilter(props);
    }

    @Bean
    public KineticInternalRoutePredicateFactory kineticInternalRoutePredicateFactory(KineticProperties props) {
        return new KineticInternalRoutePredicateFactory(props);
    }

    @Bean
    public KineticSystemAuthGatewayFilterFactory kineticSystemAuthGatewayFilterFactory(
            EnvLookup envLookup, WebClient.Builder webClientBuilder) {
        return new KineticSystemAuthGatewayFilterFactory(envLookup, webClientBuilder.clone());
    }

    @Bean
    public KineticRetryGatewayFilterFactory kineticRetryGatewayFilterFactory(RetryGatewayFilterFactory retryFactory) {
        return new KineticRetryGatewayFilterFactory(retryFactory);
    }

    @Bean
    public KineticRouteDefinitionLocator kineticRouteDefinitionLocator(KineticProperties props,
                                                                      WebClient.Builder webClientBuilder,
                                                                      ApplicationEventPublisher publisher) {
        return new KineticRouteDefinitionLocator(props, webClientBuilder, publisher);
    }

    /**
     * Resilience4j 기본값 조정: TimeLimiter 기본 1s 는 남향 호출을 끊어버리므로 사실상 끄고(10분)
     * 호출 시간 상한은 라우트별 response-timeout(timeout_ms) 이 맡는다. 회로는 최근 20회 중 50% 실패면 30초 열림.
     */
    @Bean
    public Customizer<ReactiveResilience4JCircuitBreakerFactory> kineticCircuitBreakerDefaults() {
        return factory -> factory.configureDefault(id -> new Resilience4JConfigBuilder(id)
                .timeLimiterConfig(TimeLimiterConfig.custom().timeoutDuration(Duration.ofMinutes(10)).build())
                .circuitBreakerConfig(CircuitBreakerConfig.custom()
                        .slidingWindowSize(20)
                        .minimumNumberOfCalls(10)
                        .failureRateThreshold(50)
                        .waitDurationInOpenState(Duration.ofSeconds(30))
                        .permittedNumberOfCallsInHalfOpenState(3)
                        .build())
                .build());
    }
}
