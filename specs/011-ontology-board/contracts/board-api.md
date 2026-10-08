# 계약 — Board HTTP API

**방향**: 이 기능이 **제공하는** 계약. 프론트엔드가 소비한다.

**마운트**: ontology-studio 백엔드(`host/app.py`)에 `/api/board` 접두로 마운트한다.
프론트와 **같은 오리진**이다 (constitution 원칙 VIII — "프론트엔드와 API 는 같은 오리진에 둔다").
**새 호스트 포트를 열지 않는다.**

**경로 충돌 없음**: 기존 라우터의 greedy 경로는 `/api/schema/classes/{class_name:path}` 이고
`/api/board/**` 와 겹치지 않는다. 마운트 순서에 영향을 받지 않는다.

---

## 상태

### `GET /api/board/health`

MCP 연결과 확장 플래그 상태. **UI 가 "왜 안 되는지" 를 말할 수 있게 하는 유일한 경로다** (FR-004).

```
{ "mcp": "ok" | "unreachable", "transport": "stdio" | "http",
  "datasource_expansion": true | false,
  "row_budget": {"cypher": 20, "sql": 30},
  "error": "..." }
```

`datasource_expansion: false` 면 프론트는 가상 클래스를 **회색으로 표시하고 사유를 보여준다.**

---

## 온톨로지 읽기

### `GET /api/board/models`

발행 모델 목록. `graph://schema` 의 `models` + `counts`. 발행된 것이 없으면 서버가 준 `note` 를
**그대로** 싣는다 (FR-005).

### `GET /api/board/classes?schema_name=`

팔레트용 클래스 목록. `graph://schema` 의 `classes` 를 그대로 낸다 —
`binding_kind` · `property_names` · `native_key` · `behavior_count` · `orphaned`.
**타입은 여기 없다** (CR-2). 프로파일을 부르기 전까지 프론트는 타입을 모른다.

### `GET /api/board/classes/{class_name}/profile?schema_name=&refresh=false`

→ `ObjectProfile` (data-model.md). 캐시 키는 `(schema_id, published_at)`.
`refresh=true` 면 캐시를 버리고 다시 만든다 (R-2 의 "인스턴스 증가" 구멍 대응).

`ambiguous` 면 **200 이 아니라 409** 와 함께 `schema_names[]` 를 낸다 — 임의로 고르지 않는다.

### `GET /api/board/classes/{class_name}/related`

`_datasource_refs` 기반 "연관 위젯 추천". `{class, datasource, table, via_relationship, join_on}[]`.

---

## 위젯

### `POST /api/board/classes/{class_name}/recommend`

```
요청  { "schema_name": "...", "hint": {"prefer": "timeseries"} }   ← hint 는 선택
응답  { "primary": WidgetSpec, "secondary": WidgetSpec[],
        "profile_summary": {...} }
```

**결정적이다** (FR-020). 같은 프로파일은 같은 결과. `rule` 과 `reason` 이 반드시 채워진다.
어떤 규칙에도 안 걸리면 `primary.widget_kind = "table"`, `rule = "O10"` (FR-023).

`secondary` 는 한 클래스가 둘 이상의 객체 유형을 만족할 때 채워진다 (FR-024) — 보고서 §5-1 의
"box_plot 보조 차트 병렬 추천"이 여기서 나온다.

### `POST /api/board/widgets/query`

```
요청  { "widget": WidgetSpec, "params": {...} }
응답  { "columns": [...], "rows": [...],
        "returned_count": 20, "total_count": 33, "truncated": true,
        "aggregation_promoted": {"from": "day", "to": "month"} | null,
        "badge": "33건 중 20건" }
```

- 집계는 **서버(Cypher/SQL)가** 한다 (FR-030)
- `total_count` 는 **별도 `count()`** 로 얻는다 (FR-013)
- 잘렸으면 `badge` 가 **반드시** 채워진다 (FR-034)
- 잘린 시계열은 응답에 `"fallback": "table"` 을 실어 표로 강등한다 (FR-035, G7)
- 생성된 질의는 응답에 **싣지 않는다** — 디버그가 필요하면 서버 로그로 본다

---

## 대시보드

### `GET /api/board/dashboards`
### `GET /api/board/dashboards/{id}`

열기. 위젯마다 해소 판정을 함께 낸다 (FR-062) —
`ok` · `missing_class` · `missing_property` · `expansion_disabled` · `ambiguous_class`.
**하나가 깨져도 나머지는 연다.**

### `PUT /api/board/dashboards/{id}`

저장. 서버가 **불변식을 검사**한다 (data-model.md) — 자격증명 키 없음, 질의문 없음,
`widget_kind` ∈ 목록, `param_key` 해소, `id` 유일. 하나라도 어기면 **422 와 함께 어느 위젯의
어느 필드인지** 를 낸다.

### `POST /api/board/dashboards/{id}/patch`

```
요청  { "patch": [...], "dry_run": true }
응답  { "valid": true|false, "diff": [...], "errors": [...] }
```

`dry_run: true` 가 **기본**이다. 검증과 diff 만 하고 적용하지 않는다 (FR-052).
적용은 `dry_run: false` 로 다시 부른다. 존재하지 않는 클래스·속성을 참조하면 거부한다 (FR-051).

### `POST /api/board/dashboards/{id}/export/superset`

```
응답  { "charts": [ {slice_name, viz_type, datasource_id?, params} ],
        "excluded": [ {widget_id, reason: "materialized_not_exportable"} ] }
```

**제외된 위젯을 사유와 함께 반드시 낸다** (FR-071). 조용히 빠뜨리지 않는다.

---

## 공통 규칙

- MCP 오류 문구는 **가공하지 않고 그대로** 전달한다 (FR-005)
- 어떤 응답에도 `password` · `host` · `port` · SQL · Cypher 가 실리지 않는다 (FR-061)
- 데이터 조회는 **api-gateway(9000)를 거치지 않는다** — 30초 타임아웃 (constitution 원칙 VI)
