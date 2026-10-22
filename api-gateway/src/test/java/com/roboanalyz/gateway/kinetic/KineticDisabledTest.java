package com.roboanalyz.gateway.kinetic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

/** KINETIC_ENABLED=false: 북향 라우트·JWT 없음, 기존 동작(/api/kinetic 도 프론트 catch-all 로) — 401 이 나오지 않는다. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "kinetic.enabled=false",
        "kinetic.url=http://127.0.0.1:1"
})
class KineticDisabledTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ApplicationContext ctx;

    @Test
    void noJwtWhenDisabled() {
        assertThat(ctx.getBeansOfType(KineticNorthboundRoutes.class)).isEmpty();
        client.get().uri("/api/kinetic/actions").exchange()
                .expectHeader().doesNotExist(HttpHeaders.WWW_AUTHENTICATE)
                .expectStatus().value(s -> assertThat(s).isNotEqualTo(401));
        // /svc 가드는 항상 동작
        client.get().uri("/svc/x/y").exchange().expectStatus().isForbidden();
    }
}
