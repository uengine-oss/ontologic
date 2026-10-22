# kinetic-action — 온톨로지 키네틱 액션 실행기 (spec 014)

"P1 공장에서 온도 80℃ 넘는 설비 전부 점검 모드로 바꿔" 같은 요청을
**그래프 인스턴스 선택 → 인스턴스별 정책 판정 → 계획(dry-run) → (임계 초과 시) 사람 승인 → 대상별 마이크로서비스 호출**
로 실행한다. 액션은 여러 시스템을 차례로 부르는 **다단계(사가)** 일 수 있고, 중간에 실패하면 앞 단계를 역순으로
자동 보상하며, 실행한 run 은 `POST /runs/{id}/compensate`(MCP `compensate_run`)로 역순 취소한다. 계약은 [`specs/014-kinetic-action-layer/contracts/kinetic-api.md`](../specs/014-kinetic-action-layer/contracts/kinetic-api.md)
하나뿐이고, 이 서비스는 그 계약의 구현이다.

## 구성

| 모듈 | 하는 일 |
|---|---|
| `app/main.py` | FastAPI(REST `/api/kinetic`) + MCP(`/mcp`, stateless Streamable HTTP). `/mcp` 는 인증 후 세션 매니저로 직접 넘긴다 |
| `app/auth.py` | RS256 + JWKS 검증, actor 구성, RFC 9728 401 헤더 |
| `app/catalog.py` | 그래프에서 발행된 액션 적재 (`KINETIC_CATALOG_REFRESH` 주기 + `POST /catalog/refresh`), `steps` 해석 |
| `app/registry.py` | 서비스 등록·수정·삭제·OpenAPI 새로고침, 수동 Operation, OpenAPI → Operation, 게이트웨이 Route |
| `app/targeting.py` | 구조화 필터 → 파라미터화 Cypher (라벨·속성·연산자 화이트리스트, 값은 파라미터만) |
| `app/policy.py` | CEL 정책 (기본 거부, roles 필터, 평가 오류 = 거부) |
| `app/mapping.py` | arg_mapping → method/url/headers/body (`$before`·`$steps.<단계>.response.*`·`$cancel.reason` 포함) |
| `app/plans.py` | plan · 승인 · 실행(재조회·재평가) · 대상별 사가 · 자동 보상 · 취소 · 재시도 · 되쓰기 |
| `app/dispatch.py` | 대상·단계별 호출 (동시성 제한, Idempotency-Key, X-Kinetic-Run/Internal), 시스템 health |
| `app/specs.py` | 스펙 입수 — JSON/YAML 원문, 형식 판별, Swagger 2.0 → OpenAPI 3 변환, WSDL operation 이름 (계약 §8) |
| `app/sysauth.py` | 직접 모드 시스템 인증 — api_key(header·query)·basic·bearer·OAuth2 client credentials(토큰 캐시)·login_token(JSON 로그인, 401 재로그인) |
| `app/store.py` | SQLAlchemy Core 저장소 (SQLite 기본, PostgreSQL) + 감사 로그. 기존 DB 는 빠진 컬럼만 추가(무손실) |
| `app/graph.py` | 그래프 접근 인터페이스(`GraphReader`)와 Neo4j(Bolt) 구현 |

## 실행

```bash
uv sync
KINETIC_NEO4J_URI=bolt://localhost:7690 KINETIC_NEO4J_PASSWORD=kineticdemo \
KINETIC_JWKS_URL=http://localhost:8032/.well-known/jwks.json KINETIC_ISSUER=http://localhost:8032 \
KINETIC_INTERNAL_SECRET=dev-secret KINETIC_SVC_DIRECT=1 \
uv run python -m app.main          # :8030
uv run pytest                       # 단위·통합 테스트 (그래프·서비스는 가짜)
```

데모 스택 전체(neo4j·postgres·dev IdP·mock MES·CMMS·APS)는 [`demo/kinetic-mes`](../demo/kinetic-mes/README.md).

## 환경 변수

| 변수 | 기본 | 설명 |
|---|---|---|
| `KINETIC_PORT` | `8030` | |
| `KINETIC_DB_URL` | `sqlite:///./kinetic.db` | `postgresql+psycopg://…` (또는 `postgresql://…`, 자동 변환) |
| `KINETIC_NEO4J_URI` / `_USER` / `_PASSWORD` / `_DATABASE` | `bolt://localhost:7687` / `neo4j` / – / – | ontological-db 도 같은 Bolt 로 붙는다 |
| `KINETIC_JWKS_URL` · `KINETIC_ISSUER` · `KINETIC_AUDIENCE` | – · – · `kinetic-action` | issuer 가 비면 iss 검사 생략 |
| `KINETIC_INTERNAL_SECRET` | – | 비어 있으면 `/systems/routes` 는 항상 403 |
| `KINETIC_PUBLIC_BASE` | `http://localhost:8030` | 401 의 resource_metadata URL 과 `resource` 값. 게이트웨이 뒤면 게이트웨이 주소 |
| `KINETIC_SVC_BASE` | `http://localhost:9000/svc` | 게이트웨이 경유 호출 기준 |
| `KINETIC_SVC_DIRECT` | – | `1` 이면 시스템 `base_url` 로 직접 (개발용) |
| `KINETIC_CONCURRENCY` | `8` | 동시 호출 상한 |
| `KINETIC_MAX_ATTEMPTS` | `3` | 대상별 시도(1단계부터 끝까지 한 번 = 1회) 상한 — 다다르면 `dead` |
| `KINETIC_PLAN_TTL` | `600` | 초 |
| `KINETIC_CATALOG_REFRESH` | `30` | 초 |
| `KINETIC_QUERY_MAX_ITEMS` | `500` | 조회 경로(`POST /systems/{name}/query`) 응답 배열 상한 (계약 §9.2) |

OpenTelemetry: `uv sync --extra otel` 후 표준 `OTEL_*` 환경으로 설정하면 `kinetic.plan`/`kinetic.execute`/`kinetic.dispatch`
스팬이 나간다. 설정하지 않으면 no-op.

## 계약에서 정한 해석 (구현 결정)

계약이 명시하지 않은 부분은 아래처럼 정했다. 다른 구성요소는 이 동작을 전제로 맞춘다.

1. **카탈로그 키 = (class_name, behavior_name).** 여러 모델이 같은 이름을 발행하면 `version` 이 큰 것.
   `behavior_name` 이 `^[A-Za-z0-9_]+$` 가 아니면 무시. 객체 자리의 `"[]"`(발행 모듈 `_json` 의 빈 값)는 `{}` 로 읽는다.
2. **plan 대상 라벨**은 카탈로그에 액션이 하나 이상 있는 클래스만 허용(`invalid_filter`).
3. **보이지 않는 액션**(roles 불일치)으로 plan 하면 `forbidden`(403), 발행되지 않은 액션은 `not_found`.
4. **시스템/operation 미등록**이면 plan 이 `not_found` 로 실패한다 (미리보기를 만들 수 없으므로).
5. **params 검증**은 JSON Schema 의 `required`·기본 `type`·`enum` 만 본다 (`invalid_params`).
6. **대상 키**: `key_property` 값의 문자열. 비면 `elementId(n)`. by-ids 의 `ids` 도 문자열로 비교(`toString(n.key) IN $ids`).
   by-ids plan 의 `where` 에는 `[{prop:<key_property 또는 "$elementId">, op:"in", value:ids}]` 를 기록한다.
7. **max_targets 초과**는 `LIMIT max_targets+1` 로 판정해 plan 전체를 `too_many_targets` 로 거부.
8. **confirm_threshold**: `len(allowed) > threshold` 이면 승인 필요. 승인은 `planned`/`awaiting_approval` 상태에서만,
   승인자 = plan 작성자여도 허용. 추가 엔드포인트 `POST /plans/{id}/reject`(approver) → status `rejected`, 실행 시 403.
9. **TTL**: `planned`/`awaiting_approval`/`approved` 가 만료되면 조회 시 `expired` 로 바뀐다. 이미 실행된 plan 은 만료되지 않으며
   재실행은 TTL 과 무관하게 기존 run 을 돌려준다. 실행 권한 확인(작성자)이 만료 확인보다 먼저다.
10. **재평가**: 실행 시 정책은 *현재 호출 토큰의 클레임*으로 다시 평가. 대상이 사라졌거나 거부되면 `skipped`(사유는 `error`).
11. **run 상태**: 실패/dead 없이 성공 ≥1 → `succeeded`, 성공과 실패 공존 → `partial`, 성공 0 (전부 실패 또는 전부 skipped) → `failed`.
12. **retry**: 정책은 재평가하지 않는다. 시도 후 `attempts >= KINETIC_MAX_ATTEMPTS` 이고 실패면 `dead`(execute 의 첫 시도에도
    같은 규칙). 2xx 만 성공. (개정: 같은 요청 재전송이 아니라 새 시도 번호로 1단계부터 — 28 참고)
13. **되쓰기**: 모든 단계 성공 시 **첫 단계** 응답 JSON 의 `status` 값(없으면 `"done"`)을 `writeback_property` 에 SET. 실패해도 대상은 `succeeded`,
    오류는 대상의 `writeback_error` 에 남긴다.
14. **Plan.preview 헤더**: `Idempotency-Key` 와 arg_mapping 의 header 만. `X-Kinetic-Run`(실행 시 정해짐)·비밀 헤더는 없음.
    `url` 은 실제로 호출할 주소(게이트웨이 모드면 `KINETIC_SVC_BASE/<system>/…`).
15. **시스템 인증**: `auth.secret_env` 는 환경변수 **이름**만 저장. 게이트웨이 모드에서는 게이트웨이가 주입(Route.auth_value_env).
    직접 모드에서는 kinetic-action 이 그 env 를 읽어 `auth_header` 에 넣고, `bearer` 인데 값에 `Bearer ` 접두가 없으면 붙인다.
    기본 헤더: api_key → `X-API-Key`, bearer → `Authorization`. 시스템 이름은 `^[a-z0-9][a-z0-9-]*$`.
16. **CEL 숫자 타입**: cel-python 은 int 와 double 을 섞어 비교하지 않는다(`target.temp > 80` 에서 temp 가 85.0 이면 평가 오류 → 거부).
    소수 속성은 `target.temp > 80.0` 또는 `double(target.temp) > 80.0` 으로 쓴다.
17. **MCP**: 도구 8개(`compensate_run`, §9.2 `query_system` 포함). 도구 결과는 JSON 텍스트 1개(+ structuredContent, 목록은 `{items:[…]}`). 오류는 `isError=true` 와 계약 오류 JSON.
    `/mcp` 와 `/mcp/` 둘 다 받는다 (리다이렉트 없음). DNS rebinding 보호는 끈다(게이트웨이 Host 헤더 때문).
    `/.well-known/oauth-protected-resource/mcp` 도 같은 메타데이터를 낸다.
18. **감사 로그**: `GET /api/kinetic/audit?plan_id=` (approver·admin). 이벤트: `plan`·`approve`·`reject`·`execute`·`retry`·`expire`·
    `compensate`·`register_system`·`query`(§9.2) (+ 29 의 레지스트리 이벤트). `X-Request-Id` 를 받으면 그대로 기록하고 응답에도 돌려준다.

### 다단계(사가)·보상·레지스트리 확장 (계약 §1.1·§1.3·§3·§4 개정분)

19. **steps 검증**: `name` `^[a-z][a-z0-9_]*$`·유일, 단계마다 `system`·`operation_id` 필수, `arg_mapping` 은 객체(생략 = `{}`,
    JSON 문자열도 받음). `compensation` 은 `operation_id` 필수, `system` 생략 시 그 단계의 시스템. 하나라도 어기면
    **액션 전체를 카탈로그에서 뺀다**(경고 로그). `steps` 가 없거나 `"[]"` 면 `name:"main"`, `title` = 액션 이름, 보상 없음.
    ActionSummary 의 `system`·`operation_id` 는 첫 단계 값.
20. **plan 검증**: 모든 단계와 **보상**의 시스템·operation 이 등록돼 있어야 한다 (없으면 `not_found`). 실행·재시도 시작 때도 다시 본다.
21. **preview**: 대상 × 단계 순서(대상별로 단계 1..n). Call 에 `step`·`compensable` 이 붙는다. 아직 없는 값
    (`$steps.*`, `$cancel.*`)은 `"<$steps.cmms.response.id>"` 처럼 식을 `<>` 로 감싼 문자열 — 경로 변수여도 URL 인코딩하지
    않는다. 미리보기에서 `$before` 는 plan 시점 속성. 미리보기 멱등 키는 `…:a1`.
22. **`$steps.X.response.p`**: 같은 대상의 **이번 시도에서 성공한** 단계 X 의 응답 JSON 을 점 경로로 따라간다(배열은 숫자 인덱스).
    단계가 아직 없거나 경로가 없으면 그 호출은 보내지 않고 단계 `failed`(error 에 사유). `$before.p` = 실행 직전 재평가 때
    다시 읽은 대상 속성 — run 대상의 `before` 에 저장되고 `$this` 도 같은 스냅숏이다(재시도·취소 때 그래프를 다시 읽지 않음).
23. **멱등 키**: 전진 `<plan>:<대상>:<단계>:a<시도>`, 보상은 **그 전진 키 + `:c`** = `<plan>:<대상>:<단계>:a<시도>:c`.
    계약 표기 `…:<단계>:c` 에 시도 번호를 넣은 것 — 자동 보상(a1) 뒤 재시도(a2)가 성공한 대상을 나중에 취소하면 같은 `:c`
    키가 서비스 중복 제거에 걸려 a2 가 만든 작업지시를 취소하지 못하기 때문.
24. **자동 보상**: i 단계 실패 → 남은 단계 `skipped`, 성공한 단계를 역순으로 보상(정의 없는 단계는 `compensation.status:'none'`,
    호출 없음). 보상 하나가 실패해도 **나머지 앞 단계 보상은 계속**한다. 결과: 모두 성공 → 대상 `compensated`
    (`compensated_by:'auto'`), 하나라도 실패 → `dead`. 1단계에서 실패하면 되돌릴 것이 없어 `failed`. 실패한 시도 후
    `attempts >= KINETIC_MAX_ATTEMPTS` 면 `compensated`/`failed` 도 `dead`. `$cancel.reason` 은 `"자동 보상: '<단계>' 단계 실패"`.
    대상 `error` 는 `"<단계>: <오류>"`, `http_status`·`response` 는 마지막으로 호출한 단계 값. 되쓰기는 전 단계 성공 때만.
25. **run 상태**: `skipped` 는 세지 않는다. 성공만 → `succeeded`, 성공 + (`failed`|`compensated`|`dead`) → `partial`, 성공 0 → `failed`.
    `finished_seq` 는 run 안에서 대상 사가가 끝난 순서(1부터, 재시도로 다시 끝나면 새 번호).
26. **취소**(`POST /runs/{id}/compensate`, MCP `compensate_run`): plan 작성자 또는 `kinetic_approver`(아니면 `not_plan_owner` 403).
    정책 재평가·승인 없음. `succeeded` 대상만, `finished_seq` 내림차순으로 **하나씩 순차**, 대상 안에서는 단계 역순.
    보상 없는 단계는 `none`. 대상: 다 성공 → `compensated`(`compensated_by:'cancel'`) + 되쓰기를 `$before[writeback_property]` 로 복원,
    하나라도 실패 → `dead`(복원 안 함). run: `dead` 대상이 하나라도 있으면(이전 자동 보상 실패 포함) `partially_compensated`,
    아니면 `compensated`. `reason` 이 비면 `"사용자 취소"`. `run.cancel = {actor_sub, reason, at}`. 재취소는 저장된 run 을
    그대로 돌려준다(호출 0, 권한은 확인). 취소된 run 의 retry 는 `conflict`(409). 감사 이벤트 `compensate`.
    단계 기록이 없는 이전 형식 run 은 취소 불가(`conflict`).
27. **`run.compensations`**: 실제 보상 **호출**만 호출 완료 순으로 쌓는다(`none` 은 넣지 않는다 — 단계의 `compensation` 에만).
    `seq` 는 run 전체에서 1부터, `at` 은 밀리초 RFC3339(`2026-10-22T02:27:32.922Z`). 자동 보상은 대상끼리 병렬이라 서로 섞일 수 있고,
    취소는 순차라 seq 가 곧 의미 있는 순서다. 단계의 `compensation = {status, http_status, response, at, error?}`.
28. **retry**: 대상 `failed` 와 `compensated_by:'auto'` 인 `compensated` 를 1단계부터 새 시도 번호로 다시(단계 기록은 새로 시작,
    이전 보상 이력은 `run.compensations` 에 남는다). `$this`/`$before` 는 실행 때 스냅숏, `$actor` 는 재시도 호출자(=작성자).
    이미 `attempts >= KINETIC_MAX_ATTEMPTS` 면 호출 없이 `dead`.
29. **레지스트리**: 등록(`POST /systems`)은 같은 이름이면 교체하되 `created_at`·수동 operation·(비어 있으면)`description` 을 유지한다.
    `openapi`·`openapi_url` 둘 다 없으면 빈 명세(수동 API 만 쓰는 시스템). `health_path` 기본 `/health`. 이름 `routes` 는 예약.
    `PATCH` 의 `openapi_url` 은 주소만 바꾼다(operation 갱신은 `refresh`). `refresh` 는 `openapi_url` 이 없으면 `invalid_params`.
    `DELETE` 는 지우고 `used_by` 에 그 시스템을 단계·보상에 쓰는 `Class.action` 목록을 준다.
    쓰기 이벤트는 감사에 `update_system`·`delete_system`·`refresh_system`·`add_operation`·`delete_operation`.
30. **수동 Operation**: `{operation_id, method, path, summary?, parameters?, request_body_schema?}`. `operation_id`
    `^[A-Za-z_][A-Za-z0-9_.-]*$`, method GET|POST|PUT|PATCH|DELETE(대소문자 무관, 응답은 대문자), path 는 `/` 시작,
    `parameters[].in` 은 path|query|header, path 의 `{변수}` 는 모두 `in:path` 로 선언돼야 한다(`in:path` 는 required 로 강제).
    같은 operationId 는 교체, OpenAPI 의 같은 operationId 보다 **수동이 우선**. OpenAPI 출처 operation 의 DELETE 는 `conflict`(409).
    Operation 에 `source:'openapi'|'manual'`.
31. **health**: `GET /systems/{name}/health` → `{ok, http_status, latency_ms, checked_at}` (+실패 시 `error`). 게이트웨이 모드면
    `KINETIC_SVC_BASE/<name><health_path>`(`X-Kinetic-Internal` 동반), 직접 모드면 `base_url`. 제한 3초, 2xx 만 ok.
32. **DB 이전**: 시작 때 `kinetic_systems` 에 `description`·`openapi_url`·`health_path`·`manual_ops`·`updated_at` 이 없으면
    `ALTER TABLE ADD COLUMN`(SQLite·PostgreSQL). 기존 run 문서는 그대로 읽힌다.

### 시스템 등록 모델 (계약 §8)

33. **필드**: §8.1 참고. 등록 교체 시 표시·소유 정보(`display_name`·`owner_team`·`contact`·`tags`·`icon`)는 주지 않으면 이전 값 유지,
    `auth` 는 종전처럼 주지 않으면 `none`. `tags` 는 중복 제거(≤30개·≤50자), `icon` 은 `^[a-z0-9][a-z0-9_-]*$`.
34. **환경**: 저장은 `environments`(JSON)·`active_environment`, `base_url` 컬럼은 항상 활성 환경 주소(게이트웨이 Route.uri 원천).
    environments 없이 등록하면 `[{name:'default', base_url}]`. 등록 때 environments 와 base_url 을 함께 주면 같은 주소의 환경이 활성
    (없으면 첫 환경). 환경을 바꾸면 operation 캐시도 버린다(servers 경로 접두 판단이 base_url 에 달려 있어서).
35. **스펙 입수 우선순위**: `openapi`(객체) > `openapi_text`(JSON→YAML 순으로 읽기, XML·SDL·proto 는 원문) > `openapi_url`(응답 본문을
    같은 방식으로 읽는다 — YAML URL 도 됨). 형식은 내용으로 판별하고, 판별이 안 될 때만 `spec_format` 값을 쓴다. swagger2 는 OpenAPI 3 로
    바꿔 `openapi` 컬럼에 저장(`x-kinetic-converted-from: swagger2`), wsdl·graphql_sdl·proto·asyncapi·odata_metadata 는 `spec_text` 에 원문.
    변환 범위: paths·경로 공통 parameters·`#/parameters` 참조·body/formData→requestBody·path/query/header 의 타입 필드→schema·
    responses.schema→content·definitions→components.schemas(`$ref` 재작성)·host/basePath/schemes→servers·securityDefinitions(간단).
36. **실행 불가 프로토콜**: soap·graphql·grpc·db_procedure·async 는 `executable:false`. plan(그리고 execute·retry 시작 검사)은 단계·보상의
    시스템을 operation 보다 **먼저** 확인해 `not_executable`(422). 그런 시스템은 `/systems/routes` 에 내지 않는다.
37. **인증 저장**: 컬럼 `auth_kind`(PostgreSQL 은 VARCHAR(40) 으로 넓힘)·`auth_header`·`auth_secret_env`·`auth_query_param`·
    `auth_token_url`·`auth_client_id`·`auth_client_secret_env`·`auth_scopes`(JSON). basic 의 `secret_env` 값 형식은 `"user:password"`.
    oauth2 는 `token_url`(http(s))·`client_id`·`client_secret_env` 필수, `scopes` 는 배열(또는 공백 구분 문자열).
38. **직접 모드 인증** (`KINETIC_SVC_DIRECT=1`): 게이트웨이와 같은 규칙. OAuth2 토큰은 (token_url, client_id, scopes) 별로 프로세스 메모리에
    `expires_in - 60`초 캐시(`expires_in` 없으면 300), 동시 요청은 한 번만 발급. 토큰 발급 실패 → 그 호출 `failed`,
    error `auth_unavailable: 토큰 발급 실패: HTTPStatusError HTTP 401` (본문·비밀은 남기지 않음). env 가 비면 인증 없이 보낸다.
    api_key 쿼리 값은 실제 요청 URL 에만 붙고 preview·run 기록에는 없다. health 도 같은 인증을 쓴다.
39. **`POST /systems/test`**: 검증 오류(이름·auth·environments 형식)는 422 로 거절하지 않고 — auth 형식 오류만 422 — 스펙·health 실패는
    항목별 `ok:false` 로 돌려준다. health 는 **직접** `base_url + health_path` GET(3초, 인증 없음). auth 는 필요한 env 이름이
    kinetic-action 프로세스에 있는지만 본다(값·토큰 발급 시도 없음). 감사 로그에 남기지 않는다.
40. **DB 이전**: §8 컬럼 16개를 `ALTER TABLE ADD COLUMN`. 기존 행은 protocol·environments 가 NULL → `rest`·`[{default, base_url}]` 로 읽는다.

### 기존 시스템 승격 (계약 §9 — login_token · 조회 경로 · 배열 매핑)

41. **login_token 등록**: `auth = {kind:'login_token', token_url, login_body?, username_field?='loginId', username_env,
    password_field?='password', password_env, token_path?='token', header?='Authorization', scheme?='Bearer', ttl_seconds?=1800}`.
    `token_url` http(s) 필수, `username_env`·`password_env` 는 env **이름**(`^[A-Z_][A-Z0-9_]*$`) 필수. `login_body` 는 객체(≤4000자)이고
    그 안에 `username_field`·`password_field` 키나 비밀처럼 보이는 키(`password`·`secret`·`token`·`api_key`·`access_token`… 값이 있으면,
    중첩 포함)가 있으면 `invalid_params`. `token_path` 는 점 경로(숫자 = 배열 인덱스), `scheme` 은 영문 시작 ≤30자 또는 빈 문자열
    (= 토큰만), `ttl_seconds` 60~86400. 저장: `auth_token_url`·`auth_header` + 새 컬럼 `auth_login`(JSON, 시작 때 자동 추가).
    `System.auth` 와 `Route.login_token` 은 같은 모양(`Route` 쪽은 `kind` 없음, `auth_header` 는 null). 연결 테스트의
    `required_env` 는 `[username_env, password_env]`.
42. **직접 모드 login_token**: `token_url` 에 JSON POST `{...login_body, <username_field>: env, <password_field>: env}` →
    응답 JSON 의 `token_path`. 만료 = JWT 페이로드 `exp`(서명 검증 없이 읽기), JWT 가 아니거나 `exp` 가 없으면 지금+`ttl_seconds`.
    `만료-60초`까지 (token_url, username_env, login_body) 별로 캐시, 동시 요청은 한 번만 로그인. 하위 응답 401 → 그 토큰을 버리고
    **한 번** 재로그인 후 같은 요청을 재전송(같은 Idempotency-Key). 두 번째도 401 이면 그대로 실패. env 가 비었거나 로그인 실패
    (비 2xx·JSON 아님·토큰 없음) → 그 호출 `auth_unavailable: 로그인 실패: HTTP 500` / `로그인 env 없음: X` (하위 서비스 호출 없음).
    다른 인증 종류와 달리 env 가 비면 인증 없이 보내지 않는다. health 도 같은 인증.
43. **게이트웨이 login_token** (api-gateway `KineticSystemAuth` kind `login_token`): 위와 같은 규칙, 캐시는 라우트별.
    로그인 실패·env 없음 → 503 `auth_unavailable`(메시지에 비밀 없음). 401 재시도 때 요청 본문을 다시 보내려고 그 라우트의
    본문 캐시를 켠다(내장 Retry 와 같은 방식). 라우트 인자 `scheme` 의 `-` 는 "접두 없음".
44. **조회 경로** `POST /api/kinetic/systems/{name}/query` `{operation_id, path_params?, query?}` → `{ok, http_status, data, truncated,
    latency_ms}` (+실패 시 `error`). 인증된 누구나(역할 무관). 순서: 시스템 없음 404 → 실행 불가 프로토콜 `not_executable`(422) →
    operation 없음 404 → GET 아님 `not_readonly`(422) → 경로 변수 누락 `invalid_params`. path 값은 URL 인코딩, `query` 값은
    스칼라 또는 스칼라 배열(반복 파라미터, bool 은 `true`/`false`, null 은 뺀다). 호출 경로·헤더는 dispatch 와 같다
    (게이트웨이 `KINETIC_SVC_BASE/<system><path>` + `X-Kinetic-Internal`, 직접 모드면 base_url + 인증). `Accept: application/json`,
    제한 시간 = 시스템 `timeout_ms`. 하위 비 2xx 도 REST 응답은 200 + `ok:false`·`http_status`·`data`(하위 본문)·`error:"HTTP n"`,
    연결 오류·인증 실패는 `http_status:null`. JSON 이 아니면 `data` 는 본문 문자열. 자르기: 최상위 배열, 또는 객체의
    `items|content|data|results|records|rows|list|value` 키 아래 배열(2단계까지, 예 `{data:{items:[…]}}`)을
    `KINETIC_QUERY_MAX_ITEMS` 개로 — 하나라도 잘렸으면 `truncated:true`(나머지 필드 예 `totalElements` 는 그대로).
    감사 이벤트 `query` detail `{system, operation_id, http_status, ok, truncated}` (파라미터 값은 남기지 않는다).
45. **operation 필터**: `GET /systems/{name}/operations?method=GET` (대소문자 무관).
46. **MCP `query_system(system, operation_id, path_params?, query?)`**: REST 조회 경로와 같다. 설명에 "GET 전용, 계획 전 상태 확인용,
    쓰기는 액션으로" 를 적었다.
47. **배열 인자 매핑**: `body.` 뒤 점 경로의 숫자 세그먼트는 배열 인덱스 — 배열은 인덱스까지 `null` 로 채워 늘린다
    (`body.processes.1.x` → `processes:[null,{x}]`). `body.0.a` 면 본문 자체가 배열. 같은 자리를 객체·배열로 엇갈려 쓰면, 또는
    인덱스 > 999 면 `invalid_params`(plan 단계에서 걸린다). `{"$literal": [...]}` 로 넣은 배열에 인덱스로 더 넣을 수 있다
    (리터럴은 복사해서 쓴다 — 카탈로그 원본 불변). 미리보기도 같은 본문(자리표시 규칙 21 그대로).
