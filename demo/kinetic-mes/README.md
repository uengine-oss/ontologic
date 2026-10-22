# kinetic-mes 데모 — 키네틱 액션 종단 시연

"P1 공장에서 온도 80℃ 넘는 설비 전부 점검 모드로 바꿔" 를 그래프 → 정책 → 승인 → **MES · CMMS · APS 3단계 호출**
→ 그래프 되쓰기까지 실제로 돌리고, "방금 것 취소해" 를 **역순 보상**(APS 원복 → CMMS 작업지시 취소 → MES 상태 복원)으로
되돌린다. Studio 없이 돌도록 액션을 **계약 그래프 모양으로 직접 발행**한다(`seed.py`).

| 파일 | 내용 |
|---|---|
| `dev_idp.py` | ⚠ **개발 전용 IdP** (:8032). 누구에게나 토큰을 준다. `POST /token {sub, roles, plant}`, `/.well-known/jwks.json`. 키는 `.keys/`(gitignore). 서비스 간 인증용 `POST /oauth/token` (OAuth2 client credentials, form — 클라이언트 `kinetic-gateway`, 비밀 env `KINETIC_GATEWAY_CLIENT_SECRET` 기본 `aps-demo-secret`, `aud: mock-aps`, scope `aps.write`·`aps.read`), 발급 횟수 `GET /oauth/stats`·`POST /oauth/stats/reset` |
| `mock_mes.py` | 가짜 MES (:8031, 생산관리). `POST /equipment/{code}/status`(`setEquipmentStatus`), `GET /equipment/{code}`(`getEquipment`) |
| `mock_cmms.py` | 가짜 CMMS (:8034, 설비보전). `POST /work-orders`(`createWorkOrder`) → `{id:'WO-0001', status:'OPEN'}`, `POST /work-orders/{id}/cancel`(`cancelWorkOrder`) → `CANCELLED`, `GET /work-orders`(`listWorkOrders`). `GET /work-orders/{id}` 은 OpenAPI 에 없음(수동 등록 시연) |
| `mock_aps.py` | 가짜 APS (:8035, 생산계획). `POST /reschedules`(`createReschedule`) → `{id:'RS-0001', moved_orders, status:'APPLIED'}`, `POST /reschedules/{id}/revert`(`revertReschedule`) → `REVERTED`, `GET /reschedules`(`listReschedules`) |
| `seed.py` | Plant P1/P2 · Equipment 8대 · 3단계 `setMaintenanceMode` 발행 · 세 서비스 초기화·등록 · 카탈로그 갱신 |
| `verify_kinetic.py` | 공식 `mcp` 클라이언트(Streamable HTTP) + REST 로 19개 시나리오 검증 |
| `docker-compose.yml` | neo4j · postgres · dev-idp · mock-mes · mock-cmms · mock-aps · kinetic-action |

세 mock 서비스 공통 (다른 팀이 운영하는 독립 서비스라는 설정): `Idempotency-Key` 중복 제거(처음 응답 반환, `duplicate:true` 기록),
`GET /health`, `GET /calls`(받은 요청 기록 — `operation`·`code`·`run`(X-Kinetic-Run)·`idempotency_key`·`at`(epoch 초, 소수)),
`POST /admin/fail {codes, all, status, operations}`(operations 를 주면 그 operation 만 실패, codes 없이 operations 만 주면 그 operation 전부),
`POST /admin/reset`, 운영 콘솔 `/` (시각은 `HH:MM:SS.mmm` — 보상 순서가 보이게). 콘솔 머리: MES 남색 "MES · 설비 상태 변경 수신 기록",
CMMS 주황 "CMMS · 설비보전 · 정비 작업지시", APS 청록 "생산계획 · 일정 재배정".

## 서비스 인증 (계약 §8 — 실제로 검증한다)

| 시스템 | 업무 API 인증 | 레지스트리 `auth` (seed) | 값이 있어야 하는 곳 |
|---|---|---|---|
| `mock-mes` | 없음 | `{kind:'none'}` | – |
| `mock-cmms` | `X-API-Key` = env `CMMS_API_KEY` (기본 `cmms-demo-key`), 아니면 401 | `{kind:'api_key', header:'X-API-Key', secret_env:'CMMS_API_KEY'}` | api-gateway 프로세스 env `CMMS_API_KEY` |
| `mock-aps` | `Authorization: Bearer <JWT>` — dev-idp JWKS 로 서명·`iss`·`aud:mock-aps`·만료 검증, 아니면 401 (사용자 토큰 `aud:kinetic-action` 도 거절) | `{kind:'oauth2_client_credentials', token_url:'http://localhost:8032/oauth/token', client_id:'kinetic-gateway', client_secret_env:'APS_CLIENT_SECRET', scopes:['aps.write']}` | api-gateway 프로세스 env `APS_CLIENT_SECRET` (= dev-idp `KINETIC_GATEWAY_CLIENT_SECRET`) |

`/health`·`/openapi.json`·`/calls`·`/admin/*`·콘솔 `/` 는 공개다. 레지스트리에는 비밀 **이름**만 들어가고 값은 게이트웨이(직접 모드면
kinetic-action) env 에만 있다. 게이트웨이는 OAuth2 토큰을 만료 60초 전까지 캐시한다(재시작 전까지). seed 는 세 시스템을
`display_name`·`owner_team`·`contact`·`icon`(`mes`/`cmms`/`aps`)·`tags`·`environments:[{name:'dev', base_url}]` 와 함께 등록한다
(`seed.system_body(name, base, desc)` — Studio 준비 스크립트도 이걸 쓰면 같은 등록이 된다). compose 안의 kinetic-action 이
직접 호출하면 `APS_TOKEN_URL_FOR_KINETIC=http://dev-idp:8032/oauth/token` 로 seed 한다 (토큰 `iss` 는 그대로 localhost:8032).

## 포트 (다른 프로젝트와 겹치지 않게)

neo4j bolt **7690** / http **7477** (neo4j/kineticdemo) · postgres **5440** (kinetic/kinetic) ·
kinetic-action **8030** · mock-mes **8031** · dev-idp **8032** · mock-cmms **8034** · mock-aps **8035**. 모두 127.0.0.1 에만 연다.

## 실행 — compose

```bash
cd demo/kinetic-mes
docker compose up -d --build
MOCK_MES_URL_FOR_KINETIC=http://mock-mes:8031 MOCK_CMMS_URL_FOR_KINETIC=http://mock-cmms:8034 \
MOCK_APS_URL_FOR_KINETIC=http://mock-aps:8035 \
APS_TOKEN_URL_FOR_KINETIC=http://dev-idp:8032/oauth/token \
uv run python verify_kinetic.py        # compose 안의 kinetic-action 이 직접 호출 → "19/19 PASS"
docker compose down                    # 정지 (데이터 유지)
docker compose down -v                 # 정지 + 볼륨 삭제
```

## 실행 — 네이티브 (uv)

neo4j 만 컨테이너로 띄우고(`docker compose up -d neo4j`) 나머지는 uv 로:

```bash
cd demo/kinetic-mes
uv run python dev_idp.py &                                         # :8032
uv run python mock_mes.py &                                        # :8031
uv run python mock_cmms.py &                                       # :8034
uv run python mock_aps.py &                                        # :8035
cd ../../kinetic-action
KINETIC_NEO4J_URI=bolt://localhost:7690 KINETIC_NEO4J_PASSWORD=kineticdemo \
KINETIC_JWKS_URL=http://localhost:8032/.well-known/jwks.json KINETIC_ISSUER=http://localhost:8032 \
KINETIC_INTERNAL_SECRET=demo-internal-secret KINETIC_SVC_DIRECT=1 \
CMMS_API_KEY=cmms-demo-key APS_CLIENT_SECRET=aps-demo-secret \
uv run python -m app.main &                                        # :8030, SQLite ./kinetic.db
cd ../demo/kinetic-mes
uv run python verify_kinetic.py                                    # 기본 base_url = localhost:803x
```

`MOCK_*_URL_FOR_KINETIC` 는 레지스트리 `base_url` — *kinetic-action(직접 모드) 또는 api-gateway(게이트웨이 모드)가* 서비스에 닿는
주소다. 기본은 호스트에서 닿는 `http://localhost:8031/8034/8035`.

## 실행 — 게이트웨이 경유 (현재 라이브 구성)

mock 서비스·dev-idp·neo4j 는 compose, kinetic-action 은 네이티브(:8030, `KINETIC_SVC_DIRECT=0`,
`KINETIC_SVC_BASE=http://localhost:9000/svc`), api-gateway 는 :9000(라우트 3초 갱신). compose 의 `kinetic-action` 서비스는 띄우지 않는다.
게이트웨이 프로세스 env 에 `CMMS_API_KEY=cmms-demo-key APS_CLIENT_SECRET=aps-demo-secret` 이 있어야 한다 (kinetic-action 에도 주면
`POST /systems/test` 의 auth 검사가 ok — 그 검사는 kinetic-action 프로세스 env 를 본다).

```bash
docker compose up -d --build dev-idp mock-mes mock-cmms mock-aps
KINETIC_MCP_URL=http://localhost:9000/mcp/kinetic/ KINETIC_API_URL=http://localhost:9000 \
MOCK_MES_URL_FOR_KINETIC=http://localhost:8031 MOCK_CMMS_URL_FOR_KINETIC=http://localhost:8034 \
MOCK_APS_URL_FOR_KINETIC=http://localhost:8035 uv run python verify_kinetic.py   # 19/19 PASS
```

verify 는 seed 직후 `KINETIC_ROUTE_WAIT`(기본 5초 — 게이트웨이 라우트 갱신 주기보다 길게) 기다린 뒤 세 시스템의 `GET /api/kinetic/systems/{name}/health` 가 ok 가 될 때까지(게이트웨이가 새 라우트를 읽을 때까지) 기다린다.

## 환경 변수 (seed · verify)

| 변수 | 기본 |
|---|---|
| `KINETIC_MCP_URL` | `http://localhost:8030/mcp` — 게이트웨이 경유면 `http://localhost:9000/mcp/kinetic/` |
| `KINETIC_API_URL` | `http://localhost:8030` — 게이트웨이 경유면 `http://localhost:9000` |
| `DEV_IDP_URL` | `http://localhost:8032` |
| `MOCK_MES_URL` · `MOCK_CMMS_URL` · `MOCK_APS_URL` | `http://localhost:8031` · `:8034` · `:8035` (seed 초기화·verify 관찰용으로 직접 부름) |
| `MOCK_MES_URL_FOR_KINETIC` · `MOCK_CMMS_URL_FOR_KINETIC` · `MOCK_APS_URL_FOR_KINETIC` | `http://localhost:8031` · `:8034` · `:8035` (레지스트리 base_url) |
| `KINETIC_NEO4J_URI` / `_USER` / `_PASSWORD` | `bolt://localhost:7690` / `neo4j` / `kineticdemo` |
| `CMMS_API_KEY` · `APS_CLIENT_SECRET` | `cmms-demo-key` · `aps-demo-secret` (verify 가 서비스를 직접 관찰할 때만 씀 — 등록에는 이름만) |
| `APS_TOKEN_URL_FOR_KINETIC` | `$DEV_IDP_URL/oauth/token` (레지스트리 oauth2 token_url — 게이트웨이/kinetic-action 이 닿는 주소) |
| `KINETIC_ROUTE_WAIT` | `5` 초 — 라우트(인증 설정) 변경 후 게이트웨이 반영 대기 |

게이트웨이 경유로 서비스 호출까지 태우려면 kinetic-action 을 `KINETIC_SVC_DIRECT=0`,
`KINETIC_SVC_BASE=http://host.docker.internal:9000/svc` 로 띄우고 게이트웨이의 `KINETIC_INTERNAL_SECRET` 을 같게 맞춘다
(compose 기본은 직접 호출).

## 데이터

| 설비 | 공장 | 온도 |
|---|---|---|
| EQ-101 / 102 / 103 / 104 / 105 | P1 | 85 / 92.5 / 70 / 81.2 / 65 |
| EQ-201 / 202 / 203 | P2 | 88 / 95 / 60 |

액션 `Equipment.setMaintenanceMode` (version 2): 정책 `[{roles:['plant_operator'], when:'target.plant == actor.plant'}]`,
`confirm_threshold: 2`, `max_targets: 50`, `writeback_property: 'status'`, 단계 (계약 §1.3):

| # | 단계 | 호출 | 보상 |
|---|---|---|---|
| 1 | `mes` MES 설비 상태 변경 | `mock-mes.setEquipmentStatus` `{status:'MAINTENANCE', reason, requestedBy}` | 같은 operation, `status: $before.status`, `reason: $cancel.reason` |
| 2 | `cmms` 정비 작업지시 생성 | `mock-cmms.createWorkOrder` `{equipmentCode, reason, requestedBy}` | `cancelWorkOrder` `path.id: $steps.cmms.response.id` |
| 3 | `aps` 생산 일정 재배정 | `mock-aps.createReschedule` `{equipmentCode}` | `revertReschedule` `path.id: $steps.aps.response.id` |

`resumeOperation` 은 단일 단계(구 형식, steps 없음) 액션 — 시나리오 9 에서 발행한다.
지우는 범위는 이 데모 노드(`demo:'kinetic-mes'`)와 `schema_id:'demo-kinetic-mes'` 모델뿐이다.

## 시나리오 (verify_kinetic.py)

1. 토큰 없이 MCP → 401, `WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource"`
2. P1 운영자 `list_actions` → `setMaintenanceMode`, `viewer` 역할 → 빈 목록 (`tools/list` 는 7개 고정, `compensate_run` 포함)
3. `plan_action` temp>80 → P1 3대 허용, P2 2대 거부(사유)
4. (3대 > 임계 2 → 승인 후) 실행 → mock-mes 는 P1 3대만 받음, run `succeeded`, 그래프 `status=MAINTENANCE`
5. temp>60 → 5대(>2) `requires_approval` → 승인 없이 실행 `approval_required` · 운영자 자가 승인 403 → 승인자 REST 승인 → 성공
6. EQ-103 MES 고장 주입 → 1단계 실패(되돌릴 것 없음) → run `partial` → 복구 후 `POST /runs/{id}/retry`(새 시도 `:a2`) → `succeeded`
7. 같은 plan 재실행 → 같은 run, 세 서비스 모두 추가 호출 0, 멱등 키 중복 처리 없음
8. `GET /api/kinetic/systems/routes` 내부 헤더 없음 → 403
9. `resumeOperation` 발행(그래프 갱신) + `POST /catalog/refresh` → `list_actions` 에 나타남
10. (상태 초기화 후) temp>80 3단계 실행 → MES·CMMS·APS 가 각각 정확히 P1 3대만 받음, 대상마다 단계 3개 성공
11. MCP `compensate_run` 으로 취소 → 세 서비스가 기록한 시각으로 봐도 대상 안에서는 APS 원복 → CMMS 취소 → MES 복원,
    대상끼리는 실행 완료 역순(`finished_seq` 내림차순), `run.compensations` 의 seq 도 같은 순서. 그래프 `status` 는 RUNNING 으로 복원,
    작업지시 전부 CANCELLED · 재배정 전부 REVERTED, 재취소는 같은 결과
12. APS `createReschedule` 를 EQ-102 만 고장 → EQ-102 는 자동 보상(CMMS 취소 → MES 복원, trigger `auto`) `compensated`,
    EQ-101·104 는 성공, run `partial`, 그래프는 EQ-102 만 RUNNING
13. `POST /api/kinetic/systems/mock-cmms/operations` 로 OpenAPI 에 없는 `getWorkOrder` 수동 등록 → operations 에 `source:'manual'`,
    경로 변수 누락 등록은 422, `POST …/refresh` 후에도 유지
14. `GET /api/kinetic/systems/{name}/health` (게이트웨이 경유) → 세 시스템 모두 ok
15. mock-cmms·mock-aps 업무 API 를 키·토큰 없이 직접 → 401 (사용자 JWT 로 APS → 401), kinetic 실행은 게이트웨이가 `X-API-Key` 를
    주입해 3단계 성공. 시스템 응답·preview 에 비밀 값 없음
16. mock-aps OAuth2 client credentials — 이번 검증만의 token_url(질의 문자열)로 게이트웨이 캐시 키를 새로 만든 뒤 3대 실행 →
    APS 3건 성공, dev-idp 토큰 발급 **1회**, 다음 run 도 추가 발급 0회. 끝나면 seed 설정으로 되돌림
17. Swagger 2.0 YAML 업로드(`openapi_text`) → `spec_format:'swagger2'`, operation 3개(basePath `/api/v2` 가 path 에 붙음),
    body 스키마 변환, `active_environment` 전환으로 base_url 변경 — 끝나면 삭제
18. WSDL 원문 등록 → `protocol:'soap'`, `executable:false`, `adapter_required:true`, operation 2개 · 그 시스템을 쓰는 액션 발행 →
    REST·MCP plan 모두 `not_executable`(422) — 끝나면 액션·시스템 삭제
19. `POST /api/kinetic/systems/test` (저장 안 함) → spec(operation 수)·health(직접 호출 200)·auth(env 존재) ok, 깨진 스펙·닿지 않는
    주소·없는 env 는 항목별 `ok:false`, 운영자 토큰은 403

게이트웨이 경유에서는 주입한 503 을 게이트웨이가 2번 더 재시도하므로(멱등 키가 있는 POST) 서비스 `/calls` 에 실패 기록이 3건씩 남는다.
