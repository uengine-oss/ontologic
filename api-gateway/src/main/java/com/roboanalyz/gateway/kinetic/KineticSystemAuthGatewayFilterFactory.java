package com.roboanalyz.gateway.kinetic;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.event.EnableBodyCachingEvent;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.cloud.gateway.filter.factory.RetryGatewayFilterFactory;
import org.springframework.cloud.gateway.support.HasRouteId;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.util.UriComponentsBuilder;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.util.UriUtils;
import reactor.core.publisher.Mono;
import reactor.netty.Connection;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.Base64;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 필터 {@code KineticSystemAuth} — 남향 시스템 인증 주입 (계약 §5·§8). 비밀 값은 라우트 정의에 들어가지 않는다
 * (환경 변수 <b>이름</b>만) — actuator 로 비밀이 새지 않는다. 비밀 값·토큰은 로그에 남기지 않는다.
 *
 * <ul>
 *   <li>{@code kind} 없음 또는 {@code api_key}/{@code bearer} + {@code header}: {@code header: env 값}
 *       (bearer 는 {@code Bearer } 접두가 없으면 붙인다) — 종전 동작</li>
 *   <li>{@code api_key} + {@code queryParam}: 쿼리 파라미터로 env 값</li>
 *   <li>{@code basic} + {@code basicEnv}: {@code Authorization: Basic base64(env 값 "user:password")}</li>
 *   <li>{@code oauth2_client_credentials}: {@code tokenUrl} 에 form POST
 *       (grant_type=client_credentials, client_id, client_secret=env[clientSecretEnv], scope) →
 *       {@code Authorization: Bearer <access_token>}. 토큰은 라우트별로 만료 60초 전까지 캐시한다.
 *       토큰 발급 실패 → 503 {@code auth_unavailable} (하위 서비스는 부르지 않는다).</li>
 *   <li>{@code login_token} (계약 §9.1): {@code tokenUrl} 에 JSON POST
 *       ({@code loginBody} 고정 필드 + {@code usernameField: env[usernameEnv]}, {@code passwordField: env[passwordEnv]})
 *       → 응답의 {@code tokenPath}(점 경로) 토큰을 {@code header: <scheme> <token>} 로 주입. 라우트별 캐시 —
 *       만료는 JWT {@code exp}(검증 없이 읽기)가 있으면 그것, 없으면 {@code ttlSeconds}(기본 1800), 만료 60초 전 갱신.
 *       하위 응답이 401 이면 그 토큰을 버리고 <b>한 번</b> 재로그인 후 재시도한다(요청 본문은 캐시해 다시 보낸다).
 *       로그인 실패·env 없음 → 503 {@code auth_unavailable}.</li>
 * </ul>
 * env 가 비어 있으면(api_key·bearer·basic) 경고 한 번 남기고 인증 없이 보낸다 — 서비스가 401 을 줄 것.
 */
public class KineticSystemAuthGatewayFilterFactory
        extends AbstractGatewayFilterFactory<KineticSystemAuthGatewayFilterFactory.Config> {

    private static final Logger log = LoggerFactory.getLogger(KineticSystemAuthGatewayFilterFactory.class);

    static final long REFRESH_SKEW_SECONDS = 60;
    static final long DEFAULT_EXPIRES_IN_SECONDS = 300;
    static final long DEFAULT_LOGIN_TTL_SECONDS = 1800;
    static final String RAW_SCHEME = "-";

    public static class Config implements HasRouteId {
        private String kind;
        private String header;
        private String env;
        private String queryParam;
        private String basicEnv;
        private String tokenUrl;
        private String clientId;
        private String clientSecretEnv;
        private String scopes;   // 공백 구분
        private String cacheKey; // 보통 라우트 id
        // login_token
        private String loginBody;     // JSON 객체 문자열 (비밀 없음)
        private String usernameField;
        private String usernameEnv;
        private String passwordField;
        private String passwordEnv;
        private String tokenPath;
        private String scheme;        // "-" = 접두 없이 토큰만
        private Long ttlSeconds;
        private String routeId;

        public String getKind() { return kind; }
        public void setKind(String kind) { this.kind = kind; }
        public String getHeader() { return header; }
        public void setHeader(String header) { this.header = header; }
        public String getEnv() { return env; }
        public void setEnv(String env) { this.env = env; }
        public String getQueryParam() { return queryParam; }
        public void setQueryParam(String queryParam) { this.queryParam = queryParam; }
        public String getBasicEnv() { return basicEnv; }
        public void setBasicEnv(String basicEnv) { this.basicEnv = basicEnv; }
        public String getTokenUrl() { return tokenUrl; }
        public void setTokenUrl(String tokenUrl) { this.tokenUrl = tokenUrl; }
        public String getClientId() { return clientId; }
        public void setClientId(String clientId) { this.clientId = clientId; }
        public String getClientSecretEnv() { return clientSecretEnv; }
        public void setClientSecretEnv(String clientSecretEnv) { this.clientSecretEnv = clientSecretEnv; }
        public String getScopes() { return scopes; }
        public void setScopes(String scopes) { this.scopes = scopes; }
        public String getCacheKey() { return cacheKey; }
        public void setCacheKey(String cacheKey) { this.cacheKey = cacheKey; }
        public String getLoginBody() { return loginBody; }
        public void setLoginBody(String loginBody) { this.loginBody = loginBody; }
        public String getUsernameField() { return usernameField; }
        public void setUsernameField(String usernameField) { this.usernameField = usernameField; }
        public String getUsernameEnv() { return usernameEnv; }
        public void setUsernameEnv(String usernameEnv) { this.usernameEnv = usernameEnv; }
        public String getPasswordField() { return passwordField; }
        public void setPasswordField(String passwordField) { this.passwordField = passwordField; }
        public String getPasswordEnv() { return passwordEnv; }
        public void setPasswordEnv(String passwordEnv) { this.passwordEnv = passwordEnv; }
        public String getTokenPath() { return tokenPath; }
        public void setTokenPath(String tokenPath) { this.tokenPath = tokenPath; }
        public String getScheme() { return scheme; }
        public void setScheme(String scheme) { this.scheme = scheme; }
        public Long getTtlSeconds() { return ttlSeconds; }
        public void setTtlSeconds(Long ttlSeconds) { this.ttlSeconds = ttlSeconds; }
        @Override
        public String getRouteId() { return routeId; }
        @Override
        public void setRouteId(String routeId) { this.routeId = routeId; }
    }

    static final class Token {
        final String value;
        final long validUntilMillis;

        Token(String value, long validUntilMillis) {
            this.value = value;
            this.validUntilMillis = validUntilMillis;
        }
    }

    /** 토큰 발급 실패 (메시지에 비밀 없음). */
    static final class AuthUnavailableException extends RuntimeException {
        AuthUnavailableException(String message) {
            super(message, null, false, false);
        }
    }

    private final EnvLookup envLookup;
    private final WebClient webClient;
    private final ObjectMapper mapper = new ObjectMapper();
    private final Set<String> warnedMissing = ConcurrentHashMap.newKeySet();
    private final ConcurrentHashMap<String, Token> tokens = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Mono<Token>> inflight = new ConcurrentHashMap<>();
    private final AtomicInteger tokenRequests = new AtomicInteger();
    private final AtomicInteger loginRequests = new AtomicInteger();

    public KineticSystemAuthGatewayFilterFactory(EnvLookup envLookup) {
        this(envLookup, WebClient.builder());
    }

    public KineticSystemAuthGatewayFilterFactory(EnvLookup envLookup, WebClient.Builder webClientBuilder) {
        super(Config.class);
        this.envLookup = envLookup;
        this.webClient = webClientBuilder.build();
    }

    @Override
    public List<String> shortcutFieldOrder() {
        return Arrays.asList("header", "env");
    }

    /** 관찰·테스트용: 토큰 엔드포인트 호출 수. */
    public int tokenRequestCount() {
        return tokenRequests.get();
    }

    /** 관찰·테스트용: login_token 로그인 호출 수. */
    public int loginRequestCount() {
        return loginRequests.get();
    }

    /** 테스트용: 캐시된 토큰의 유효 기한(밀리초, 만료 60초 전) — 없으면 null. */
    Long tokenValidUntil(String routeId) {
        for (java.util.Map.Entry<String, Token> e : tokens.entrySet()) {
            if (e.getKey().startsWith("login|" + routeId + "|")) {
                return e.getValue().validUntilMillis;
            }
        }
        return null;
    }

    /** 테스트용: 캐시 비우기. */
    public void clearTokenCache() {
        tokens.clear();
    }

    @Override
    public GatewayFilter apply(Config config) {
        final String kind = config.getKind() == null ? "" : config.getKind();
        switch (kind) {
            case "oauth2_client_credentials":
                return oauth2(config);
            case "login_token":
                return loginToken(config);
            case "basic":
                return basic(config);
            case "api_key":
                if (notEmpty(config.getQueryParam())) {
                    return queryParam(config);
                }
                return header(config, false);
            case "bearer":
                return header(config, true);
            default:
                return header(config, false);
        }
    }

    private String envValue(String env, String what) {
        if (!notEmpty(env)) {
            return null;
        }
        String value = envLookup.get(env);
        if (value == null || value.isEmpty()) {
            if (warnedMissing.add(env)) {
                log.warn("kinetic: env {} for system auth ({}) is not set — forwarding without it", env, what);
            }
            return null;
        }
        return value;
    }

    private GatewayFilter header(Config config, boolean bearer) {
        final String header = config.getHeader();
        final String env = config.getEnv();
        return (exchange, chain) -> {
            if (!notEmpty(header)) {
                return chain.filter(exchange);
            }
            String value = envValue(env, "header " + header);
            if (value == null) {
                return chain.filter(exchange);
            }
            final String v = bearer && !value.regionMatches(true, 0, "Bearer ", 0, 7) ? "Bearer " + value : value;
            ServerHttpRequest req = exchange.getRequest().mutate().headers(h -> h.set(header, v)).build();
            return chain.filter(exchange.mutate().request(req).build());
        };
    }

    private GatewayFilter queryParam(Config config) {
        final String param = config.getQueryParam();
        final String env = config.getEnv();
        return (exchange, chain) -> {
            String value = envValue(env, "query param " + param);
            if (value == null) {
                return chain.filter(exchange);
            }
            URI uri = UriComponentsBuilder.fromUri(exchange.getRequest().getURI())
                    .replaceQueryParam(param, UriUtils.encodeQueryParam(value, StandardCharsets.UTF_8))
                    .build(true).toUri();
            ServerHttpRequest req = exchange.getRequest().mutate().uri(uri).build();
            return chain.filter(exchange.mutate().request(req).build());
        };
    }

    private GatewayFilter basic(Config config) {
        final String env = notEmpty(config.getBasicEnv()) ? config.getBasicEnv() : config.getEnv();
        return (exchange, chain) -> {
            String value = envValue(env, "basic");
            if (value == null) {
                return chain.filter(exchange);
            }
            final String v = "Basic " + Base64.getEncoder().encodeToString(value.getBytes(StandardCharsets.UTF_8));
            ServerHttpRequest req = exchange.getRequest().mutate()
                    .headers(h -> h.set(HttpHeaders.AUTHORIZATION, v)).build();
            return chain.filter(exchange.mutate().request(req).build());
        };
    }

    private GatewayFilter oauth2(Config config) {
        final String key = (config.getCacheKey() == null ? "" : config.getCacheKey()) + "|" + config.getTokenUrl()
                + "|" + config.getClientId() + "|" + (config.getScopes() == null ? "" : config.getScopes());
        return (exchange, chain) -> token(key, config)
                .flatMap(token -> {
                    ServerHttpRequest req = exchange.getRequest().mutate()
                            .headers(h -> h.set(HttpHeaders.AUTHORIZATION, "Bearer " + token)).build();
                    return chain.filter(exchange.mutate().request(req).build());
                })
                .onErrorResume(AuthUnavailableException.class, e -> KineticErrors.write(exchange.getResponse(),
                        HttpStatus.SERVICE_UNAVAILABLE, "auth_unavailable", e.getMessage()));
    }

    Mono<String> token(String key, Config config) {
        Token cached = tokens.get(key);
        if (cached != null && cached.validUntilMillis > System.currentTimeMillis()) {
            return Mono.just(cached.value);
        }
        return inflight.computeIfAbsent(key, k -> fetch(config)
                        .doOnNext(t -> tokens.put(k, t))
                        .doFinally(s -> inflight.remove(k))
                        .cache())
                .map(t -> t.value);
    }

    private Mono<Token> fetch(Config config) {
        return Mono.defer(() -> {
            String tokenUrl = config.getTokenUrl();
            if (!notEmpty(tokenUrl) || !notEmpty(config.getClientId())) {
                return Mono.error(new AuthUnavailableException("oauth2 token_url/client_id not configured"));
            }
            String secret = notEmpty(config.getClientSecretEnv()) ? envLookup.get(config.getClientSecretEnv()) : null;
            if (secret == null || secret.isEmpty()) {
                log.warn("kinetic: oauth2 client secret env {} is not set (token_url {})",
                        config.getClientSecretEnv(), tokenUrl);
                return Mono.error(new AuthUnavailableException(
                        "oauth2 client secret env " + config.getClientSecretEnv() + " is not set"));
            }
            MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
            form.add("grant_type", "client_credentials");
            form.add("client_id", config.getClientId());
            form.add("client_secret", secret);
            if (notEmpty(config.getScopes())) {
                form.add("scope", config.getScopes());
            }
            tokenRequests.incrementAndGet();
            return webClient.post().uri(tokenUrl)
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(BodyInserters.fromFormData(form))
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofSeconds(10))
                    .map(this::parseToken)
                    .onErrorMap(e -> !(e instanceof AuthUnavailableException), e -> {
                        String why = e instanceof WebClientResponseException
                                ? "HTTP " + ((WebClientResponseException) e).getRawStatusCode()
                                : e.getClass().getSimpleName();
                        log.warn("kinetic: oauth2 token request to {} failed ({})", tokenUrl, why);
                        return new AuthUnavailableException("token endpoint failed: " + why);
                    });
        });
    }

    private Token parseToken(String body) {
        try {
            JsonNode n = mapper.readTree(body);
            JsonNode at = n == null ? null : n.get("access_token");
            if (at == null || !at.isTextual() || at.asText().isEmpty()) {
                throw new AuthUnavailableException("token endpoint response has no access_token");
            }
            long expiresIn = n.hasNonNull("expires_in") && n.get("expires_in").canConvertToLong()
                    ? n.get("expires_in").asLong() : DEFAULT_EXPIRES_IN_SECONDS;
            long ttl = Math.max(0, expiresIn - REFRESH_SKEW_SECONDS);
            return new Token(at.asText(), System.currentTimeMillis() + ttl * 1000);
        } catch (AuthUnavailableException e) {
            throw e;
        } catch (Exception e) {
            throw new AuthUnavailableException("token endpoint response is not JSON");
        }
    }

    // ---------------------------------------------------------------- login_token (계약 §9.1)

    private GatewayFilter loginToken(Config config) {
        if (config.getRouteId() != null && getPublisher() != null) {
            // 401 재시도 때 본문을 다시 보내려면 본문 캐시가 필요하다 (내장 Retry 와 같은 방식)
            getPublisher().publishEvent(new EnableBodyCachingEvent(this, config.getRouteId()));
        }
        final String key = "login|" + (config.getCacheKey() == null ? "" : config.getCacheKey()) + "|"
                + config.getTokenUrl() + "|" + config.getUsernameEnv() + "|"
                + (config.getLoginBody() == null ? "" : config.getLoginBody());
        final String header = notEmpty(config.getHeader()) ? config.getHeader() : HttpHeaders.AUTHORIZATION;
        return (exchange, chain) -> login(key, config)
                .flatMap(first -> chain.filter(withHeader(exchange, header, headerValue(config, first)))
                        .then(Mono.defer(() -> {
                            Integer status = exchange.getResponse().getRawStatusCode();
                            if (status == null || status != HttpStatus.UNAUTHORIZED.value()) {
                                return Mono.empty();
                            }
                            Token cached = tokens.get(key);
                            if (cached != null && cached.value.equals(first)) {
                                tokens.remove(key, cached);
                            }
                            log.info("kinetic: downstream 401 on route {} — logging in again and retrying once",
                                    config.getCacheKey());
                            resetForRetry(exchange);
                            return login(key, config).flatMap(second ->
                                    chain.filter(withHeader(exchange, header, headerValue(config, second))));
                        })))
                .onErrorResume(AuthUnavailableException.class, e -> KineticErrors.write(exchange.getResponse(),
                        HttpStatus.SERVICE_UNAVAILABLE, "auth_unavailable", e.getMessage()));
    }

    private static ServerWebExchange withHeader(ServerWebExchange exchange, String header, String value) {
        ServerHttpRequest req = exchange.getRequest().mutate().headers(h -> h.set(header, value)).build();
        return exchange.mutate().request(req).build();
    }

    private static String headerValue(Config config, String token) {
        String scheme = config.getScheme() == null ? "Bearer" : config.getScheme();
        return scheme.isEmpty() || RAW_SCHEME.equals(scheme) ? token : scheme + " " + token;
    }

    /** 내장 Retry 의 reset 과 같다 — 앞 응답 연결을 버리고 "이미 라우팅됨" 표시·응답 헤더를 지운다. */
    private static void resetForRetry(ServerWebExchange exchange) {
        Connection conn = exchange.getAttribute(ServerWebExchangeUtils.CLIENT_RESPONSE_CONN_ATTR);
        if (conn != null) {
            conn.dispose();
            exchange.getAttributes().remove(ServerWebExchangeUtils.CLIENT_RESPONSE_CONN_ATTR);
        }
        exchange.getAttributes().remove(RetryGatewayFilterFactory.RETRY_ITERATION_KEY);
        ServerWebExchangeUtils.reset(exchange);
    }

    Mono<String> login(String key, Config config) {
        Token cached = tokens.get(key);
        if (cached != null && cached.validUntilMillis > System.currentTimeMillis()) {
            return Mono.just(cached.value);
        }
        return inflight.computeIfAbsent(key, k -> fetchLogin(config)
                        .doOnNext(t -> tokens.put(k, t))
                        .doFinally(s -> inflight.remove(k))
                        .cache())
                .map(t -> t.value);
    }

    private Mono<Token> fetchLogin(Config config) {
        return Mono.defer(() -> {
            String tokenUrl = config.getTokenUrl();
            if (!notEmpty(tokenUrl)) {
                return Mono.error(new AuthUnavailableException("login token_url not configured"));
            }
            List<String> missing = new java.util.ArrayList<>();
            String user = notEmpty(config.getUsernameEnv()) ? envLookup.get(config.getUsernameEnv()) : null;
            String password = notEmpty(config.getPasswordEnv()) ? envLookup.get(config.getPasswordEnv()) : null;
            if (user == null || user.isEmpty()) {
                missing.add(String.valueOf(config.getUsernameEnv()));
            }
            if (password == null || password.isEmpty()) {
                missing.add(String.valueOf(config.getPasswordEnv()));
            }
            if (!missing.isEmpty()) {
                log.warn("kinetic: login env {} not set (token_url {})", missing, tokenUrl);
                return Mono.error(new AuthUnavailableException("login env not set: " + String.join(", ", missing)));
            }
            ObjectNode body;
            try {
                JsonNode parsed = notEmpty(config.getLoginBody()) ? mapper.readTree(config.getLoginBody()) : null;
                body = parsed != null && parsed.isObject() ? (ObjectNode) parsed : mapper.createObjectNode();
            } catch (Exception e) {
                return Mono.error(new AuthUnavailableException("login_body is not a JSON object"));
            }
            body.put(notEmpty(config.getUsernameField()) ? config.getUsernameField() : "loginId", user);
            body.put(notEmpty(config.getPasswordField()) ? config.getPasswordField() : "password", password);
            final String json;
            try {
                json = mapper.writeValueAsString(body);
            } catch (Exception e) {
                return Mono.error(new AuthUnavailableException("login body serialization failed"));
            }
            loginRequests.incrementAndGet();
            return webClient.post().uri(tokenUrl)
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .bodyValue(json)
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofSeconds(10))
                    .map(resp -> parseLogin(resp, config))
                    .onErrorMap(e -> !(e instanceof AuthUnavailableException), e -> {
                        String why = e instanceof WebClientResponseException
                                ? "HTTP " + ((WebClientResponseException) e).getRawStatusCode()
                                : e.getClass().getSimpleName();
                        log.warn("kinetic: login to {} failed ({})", tokenUrl, why);
                        return new AuthUnavailableException("login failed: " + why);
                    });
        });
    }

    private Token parseLogin(String body, Config config) {
        JsonNode n;
        try {
            n = mapper.readTree(body);
        } catch (Exception e) {
            throw new AuthUnavailableException("login response is not JSON");
        }
        String path = notEmpty(config.getTokenPath()) ? config.getTokenPath() : "token";
        for (String part : path.split("\\.")) {
            if (n == null) {
                break;
            }
            n = n.isArray() && part.matches("\\d+") ? n.get(Integer.parseInt(part)) : n.get(part);
        }
        if (n == null || !n.isTextual() || n.asText().isEmpty()) {
            log.warn("kinetic: login response from {} has no token at '{}'", config.getTokenUrl(), path);
            throw new AuthUnavailableException("login response has no token at '" + path + "'");
        }
        String token = n.asText();
        long now = System.currentTimeMillis();
        Long exp = jwtExp(token);
        long ttl = config.getTtlSeconds() != null && config.getTtlSeconds() > 0
                ? config.getTtlSeconds() : DEFAULT_LOGIN_TTL_SECONDS;
        long expiresAt = exp != null ? exp * 1000 : now + ttl * 1000;
        return new Token(token, Math.max(now, expiresAt - REFRESH_SKEW_SECONDS * 1000));
    }

    /** JWT 페이로드의 exp(초) — 서명은 검증하지 않는다(만료 시각만 본다). JWT 가 아니면 null. */
    Long jwtExp(String token) {
        String[] parts = token.split("\\.");
        if (parts.length != 3) {
            return null;
        }
        try {
            JsonNode p = mapper.readTree(Base64.getUrlDecoder().decode(parts[1]));
            JsonNode exp = p == null ? null : p.get("exp");
            return exp != null && exp.isNumber() ? exp.asLong() : null;
        } catch (Exception e) {
            return null;
        }
    }

    static boolean notEmpty(String s) {
        return s != null && !s.isEmpty();
    }
}
