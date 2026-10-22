# 계약: 키네틱 액션 레이어 (spec 014)

세 구성요소 — **Ontology Studio**(정의·발행·UI), **kinetic-action**(실행기), **api-gateway**(인증·서비스 연동) — 가
공유하는 단일 계약. 바꿀 때는 이 문서를 먼저 고친다.

## 1. 발행된 액션 (그래프, Studio → kinetic-action)

```
(m:_OntologyModel {schema_id})-[:HAS_CLASS]->(c:_OntologyClass {class_name})
                                             -[:HAS_ACTION]->(a:_OntologyBehavior {behavior_type:'action'})
```

`a` 의 속성 (JSON 값은 **문자열로 직렬화**, 발행 모듈의 `_json` 관례):

| 속성 | 타입 | 예 |
|---|---|---|
| `behavior_type` | `'action'` | 고정. 기존 SQL behavior 는 `'sql'` (없으면 `'sql'` 로 읽는다) |
| `behavior_name` | str | `setMaintenanceMode` (영문·숫자·`_`) |
| `class_name` | str | `Equipment` (인스턴스 라벨과 같다) |
| `schema_id` | str | 발행한 스키마 그룹 id |
| `description` | str | 에이전트에게 보이는 설명 |
| `parameters` | JSON Schema(object) | `{"type":"object","properties":{"reason":{"type":"string"}},"required":["reason"]}` |
| `key_property` | str | 인스턴스 식별 속성. 예 `code`. 비면 `elementId(n)` |
| `system` | str | 서비스 레지스트리 이름. 예 `mock-mes` |
| `operation_id` | str | 그 시스템 OpenAPI 의 operationId. 예 `setEquipmentStatus` |
| `arg_mapping` | JSON object | 아래 §1.1 |
| `effect` | `'read'\|'write'` | |
| `confirm_threshold` | int | 허용 대상 수가 이 값을 **넘으면** 사람 승인 필요. 0 = 항상 승인 |
| `max_targets` | int | 대상 상한. 넘으면 plan 거부 |
| `policy` | JSON array | 아래 §1.2 |
| `steps` | JSON array | **다단계(사가) 정의** — §1.3. 있으면 `system`·`operation_id`·`arg_mapping` 은 무시한다 |
| `compensate` | str | (구) 보상 액션 이름 — 메타데이터. 실제 보상은 `steps[].compensation` |
| `writeback_property` | str | 성공 시 대상 노드에 SET 할 속성 (빈 문자열 = 안 함) |
| `version` | int | |

### 1.1 arg_mapping

키는 `<위치>.<이름>` — 위치는 `path` · `query` · `header` · `body`. `body` 는 점 경로 허용(`body.a.b`).
값은 표현식 문자열:

- `$this.<prop>` — 대상 인스턴스 속성
- `$this.$key` — 대상 키 값
- `$params.<name>` — 호출 파라미터
- `$actor.<claim>` — 호출자 클레임 (예 `$actor.sub`)
- `$run.id`, `$plan.id`
- `$before.<prop>` — 실행 직전(재평가 시점) 대상 속성 스냅숏. 보상에서 원래 값 복원에 쓴다
- `$steps.<단계이름>.response.<점.경로>` — 같은 대상의 앞 단계 응답 (예: 작업지시 id)
- `$cancel.reason` — 취소 요청 사유 (보상 매핑에서만)
- 그 밖의 문자열 = 리터럴. JSON 리터럴이 필요하면 `{"$literal": <value>}`

예:
```json
{"path.code": "$this.code", "body.status": "MAINTENANCE", "body.reason": "$params.reason", "body.requestedBy": "$actor.sub"}
```

### 1.2 policy

```json
[{"roles": ["plant_operator"], "when": "target.plant == actor.plant", "description": "담당 공장 설비만"}]
```

- 규칙은 OR. 규칙이 하나도 없거나 아무 규칙도 맞지 않으면 **거부** (기본 거부).
- `roles` 생략·빈 배열 = 모든 인증 사용자. 있으면 `actor.roles` 와 교집합이 있어야 그 규칙 적용.
- `when` 생략 = true. CEL 식. 변수: `actor`(JWT 클레임 맵), `target`(인스턴스 속성 맵, `target["$key"]` 포함),
  `params`, `now`(RFC3339 문자열).
- **도구 노출**(list_actions)은 `roles` 만으로 판정 — 적용 가능한 규칙이 하나라도 있으면 보인다.
- **인스턴스 판정**은 `roles` + `when` 둘 다.

### 1.3 steps — 다단계 액션과 보상 (사가)

```json
[{"name": "mes", "title": "MES 설비 상태 변경", "system": "mock-mes", "operation_id": "setEquipmentStatus",
  "arg_mapping": {"path.code": "$this.code", "body.status": "MAINTENANCE", "body.reason": "$params.reason"},
  "compensation": {"system": "mock-mes", "operation_id": "setEquipmentStatus",
                   "arg_mapping": {"path.code": "$this.code", "body.status": "$before.status", "body.reason": "$cancel.reason"}}},
 {"name": "cmms", "title": "정비 작업지시 생성", "system": "mock-cmms", "operation_id": "createWorkOrder",
  "arg_mapping": {"body.equipmentCode": "$this.code", "body.reason": "$params.reason"},
  "compensation": {"system": "mock-cmms", "operation_id": "cancelWorkOrder",
                   "arg_mapping": {"path.id": "$steps.cmms.response.id", "body.reason": "$cancel.reason"}}},
 {"name": "aps", "title": "생산 일정 재배정", "system": "mock-aps", "operation_id": "createReschedule",
  "arg_mapping": {"body.equipmentCode": "$this.code"},
  "compensation": {"system": "mock-aps", "operation_id": "revertReschedule",
                   "arg_mapping": {"path.id": "$steps.aps.response.id"}}}]
```

- `name` 은 `^[a-z][a-z0-9_]*$`, 액션 안에서 유일. `compensation` 은 선택 (없으면 그 단계는 되돌리지 않는다 — 계획 카드에 표시).
- **대상 하나 = 사가 하나.** 단계는 순서대로, 대상끼리는 서로 독립(병렬 가능).
- **자동 보상**: 대상의 i 번째 단계가 실패하면 이미 성공한 단계 i-1 … 1 의 보상을 **역순**으로 호출한다.
  대상 상태 `compensated`. 보상까지 실패하면 `dead` (사람 처리).
- **취소(사용자 보상)**: `POST /runs/{id}/compensate` — `succeeded` 인 대상을 **실행 완료 역순**으로 하나씩,
  각 대상 안에서는 단계 **역순**으로 보상한다. 대상 상태 `compensated`, run 상태 `compensated`
  (일부만이면 `partially_compensated`). 취소는 원상 복구 방향이라 승인 없이 plan 작성자 또는 approver 가 할 수 있고,
  감사에 `compensate` 로 남는다. 같은 run 재취소는 기존 결과를 돌려준다.
- 멱등 키: 전진 `<plan>:<target>:<step>:a<attempt>`, 보상은 그 전진 키 + `:c` (`…:a<attempt>:c`) — 재시도 뒤 취소가 앞 시도의 보상 키와 겹치지 않게.
- writeback: 모든 단계 성공 시 `writeback_property` 에 첫 단계 응답의 `status`(없으면 `"done"`), 보상 완료 시 `$before` 값으로 되돌린다.
- `steps` 가 없으면 `system`·`operation_id`·`arg_mapping` 하나짜리 단계(`name:"main"`, 보상 없음)로 본다 — 하위 호환.

## 2. 인증 (모든 구성요소 공통)

- `Authorization: Bearer <JWT>`, RS256, JWKS 로 검증. env: `KINETIC_JWKS_URL`, `KINETIC_ISSUER`, `KINETIC_AUDIENCE`
  (기본 audience `kinetic-action`).
- 클레임: `sub`(필수), `roles`(문자열 배열), 그 밖의 속성(예 `plant`) 은 그대로 `actor` 에 들어간다.
- 역할 `kinetic_approver` 만 plan 을 승인할 수 있다. 역할 `kinetic_admin` 만 서비스 레지스트리를 쓸 수 있다.
- 401 응답은 `WWW-Authenticate: Bearer resource_metadata="<base>/.well-known/oauth-protected-resource"` 를 단다 (RFC 9728).
  api-gateway 경유 시 `<gateway>/.well-known/oauth-protected-resource/mcp/kinetic` (RFC 9728 경로 접미 형식) — 두 경로 모두 라우팅된다.
- JWKS 조회 실패는 401 이 아니라 503 `service_unavailable`.
- 남향 POST 재시도는 `Idempotency-Key` 가 있을 때만 — 서비스는 이 키로 중복을 걸러야 한다.

## 3. kinetic-action REST (`/api/kinetic`)

| 메서드 · 경로 | 권한 | 본문 / 응답 |
|---|---|---|
| `GET /.well-known/oauth-protected-resource` | 공개 | `{resource, authorization_servers:[issuer], bearer_methods_supported:["header"], scopes_supported:[]}` |
| `GET /api/kinetic/health` | 공개 | `{ok:true}` |
| `POST /api/kinetic/systems` | admin | `{name, base_url, openapi?:object, openapi_url?:str, auth?:{kind:'none'\|'api_key'\|'bearer', header?:str, secret_env?:str}, timeout_ms?:int}` → `System` |
| `GET /api/kinetic/systems` | 인증 | `[System]` (secret 값은 절대 포함 안 함) |
| `GET /api/kinetic/systems/{name}/operations` | 인증 | `[Operation]` |
| `GET /api/kinetic/systems/{name}` | 인증 | `System` + `operations` |
| `PATCH /api/kinetic/systems/{name}` | admin | `{description?, base_url?, auth?, timeout_ms?, health_path?, openapi_url?}` → `System` |
| `DELETE /api/kinetic/systems/{name}` | admin | 삭제 → `{deleted:true, used_by:[action...]}` (발행된 액션이 쓰고 있어도 지운다, 목록만 알려 준다) |
| `POST /api/kinetic/systems/{name}/refresh` | admin | `openapi_url` 을 다시 읽어 operation 갱신 (수동 등록분은 유지) → `System` |
| `GET /api/kinetic/systems/{name}/health` | 인증 | 게이트웨이 경유 `health_path` GET → `{ok, http_status, latency_ms, checked_at}` |
| `POST /api/kinetic/systems/{name}/operations` | admin | 수동 API 등록 `Operation` (+`source:'manual'`) → `Operation`. 같은 operationId 는 교체 |
| `DELETE /api/kinetic/systems/{name}/operations/{operation_id}` | admin | 삭제 |
| `GET /api/kinetic/systems/routes` | **내부 헤더** | `[Route]` — api-gateway 동적 라우트 원천 |
| `GET /api/kinetic/actions?class=` | 인증 | `[ActionSummary]` 호출자에게 보이는 것만 |
| `POST /api/kinetic/plans` | 인증 | `{class, action, where:[Filter], params}` → `Plan` |
| `POST /api/kinetic/plans/by-ids` | 인증 | `{class, action, ids:[str], params}` → `Plan` |
| `GET /api/kinetic/plans/{id}` | 인증 | `Plan` |
| `POST /api/kinetic/plans/{id}/approve` | approver | `{note?}` → `Plan` (status `approved`) |
| `POST /api/kinetic/plans/{id}/execute` | 인증, plan 작성자 | → `Run` |
| `GET /api/kinetic/runs/{id}` | 인증 | `Run` |
| `POST /api/kinetic/runs/{id}/retry` | 인증, 작성자 | 실패·자동보상된 대상을 1단계부터 다시 → `Run` |
| `POST /api/kinetic/runs/{id}/compensate` | 작성자 또는 approver | `{reason?}` 취소 — 역순 보상 → `Run` |
| `POST /api/kinetic/catalog/refresh` | 인증 | 카탈로그 즉시 재적재 → `{actions:int}` |

```ts
System    = {name, description, base_url, openapi_url, auth_kind, auth_header, auth_secret_env, timeout_ms, health_path, operations_count, route:"/svc/<name>", created_at, updated_at}
Operation = {operation_id, method, path, summary, parameters:[{name, in, required, schema}], request_body_schema, source:'openapi'|'manual'}
Route     = {id:"svc-<name>", system, path_prefix:"/svc/<name>", uri:base_url, auth_header, auth_value_env, timeout_ms}
Filter    = {prop, op:'='|'!='|'>'|'>='|'<'|'<='|'in'|'contains'|'starts_with'|'is_null'|'not_null', value?}
ActionSummary = {class, action, description, parameters, effect, confirm_threshold, max_targets, system, operation_id, steps:[{name, title, system, operation_id, compensable:bool}]}
Plan = {id, class, action, actor_sub, params, where, status:'planned'|'awaiting_approval'|'approved'|'executed'|'expired'|'rejected',
        requires_approval:bool, expires_at, allowed:[Target], denied:[Target & {reason}], preview:[Call], created_at}
Target = {key, props}
Call   = {target_key, step, method, url, headers(비밀 제외), body}   // 대상 × 단계
Run  = {id, plan_id, status:'running'|'succeeded'|'partial'|'failed'|'compensated'|'partially_compensated', started_at, finished_at,
        targets:[{key, status:'succeeded'|'failed'|'compensated'|'dead'|'skipped', http_status, response, error, attempts, finished_seq,
                  steps:[{name, title, system, status:'succeeded'|'failed'|'skipped'|'pending', http_status, response, error,
                          compensation:{status:'succeeded'|'failed'|'none', http_status, response, at}|null}]}],
        compensations:[{seq, at, target_key, step, system, operation_id, status, http_status, trigger:'auto'|'cancel'}],   // 보상 호출 순서 그대로
        cancel:{actor_sub, reason, at}|null}
```

규칙:
- plan 의 `where` 는 구조화 필터만. `prop` 은 `^[A-Za-z_가-힣][A-Za-z0-9_가-힣]*$`. 원문 Cypher 는 받지 않는다.
- plan TTL 기본 600초 (`KINETIC_PLAN_TTL`). 만료되면 실행 거부.
- `allowed` 수 > `confirm_threshold` → `requires_approval=true`, status `awaiting_approval`. 승인은 **REST 만**
  (MCP 도구에 approve 없음 — 에이전트가 스스로 승인하지 못하게).
- 실행 직전 대상을 다시 조회하고 정책을 다시 평가한다. plan 이후 정책을 잃은 대상은 `skipped`.
- 같은 plan 재실행 → 기존 run 을 그대로 반환 (중복 호출 없음).
- 대상·단계별 호출 헤더 `Idempotency-Key` (§1.3), `X-Kinetic-Run: <run_id>`, `X-Kinetic-Internal: <secret>`.
- 오류 코드(JSON `{error:{code, message}}`): `unauthenticated`(401), `forbidden`(403), `not_found`(404),
  `invalid_filter`/`invalid_params`(422), `too_many_targets`(422), `plan_expired`(409), `approval_required`(409), `not_plan_owner`(403).

## 4. kinetic-action MCP (`/mcp`, stateless Streamable HTTP)

같은 인증. 도구는 REST 와 1:1:

| 도구 | 인자 | REST |
|---|---|---|
| `list_actions` | `class?` | GET actions |
| `plan_action` | `class, action, where, params` | POST plans |
| `plan_action_ids` | `class, action, ids, params` | POST plans/by-ids |
| `execute_plan` | `plan_id` | POST plans/{id}/execute |
| `get_plan` | `plan_id` | GET plans/{id} |
| `get_run` | `run_id` | GET runs/{id} |
| `compensate_run` | `run_id, reason?` | POST runs/{id}/compensate — "취소해", "되돌려" |

`tools/list` 는 호출자와 무관하게 위 7개(도구 = 기능). **어떤 액션을 쓸 수 있는지**는 `list_actions` 가 호출자 정책으로 거른다.
`plan_action` 의 설명에 "승인이 필요하면 사람이 Studio 에서 승인해야 한다"를 적는다.

## 5. 마이크로서비스 호출 경로 (kinetic-action → api-gateway → 서비스)

- kinetic-action 은 `KINETIC_SVC_BASE`(기본 `http://localhost:9000/svc`) + `/<system>` + operation path 로 호출.
  `KINETIC_SVC_DIRECT=1` 이면 게이트웨이를 건너 `base_url` 로 직접 (개발·단위 테스트용).
- 모든 호출에 `X-Kinetic-Internal: $KINETIC_INTERNAL_SECRET`.
- api-gateway: `/svc/<name>/**` 는 이 헤더가 env 값과 같을 때만 통과, 통과 시 헤더를 **제거**하고
  `RewritePath /svc/<name>/(?<s>.*) → /${s}`, 시스템 auth 헤더(`auth_header: ${env[auth_value_env]}`) 주입,
  Retry(GET/멱등 키 있는 POST 2회, 5xx·연결 오류), CircuitBreaker, `timeout_ms`.
- api-gateway 는 `GET {KINETIC_URL}/api/kinetic/systems/routes`(같은 내부 헤더 동반)를 `KINETIC_ROUTE_REFRESH`(기본 15s)마다 읽는다.

## 6. api-gateway 북향

- `/mcp/kinetic/**` → kinetic-action `/mcp/**`, `/api/kinetic/**` → 그대로. JWT 검증(같은 JWKS). SSE 버퍼링 없음.
- `/.well-known/oauth-protected-resource/mcp/kinetic` 과 `/.well-known/oauth-protected-resource` → kinetic-action 공개 엔드포인트.
- 그 밖의 기존 라우트는 인증 없이 기존 동작 유지.
- 주체(`sub`) 단위 RequestRateLimiter (인메모리).

## 7. 데모 마이크로서비스 (demo/kinetic-mes)

서로 다른 팀이 운영하는 독립 서비스라는 설정. 각자 OpenAPI·`/health`·운영 콘솔(`/`)·고장 주입(`/admin/fail`)·초기화(`/admin/reset`)를 가진다.
모두 `Idempotency-Key` 로 중복을 걸러 처음 응답을 돌려준다.

| 시스템 이름 | 포트 | 역할 | operation |
|---|---|---|---|
| `mock-mes` | 8031 | 생산관리 — 설비 상태 | `setEquipmentStatus` POST `/equipment/{code}/status` `{status, reason, requestedBy}` → `{code, status, ...}` · `getEquipment` |
| `mock-cmms` | 8034 | 설비보전 — 정비 작업지시 | `createWorkOrder` POST `/work-orders` `{equipmentCode, reason, requestedBy}` → `{id, status:'OPEN', ...}` · `cancelWorkOrder` POST `/work-orders/{id}/cancel` `{reason}` → `{id, status:'CANCELLED'}` · `listWorkOrders` GET `/work-orders` |
| `mock-aps` | 8035 | 생산계획 — 일정 재배정 | `createReschedule` POST `/reschedules` `{equipmentCode}` → `{id, equipmentCode, moved_orders:[...], status:'APPLIED'}` · `revertReschedule` POST `/reschedules/{id}/revert` → `{id, status:'REVERTED'}` · `listReschedules` GET `/reschedules` |

`/admin/fail` 본문 `{codes:[설비코드...], all:bool, status:int, operations:[operationId...]}` — `operations` 가 있으면 그 operation 만 실패시킨다.

## 8. 시스템(서비스) 등록 모델 — API 관리 도구 공통 항목 (2026-10-22 추가)

Kong(Service/Route) · Apigee(API proxy) · Azure APIM · AWS API Gateway 가 공통으로 받는 값을 따른다.
**실행기는 항상 "HTTP + JSON operation" 하나만 본다.** 프로토콜 차이는 등록(스펙 변환)과 어댑터가 흡수한다.

`POST /api/kinetic/systems` 본문(기존 필드에 추가):

```ts
{
  name, display_name?, description?, owner_team?, contact?, tags?: string[], icon?: string,   // icon: 'mes'|'cmms'|'aps'|'erp'|'sap'|'scm'|'wms'|'generic'… (UI 아이콘 키)
  protocol: 'rest'|'odata'|'graphql'|'grpc'|'soap'|'db_procedure'|'async',                   // 기본 'rest'
  spec_format?: 'openapi3'|'swagger2'|'wsdl'|'graphql_sdl'|'proto'|'asyncapi'|'odata_metadata',
  openapi?: object, openapi_text?: string /* JSON 또는 YAML 원문 — 파일 업로드 */, openapi_url?: string,
  environments?: {name: string, base_url: string}[], active_environment?: string,         // 없으면 base_url 하나 = 'default'
  base_url,                                                                              // = 활성 환경 주소 (하위 호환)
  auth?: {kind: 'none'|'api_key'|'basic'|'bearer'|'oauth2_client_credentials',
          header?, query_param?,                       // api_key: header 또는 query_param 중 하나
          secret_env?,                                 // api_key·bearer 값, basic 은 "user:password"
          token_url?, client_id?, client_secret_env?, scopes?: string[]},   // oauth2_client_credentials
  timeout_ms?, retries?, health_path?
}
```

- 비밀 값은 **절대 저장하지 않는다** — 환경변수(또는 비밀 저장소) **이름**만. 응답에도 이름만.
- `protocol != 'rest'` 이고 `odata` 가 아니면 등록은 되지만 `executable:false`, `adapter_required:true` — 계획 단계에서
  `not_executable`(422) 로 막는다. (어댑터 로드맵: soap → db_procedure → grpc → graphql → async)
- `swagger2` 는 등록 시 OpenAPI 3 로 변환해 operation 을 뽑는다. YAML 원문도 받는다.
- `POST /api/kinetic/systems/test` (admin) — 저장하지 않고 연결 테스트: 스펙 파싱 결과(operation 수·오류),
  `health_path` 직접 호출 결과, 인증 설정 검사(필요한 환경변수 존재 여부만, 값은 보지 않음).
- `System` 응답에 위 필드 + `executable`, `adapter_required`, `environments`, `auth`(비밀 제외).
- `Route` 에 `auth_kind`, `auth_query_param`, `basic_env`, `oauth2:{token_url, client_id, client_secret_env, scopes}` 추가 —
  api-gateway 는 basic(`Authorization: Basic base64(env)`), api_key query 파라미터 주입, **OAuth2 client credentials
  토큰 발급·캐시(만료 60초 전 갱신)** 후 `Authorization: Bearer` 주입을 한다.

### 8.1 구현에서 정한 값 (kinetic-action · api-gateway, 2026-10-22)

- `System` 추가 필드: `display_name`(없으면 name), `owner_team`, `contact`, `tags:[]`, `icon`(없으면 `'generic'`), `protocol`,
  `spec_format`, `executable`, `adapter_required`, `environments:[{name, base_url}]`, `active_environment`(없으면 `'default'`),
  `retries`(기본 2, 0~5), `auth:{kind, header?, query_param?, secret_env?, token_url?, client_id?, client_secret_env?, scopes?}`.
  기존 `auth_kind`·`auth_header`·`auth_secret_env` 도 그대로 낸다.
- `protocol` 생략 시 스펙 형식에서 정한다(wsdl→soap, graphql_sdl→graphql, proto→grpc, asyncapi→async, odata_metadata→odata, 그 밖 rest).
  rest·odata·soap·graphql 의 base_url 은 http(s), grpc·db_procedure·async 는 아무 문자열.
- `PATCH` 는 `display_name·owner_team·contact·tags·icon·protocol·environments·active_environment·base_url·retries·openapi·openapi_text`
  도 받는다. `active_environment` 전환 = base_url 변경, environments 없이 `base_url` 만 주면 활성 환경 주소를 바꾼다.
- OpenAPI 3 `servers[0].url` 의 경로(Swagger 2 `basePath`)를 base_url 이 담고 있지 않으면 operation path 앞에 붙인다.
- WSDL 은 portType operation 이름만 Operation(`source:'wsdl'`, 실행 불가)으로 보인다.
- `POST /systems/test` 응답: `{ok, protocol, executable, adapter_required,
  spec:{ok, format, operations:int, operation_ids:[], error?, note?},
  health:{ok, http_status, latency_ms, url, error?},
  auth:{ok, kind, required_env:[], missing_env:[], checked_in:'kinetic-action', injected_by:'api-gateway'|'kinetic-action'}}`.
  env 검사는 kinetic-action 프로세스 기준이다 (게이트웨이 모드에서 실제 주입은 게이트웨이 env).
- `Route` 는 **실행 가능한 시스템만** 낸다. `{…기존, auth_kind, auth_query_param, basic_env, oauth2:{token_url, client_id,
  client_secret_env, scopes:[]}|null, retries}`. api_key(header)·bearer 는 기존 `auth_header`+`auth_value_env`,
  api_key(query) 는 `auth_query_param`+`auth_value_env`.
- 오류 코드 추가: `not_executable`(422, plan·execute·retry), 게이트웨이 `/svc/**` 의 `auth_unavailable`(503 — OAuth2 토큰 발급 실패
  또는 client secret env 없음, 하위 서비스는 부르지 않는다). 직접 모드에서는 그 대상·단계가 `failed`, error `auth_unavailable: …`.
- 비밀 필드(`auth.secret`·`value`·`password`·`client_secret`·`token`·`api_key`)를 값으로 보내면 `invalid_params`.

## 9. 기존 시스템 승격 — 로그인 토큰 인증 · 조회 경로 · 배열 매핑 (2026-10-22, PriMES)

### 9.1 인증 종류 `login_token`
JSON 로그인으로 토큰을 받는 사내 시스템(PriMES 등). OAuth2 표준이 아니다.

```ts
auth: {kind: 'login_token',
       token_url,                          // 예 http://localhost:8080/api/auth/login
       login_body?: object,                // 고정 필드 (예 {"tenant":"standard"})
       username_field?: 'loginId', username_env,   // 아이디를 담은 env 이름
       password_field?: 'password', password_env,  // 비밀번호 env 이름
       token_path?: 'token',               // 응답 JSON 에서 토큰 위치 (점 경로)
       header?: 'Authorization', scheme?: 'Bearer'}
```
- 게이트웨이(직접 모드면 kinetic-action)가 로그인 → 토큰 캐시. 만료는 JWT `exp` 가 있으면 그것, 없으면 `ttl_seconds`(기본 1800). 만료 60초 전 갱신.
  하위 호출이 401 이면 한 번 재로그인 후 재시도. 로그인 실패 → 503 `auth_unavailable`.
- 비밀 값은 env 이름만 저장 (§8 규칙 그대로). Route 에 같은 필드.

### 9.2 조회 경로 — `POST /api/kinetic/systems/{name}/query`
등록된 시스템의 **GET operation 만** 바로 부른다 (계획·승인 없음). 쓰기는 오직 액션.
```ts
req  {operation_id, path_params?: {}, query?: {}}     // GET 이 아닌 operation → 422 not_readonly
resp {ok, http_status, data, truncated: bool, latency_ms}  // data 는 JSON, 배열이면 최대 KINETIC_QUERY_MAX_ITEMS(500)
```
- 권한: 인증된 사용자 누구나 (시스템 자체 인가는 시스템이 한다). 감사에 `query` 로 남긴다.
- 게이트웨이 경유(인증 주입·재시도 동일). MCP 도구 `query_system(system, operation_id, path_params?, query?)`.
- 용도: (1) 구축 에이전트가 인스턴스 적재 (2) 채팅 에이전트가 현재 값 확인 (금형 남은 타수, 자재 소요 등).

### 9.3 배열 인자 매핑
`arg_mapping` 키의 점 경로에서 **숫자 세그먼트는 배열 인덱스**다: `body.lines.0.productCode`, `body.processes.1.equipmentCode`.
값 쪽 `$steps.x.response.workOrders.0.woNo` 도 같다(이미 지원). 리터럴 배열·객체는 `{"$literal": ...}`.

### 9.4 구현 메모 (kinetic-action · api-gateway, 2026-10-22)

- `System.auth`(login_token) = `{kind:'login_token', token_url, login_body, username_field, username_env, password_field, password_env,
  token_path, header, scheme, ttl_seconds}` — 기본값이 채워져 나온다(`loginId`·`password`·`token`·`Authorization`·`Bearer`·1800).
  `Route.login_token` = 같은 객체에서 `kind` 만 뺀 것(그 밖의 kind 면 null), 이때 `Route.auth_header` 는 null.
- `login_body` 안에 아이디·비밀번호 필드나 비밀 이름 키(`password`·`secret`·`token`·`api_key`…)가 있으면 `invalid_params`.
  `scheme:""` = 접두 없이 토큰만. `ttl_seconds` 60~86400. `token_path` 의 숫자 세그먼트는 배열 인덱스.
- 만료 판정은 JWT `exp` 를 **서명 검증 없이** 읽는다. login_token 은 env 가 비면 인증 없이 보내지 않고 `auth_unavailable`.
  401 재로그인은 한 번뿐 — 두 번째 401 은 그대로 돌려준다. 재시도 요청은 같은 본문·같은 `Idempotency-Key`.
- 조회 응답: 하위 비 2xx 여도 HTTP 200 + `ok:false`, `http_status`, `data`(하위 본문), `error`. 연결·인증 실패는 `http_status:null`.
  자르는 대상은 최상위 배열과 `items|content|data|results|records|rows|list|value` 아래 배열(2단계까지). JSON 이 아니면 `data` 는 문자열.
  오류 순서: 404(시스템) → `not_executable` → 404(operation) → `not_readonly` → `invalid_params`(경로 변수·query 값 형식).
- `GET /systems/{name}/operations?method=GET` 필터 추가. MCP `tools/list` 는 8개(§4 의 7개 + `query_system`).
- 배열 매핑: 인덱스까지 `null` 로 채운다, 인덱스 상한 999, 객체·배열 충돌은 `invalid_params`. `body.0.x` 면 본문이 배열.
