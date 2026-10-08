# Phase 1 — 데이터 모델

**Feature**: 011-ontology-board · **Date**: 2026-08-19

세 가지가 있다. **ObjectProfile** 은 파생·캐시이고 밖으로 나가지 않는다. **WidgetSpec** 과
**DashboardSpec** 은 저장되는 정본이다. 넷째 **WidgetKind** 는 닫힌 목록이다.

경계 하나를 먼저 못박는다 — **저장되는 것에는 질의문이 없다.** Cypher 도 SQL 도 조회 시점에
만든다(FR-036). 그래야 모델이 바뀌어도 저장물이 썩지 않고, 저장물에 SQL 이 새지 않는다.

---

## WidgetKind (닫힌 목록)

```
kpi · kpi_group · table · bar · bar_h · pie · timeseries_line
box_plot · treemap · sunburst · word_cloud · heatmap · scatter
pivot_table · geo_point · geo_path · geo_polygon
```

각 값은 Superset `viz_type` 과 1:1 대응을 갖는다 (contracts/superset-mapping.md).
**목록에 없는 값은 스펙 검증에서 거부한다** — 열어 두면 매핑표와 렌더러가 조용히 갈라진다.

---

## ObjectProfile (파생 · 캐시 · 밖으로 나가지 않는다)

클래스 하나의 "이 객체는 무엇으로 생겼는가". 매핑 엔진의 유일한 입력이다.

| 필드 | 타입 | 출처 | 비고 |
|---|---|---|---|
| `schema_name` | string | `graph://schema` | 같은 클래스명이 여러 그룹에 있을 수 있다 |
| `class_name` | string | `graph://schema` | |
| `binding_kind` | `materialized` \| `virtual` | `graph://schema` | 프로파일링 경로를 가른다 |
| `instance_count` | int \| null | **별도 `count()` 질의** | FR-013. 반환 행 수를 쓰지 않는다 |
| `native_key` | string[] | `graph://schema` | `identifier` 판정 |
| `source` | `{datasource, schema, table}` \| null | `graph://schema` | virtual 일 때만 |
| `datasource_refs` | Ref[] | `ontology_graph_cypher` 응답 | "연관 위젯 추천"의 재료 |
| `properties` | PropertyProfile[] | 아래 | |
| `cache_key` | `(schema_id, published_at)` | `graph://schema` | R-2 |

### PropertyProfile

| 필드 | 타입 | 비고 |
|---|---|---|
| `name` | string | `property_names` 또는 `column_map[].property` |
| `column` | string \| null | virtual 일 때 물리 컬럼명. **속성명 ≠ 컬럼명** |
| `role` | `identifier` \| `temporal` \| `numeric` \| `categorical` \| `unknown` | 006 1단계 승계 |
| `type` | `boolean` \| `integer` \| `float` \| `date` \| `string` \| `geojson` \| null | `map_sql_type` 5종 + `geojson` |
| `type_source` | `column_map` \| `value_inference` \| `none` | **FR-012. 추론인지 선언인지 반드시 구분된다** |
| `distinct_count` | int \| null | 샘플 기준. `k(C)` |
| `null_ratio` | float \| null | |
| `min` / `max` | any \| null | 좌표 범위 판정(O4) |
| `avg_length` | float \| null | 자유 텍스트 판정(O7) |
| `geo_shape` | `point` \| `linestring` \| `polygon` \| null | O4~O6 |
| `is_reference` | bool | `column_map[].reference` |

**`type` 에 `geojson` 을 더한 이유**: `map_sql_type` 은 SQL 타입만 다루므로 GeoJSON 문자열이
`string` 으로 떨어진다. 그러면 O5·O6 이 영원히 발동하지 않는다. 값 형태로만 판정 가능한
타입이므로 `type_source` 는 항상 `value_inference` 다.

### 프로파일링 경로 (binding_kind 에 따라 갈린다)

```
virtual       → ontology_get_datasource_schema(class)
                → column_map[].{property, column, type, reference} 를 그대로 옮긴다
                → type_source = "column_map"        (FR-011: 값 추론을 우선하지 않는다)

materialized  → ontology_graph_cypher("MATCH (n:_Entity:<Class>) RETURN n LIMIT <sample>")
                → 노드를 통째로 받아 값에서 추론      (FR-010, 원칙 0)
                → type_source = "value_inference"
```

두 경로 모두 `instance_count` 는 **별도 `count()` 질의**로 따로 받는다.

---

## WidgetSpec (저장된다)

| 필드 | 타입 | 비고 |
|---|---|---|
| `id` | string | 대시보드 안에서 유일 |
| `schema_name` / `class_name` | string | 무엇을 그리는가 |
| `widget_kind` | WidgetKind | |
| `rule` / `reason` | string | `"O5"` / 사람이 읽는 근거. **FR-022 — 사용자에게 보인다** |
| `pinned` | bool | true 면 자동 추천이 덮어쓰지 않는다 (FR-043) |
| `dimensions` | string[] | 속성명. 계층은 순서가 의미를 갖는다 (O3) |
| `measures` | `{property, agg}[]` | `agg` ∈ `count·sum·avg·min·max` |
| `filters` | `{property, op, param_key}[]` | **값이 아니라 `param_key`** — 아래 참조 |
| `time_grain` | `hour·day·week·month·quarter·year` \| null | AD-10 의 승격 대상 |
| `top_n` | int \| null | 범주 축소 |
| `layout` | `{x, y, w, h}` | gridstack `save()` 형태 |
| `title` | string | LLM 이 쓸 수 있는 유일한 곳 중 하나 (AD-2) |
| `options` | object | 색상 등 렌더 옵션 |

**`filters` 가 값을 담지 않는 이유가 둘이다.**

1. 값을 담으면 사람마다 다른 값을 보는 대시보드를 공유할 수 없다. 값은 `DashboardSpec.params`
   에 기본값으로 있고 조회 시점에 주입된다.
2. **필터 값이 `Table`·`Column`·`Schema`·`DataSource` 와 같으면 Cypher 게이트가 질의를 거부한다**
   (CR-6). `params` 로 넘기는 것이 유일하게 안전한 경로다 (FR-032).

**담지 않는 것**: `cypher`, `sql`, `datasource`, 접속정보. 전부 조회 시점에 유도된다.

---

## DashboardSpec (정본 · 텍스트)

| 필드 | 타입 | 비고 |
|---|---|---|
| `format_version` | int | 읽을 수 없는 버전은 거부한다 (009 FR-021 과 같은 정신) |
| `name` / `description` | string | |
| `model` | `{schema_id, schema_name}` | 어느 발행 모델을 보는가 |
| `widgets` | WidgetSpec[] | |
| `params` | `{key: default_value}` | 필터 값의 기본값 |
| `created_at` / `updated_at` | ISO 8601 | |

**불변식** (저장·불러오기 양쪽에서 검사한다):

- `password` · `host` · `port` · `user` 키가 **어디에도 없다** (FR-061, SC-005)
- `SELECT` · `MATCH` 로 시작하는 문자열이 **어디에도 없다** (FR-036, FR-061)
- 모든 `widget.widget_kind` ∈ WidgetKind
- 모든 `filters[].param_key` ∈ `params` 의 키
- `widgets[].id` 가 유일하다

### 열 때의 해소 (FR-062)

불러오기는 **전부-또는-전무가 아니다.** 참조가 깨진 위젯만 못 그리고 나머지는 그린다.
위젯마다 다음 중 하나로 판정한다:

| 판정 | 조건 |
|---|---|
| `ok` | 클래스가 발행돼 있고 참조 속성이 전부 존재 |
| `missing_class` | `graph://schema` 에 그 클래스가 없다 |
| `missing_property` | 클래스는 있으나 `dimensions`/`measures` 의 속성이 없다 |
| `expansion_disabled` | virtual 인데 `MCP_ALLOW_DATASOURCE_EXPANSION` 이 꺼져 있다 (G8) |
| `ambiguous_class` | 같은 클래스명이 여러 그룹에 있다 |

**009 의 전부-또는-전무(FR-020)와 다른 이유**: 009 는 *모델*을 적용하는 것이라 반쯤 적용되면
온톨로지가 깨진다. 여기는 *보기*라서 반쯤 그려도 아무것도 깨지지 않고, 오히려 전부 막으면
사용자가 무엇이 문제인지 못 본다.

---

## 조회 결과 (저장되지 않는다)

| 필드 | 비고 |
|---|---|
| `columns` / `rows` | 위젯 렌더 입력 |
| `returned_count` | 실제 받은 행 수 |
| `total_count` | **별도 `count()` 로 얻은 참값** |
| `truncated` | `returned_count < total_count` |
| `aggregation_promoted` | AD-10 ① 이 발동했는가 (`day → month` 등) |
| `badge` | `"33건 중 20건"` — **잘렸으면 반드시 채워진다** (FR-034) |

`total_count` 를 별도로 받는 이유는 CR-5 다 — Cypher 경로의 `row_count` 는 잘린 뒤의 수라서
참값이 아니다.

---

## 상태 전이

```
클래스 드롭
   ↓  프로파일 캐시 조회 (cache_key)
   ├─ hit  → ObjectProfile
   └─ miss → MCP 왕복 (count + 샘플/JIT 스키마) → 캐시 적재
   ↓
매핑 엔진 (결정적)  → WidgetSpec{widget_kind, rule, reason, pinned=false}
   ↓
질의 생성 → MCP 호출 → 결과 → 렌더
   ↓
사용자 편집 ─┬─ 인스펙터 클릭 → WidgetSpec 갱신, pinned=true
             └─ 자연어 패치  → 검증 → diff 제시 → 승인 시 적용, pinned=true
   ↓
저장 → DashboardSpec (불변식 검사)
```

`pinned` 가 이 흐름의 유일한 되돌릴 수 없는 지점이다 — 한 번 사람이 정하면 자동 추천이
다시 덮지 않는다(FR-043). 명시적으로 "자동 추천으로 되돌리기"를 눌러야 풀린다.
