# API Gateway

Spring Cloud Gateway를 사용한 중앙 API 게이트웨이입니다.

## 개요

여러 마이크로서비스들을 하나의 엔드포인트(포트 9000)에서 접근할 수 있도록 라우팅하며, CORS 이슈를 통합 관리합니다.

## 아키텍처

```
                     ┌─────────────────────────────────────────────────────────────┐
                     │                     API Gateway (9000)                       │
                     │                                                               │
   Frontend Apps     │    ┌──────────────────────────────────────────────────────┐  │
   ─────────────────────▶│                   CORS Handler                         │  │
   (3000, 5173, 5175)    │    ┌───────────────────────────────────────────────┐  │  │
                         │    │              Route Configuration              │  │  │
                         │    └───────────────────────────────────────────────┘  │  │
                         └──────────────────────────────────────────────────────┘  │
                     └─────────────────────────────────────────────────────────────┘
                                                   │
       ┌───────────────────────────────────────────┼───────────────────────────────────────────┐
       │                      │                    │                    │                      │
       ▼                      ▼                    ▼                    ▼                      ▼
 ┌──────────┐         ┌──────────┐         ┌──────────┐         ┌──────────┐         ┌──────────┐
 │  ANTLR   │         │   ROBO   │         │ Text2SQL │         │   OLAP   │         │Architect │
 │  Parser  │         │ Analyzer │         │          │         │          │         │          │
 │  (8081)  │         │  (5502)  │         │  (8000)  │         │  (8007)  │         │  (8001)  │
 └──────────┘         └──────────┘         └──────────┘         └──────────┘         └──────────┘
   Java/Spring          Python/FastAPI      Python/FastAPI      Python/FastAPI      Python/FastAPI
```

## 라우팅 설정

`application.yml`에 선언된 순서대로 **first-match** 라우팅합니다(위에서부터 먼저 매칭되는 라우트로).

### 직접 경로

| 경로 패턴 | 대상 서비스 | 포트 | 비고 |
|-----------|-------------|------|------|
| `/antlr/**` | ANTLR Parser | 8081 | |
| `/robo/analyze/**`, `/robo/pipeline/**` | ROBO Analyzer | 5502 | |
| `/robo/glossary/**`, `/robo/business-calendar/**` | ROBO Data Catalog | 5503 | |
| `/robo/**` (catch-all) | ROBO Glossary | 5504 | |
| `/text2sql/**` | Text2SQL | 8000 | |
| `/olap/**` | Data Platform OLAP | **8007** | prefix 제거 |
| `/architect/**` | ROBO Architect | 8001 | prefix 제거 |
| `/langchain/**` | LangChain | 8001 | prefix 제거 |
| `/ontology/**`, `/api/ontology/**` | Domain Layer / Ontology | 8002 | |
| `/risk-calculator/**` | Risk Calculator | 8003 | |
| `/data-fabric/**` | Data Fabric | 8004 | |
| `/whatif/**` | What-If Simulator | 8005 | `/whatif/`→`/api/` |
| `/api/security/**` | Data Secure Guard | 8006 | |
| `/agent-scheduler/**` | Agent Scheduler | 8089 | |
| `/node-agent-scheduler/**` | Node Agent Scheduler | 8091 | |
| `/**` (fallback) | robo-data-frontend | 3000 | 미매치는 프론트로 |

### `/api/gateway/<svc>/**` prefix 라우트군

프론트가 `/api/gateway/` prefix를 붙여 보내면 RewritePath로 prefix를 떼고 위와 **동일 서비스**로 전달합니다(antlr·robo·text2sql·olap·architect·langchain·ontology·domain-whatif·data-fabric·whatif·security·risk-calculator 등).

## 시작 방법

### 사전 요구사항

- Java 8 이상 (Spring Boot 2.7.18 / Spring Cloud 2021.0.9)
- Maven 3.9 이상 (또는 mvnw 사용)

### 1. Maven 사용

```bash
cd api-gateway
mvn spring-boot:run
```

### 2. 스크립트 사용

```bash
chmod +x run-gateway.sh
./run-gateway.sh
```

### 3. JAR 빌드 후 실행

```bash
mvn clean package -DskipTests
java -jar target/api-gateway-1.0.0-SNAPSHOT.jar
```

## 키네틱 액션 레이어 (spec 014)

계약: `../specs/014-kinetic-action-layer/contracts/kinetic-api.md` (§2 인증, §5 남향, §6 북향). 코드는 `src/main/java/com/roboanalyz/gateway/kinetic/`.
아래 라우트는 Java 로 정의되며 기존 `application.yml` 라우트(인증 없음, CORS 동일)는 바뀌지 않습니다.

### 북향 (에이전트·Studio → kinetic-action)

| 경로 | 대상 (`KINETIC_URL`) | 인증 | 비고 |
|------|------|------|------|
| `/mcp/kinetic`, `/mcp/kinetic/**` | `/mcp`, `/mcp/**` | JWT | 응답 타임아웃 없음(SSE/Streamable HTTP 버퍼링 없음) |
| `/api/kinetic/**` | 같은 경로 | JWT (`GET /api/kinetic/health` 만 공개) | 응답 타임아웃 600s |
| `/.well-known/oauth-protected-resource`, `/.well-known/oauth-protected-resource/mcp/kinetic` | `/.well-known/oauth-protected-resource` | 공개 | RFC 9728 메타데이터 |
| `/api/kinetic/systems/routes` | — | — | 내부 전용이라 북향에서는 403 |

- JWT: RS256, JWKS(`KINETIC_JWKS_URL`)로 서명 검증 + `iss`·`aud`·만료 검증. JWKS 는 첫 요청 때 가져오므로 기동 시 JWKS 가 죽어 있어도 게이트웨이는 뜹니다(그동안 토큰 요청은 503 `service_unavailable`).
- 401 응답: `WWW-Authenticate: Bearer resource_metadata="${KINETIC_PUBLIC_BASE}/.well-known/oauth-protected-resource/mcp/kinetic"` + `{"error":{"code":"unauthenticated","message":...}}`.
- `Authorization` 헤더는 그대로 kinetic-action 에 전달합니다(kinetic-action 이 다시 검증). 클라이언트가 보낸 `X-Kinetic-Internal` 은 제거합니다.
- 레이트 리밋: JWT `sub` 단위 인메모리 토큰 버킷(인스턴스별 계산, Redis 불필요). 초과 시 429 `{"error":{"code":"rate_limited"}}`.
- CORS: 기존 `CorsConfig` 설정을 그대로 쓰고, 401 의 `WWW-Authenticate` 만 노출 헤더에 추가합니다. OPTIONS 프리플라이트는 인증 없이 통과합니다.

### 남향 (kinetic-action → 게이트웨이 → 업무 시스템)

- `KINETIC_ROUTE_REFRESH` 마다 `GET ${KINETIC_URL}/api/kinetic/systems/routes`(헤더 `X-Kinetic-Internal`)를 읽어 시스템마다 `/svc/<system>/**` 라우트를 만듭니다. 바뀌었을 때만 라우트를 갱신하고, kinetic-action 이 죽어 있으면 마지막으로 받은 라우트를 유지하고 경고 로그만 남깁니다.
- `/svc/**` 는 라우팅 전에 `X-Kinetic-Internal == KINETIC_INTERNAL_SECRET` 을 검사합니다. 없거나 다르면 등록 여부와 상관없이 403 `{"error":{"code":"forbidden"}}`. 비밀이 설정되지 않으면 `/svc/**` 는 모두 403. 비밀은 맞는데 등록되지 않은 시스템이면 404 `not_found`.
- 통과한 요청의 처리 순서: `X-Kinetic-Internal` 제거 → `/svc/<system>/(?<s>.*)` 를 `/${s}` 로 바꿈 → 시스템 인증 주입(아래) → CircuitBreaker `svc-<system>`(열리거나 연결 실패 시 503 `service_unavailable`) → Retry(Route `retries`, 기본 2회, 0 이면 재시도 없음 — 5xx·연결 오류) → 응답 타임아웃 `timeout_ms`.
- 시스템 인증 (계약 §8, Route `auth_kind`): `api_key` 헤더 = `auth_header: $env[auth_value_env]`, `api_key` 쿼리 = `?<auth_query_param>=$env[auth_value_env]`(URL 인코딩),
  `basic` = `Authorization: Basic base64($env[basic_env])`(값 형식 `user:password`), `bearer` = `Authorization: Bearer $env[auth_value_env]`(접두 없으면 붙임),
  `oauth2_client_credentials` = `oauth2.token_url` 에 form POST(`grant_type=client_credentials`, `client_id`, `client_secret=$env[client_secret_env]`, `scope`=scopes 공백 결합)
  → `access_token` 을 라우트별로 `expires_in - 60`초 캐시(없으면 300초, 동시 요청은 한 번만 발급, 라우트 갱신에도 유지) → `Authorization: Bearer`.
  토큰 발급 실패·client secret env 없음 → 503 `{"error":{"code":"auth_unavailable"}}` (하위 서비스는 부르지 않음).
  api_key·bearer·basic 의 env 가 비면 경고 한 번 남기고 인증 없이 보냅니다. 비밀·토큰은 로그에 남기지 않습니다.
  `login_token`(계약 §9.1, PriMES 같은 사내 JSON 로그인) = `login_token.token_url` 에 JSON POST(`login_body` + `<username_field>: $env[username_env]`,
  `<password_field>: $env[password_env]`) → 응답 JSON 의 `token_path`(점 경로) 토큰을 `header: <scheme> <token>` 로 주입. 라우트별 캐시 — 만료는
  JWT `exp`(서명 검증 없이 읽음)가 있으면 그것, 없으면 `ttl_seconds`(기본 1800), 만료 60초 전 갱신. 하위 응답 401 → 토큰을 버리고 **한 번**
  재로그인 후 재시도(본문 캐시로 같은 본문 재전송). 로그인 실패·env 없음 → 503 `auth_unavailable`.
- Retry 는 GET 과 **`Idempotency-Key` 헤더가 있는 POST** 에만 걸립니다. POST 를 재시도해도 되는 근거는 kinetic-action 이 대상마다 `Idempotency-Key: <plan_id>:<target_key>` 를 보내고 하위 서비스가 그 키로 중복을 거른다는 계약입니다. 키 없는 POST 는 재시도하지 않습니다.
- 시스템 인증값은 라우트 정의에 들어가지 않고(환경 변수 이름만) 요청 때 읽으므로 `/actuator/gateway/routes` 에 비밀이 나오지 않습니다.

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `KINETIC_ENABLED` | `true` | `false` 면 북향 라우트·JWT 검증·라우트 갱신을 끔(`/svc/**` 403 가드는 유지) |
| `KINETIC_URL` | `http://localhost:8030` (docker: `http://kinetic-action:8030`) | kinetic-action 주소 |
| `KINETIC_JWKS_URL` | `http://localhost:8032/.well-known/jwks.json` | JWKS |
| `KINETIC_ISSUER` | `http://localhost:8032` | 기대하는 `iss` |
| `KINETIC_AUDIENCE` | `kinetic-action` | 기대하는 `aud` |
| `KINETIC_PUBLIC_BASE` | `http://localhost:9000` | 401 의 `resource_metadata` 에 쓰는 외부 주소 |
| `KINETIC_INTERNAL_SECRET` | (없음) | `/svc/**` 와 routes 조회에 쓰는 내부 헤더 값 |
| `KINETIC_ROUTE_REFRESH` | `15s` | 남향 라우트 갱신 주기 |
| `KINETIC_RATE_PER_SEC` | `10` | `sub` 별 초당 허용량 |
| `KINETIC_RATE_BURST` | `20` | `sub` 별 순간 최대량 |
| (Route 의 `auth_value_env` · `basic_env` · `oauth2.client_secret_env` · `login_token.username_env`/`password_env`) | — | 시스템별 인증값을 담은 환경 변수 (데모: `CMMS_API_KEY`, `APS_CLIENT_SECRET`, PriMES `PRIMES_LOGIN_ID`/`PRIMES_PASSWORD`) |

### 테스트

```bash
mvn -q test   # kinetic-action·JWKS·하위 서비스는 MockWebServer 로 흉내 냄
```

## 헬스 체크

```bash
# 게이트웨이 상태 확인
curl http://localhost:9000/actuator/health

# 라우팅 정보 확인
curl http://localhost:9000/actuator/gateway/routes
```

## CORS 설정

CORS는 **두 곳**에 정의되어 있습니다:

1. **`application.yml` globalcors** — origin을 **패턴**으로 허용: 모든 `http://localhost:[*]` · `http://127.0.0.1:[*]` 포트 + `https://*.ngrok-free.app`. 메서드 GET/POST/PUT/DELETE/PATCH/OPTIONS (HEAD 없음), allowCredentials.
2. **`CorsConfig.java`** — 명시 origin 목록(localhost/127.0.0.1 × 3000~3002, 5173~5175)에 **HEAD** 메서드와 `X-Total-Count` 노출 헤더 추가.

## 프론트엔드 연결

프론트엔드에서는 게이트웨이 주소 하나만 사용하면 됩니다:

### robo-data-frontend

환경 변수 `VITE_API_GATEWAY_URL`을 설정하거나, 기본값 `http://localhost:9000` 사용.

```typescript
// 자동으로 게이트웨이 URL 사용
import { antlrApi, roboApi, text2sqlApi } from '@/services/api'
```

### data-platform-olap/frontend

```javascript
// 자동으로 게이트웨이 URL 사용
import * as api from './services/api'
```

### robo-architect/frontend

`main.js`에서 fetch를 래핑하여 `/api/*` 경로를 자동으로 게이트웨이로 라우팅합니다.

## 환경 변수

### 게이트웨이 서버

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SERVER_PORT` | 9000 | 게이트웨이 포트 |

### 프론트엔드

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `VITE_API_GATEWAY_URL` | http://localhost:9000 | API 게이트웨이 URL |

## 문제 해결

### CORS 오류

1. 게이트웨이가 실행 중인지 확인
2. 프론트엔드 origin이 `application.yml`의 `allowedOrigins`에 포함되어 있는지 확인
3. 브라우저 캐시 삭제 후 재시도

### 라우팅 실패

1. 대상 백엔드 서비스가 실행 중인지 확인
2. 포트 번호가 올바른지 확인
3. 로그 확인: `curl http://localhost:9000/actuator/health`

### 디버그 로깅

`application.yml`에서 로깅 레벨을 조정할 수 있습니다:

```yaml
logging:
  level:
    org.springframework.cloud.gateway: DEBUG
    reactor.netty: DEBUG
```
