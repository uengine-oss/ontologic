# 계약 — 답변 모드 도구 대응표

**전제**: `ontology_mcp` 가 떠 있고 `MCP_ALLOW_DATASOURCE_EXPANSION=true` 다. 꺼지면
아래 표의 "확장" 표시가 붙은 도구는 **등록되지 않는다** (spec 010 FR-011).

## 무엇이 무엇을 대신하는가

| 기존 내장 도구 | MCP 경유 | 확장 | 비고 |
|---|---|---|---|
| `schema_get` | `ontology_get_schema` | | 발행된 그래프에서 읽는다 |
| `graph_stats` | `ontology_list_schemas` | | 클래스별 엔티티 수가 여기 들어 있다 |
| `vector_search` | `ontology_list_entities(semantic_query=…)` | | |
| `entity_search` | `ontology_list_entities(class_name=…, criteria=…)` | | |
| `neo4j_cypher_readonly` | `ontology_graph_cypher` | ✔ | 카탈로그·발행 레지스트리 라벨 차단이 붙는다 |
| — | `ontology_resolve_entity` | ✔ | 이름 → 캐노니컬 키. 기존 경로에 대응물이 없었다 |
| `behavior_list` | `ontology_get_datasource_schema(class_name)` | ✔ | **클래스 하나씩.** 전체를 쏟지 않는다 |
| `behavior_invoke` / `entity_fetch` | `ontology_query_datasource_sql` | ✔ | 파라미터 behavior 대신 스코프된 SQL |
| `datasource_sql_query` | `ontology_query_datasource_sql` | ✔ | |
| — (리소스) | `ontology_graph_schema()` | | `graph://schema` 리소스를 읽는 **로컬 래퍼**. MCP 도구 목록에는 추가하지 않는다 |
| `sandbox_read` | `sandbox_read` | | 로컬 유지. 그래프·데이터에 닿지 않는다 |

`ontology_query` 는 **대응표에 없다.** 그 도구가 답변 에이전트를 구동하므로, 답변 모드에
등록하면 자기 자신을 부른다.

## 궤적을 만드는 응답 모양

`traversed_nodes` 이벤트는 아래 도구의 결과에서만 만든다.

| 도구 | 노드가 실려 오는 키 | 노드 안의 id 키 |
|---|---|---|
| `ontology_graph_cypher` | `rows`, `nodes`, `results` | 행 안의 노드 dict, 또는 행의 `_element_id` |
| `ontology_list_entities` | `entities`, `results` | `id` (elementId), `node_id` |
| `ontology_resolve_entity` | `matches`, `candidates`, `results` | `_element_id` |

값이 하나도 없으면 이벤트를 만들지 않는다 (FR-012). 가상 클래스 조회는 노드가 없으므로
정상적으로 0건이다.

### 투영만 한 Cypher 에서 id 를 회수하는 방법

에이전트는 보통 `RETURN s.name, s.load_pct` 처럼 필요한 속성만 고른다. 그러면 결과에 노드가
없다. 그때는 **같은 질의의 RETURN 앞에 `elementId(n)` 을 덧붙여** 다시 실행해 회수한다.

투영을 **지우지 않는 것**이 핵심이다. 예전 구현은 `RETURN` 뒤를 통째로 버렸는데, 그러면
`ORDER BY load DESC` 같은 별칭 정렬이 사라져 행 수는 같고 순서만 달라진다 — 호출자는 눈치채지
못한 채 **엉뚱한 노드를 하이라이트한다** (실측으로 잡음).

다음 질의는 회수를 **포기한다.** 투영을 건드리면 의미가 바뀌기 때문이다. 틀린 노드를
하이라이트하느니 하지 않는 편이 낫다.

- `DISTINCT`
- `RETURN *`
- 집계 (`count` · `sum` · `avg` · `min` · `max` · `collect` · `percentile*` · `stDev*`)

같은 헬퍼(`ontology/tools._try_inject_element_ids`)를 내장 경로도 쓴다. 규칙을 두 벌로
만들지 않는다.

## 실패 표면

| 상황 | 사용자가 보는 것 |
|---|---|
| MCP 에 연결 실패 | `온톨로지 MCP 에 연결하지 못했습니다 (http: <url>): <원인>` + 띄우는 방법 안내. 원인은 anyio 의 `ExceptionGroup` 을 풀어 실제 사유(연결 거부·404)를 싣는다 |
| 확장 꺼짐 | 해당 도구가 목록에 없고, 호출 시도 시 서버가 사유를 돌려준다 |
| 미발행 | `graph://schema` 의 발행 안내 문구가 그대로 전달된다 |
