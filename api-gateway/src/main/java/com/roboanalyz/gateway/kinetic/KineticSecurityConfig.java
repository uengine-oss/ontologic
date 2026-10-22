package com.roboanalyz.gateway.kinetic;

import com.roboanalyz.gateway.config.CorsConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

/**
 * 북향 JWT 검증 (계약 §2, §6).
 *
 * <p>SecurityWebFilterChain 은 {@code /mcp/kinetic}, {@code /mcp/kinetic/**}, {@code /api/kinetic/**} 에만
 * 매칭된다(securityMatcher). 그 밖의 요청은 체인을 아예 거치지 않으므로 기존 라우트의 동작·헤더·CORS 는 그대로다.
 *
 * <p>JWKS 는 첫 검증 때 가져온다(NimbusReactiveJwtDecoder.withJwkSetUri 는 지연 조회) — 기동 시 JWKS 가 죽어 있어도 앱은 뜬다.
 */
@Configuration
@EnableWebFluxSecurity
@EnableConfigurationProperties(KineticProperties.class)
public class KineticSecurityConfig {

    private static final Logger log = LoggerFactory.getLogger(KineticSecurityConfig.class);

    static final String[] PROTECTED_PATHS = {"/mcp/kinetic", "/mcp/kinetic/**", "/api/kinetic/**"};

    /** 지연 JWKS 조회 디코더 + issuer·audience·만료 검증. */
    @Bean
    public ReactiveJwtDecoder kineticJwtDecoder(KineticProperties props) {
        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder.withJwkSetUri(props.getJwksUrl()).build();
        final String audience = props.getAudience();
        OAuth2TokenValidator<Jwt> audienceValidator = new JwtClaimValidator<Collection<String>>(
                JwtClaimNames.AUD, aud -> aud != null && aud.contains(audience));
        List<OAuth2TokenValidator<Jwt>> validators = new ArrayList<>();
        validators.add(JwtValidators.createDefaultWithIssuer(props.getIssuer()));
        validators.add(audienceValidator);
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(validators));
        // JWKS 조회 실패(연결 오류 등)는 WebClient 예외가 그대로 새어 500 이 된다. JwtException(BadJwtException 아님)으로
        // 감싸면 AuthenticationServiceException 으로 바뀌고, 진입점이 503 으로 답한다(토큰 잘못이 아니므로 401 아님).
        return token -> decoder.decode(token).onErrorMap(e -> !(e instanceof JwtException),
                e -> new JwtException("cannot verify token (JWKS unavailable): " + e.getMessage(), e));
    }

    @Bean
    public SecurityWebFilterChain kineticSecurityWebFilterChain(ServerHttpSecurity http, KineticProperties props,
                                                                ReactiveJwtDecoder kineticJwtDecoder) {
        if (!props.isEnabled()) {
            // 키네틱 비활성: 어떤 요청에도 매칭되지 않는 체인 하나만 둔다
            // (체인이 없으면 Spring Boot 기본 체인이 모든 경로에 Basic 인증을 건다).
            log.info("kinetic: disabled (KINETIC_ENABLED=false) — no JWT chain");
            return http.securityMatcher(exchange -> ServerWebExchangeMatcher.MatchResult.notMatch())
                    .csrf().disable().httpBasic().disable().formLogin().disable().logout().disable()
                    .build();
        }

        KineticAuthenticationEntryPoint entryPoint = new KineticAuthenticationEntryPoint(props.resourceMetadataUrl());

        // 기존 CORS 설정 그대로 + 401 의 WWW-Authenticate 를 브라우저가 읽을 수 있게 노출.
        CorsConfiguration cors = new CorsConfiguration(CorsConfig.baseCorsConfiguration());
        cors.addExposedHeader(HttpHeaders.WWW_AUTHENTICATE);
        UrlBasedCorsConfigurationSource corsSource = new UrlBasedCorsConfigurationSource();
        corsSource.registerCorsConfiguration("/**", cors);

        log.info("kinetic: JWT required on {} (jwks={}, iss={}, aud={})",
                String.join(",", PROTECTED_PATHS), props.getJwksUrl(), props.getIssuer(), props.getAudience());

        return http
                .securityMatcher(ServerWebExchangeMatchers.pathMatchers(PROTECTED_PATHS))
                .csrf().disable()
                .httpBasic().disable()
                .formLogin().disable()
                .logout().disable()
                .requestCache().disable()
                .securityContextRepository(NoOpServerSecurityContextRepository.getInstance())
                .cors(c -> c.configurationSource(corsSource))
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.OPTIONS).permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/kinetic/health").permitAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(o -> o
                        .jwt(j -> j.jwtDecoder(kineticJwtDecoder))
                        .authenticationEntryPoint(entryPoint))
                .exceptionHandling(e -> e.authenticationEntryPoint(entryPoint))
                .build();
    }
}
