# 계약 — MCP 표면 소비

**방향**: 이 기능이 **소비하는** 계약. 우리가 정의하지 않고 spec 010 이 정의했다.
여기서는 **무엇에 의존하는지**와 **깨지면 어떻게 드러나는지**를 고정한다.

**서버**: `ontology-studio-search` (`python -m backend.src.modules.ontology_mcp`)
**전송**: stdio 또는 streamable HTTP (`MCP_TRANSPORT`, 기본 `stdio`; HTTP 시 `/mcp`)
**전제**: `MCP_ALLOW_DATASOURCE_EXPANSION=true` — 꺼지면 하이브리드 도구 4종이 **등록되지 않는다**

---

## 우리가 쓰는 표면

| 종류 | 이름 | 무엇을 얻는가 |
|---|---|---|
| Resource | `graph://schema` | 클래스·관계 지도. **컬럼 없음** |
| Tool | `ontology_graph_cypher(query, params)` | 인스턴스 조회·집계, `_datasource_refs` |
| Tool | `ontology_get_datasource_schema(class_name, schema_name="")` | 한 클래스의 컬럼·타입·behavior |
| Tool | `ontology_query_datasource_sql(sql, limit)` | 바인딩 테이블 안 SELECT |
| Tool | `ontology_resolve_entity(text, class_name, limit)` | 이름 → 키 (필터 값 선택) |

**쓰지 않는 것**: `ontology_query` · `ontology_list_entities` · `ontology_list_schemas` ·
`ontology_get_schema` — 이 넷은 스튜디오 SQLite 를 읽는다. FR-001·R-7 위반이 된다.

---

## 응답에서 우리가 의존하는 필드

### `graph://schema`

```
models[]        {schema_id, name, description, intent, golden_questions,
                 format_version, published_at}
classes[]       {schema_name, class_name, description, binding_kind,
                 property_names[], property_source, native, native_key[],
                 behavior_count, source?{datasource,schema,table}, key_columns?,
                 orphaned?}
relationships[] {name, from_class, to_class, properties[]}
counts          {classes, virtual_classes, relationships}
note?           발행된 것이 없을 때만
```

- **`property_names` 에 타입이 없다.** 이것이 AD-4 의 근거다 (CR-2)
- `published_at` 이 **프로파일 캐시 키**다 (R-2)
- `orphaned` 가 붙은 클래스는 팔레트에 표시하되 **경고와 함께** 낸다

### `ontology_graph_cypher`

```
rows[] · row_count · truncated · _datasource_refs[] · _datasource_hint
error?
```

- **`row_count` 는 참값이 아니다** — 잘린 뒤의 수다 (CR-5). 총계는 별도 `count()` 로 받는다
- `_datasource_refs[]` = `{from_class, class, datasource, schema, table,
  via_relationship, join_on}` — 응답 **최상단**에 붙는 쪽을 쓴다. 행 단위는 노드를 통째로
  RETURN 했을 때만 붙으므로 신뢰하지 않는다

### `ontology_get_datasource_schema`

```
columns[] {property, column, type, description, reference?}
key_columns[] · base_conditions[] · behaviors[]
error? · ambiguous? · schema_names[]
```

- `pii` 컬럼은 **이미 제거되어** 온다 — 우리가 다시 거를 필요가 없다
- `sql_template` 은 **오지 않는다** — 요구하지 않는다
- `ambiguous: true` 면 **사용자에게 고르게 한다.** 임의로 하나 고르면 다른 테이블 컬럼을 쓴다

### `ontology_query_datasource_sql`

```
status · columns[] · rows[] · row_count · truncated_for_agent · truncated · sql · source
```

- `row_count` 는 **참값이다**(가져온 행 수). `rows` 는 30행으로 잘려 온다
- `sql` 이 응답에 있으나 **DashboardSpec 에 저장하지 않는다** (FR-036)

---

## 우리가 지켜야 하는 제약

| 제약 | 근거 | 어기면 |
|---|---|---|
| Cypher 에 `CALL` 금지 | `_WRITE_CLAUSE_PATTERN` (CR-6) | 도구가 "읽기 전용만 허용" 으로 거부 |
| Cypher 에 `CREATE/MERGE/DELETE/DETACH/SET/REMOVE/DROP/FOREACH/LOAD CSV` 금지 | 같음 | 같음 |
| 차단 라벨 이름을 **문자열로도** 쓰지 않기 | `_blocked_label_used` (CR-6) | 필터 값이 `Table` 이면 질의 거부 → **`params` 로 넘긴다** |
| `:DataSource`/`:Schema`/`:Table`/`:Column`/`_Ontology*` 조회 금지 | 같음 | 거부 |
| 동적 속성 접근 `n[k]` 금지, `properties(n)` 금지 | constitution 원칙 0 | ontological-db 에서 실패 |
| SQL 에 `LIMIT` 직접 쓰지 않기 | 도구 docstring | 서버가 `limit` 인자로 적용한다 |

---

## 행 예산 (실측 2026-08-19)

| 경로 | 상한 | 설정 키 | 기본 |
|---|---|---|---|
| `ontology_graph_cypher` | 반환 행 | `MCP_MAX_RESULTS` | **20** |
| `ontology_query_datasource_sql` | 반환 행 | `DATASOURCE_AGENT_ROW_PREVIEW` | **30** |
| (SQL 실행 자체) | 가져오는 행 | `DATASOURCE_MAX_ROWS` | 500 |

`count()` 질의는 1행이라 상한과 무관하다 — **총계를 아는 유일한 경로**다.

---

## 깨짐 감지

기능이 조용히 틀리는 것을 막기 위해 아래를 **계약 테스트**로 고정한다.

1. `graph://schema` 의 클래스 엔트리에 `property_names` 가 있고 `properties` (타입 포함)가 **없다**
   — 있게 되면 AD-4 를 재검토해야 한다는 신호다
2. `ontology_get_datasource_schema` 가 materialized 클래스에 **거절**을 돌려준다
3. `ontology_graph_cypher` 응답 최상단에 `_datasource_refs` 가 있다
4. 확장 플래그가 꺼지면 `tools/list` 가 **정확히 4개**다 (spec 010 FR-016 · FR-080)
5. `MCP_MAX_RESULTS` 를 넘는 결과에 `truncated: true` 가 붙는다
