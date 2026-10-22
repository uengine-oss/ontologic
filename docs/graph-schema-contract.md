# 그래프 스키마 계약 — 발행된 온톨로지를 그래프 자체의 스키마에서 읽는다

[`.specify/memory/constitution.md`](../.specify/memory/constitution.md) 가 규칙을 정하고,
[`catalog-schema.md`](catalog-schema.md) 가 **데이터 패브릭 카탈로그**의 실측을 기록한다.
이 문서는 그 위에 있는 층 — **온톨로지 모델이 그래프에 어떻게 배포되고 어떻게 읽히는가** — 를
다룬다.

존재 이유: MCP 런타임은 **ontology-studio 가 떠 있지 않은 환경**에서 동작해야 한다. 따라서
스튜디오의 관리용 SQLite(`backend/data/sessions.db`)를 스키마 원천으로 쓸 수 없고, 그래프에
배포된 것만 읽는다.

재확인 (ontologic 루트에서):

```bash
uv run --with neo4j python scripts/probe_graph_schema_api.py \
  --uri bolt://localhost:7688 --user neo4j --password <pw> --name Neo4j
```

---

## 실측 결과 (2026-08-17, `neo4j:2025.11.2-community`, bolt 7688)

핵심 질문은 하나였다 — **인스턴스가 0건인 가상 클래스를 그래프 자체의 스키마로 표현할 수
있는가?** 가상 클래스는 인스턴스를 0건 유지하므로(constitution — ontology-studio 절),
데이터에서 유추하는 방식으로는 영원히 보이지 않는다.

| 관측 | 결과 |
|---|---|
| 제약 생성 지원 | 예 |
| 인덱스 생성 지원 | 예 |
| **노드 0건 + 제약만으로 `db.labels()` 에 라벨 노출** | **예** |
| `SHOW CONSTRAINTS` / `SHOW INDEXES` 에 노출 | 예 |
| `db.schema.visualization()` 에 노출 | 예 |
| `apoc.meta.schema()` 에 노출 | **아니오** |
| 제약이 참조한 속성 키가 `db.propertyKeys()` 에 노출 | 예 |
| 제약·인덱스를 모두 지우고 노드도 없으면 라벨 사라짐 | 예 |

독립 확인:

```cypher
CREATE CONSTRAINT t0 FOR (n:T0OnlyConstraintNeverAnyNode) REQUIRE n.k IS UNIQUE;
MATCH (n:T0OnlyConstraintNeverAnyNode) RETURN count(n);   -- 0
CALL db.labels() YIELD label WHERE label STARTS WITH 'T0' RETURN label;
-- "T0OnlyConstraintNeverAnyNode"
```

### 도출되는 규칙

> **라벨은 노드를 갖거나 스키마 객체(제약·인덱스)를 가지면 `db.labels()` 에 나타난다.**

실측 그래프가 이 규칙과 정확히 일치한다 — 노드 0건인데 목록에 있는 라벨
(`FUNCTION`·`MODULE`·`PACKAGE`·`CONSTANT`·`DATA_TYPE`·`RULE`·`EXAMPLE`·`QUESTION`·
`SCHEMA`·`TABLE`·`VARIABLE`·`ExplainCache`)은 **전부** 제약이나 인덱스를 갖고 있다.
유령 토큰은 없다.

따라서 **가상 클래스는 앵커 노드 없이 발행할 수 있다.** 키 컬럼에 제약을 선언하는 것만으로
그래프 자체의 스키마에 등재되고, `db.labels()` · `db.schema.visualization()` 로 조회된다.
"가상 클래스의 저장 인스턴스는 0건"(spec 001 SC-001)이 깨지지 않는다.

### `apoc.meta.schema()` 는 계약에서 제외한다

데이터를 **샘플링**하므로 노드가 0건인 가상 클래스를 보지 못한다(위 표에서 유일한 "아니오").
이 기능의 핵심 대상이 정확히 그 클래스이므로 쓸 수 없다.

---

## `db.labels()` 만으로는 부족하다 — 발행 목록이 따로 필요한 이유

이 그래프는 플랫폼이 공유한다. `db.labels()` 는 온톨로지와 무관한 라벨도 함께 돌려준다:

| 라벨 | 주인 |
|---|---|
| `DataSource` · `Schema` · `Table` · `Column` | data-fabric 카탈로그 |
| `RULE` · `EXAMPLE` · `QUESTION` · `Query` · `ExplainCache` · `ValueMapping` | neo4j-text2sql |
| `MODULE` · `FUNCTION` · `PACKAGE` · `VARIABLE` · `CONSTANT` · `DATA_TYPE` | robo-analyzer |
| `OntologySchema` · `OntologyType` · `OntologyBehavior` · `Behavior` · `Table:ObjectType` | **domain-layer** (별도 온톨로지) |
| `_Entity` + 클래스명 | ontology-studio 인스턴스 |

그래서 계약은 **두 층**이다.

1. **네이티브 스키마 투영** — 클래스는 라벨이고, 키는 제약이고, 속성은 속성 키다. 그래프
   도구(브라우저·`db.schema.visualization()`)가 온톨로지를 그대로 본다. 사용자가 요구한
   "스키마는 그래프 자체의 스키마에 저장된다"가 이 층이다.
2. **발행 레지스트리** — 그중 **무엇이 이 온톨로지의 클래스인지**, 그리고 라벨로는 표현할 수
   없는 것(데이터소스 바인딩·behavior·base condition·PII)을 담는다.

2층이 필요한 이유는 두 가지이고 둘 다 회피할 수 없다.

- 위 표대로 **남의 라벨과 구분해야 한다.** `db.labels()` 를 그대로 클래스 목록으로 쓰면
  `FUNCTION`·`Column` 이 온톨로지 클래스로 보고된다.
- **Neo4j Community 에는 바인딩을 담을 자리가 없다.** existence/node-key/property-type
  제약이 전부 Enterprise 이고, 라벨에 "이 클래스는 `manufacturing.mfg_daily_equipment` 에
  이 SQL 로 매핑된다"를 붙이는 수단은 어느 에디션에도 없다.

---

## 발행 표현

### 1층 — 네이티브

| 온톨로지 | 그래프 자체의 스키마 |
|---|---|
| 클래스 | 라벨 |
| 키 컬럼 | `CREATE CONSTRAINT ... FOR (n:<Class>) REQUIRE ... IS UNIQUE` |
| 속성 | 속성 키 (제약·인덱스가 참조하면 `db.propertyKeys()` 에 등재) |
| 관계 유형 | 관계 타입 |

### 2층 — 발행 레지스트리

`_` 접두를 쓴다. **domain-layer 가 이미** `:OntologySchema` · `:OntologyType` ·
`:OntologyBehavior` · `:Behavior` 를 **같은 그래프**에 쓰고 있어서, 접두 없이는 두 온톨로지가
섞인다 (↳ `domain-layer/app/services/schema_store.py:345,382,645`).

```
(:_OntologyModel {schema_id, name, description, intent, golden_questions, published_at, format_version})
  ├─[:HAS_CLASS]──→ (:_OntologyClass {class_name, description, binding_kind, properties, key_columns})
  │                    ├─[:HAS_BINDING]→ (:_OntologyBinding {datasource, source_schema, table,
  │                    │                     extra_tables, key_columns, column_map,
  │                    │                     base_conditions, label_property, default_limit})
  │                    │     └─[:HAS_BEHAVIOR]→ (:_OntologyBehavior {behavior_type:'sql', name,
  │                    │                            description, parameters, sql_template,
  │                    │                            output_columns, result_kind, max_rows,
  │                    │                            golden_question})
  │                    └─[:HAS_ACTION]→ (:_OntologyBehavior {behavior_type:'action', behavior_name,
  │                                        class_name, schema_id, description, parameters,
  │                                        key_property, system, operation_id, arg_mapping,
  │                                        effect, confirm_threshold, max_targets, policy,
  │                                        compensate, writeback_property, version})
  └─[:HAS_RELATIONSHIP]→ (:_OntologyRelationship {name, from_class, to_class, description, properties})
```

**`_OntologyBehavior` 는 판별자 `behavior_type` 로 종류를 가른다** (spec 014,
[`ontology-metamodel-direction.md`](ontology-metamodel-direction.md) §3·§6).

| `behavior_type` | 매달리는 곳 | 실행 주체 | 비고 |
|---|---|---|---|
| `'sql'` | 바인딩 아래 `HAS_BEHAVIOR` | neo4j-text2sql → MindsDB | 판별자가 **없는** 옛 발행물도 `'sql'` 로 읽는다 |
| `'action'` | 클래스 아래 `HAS_ACTION` | kinetic-action | 바인딩이 없는 materialized 클래스에도 붙는다 |

- 액션의 속성 의미·JSON 형식(`parameters`·`arg_mapping`·`policy` 는 JSON **문자열**)은
  [`specs/014-kinetic-action-layer/contracts/kinetic-api.md`](../specs/014-kinetic-action-layer/contracts/kinetic-api.md)
  §1 이 원천이다. 여기에 다시 적지 않는다.
- 런타임 리더(`ontology_runtime.get_binding`)는 `HAS_BEHAVIOR` 경로만 읽고, `behavior_type`
  이 `'sql'` 이 아닌 노드는 SQL 로 실행하지 않는다.
- 재발행 정리 범위 `(m)-[*1..3]->(child:_Ontology*)` 가 액션 노드(m→c→a, 깊이 2)를 덮는다 —
  지운 액션은 다음 발행에서 그래프에서도 사라진다. 발행 직후 스튜디오는 best-effort 로
  `POST {KINETIC_URL}/api/kinetic/catalog/refresh` 를 부른다(실패해도 발행은 성공).
- 액션 노드는 `_OntologyBehavior` 라벨이므로 외부 Cypher 표면의 발행 레지스트리 차단
  (`runtime_adapters.BLOCKED_LABELS_REGISTRY`)이 그대로 적용된다.

**자격증명은 어떤 노드에도 싣지 않는다.** 데이터소스는 이름으로만 지칭한다
(constitution V, spec 009 FR-003). 카탈로그의 `:DataSource` 노드가 `password` 를 평문으로
갖는 것과 대조된다 — 발행물은 그것을 복제하지 않는다.

`sql_template` 은 발행물에 **포함된다**(런타임이 behavior 를 실행하려면 필요하다). 대신
**MCP 응답에는 절대 나가지 않는다** (spec 001 FR-021).

---

## 읽기 계약 — 무엇을 어디서 얻는가

**클래스의 권위는 그래프 자체의 스키마 API 다.** 레지스트리는 스키마 API 가 구조적으로
담을 수 없는 것만 채운다. 어느 쪽에서 왔는지는 응답의 `property_source` / `native` /
`observed_in_graph` 로 드러난다 — 값이 비었을 때 정상인지 고장인지 구분하기 위해서다.

| 무엇 | 1순위 (그래프 스키마 API) | 이식성 | 채우지 못하는 부분 |
|---|---|---|---|
| **클래스 존재** | `CALL db.labels()` | **양쪽** | — (가상 클래스 포함 전부 나온다) |
| **키 컬럼** | `SHOW CONSTRAINTS ... 'ont_pub_'` | Neo4j 만 | ontological → 레지스트리 `key_columns` |
| 속성 | `CALL db.schema.nodeTypeProperties()` | Neo4j 만 | 가상 클래스(노드 0건)·ontological → 레지스트리 |
| 관계 | `CALL db.schema.visualization()` | Neo4j 만 | 가상 클래스가 걸린 관계·ontological → 레지스트리 |
| 바인딩·behavior | **없음** | — | 전부 레지스트리 |
| 인스턴스 | `MATCH (n:_Entity:<Class>)` | 양쪽 | — |

**`db.labels()` 가 클래스 존재의 권위다** — 두 백엔드가 모두 구현하고, 둘 다 인스턴스가
0건인 클래스를 포함하는 유일한 조회이기 때문이다. 다만 그것만으로는 부족하다. 같은 그래프에
카탈로그·text2sql·analyzer·domain-layer 의 라벨이 섞여 있으므로, **발행 레지스트리가 아는
이름과 교집합**을 취한다 — 레지스트리는 "무엇이 내 것인가"를, 스키마 API 는 "그중 실제로
그래프 스키마에 올라와 있는가"를 답한다.

처음에는 `SHOW CONSTRAINTS` 를 클래스 목록의 권위로 삼았는데, ontological-db 가 그 구문을
파싱하지 못해 **그 백엔드에서 클래스가 하나도 보이지 않았다.** 지금은 키를 얻는 보조 경로로만
쓴다.

### 실측 (`제조 하이브리드`, 클래스 8개)

```
SHOW CONSTRAINTS      → 8/8 클래스 (가상 3개 포함, 노드 0건인데도)
nodeTypeProperties()  → 5/8 (materialized 만 — 샘플링이므로)
schema.visualization()→ materialized 간 엣지만 observed=True
```

가상 클래스의 관계가 `observed_in_graph: false` 인 것은 **정상이다.** 인스턴스가 없으니
엣지도 없고, 두 세계는 키 값으로만 이어진다.

`ontology_runtime` 은 이 목록 밖의 조회를 하지 않는다. 백엔드 분기도 하지 않는다
(constitution 원칙 0 — 바뀌는 것은 `NEO4J_URI` 뿐). 계약 밖 프로시저 호출은
`backend/tests/modules/ontology_runtime/test_no_sqlite_dependency.py` 가 막는다.

카탈로그(`:Table`/`:Column`)를 읽을 때는 [`catalog-schema.md`](catalog-schema.md) 의 규칙을
그대로 따른다 — `coalesce(c.type, c.dtype)`, `coalesce(c.primary_key, c.is_primary_key)`,
`(t.datasource = $ds OR t.db = $ds)`.

---

## ontological-db — 실측 (2026-08-17, pull 후 재빌드)

같은 코드를 `NEO4J_URI`·자격증명·`NEO4J_DATABASE` 만 바꿔 두 번째 백엔드에서 돌린 결과다
(`scripts/verify_ontological_backend.py`). **발행·조회·에이전트 질의 전부 통과한다.**

| 능력 | Neo4j | ontological-db (수정 전) | **수정 후** |
|---|---|---|---|
| `db.labels()` (0-인스턴스 클래스 포함) | 예 | 예 | 예 |
| `CREATE CONSTRAINT` | 예 | 예 | 예 |
| `SHOW CONSTRAINTS` / `SHOW INDEXES` | 예 | 아니오 (SyntaxError) | **예** |
| `properties(n)` | 예 | 아니오 | **예** |
| `n[k]` 동적 속성 접근 | 예 | 아니오 (jsonb→int 캐스트) | **예** |
| 제약 선행 후 `(:_Entity:X)` 인스턴스 | 예 | 아니오 (영구 거부) | **예** |
| jsonb 컬럼 + 파라미터로 `STARTS WITH` | 예 | **조용히 0행** | **예** |
| `db.schema.visualization()` / `nodeTypeProperties()` | 예 | 아니오 | 아니오 (미구현) |
| `CREATE INDEX` (속성이 아직 없을 때) | 예 | 아니오 | 아니오 |

> **수정 후** 열은 `ontology-studio/ontological-db` 엔진에 넣은 변경이다. 회귀 검사는
> `engine/tests/neo4j_compat_fixes.py`. 스튜디오 쪽 대체 경로는 **그대로 둔다** — Neo4j 와
> 구버전 엔진을 위해 여전히 필요하고, 지금은 쓰이지 않을 뿐이다.

그래서 코드는 **분기하지 않고 시도 후 대체**한다. 클래스의 존재는 `db.labels()` 가 정하고
(양쪽 지원), 키·속성·관계는 지원되면 스키마 API 에서, 아니면 발행 레지스트리에서 온다.
어느 쪽에서 왔는지는 `property_source`·`native`·`observed_in_graph` 로 응답에 드러난다.

### 다섯 번째 결함 — 조용히 0행을 돌려주던 문자열 비교

능력 표에 없던 것이 하나 더 나왔다. `CALL … YIELD label WHERE label STARTS WITH $p` 가
**오류 없이 0행**을 돌려줬다. YIELD 로 나온 컬럼은 jsonb 인데 `jsonb::text` 는 따옴표를
남겨(`"Doc"`) `'Do%'` 와 절대 일치하지 않기 때문이다. 리터럴로 쓰면 타입 힌트가 먼저
값을 꺼내 줘서 **우연히** 동작했고, 그래서 파라미터로 바꾸는 순간에만 깨졌다.

오류가 아니라 빈 결과라는 점이 나쁘다 — 프로시저 출력을 파라미터로 거르는 코드는 어디서나
쓰인다. 엔진에서 문자열 술어의 양변을 **text 로 컴파일**하도록 고쳤다.

### 반드시 지켜야 할 순서 — 서브타입 선언이 제약보다 **먼저**

ontological-db 에는 **진짜 타입 시스템**이 있다. Neo4j 는 라벨을 자유로운 집합으로 보지만,
여기서는 한 노드가 `(:_Entity:MfgProduct)` 를 함께 지려면 둘이 한 상속 사슬 위에 있어야
한다. 실측으로 확인한 순서 의존:

```
_Entity 가 먼저 있고 클래스가 처음 등장  → 하위 타입으로 자동 선언, 인스턴스 생성 OK
제약이 먼저 클래스를 루트 타입으로 만듦   → 이후 (:_Entity:Class) 는 영구히 거부
   "no node can carry the labels (:_Entity:MfgProduct) at once —
    they are not on one inheritance chain, so there is no type to create"
```

그래서 발행은 제약보다 **먼저** 임시 노드를 하나 만들었다 지워 서브타입을 선언한다
(`publish._declare_subtype`). 남는 것은 타입 선언뿐이고 인스턴스 수는 0으로 돌아온다.
Neo4j 에서는 무해한 왕복이며, **양쪽에서 같은 Cypher 가 돈다** — 저장소 분기가 아니다.

이 순서를 지키지 않으면 증상이 고약하다. 발행은 성공하고 `db.labels()` 에도 클래스가
보이는데, 인스턴스 적재만 영구히 실패한다.

### `NEO4J_DATABASE` 는 ontological 에서 **그래프**를 고른다

스튜디오는 이 값을 읽지도 넘기지도 않았다. Neo4j Community 는 데이터베이스가 하나뿐이라
문제가 드러나지 않았지만, ontological-db 에서는 **모든 세션이 서버 기본 그래프로 가고 다른
그래프에 닿을 방법이 없다**는 뜻이었다. `tools.session_kwargs()` 가 이제 이 값을 전달한다.

> 실제로 이것 때문에 사고가 났다 — 시드 스크립트가 자체 세션을 열고 있어서 121개 인스턴스가
> 의도한 그래프가 아니라 **다른 그래프**에 적재됐다. 그래프를 여는 모든 경로가 같은 헬퍼를
> 거쳐야 한다.

## ontological-db (소스 확인)

`db.labels()` / `db.relationshipTypes()` / `db.propertyKeys()` 를 지원하며, **선언된 타입
카탈로그에서** 읽는다:

```rust
"db.labels" => "SELECT name FROM og_catalog.type WHERE graph_id = {gid} AND kind = 'e'"
```
↳ `ontology-studio/ontological-db/engine/src/compat/procs.rs:117`

즉 인스턴스가 0건인 타입도 나온다 — Neo4j 와 **결론이 같다**(분기 A). 다만 도달 경로가
다르다: Neo4j 는 제약 선언으로, ontological-db 는 타입 선언으로 등재된다.

ontological-db 에는 바인딩을 담을 네이티브 자리가 실제로 있다 —
`og_catalog.mapping {type_id, source_table, id_column, property_map, writable}`. 현재
**0행**이며 ontology-studio 는 이것을 쓰지 않는다. 2층 레지스트리를 이 테이블로 승격하는
것은 후속 과제이고, 지금은 두 백엔드에서 같은 Cypher 가 도는 표현을 쓴다.

> 이 절은 **소스 확인**이며 실측이 아니다. 실행 중인 `ontology-ontological` 인스턴스는 다른
> 작업이 쓰고 있어 쓰기 프로브를 돌리지 않았다. ontological 모드로 검증할 때 위 probe
> 스크립트를 그 인스턴스에 돌려 이 표를 채운다.


---

## 추출 인스턴스의 출처 속성 (spec 013)

문서 추출 경로(`quality/ingest_gate.py`)가 쓰는 `_Entity` 노드와 관계에 붙는다. 기존 적재분에는
없을 수 있으므로 읽을 때는 `coalesce` 한다.

| 속성 | 대상 | 의미 |
|---|---|---|
| `_source_id` | 노드 | MERGE 키. 파서 id, 없으면 `클래스:이름` |
| `_confidence` | 노드·관계 | 처음 적재될 때의 복합 신뢰도 S_c. 사람이 승인한 것은 자동 적재 하한 이상 |
| `_run_id` | 노드·관계 | 처음 적재한 추출 실행 (`extraction_runs.run_id`) |
| `_evidence_ref` | 노드·관계 | `문서#청크@쪽:시작-끝` — 원문 근거 위치 |

트랜잭션 메타데이터: `actor`(`studio:auto` 또는 검수자), `source`(`extract:<run_id>`),
`reason`(`S_c=0.91` 또는 `hitl:approve`). ontological-db 는 이것을 감사 로그와 `__actor/__source`
스탬프로 남긴다(ontological spec 014). 예약어 `_id/_type/_src/_dst/__*` 는 쓰지 않는다.

S_graph(기존 그래프 지지도)는 `_confidence` 를 읽는다. 값이 없는 엣지는 0.7 로 본다.
