package com.roboanalyz.gateway.kinetic;

/**
 * 환경 변수 조회 추상화. 남향 시스템 인증값(Route.auth_value_env)을 읽는다.
 * 테스트에서는 맵 기반 구현으로 바꿔 끼운다.
 */
@FunctionalInterface
public interface EnvLookup {
    String get(String name);

    static EnvLookup system() {
        return System::getenv;
    }
}
