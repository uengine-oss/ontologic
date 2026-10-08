# Quickstart — 검증 가이드

**Feature**: 011-ontology-board

이 문서는 **구현이 실제로 동작하는지 확인하는 절차**다. 구현 방법이 아니라 실행과 판정을 적는다.
constitution 원칙 VII — *"단위 테스트만 통과한 것을 '동작한다'고 보고하지 않는다."*

---

## 0. 전제 — 인프라와 발행 모델

```bash
docker ps --format '{{.Names}}\t{{.Ports}}'    # robo-neo4j(7688) · robo-postgres(5433) · robo-mindsdb(47334)
```

발행된 모델이 없으면 만든다:

```bash
uv run python scripts/seed_hybrid_demo.py --datasource legacy
```

**기대**: `제조 하이브리드` — 클래스 9개(가상 4·materialized 5), 관계 10개.

계약이 여전히 유효한지 먼저 본다 (추측으로 고치지 않는다):

```bash
uv run --with neo4j python scripts/probe_graph_schema_api.py    # 기대: "판정: 분기 A"
```

---

## 1. MCP 서버를 띄운다 — 스튜디오 SQLite 없이

```bash
cd ontology-studio
SESSION_DB_PATH=/nonexistent/none.db \
MCP_TRANSPORT=http MCP_PORT=8100 MCP_ALLOW_DATASOURCE_EXPANSION=true \
  uv run python -m backend.src.modules.ontology_mcp
```

`SESSION_DB_PATH` 가 **존재하지 않는 경로**인 것이 요점이다 — 에이전트가 보는 온톨로지가 전부
그래프에서 온다는 것을 이 한 줄이 보장한다 (R-7).

---

## 2. 계약 프로브 — 코드가 MCP 를 부른다

```bash
uv run python scripts/probe_board_mcp.py --transport http --url http://127.0.0.1:8100/mcp
```

이 스크립트는 `scripts/agentic_rag_session.py` 와 같은 자리에 두되 **LLM 을 부르지 않는다.**
`ClientSession` 으로 붙어 도구를 직접 호출하고 응답 원문을 `demo/board-probe/` 에 남긴다.

**판정 (contracts/mcp-consumption.md §깨짐 감지)**:

| # | 확인 | 기대 |
|---|---|---|
| 1 | `resources/read graph://schema` | `classes[]` 에 `property_names` 가 있고 **타입이 없다** |
| 2 | `ontology_get_datasource_schema("MfgProduct")` | **거절** — materialized 이므로 |
| 3 | `ontology_get_datasource_schema("MfgDailyEquipment")` | `columns[].type` 이 채워져 온다 |
| 4 | `ontology_graph_cypher("MATCH (n:_Entity:MfgProduct) RETURN n LIMIT 2")` | 최상단에 `_datasource_refs`, `join_on: "product_id = product_id"` |
| 5 | `ontology_graph_cypher("MATCH (n:_Entity:MfgProductBom) RETURN n.product_id AS pid")` | **20행**, `truncated: true` |
| 6 | `ontology_graph_cypher("MATCH (n:_Entity:MfgProductBom) RETURN count(n) AS c")` | **33** — 총계는 상한과 무관 |
| 7 | 플래그 off 로 재기동 후 `tools/list` | **정확히 4개** (FR-080) |
| 8 | `ontology_graph_cypher("MATCH (n:Table) RETURN n")` | 거부 |
| 9 | `ontology_graph_cypher("MATCH (n) WHERE 'DataSource' IN labels(n) RETURN n")` | 거부 (문자열 우회 차단) |

5·6 의 **20 대 33** 이 이 기능의 핵심 제약을 눈으로 확인하는 지점이다.

---

## 3. 백엔드 단위·구조 테스트

```bash
cd ontology-studio
uv run --with pytest pytest backend/tests/modules/board -q
```

**반드시 통과해야 하는 것**:

- `test_no_direct_graph_access.py` — `modules/board/` 가 `neo4j` · `ontology_runtime` ·
  `session_store` · `agent_session` · `ontology.tools` 를 import 하지 않는다 (FR-001·FR-002).
  `ontology_runtime/test_no_sqlite_dependency.py` 의 AST 검사를 본뜬다
- `test_widget_map.py` — 같은 프로파일 → 같은 위젯 (FR-020 결정성). 규칙 O1~O10 각각의 최소 사례
- `test_query_gen.py` — 생성된 Cypher 에 `CALL` 이 없고, 필터 값이 항상 `params` 로 간다
  (FR-031·FR-032). 값이 `"Table"` 인 필터로 회귀 테스트를 만든다
- `test_spec_invariants.py` — `DashboardSpec` 에 `password`/`host`/`SELECT`/`MATCH` 가 있으면
  저장이 거부된다 (FR-061·SC-005)

---

## 4. 전체 스택 E2E

```bash
./start-all-services.sh          # 또는 최소: data-fabric 8004 · text2sql 8020 · studio 백엔드
```

```bash
curl -s http://127.0.0.1:8010/api/board/health | jq
```

**기대**: `{"mcp":"ok","datasource_expansion":true,"row_budget":{"cypher":20,"sql":30}}`

`datasource_expansion:false` 면 가상 클래스 위젯이 안 된다는 뜻이고, **UI 가 그 사실을 말해야
한다** (FR-004) — 빈 차트로 두면 실패다.

### 시나리오 판정

| # | 조작 | 기대 | 대응 요구 |
|---|---|---|---|
| S1 | `MfgProduct` 를 캔버스에 드롭 | 위젯이 그려지고 `rule`·`reason` 이 보인다 | US1-1, FR-022 |
| S2 | `MfgDailyEquipment`(가상) 드롭 | 컬럼이 JIT 로 오고 시계열 위젯 | US1-1 |
| S3 | 플래그를 끄고 S2 반복 | 위젯 없음 + 서버 문구 그대로 표시 | US1-3, G8 |
| S4 | `MfgProductBom` 드롭 | 배지 **"33건 중 20건"** | FR-034, SC-006 |
| S5 | X축 라벨 클릭 | 그 축의 인스펙터가 열린다 | US2-1, FR-041 |
| S6 | 위젯 종류 수동 변경 후 저장·재열기 | 수동 선택이 유지된다 (`pinned`) | US2-2, FR-043 |
| S7 | 위젯 선택 후 *"지역별로 쪼개줘"* | diff 가 먼저 뜬다. 승인해야 적용 | US3-1, FR-052 |
| S8 | 없는 속성을 참조하는 패치 | 거부, 대시보드 불변 | US3-2, FR-051 |
| S9 | 저장 후 파일 열기 | `password`·`host`·`SELECT` **0건** | US4-1, SC-005 |
| S10 | 클래스를 unpublish 후 재열기 | 그 위젯만 `missing_class`, 나머지는 그려진다 | US4-2, FR-062 |
| S11 | Superset 내보내기 | materialized 위젯이 `excluded[]` 에 사유와 함께 | US5-2, FR-071 |

---

## 5. 결정성과 성능

```bash
# SC-008 — 같은 스펙을 두 번 열면 같은 위젯
uv run python scripts/probe_board_mcp.py --recommend-all --repeat 2 --diff
```

**기대**: 두 실행의 `widget_kind`·`rule`·축 매핑이 **완전히 같다.**

**SC-003** — 9개 클래스 전부에 위젯이 정해지고 폴백(`table`)이 아닌 것이 **5개 이상**.
**SC-002** — 드롭 → 렌더 **3초 이내** (프로파일 캐시 미스 포함).

---

## 6. ontological-db 이식성

```bash
uv run python scripts/verify_ontological_backend.py
```

생성된 Cypher 가 `properties(n)` 과 동적 `n[k]` 를 쓰지 않는지 **여기서 드러난다**
(constitution 원칙 0). Neo4j 에서만 돌고 여기서 죽으면 FR-010 위반이다.

---

## 7. 영상 증거 (완료 판정)

전략 §6 규칙 — **구현 작업은 영상 증거 없이 완료로 치지 않는다.**

```bash
cd ontology-studio/demo && HEADLESS=false npx playwright test board
```

- 보관: `docs/business/evidence/<번호>-<이름>/` — 영상 + 캡처 + 무엇을 보여주는지 적은 `README.md`
- 스크린샷은 **CSS 트랜지션이 끝난 뒤** 찍는다 (원칙 VII)
- 되지 않는 부분은 **숨기지 말고 그대로 녹화하고** 무엇이 안 되는지 적는다

최소한 S1 · S4 · S5 · S7 · S11 이 영상에 있어야 한다 — 각각 자동 매핑 · 정직한 잘림 표시 ·
위지윅 · 바이브코딩 · 내보내기 한계를 보여주는 장면이다.
