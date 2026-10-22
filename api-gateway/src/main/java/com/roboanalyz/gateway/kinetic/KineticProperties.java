package com.roboanalyz.gateway.kinetic;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

/**
 * 키네틱 액션 레이어 설정 (spec 014, contracts/kinetic-api.md §2, §5, §6).
 * application.yml 의 {@code kinetic.*} 가 KINETIC_* 환경 변수에서 값을 받는다.
 */
@ConfigurationProperties(prefix = "kinetic")
public class KineticProperties {

    /** KINETIC_ENABLED — false 면 북향 라우트·JWT 체인·동적 라우트 갱신을 끈다. */
    private boolean enabled = true;
    /** KINETIC_URL — kinetic-action 서비스 주소. */
    private String url = "http://localhost:8030";
    /** KINETIC_JWKS_URL */
    private String jwksUrl = "http://localhost:8032/.well-known/jwks.json";
    /** KINETIC_ISSUER */
    private String issuer = "http://localhost:8032";
    /** KINETIC_AUDIENCE */
    private String audience = "kinetic-action";
    /** KINETIC_PUBLIC_BASE — 외부에서 본 게이트웨이 주소 (WWW-Authenticate resource_metadata 에 쓴다). */
    private String publicBase = "http://localhost:9000";
    /** KINETIC_INTERNAL_SECRET — /svc/** 및 routes 조회에 쓰는 내부 헤더 값. 비어 있으면 /svc/** 는 전부 403. */
    private String internalSecret = "";
    /** KINETIC_ROUTE_REFRESH */
    private Duration routeRefresh = Duration.ofSeconds(15);
    /** KINETIC_RATE_PER_SEC — 주체(sub)별 초당 토큰 보충량. */
    private double ratePerSec = 10;
    /** KINETIC_RATE_BURST — 주체별 버킷 용량. */
    private long rateBurst = 20;
    /** Route.timeout_ms 가 비었을 때 남향 응답 타임아웃(ms). */
    private long svcDefaultTimeoutMs = 30000;
    /** 남향 Retry 재시도 횟수. */
    private int svcRetries = 2;
    /** /api/kinetic/** 응답 타임아웃(ms). -1 = 없음. */
    private long apiResponseTimeoutMs = 600000;

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public String getUrl() { return url; }
    public void setUrl(String url) { this.url = url; }
    public String getJwksUrl() { return jwksUrl; }
    public void setJwksUrl(String jwksUrl) { this.jwksUrl = jwksUrl; }
    public String getIssuer() { return issuer; }
    public void setIssuer(String issuer) { this.issuer = issuer; }
    public String getAudience() { return audience; }
    public void setAudience(String audience) { this.audience = audience; }
    public String getPublicBase() { return publicBase; }
    public void setPublicBase(String publicBase) { this.publicBase = publicBase; }
    public String getInternalSecret() { return internalSecret; }
    public void setInternalSecret(String internalSecret) { this.internalSecret = internalSecret; }
    public Duration getRouteRefresh() { return routeRefresh; }
    public void setRouteRefresh(Duration routeRefresh) { this.routeRefresh = routeRefresh; }
    public double getRatePerSec() { return ratePerSec; }
    public void setRatePerSec(double ratePerSec) { this.ratePerSec = ratePerSec; }
    public long getRateBurst() { return rateBurst; }
    public void setRateBurst(long rateBurst) { this.rateBurst = rateBurst; }
    public long getSvcDefaultTimeoutMs() { return svcDefaultTimeoutMs; }
    public void setSvcDefaultTimeoutMs(long svcDefaultTimeoutMs) { this.svcDefaultTimeoutMs = svcDefaultTimeoutMs; }
    public int getSvcRetries() { return svcRetries; }
    public void setSvcRetries(int svcRetries) { this.svcRetries = svcRetries; }
    public long getApiResponseTimeoutMs() { return apiResponseTimeoutMs; }
    public void setApiResponseTimeoutMs(long apiResponseTimeoutMs) { this.apiResponseTimeoutMs = apiResponseTimeoutMs; }

    /** RFC 9728 보호 자원 메타데이터 URL (401 의 WWW-Authenticate 에 싣는다). */
    public String resourceMetadataUrl() {
        String base = publicBase == null ? "" : publicBase.replaceAll("/+$", "");
        return base + "/.well-known/oauth-protected-resource/mcp/kinetic";
    }

    public String baseUrl() {
        return url == null ? "" : url.replaceAll("/+$", "");
    }
}
