package com.roboanalyz.gateway.kinetic;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 키네틱 북향·남향 통합 테스트. kinetic-action·JWKS·하위 서비스는 MockWebServer 로 흉내 낸다.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class KineticGatewayIntegrationTest {

    static final String SECRET = "test-internal-secret";
    static final String ISSUER = "http://issuer.test";
    static final String AUDIENCE = "kinetic-action";

    static final RSAKey RSA = generateKey("k1");
    static final RSAKey OTHER_RSA = generateKey("k1");

    static final MockWebServer KINETIC = new MockWebServer();
    static final MockWebServer MES = new MockWebServer();
    static final MockWebServer LEGACY = new MockWebServer();
    /** 계약 §8 인증 종류 검증용 하위 서비스와 OAuth2 토큰 엔드포인트. */
    static final MockWebServer SVC2 = new MockWebServer();
    static final MockWebServer IDP = new MockWebServer();
    static final List<RecordedRequest> SVC2_REQUESTS = Collections.synchronizedList(new ArrayList<>());
    static final List<RecordedRequest> IDP_REQUESTS = Collections.synchronizedList(new ArrayList<>());
    static final AtomicInteger IDP_STATUS = new AtomicInteger(200);
    static final AtomicInteger IDP_EXPIRES_IN = new AtomicInteger(3600);
    static final AtomicInteger IDP_SEQ = new AtomicInteger();

    /** 계약 §9.1 login_token — JSON 로그인으로 토큰을 주는 사내 시스템(PriMES 흉내). */
    static final MockWebServer ERP = new MockWebServer();
    static final List<RecordedRequest> ERP_LOGINS = Collections.synchronizedList(new ArrayList<>());
    static final List<RecordedRequest> ERP_CALLS = Collections.synchronizedList(new ArrayList<>());
    static final java.util.Set<String> ERP_VALID = ConcurrentHashMap.newKeySet();
    static final AtomicInteger ERP_LOGIN_STATUS = new AtomicInteger(200);
    static final java.util.concurrent.atomic.AtomicBoolean ERP_REJECT_ALL = new java.util.concurrent.atomic.AtomicBoolean();
    /** 로그인 토큰 모양: 0 = 불투명 문자열, 그 밖 = exp 가 지금 + N초인 JWT. */
    static final AtomicInteger ERP_EXP_IN = new AtomicInteger(3600);

    static final AtomicReference<String> ROUTES_JSON = new AtomicReference<>();
    static final AtomicInteger ROUTES_STATUS = new AtomicInteger(200);
    static final Map<String, AtomicInteger> FLAKY = new ConcurrentHashMap<>();
    static final List<RecordedRequest> MES_REQUESTS = Collections.synchronizedList(new ArrayList<>());
    static final List<RecordedRequest> KINETIC_REQUESTS = Collections.synchronizedList(new ArrayList<>());

    static {
        KINETIC.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest req) {
                String path = req.getPath();
                if (path.startsWith("/.well-known/jwks.json")) {
                    return json(200, new JWKSet(RSA.toPublicJWK()).toString());
                }
                if (path.startsWith("/api/kinetic/systems/routes")) {
                    if (!SECRET.equals(req.getHeader("X-Kinetic-Internal"))) {
                        return json(403, "{\"error\":{\"code\":\"forbidden\"}}");
                    }
                    if (ROUTES_STATUS.get() != 200) {
                        return json(ROUTES_STATUS.get(), "{}");
                    }
                    return json(200, ROUTES_JSON.get());
                }
                KINETIC_REQUESTS.add(req);
                if (path.startsWith("/.well-known/oauth-protected-resource")) {
                    return json(200, "{\"resource\":\"kinetic\",\"authorization_servers\":[\"" + ISSUER + "\"]}");
                }
                if (path.startsWith("/mcp")) {
                    return new MockResponse().setResponseCode(200)
                            .setHeader("Content-Type", "text/event-stream")
                            .setBody("event: message\ndata: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\n\n");
                }
                return json(200, "{\"path\":\"" + path + "\"}");
            }
        });
        MES.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest req) {
                MES_REQUESTS.add(req);
                String path = req.getPath();
                if (path.startsWith("/flaky/")) {
                    int n = FLAKY.computeIfAbsent(path + req.getMethod(), k -> new AtomicInteger()).incrementAndGet();
                    return n <= 2 ? json(500, "{\"err\":" + n + "}") : json(200, "{\"ok\":true,\"attempt\":" + n + "}");
                }
                if (path.startsWith("/always500")) {
                    return json(500, "{\"err\":true}");
                }
                return json(200, "{\"ok\":true}");
            }
        });
        LEGACY.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest req) {
                return json(200, "{\"legacy\":\"" + req.getPath() + "\"}");
            }
        });
        SVC2.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest req) {
                SVC2_REQUESTS.add(req);
                return json(200, "{\"ok\":true}");
            }
        });
        IDP.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest req) {
                IDP_REQUESTS.add(req);
                if (IDP_STATUS.get() != 200) {
                    return json(IDP_STATUS.get(), "{\"error\":\"invalid_client\"}");
                }
                return json(200, "{\"access_token\":\"tok-" + IDP_SEQ.incrementAndGet()
                        + "\",\"token_type\":\"Bearer\",\"expires_in\":" + IDP_EXPIRES_IN.get() + "}");
            }
        });
        ERP.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest req) {
                if (req.getPath().startsWith("/api/auth/login")) {
                    ERP_LOGINS.add(req);
                    if (ERP_LOGIN_STATUS.get() != 200) {
                        return json(ERP_LOGIN_STATUS.get(), "{\"message\":\"bad credentials\"}");
                    }
                    String tok = loginToken(ERP_LOGINS.size(), ERP_EXP_IN.get());
                    ERP_VALID.add(tok);
                    return json(200, "{\"data\":{\"token\":\"" + tok + "\"},\"user\":\"guest\"}");
                }
                ERP_CALLS.add(req);
                String auth = req.getHeader(HttpHeaders.AUTHORIZATION);
                if (ERP_REJECT_ALL.get() || auth == null || !auth.startsWith("Bearer ")
                        || !ERP_VALID.contains(auth.substring(7))) {
                    return json(401, "{\"message\":\"expired\"}");
                }
                return json(200, "{\"molds\":[\"FM540-1\"],\"body\":\"" + req.getBody().readUtf8()
                        .replace("\"", "'") + "\"}");
            }
        });
        try {
            ERP.start();
            KINETIC.start();
            MES.start();
            LEGACY.start();
            SVC2.start();
            IDP.start();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
        ROUTES_JSON.set(defaultRoutes());
    }

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry r) {
        r.add("kinetic.url", () -> "http://127.0.0.1:" + KINETIC.getPort());
        r.add("kinetic.jwks-url", () -> "http://127.0.0.1:" + KINETIC.getPort() + "/.well-known/jwks.json");
        r.add("kinetic.issuer", () -> ISSUER);
        r.add("kinetic.audience", () -> AUDIENCE);
        r.add("kinetic.public-base", () -> "https://gw.example");
        r.add("kinetic.internal-secret", () -> SECRET);
        r.add("kinetic.route-refresh", () -> "1h");
        r.add("kinetic.rate-per-sec", () -> "1");
        r.add("kinetic.rate-burst", () -> "5");
        // 기존 라우트(api-gateway-text2sql, text2sql-service)는 ROBO_TEXT2SQL_URL 플레이스홀더를 쓴다.
        r.add("ROBO_TEXT2SQL_URL", () -> "http://127.0.0.1:" + LEGACY.getPort());
    }

    @TestConfiguration
    static class TestEnv {
        @Bean
        @Primary
        EnvLookup testEnvLookup() {
            Map<String, String> env = new HashMap<>();
            env.put("MES_API_KEY", "mes-secret-value");
            env.put("Q_KEY", "q value&=1");
            env.put("BASIC_CRED", "svc-user:pa:ss");
            env.put("BEARER_TOK", "bt-value");
            env.put("OAUTH_SECRET", "cs-value");
            env.put("ERP_ID", "guest");
            env.put("ERP_PW", "1234!@#$");
            return env::get;
        }
    }

    @AfterAll
    static void stop() throws Exception {
        KINETIC.shutdown();
        MES.shutdown();
        LEGACY.shutdown();
        SVC2.shutdown();
        IDP.shutdown();
        ERP.shutdown();
    }

    @Autowired
    KineticSystemAuthGatewayFilterFactory systemAuth;

    @Autowired
    WebTestClient client;

    @Autowired
    KineticRouteDefinitionLocator locator;

    @BeforeEach
    void setUp() {
        client = client.mutate().responseTimeout(Duration.ofSeconds(30)).build();
        MES_REQUESTS.clear();
        KINETIC_REQUESTS.clear();
        SVC2_REQUESTS.clear();
        IDP_REQUESTS.clear();
        IDP_STATUS.set(200);
        IDP_EXPIRES_IN.set(3600);
        ERP_LOGINS.clear();
        ERP_CALLS.clear();
        ERP_VALID.clear();
        ERP_LOGIN_STATUS.set(200);
        ERP_EXP_IN.set(3600);
        systemAuth.clearTokenCache();
        ROUTES_STATUS.set(200);
        locator.refresh().block();
        awaitRoute("/svc/mock-mes/ping");
    }

    // ---------------------------------------------------------------- 기존 라우트

    @Test
    void existingRouteUnaffectedWithoutAuth() {
        client.get().uri("/text2sql/health").exchange()
                .expectStatus().isOk()
                .expectHeader().doesNotExist(HttpHeaders.WWW_AUTHENTICATE)
                .expectBody().jsonPath("$.legacy").isEqualTo("/text2sql/health");
        client.get().uri("/api/gateway/text2sql/x").exchange()
                .expectStatus().isOk()
                .expectBody().jsonPath("$.legacy").isEqualTo("/text2sql/x");
    }

    @Test
    void existingRoutePreflightUnchanged() {
        client.options().uri("/text2sql/health")
                .header("Origin", "http://localhost:3000")
                .header("Access-Control-Request-Method", "POST")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("Access-Control-Allow-Origin", "http://localhost:3000");
    }

    // ---------------------------------------------------------------- 북향 JWT

    @Test
    void apiKineticWithoutTokenIs401WithResourceMetadata() {
        client.get().uri("/api/kinetic/actions").exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(HttpHeaders.WWW_AUTHENTICATE,
                        "Bearer resource_metadata=\"https://gw.example/.well-known/oauth-protected-resource/mcp/kinetic\"")
                .expectBody().jsonPath("$.error.code").isEqualTo("unauthenticated")
                .jsonPath("$.error.message").exists();
        assertThat(KINETIC_REQUESTS).isEmpty();
    }

    @Test
    void mcpWithoutTokenIs401() {
        client.post().uri("/mcp/kinetic").exchange().expectStatus().isUnauthorized()
                .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void validTokenIsProxiedWithAuthorizationForwarded() throws Exception {
        String token = token("alice", AUDIENCE, ISSUER, RSA);
        client.get().uri("/api/kinetic/actions?class=Equipment")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .header("X-Kinetic-Internal", "spoofed")
                .exchange()
                .expectStatus().isOk()
                .expectBody().jsonPath("$.path").isEqualTo("/api/kinetic/actions?class=Equipment");
        RecordedRequest rec = lastKinetic();
        assertThat(rec.getHeader(HttpHeaders.AUTHORIZATION)).isEqualTo("Bearer " + token);
        assertThat(rec.getHeader("X-Kinetic-Internal")).isNull();
    }

    @Test
    void mcpIsRewrittenAndStreamed() throws Exception {
        String token = token("mcp-user", AUDIENCE, ISSUER, RSA);
        EntityExchangeResult<byte[]> res = client.post().uri("/mcp/kinetic")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON, MediaType.TEXT_EVENT_STREAM)
                .bodyValue("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .expectBody().returnResult();
        assertThat(new String(res.getResponseBody(), "UTF-8")).contains("\"jsonrpc\":\"2.0\"");
        assertThat(lastKinetic().getPath()).isEqualTo("/mcp");

        client.post().uri("/mcp/kinetic/messages")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .exchange().expectStatus().isOk();
        assertThat(lastKinetic().getPath()).isEqualTo("/mcp/messages");
    }

    @Test
    void wrongAudienceIs401() {
        client.get().uri("/api/kinetic/actions")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token("bob", "someone-else", ISSUER, RSA))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().value(HttpHeaders.WWW_AUTHENTICATE, v -> assertThat(v).contains("resource_metadata="))
                .expectBody().jsonPath("$.error.code").isEqualTo("unauthenticated");
    }

    @Test
    void wrongIssuerAndWrongKeyAre401() {
        client.get().uri("/api/kinetic/actions")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token("bob", AUDIENCE, "http://evil", RSA))
                .exchange().expectStatus().isUnauthorized();
        client.get().uri("/api/kinetic/actions")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token("bob", AUDIENCE, ISSUER, OTHER_RSA))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wellKnownIsPublic() throws Exception {
        client.get().uri("/.well-known/oauth-protected-resource/mcp/kinetic").exchange()
                .expectStatus().isOk().expectBody().jsonPath("$.resource").isEqualTo("kinetic");
        assertThat(lastKinetic().getPath()).isEqualTo("/.well-known/oauth-protected-resource");
        client.get().uri("/.well-known/oauth-protected-resource").exchange().expectStatus().isOk();
        assertThat(lastKinetic().getPath()).isEqualTo("/.well-known/oauth-protected-resource");
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/api/kinetic/health").exchange().expectStatus().isOk();
    }

    @Test
    void internalRoutesEndpointNotExposedNorthbound() {
        client.get().uri("/api/kinetic/systems/routes")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token("carol", AUDIENCE, ISSUER, RSA))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void kineticPreflightPasses() {
        client.options().uri("/api/kinetic/plans")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "authorization,content-type")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("Access-Control-Allow-Origin", "http://localhost:5173");
    }

    @Test
    void unauthorizedResponseCarriesCorsHeaders() {
        client.get().uri("/api/kinetic/actions").header("Origin", "http://localhost:3000").exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals("Access-Control-Allow-Origin", "http://localhost:3000")
                .expectHeader().value("Access-Control-Expose-Headers",
                        v -> assertThat(v).contains(HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void rateLimitPerSubjectReturns429() {
        String token = token("rate-limited-user", AUDIENCE, ISSUER, RSA);
        int ok = 0;
        int limited = 0;
        String lastBody = null;
        for (int i = 0; i < 8; i++) {
            EntityExchangeResult<byte[]> r = client.get().uri("/api/kinetic/actions")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                    .exchange().expectBody().returnResult();
            if (r.getStatus() == HttpStatus.TOO_MANY_REQUESTS) {
                limited++;
                lastBody = new String(r.getResponseBody());
            } else if (r.getStatus() == HttpStatus.OK) {
                ok++;
            }
        }
        assertThat(ok).isBetween(5, 6);
        assertThat(limited).isGreaterThanOrEqualTo(2);
        assertThat(lastBody).contains("\"code\":\"rate_limited\"");
        // 다른 주체는 영향 없음
        client.get().uri("/api/kinetic/actions")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token("other-user", AUDIENCE, ISSUER, RSA))
                .exchange().expectStatus().isOk();
    }

    // ---------------------------------------------------------------- 남향 /svc

    @Test
    void svcWithoutSecretIs403() {
        client.get().uri("/svc/mock-mes/equipment/E1").exchange()
                .expectStatus().isForbidden()
                .expectBody().jsonPath("$.error.code").isEqualTo("forbidden");
        client.get().uri("/svc/mock-mes/equipment/E1").header("X-Kinetic-Internal", "wrong").exchange()
                .expectStatus().isForbidden();
        client.get().uri("/svc/unknown-system/x").exchange()
                .expectStatus().isForbidden()
                .expectBody().jsonPath("$.error.code").isEqualTo("forbidden");
        assertThat(MES_REQUESTS).isEmpty();
    }

    @Test
    void svcUnknownSystemWithSecretIs404() {
        client.get().uri("/svc/unknown-system/x").header("X-Kinetic-Internal", SECRET).exchange()
                .expectStatus().isNotFound()
                .expectBody().jsonPath("$.error.code").isEqualTo("not_found");
    }

    @Test
    void svcWithSecretIsProxiedRewrittenStrippedAndAuthInjected() {
        client.put().uri("/svc/mock-mes/equipment/E1/status?x=1")
                .header("X-Kinetic-Internal", SECRET)
                .header("Idempotency-Key", "p1:E1")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"status\":\"MAINTENANCE\"}")
                .exchange()
                .expectStatus().isOk()
                .expectBody().jsonPath("$.ok").isEqualTo(true);
        assertThat(MES_REQUESTS).hasSize(1);
        RecordedRequest rec = MES_REQUESTS.get(0);
        assertThat(rec.getPath()).isEqualTo("/equipment/E1/status?x=1");
        assertThat(rec.getMethod()).isEqualTo("PUT");
        assertThat(rec.getHeader("X-Kinetic-Internal")).isNull();
        assertThat(rec.getHeader("X-Api-Key")).isEqualTo("mes-secret-value");
        assertThat(rec.getHeader("Idempotency-Key")).isEqualTo("p1:E1");
        assertThat(rec.getBody().readUtf8()).isEqualTo("{\"status\":\"MAINTENANCE\"}");
    }

    @Test
    void svcGet5xxIsRetried() {
        client.get().uri("/svc/mock-mes/flaky/get").header("X-Kinetic-Internal", SECRET).exchange()
                .expectStatus().isOk()
                .expectBody().jsonPath("$.attempt").isEqualTo(3);
        assertThat(MES_REQUESTS).hasSize(3);
    }

    @Test
    void svcPostWithIdempotencyKeyIsRetriedWithBody() {
        client.post().uri("/svc/mock-mes/flaky/post").header("X-Kinetic-Internal", SECRET)
                .header("Idempotency-Key", "plan-1:E7")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"a\":1}")
                .exchange()
                .expectStatus().isOk()
                .expectBody().jsonPath("$.attempt").isEqualTo(3);
        assertThat(MES_REQUESTS).hasSize(3);
        for (RecordedRequest r : MES_REQUESTS) {
            assertThat(r.getBody().readUtf8()).isEqualTo("{\"a\":1}");
        }
    }

    @Test
    void svcPostWithoutIdempotencyKeyIsNotRetried() {
        client.post().uri("/svc/mock-mes/flaky/post-nokey").header("X-Kinetic-Internal", SECRET)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"a\":1}")
                .exchange()
                .expectStatus().isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(MES_REQUESTS).hasSize(1);
    }

    @Test
    void dynamicRefreshPicksUpNewSystemAndKeepsRoutesWhenSourceDown() {
        String before = ROUTES_JSON.get();
        try {
            ROUTES_JSON.set(routesJson(
                    route("mock-mes", MES.url("/").toString(), "X-Api-Key", "MES_API_KEY", 3000),
                    route("mock-erp", MES.url("/").toString(), null, null, 2000),
                    route("dead", "http://127.0.0.1:1", null, null, 500)));
            assertThat(locator.refresh().block()).isTrue();
            awaitRoute("/svc/mock-erp/orders/1");
            client.get().uri("/svc/mock-erp/orders/1").header("X-Kinetic-Internal", SECRET).exchange()
                    .expectStatus().isOk();
            RecordedRequest rec = MES_REQUESTS.get(MES_REQUESTS.size() - 1);
            assertThat(rec.getPath()).isEqualTo("/orders/1");
            assertThat(rec.getHeader("X-Api-Key")).isNull();

            // 연결 불가 시스템 → 재시도 후 CircuitBreaker fallback 503 JSON
            client.get().uri("/svc/dead/x").header("X-Kinetic-Internal", SECRET).exchange()
                    .expectStatus().isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
                    .expectBody().jsonPath("$.error.code").isEqualTo("service_unavailable");

            // 원천이 죽어도 마지막 라우트 유지
            ROUTES_STATUS.set(500);
            assertThat(locator.refresh().block()).isFalse();
            client.get().uri("/svc/mock-erp/orders/2").header("X-Kinetic-Internal", SECRET).exchange()
                    .expectStatus().isOk();
            ROUTES_STATUS.set(200);
        } finally {
            ROUTES_STATUS.set(200);
            ROUTES_JSON.set(before);
            locator.refresh().block();
        }
    }

    @Test
    void unchangedRoutesDoNotRepublish() {
        assertThat(locator.refresh().block()).isFalse();
    }

    // ---------------------------------------------------------------- 남향 인증 종류 (계약 §8)

    @Test
    void apiKeyQueryParamIsInjectedEncoded() {
        svc2("/svc/k-query/items?x=1").expectStatus().isOk();
        RecordedRequest rec = SVC2_REQUESTS.get(0);
        assertThat(rec.getPath()).isEqualTo("/items?x=1&apikey=q%20value%26%3D1");
        assertThat(rec.getRequestUrl().queryParameter("apikey")).isEqualTo("q value&=1");
        assertThat(rec.getHeader("X-API-Key")).isNull();
    }

    @Test
    void basicAuthIsInjected() {
        svc2("/svc/k-basic/items").expectStatus().isOk();
        String expected = "Basic " + java.util.Base64.getEncoder()
                .encodeToString("svc-user:pa:ss".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        assertThat(SVC2_REQUESTS.get(0).getHeader(HttpHeaders.AUTHORIZATION)).isEqualTo(expected);
    }

    @Test
    void bearerGetsPrefixAndKineticCallerAuthorizationIsReplaced() {
        client.get().uri("/svc/k-bearer/items").header("X-Kinetic-Internal", SECRET)
                .header(HttpHeaders.AUTHORIZATION, "Bearer caller-token").exchange().expectStatus().isOk();
        assertThat(SVC2_REQUESTS.get(0).getHeader(HttpHeaders.AUTHORIZATION)).isEqualTo("Bearer bt-value");
    }

    @Test
    void oauth2ClientCredentialsTokenIsFetchedCachedAndInjected() throws Exception {
        for (int i = 0; i < 3; i++) {
            svc2("/svc/k-oauth/items/" + i).expectStatus().isOk();
        }
        assertThat(IDP_REQUESTS).hasSize(1);
        RecordedRequest tokenReq = IDP_REQUESTS.get(0);
        assertThat(tokenReq.getMethod()).isEqualTo("POST");
        assertThat(tokenReq.getPath()).isEqualTo("/oauth/token");
        assertThat(tokenReq.getHeader(HttpHeaders.CONTENT_TYPE)).startsWith("application/x-www-form-urlencoded");
        String form = java.net.URLDecoder.decode(tokenReq.getBody().readUtf8(), "UTF-8");
        assertThat(form).contains("grant_type=client_credentials", "client_id=kinetic-gateway",
                "client_secret=cs-value", "scope=aps.write aps.read");
        String token = SVC2_REQUESTS.get(0).getHeader(HttpHeaders.AUTHORIZATION);
        assertThat(token).startsWith("Bearer tok-");
        for (RecordedRequest r : SVC2_REQUESTS) {
            assertThat(r.getHeader(HttpHeaders.AUTHORIZATION)).isEqualTo(token);
        }
        assertThat(SVC2_REQUESTS.get(0).getHeader("X-Kinetic-Internal")).isNull();
    }

    @Test
    void oauth2TokenNearExpiryIsRefreshed() {
        IDP_EXPIRES_IN.set(30); // 60초 여유보다 짧다 → 캐시하지 않는다
        svc2("/svc/k-oauth/a").expectStatus().isOk();
        svc2("/svc/k-oauth/b").expectStatus().isOk();
        assertThat(IDP_REQUESTS).hasSize(2);
        assertThat(SVC2_REQUESTS.get(0).getHeader(HttpHeaders.AUTHORIZATION))
                .isNotEqualTo(SVC2_REQUESTS.get(1).getHeader(HttpHeaders.AUTHORIZATION));
    }

    @Test
    void oauth2TokenEndpointFailureIs503AuthUnavailableWithoutCallingService() {
        IDP_STATUS.set(401);
        EntityExchangeResult<byte[]> r = svc2("/svc/k-oauth/items").expectStatus()
                .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
                .expectBody().jsonPath("$.error.code").isEqualTo("auth_unavailable").returnResult();
        String body = new String(r.getResponseBody());
        assertThat(body).contains("HTTP 401").doesNotContain("cs-value");
        assertThat(SVC2_REQUESTS).isEmpty();
        // 복구되면 다음 요청은 새로 발급
        IDP_STATUS.set(200);
        svc2("/svc/k-oauth/items").expectStatus().isOk();
        assertThat(SVC2_REQUESTS).hasSize(1);
    }

    @Test
    void oauth2MissingSecretEnvIs503() {
        svc2("/svc/k-oauth-nosecret/items").expectStatus().isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
                .expectBody().jsonPath("$.error.code").isEqualTo("auth_unavailable");
        assertThat(IDP_REQUESTS).isEmpty();
        assertThat(SVC2_REQUESTS).isEmpty();
    }

    @Test
    void routeDefinitionsCarryEnvNamesOnlyAndRouteRetries() {
        String defs = locator.getRouteDefinitions().collectList().block().toString();
        assertThat(defs).contains("OAUTH_SECRET", "BASIC_CRED", "Q_KEY")
                .doesNotContain("cs-value", "svc-user:pa:ss", "q value");
        org.springframework.cloud.gateway.route.RouteDefinition oauth = locator.getRouteDefinitions()
                .filter(d -> d.getId().equals("svc-k-oauth")).blockFirst();
        assertThat(oauth.getFilters()).noneMatch(f -> f.getName().equals("KineticRetry")); // retries 0
        org.springframework.cloud.gateway.route.RouteDefinition basic = locator.getRouteDefinitions()
                .filter(d -> d.getId().equals("svc-k-basic")).blockFirst();
        assertThat(basic.getFilters()).anySatisfy(f -> {
            assertThat(f.getName()).isEqualTo("KineticRetry");
            assertThat(f.getArgs()).containsEntry("retries", "1");
        });
    }

    // ---------------------------------------------------------------- login_token (계약 §9.1)

    @Test
    void loginTokenLogsInOnceCachesAndInjects() throws Exception {
        for (int i = 0; i < 3; i++) {
            svc2("/svc/k-login/api/mold/views/mold").expectStatus().isOk()
                    .expectBody().jsonPath("$.molds[0]").isEqualTo("FM540-1");
        }
        assertThat(ERP_LOGINS).hasSize(1);
        RecordedRequest login = ERP_LOGINS.get(0);
        assertThat(login.getMethod()).isEqualTo("POST");
        assertThat(login.getHeader(HttpHeaders.CONTENT_TYPE)).startsWith("application/json");
        com.fasterxml.jackson.databind.JsonNode body = new com.fasterxml.jackson.databind.ObjectMapper()
                .readTree(login.getBody().readUtf8());
        assertThat(body.get("tenant").asText()).isEqualTo("standard");
        assertThat(body.get("loginId").asText()).isEqualTo("guest");
        assertThat(body.get("password").asText()).isEqualTo("1234!@#$");
        assertThat(ERP_CALLS).hasSize(3);
        String auth = ERP_CALLS.get(0).getHeader(HttpHeaders.AUTHORIZATION);
        assertThat(auth).startsWith("Bearer ");
        for (RecordedRequest r : ERP_CALLS) {
            assertThat(r.getHeader(HttpHeaders.AUTHORIZATION)).isEqualTo(auth);
            assertThat(r.getHeader("X-Kinetic-Internal")).isNull();
            assertThat(r.getPath()).isEqualTo("/api/mold/views/mold");
        }
        // 라우트 정의에는 env 이름만
        String defs = locator.getRouteDefinitions().collectList().block().toString();
        assertThat(defs).contains("ERP_ID", "ERP_PW").doesNotContain("1234!@#$");
    }

    @Test
    void loginTokenExpiryFromJwtExpOrTtl() {
        ERP_EXP_IN.set(30); // exp 가 60초 안 → 캐시하지 않는다
        svc2("/svc/k-login/a").expectStatus().isOk();
        svc2("/svc/k-login/b").expectStatus().isOk();
        assertThat(ERP_LOGINS).hasSize(2);

        systemAuth.clearTokenCache();
        ERP_EXP_IN.set(7200);
        svc2("/svc/k-login/c").expectStatus().isOk();
        long left = systemAuth.tokenValidUntil("svc-k-login") - System.currentTimeMillis();
        assertThat(left).isBetween((7200L - 60 - 10) * 1000, (7200L - 60) * 1000);

        systemAuth.clearTokenCache();
        ERP_EXP_IN.set(0); // JWT 아님 → ttl_seconds (라우트 900)
        svc2("/svc/k-login/d").expectStatus().isOk();
        left = systemAuth.tokenValidUntil("svc-k-login") - System.currentTimeMillis();
        assertThat(left).isBetween((900L - 60 - 10) * 1000, (900L - 60) * 1000);
        assertThat(ERP_LOGINS).hasSize(4);
    }

    @Test
    void loginToken401ReloginsOnceAndRetriesWithBody() {
        svc2("/svc/k-login/warm").expectStatus().isOk();
        ERP_VALID.clear(); // 서버가 토큰을 버렸다 (재시작 등)
        client.post().uri("/svc/k-login/api/orders").header("X-Kinetic-Internal", SECRET)
                .header("Idempotency-Key", "p:EQ:main:a1")
                .contentType(MediaType.APPLICATION_JSON).bodyValue("{\"lines\":[{\"q\":1}]}")
                .exchange()
                .expectStatus().isOk()
                .expectBody().jsonPath("$.body").isEqualTo("{'lines':[{'q':1}]}");
        assertThat(ERP_LOGINS).hasSize(2);
        assertThat(ERP_CALLS).hasSize(3); // warm + 401 + 재시도
        assertThat(ERP_CALLS.get(1).getHeader(HttpHeaders.AUTHORIZATION))
                .isNotEqualTo(ERP_CALLS.get(2).getHeader(HttpHeaders.AUTHORIZATION));
        // 재시도 본문은 응답의 $.body 로 확인했다 (하위 서비스가 받은 본문을 그대로 돌려준다)

        // 재로그인 후에도 401 이면 한 번만 — 401 을 그대로 돌려준다
        ERP_EXP_IN.set(0);
        ERP_LOGINS.clear();
        ERP_CALLS.clear();
        ERP_VALID.clear();
        systemAuth.clearTokenCache();
        ERP_LOGIN_STATUS.set(200);
        ERP_REJECT_ALL.set(true); // 로그인은 되지만 하위 서비스가 늘 거부
        try {
            svc2("/svc/k-login/always401").expectStatus().isUnauthorized();
        } finally {
            ERP_REJECT_ALL.set(false);
        }
        assertThat(ERP_CALLS.size()).isEqualTo(2);
        assertThat(ERP_LOGINS.size()).isEqualTo(2);
    }

    @Test
    void loginTokenFailureIs503AuthUnavailableWithoutCallingService() {
        ERP_LOGIN_STATUS.set(401);
        EntityExchangeResult<byte[]> r = svc2("/svc/k-login/items").expectStatus()
                .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
                .expectBody().jsonPath("$.error.code").isEqualTo("auth_unavailable").returnResult();
        assertThat(new String(r.getResponseBody())).contains("HTTP 401").doesNotContain("1234!@#$");
        assertThat(ERP_CALLS).isEmpty();
        ERP_LOGIN_STATUS.set(200);
        svc2("/svc/k-login/items").expectStatus().isOk();
        assertThat(ERP_CALLS).hasSize(1);
    }

    @Test
    void loginTokenMissingEnvIs503() {
        svc2("/svc/k-login-noenv/items").expectStatus().isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
                .expectBody().jsonPath("$.error.code").isEqualTo("auth_unavailable")
                .jsonPath("$.error.message").value(m -> assertThat(m.toString()).contains("MISSING_PW"));
        assertThat(ERP_LOGINS).isEmpty();
        assertThat(ERP_CALLS).isEmpty();
    }

    static String loginToken(int n, int expIn) {
        if (expIn == 0) {
            return "opaque-" + n;
        }
        java.util.Base64.Encoder b64 = java.util.Base64.getUrlEncoder().withoutPadding();
        String header = b64.encodeToString("{\"alg\":\"HS256\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        String payload = b64.encodeToString(("{\"sub\":\"guest\",\"n\":" + n + ",\"exp\":"
                + (System.currentTimeMillis() / 1000 + expIn) + "}").getBytes(java.nio.charset.StandardCharsets.UTF_8));
        return header + "." + payload + ".sig";
    }

    static Map<String, Object> loginRoute(String system, String passwordEnv) {
        Map<String, Object> r = route(system, ERP.url("/").toString(), null, null, 3000);
        r.put("auth_kind", "login_token");
        Map<String, Object> l = new HashMap<>();
        l.put("token_url", ERP.url("/api/auth/login").toString());
        l.put("login_body", Collections.singletonMap("tenant", "standard"));
        l.put("username_field", "loginId");
        l.put("username_env", "ERP_ID");
        l.put("password_field", "password");
        l.put("password_env", passwordEnv);
        l.put("token_path", "data.token");
        l.put("header", "Authorization");
        l.put("scheme", "Bearer");
        l.put("ttl_seconds", 900);
        r.put("login_token", l);
        r.put("retries", 0);
        return r;
    }

    private WebTestClient.ResponseSpec svc2(String path) {
        return client.get().uri(path).header("X-Kinetic-Internal", SECRET).exchange();
    }

    static String defaultRoutes() {
        String svc2 = SVC2.url("/").toString();
        Map<String, Object> query = route("k-query", svc2, null, "Q_KEY", 3000);
        query.put("auth_kind", "api_key");
        query.put("auth_query_param", "apikey");
        Map<String, Object> basic = route("k-basic", svc2, null, null, 3000);
        basic.put("auth_kind", "basic");
        basic.put("basic_env", "BASIC_CRED");
        basic.put("retries", 1);
        Map<String, Object> bearer = route("k-bearer", svc2, "Authorization", "BEARER_TOK", 3000);
        bearer.put("auth_kind", "bearer");
        Map<String, Object> oauth = route("k-oauth", svc2, null, null, 3000);
        oauth.put("auth_kind", "oauth2_client_credentials");
        Map<String, Object> o2 = new HashMap<>();
        o2.put("token_url", IDP.url("/oauth/token").toString());
        o2.put("client_id", "kinetic-gateway");
        o2.put("client_secret_env", "OAUTH_SECRET");
        o2.put("scopes", Arrays.asList("aps.write", "aps.read"));
        oauth.put("oauth2", o2);
        oauth.put("retries", 0);
        Map<String, Object> noSecret = route("k-oauth-nosecret", svc2, null, null, 3000);
        noSecret.put("auth_kind", "oauth2_client_credentials");
        Map<String, Object> o3 = new HashMap<>(o2);
        o3.put("client_secret_env", "MISSING_SECRET");
        noSecret.put("oauth2", o3);
        return routesJson(route("mock-mes", MES.url("/").toString(), "X-Api-Key", "MES_API_KEY", 3000),
                query, basic, bearer, oauth, noSecret, loginRoute("k-login", "ERP_PW"),
                loginRoute("k-login-noenv", "MISSING_PW"));
    }

    // ---------------------------------------------------------------- helpers

    private void awaitRoute(String path) {
        long deadline = System.currentTimeMillis() + 5000;
        while (System.currentTimeMillis() < deadline) {
            HttpStatus s = client.get().uri(path).header("X-Kinetic-Internal", SECRET).exchange()
                    .returnResult(byte[].class).getStatus();
            if (s != HttpStatus.NOT_FOUND) {
                MES_REQUESTS.clear();
                return;
            }
            try {
                Thread.sleep(50);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
        throw new AssertionError("route for " + path + " never appeared");
    }

    private static RecordedRequest lastKinetic() {
        assertThat(KINETIC_REQUESTS).isNotEmpty();
        return KINETIC_REQUESTS.get(KINETIC_REQUESTS.size() - 1);
    }

    static Map<String, Object> route(String system, String uri, String authHeader, String env, int timeoutMs) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", "svc-" + system);
        m.put("system", system);
        m.put("path_prefix", "/svc/" + system);
        m.put("uri", uri.endsWith("/") ? uri.substring(0, uri.length() - 1) : uri);
        m.put("auth_header", authHeader);
        m.put("auth_value_env", env);
        m.put("timeout_ms", timeoutMs);
        return m;
    }

    @SafeVarargs
    static String routesJson(Map<String, Object>... routes) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(Arrays.asList(routes));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    static String token(String sub, String aud, String iss, RSAKey key) {
        try {
            JWTClaimsSet claims = new JWTClaimsSet.Builder()
                    .subject(sub)
                    .issuer(iss)
                    .audience(aud)
                    .claim("roles", Collections.singletonList("plant_operator"))
                    .issueTime(new Date())
                    .expirationTime(new Date(System.currentTimeMillis() + TimeUnit.MINUTES.toMillis(5)))
                    .build();
            SignedJWT jwt = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256)
                    .keyID(key.getKeyID()).type(JOSEObjectType.JWT).build(), claims);
            jwt.sign(new RSASSASigner(key));
            return jwt.serialize();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    static RSAKey generateKey(String kid) {
        try {
            return new RSAKeyGenerator(2048).keyID(kid).generate();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    static MockResponse json(int status, String body) {
        return new MockResponse().setResponseCode(status).setHeader("Content-Type", "application/json").setBody(body);
    }
}
