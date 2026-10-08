# Implementation Plan: 온톨로지 객체 기반 대시보드 빌더

**Branch**: `011-ontology-board` (미생성 — 현재 `main`) | **Date**: 2026-08-19 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-ontology-board/spec.md`

## Summary

발행된 온톨로지(`_Ontology*`)를 **MCP 표면으로 읽어** 객체 유형을 결정적으로 판정하고 위젯을
정한다. 드래그앤드롭으로 배치하고, 그려진 요소를 클릭해 고치고, 자연어로 패치한다.
저장물은 자격증명 없는 텍스트 문서 하나다.

기술적 접근의 핵심은 하나다 — **애플리케이션이 MCP 클라이언트다.** Neo4j 드라이버도 DB
커넥션도 갖지 않고, `mcp` SDK 의 `ClientSession` 으로 `ontology-studio-search` 서버에 붙어
도구를 **코드가** 호출한다(LLM 이 아니다). 그래서 spec 010 이 이미 보장한 것 — 카탈로그·레지스트리
라벨 차단, 바인딩 테이블 밖 SQL 금지, PII 제거, 읽기 전용 — 을 코드 한 줄 없이 상속한다.

대가는 **행 예산이 에이전트 기준**이라는 것이다(Cypher 20 / SQL 30, 실측). 집계 승격으로
흡수하고, 총계는 별도 `count()` 로 얻고, 그래도 모자라면 전용 MCP 프로파일에 붙는다.

## Technical Context

**Language/Version**: Python 3.12+ (백엔드) · JavaScript ES2022 + Vue 3.5 SFC (프론트엔드)

**Primary Dependencies**:
- 백엔드 — 기존 `fastapi` · `pydantic` · **`mcp` 1.28.1** (이미 설치, 신규 추가 없음)
- 프론트엔드 — **신규 2개**: `echarts` (차트) · `gridstack` (격자 캔버스).
  `vue-echarts` 는 **불필요** — 이식 대상이 raw ECharts 를 직접 다룬다 (research R-5)

**Storage**: `DashboardSpec` 텍스트 문서(JSON). 로컬 파일 — 새 DB·테이블 없음.
프로파일은 **메모리 캐시**, 키는 `(schema_id, published_at)`

**Testing**: `uv run --with pytest pytest` (백엔드, pytest 9.1.1) · AST 기반 import 금지 테스트 ·
Playwright headed (프론트·영상 증거) · `scripts/probe_board_mcp.py` (계약 프로브)

**Target Platform**: 로컬 데스크톱(Electron 셸) 및 사내 서버 배포. 그래프는 Neo4j 5 와
ontological-db **양쪽**에서 동작해야 한다

**Project Type**: 기존 웹 애플리케이션(ontology-studio)에 백엔드 모듈 + 프론트엔드 feature 추가

**Performance Goals**: 드롭 → 렌더 **3초 이내**(프로파일 캐시 미스 포함, SC-002) ·
자동 추천 결정성 100%(SC-008)

**Constraints**:
- **행 예산** — `MCP_MAX_RESULTS` 20 / `DATASOURCE_AGENT_ROW_PREVIEW` 30 (실측)
- Cypher 에 `CALL` 금지, 차단 라벨은 **문자열로도** 금지 → 필터는 `params`
- `properties(n)` · 동적 `n[k]` 금지 (ontological-db 이식성)
- **새 호스트 포트 0** (원칙 VIII)
- 데이터 조회는 api-gateway(9000)를 거치지 않는다 — 30초 타임아웃

**Scale/Scope**: 모델당 클래스 ~수십 개 · 대시보드당 위젯 ~20개 · 위젯 17종 · 판정 규칙 O1~O10
(+ 006 의 R1~R13 승계)

## Constitution Check

*GATE: Phase 0 이전 통과 필수. Phase 1 설계 후 재점검.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| **0. 그래프 저장소 두 가지** | **PASS** (주의) | 그래프에 직접 붙지 않는다. 다만 **생성하는 Cypher** 는 두 백엔드에서 돌아야 한다 — `properties(n)`·동적 `n[k]` 금지를 FR-010 이 명문화했고 quickstart §6 이 `verify_ontological_backend.py` 로 검증한다 |
| **I. 카탈로그는 그래프가 단일 원천** | **PASS** | 카탈로그를 읽지 않는다. 온톨로지는 발행 레지스트리에서, 데이터는 MCP 도구로 온다 |
| **II. Table 정체성·데이터소스 필터** | **N/A** | `:Table` 은 MCP 게이트가 차단한다. 닿을 경로가 없다 |
| **III. 두 표기 COALESCE** | **N/A** | 카탈로그 속성을 직접 읽지 않는다. `column_map[].type` 은 이미 정규화되어 온다 |
| **IV. 전역 삭제 금지** | **PASS** | 그래프에 **쓰지 않는다**. 쓰기는 `DashboardSpec` 뿐 |
| **V. 자격증명 미유출** | **PASS** (설계로) | 자격증명을 **가질 수 없다** (AD-1). FR-061 + SC-005 자동 검사 |
| **VI. 루트 `.env` 단일 원천** | **PASS** (주의) | 서브모듈에 `.env` 를 만들지 않는다. 새 키(`BOARD_MCP_*`)는 루트에. **URL 접두사 함정** — MCP HTTP 엔드포인트가 `/mcp` 를 포함하는지 여부를 한 곳에서 정규화하고 단위 테스트로 고정한다 |
| **VII. 실제 실행 검증** | **PASS** | quickstart.md 전체가 이 원칙의 이행이다. 영상 증거 없이 완료로 치지 않는다 |
| **VIII. 호스트 포트 최소** | **PASS** | **새 포트 0.** 보드 API 는 studio 백엔드에 `/api/board` 로 마운트(프론트와 같은 오리진), MCP 는 이미 점유 중인 8100 |
| **ontology-studio — 결정적 매핑 (LLM 금지)** | **PASS** | FR-020. LLM 은 문구·순서·라벨 제안에만 (AD-2) |
| **ontology-studio — 가상 클래스 인스턴스 0** | **PASS** | 읽기만 한다. UI 는 "가상"으로 표시하고 0 을 보여주지 않는다 |
| **ontology-studio — 모드별 권한 안 넓힘** | **PASS** | 새 `dashboard` 모드를 만든다. `answer` 경계 불변(FR-083). `ontology_mcp` 에 쓰기를 올리지 않는다(spec 004 FR-013) |
| **ontology-studio — 스킬은 표준 패키지** | **PASS** | `skills/dashboard-edit/SKILL.md` 하나 |
| **ontology-studio — 지시문과 값을 섞지 않음** | **PASS** | FR-055. 선택 위젯·프로파일은 **값**이므로 라벨 블록으로 전달 |

**위반 없음** — Complexity Tracking 비어 있다.

### Phase 1 설계 후 재점검

설계 산출물(data-model · contracts · quickstart)을 낸 뒤 다시 봤을 때 **판정이 바뀐 항목 없음.**
새로 확인한 것 둘:

- 원칙 VIII 이 요구하는 "같은 오리진"이 **경로 충돌을 만들지 않는다** — 기존 greedy 경로는
  `/api/schema/classes/{class_name:path}` 이고 `/api/board/**` 와 겹치지 않는다
- 원칙 V 를 **응답 계층에서도** 지켜야 한다 — `ontology_query_datasource_sql` 이 응답에 `sql` 을
  싣는데, 보드 API 는 그것을 밖으로 내보내지 않는다 (contracts/board-api.md)

## Project Structure

### Documentation (this feature)

```text
specs/011-ontology-board/
├── plan.md              # 이 파일
├── spec.md              # 요구사항 (이미 존재)
├── research.md          # Phase 0 — R-1..R-8, 남은 미결정
├── data-model.md        # Phase 1 — ObjectProfile / WidgetSpec / DashboardSpec / WidgetKind
├── quickstart.md        # Phase 1 — 검증 절차와 판정
├── contracts/
│   ├── mcp-consumption.md    # 소비 계약 (spec 010 표면)
│   ├── board-api.md          # 제공 계약 (프론트엔드용 HTTP)
│   ├── superset-mapping.md   # 내보내기 계약
│   └── agent-tools.md        # 에이전트 도구 계약 (dashboard 모드)
└── tasks.md             # Phase 2 (/speckit-tasks 가 만든다 — 여기서 만들지 않는다)
```

### Source Code (repository root)

```text
ontology-studio/
├── backend/src/modules/board/          # 신규 — 유일한 데이터 출입구는 mcp_client
│   ├── mcp_client.py                   #   ClientSession (stdio | streamable HTTP)
│   ├── profile.py                      #   ObjectProfile — count + 샘플/JIT 스키마, 캐시
│   ├── widget_map.py                   #   O1~O10 + 006 의 역할·가드·R1~R13 재사용
│   ├── query_gen.py                    #   WidgetSpec → Cypher | SQL (집계 승격 포함)
│   ├── spec_store.py                   #   DashboardSpec 검증·저장·패치 (쓰기는 여기)
│   ├── superset_export.py              #   WidgetKind → viz_type / form_data
│   ├── tools.py                        #   dashboard_get · widget_recommend · dashboard_patch
│   └── api.py                          #   /api/board 라우터
├── backend/src/modules/agent_bridge_mcp/
│   ├── router.py                       # 수정 — _MODES 에 "dashboard" 추가
│   └── server.py                       # 수정 — tools_for() 분기 추가
├── backend/src/modules/agent_session/
│   └── service.py                      # 수정 — AgentMode 에 "dashboard", _DASHBOARD_MODE_TOOLS
├── backend/src/host/app.py             # 수정 — board 라우터 마운트
├── backend/tests/modules/board/        # 신규
│   ├── test_no_direct_graph_access.py  #   AST import 금지 (FR-002)
│   ├── test_widget_map.py              #   결정성 + O1~O10 최소 사례
│   ├── test_query_gen.py               #   CALL 금지 · 필터는 params
│   └── test_spec_invariants.py         #   자격증명·질의문 0
├── frontend/src/features/board/        # 신규
│   ├── BoardCanvas.vue                 #   gridstack
│   ├── ObjectPalette.vue               #   graph://schema 기반 트리
│   ├── WidgetInspector.vue             #   포인트 클릭 편집
│   ├── charts/                         #   robo-data-frontend 에서 이식 (6파일)
│   └── useBoard.js                     #   useOntologyStudio.js 패턴
├── frontend/src/assets/geo/korea.json  # 이식 (5KB, 시도 17)
├── frontend/package.json               # 수정 — echarts, gridstack 추가
└── skills/dashboard-edit/SKILL.md      # 신규

scripts/probe_board_mcp.py              # 신규 — 코드가 MCP 를 부르는 계약 프로브
```

**Structure Decision**: 기존 ontology-studio 애플리케이션에 **백엔드 모듈 하나 + 프론트엔드
feature 하나**를 더한다. 새 서비스를 만들지 않는 이유가 둘이다 — 원칙 VIII(호스트 포트 최소,
프론트와 API 같은 오리진)이고, 바이브코딩이 "선택 상태 + 에이전트"가 같은 런타임에 있어야
성립하기 때문이다(AD-7).

`modules/board/` 는 **`ontology_runtime` 도 `neo4j` 도 import 하지 않는다.** 같은 저장소 안에
있으면서도 MCP 를 통해서만 말한다. 이 규율은 사람이 지키지 못하므로
`test_no_direct_graph_access.py` 가 AST 로 강제한다 —
`ontology_runtime/test_no_sqlite_dependency.py` 가 같은 이유로 이미 존재한다.

## Complexity Tracking

> Constitution Check 위반 없음 — 비어 있다.

## Phase 2 미리보기 (범위 밖, `/speckit-tasks` 가 만든다)

작업 순서의 제약만 적어 둔다. 앞의 것이 없으면 뒤의 것을 검증할 수 없다.

1. `mcp_client` + `scripts/probe_board_mcp.py` — **계약을 먼저 고정**한다
2. `profile` (count + 샘플/JIT, 캐시)
3. `widget_map` (O1~O10) — 순수 함수라 단위 테스트가 쉽다
4. `query_gen` (집계 승격 포함)
5. `api` + 차트 래퍼 이식 + `BoardCanvas` → **첫 영상 증거**
6. `WidgetInspector` → 영상 증거
7. `spec_store` + 저장/열기
8. `dashboard` 모드 + 스킬 → 영상 증거
9. `superset_export`

**선행 결함 없음** — 006 이 안고 있던 잘림 신호 결함(CR-3)은 MCP 경로에서는 `truncated` 플래그와
별도 `count()` 로 우회 가능하므로 이 기능의 선행 작업이 아니다.
