# Feature Specification: 그래프에 발행되는 온톨로지 + 하이브리드 RAG MCP

**Feature Branch**: `010-graph-published-ontology-mcp`

**Created**: 2026-08-17

**Status**: Implemented

**Input**: "ontology-studio 에서 만들어진 datasource 기반으로 된 서비스에 접근할 수 있는 MCP 를
만든다. graph 탐색과 데이터소스 탐색이 혼합된 agentic RAG 시나리오를 커버한다." + "스키마는
neo4j 자체의 스키마에 저장되어야 한다. ontology-studio 가 떠 있지 않은 실행 전용 환경에서도
동작하는 MCP 여야 하기 때문."

## 왜 이 스펙이 플랫폼 단위인가

세 저장소의 계약이 함께 걸린다 — 온톨로지 발행은 **ontology-studio**, 카탈로그는
**data-fabric**, SQL 실행은 **neo4j-text2sql**. 그리고 발행 형식은 [spec 009](../009-ontology-export-import/spec.md)
의 패키지 내용과 같은 것을 담는다. 하나를 되돌리면 계약이 깨진다.

관련: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) 원칙 0·I·II·III·IV·V ·
[`docs/graph-schema-contract.md`](../../docs/graph-schema-contract.md) ·
[spec 001](../001-datasource-backed-virtual-classes/spec.md) · [spec 009](../009-ontology-export-import/spec.md)

---

## 문제 정의

기업 지식그래프(관계·토폴로지)와 이종 데이터소스(대용량 시계열)를 **하나의 MCP 표면**으로
묶어야 한다. 세 가지가 동시에 걸린다.

1. **저장소 이원화** — 공간·토폴로지 관계는 그래프에, 일자별 대용량 시계열은 RDB 에 있다.
2. **스키마 과부하와 보안** — 두 층을 다 쓰려면 하부 스키마가 필요한데, 전체를 미리 넘기면
   토큰이 터지고 추론 정확도가 떨어지며 DB 구조가 전면 노출된다.
3. **런타임에는 스튜디오가 없다** — 그런데 온톨로지 모델(클래스·관계·바인딩·behavior)은
   스튜디오의 SQLite 에만 있었다. 그래프에는 **인스턴스와 데이터 패브릭 카탈로그만** 있다
   (spec 009 가 플랫폼 사실로 명시). 그래서 그래프만 있는 환경에서 MCP 는 빈 온톨로지를 봤다.

3번이 이 스펙의 무게중심이다. 1·2번만 풀면 스튜디오에 종속된 도구가 하나 더 생길 뿐이다.

### 실측으로 확인한 출발점 (2026-08-17)

- 스튜디오가 실행하는 Cypher 중 **스키마를 쓰는 것은 없다.** `schema_create_class` 독스트링이
  *"Create or update an ontology class in SQLite (source of truth)"* 이고 Cypher 0줄이다.
- `ontology-studio/docker-compose.yml` 의 `mcp` 서비스는 `depends_on: backend` 가 없어 **이미**
  스튜디오 없이 뜬다. 그런데 `SESSION_DB_PATH` 도 볼륨도 없어 **자기 컨테이너의 빈 SQLite** 를
  연다 — 조용히 빈 온톨로지를 보고한다.
- 발행/배포 개념이 코드에 없다.

---

## User Scenarios & Testing

### User Story 1 - 스튜디오 없이 온톨로지를 읽는다 (P1)

운영 환경에는 그래프 DB 와 MCP 서버만 있다. 스튜디오는 개발자 머신에 있고 꺼져 있다.

**Independent Test**: `SESSION_DB_PATH` 를 **존재하지 않는 경로**로 두고 MCP 를 띄워
`graph://schema` 를 읽으면 발행된 클래스가 나온다.

**Acceptance Scenarios**:

1. **Given** 온톨로지가 발행됐고 스튜디오가 꺼져 있고 **When** `graph://schema` 를 읽으면
   **Then** 클래스·관계·바인딩 종류가 반환된다
2. **Given** 아무것도 발행되지 않았고 **When** 리소스를 읽으면 **Then** 빈 배열이 아니라
   **발행하라는 안내**가 함께 온다 — 카탈로그가 빈 것과 구분돼야 한다
3. **Given** 발행 형식이 런타임보다 새롭고 **When** 모델을 나열하면 **Then** 조용히 건너뛰지
   않고 해석할 수 없다고 표시한다

### User Story 2 - 가상 클래스가 그래프 자체의 스키마에 등재된다 (P1)

가상 클래스는 인스턴스를 0건 유지한다. 데이터에서 유추하는 스키마 조회로는 영원히 보이지 않는다.

**Independent Test**: 발행 후 `CALL db.labels()` 에 가상 클래스가 나오고, 같은 라벨의 노드 수는
0 이다.

**Acceptance Scenarios**:

1. **Given** 가상 클래스를 발행했고 **When** `db.labels()` 를 부르면 **Then** 그 라벨이 나온다
2. **Given** 같은 상태에서 **When** 그 라벨의 노드를 세면 **Then** **0** 이다 (spec 001 SC-001)
3. **Given** 발행을 거두면 **When** `db.labels()` 를 다시 부르면 **Then** 그 라벨이 사라진다

### User Story 3 - 스키마를 필요한 만큼만 받는다 (P1)

**Independent Test**: 지도(`graph://schema`)에는 컬럼이 없고, 한 클래스를 지목했을 때만 그
클래스의 컬럼이 온다.

**Acceptance Scenarios**:

1. **Given** 가상 클래스가 여럿이고 **When** 지도를 읽으면 **Then** 어떤 클래스의 컬럼도 없다
2. **Given** 그래프 탐색 결과가 있고 **When** 노드를 받으면 **Then** 그 클래스에서 닿는 가상
   클래스와 **조인 컬럼**이 결과에 실려 온다
3. **Given** 클래스 하나를 지목하면 **When** 스키마를 요청하면 **Then** 그 클래스의 컬럼만 오고
   다른 클래스의 컬럼은 오지 않는다
4. **Given** 같은 클래스명이 여러 발행 그룹에 있고 **When** 그룹을 지정하지 않으면 **Then**
   임의로 고르지 않고 **모호하다고 알린다**

### User Story 4 - 집계는 DB 가 한다 (P2)

**Acceptance Scenarios**:

1. **Given** 바인딩된 테이블이고 **When** `GROUP BY` SQL 을 실행하면 **Then** 집계 결과가 온다
2. **Given** 바인딩되지 않은 테이블을 참조하면 **When** 실행하면 **Then** 거부되고 허용 테이블이
   함께 보고된다
3. **Given** 호출자가 `LIMIT` 을 쓰면 **When** 실행하면 **Then** 거부된다 — 상한은 시스템이 정한다

### Edge Cases

- **카탈로그와 온톨로지가 같은 그래프를 쓴다** → 외부 Cypher 로 `:DataSource` 를 읽으면 평문
  비밀번호가 나간다. 라벨 차단이 필요하고, `labels(n)` 문자열 비교 우회도 함께 막아야 한다.
- **발행 레지스트리에 `sql_template` 이 있다** → Cypher 로 레지스트리를 읽으면 FR-021 이
  우회된다. 레지스트리 라벨도 차단 대상이다.
- **같은 `schema.table` 이 두 데이터소스에 있다** → `:Table` 의 MERGE 키가 `(name, schema)` 라
  노드가 합쳐지고 `datasource` 속성은 마지막 writer 가 이긴다. 관계로는 닿는데 속성으로는 안
  닿는 상태가 되며, 증상이 "카탈로그가 비었다"라서 원인을 짚기 어렵다. **실제로 겪었다.**
- **FK 가 발행 묶음을 가로지른다** → 마스터와 일별을 따로 생성하면 둘을 잇는 FK 가 양쪽에서
  빠지고, 그래프에서 데이터소스로 건너갈 단서가 사라진다. **실제로 겪었다.**
- **CTE 이름을 테이블로 오인한다** → 정규식 테이블 추출이 `WITH x AS (...)` 의 `x` 를 미바인딩
  테이블로 보고 정상 질의를 거부한다.

---

## Requirements

### 발행

- **FR-001**: 시스템은 스키마 그룹을 그래프에 **발행**할 수 있어야 하며, 발행물은 클래스·관계·
  바인딩·behavior·구축 의도·골든 퀘스천을 담아야 한다 (spec 009 FR-002 와 같은 내용).
- **FR-002**: 발행물은 접속 자격증명(host·port·user·password)을 **어떤 형태로도** 포함해서는
  안 된다. 데이터소스는 이름으로만 지칭한다.
- **FR-003**: 발행은 **멱등**이어야 한다. 같은 그룹을 다시 발행해도 결과 상태가 같다.
- **FR-004**: 발행과 철회는 **자기 라벨 범위만** 건드려야 한다. 데이터 패브릭 카탈로그와 다른
  스키마 그룹, 다른 서비스의 노드를 지우거나 바꿔서는 안 된다.
- **FR-005**: 발행 전에 `dry_run` 으로 계획을 반환할 수 있어야 하며 그래프를 바꾸지 않아야 한다.
- **FR-006**: 클래스는 그래프 **자체의 스키마**에 등재돼야 한다 — 라벨로, 키는 제약으로.
  인스턴스가 0건인 가상 클래스도 등재돼야 하며, 이를 위해 **앵커 노드를 만들지 않는다**.

### 런타임 조회

- **FR-007**: 런타임 리더는 스튜디오의 SQLite 를 **읽지 않아야** 하며, 이것은 규율이 아니라
  import 그래프 검사로 강제돼야 한다.
- **FR-008**: 런타임 리더는 백엔드(Neo4j / ontological-db)에 따라 **분기하지 않아야** 한다.
  두 백엔드의 능력이 실제로 다르므로(아래 FR-008a), 분기 대신 **시도하고 안 되면 대체**한다.
- **FR-008a**: 발행은 클래스를 `_Entity` 의 **하위 타입으로 먼저 선언**한 뒤 제약을 만들어야
  한다. ontological-db 에는 진짜 타입 시스템이 있어, 제약이 클래스를 루트 타입으로 만들어
  버리면 그 뒤로 `(:_Entity:Class)` 인스턴스 생성이 **영구히 거부**된다.
- **FR-008b**: 그래프를 여는 **모든** 경로는 `NEO4J_DATABASE` 를 전달해야 한다. Neo4j 에서는
  데이터베이스, ontological-db 에서는 **그래프**를 고르는 값이며, 전달하지 않으면 서버 기본
  그래프 외에는 닿을 수 없다.
- **FR-009**: 발행된 것이 없을 때 빈 결과가 아니라 **발행이 필요하다는 사실**을 알려야 한다.
- **FR-010**: 클래스 **존재**의 권위는 그래프 자체의 스키마 API — `CALL db.labels()` 여야
  한다. 두 백엔드가 모두 구현하고, 둘 다 인스턴스가 0건인 클래스를 포함하는 유일한 조회다.
  - `db.labels()` 만으로는 부족하다. 같은 그래프에 카탈로그·text2sql·analyzer·domain-layer
    의 라벨이 섞여 있으므로 **발행 레지스트리가 아는 이름과 교집합**을 취한다.
  - 키는 `SHOW CONSTRAINTS` 에서 얻되 **보조 경로**다. ontological-db 는 그 구문을 파싱하지
    못하므로(실측) 그쪽에서는 레지스트리의 `key_columns` 가 같은 값을 준다.
  - 스키마 API 가 **구조적으로 담을 수 없는 것만** 레지스트리가 채운다 — 데이터소스 바인딩,
    behavior, 그리고 노드가 0건이라 `db.schema.nodeTypeProperties()` 에 잡히지 않는 가상
    클래스의 속성 목록.
  - 값이 어느 쪽에서 왔는지 응답에 밝혀야 한다(`property_source` · `native` ·
    `observed_in_graph`). 출처를 감추면 비어 있는 것이 정상인지 고장인지 구분할 수 없다.
- **FR-010a**: 스키마 API 에는 있는데 레지스트리에 없는 클래스는 **드러내야** 한다
  (`orphaned`). 조용히 빼면 발행이 반쯤 적용된 상태가 보이지 않는다.

### MCP 표면

- **FR-011**: 하이브리드 도구는 `MCP_ALLOW_DATASOURCE_EXPANSION` 이 켜졌을 때만 등록돼야 하며,
  꺼진 상태의 도구 목록은 기존 4개와 **정확히 같아야** 한다 (spec 001 SC-006).
- **FR-012**: 스키마 지도(`graph://schema`)에는 **컬럼이 포함되지 않아야** 한다.
- **FR-013**: 그래프 조회 결과의 노드에는 그 클래스에서 닿는 가상 클래스와 **조인 컬럼**이
  주석으로 실려야 한다.
- **FR-014**: 데이터소스 스키마 조회는 **요청한 클래스 하나**만 반환해야 한다.
- **FR-015**: `sql_template` 은 외부 표면에 **절대** 나타나지 않아야 한다 (spec 001 FR-021).
- **FR-016**: `pii` 로 표시된 컬럼은 반환에서 제외돼야 한다 (spec 001 FR-014).
- **FR-017**: 외부 Cypher 는 카탈로그 라벨(`DataSource`·`Schema`·`Table`·`Column`)과 발행
  레지스트리 라벨을 **참조할 수 없어야** 하며, `labels(n)` 문자열 비교 우회도 막아야 한다.
- **FR-018**: 자유 SQL 은 **발행된 바인딩의 테이블만** 참조할 수 있어야 하고, 데이터소스는
  호출자가 아니라 바인딩에서 도출돼야 한다.
- **FR-019**: 같은 클래스명이 여러 발행 그룹에 있으면 **모호하다고 보고**해야 한다.
- **FR-020**: 2-step 추론 가이드는 `skills/<name>/SKILL.md` 하나가 원천이어야 하며 파이썬에
  조립되지 않아야 한다.

### Key Entities

- **발행 모델**: 한 스키마 그룹의 그래프 투영. 형식 버전과 발행 시각을 갖는다.
- **발행 클래스 / 바인딩 / behavior**: spec 009 FR-002 가 정의한 내용을 그래프 노드로 담은 것.
- **네이티브 투영**: 클래스=라벨, 키=제약. 그래프 도구가 온톨로지를 그대로 보는 층.
- **`_datasource_refs`**: 그래프 결과에서 데이터소스로 건너가는 단서. 가상 클래스는 노드가
  없어 관계로 이어지지 않으므로 **키 값**으로만 이어진다.

---

## Success Criteria

- **SC-001**: `SESSION_DB_PATH` 가 **존재하지 않는 경로**인 상태에서 4단계 워크플로우가 전부
  동작한다. ↳ 실측 확인
- **SC-002**: 가상 클래스가 `db.labels()` 에 등재되면서 같은 라벨의 노드 수는 **정확히 0** 이다.
  ↳ 실측 확인 (3,510행을 조회한 뒤에도 0)
- **SC-003**: 스키마 지도에 컬럼이 포함되지 않는다. 8클래스(가상 3개) 기준 지도 7,574자,
  JIT 1건 1,994자 → 일괄 전달 대비 **31% 절감**, 컬럼 53개 중 13개만 수신.
  ↳ 실측 확인. 규모가 작아 절감폭도 작다 — 가상 20개면 62%, 100개면 68% (투영).
  ↳ [`docs/agentic-rag-walkthrough.md` — 토큰 비용](../../docs/agentic-rag-walkthrough.md)
- **SC-004**: `MATCH (d:DataSource) RETURN d.password` 가 거부된다. ↳ 실측 확인
- **SC-005**: 전 과정 응답에 `password`·`host`·`port`·`sql_template` 이 나타나지 않는다.
  ↳ 실측 확인
- **SC-006**: `MCP_ALLOW_DATASOURCE_EXPANSION` 이 꺼진 상태의 도구 목록이 기존 4개와 같다.
  ↳ MCP 프로토콜로 실측 확인
- **SC-007**: 같은 그룹을 세 번 발행해도 모델 노드가 1개다. ↳ 실측 확인
- **SC-008**: 발행 철회 후 데이터 패브릭 카탈로그의 `:Table` 수가 변하지 않는다. ↳ 실측 확인

### 실제 검증 상태 (2026-08-17)

| 검증 | 결과 |
|---|---|
| 단위 테스트 (`backend/tests`) | 631 passed |
| 그래프 스키마 API 실측 (T0) | 분기 A 확정 — 제약만으로 라벨 등재 |
| 발행 왕복 (실 Neo4j) | 26 checks passed |
| 런타임 전용 (SQLite 없는 경로) | 20 checks passed |
| 골든 퀘스천 E2E | 4단계 전부 통과 |
| MCP 프로토콜 (streamable HTTP) | 도구·리소스·프롬프트 전부 확인 |
| 에이전트 실사용 (gpt-4.1 · claude-opus-4-8, 8개 시나리오) | [`docs/agentic-rag-walkthrough.md`](../../docs/agentic-rag-walkthrough.md) |
| **ontological-db 백엔드** | `scripts/verify_ontological_backend.py` — 발행·조회·에이전트 질의 통과 |

**ontological-db 검증 (2026-08-17, pull 후 재빌드)**: 같은 코드로 통과했다. 다만 그 과정에서
세 가지 이식성 결함이 드러났고 전부 고쳤다 — ① `SHOW CONSTRAINTS`·`db.schema.*` 미지원,
② `properties(n)`·`n[k]` 미지원, ③ 서브타입 선언 순서. 상세는
[`docs/graph-schema-contract.md`](../../docs/graph-schema-contract.md) 의 "ontological-db — 실측".

**미검증**: `mfg_daily_*` 실데이터 SQL 은 두 백엔드 모두 같은 text2sql→MindsDB 경로를 쓰므로
그래프 백엔드와 무관하다. ontological 모드의 프론트엔드·포털은 이 작업 범위 밖이다.

---

## Assumptions

- 데이터소스 등록과 메타데이터 추출은 이 기능의 **선행 조건**이다.
- SQL 실행은 neo4j-text2sql 이 담당한다. 이 기능은 자격증명을 갖지 않는다.
- 스튜디오의 **원천은 여전히 SQLite** 다. 그래프 발행은 런타임을 위한 투영이며, 스튜디오 간
  이식(spec 009 의 파일 패키지)을 대체하지 않는다.
- 발행 레지스트리를 ontological-db 의 네이티브 `og_catalog.mapping` 으로 승격하는 것은 후속
  과제다. 지금은 두 백엔드에서 같은 Cypher 가 도는 표현을 쓴다.

## Out of Scope

- domain-layer 의 온톨로지 표현(`:OntologySchema`·`:OntologyType`)과의 통합. 같은 그래프에
  온톨로지 표현이 둘이라는 사실은 남으며, spec 008 이 이미 지적한 문제다.
- `:Table` MERGE 키를 고치는 일. 카탈로그의 writer 는 data-fabric 이다.
- SQL 파서 도입. 테이블 추출은 기존 정규식을 재사용하고 CTE 오탐만 줄였다.
