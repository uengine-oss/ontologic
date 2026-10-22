package com.roboanalyz.gateway.kinetic;

import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/** CircuitBreaker fallback ({@code forward:/__kinetic/svc-fallback}) → 503 JSON. */
@RestController
public class KineticSvcFallbackController {

    public static final String PATH = "/__kinetic/svc-fallback";

    @RequestMapping(PATH)
    public Mono<Void> fallback(ServerWebExchange exchange) {
        Throwable t = exchange.getAttribute(ServerWebExchangeUtils.CIRCUITBREAKER_EXECUTION_EXCEPTION_ATTR);
        String message = "downstream system unavailable";
        if (t != null) {
            message += " (" + t.getClass().getSimpleName() + (t.getMessage() != null ? ": " + t.getMessage() : "") + ")";
        }
        return KineticErrors.write(exchange.getResponse(), HttpStatus.SERVICE_UNAVAILABLE, "service_unavailable", message);
    }
}
