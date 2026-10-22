package com.roboanalyz.gateway.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

import java.util.Arrays;
import java.util.List;

@Configuration
public class CorsConfig {

    @Bean
    public CorsWebFilter corsWebFilter() {
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", baseCorsConfiguration());
        
        return new CorsWebFilter(source);
    }

    /**
     * 기존 CORS 설정 원본. 키네틱 JWT 체인(KineticSecurityConfig)도 이 설정을 복사해
     * 401 응답에 같은 CORS 헤더를 단다 (WWW-Authenticate 노출만 추가).
     */
    public static CorsConfiguration baseCorsConfiguration() {
        CorsConfiguration corsConfig = new CorsConfiguration();
        
        // Allowed Origins (모든 프론트엔드 포트)
        corsConfig.setAllowedOrigins(Arrays.asList(
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3002",
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:3002",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5175"
        ));
        
        // Allowed Methods
        corsConfig.setAllowedMethods(Arrays.asList(
            "GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"
        ));
        
        // Allowed Headers
        corsConfig.addAllowedHeader("*");
        
        // Exposed Headers
        corsConfig.setExposedHeaders(Arrays.asList(
            "Content-Disposition",
            "Content-Type",
            "X-Total-Count"
        ));
        
        // Allow Credentials
        corsConfig.setAllowCredentials(true);
        
        // Max Age
        corsConfig.setMaxAge(3600L);
        
        return corsConfig;
    }
}

