package com.roboanalyz.gateway.kinetic;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.cloud.gateway.filter.FilterDefinition;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionLocator;
import org.springframework.cloud.gateway.support.NameUtils;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;

import static org.springframework.cloud.gateway.support.RouteMetadataUtils.CONNECT_TIMEOUT_ATTR;
import static org.springframework.cloud.gateway.support.RouteMetadataUtils.RESPONSE_TIMEOUT_ATTR;

/**
 * 남향 동적 라우트 (계약 §5). {@code KINETIC_ROUTE_REFRESH} 마다
 * {@code GET {KINETIC_URL}/api/kinetic/systems/routes} (헤더 X-Kinetic-Internal) 를 읽어
 * 시스템마다 {@code /svc/<system>/**} 라우트를 만든다.
 *
 * <p>라우트 필터 순서: RemoveRequestHeader(X-Kinetic-Internal) → RewritePath → KineticSystemAuth →
 * CircuitBreaker(svc-&lt;system&gt;, 503 fallback) → KineticRetry(2). CircuitBreaker 가 바깥이라 재시도가 다 끝난
 * 결과만 회로 상태에 반영된다.
 *
 * <p>kinetic-action 이 죽었거나 응답이 이상하면 마지막으로 알던 라우트를 유지하고 경고만 남긴다.
 */
public class KineticRouteDefinitionLocator implements RouteDefinitionLocator,
        ApplicationListener<ApplicationReadyEvent>, DisposableBean {

    private static final Logger log = LoggerFactory.getLogger(KineticRouteDefinitionLocator.class);

    static final int SVC_ROUTE_ORDER = -10;
    static final Pattern SYSTEM_NAME = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9_.-]*$");
    static final Pattern HEADER_NAME = Pattern.compile("^[!#$%&'*+.^_`|~0-9A-Za-z-]+$");

    private final KineticProperties props;
    private final WebClient webClient;
    private final ApplicationEventPublisher publisher;
    private final ObjectMapper mapper = new ObjectMapper();

    private volatile List<SvcRoute> current = Collections.emptyList();
    private volatile List<RouteDefinition> definitions = Collections.emptyList();
    private volatile boolean lastFetchFailed;
    private volatile Disposable poller;

    public KineticRouteDefinitionLocator(KineticProperties props, WebClient.Builder webClientBuilder,
                                         ApplicationEventPublisher publisher) {
        this.props = props;
        this.webClient = webClientBuilder.build();
        this.publisher = publisher;
    }

    @Override
    public Flux<RouteDefinition> getRouteDefinitions() {
        return Flux.fromIterable(definitions);
    }

    public List<SvcRoute> currentRoutes() {
        return current;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        start();
    }

    public synchronized void start() {
        if (poller != null || !props.isEnabled()) {
            return;
        }
        if (props.getInternalSecret() == null || props.getInternalSecret().isEmpty()) {
            log.warn("kinetic: KINETIC_INTERNAL_SECRET is empty — every /svc/** request will be rejected with 403");
        }
        Duration every = props.getRouteRefresh() == null || props.getRouteRefresh().isZero()
                ? Duration.ofSeconds(15) : props.getRouteRefresh();
        log.info("kinetic: polling {} every {}", routesUrl(), every);
        poller = Flux.interval(Duration.ZERO, every, Schedulers.boundedElastic())
                .onBackpressureDrop()
                .concatMap(i -> refresh().onErrorResume(e -> Mono.just(false)), 1)
                .subscribe();
    }

    @Override
    public void destroy() {
        Disposable p = poller;
        if (p != null) {
            p.dispose();
        }
    }

    String routesUrl() {
        return props.baseUrl() + "/api/kinetic/systems/routes";
    }

    /**
     * 한 번 읽어 반영한다. 바뀌었으면 RefreshRoutesEvent 를 발행하고 true. 실패 시 기존 라우트 유지, false.
     */
    public Mono<Boolean> refresh() {
        WebClient.RequestHeadersSpec<?> req = webClient.get().uri(routesUrl()).accept(MediaType.APPLICATION_JSON);
        String secret = props.getInternalSecret();
        if (secret != null && !secret.isEmpty()) {
            req = req.header(SvcInternalGuardFilter.HEADER, secret);
        }
        return req.retrieve()
                .bodyToMono(String.class)
                .timeout(Duration.ofSeconds(10))
                .map(this::parse)
                .map(this::apply)
                .doOnSuccess(x -> {
                    if (lastFetchFailed) {
                        log.info("kinetic: route source {} reachable again", routesUrl());
                    }
                    lastFetchFailed = false;
                })
                .onErrorResume(e -> {
                    if (!lastFetchFailed) {
                        log.warn("kinetic: cannot load routes from {} ({}) — keeping {} last known route(s)",
                                routesUrl(), e.toString(), current.size());
                    } else {
                        log.debug("kinetic: route source still unavailable: {}", e.toString());
                    }
                    lastFetchFailed = true;
                    return Mono.just(false);
                });
    }

    List<SvcRoute> parse(String body) {
        try {
            JsonNode root = mapper.readTree(body == null ? "[]" : body);
            if (root != null && root.isObject() && root.has("routes")) {
                root = root.get("routes");
            }
            if (root == null || !root.isArray()) {
                throw new IllegalArgumentException("routes response is not a JSON array");
            }
            Map<String, SvcRoute> bySystem = new LinkedHashMap<>();
            for (JsonNode n : root) {
                SvcRoute r = SvcRoute.from(n);
                String problem = r.validate();
                if (problem != null) {
                    log.warn("kinetic: skipping route {}: {}", n, problem);
                    continue;
                }
                bySystem.put(r.system, r);
            }
            return new ArrayList<>(bySystem.values());
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException("invalid routes JSON: " + e.getMessage(), e);
        }
    }

    private synchronized boolean apply(List<SvcRoute> routes) {
        if (routes.equals(current)) {
            return false;
        }
        List<RouteDefinition> defs = new ArrayList<>(routes.size());
        for (SvcRoute r : routes) {
            defs.add(toDefinition(r));
        }
        this.current = Collections.unmodifiableList(routes);
        this.definitions = Collections.unmodifiableList(defs);
        log.info("kinetic: southbound routes updated: {}", systems(routes));
        publisher.publishEvent(new RefreshRoutesEvent(this));
        return true;
    }

    private static List<String> systems(List<SvcRoute> routes) {
        List<String> names = new ArrayList<>();
        for (SvcRoute r : routes) {
            names.add(r.system + "->" + r.uri);
        }
        return names;
    }

    RouteDefinition toDefinition(SvcRoute r) {
        RouteDefinition def = new RouteDefinition();
        def.setId(r.routeId());
        def.setUri(URI.create(r.uri));
        def.setOrder(SVC_ROUTE_ORDER);

        PredicateDefinition path = new PredicateDefinition();
        path.setName("Path");
        path.addArg(NameUtils.generateName(0), "/svc/" + r.system);
        path.addArg(NameUtils.generateName(1), "/svc/" + r.system + "/**");
        PredicateDefinition internal = new PredicateDefinition();
        internal.setName("KineticInternal");
        def.getPredicates().add(path);
        def.getPredicates().add(internal);

        List<FilterDefinition> filters = def.getFilters();
        FilterDefinition removeSecret = new FilterDefinition();
        removeSecret.setName("RemoveRequestHeader");
        removeSecret.addArg("name", SvcInternalGuardFilter.HEADER);
        filters.add(removeSecret);

        FilterDefinition rewrite = new FilterDefinition();
        rewrite.setName("RewritePath");
        rewrite.addArg("regexp", "/svc/" + Pattern.quote(r.system) + "/?(?<s>.*)");
        rewrite.addArg("replacement", "/${s}");
        filters.add(rewrite);

        FilterDefinition auth = authFilter(r);
        if (auth != null) {
            filters.add(auth);
        }

        FilterDefinition cb = new FilterDefinition();
        cb.setName("CircuitBreaker");
        cb.addArg("name", r.routeId());
        cb.addArg("fallbackUri", "forward:" + KineticSvcFallbackController.PATH);
        filters.add(cb);

        int retries = r.retries != null ? r.retries : props.getSvcRetries();
        if (retries > 0) { // Retry 필터는 0 을 받지 않는다 — 0 이면 필터를 빼서 재시도 없음
            FilterDefinition retry = new FilterDefinition();
            retry.setName("KineticRetry");
            retry.addArg("retries", Integer.toString(retries));
            filters.add(retry);
        }

        Map<String, Object> md = new LinkedHashMap<>();
        long timeout = r.timeoutMs != null && r.timeoutMs > 0 ? r.timeoutMs : props.getSvcDefaultTimeoutMs();
        md.put(RESPONSE_TIMEOUT_ATTR, timeout);
        md.put(CONNECT_TIMEOUT_ATTR, (int) Math.min(timeout, 5000L));
        md.put("kinetic-system", r.system);
        def.setMetadata(md);
        return def;
    }

    static boolean notEmpty(String s) {
        return s != null && !s.isEmpty();
    }

    /** 계약 §8 Route 의 인증 설정 → KineticSystemAuth 필터 (없으면 null). 인자에는 env <b>이름</b>만 들어간다. */
    static FilterDefinition authFilter(SvcRoute r) {
        String kind = r.authKind == null ? "" : r.authKind;
        FilterDefinition auth = new FilterDefinition();
        auth.setName("KineticSystemAuth");
        switch (kind) {
            case "oauth2_client_credentials":
                if (r.oauth2 == null) {
                    return null;
                }
                auth.addArg("kind", kind);
                auth.addArg("tokenUrl", r.oauth2.tokenUrl);
                auth.addArg("clientId", r.oauth2.clientId);
                auth.addArg("clientSecretEnv", r.oauth2.clientSecretEnv == null ? "" : r.oauth2.clientSecretEnv);
                auth.addArg("scopes", String.join(" ", r.oauth2.scopes));
                auth.addArg("cacheKey", r.routeId());
                return auth;
            case "login_token":
                if (r.login == null) {
                    return null;
                }
                auth.addArg("kind", kind);
                auth.addArg("tokenUrl", r.login.tokenUrl);
                auth.addArg("loginBody", r.login.loginBody);
                auth.addArg("usernameField", r.login.usernameField);
                auth.addArg("usernameEnv", r.login.usernameEnv == null ? "" : r.login.usernameEnv);
                auth.addArg("passwordField", r.login.passwordField);
                auth.addArg("passwordEnv", r.login.passwordEnv == null ? "" : r.login.passwordEnv);
                auth.addArg("tokenPath", r.login.tokenPath);
                auth.addArg("header", r.login.header);
                auth.addArg("scheme", r.login.scheme.isEmpty()
                        ? KineticSystemAuthGatewayFilterFactory.RAW_SCHEME : r.login.scheme);
                auth.addArg("ttlSeconds", Long.toString(r.login.ttlSeconds));
                auth.addArg("cacheKey", r.routeId());
                return auth;
            case "basic":
                if (!notEmpty(r.basicEnv)) {
                    return null;
                }
                auth.addArg("kind", kind);
                auth.addArg("basicEnv", r.basicEnv);
                return auth;
            case "api_key":
                if (notEmpty(r.authQueryParam) && notEmpty(r.authValueEnv)) {
                    auth.addArg("kind", kind);
                    auth.addArg("queryParam", r.authQueryParam);
                    auth.addArg("env", r.authValueEnv);
                    return auth;
                }
                break;
            default:
                break;
        }
        if (notEmpty(r.authHeader) && notEmpty(r.authValueEnv)) {
            if (!kind.isEmpty()) {
                auth.addArg("kind", kind);
            }
            auth.addArg("header", r.authHeader);
            auth.addArg("env", r.authValueEnv);
            return auth;
        }
        return null;
    }

    /** 계약 §8 Route.oauth2. */
    public static final class OAuth2 {
        final String tokenUrl;
        final String clientId;
        final String clientSecretEnv;
        final List<String> scopes;

        OAuth2(String tokenUrl, String clientId, String clientSecretEnv, List<String> scopes) {
            this.tokenUrl = tokenUrl;
            this.clientId = clientId;
            this.clientSecretEnv = clientSecretEnv;
            this.scopes = scopes;
        }

        static OAuth2 from(JsonNode n) {
            if (n == null || !n.isObject()) {
                return null;
            }
            List<String> scopes = new ArrayList<>();
            JsonNode s = n.get("scopes");
            if (s != null && s.isArray()) {
                for (JsonNode x : s) {
                    scopes.add(x.asText());
                }
            } else if (s != null && s.isTextual() && !s.asText().trim().isEmpty()) {
                scopes.addAll(Arrays.asList(s.asText().trim().split("\\s+")));
            }
            return new OAuth2(SvcRoute.text(n, "token_url"), SvcRoute.text(n, "client_id"),
                    SvcRoute.text(n, "client_secret_env"), scopes);
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (!(o instanceof OAuth2)) return false;
            OAuth2 x = (OAuth2) o;
            return Objects.equals(tokenUrl, x.tokenUrl) && Objects.equals(clientId, x.clientId)
                    && Objects.equals(clientSecretEnv, x.clientSecretEnv) && Objects.equals(scopes, x.scopes);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tokenUrl, clientId, clientSecretEnv, scopes);
        }
    }

    /** 계약 §9.1 Route.login_token — env <b>이름</b>만, 비밀 값 없음. */
    public static final class Login {
        final String tokenUrl;
        final String loginBody; // JSON 객체 문자열
        final String usernameField;
        final String usernameEnv;
        final String passwordField;
        final String passwordEnv;
        final String tokenPath;
        final String header;
        final String scheme;
        final long ttlSeconds;

        Login(String tokenUrl, String loginBody, String usernameField, String usernameEnv, String passwordField,
              String passwordEnv, String tokenPath, String header, String scheme, long ttlSeconds) {
            this.tokenUrl = tokenUrl;
            this.loginBody = loginBody;
            this.usernameField = usernameField;
            this.usernameEnv = usernameEnv;
            this.passwordField = passwordField;
            this.passwordEnv = passwordEnv;
            this.tokenPath = tokenPath;
            this.header = header;
            this.scheme = scheme;
            this.ttlSeconds = ttlSeconds;
        }

        static Login from(JsonNode n) {
            if (n == null || !n.isObject()) {
                return null;
            }
            JsonNode body = n.get("login_body");
            String scheme = n.has("scheme") ? (n.get("scheme").isNull() ? "" : n.get("scheme").asText()) : "Bearer";
            long ttl = n.hasNonNull("ttl_seconds") && n.get("ttl_seconds").canConvertToLong()
                    ? n.get("ttl_seconds").asLong() : KineticSystemAuthGatewayFilterFactory.DEFAULT_LOGIN_TTL_SECONDS;
            return new Login(SvcRoute.text(n, "token_url"),
                    body != null && body.isObject() ? body.toString() : "{}",
                    or(SvcRoute.text(n, "username_field"), "loginId"), SvcRoute.text(n, "username_env"),
                    or(SvcRoute.text(n, "password_field"), "password"), SvcRoute.text(n, "password_env"),
                    or(SvcRoute.text(n, "token_path"), "token"), or(SvcRoute.text(n, "header"), "Authorization"),
                    scheme, ttl);
        }

        private static String or(String v, String d) {
            return v == null || v.isEmpty() ? d : v;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (!(o instanceof Login)) return false;
            Login x = (Login) o;
            return ttlSeconds == x.ttlSeconds && Objects.equals(tokenUrl, x.tokenUrl)
                    && Objects.equals(loginBody, x.loginBody) && Objects.equals(usernameField, x.usernameField)
                    && Objects.equals(usernameEnv, x.usernameEnv) && Objects.equals(passwordField, x.passwordField)
                    && Objects.equals(passwordEnv, x.passwordEnv) && Objects.equals(tokenPath, x.tokenPath)
                    && Objects.equals(header, x.header) && Objects.equals(scheme, x.scheme);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tokenUrl, loginBody, usernameField, usernameEnv, passwordField, passwordEnv,
                    tokenPath, header, scheme, ttlSeconds);
        }
    }

    /** 계약 §3 Route. */
    public static final class SvcRoute {
        final String id;
        final String system;
        final String pathPrefix;
        final String uri;
        final String authHeader;
        final String authValueEnv;
        final Long timeoutMs;
        final String authKind;
        final String authQueryParam;
        final String basicEnv;
        final OAuth2 oauth2;
        final Integer retries;
        Login login;

        SvcRoute(String id, String system, String pathPrefix, String uri, String authHeader, String authValueEnv,
                 Long timeoutMs) {
            this(id, system, pathPrefix, uri, authHeader, authValueEnv, timeoutMs, null, null, null, null, null);
        }

        SvcRoute(String id, String system, String pathPrefix, String uri, String authHeader, String authValueEnv,
                 Long timeoutMs, String authKind, String authQueryParam, String basicEnv, OAuth2 oauth2,
                 Integer retries) {
            this.id = id;
            this.system = system;
            this.pathPrefix = pathPrefix;
            this.uri = uri;
            this.authHeader = authHeader;
            this.authValueEnv = authValueEnv;
            this.timeoutMs = timeoutMs;
            this.authKind = authKind;
            this.authQueryParam = authQueryParam;
            this.basicEnv = basicEnv;
            this.oauth2 = oauth2;
            this.retries = retries;
        }

        static SvcRoute from(JsonNode n) {
            SvcRoute r = new SvcRoute(text(n, "id"), text(n, "system"), text(n, "path_prefix"), text(n, "uri"),
                    text(n, "auth_header"), text(n, "auth_value_env"),
                    n.hasNonNull("timeout_ms") && n.get("timeout_ms").canConvertToLong()
                            ? n.get("timeout_ms").asLong() : null,
                    text(n, "auth_kind"), text(n, "auth_query_param"), text(n, "basic_env"),
                    OAuth2.from(n.get("oauth2")),
                    n.hasNonNull("retries") && n.get("retries").canConvertToInt()
                            ? Math.max(0, Math.min(5, n.get("retries").asInt())) : null);
            r.login = Login.from(n.get("login_token"));
            return r;
        }

        static String text(JsonNode n, String field) {
            JsonNode v = n.get(field);
            return v == null || v.isNull() ? null : v.asText();
        }

        /** 라우트 id 는 계약대로 svc-<system> 로 고정한다(응답의 id 는 참고만). */
        String routeId() {
            return "svc-" + system;
        }

        String validate() {
            if (system == null || !SYSTEM_NAME.matcher(system).matches()) {
                return "invalid system name";
            }
            if (pathPrefix != null && !pathPrefix.isEmpty() && !pathPrefix.equals("/svc/" + system)) {
                return "path_prefix must be /svc/" + system;
            }
            if (uri == null) {
                return "missing uri";
            }
            try {
                URI u = URI.create(uri);
                String scheme = u.getScheme();
                if (scheme == null || !(scheme.equalsIgnoreCase("http") || scheme.equalsIgnoreCase("https"))
                        || u.getHost() == null) {
                    return "uri must be absolute http(s)";
                }
            } catch (IllegalArgumentException e) {
                return "invalid uri";
            }
            if (notEmpty(authHeader) && !HEADER_NAME.matcher(authHeader).matches()) {
                return "invalid auth_header";
            }
            if (notEmpty(authQueryParam) && !HEADER_NAME.matcher(authQueryParam).matches()) {
                return "invalid auth_query_param";
            }
            if ("login_token".equals(authKind)) {
                if (login == null || login.tokenUrl == null) {
                    return "login_token requires token_url";
                }
                try {
                    URI t = URI.create(login.tokenUrl);
                    if (t.getScheme() == null || !(t.getScheme().equalsIgnoreCase("http")
                            || t.getScheme().equalsIgnoreCase("https")) || t.getHost() == null) {
                        return "login_token.token_url must be absolute http(s)";
                    }
                } catch (IllegalArgumentException e) {
                    return "invalid login_token.token_url";
                }
                if (!HEADER_NAME.matcher(login.header).matches()) {
                    return "invalid login_token.header";
                }
            }
            if ("oauth2_client_credentials".equals(authKind)) {
                if (oauth2 == null || oauth2.tokenUrl == null || oauth2.clientId == null) {
                    return "oauth2 requires token_url and client_id";
                }
                try {
                    URI t = URI.create(oauth2.tokenUrl);
                    if (t.getScheme() == null || !(t.getScheme().equalsIgnoreCase("http")
                            || t.getScheme().equalsIgnoreCase("https")) || t.getHost() == null) {
                        return "oauth2.token_url must be absolute http(s)";
                    }
                } catch (IllegalArgumentException e) {
                    return "invalid oauth2.token_url";
                }
            }
            return null;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (!(o instanceof SvcRoute)) return false;
            SvcRoute r = (SvcRoute) o;
            return Objects.equals(id, r.id) && Objects.equals(system, r.system)
                    && Objects.equals(pathPrefix, r.pathPrefix) && Objects.equals(uri, r.uri)
                    && Objects.equals(authHeader, r.authHeader) && Objects.equals(authValueEnv, r.authValueEnv)
                    && Objects.equals(timeoutMs, r.timeoutMs) && Objects.equals(authKind, r.authKind)
                    && Objects.equals(authQueryParam, r.authQueryParam) && Objects.equals(basicEnv, r.basicEnv)
                    && Objects.equals(oauth2, r.oauth2) && Objects.equals(retries, r.retries)
                    && Objects.equals(login, r.login);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, system, pathPrefix, uri, authHeader, authValueEnv, timeoutMs, authKind,
                    authQueryParam, basicEnv, oauth2, retries, login);
        }

        @Override
        public String toString() {
            return "SvcRoute{" + system + " -> " + uri + "}";
        }
    }
}
