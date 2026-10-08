# Tasks: 온톨로지 객체 기반 대시보드 빌더

**Feature**: 011-ontology-board · **Date**: 2026-08-19
**Input**: [plan.md](plan.md) · [research.md](research.md) · [data-model.md](data-model.md) ·
[contracts/](contracts/) · [quickstart.md](quickstart.md)

## Format: `[ID] [P?] [Story] Description`

`[P]` = 다른 `[P]` 와 병렬 가능(다른 파일, 의존 없음). `[US n]` = User Story n.

## Path Conventions

백엔드 `ontology-studio/backend/src/modules/board/` · 프론트 `ontology-studio/frontend/src/features/board/` ·
테스트 `ontology-studio/backend/tests/modules/board/` · 데모 `ontology-studio/demo/`

---

## Phase 1: Setup

- [x] T001 `modules/board/` · `tests/modules/board/` · `features/board/` 디렉터리와 `__init__.py` 생성
- [x] T002 프론트 의존성 추가 — `echarts`, `gridstack` (`frontend/package.json`). **둘뿐이다** (research R-5)
- [x] T003 [P] 루트 `.env.example` 에 `BOARD_MCP_TRANSPORT` · `BOARD_MCP_URL` · `BOARD_MCP_COMMAND` 추가. **서브모듈에 `.env` 를 만들지 않는다** (원칙 VI)

## Phase 2: Foundational (Blocking)

**모든 User Story 가 이것에 의존한다. 여기서 계약을 고정하지 않으면 뒤의 검증이 전부 무의미하다.**

- [x] T004 `board/settings.py` — MCP 엔드포인트 설정 정규화. **URL 접두사(`/mcp`) 를 한 곳에서만 조립**하고 단위 테스트로 고정한다 (원칙 VI 의 접두사 함정)
- [x] T005 `board/mcp_client.py` — `ClientSession` + `streamablehttp_client`/`stdio_client`. 세션 재사용, 재연결, 구조화된 오류. **유일한 데이터 출입구**
- [x] T006 `scripts/probe_board_mcp.py` — 코드가 MCP 를 부르는 계약 프로브. quickstart §2 의 9개 판정을 그대로 구현. 응답 원문을 `demo/board-probe/` 에 남긴다
- [x] T007 **프로브 실행 → 9개 판정 확인.** 특히 5·6 의 `20 대 33`. 여기서 어긋나면 계약이 이미 바뀐 것이므로 **설계를 먼저 고친다**
- [x] T008 [P] `tests/modules/board/test_no_direct_graph_access.py` — AST import 금지. 금지 목록 `neo4j`·`ontology_runtime`·`session_store`·`agent_session`·`ontology.tools`·`ontology.datasource_exec` (FR-001·FR-002). `ontology_runtime/test_no_sqlite_dependency.py` 를 본뜬다
- [x] T009 [P] `board/models.py` — `WidgetKind`(닫힌 목록) · `PropertyProfile` · `ObjectProfile` · `WidgetSpec` · `DashboardSpec` Pydantic 모델 (data-model.md)

**Checkpoint**: 프로브가 통과하고 import 금지 테스트가 초록이면 다음으로 간다.

---

## Phase 3: User Story 1 — 객체를 끌어다 놓으면 위젯이 된다 (P1) 🎯 MVP

**목표**: 클래스를 드롭하면 위젯이 자동으로 정해져 그려지고, 근거가 보인다.

### Tests

- [x] T010 [P] [US1] `test_widget_map.py` — O1~O10 각각의 최소 사례 + **결정성**(같은 프로파일 → 같은 결과, FR-020/SC-008)
- [x] T011 [P] [US1] `test_query_gen.py` — 생성 Cypher 에 `CALL` 없음(FR-031), 필터가 항상 `params`(FR-032). **값이 `"Table"` 인 필터 회귀 테스트**(CR-6)

### Implementation

- [x] T012 [US1] `board/profile.py` — `ObjectProfile` 생성. virtual → `ontology_get_datasource_schema`, materialized → 노드 통째 RETURN 샘플 + 값 추론(FR-010/011). `instance_count` 는 **별도 `count()`**(FR-013). `type_source` 필수(FR-012)
- [x] T013 [US1] `board/profile.py` — 캐시. 키 `(schema_id, published_at)`, 수동 무효화(FR-014, research R-2)
- [x] T014 [US1] `board/widget_map.py` — 1단계 역할 판정(006 승계) + `geojson` 타입 감지
- [x] T015 [US1] `board/widget_map.py` — 2단계 가드 G1~G6(006 승계) + G7(잘린 시계열) · G8(확장 플래그 off)
- [x] T016 [US1] `board/widget_map.py` — 3단계 O1~O10, 첫 매치 승리. 폴백 `table`/`O10`(FR-023). 보조 위젯(FR-024). O3 의 `groupby` 는 카디널리티 오름차순(FR-025)
- [x] T017 [US1] `board/query_gen.py` — `WidgetSpec` → Cypher(materialized) / SQL(virtual). 집계는 서버가(FR-030)
- [x] T018 [US1] `board/query_gen.py` — **집계 승격**(AD-10 ①): 시간 입도 상향, 범주 상위 N. `total_count` 별도 조회, `badge` 생성(FR-034), 잘린 시계열은 표로 강등(FR-035)
- [x] T019 [US1] `board/api.py` — `GET /health` · `/models` · `/classes` · `/classes/{n}/profile` · `/classes/{n}/related` · `POST /classes/{n}/recommend` · `POST /widgets/query` (contracts/board-api.md). `ambiguous` 는 **409**
- [x] T020 [US1] `host/app.py` 에 board 라우터 마운트 (`/api/board`)
- [x] T021 [P] [US1] 차트 래퍼 이식 — `robo-data-frontend/src/shared/charts/` 6파일 + `assets/geo/korea.json` → `features/board/charts/`. **원본 커밋 해시를 파일 헤더에 적는다**(동기화하지 않는다는 표시)
- [x] T022 [US1] `features/board/useBoard.js` — API 클라이언트 (`useOntologyStudio.js` 패턴)
- [x] T023 [US1] `features/board/ObjectPalette.vue` — 클래스 트리. `binding_kind`·`orphaned` 표시. **가상 클래스에 인스턴스 0 을 보여주지 않는다**
- [x] T024 [US1] `features/board/BoardCanvas.vue` — gridstack 격자, 드롭 수용, 위젯 렌더. `rule`·`reason` 배지(FR-022), 잘림 배지(FR-034)
- [x] T025 [US1] 확장 플래그 off 상태 표시 — `/health` 의 `datasource_expansion:false` 를 UI 가 말한다(FR-004). **빈 차트로 두지 않는다**
- [x] T026 [US1] AppShell 에 Board 탭 연결

**Checkpoint (US1 = MVP)**: quickstart S1·S2·S3·S4 가 통과한다.

---

## Phase 4: User Story 2 — 그려진 화면에서 클릭해 고친다 (P1)

- [x] T027 [US2] `features/board/WidgetInspector.vue` — 위젯/축/계열 속성 편집, 위젯 종류 수동 변경
- [x] T028 [US2] 차트 요소 클릭 → 인스펙터 포커스. ECharts `click` 이벤트의 `componentType` 으로 축·계열·범례를 가른다(FR-041)
- [x] T029 [US2] `pinned` 플래그 — 수동 선택을 자동 추천이 덮지 않는다(FR-043). "자동 추천으로 되돌리기" 제공
- [x] T030 [US2] 되돌리기(undo) 스택(FR-044)
- [x] T031 [US2] gridstack `save()` → `layout` 반영(FR-042)

**Checkpoint**: S5·S6 통과.

---

## Phase 5: User Story 4 — 저장하고 준다 (P2)

> US3(바이브코딩)보다 먼저 한다 — 패치가 적용될 문서가 있어야 US3 을 검증할 수 있다.

- [x] T032 [P] [US4] `test_spec_invariants.py` — `password`/`host`/`SELECT`/`MATCH` 가 있으면 저장 거부(FR-061·SC-005)
- [x] T033 [US4] `board/spec_store.py` — `DashboardSpec` 검증(불변식) · 저장 · 목록 · 열기. **로컬 파일**(FR-063)
- [x] T034 [US4] 열기 시 위젯별 해소 판정 — `ok`/`missing_class`/`missing_property`/`expansion_disabled`/`ambiguous_class`. **하나가 깨져도 나머지는 연다**(FR-062)
- [x] T035 [US4] `api.py` — `GET/PUT /dashboards`, `GET /dashboards/{id}`
- [x] T036 [US4] 프론트 저장/열기 UI + 위젯별 해소 사유 표시

**Checkpoint**: S9·S10 통과.

---

## Phase 6: User Story 3 — 말로 고친다 (P2)

- [x] T037 [US3] `board/tools.py` — `dashboard_get` · `widget_recommend` · `dashboard_patch(dry_run=True 기본)`. **`execute` 를 올리지 않는다**(FR-050)
- [x] T038 [US3] 패치 검증 — 클래스·속성 존재, `widget_kind` ∈ 목록, `param_key` 해소, 불변식(FR-051)
- [x] T039 [US3] `agent_session/service.py` — `AgentMode` 에 `"dashboard"`, `_DASHBOARD_MODE_TOOLS` 구성
- [x] T040 [US3] `agent_bridge_mcp/router.py` `_MODES` + `server.py` `tools_for()` 에 `dashboard` 추가. **`ontology_mcp` 는 건드리지 않는다**(spec 004 FR-013)
- [x] T041 [US3] `skills/dashboard-edit/SKILL.md` — 권한 경계·`dry_run` 규율·도구 전제 점검. **파이썬에서 프롬프트를 조립하지 않는다**(FR-055)
- [x] T042 [US3] `api.py` — `POST /dashboards/{id}/patch`. 프론트에 **diff 확인 UI**(FR-052)
- [x] T043 [US3] 선택 컨텍스트 → 에이전트 전달 (선택 위젯·클래스·프로파일을 **값**으로)

**Checkpoint**: S7·S8 통과.

---

## Phase 7: User Story 5 — Superset 내보내기 (P3)

- [x] T044 [P] [US5] `board/superset_export.py` — `WidgetKind` → `viz_type`/`form_data` (contracts/superset-mapping.md). `kpi_group` 은 분해
- [x] T045 [US5] 제외 처리 — materialized 위젯은 `excluded[]` 에 **사유와 함께**(FR-071). 조용히 빠뜨리지 않는다
- [x] T046 [US5] `api.py` — `POST /dashboards/{id}/export/superset` + 프론트 표시

**Checkpoint**: S11 통과.

---

## Phase 8: 검증과 증거

- [x] T047 백엔드 전체 테스트 — `uv run --with pytest pytest backend/tests/modules/board -q`
- [x] T048 회귀 — 확장 플래그 off 시 `ontology_mcp` 도구 목록이 **정확히 4개**(FR-080). `answer` 모드 쓰기 도구 없음 유지(FR-083)
- [x] T049 **ontological-db 이식성** — `scripts/verify_ontological_backend.py`. 생성 Cypher 가 `properties(n)`·동적 `n[k]` 를 쓰지 않는지 여기서 드러난다
- [x] T050 결정성·성능 — SC-002(3초) · SC-003(폴백 아닌 것 5개 이상) · SC-008(2회 실행 동일)
- [x] T051 **Playwright headed 시나리오** — `demo/` 에 `board.spec.js`. S1·S4·S5·S7·S11 을 영상으로. 스크린샷은 **CSS 트랜지션 후**(원칙 VII)
- [x] T052 증거 보관 — `docs/business/evidence/011-board/` 에 영상 + 캡처 + 무엇을 보여주는지 적은 `README.md`. **되지 않는 부분은 그대로 녹화한다**
- [x] T053 사용자 매뉴얼 생성 — 캡처를 사용해 엔드유저 관점 매뉴얼

---

## Dependencies

```
Phase 1 → Phase 2 (T004→T005→T006→T007 은 순차)
Phase 2 → Phase 3 (US1, MVP)
Phase 3 → Phase 4 (US2 는 렌더된 위젯이 있어야 클릭한다)
Phase 4 → Phase 5 (US4 는 편집 결과를 저장한다)
Phase 5 → Phase 6 (US3 은 패치할 문서가 있어야 한다)
Phase 3 → Phase 7 (US5 는 위젯만 있으면 된다 — US2~4 와 병렬 가능)
전부 → Phase 8
```

**병렬 가능**: T008·T009 · T010·T011 · T021 · T032 · T044

## Implementation Strategy

**MVP = Phase 1~3.** 거기서 멈춰도 "객체를 끌어다 놓으면 위젯이 된다"가 성립한다.
Phase 2 의 T007(프로브 실행)이 유일한 하드 게이트다 — 계약이 어긋난 상태로 위에 쌓으면
두 번 고친다.


---

## 2차 라운드 (2026-08-19 · 사용자 요청 4건)

- [x] T054 자연어 편집 UI (`AskBar.vue`) + `POST /dashboards/{id}/ask` · **CLI 에이전트 경로**
- [x] T055 전역 필터 위젯 (`FilterBar.vue`) + `GlobalFilter` 모델 + 값 목록 API
- [x] T056 관계 기반 연결 해소 (`linkage.py`) — `same_class` · `same_name` · `join` 한 홉
- [x] T057 교차 필터 — 요소 클릭 → 키로 선택 → 관련 위젯 재조회
- [x] T058 미국 전력망 예제 (`scripts/seed_us_grid_demo.py`) + 미국 주 경계 GeoJSON
- [x] T059 지도 렌더 개선 — 배경 자동 선택 · 데이터 범위 맞춤 · 폴리곤 custom 시리즈
- [x] T060 규칙 순서 정정 — 공간 → 시간 → 계층·분포
- [x] T061 원시 위젯 투영에 키 포함 (교차 필터의 전제)
- [x] T062 Playwright S12~S15 추가 · **9/9 통과**
- [x] T063 전력망 도메인 나레이션 데모 (OpenAI TTS, 5분 39초)
- [x] T064 증거·매뉴얼 갱신


---

## 3차 라운드 (2026-08-20 · 자동 구성과 갤러리)

- [x] T065 `skills/dashboard-compose/SKILL.md` — 골든 퀘스천으로 무엇을 담을지 고르는 지시문
- [x] T066 `board/compose.py` — 추천 전량 실행 · 에이전트 선택 · 배치 · 전역 필터 제안
- [x] T067 `POST /compose` — **진짜 SSE** (`asyncio.Queue` + 태스크)
- [x] T068 `BoardGallery.vue` — 진입점 · 새로 만들기 · 자동 구성 · 삭제 확인
- [x] T069 BoardPanel 갤러리↔편집 2단계 · 빈 캔버스에 두 경로 안내
- [x] T070 `AskPanel.vue` — 속성창 아래 대화창 + **실행 로그** (이벤트 어휘는 `cliagents_backend` 와 동일)
- [x] T071 `POST /ask/stream` — 자연어 편집 스트리밍
- [x] T072 agent-bridge 도구 연결(`--mcp-config`) + `_engine_owns_widget_kind` 로 결정성 구조화
- [x] T073 구축 화면 스키마 목록 → 📊 → 자동 구성 진입
- [x] T074 `_extract_json` 괄호 균형 파서 (중첩 JSON 절단 버그)
- [x] T075 gridstack 13 `batchUpdate(false)` · 저장된 필터 선택지 채우기
- [x] T076 Playwright S17·S18 추가 · **12/12 통과**
- [x] T077 나레이션 데모 재녹화 (7분 28초, 21장면) · 증거·매뉴얼 갱신
