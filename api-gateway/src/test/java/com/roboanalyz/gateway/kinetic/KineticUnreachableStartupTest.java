package com.roboanalyz.gateway.kinetic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

/** kinetic-action·JWKS 가 기동 시 죽어 있어도 앱이 뜨고, 라우트 갱신 실패는 경고만 남긴다. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "kinetic.url=http://127.0.0.1:1",
        "kinetic.jwks-url=http://127.0.0.1:1/.well-known/jwks.json",
        "kinetic.internal-secret=s",
        "kinetic.route-refresh=1h"
})
class KineticUnreachableStartupTest {

    @Autowired
    WebTestClient client;

    @Autowired
    KineticRouteDefinitionLocator locator;

    @Test
    void startsAndRejectsWithoutCrashing() {
        assertThat(locator.refresh().block()).isFalse();
        assertThat(locator.currentRoutes()).isEmpty();
        client.get().uri("/api/kinetic/actions").exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
        // JWKS 를 못 가져오면 토큰은 검증 불가 → 503 JSON (앱은 계속 동작)
        String token = KineticGatewayIntegrationTest.token("x", "kinetic-action", "http://localhost:8032",
                KineticGatewayIntegrationTest.RSA);
        client.get().uri("/api/kinetic/actions").header(HttpHeaders.AUTHORIZATION, "Bearer " + token).exchange()
                .expectStatus().isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
                .expectBody().jsonPath("$.error.code").isEqualTo("service_unavailable");
    }
}
