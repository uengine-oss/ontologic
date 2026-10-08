# Feature Specification: 온톨로지 객체 기반 대시보드 빌더

**Feature Branch**: `011-ontology-board`

**Created**: 2026-08-19

**Status**: Draft

**Input**: 연구 보고서 *"발전 및 송배전 도메인 특화 아파치 슈퍼셋 위젯-객체 유형 AI 자동 매핑
체계 및 매핑 테이블"* · 제품 결정 [`docs/business/ontology-board-product.md`](../../docs/business/ontology-board-product.md)

## 관계

[010](../010-graph-published-ontology-mcp/spec.md) 이 **모델을 그래프에 발행하고 스튜디오 없이
읽는 MCP 표면**을 만들었다. [`docs/agentic-rag-walkthrough.md`](../../docs/agentic-rag-walkthrough.md)
는 그 표면만으로 에이전트가 그래프 탐색 → JIT 스키마 → DB 집계를 스스로 밟는 것을 기록했다.

이 스펙은 **그 호출 순서를 LLM 이 아니라 코드가 밟게 한다.** 결과가 대시보드다.

[006](../006-visualization-and-report/spec.md) 과의 경계는 분명하다.

| | 006 | **011 (이 스펙)** |
|---|---|---|
| 계기 | 질의 결과가 나왔다 | 사용자가 객체를 캔버스에 놓았다 |
| 수명 | 세션 한정 | 저장되는 문서 |
| 데이터 접근 | 스튜디오 백엔드 내부 도구 계층 | **MCP 표면** (스튜디오 미의존) |
| 차트 규칙 | R1~R13 (결과 형태) | **R1~R13 승계 + O1~O10** (객체 유형) |
| 지도 | R12 — 범위 밖 | **1급** (AD-5) |

006 이 `## Out of Scope` 로 명시한 *"대시보드 저장·공유 / 드릴다운 / BI 커넥터"* 가 이 스펙의
본문이다. **006 의 규칙표를 다시 정의하지 않고 참조한다.**

[001](../001-datasource-backed-virtual-classes/spec.md) 의 가상 클래스 계약(SQL 안전성·기밀
유지·인스턴스 0건)은 MCP 표면을 통해 **자동으로** 상속된다 — 이 스펙이 다시 규정하지 않는다.

## 왜 이 스펙이 플랫폼 단위인가

되돌리면 계약이 깨지는 것이 셋이다.

- **MCP 표면의 소비 계약.** 이 제품은 `ontology_mcp` 의 응답 형태에 의존한다. 그 서버는
  `ontology-studio` 에 있고, 행 상한은 루트 `.env` 가 정하며, SQL 실행은 `neo4j-text2sql` 이
  한다. 한 저장소만 되돌려도 대시보드가 빈 화면이 된다.
- **에이전트 모드 목록.** `dashboard` 모드가 `agent_bridge_mcp` 의 `_MODES` 에 추가된다.
  spec 004 FR-012 가 규정한 "모드별 엔드포인트 분리"의 확장이다.
- **행 예산 설정의 의미.** `MCP_MAX_RESULTS` · `DATASOURCE_AGENT_ROW_PREVIEW` 가 지금은
  "에이전트 컨텍스트 보호"만 뜻하지만, 이 스펙 이후 **위젯이 그릴 수 있는 점의 개수**가 된다.
  루트 `.env` 키의 의미가 바뀌므로 `specs/README.md` 기준으로 이곳에 속한다.

---

## 현재 코드 현실 — 조사 결과

**2026-08-19, `제조 하이브리드` (클래스 9개·가상 4개·관계 10개, Neo4j `bolt://localhost:7688`)
에서 실행해 확인한 것만 적었다.** 확인하지 못한 것은 그렇게 표시하고 §미결정으로 내렸다.

### CR-1. 발행된 모델은 실제로 스튜디오 없이 읽힌다

`published_models()` → 1건(`제조 하이브리드`, `format_version: 1`), `list_classes()` → 9건
(가상 4 / materialized 5), `list_relationships()` → 10건. 스튜디오 백엔드(8010)는 **꺼져 있었다.**

`probe_graph_schema_api.py` 판정: **분기 A — 인스턴스 없이 발행 가능.** 제약만으로 라벨이
`db.labels()` 에 노출되고, `apoc.meta.schema()` 에는 노출되지 않는다(계약이 배제한 이유 그대로).

### CR-2. `graph://schema` 는 속성 **이름**만 준다 — 타입이 없다

`MfgProduct`(materialized) 엔트리 원문:

```json
{"class_name": "MfgProduct", "binding_kind": "materialized",
 "property_names": ["created_date","is_active","lead_time_days","min_order_qty",
                    "product_category","product_id","product_name","unit_cost","unit_price"],
 "property_source": "graph_schema_api", "native": true, "native_key": ["product_id"],
 "behavior_count": 0}
```

↳ `ontology-studio/backend/src/modules/ontology_runtime/graph_schema.py:294-315`
(`column_map` 을 싣지 않는다는 주석이 `:258-260` 에 있다)

가상 클래스는 `property_source: "published_registry"`, materialized 는 `"graph_schema_api"` 로
갈렸다 — 후자는 인스턴스 샘플링, 전자는 레지스트리다.

**타입을 주는 유일한 도구 `ontology_get_datasource_schema` 는 가상 클래스 전용이다.** 바인딩이
없으면 *"binding_kind 가 virtual 인 클래스를 고르세요"* 로 거절한다.
↳ `ontology_mcp/runtime_adapters.py:346-350`

**이것이 이 스펙의 첫 번째 제약이다.** 사용자가 고른 기본 경로가 Neo4j(materialized) 모드인데,
위젯 매핑은 타입이 있어야 성립한다.

### CR-3. 노드를 통째로 RETURN 하면 속성이 전부 온다 — 타입 추론의 재료

```
MATCH (n:_Entity:MfgProduct) RETURN n LIMIT 2
→ rows[0]["n"] 의 키 9개 = property_names 와 일치
```

constitution 원칙 0 이 `properties(n)` 대신 명시한 형태가 **"노드를 통째로 RETURN"** 이고,
`n[k]` 동적 접근 대신 **"선언된 속성명으로 정적 접근"** 이다. `property_names` 가 있으므로
집계 질의도 정적으로 조립할 수 있다. ↳ `.specify/memory/constitution.md:113-114`

### CR-4. `_datasource_refs` 는 신뢰할 수 있다 — 응답 최상단에 항상 붙는다

```json
{"from_class": "MfgProduct", "class": "MfgDailyQualityIssue",
 "datasource": "legacy", "schema": "manufacturing", "table": "mfg_daily_quality_issue",
 "via_relationship": "REFERENCES_MFG_PRODUCT", "join_on": "product_id = product_id"}
```

워크스루 §결함② 가 *"대부분 붙지도 않았다"* 고 적은 것은 **행 단위** 주석이고, 그것은 노드를
통째로 RETURN 했을 때만 붙는다. 수정 후 **질의가 언급한 라벨**에서 뽑아 응답 최상단에도 싣는다.
발행된 관계 10개가 모두 `join` 속성을 갖고 있어 `join_on` 이 채워진다.
↳ `runtime_adapters.py:164-208`, `:283-300`

응답 최상단 키: `rows`, `row_count`, `truncated`, `_datasource_refs`, `_datasource_hint`.

### CR-5. **행 예산이 에이전트 기준이다 — 두 경로가 서로 다르게 잘린다**

| 경로 | 실제 존재 | 요청 | **반환** | `row_count` | 상한 |
|---|---|---|---|---|---|
| `ontology_graph_cypher` | 33 (`MfgProductBom`) | 제한 인자 **없음** | **20** | **20 — 참값 아님** | `MCP_MAX_RESULTS` 기본 **20** |
| `ontology_query_datasource_sql` | 3,510 | `limit=200` | **30** | 200 (참값) | `DATASOURCE_AGENT_ROW_PREVIEW` 기본 **30** |

↳ `shared/kernel/settings.py:195`, `:217` · 적용부 `runtime_adapters.py:259-265`, `:425-433`

**Cypher 경로는 잘린 양을 알려주지 않는다.** `row_count` 가 잘린 뒤의 수여서 호출자는 "20건이
전부"인지 "33건 중 20건"인지 구분할 수 없다. `truncated: true` 플래그만 있다. 이것은 006 CR-3 이
지적한 결함과 같은 종류가 MCP 표면에서 반복되는 것이다.

**다만 `count()` 질의는 1행이라 상한과 무관하다** — `RETURN count(n)` 로 33·55·8·15·10 을
정확히 받았다. 총계를 아는 경로가 있다.

### CR-6. Cypher 게이트가 `CALL` 과 **문자열 리터럴**까지 막는다

- `_WRITE_CLAUSE_PATTERN` 에 `CALL` 이 포함된다 → `CALL {}` 서브쿼리·APOC 전부 불가
- `_blocked_label_used()` 는 `:Label` 뿐 아니라 `'Label'` / `"Label"` **문자열 비교도** 막는다
  (`MATCH (n) WHERE 'DataSource' IN labels(n)` 우회 차단이 목적)

↳ `runtime_adapters.py:47-53`, `:55-68`

**부작용**: 필터 값이 우연히 `Table` · `Column` · `Schema` · `DataSource` 와 같으면 인라인
리터럴로 쓰는 순간 질의가 거부된다. 대시보드 필터는 **반드시 `params` 로** 넘겨야 한다.

### CR-7. 쓰기 도구를 `ontology_mcp` 에 올리면 안 된다 — spec 004 가 명시적으로 금지한다

> **FR-013**: 이 서버는 기존 읽기 전용 검색 서버(`ontology_mcp`)와 **별개**여야 한다.
> 그 서버의 보안 경계를 넓히면 안 된다.

↳ `specs/004-pluggable-agent-backend/spec.md:133-134`

그리고 확장 지점은 이미 있다 — `agent_bridge_mcp` 가 **모드마다 별도 엔드포인트**를 마운트한다:

```python
_MODES = ("build", "answer", "answer_nods", "brief_draft")
```
↳ `agent_bridge_mcp/router.py:14` · 도구 선택 `agent_bridge_mcp/server.py:31-41`

### CR-8. 프론트엔드에 차트도 그리드도 없다

`ontology-studio/frontend/package.json` 의 런타임 의존성은 `cytoscape` · `marked` · `vue` **셋뿐**
이다. 그리고 레포 전체(8개 `package.json`)에서 `gridstack|vue-grid-layout|react-grid-layout|
golden-layout|interactjs` 는 **0건**, `vuedraggable` 만 `data-platform-olap` 에 1건 있다.

반면 `robo-data-frontend` 에는 이식 가능한 자산이 있다 — `echarts ^6.0.0` + `vue-echarts ^8.0.1`
기반의 `shared/charts/ChartRenderer.vue`(타입 디스패치) + `Bar/Line/Pie/MapChart.vue`,
그리고 ObjectType 의 컬럼→축 매핑 위지윅 편집기 `domains/ontology/ui/modeling/ChartConfigTab.vue`.

### CR-9. 대시보드·위젯·레이아웃을 저장하는 모델이 어디에도 없다

`data-platform-olap` 은 큐브 메타데이터를 JSON 파일로 덤프하고(`data/cubes.json`), ORM 도
테이블도 없다. `domain-layer` 는 `:Table:ObjectType` 노드에 `chartConfig` 를 JSON 문자열로
붙이는 경로가 있으나(`PATCH /object-types/{name}/chart-config`), 그것은 **domain-layer 의 다른
온톨로지 표현**이고 `_Ontology*` 발행 레지스트리와 별개다(spec 010 Out of Scope).

**결론 (research R-6)**: **재사용하지 않는다.** 이유가 두 겹이다. ① 다른 온톨로지 표현이고
(`domain-layer/app/routers/ontology.py:1677`), 두 표현의 통합은 spec 008 의 문제다.
② `:Table` 은 `BLOCKED_LABELS` 에 있어 **MCP 표면으로 읽을 수조차 없다**
(`runtime_adapters.py:34`). FR-001 을 지키는 한 닿을 경로가 없다.

---

## 아키텍처 결정

결정과 그 근거는 [`docs/business/ontology-board-product.md`](../../docs/business/ontology-board-product.md) §8
에 있다. 여기서는 요구사항이 걸리는 지점만 재진술한다.

| | 결정 |
|---|---|
| **AD-1** | 애플리케이션은 **MCP 클라이언트**. Neo4j 드라이버·DB 커넥션을 갖지 않는다 |
| **AD-2** | 위젯 선택은 결정적. LLM 은 문구·순서·라벨 제안에만 |
| **AD-3** | 집계는 서버(Cypher/SQL)가. 클라이언트 재집계 금지 |
| **AD-4** | materialized 클래스의 타입은 **노드 통째 RETURN 후 값 추론** (CR-2·CR-3) |
| **AD-5** | 지도는 **타일 없이** ECharts `geo` + GeoJSON `registerMap` |
| **AD-6** | 정본은 텍스트 `DashboardSpec`. 자격증명 0 |
| **AD-7** | 프론트는 ontology-studio 안. 차트 래퍼는 robo-data-frontend 에서 이식 (CR-8) |
| **AD-8** | 읽기는 `ontology_mcp`, 쓰기는 **agent-bridge MCP 의 새 `dashboard` 모드** (CR-7) |
| **AD-9** | Superset 은 내보내기 타깃. **가상 클래스 위젯에서만** 성립 |
| **AD-10** | 행 예산은 ① 집계로 흡수 ② 총계는 별도 `count()` ③ 부족하면 전용 MCP 프로파일 (CR-5) |
| **AD-11** | 전역 필터와 교차 필터는 **발행된 관계의 `join` 속성**으로 푼다. 한 홉만 본다 |
| **AD-12** | 자연어 편집은 `AGENT_BACKEND` 가 고른다 — **CLI 에이전트가 기본**, API 키는 대체 경로 |
| **AD-13** | 자동 구성에서도 **위젯 종류는 엔진이** 정한다. 에이전트는 선택·순서·제목만 |
| **AD-14** | 진입점은 **갤러리**다. 편집 화면은 대시보드를 고른 뒤에 온다 |

### AD-13 — 자동 구성의 분업

골든 퀘스천은 **무엇을 보고 싶은가**를 담고 있고 그것은 데이터의 모양에서 나오지 않는다.
그러니 여기에는 에이전트가 필요하다. 그러나 **위젯 종류까지 맡기면 결정성이 깨진다.**

| 누가 | 무엇을 정하는가 |
|---|---|
| 에이전트 | 어떤 클래스를 담을지 · 순서 · 대시보드 제목 · 위젯 제목 |
| 엔진 | 위젯 종류 · 축 · 지표 · 시간 입도 (O/R 규칙) |
| 결정적 코드 | 배치(2열) · 전역 필터 후보(관계로 2개 이상 위젯에 닿는 속성) |

자연어 편집에서 이미 같은 문제를 겪었다 — 실측에서 에이전트가 도구를 못 쓰자 위젯 종류를
스스로 골랐고, 그래서 `_engine_owns_widget_kind` 로 **구조로** 막았다. 자동 구성은 애초에
클래스 이름만 받는다.

### AD-14 — 갤러리가 먼저다

지금까지 「대시보드」를 누르면 빈 편집 화면이 떴다. 저장한 것이 여러 개가 되는 순간 그 화면은
길을 잃는다 — 무엇을 열지 고를 곳이 없다. 갤러리 → 편집 순서로 바꾸고, 새 대시보드를 만들 때
**두 경로를 나란히** 보인다: 끌어다 놓기(직접)와 대화(자동 구성).

---

## 객체 유형 판정 규칙

### 1단계 — 속성 역할 판정

**006 의 1단계를 그대로 승계한다.** 타입 출처 우선순위만 이 스펙의 사실로 교체한다:

| 순위 | 출처 | 적용 대상 |
|---|---|---|
| 1 | `ontology_get_datasource_schema` 의 `column_map[].type` | 가상 클래스 |
| 2 | 노드 통째 RETURN 샘플의 **값 기반 추론** | materialized 클래스 (AD-4) |
| 3 | 추론 불가 | `unknown` — 차트에 쓰지 않는다 |

`identifier` 판정에는 `native_key` · `key_columns` · `column_map[].reference` · 006 의
`_FK_SUFFIXES` 를 쓴다.

### 2단계 — 가드

**006 의 G1~G6 을 그대로 승계한다.** 다음 둘을 더한다:

| 가드 | 조건 | 동작 |
|---|---|---|
| **G7** | 총계(별도 `count()`) 대비 반환 행이 잘렸고 후보가 시계열 | 집계 승격을 시도하고, 그래도 잘리면 **차트 없음 + 표** (006 G3 과 같은 정신) |
| **G8** | 클래스가 가상인데 `MCP_ALLOW_DATASOURCE_EXPANSION` 이 꺼져 있다 | 위젯 없음 + *"데이터소스 확장이 꺼져 있습니다"* 를 그대로 표시 |

### 3단계 — 객체 유형표 (위에서부터 첫 번째로 맞는 것 하나)

`T`=temporal, `N`=numeric, `C`=categorical, `k(C)`=고유값 개수, `I`=인스턴스 수.

| # | 조건 | 위젯 | 근거 |
|---|---|---|---|
| **O1** | `T`=1 · `N`≥1 · `I`≥3 | `timeseries_line` | 시간은 순서 있는 연속 축 |
| **O2** | `C`=1 · `N`=1 · `N` 의 고유값 ≥ 4×k(C) | `box_plot` | 분포를 볼 만큼 값이 흩어져 있다 |
| **O3** | `C`≥2 이고 카디널리티 단조 증가, **또는** 자기참조 관계 존재 | `treemap` (k 총곱 ≤ 400) / `sunburst` | `groupby` 순서 = 카디널리티 오름차순 |
| **O4** | 위·경도 속성 쌍 (이름 패턴 + 값 범위 ±90/±180) | `geo_point` | |
| **O5** | GeoJSON `LineString` 또는 WKT `LINESTRING` | `geo_path` | |
| **O6** | GeoJSON `Polygon`/`MultiPolygon` | `geo_polygon` | |
| **O7** | `string` 평균 길이 > 40 이고 고유값 ≈ `I` | `word_cloud` + `table` | 자유 텍스트 |
| **O8** | `C`=2 (각 k ≤ 15) · `N`=1 | `heatmap` (k≤15) / `pivot_table` | 006 R9 의 15×15 한계 |
| **O9** | `I`=1 · `N` 1~6 · `C`=0 · `T`=0 | `kpi` / `kpi_group` | 006 R1·R2 |
| **O10** | 그 외 전부 | **`table`** | **폴백. 억지로 그리지 않는다** |

**적용 순서는 위 번호가 아니다.** 구현에서 실측한 결과 스펙 표 순서(O1→O10)가 틀렸다 —
변전소(위·경도 + 준공일)가 O1 로 떨어져 "준공일 추이" 가 되고, 송전선로(LineString +
전압)가 O3 트리맵이 됐다. **가장 구체적인 신호가 먼저다**: 형상 컬럼은 렌더링이 하나뿐이고
(O5·O6), 위·경도 쌍이 그 다음이며(O4), "날짜 컬럼이 있다"는 그보다 약하다 — 마스터
테이블도 준공일을 갖는다.

실제 순서: **O5 → O6 → O4 → O1 → O2 → O3 → O7 → O8 → O9 → R 티어 → O10.**
뒤로 밀린 규칙은 보조 위젯으로 함께 추천되므로 사라지지 않는다.
↳ `modules/board/widget_map.py` 의 `RULES`

O1~O10 중 어느 것에도 안 걸리면 **006 의 R1~R13 을 그 다음 순서로 적용한다.** 두 표는 경쟁하지
않는다 — O 는 객체(클래스) 축, R 은 결과(행) 축이다.

**한 클래스가 둘 이상을 만족하면 첫 번째를 주 위젯으로, 나머지를 보조 위젯으로 추천한다.**
보고서 §5-1 이 요구한 *"box_plot 보조 차트 병렬 자동 추천"* 이 여기서 나온다.

### 4단계 — 산출

`{widget_kind, rule: "O5", reason, fields, aggregation, truncation}` 을 낸다. `rule` 과
`reason` 은 **사용자에게 보인다** — 자동으로 정해진 위젯은 왜 그 모양인지 말할 수 있어야 한다.

---

## 데이터 계약

### ObjectProfile (파생 · 캐시 · 밖으로 나가지 않는다)

```
class_name, schema_name, binding_kind, instance_count(별도 count 질의),
properties: [{name, role, type, type_source, distinct_count, null_ratio,
              min, max, avg_length, sample_shape}]
```

### WidgetSpec (DashboardSpec 안에 저장된다)

```
id, class_name, schema_name, widget_kind, rule, reason,
dimensions: [property], measures: [{property, agg}], filters: [{property, op, param_key}],
time_grain, top_n, layout: {x, y, w, h}, title, options
```

**SQL 도 Cypher 도 담지 않는다.** 질의는 조회 시점에 `query_gen` 이 만든다.

### DashboardSpec (정본 · 텍스트)

```
format_version, name, description, model: {schema_id, schema_name},
widgets: [WidgetSpec], params: {key: default_value}, created_at, updated_at
```

**자격증명·접속정보·SQL 템플릿을 담지 않는다** — AD-1 덕분에 애초에 손에 넣을 수 없다.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 객체를 끌어다 놓으면 위젯이 된다 (Priority: P1)

**Why this priority**: 이것이 안 되면 나머지 전부가 무의미하다. 제품의 존재 이유다.

**Independent Test**: 발행된 온톨로지 하나만 있으면 된다. 스튜디오 백엔드는 꺼도 된다.

**Acceptance Scenarios**:

1. **Given** `제조 하이브리드` 가 발행돼 있고 MCP 만 떠 있을 때, **When** 팔레트에서
   `MfgProduct` 를 캔버스에 드롭하면, **Then** 위젯이 자동으로 정해져 그려지고 어떤 규칙이
   왜 발동했는지가 함께 보인다.
2. **Given** 클래스에 인스턴스가 0건일 때, **When** 드롭하면, **Then** 차트 대신 *"인스턴스가
   없습니다"* 가 보이고 가상 클래스면 그 사실을 밝힌다 (G2·가상 클래스 표시 규칙).
3. **Given** `MCP_ALLOW_DATASOURCE_EXPANSION` 이 꺼져 있을 때, **When** 가상 클래스를 드롭하면,
   **Then** 서버가 준 문구를 그대로 보여주고 위젯을 만들지 않는다 (G8).

### User Story 2 - 그려진 화면에서 클릭해 고친다 (Priority: P1)

**Why this priority**: "위지윅"의 실체. 이것이 없으면 자동 추천의 오차를 사용자가 고칠 방법이 없다.

**Acceptance Scenarios**:

1. **Given** 막대 차트가 그려져 있을 때, **When** X축 라벨을 클릭하면, **Then** 그 축의
   인스펙터가 열리고 다른 속성으로 바꿀 수 있다.
2. **Given** 위젯 종류를 수동으로 바꿨을 때, **When** 저장하면, **Then** 그 선택이
   `DashboardSpec` 에 남고 다음에 열 때 자동 추천이 그것을 덮어쓰지 않는다.

### User Story 3 - 말로 고친다 (Priority: P2)

**Acceptance Scenarios**:

1. **Given** 위젯 하나를 선택한 상태에서, **When** *"지역별로 쪼개줘"* 라고 하면, **Then**
   에이전트가 패치를 제안하고 **적용 전 diff 를 보여주며** 되돌릴 수 있다.
2. **Given** 에이전트가 존재하지 않는 속성을 참조하는 패치를 냈을 때, **When** 적용을 시도하면,
   **Then** 스키마 검증에서 거부되고 대시보드는 바뀌지 않는다.

### User Story 4 - 저장하고 다른 사람에게 준다 (Priority: P2)

**Acceptance Scenarios**:

1. **Given** 대시보드를 만들었을 때, **When** 저장하면, **Then** 텍스트 문서 하나가 나오고
   그 안에 접속정보도 SQL 도 없다.
2. **Given** 다른 인스턴스에서 그 문서를 열었을 때, **When** 참조하는 클래스가 발행돼 있지
   않으면, **Then** 어떤 위젯이 왜 못 그려지는지를 위젯별로 밝힌다.

### User Story 5 - Superset 으로 내보낸다 (Priority: P3)

**Acceptance Scenarios**:

1. **Given** 가상 클래스 위젯이 있을 때, **When** 내보내면, **Then** `viz_type` 과 `form_data`
   가 채워진 payload 가 나온다.
2. **Given** materialized 위젯이 섞여 있을 때, **When** 내보내면, **Then** 그 위젯은 제외되고
   **제외 사유가 위젯별로 표시된다** — 조용히 빠뜨리지 않는다.

### User Story 6 - 온톨로지를 만들면 대시보드가 따라온다 (Priority: P1)

**Why this priority**: 빈 캔버스는 진입 장벽이다. 모델을 만든 사람은 이미 **무엇을 보고
싶은지**를 골든 퀘스천으로 적었는데, 대시보드를 처음부터 다시 조립하게 하는 것은 그 정보를
버리는 것이다.

**Independent Test**: 골든 퀘스천이 있는 발행 모델 하나만 있으면 된다.

**Acceptance Scenarios**:

1. **Given** 골든 퀘스천이 적힌 모델이 발행돼 있을 때, **When** 「대시보드도 함께 생성」을
   누르면, **Then** 위젯이 배치된 대시보드가 만들어지고 갤러리에 나타난다.
2. **Given** 자동 구성이 도는 동안, **When** 화면을 보면, **Then** 어떤 클래스를 보고 있고
   무엇을 골랐는지가 **실행 로그로** 흐른다.
3. **Given** 어떤 클래스도 위젯이 되지 못했을 때, **When** 구성이 끝나면, **Then** 빈
   대시보드를 만드는 대신 **왜 만들지 못했는지**를 말한다.

### User Story 7 - 대시보드를 골라서 연다 (Priority: P2)

**Acceptance Scenarios**:

1. **Given** 저장된 대시보드가 여럿일 때, **When** 「대시보드」 메뉴에 들어가면, **Then**
   갤러리가 먼저 보이고 위젯 수·수정 시각이 함께 나온다.
2. **Given** 갤러리에서, **When** 「새 대시보드」를 누르면, **Then** 빈 편집 화면이 열리고
   **끌어다 놓기와 대화 두 경로**가 모두 제시된다.

### Edge Cases

- 발행된 모델이 0건 → 팔레트가 *"발행하세요"* 를 안내한다 (`graph://schema` 의 `note` 를 그대로)
- 같은 클래스명이 두 그룹에 있음 → `ambiguous` 응답을 그대로 노출하고 사용자가 고른다
- 필터 값이 `Table` · `Column` 등 차단 라벨과 같은 문자열 → `params` 로 넘겨 통과한다 (CR-6)
- 총계가 상한을 넘음 → 집계 승격 → 그래도 넘으면 배지 *"N건 중 M건"* (CR-5)
- 그래프가 ontological-db → `SHOW CONSTRAINTS` 등이 없어도 동작해야 한다 (원칙 0)

---

## Requirements *(mandatory)*

### Functional Requirements — MCP 소비

- **FR-001**: 대시보드 백엔드는 온톨로지와 데이터를 **MCP 도구 호출로만** 얻어야 한다.
  Neo4j 드라이버·DB 드라이버·`ontology_runtime` 을 직접 import 해서는 안 된다.
- **FR-002**: 그 금지는 **테스트로 강제되어야 한다** — spec 010 의
  `test_no_sqlite_dependency.py` 와 같은 방식의 import 금지 테스트.
- **FR-003**: MCP 엔드포인트(전송 방식·주소·토큰)는 설정으로 교체 가능해야 한다. 로컬 stdio 와
  원격 HTTP 가 같은 코드로 동작해야 한다.
- **FR-004**: `MCP_ALLOW_DATASOURCE_EXPANSION` 이 꺼져 있으면 가상 클래스 위젯을 만들 수 없다는
  것을 **UI 가 밝혀야 한다.** 빈 차트로 두어서는 안 된다.
- **FR-005**: MCP 가 반환한 오류 문구는 **가공하지 않고 그대로** 사용자에게 보여야 한다.

### Functional Requirements — 객체 프로파일링

- **FR-010**: materialized 클래스의 속성 타입은 **노드를 통째로 RETURN 한 샘플의 값**에서
  추론해야 한다. `properties(n)` 과 동적 `n[k]` 접근을 써서는 안 된다.
- **FR-011**: 가상 클래스의 속성 타입은 `ontology_get_datasource_schema` 의 `column_map[].type`
  에서 와야 한다. 값 추론을 우선해서는 안 된다.
- **FR-012**: 프로파일은 **타입의 출처**(`type_source`)를 함께 담아야 한다. 추론인지 선언인지
  구분되지 않으면 오판의 원인을 짚을 수 없다.
- **FR-013**: 인스턴스 총계는 **별도 `count()` 질의**로 얻어야 한다. 반환 행 수를 총계로
  삼아서는 안 된다 (CR-5).
- **FR-014**: 프로파일은 캐시되어야 하며, 캐시 키는 **`(schema_id, published_at)`** 이어야 한다.
  재발행이 유일한 모델 변경 경로이므로 그것이 곧 무효화 신호다. TTL 을 쓰지 않는다.
  인스턴스 증가는 이 신호로 잡히지 않으므로 **수동 새로고침**을 함께 제공해야 한다 (research R-2).

### Functional Requirements — 위젯 자동 매핑

- **FR-020**: 위젯 선택은 **결정적**이어야 한다. 같은 프로파일은 항상 같은 위젯을 낸다.
  LLM 에 위젯 종류를 묻지 않는다.
- **FR-021**: 006 의 속성 역할 판정·가드 G1~G6·규칙 R1~R13 을 **재정의하지 않고 재사용**해야 한다.
- **FR-022**: 어느 규칙이 왜 발동했는지(`rule`, `reason`)를 **사용자에게** 노출해야 한다.
- **FR-023**: 어떤 규칙에도 걸리지 않으면 **표**로 폴백해야 한다. 억지로 차트를 그려서는 안 된다.
- **FR-024**: 한 클래스가 둘 이상의 객체 유형을 만족하면 **보조 위젯으로 함께 추천**해야 한다.
- **FR-025**: 계층(`O3`)의 `groupby` 순서는 **카디널리티 오름차순으로 자동 결정**되어야 한다.

### Functional Requirements — 질의 생성과 행 예산

- **FR-030**: 집계는 서버가 해야 한다. 행을 가져와 클라이언트에서 평균·합계를 계산해서는 안 된다.
- **FR-031**: 생성된 Cypher 에 `CALL` 이 포함되어서는 안 된다 (게이트가 거부한다 — CR-6).
- **FR-032**: 필터 값은 **`params` 로** 전달해야 한다. 질의문에 인라인 리터럴로 넣어서는 안 된다.
- **FR-033**: 후보 결과가 행 상한을 넘으면 **집계를 먼저 승격**해야 한다 (시간 입도 상향,
  범주 상위 N + 기타).
- **FR-034**: 승격 후에도 잘리면 **"N건 중 M건" 배지를 반드시 병기**해야 한다. 잘렸다는 사실을
  숨기고 그려서는 안 된다.
- **FR-035**: 잘린 시계열은 **그리지 않고 표로 폴백**해야 한다 (G7 — 006 G3 과 같은 정신).
- **FR-036**: 생성된 질의는 **DashboardSpec 에 저장되지 않아야** 한다. 조회 시점에 만든다.

### Functional Requirements — 위지윅 편집

- **FR-040**: 팔레트에서 캔버스로의 드롭은 **검증된 페이로드 계약**을 통과해야 한다.
- **FR-041**: 그려진 차트의 요소(축·계열·범례)를 클릭하면 **그 요소의 인스펙터**가 열려야 한다.
- **FR-042**: 위젯의 위치·크기 변경이 `DashboardSpec.layout` 에 반영되어야 한다.
- **FR-043**: 사용자가 수동으로 정한 위젯 종류·축 매핑은 **자동 추천이 덮어쓰지 않아야** 한다.
- **FR-044**: 모든 편집은 **되돌릴 수 있어야** 한다.

### Functional Requirements — 바이브코딩

- **FR-050**: 에이전트는 `DashboardSpec` 의 **패치**만 낼 수 있어야 한다. 임의 코드 실행 도구
  (`execute`)를 이 모드에 올려서는 안 된다.
- **FR-051**: 패치는 **적용 전 스키마 검증**을 통과해야 하며, 존재하지 않는 클래스·속성을
  참조하면 거부되어야 한다.
- **FR-052**: 패치는 **적용 전 diff 로 제시**되어야 한다.
- **FR-053**: 쓰기 도구는 **`agent_bridge_mcp` 의 새 `dashboard` 모드**에 올려야 하며,
  읽기 전용 `ontology_mcp` 서버에 올려서는 안 된다 (spec 004 FR-013).
- **FR-054**: 내장 에이전트와 외부 에이전트는 **같은 함수 객체**를 써야 한다 (spec 004 FR-011).
- **FR-055**: 이 모드의 지시문은 `skills/dashboard-edit/SKILL.md` **하나**여야 한다.
  파이썬에서 프롬프트를 조립해서는 안 된다 (spec 005).
- **FR-056**: 실행 주체는 `AGENT_BACKEND` 가 골라야 하며, **CLI 에이전트가 기본**이어야 한다
  (AD-12). 대시보드가 자기 LLM 을 직접 부르는 경로를 유일한 경로로 두어서는 안 된다.
- **FR-057**: 에이전트가 패치 대신 산문으로 답하면(대개 거절) 그 말을 **그대로 전해야** 하며
  오류로 바꾸어서는 안 된다.
- **FR-058**: 패치 적용은 대입 시점에 **타입 검증**을 통과해야 한다. 형태가 틀린 값이 저장됐다가
  조회 시점에 터져서는 안 된다.

### Functional Requirements — 자동 구성

- **FR-110**: 발행 모델 하나에서 대시보드를 **자동 구성**할 수 있어야 한다. 입력은 모델의
  클래스 목록과 `golden_questions` 다.
- **FR-111**: 위젯 종류는 여기서도 **엔진이 정해야** 한다 (AD-13). 에이전트는 **어떤 클래스를
  어떤 순서로 담을지**와 제목만 정한다.
- **FR-112**: 골든 퀘스천이 없거나 에이전트를 쓸 수 없어도 자동 구성이 **실패해서는 안 된다.**
  결정적 순서로 채운다.
- **FR-113**: 어떤 클래스가 왜 빠졌는지(가드 사유)를 **함께 돌려주어야** 한다. 조용히 빼면
  사용자는 모델이 잘못된 줄 안다.
- **FR-114**: 여러 위젯에 걸리는 속성을 찾아 **전역 필터를 제안**해야 한다. 걸리는 위젯이
  2개 미만이면 제안하지 않는다.
- **FR-115**: 자동 구성은 진행을 **실행 로그로 흘려야** 한다 (FR-056 과 같은 이벤트 어휘).
- **FR-116**: 한 위젯도 만들지 못하면 **빈 대시보드를 저장하지 않고** 사유를 낸다.

### Functional Requirements — 갤러리

- **FR-120**: 「대시보드」 진입 시 **갤러리가 먼저** 보여야 한다. 편집 화면으로 바로 들어가지
  않는다.
- **FR-121**: 갤러리는 이름·위젯 수·수정 시각을 보여야 한다.
- **FR-122**: 새 대시보드를 만들 때 **끌어다 놓기와 대화 두 경로**가 모두 제시되어야 한다.
- **FR-123**: 갤러리에서 대시보드를 지울 수 있어야 하며, 지우기 전에 확인해야 한다.

### Functional Requirements — 저장과 이식

- **FR-060**: `DashboardSpec` 은 **사람이 읽고 diff 할 수 있는 텍스트**여야 하며 비-ASCII 를
  보존해야 한다.
- **FR-061**: 어떤 형태로도 **자격증명·접속정보·SQL 템플릿을 담아서는 안 된다.**
- **FR-062**: 다른 인스턴스에서 열었을 때 참조하는 클래스가 없으면 **위젯별로 사유를 밝혀야**
  한다. 대시보드 전체를 열지 못하게 해서는 안 된다.
- **FR-063**: 저장은 **로컬 파일**로 성립해야 한다 (OSS 축소판). 중앙 저장소를 요구해서는 안 된다.

### Functional Requirements — Superset 내보내기

- **FR-070**: `WidgetKind` → `viz_type` 대응은 **표 하나로 관리**되어야 한다.
- **FR-071**: materialized 위젯은 내보내기에서 제외하고 **제외 사유를 위젯별로 표시**해야 한다.
- **FR-072**: 내보내기 payload 에 접속정보가 포함되어서는 안 된다.

### Functional Requirements — 전역 필터와 교차 필터

- **FR-090**: 전역 필터는 **어느 클래스의 어느 속성인지**를 함께 담아야 한다. 속성 이름만으로는
  관계를 따라 건널 수 없다.
- **FR-091**: 필터가 어느 위젯에 걸리는지 **적용 전에** 알려야 한다. 걸리지 않는 위젯이 있는데
  표시가 없으면 사용자는 필터가 고장 났다고 판단한다.
- **FR-092**: 해소할 수 없으면 **걸지 않아야** 한다. 이름이 비슷하다는 이유로 추측해서 걸어서는
  안 된다.
- **FR-093**: 조인은 **한 홉만** 따라가야 한다.
- **FR-094**: 위젯 요소를 클릭하면 그 행의 **키**로 선택을 만들어야 한다. 축의 첫 차원을
  무조건 쓰면 지도 위젯에서 위도가 선택된다.
- **FR-095**: 원시 위젯의 조회에는 클래스의 키 속성이 포함되어야 한다.
- **FR-096**: 걸린 필터와 걸리지 않은 필터를 **위젯마다** 사유와 함께 돌려주어야 한다.

### Functional Requirements — 지도

- **FR-100**: 배경 지도는 **타일 서버 없이** 그려야 한다 (AD-5).
- **FR-101**: 배경 지도는 데이터의 좌표 범위로 **결정적으로** 골라야 하며, 위젯 옵션이 있으면
  그것이 우선한다.
- **FR-102**: 지도 뷰포트는 데이터가 있는 범위에 맞춰야 한다. 점이 하나도 없는 영역 때문에
  볼 것이 작아져서는 안 된다.
- **FR-103**: 지원하지 않는 지역이면 배경 없이 형상만 그리고, 그 사실을 숨기지 않는다.

### Functional Requirements — 회귀 금지

- **FR-080**: `MCP_ALLOW_DATASOURCE_EXPANSION` 이 꺼졌을 때 `ontology_mcp` 의 도구 목록은
  여전히 **정확히 4개**여야 한다 (spec 010 FR-016).
- **FR-081**: `ontology_mcp` 의 차단 라벨 목록과 읽기 전용 보장이 유지되어야 한다.
- **FR-082**: 006 의 세션 한정 차트 경로(구현되면)와 이 스펙의 대시보드 경로는 **서로를 막지
  않아야** 한다.
- **FR-083**: `answer` 모드의 쓰기 도구 없음 경계가 유지되어야 한다 (006 CR-8).

---

## Key Entities

- **ObjectProfile** — 클래스 하나의 속성별 역할·타입·분포. 파생물이며 캐시된다.
- **WidgetSpec** — 클래스 하나에서 나온 위젯 한 개의 선언. 질의를 담지 않는다.
- **DashboardSpec** — 위젯의 모음과 배치. 정본이며 텍스트다.
- **WidgetKind** — 위젯 종류의 닫힌 목록. Superset `viz_type` 과 1:1 대응표를 갖는다.

---

## Success Criteria *(mandatory)*

- **SC-001**: 스튜디오의 모델링 원천(SQLite)이 **비어 있거나 없어도** 발행된 온톨로지만으로
  대시보드를 만들고 열 수 있다 — 워크스루와 같은 조건(`SESSION_DB_PATH=/nonexistent/none.db`)
  에서 검증한다. *(원래 "스튜디오 백엔드를 끈 상태"라고 썼으나, 보드 API 는 그 백엔드에
  마운트되고 프론트도 거기서 서빙되므로 성립할 수 없는 주장이었다 — research R-7)*
- **SC-002**: 클래스를 드롭한 뒤 위젯이 그려지기까지 **3초 이내** (Neo4j 경로, 인스턴스 1만 건 이하).
- **SC-003**: `제조 하이브리드` 의 9개 클래스 전부에 대해 위젯이 정해지고, **폴백(`table`)이
  아닌 것이 5개 이상**이다.
- **SC-004**: 자동 추천된 위젯 종류가 사람의 선택과 일치하는 비율이 **70% 이상** (9개 클래스,
  평가자 2인 이상).
- **SC-005**: 저장된 `DashboardSpec` 에 `password` · `host` · `SELECT` 문자열이 **0건**
  (자동 검사).
- **SC-006**: 잘림이 발생한 위젯 **100%** 에 "N건 중 M건" 배지가 붙는다.
- **SC-007**: 대시보드 백엔드 모듈이 `neo4j` · `ontology_runtime` 을 import 하지 않는다
  (import 금지 테스트 통과).
- **SC-008**: 같은 `DashboardSpec` 을 두 번 열면 **같은 위젯·같은 축**이 나온다 (결정성).

---

## Assumptions

- 온톨로지는 이미 Ontology Studio 에서 만들어져 **발행되어 있다.** 이 스펙은 모델링을 다루지 않는다.
- 전력 도메인 지식은 **온톨로지 안에** 있다. IEC 61850 · CIM 어휘 매핑을 구현하지 않는다.
- 기본 데이터 경로는 **Neo4j(materialized)** 이다. 가상 클래스 경로는 지원하되 2급이다.
- `MCP_ALLOW_DATASOURCE_EXPANSION=true` 인 MCP 인스턴스가 있다.
- 보드 API 는 스튜디오 백엔드 프로세스에 마운트된다(원칙 VIII — 프론트와 API 는 같은 오리진).
  독립성 주장의 범위는 **프로세스가 아니라 모델링 원천(SQLite)** 이다 (research R-7).
- 지도는 **오프라인 GeoJSON** 으로 성립한다 (타일 서버 없음).

---

## Out of Scope

### 이번에 하지 않는 것

- **크로스 필터·드릴다운.** 위젯 간 상호작용은 저장된 대시보드가 자리를 잡은 뒤에 온다.
- **여러 클래스를 하나의 위젯으로 조인.** 조인은 질의의 일이다 (001 의 같은 원칙).
- **실시간 스트리밍 갱신.** 보고서 §7 이 향후 과제로 든 항목이며 MCP 표면이 폴링뿐이다.
- **백엔드 차트 렌더링.** 006 AD-4 의 메모리 예산 판단이 그대로 유효하다.
- **두 온톨로지 표현의 통합** (`:Table:ObjectType` ↔ `_Ontology*`) — spec 008 의 문제다.
- **리포트 생성.** 006 이 다룬다. 대시보드를 리포트로 굽는 것은 그 뒤다.

### Enterprise 영역 (전략 §3 개정안)

중앙 저장소·공유·권한, SSO/RBAC, 감사 로그, 스케줄 새로고침과 배포, 조직 공용 템플릿,
중앙 MCP 엔드포인트와 사용자별 토큰, Superset/Metabase **동기화**(1회 내보내기는 OSS).

---

## 미결정 사항 / 리스크

### 미결정

- **U-1. `ontology_get_class_profile` 도구화.** materialized 클래스의 타입을 MCP 가 직접 주면
  표면이 일관돼지고 다른 에이전트도 혜택을 본다. 단 spec 010 FR-016(플래그 off 시 도구 정확히
  4개) 때문에 확장 세트에 넣어야 하고 **010 개정을 수반**한다. v1 은 AD-4 로 성립시킨다.
- **U-2. `ontology_graph_cypher` 의 per-call `limit` 인자.** SQL 도구와 대칭이 되고 CR-5 의
  비대칭이 사라진다. 역시 010 개정 수반.
- **U-3. Cypher 경로의 `row_count` 가 참값이 아닌 것을 결함으로 볼 것인가.** 별도 `count()` 로
  우회 가능하므로 v1 은 우회한다. 그러나 다른 소비자도 같은 함정에 빠질 수 있다.
- **U-4a. 배경 지도 확장.** 지금은 대한민국(시도 17)과 미국(주 52) 둘뿐이다. 다른 나라
  데이터는 배경 없이 형상만 그려진다. 사용자 GeoJSON 등록 경로가 필요하나 v1 범위 밖이다.
- **U-4. 시군구 단위 배경 지도.** 시도 단위(17개)는 `robo-data-frontend` 에 이미 있고 5KB 라
  이식하면 끝난다(research R-3). 그러나 정전 구역(O6)에는 입도가 부족하다. 사용자 GeoJSON
  등록 경로가 필요하나 v1 범위 밖이다.

> **해소됨**: 원래의 U-4(GeoJSON 출처) → research R-3 · U-5(캐시 무효화) → R-2, FR-014 반영 ·
> U-6(`chartConfig` 재사용) → R-6, 재사용하지 않는다.

### 리스크

- **R-1. 행 예산.** 20/30 은 에이전트용 치수다. 집계 승격으로 대부분 흡수되지만 "일별 90일
  추이"처럼 흡수 불가능한 요구가 온다. 전용 MCP 프로파일이 실질적 해법이고, 이는 **배포 구성이
  하나 더 늘어난다**는 뜻이다.
- **R-2. 값 기반 타입 추론의 오판.** 샘플이 편향되면 틀린 위젯이 나온다. `type_source` 노출과
  수동 오버라이드(FR-043)로 완화하되, 근본 해결은 U-1 이다.
- **R-3. 차단 라벨 문자열 오탐.** 필터 값이 `Table` 등과 같으면 거부된다. `params` 강제(FR-032)로
  막지만, 사용자가 만든 Cypher 를 허용하는 순간 다시 열린다 — 허용하지 않는다.
- **R-4. 이식 비용.** ECharts 래퍼 4파일 + 위지윅 편집기를 TS→JS 로 옮긴다. 원본이 계속
  발전하면 두 벌이 갈라진다. 이식 후 원본을 참조로만 두고 동기화하지 않는다는 것을 명시한다.
- **R-5. Superset 내보내기의 좁은 적용 범위.** 기본 경로(Neo4j)에서 내보낼 수 없다는 사실이
  영업 기대와 어긋날 수 있다. 기획서 §5 에 먼저 적었다.
