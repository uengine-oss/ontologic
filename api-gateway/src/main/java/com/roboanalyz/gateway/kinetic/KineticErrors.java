package com.roboanalyz.gateway.kinetic;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;

/** 계약 §3 오류 형식 {@code {"error":{"code","message"}}} 응답 도우미. */
public final class KineticErrors {

    private KineticErrors() {
    }

    public static String json(String code, String message) {
        StringBuilder sb = new StringBuilder("{\"error\":{\"code\":\"").append(escape(code)).append('"');
        if (message != null) {
            sb.append(",\"message\":\"").append(escape(message)).append('"');
        }
        return sb.append("}}").toString();
    }

    public static Mono<Void> write(ServerHttpResponse response, HttpStatus status, String code, String message) {
        if (response.isCommitted()) {
            return Mono.empty();
        }
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        byte[] bytes = json(code, message).getBytes(StandardCharsets.UTF_8);
        response.getHeaders().setContentLength(bytes.length);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }

    static String escape(String s) {
        StringBuilder out = new StringBuilder(s.length() + 8);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': out.append("\\\""); break;
                case '\\': out.append("\\\\"); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.toString();
    }
}
