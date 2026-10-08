# Phase 0 — 연구와 결정

**Feature**: 011-ontology-board · **Date**: 2026-08-19

스펙의 `[NEEDS CLARIFICATION]` 과 `## 미결정 사항` 을 실측·코드 확인으로 닫는다.
닫지 못한 것은 그대로 열어 두고 왜 닫지 못했는지 적는다.

---

## R-1. MCP 클라이언트를 무엇으로 구현하는가

**Decision**: `mcp` 파이썬 SDK 의 `ClientSession` + `streamablehttp_client` / `stdio_client`.
전송 방식은 설정으로 고른다.

**Rationale**: 이미 설치돼 있고(**mcp 1.28.1**, `pyproject.toml` 의 `mcp>=1.2.0`) 두 전송이
모두 import 된다 — 실측 확인:

```
mcp 1.28.1
from mcp.client.streamable_http import streamablehttp_client   ✓
from mcp.client.stdio import stdio_client                       ✓
from mcp import ClientSession                                   ✓
```

같은 코드가 로컬 stdio(OSS)와 원격 HTTP(Enterprise 중앙 엔드포인트)에 붙는다 — 기획서 §3 의
"OSS→Enterprise 전환이 설정 변경" 이 여기서 성립한다.

**Alternatives considered**:
- `runtime_adapters` 직접 호출 (in-process). **기각** — FR-001 위반이고, 원격 MCP 로 갈 때
  코드가 갈라진다. `agent_bridge_mcp` 가 in-process 마운트를 쓰는 것은 *자기 프로세스의 도구*를
  노출하기 때문이고, 여기는 *남의 서버*를 소비하는 반대 방향이다.
- 직접 HTTP/JSON-RPC 조립. **기각** — 프로토콜 협상·세션 수명·알림을 다시 구현하게 된다.

---

## R-2. 프로파일 캐시 무효화 기준 (스펙 FR-014 · U-5)

**Decision**: 캐시 키는 **`(schema_id, published_at)`**. `published_at` 이 바뀌면 그 모델의
프로파일 전체를 버린다. 여기에 사용자용 **수동 새로고침**을 둔다. TTL 은 두지 않는다.

**Rationale**: `_OntologyModel` 이 `published_at` 을 갖는다 — 실측:

```json
{"schema_id": "a0edf61cc416", "name": "제조 하이브리드",
 "format_version": 1, "published_at": 1786947759.0137112}
```

발행은 멱등이고 재발행마다 이 값이 갱신되므로, **모델이 바뀌는 유일한 경로가 곧 무효화 신호**다.
TTL 은 두 방향으로 틀린다 — 모델이 안 바뀌었는데 다시 프로파일링하거나(비용), 바뀌었는데
TTL 이 남아 옛 타입을 쓴다(오류).

**남는 구멍**: 모델은 그대로인데 **인스턴스가 늘어나는** 경우. 카디널리티·분포가 달라져도
캐시가 살아 있다. 그래서 수동 새로고침을 함께 둔다. 자동 감지는 매번 `count()` 를 던져야 하므로
v1 범위 밖이다.

**Alternatives considered**: TTL(위 이유로 기각) · 매 조회 프로파일링(위젯당 최소 2회 왕복 추가,
기각) · 그래프 변경 알림 구독(MCP 표면에 그런 것이 없다).

---

## R-3. 지도용 GeoJSON 은 어디서 오는가 (스펙 U-4)

**Decision**: **이미 레포에 있다.** `robo-data-frontend/src/assets/geo/korea.json` 을
차트 래퍼와 함께 이식한다. 배경 경계는 그것으로 그리고, **선로·구역 형상은 온톨로지 속성값의
GeoJSON 을 그대로** 쓴다.

**Rationale**: 실측한 파일의 실체:

| 항목 | 값 |
|---|---|
| 크기 | **5.0 KB** |
| features | **17** (시도 단위) |
| properties | `{name, code}` — `서울특별시`, `부산광역시` … |
| geometry | 전부 `Polygon` |
| 사용 방식 | `echarts.registerMap('korea', koreaGeoJson)` ↳ `MapChart.vue:283` |

**타일 서버를 쓰지 않는다는 AD-5 가 이미 동작하는 코드로 존재한다.** 번들 비용 5KB 는 논의할
크기가 아니다.

**한계 (기록)**: 17개 시도는 매우 단순화된 경계다. 5KB 에 폴리곤 17개면 정점이 성기다는 뜻이다.
**시군구 단위 정전 구역(O6)에는 부족하다.** 그 경우 배경 없이 형상만 그리거나, 사용자가 준
GeoJSON 을 설정으로 등록하는 경로가 필요하다 — v1 은 배경 없이 형상만 그리는 것으로 성립시키고
사용자 GeoJSON 등록은 범위 밖으로 둔다.

**Alternatives considered**: 외부 타일 서버(006 R12 가 기각한 사유 그대로 기각) ·
행정경계 전체 번들(라이선스·용량 미확인, v1 불필요).

---

## R-4. 그리드 레이아웃 라이브러리

**Decision**: **gridstack.js**.

**Rationale**: 레포 전체(`package.json` 8개)에 그리드 라이브러리가 **0건**이므로 선례가 없다.
선택 기준 둘:

- **레이아웃 직렬화가 1급이어야 한다.** `DashboardSpec.layout` 이 정본이므로(AD-6),
  `save()` 로 `{x,y,w,h}` 를 그대로 내는 것이 필요하다. gridstack 이 이것을 API 로 갖는다.
- **Vue 버전에 결합되지 않아야 한다.** gridstack 은 프레임워크 무관이라 Vue 3.5 / Vite 8
  조합에 얹는 데 어댑터 레이어가 필요 없다.

**Alternatives considered**:
- `grid-layout-plus` (vue-grid-layout 의 Vue3 포트). Vue 컴포넌트라 통합은 더 매끄럽지만
  Vue 메이저 전환마다 상류를 기다려야 한다. 이 제품은 데스크톱 패키징 대상이라 상류 대기가 비싸다.
- `vuedraggable` (`data-platform-olap` 에 유일하게 있는 것). **정렬**용이지 **격자 배치**용이
  아니다 — 크기 조절이 없다.

---

## R-5. ECharts 이식 범위와 방식

**Decision**: `robo-data-frontend/src/shared/charts/` 의 **6파일 1,055줄을 그대로 이식**하고,
새 의존성은 **`echarts` 하나만** 추가한다. `<script setup lang="ts">` 는 **그대로 둔다.**

**Rationale**: 실측한 사실 셋.

1. 대상 파일과 규모 — `ChartRenderer.vue`(113) · `BarChart.vue`(192) · `LineChart.vue`(214) ·
   `PieChart.vue`(188) · `MapChart.vue`(329) · `index.ts`(19).
2. **`vue-echarts` 를 쓰지 않는다.** 전부 `import * as echarts from 'echarts'` 로 raw ECharts 를
   직접 다룬다(`shallowRef` + `onMounted`/`onUnmounted` + resize 핸들러). 따라서 이식에
   `vue-echarts` 가 필요 없다 — 신규 의존성이 하나 줄어든다.
3. **`lang="ts"` 를 벗길 필요가 없다.** studio 프론트는 `@vitejs/plugin-vue ^6.0.5` + `vite ^8`
   이고, Vite 는 esbuild 로 타입을 벗겨 낸다. **타입 체크는 하지 않지만 빌드는 된다.**
   `vue-tsc` 를 도입하지 않는 한 TypeScript 를 의존성으로 추가할 필요가 없다.

따라서 프론트 신규 의존성은 **`echarts` + `gridstack` 둘뿐**이다 (CR-8 의 현재 3개 → 5개).

**Alternatives considered**: 새로 작성(1,055줄을 다시 쓸 이유가 없다) · `vue-echarts` 도입
(래퍼가 이미 수명주기를 다루므로 중복) · `lang="ts"` 제거(불필요한 diff 를 만들고 상류와의
대조가 어려워진다).

**기록해 둘 위험**: 이식본과 원본이 갈라진다. **동기화하지 않는다**는 것을 명시하고, 이식 시점의
원본 커밋을 이식 파일 헤더에 적는다.

---

## R-6. `domain-layer` 의 `chartConfig` 를 재사용할 수 있는가 (스펙 U-6 · CR-9)

**Decision**: **재사용하지 않는다.** 두 겹의 이유로 불가능하다.

**Rationale**:

1. **다른 온톨로지 표현이다.** `chartConfig` 는 `(:Table:ObjectType)` 노드의 속성으로 저장된다
   (`domain-layer/app/routers/ontology.py:1677`, `:1695`, `:1622` `ChartConfigModel`).
   이것은 domain-layer 의 온톨로지이고 `_Ontology*` 발행 레지스트리와 별개다 — 둘의 통합은
   spec 010 이 Out of Scope 로, spec 008 의 문제로 넘겼다.
2. **MCP 표면으로 읽을 수조차 없다.** `:Table` 은 `BLOCKED_LABELS` 에 있어
   `ontology_graph_cypher` 가 거부한다 (`runtime_adapters.py:34`). FR-001(도구만 사용)을 지키는
   한 이 노드에 닿는 경로가 없다.

**따라서 U-6 은 닫힌다** — 스펙의 "미검증" 표시를 해제하고 이 결론으로 대체한다.

**Alternatives considered**: MCP 게이트에 예외를 뚫는다. **기각** — `:Table` 은 데이터 패브릭
카탈로그 라벨이고 그 예외는 카탈로그 전체를 여는 것과 같다.

---

## R-7. "스튜디오 없이 동작한다"는 주장의 정확한 범위 (스펙 SC-001 수정)

**문제**: 스펙 SC-001 이 *"스튜디오 백엔드를 끈 상태에서 대시보드를 만들고 열 수 있다"* 라고
썼는데, 보드 API 는 스튜디오 백엔드 프로세스 안의 모듈이고(원칙 VIII — 프론트와 API 는 같은
오리진) 프론트도 그 백엔드가 서빙한다. **그 상태로는 성립할 수 없는 주장이다.**

**Decision**: 주장을 정확한 것으로 바꾼다 —
**"스튜디오의 모델링 원천(SQLite)이 비어 있거나 없어도 동작한다."**

**Rationale**: 실제로 지켜야 하는 독립성은 *프로세스* 가 아니라 *데이터 원천* 이다. spec 010 이
`test_no_sqlite_dependency.py` 로 강제한 것도 그것이고, 워크스루가
`SESSION_DB_PATH=/nonexistent/none.db` 로 시험한 것도 그것이다. 이 독립성이 지켜지면 **발행물만
받은 런타임 서버**에서 대시보드가 돈다 — 그것이 Enterprise 배포 형태다.

MCP 서버 쪽은 별개 프로세스이므로 원래대로 스튜디오 없이 돈다(CR-1 에서 실측: 8010 이 닫힌
상태에서 9개 클래스를 읽었다).

**스펙 반영**: SC-001 문구 교체 + `## Assumptions` 에 한 줄 추가.

---

## R-8. 테스트 방법

**Decision**: 백엔드는 `uv run --with pytest pytest`, import 금지 규칙은 **AST 검사 테스트**로
강제한다. 프론트는 기존 Playwright 파이프라인.

**Rationale**:
- pytest 는 선언된 의존성이 아니지만 `uv run --with pytest` 로 동작한다 (실측: pytest 9.1.1).
  기존 테스트 트리는 `backend/tests/{modules,shared}/`.
- FR-002 가 요구하는 import 금지는 **베낄 원본이 있다** —
  `backend/tests/modules/ontology_runtime/test_no_sqlite_dependency.py` 가 `ast.walk` 로
  import 그래프를 검사한다. 그 파일의 주석이 이유를 정확히 적어 뒀다:
  > 규율로는 유지되지 않는다. … 그때 나타나는 증상은 "온톨로지가 비어 있다"라서 원인을 짚기 어렵다.

  보드용 금지 목록은 `("neo4j", "ontology_runtime", "session_store", "agent_session",
  "ontology.tools", "ontology.datasource_exec")` 가 된다.

---

## 남은 미결정 (닫지 못한 것)

| | 내용 | 왜 닫지 못했나 |
|---|---|---|
| **U-1** | `ontology_get_class_profile` MCP 도구화 | spec 010 FR-016(플래그 off 시 도구 정확히 4개) 개정을 수반한다. v1 은 AD-4 로 우회하므로 **지금 결정할 필요가 없다** — 우회의 비용(프로파일링 왕복)이 실측된 뒤에 판단한다 |
| **U-2** | `ontology_graph_cypher` 의 per-call `limit` | 같은 이유. AD-10 의 집계 승격이 실제로 몇 %를 흡수하는지 본 뒤에 판단한다 |
| **U-3** | Cypher 경로 `row_count` 가 참값이 아닌 것 | 별도 `count()` 로 우회 가능(실측 확인)하므로 v1 은 우회한다. 다른 소비자도 같은 함정에 빠지므로 **결함으로 등록하되 이 스펙에서 고치지 않는다** |
| **신규** | 시군구 단위 배경 지도 | R-3 의 한계. 사용자 GeoJSON 등록 경로가 필요하나 v1 범위 밖 |

**U-1·U-2·U-3 은 셋 다 spec 010 의 표면에 관한 것이다.** 한꺼번에 다루는 것이 옳고, 그
근거는 이 기능의 실측치여야 한다. 그래서 v1 구현 후 재검토로 미룬다.
