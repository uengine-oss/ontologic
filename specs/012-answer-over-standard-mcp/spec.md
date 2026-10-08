# Feature Specification: 스튜디오 질의응답을 표준 MCP 경유로 전환

**Feature Branch**: `012-answer-over-standard-mcp`

**Created**: 2026-08-19

**Status**: Implemented

**Input**: "현재 ontology studio 의 질의응답 기능은 표준 MCP 를 기반하고 있지 않다. 아마 결과를
보여줄 때 온톨로지의 궤적이라든지 등의 효과 때문에 부족할지 모르지만, 표준 MCP 를 경유하여
질의가 이뤄지는 형태가 표준적으로 좋을 것 같다."

## 왜 이 스펙이 플랫폼 단위인가

바꾸는 코드는 ontology-studio 안에만 있지만, **바꾸는 계약은 그 밖에 있다.**

- 질의 표면이 [spec 010](../010-graph-published-ontology-mcp/spec.md) 의 MCP 도구 목록에
  묶인다. 그 목록이 바뀌면 스튜디오 질의응답이 함께 바뀐다.
- 질의가 읽는 온톨로지의 출처가 스튜디오 SQLite 에서 **발행된 그래프**로 옮겨간다
  ([`docs/graph-schema-contract.md`](../../docs/graph-schema-contract.md)).
- 새 런타임 의존성이 생긴다 — 스튜디오 백엔드가 MCP 서버(8100)에 **붙어야** 답한다.
  포트·기동 순서는 루트 계약이다 (constitution VIII).
- 헌법의 "답변 에이전트는 `behavior_list` 를 먼저 호출해야 한다 — 이것이 가상 클래스의
  유일한 발견 경로다" 항목이 **더 이상 사실이 아니게 된다.** 헌법 개정이 수반된다.

관련: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) 원칙 V·VI·VII ·
[spec 001](../001-datasource-backed-virtual-classes/spec.md) ·
[spec 004](../004-pluggable-agent-backend/spec.md) ·
[spec 010](../010-graph-published-ontology-mcp/spec.md) ·
[spec 011](../011-ontology-board/spec.md)

---

## 문제 정의

스튜디오의 질의응답은 **자기 프로세스 안의 파이썬 함수**를 도구로 쥔다.
`agent_session/service.py` 의 `_ANSWER_MODE_TOOLS` 가 그 목록이다 — `vector_search`,
`neo4j_cypher_readonly`, `behavior_list`, `behavior_invoke`, `entity_fetch`,
`datasource_sql_query`.

같은 저장소 안에 **표준 MCP 표면이 이미 있다.** spec 010 이 만든 `ontology_mcp` 서버가
`ontology_resolve_entity` · `ontology_graph_cypher` · `ontology_get_datasource_schema` ·
`ontology_query_datasource_sql` 과 `graph://schema` 리소스를 제공한다. spec 011 의 board 는
같은 저장소 안에 있으면서도 **이미 그 MCP 를 경유해서만** 데이터에 닿는다.

즉 지금은 **같은 그래프를 읽는 두 개의 표면**이 있고, 질의응답만 표준 표면 밖에 있다.

### 두 표면이 갈라져서 생기는 것 (실측)

| | 내장 질의응답 (`_ANSWER_MODE_TOOLS`) | 표준 MCP (`ontology_mcp`) |
|---|---|---|
| 온톨로지 출처 | 스튜디오 SQLite | **발행된 그래프** (스튜디오 없이 동작) |
| 카탈로그 라벨 차단 | **없음** — `MATCH (d:DataSource) RETURN d.password` 가 통과한다 | `BLOCKED_LABELS` 로 차단 |
| 발행 레지스트리(`_Ontology*`) 차단 | 없음 | 차단 (`sql_template` 유출 방지) |
| PII 컬럼 제거 | behavior 정의에 의존 | `get_datasource_schema` 가 `pii` 컬럼을 제거 |
| 스키마 전달량 | `behavior_list()` 가 **모든 가상 클래스의 모든 컬럼**을 한 번에 | 클래스 하나씩 JIT |
| 바인딩 테이블 밖 SQL | 금지(behavior 경유) | 금지(`prepare_scoped_adhoc_sql`) |

`runtime_adapters.py` 의 주석이 첫 두 줄을 그대로 적어 두었다 — 스튜디오 UI 안에서는
운영자가 보는 것이지만, 같은 질의 경로를 외부에 열면 그것이 곧 자격증명 유출이다.

그리고 세 번째 문제: **개선이 두 번 필요하다.** JIT 스키마 전달(spec 010 의 무게중심)은 MCP
표면에만 들어갔다. 스튜디오 UI 로 물으면 여전히 `behavior_list()` 가 전부를 쏟아낸다.

### 왜 지금까지 미뤄졌는가 — 궤적(trajectory)

스튜디오 화면은 답변만 보여주지 않는다. 에이전트가 **어느 노드를 지나갔는지**를 그래프에
하이라이트한다. 그 경로는 `service.py:1335` 가 도구 결과를 파싱해 만든다:

```python
_QA_NODE_TOOLS = {"entity_search", "neo4j_cypher_readonly", "vector_search"}
if tool_name in _QA_NODE_TOOLS:
    node_ids = _extract_node_ids(content, tool_name)
    if node_ids:
        events.append(_format_sse("traversed_nodes", {"tool": tool_name, "node_ids": node_ids}))
```

**도구 이름과 결과 모양에 붙어 있다.** 도구를 MCP 로 갈아끼우면 이 집합에 아무것도 걸리지
않고, 궤적이 조용히 사라진다. 화면은 그대로 동작하는 것처럼 보이므로 테스트 없이는 눈치채기
어렵다 — 이 스펙에서 가장 회귀하기 쉬운 지점이 여기다.

---

## User Scenarios & Testing

### User Story 1 - 질의가 표준 MCP 를 경유한다 (P1)

사용자가 스튜디오 화면에서 질문한다. 답은 지금과 같이 나오지만, 그 답을 만든 도구 호출은
전부 MCP 서버를 지나간다.

**Independent Test**: MCP 서버 로그(또는 목 트랜스포트)에 `ontology_graph_cypher` 호출이
남고, 스튜디오 프로세스에서는 `neo4j_cypher_readonly` 가 호출되지 않는다.

**Acceptance Scenarios**:

1. **Given** MCP 서버가 떠 있고 온톨로지가 발행돼 있고, **When** 화면에서 그래프 질문을
   하면, **Then** 답변이 나오고 도구 호출은 MCP 표면의 이름(`ontology_*`)으로 기록된다
2. **Given** 같은 상태에서 **When** 수치·집계 질문을 하면, **Then**
   `ontology_get_datasource_schema` → `ontology_query_datasource_sql` 순서로 호출된다
3. **Given** 답변 모드에서 **When** 도구 목록을 보면, **Then** 쓰기 도구가 하나도 없다

### User Story 2 - 궤적이 그대로 보인다 (P1)

**이 스펙이 통과했다고 말할 수 있는 유일한 화면 근거다.**

**Independent Test**: MCP 경유로 답한 뒤 `traversed_nodes` SSE 이벤트가 프런트에 도달하고,
그래프에서 지나간 노드가 하이라이트된다.

**Acceptance Scenarios**:

1. **Given** MCP 경유 질의가 그래프 노드를 반환했고, **When** 스트림을 보면, **Then**
   `traversed_nodes` 이벤트가 그 노드 id 를 싣고 온다
2. **Given** `ontology_list_entities` 가 시맨틱 검색으로 노드를 찾았고, **When** 스트림을
   보면, **Then** 그 노드들도 궤적에 포함된다
3. **Given** 가상 클래스 조회처럼 **노드가 없는** 결과라면, **When** 스트림을 보면,
   **Then** 궤적 이벤트를 만들지 않는다 (빈 배열을 보내 하이라이트를 지우지 않는다)

### User Story 3 - MCP 에 못 붙으면 그 사실을 말한다 (P1)

MCP 서버가 꺼져 있다. 사용자는 "답이 안 나온다"가 아니라 **왜 안 나오는지**를 봐야 한다.

**Independent Test**: MCP 를 내리고 질문하면, 추측 답변 대신 연결 실패 안내가 나온다.

**Acceptance Scenarios**:

1. **Given** MCP 서버가 꺼져 있고, **When** 질문하면, **Then** *"온톨로지 MCP 에 연결하지
   못했습니다"* 와 접속 대상(transport·URL)과 **실제 사유**가 함께 표시되고, 에이전트는 도구
   없이 답을 지어내지 않는다. anyio 가 감싼 `ExceptionGroup` 을 그대로 찍어 *"unhandled
   errors in a TaskGroup"* 만 남기면 사용자는 무엇을 고쳐야 할지 알 수 없다
2. **Given** MCP 는 떠 있지만 `MCP_ALLOW_DATASOURCE_EXPANSION` 이 꺼져 있고, **When**
   질문하면, **Then** 등록된 도구만으로 답하고, 데이터소스 질문에는 확장이 꺼져 있다고
   말한다 (조용히 빈 결과로 답하지 않는다)
3. **Given** 온톨로지가 아직 발행되지 않았고, **When** 질문하면, **Then**
   `graph://schema` 가 돌려주는 **발행 안내**가 그대로 사용자에게 전달된다

### User Story 4 - 두 에이전트 백엔드가 같은 표면을 본다 (P2)

`AGENT_BACKEND` 를 `deepagents` ↔ `cliagents` 로 바꿔도 답변 모드가 쥐는 도구가 같아야 한다
(spec 004 FR-011).

**Independent Test**: `tools_for("answer")` 와 내장 에이전트의 도구 목록이 **같은 함수
객체**다.

**Acceptance Scenarios**:

1. **Given** MCP 경유가 켜져 있고, **When** agent-bridge 의 answer 모드 도구를 나열하면,
   **Then** 내장 에이전트와 같은 목록이 나온다
2. **Given** `answer_nods` 모드에서, **When** 도구를 나열하면, **Then** 데이터소스에 닿는
   도구가 하나도 없다

### Edge Cases

- **자기 자신 호출.** MCP 서버의 `ontology_query` 도구는 답변 에이전트를 구동한다. 그
  에이전트가 다시 MCP 로 붙으면 같은 서버로 되돌아온다. 재귀가 되지 않는 유일한 이유는
  **답변 모드 도구 목록에 `ontology_query` 가 없기** 때문이다. 이 제외는 우연이 아니라 계약이다.
- **MCP 도구 목록이 서버마다 다르다.** `MCP_ALLOW_DATASOURCE_EXPANSION` 이 도구 등록을
  가른다. 클라이언트는 목록을 **물어보고** 있는 것만 등록해야 한다. 있다고 가정하고 부르면
  런타임에 "unknown tool" 로 실패한다.
- **비동기/동기 경계.** 내장 에이전트의 스트림은 전용 스레드에서 **동기**로 돈다. 같은 도구
  함수가 agent-bridge(FastMCP, 이벤트 루프 안)에도 등록된다. 도구는 두 문맥 모두에서
  호출 가능해야 한다.
- **세션 수명.** MCP SDK 세션은 진입한 anyio 태스크에서 나가야 한다. 호출 단위로 열고
  닫는다 (board 가 같은 이유로 같은 선택을 했다).

---

## Requirements

### 질의 경로

- **FR-001**: 답변 모드(`answer`·`answer_nods`)의 그래프·데이터소스 도구는 **표준 MCP
  서버(`ontology_mcp`)를 경유**해야 한다. 스튜디오 프로세스가 Neo4j 드라이버나 데이터소스
  커넥션을 직접 잡는 질의 경로가 답변 모드에 남아 있으면 안 된다.
- **FR-002**: 등록되는 도구는 MCP 서버에 **실제로 존재하는 것만**이어야 한다. 클라이언트는
  세션을 열어 `list_tools()` 로 확인한 뒤 그 목록에서 도구를 만든다.
- **FR-003**: `graph://schema` 는 MCP 에서 **리소스**다. 리소스를 읽을 수 없는 도구 전용
  에이전트를 위해 스튜디오가 이를 도구 하나(`ontology_graph_schema`)로 감싸되, 그 도구는
  **리소스를 읽어서** 돌려줘야 한다. spec 010 의 도구 목록(SC-006)은 늘어나지 않는다.
- **FR-004**: 답변 모드는 `ontology_query` 를 도구로 갖지 않는다 (재귀 금지, 위 Edge Case).
- **FR-005**: 샌드박스 읽기(`sandbox_read`)는 MCP 표면에 대응물이 없고 그래프·데이터에
  닿지 않으므로 **로컬 도구로 남는다.** 답변 모드의 로컬 도구는 이것뿐이다.
- **FR-006**: 도구 함수는 **동기 호출과 비동기 문맥 양쪽**에서 호출 가능해야 한다. 실행 중인
  이벤트 루프가 있으면 별도 스레드의 루프에서 코루틴을 돌린다.

### 궤적 (trajectory)

- **FR-010**: MCP 경유 도구 결과에서도 노드 id 를 추출해 `traversed_nodes` SSE 이벤트를
  내보내야 한다. 대상 도구는 최소한 `ontology_graph_cypher` · `ontology_list_entities` ·
  `ontology_resolve_entity` 다.
- **FR-011**: 노드 id 추출은 MCP 응답의 **감싼 모양**(`{"nodes": [...]}`,
  `{"entities": [...]}`, `{"results": [...]}`, `{"matches": [...]}`)을 풀어서 봐야 한다.
  최상위 리스트만 보는 구현은 MCP 응답에서 언제나 0건을 낸다.
- **FR-012**: 추출된 id 가 없으면 이벤트를 만들지 않는다. 빈 배열을 보내 기존 하이라이트를
  지우지 않는다.
- **FR-013**: MCP 표면의 그래프 응답은 **노드 element id 를 실어야 한다.** 실측 결과
  `ontology_graph_cypher` 는 노드를 `dict(node)` 로만 돌려주고 `ontology_resolve_entity` 는
  `properties` 만 돌려줘서, 궤적을 되짚을 근거가 아예 없었다. 새로 드러나는 정보가 아니다 —
  `ontology_query` 의 `sources` 가 이미 같은 값을 내보낸다.

### 지시문

- **FR-020**: 답변 모드의 시스템 프롬프트는 **그 모드가 실제로 쥔 도구를 설명하는 SKILL.md
  하나**여야 한다 (constitution — 지시문은 SKILL.md 하나가 원천). MCP 경유일 때는
  `ontologic-agentic-rag`, 레거시 경로일 때는 `ontology-answer` 다.
- **FR-021**: 파이썬에서 도구 목록을 문장으로 조립해 프롬프트에 덧붙이지 않는다. 백엔드가
  넘기는 것은 **값**(환경 바인딩 블록)뿐이다.

### 설정과 운영

- **FR-030**: `ANSWER_TOOLS_VIA_MCP` 로 경유 여부를 고를 수 있어야 하며 **기본값은 켜짐**
  이다. 끄면 기존 내장 도구 목록으로 돌아간다 (탈출구).
- **FR-031**: 접속 설정(`ANSWER_MCP_TRANSPORT` · `ANSWER_MCP_URL` · `ANSWER_MCP_COMMAND` ·
  `ANSWER_MCP_TIMEOUT`)은 **루트 `.env`** 에 둔다. 서브모듈에 `.env` 를 만들지 않는다
  (원칙 VI).
- **FR-032**: URL 은 어떤 형태로 주든 `.../mcp` 하나로 정규화해야 한다. `/mcp/mcp` 나
  `/mcp` 누락이 생기면 안 된다 (원칙 VI 가 기록한 반복 사고).
- **FR-033**: 값이 없으면 MCP 서버 자신의 설정(`MCP_PORT`)에서 유도한다. `MCP_HOST` 는
  바인드 주소이므로 접속 주소로 쓰지 않는다.
- **FR-034**: MCP 에 닿지 못하면 **명시적으로 실패**해야 한다. 조용히 레거시 도구로
  되돌아가지 않는다 — 그러면 사용자는 어느 경로로 답했는지 알 수 없다.

### 경계

- **FR-040**: 이 스펙은 `ontology_mcp` 의 도구 목록·권한 경계를 넓히지 않는다. 답변 모드가
  더 필요한 것이 있어도 MCP 서버에 쓰기 도구를 추가하는 방식으로 풀지 않는다
  (spec 004 FR-013).
- **FR-041**: 빌드 모드(`build`)는 이 스펙의 대상이 **아니다.** 빌드는 쓰기이고 표준 MCP
  표면은 읽기 전용이다.

### 코드 중복 금지

- **FR-050**: MCP 클라이언트(세션·정규화·결과 언랩)는 **한 곳**에만 있어야 한다. board 와
  답변 모드가 같은 구현을 쓴다. 두 벌이 생기면 원칙 III 이 경고하는 divergence 가 재현된다.

---

## Success Criteria

- **SC-001**: MCP 경유가 켜진 상태에서 답변 모드 도구 목록에 `neo4j_cypher_readonly` ·
  `behavior_list` · `behavior_invoke` · `datasource_sql_query` 가 **하나도 없다.**
- **SC-002**: 같은 상태에서 도구 이름이 전부 `ontology_` 로 시작하거나 `sandbox_read` 다.
- **SC-003**: `ontology_graph_cypher` · `ontology_list_entities` · `ontology_resolve_entity`
  의 MCP 응답 모양에서 `traversed_nodes` 이벤트가 만들어진다 (단위 테스트로 고정).
- **SC-004**: `tools_for("answer")` == 내장 답변 에이전트의 도구 목록 (같은 함수 객체).
- **SC-005**: `tools_for("answer_nods")` 에 데이터소스 도구가 없다.
- **SC-006**: MCP 를 내린 상태에서 질문하면 접속 대상이 포함된 실패 메시지가 나온다.
- **SC-007**: MCP 클라이언트 구현 파일이 저장소에 **하나**다 (board 는 재수출만 한다).
- **SC-008**: `ANSWER_TOOLS_VIA_MCP=false` 로 두면 기존 동작이 그대로 재현된다.

---

## 운영 영향 (읽고 넘어가지 말 것)

**질의응답이 새 프로세스에 의존하게 된다.** 지금까지 스튜디오 백엔드만 띄우면 답했다. 이제
`ontology_mcp`(8100)가 함께 떠 있어야 한다. `docker-compose.yml` 의 `mcp` 서비스가 그것이고,
로컬에서는 다음으로 띄운다:

```bash
cd ontology-studio
MCP_TRANSPORT=http MCP_PORT=8100 MCP_ALLOW_DATASOURCE_EXPANSION=true \
  uv run python -m backend.src.modules.ontology_mcp
```

**`MCP_ALLOW_DATASOURCE_EXPANSION` 이 꺼져 있으면 데이터소스 질문에 답하지 못한다.**
compose 의 기본값은 `false` 다 — 외부 클라이언트를 상정한 값이다. board 가 이미 같은 전제를
갖고 있으므로(spec 011), 스튜디오를 온전히 쓰는 배포는 이 값을 켠 인스턴스를 쓴다.

**온톨로지를 발행하지 않으면 답하지 못한다.** MCP 는 스튜디오 SQLite 가 아니라 그래프를
읽는다. `POST /api/schema/{id}/publish` 가 선행 조건이다. 발행 전에는 `graph://schema` 가
빈 배열이 아니라 발행 안내를 돌려주므로(spec 010 US1), 사용자는 이유를 본다.

---

## 실측 검증 (2026-08-19)

단위 테스트만 통과한 것을 "동작한다"고 보지 않는다 (constitution VII). 실제 그래프
(`bolt://localhost:7688`, 발행 모델 `미국 전력망` · `제조 하이브리드`)와 별도 MCP 인스턴스
(127.0.0.1:8150, 확장 켬)로 답변 턴을 돌린 결과:

| 확인한 것 | 결과 |
|---|---|
| 도구 표면 | `sandbox_read` · `ontology_graph_schema` · `ontology_get_datasource_schema` · `ontology_graph_cypher` · `ontology_query_datasource_sql` — 전부 MCP 이름 |
| 그래프 질문 | 상위 3개 변전소를 정확히 답함 (94.5 / 92.0 / 89.6%) |
| 궤적 | `traversed_nodes` 2회, 노드 6개. 최상위 행의 id 가 실제 Houston 변전소 노드와 일치 |
| 데이터소스 질문 | `graph_schema` → `get_datasource_schema` → `query_datasource_sql` 순서로 진행, DB 가 집계, 답변에 `legacy.manufacturing.mfg_daily_equipment` 와 행 수 명시 |
| 가상 클래스 질의의 궤적 | 0건 — 노드가 없으므로 이벤트를 만들지 않음 (FR-012 그대로) |

### 브라우저 검증 (Playwright, 2026-08-20)

CLI 로 도는 것과 **화면에 궤적이 남는 것**은 다른 문제다. 그래서 실제 브라우저로 한 번 더
돌렸다 — `tests/e2e_answer_over_mcp_traversal.spec.js`, 녹화와 근거는
[`ontology-studio/demo/spec-012/`](../../ontology-studio/demo/spec-012/README.md).

| 확인한 것 | 결과 |
|---|---|
| 도구 칩 | `sandbox_read` · `ontology_graph_schema` · `ontology_list_schemas` · `ontology_get_datasource_schema` · `ontology_graph_cypher` — 내장 도구 0개 |
| 궤적 이벤트 | `traversed_nodes` 2회, 노드 id 6개 |
| **그래프 하이라이트** | cytoscape `.traversed` **3개**, `.faded` **197개** |
| 답변 | Houston 94.5% · Atlanta 92.0% · Philadelphia 89.6% |

SSE 이벤트가 왔다는 것으로 통과시키지 않는다. 하이라이트는 canvas 라서 DOM 으로 보이지
않으므로, cytoscape 인스턴스에 `.traversed` 클래스가 **실제로 붙었는지**까지 확인한다.

**여기서 또 하나가 잡혔다.** 브라우저에서는 답이 정상인데 궤적만 0건이었다. 원인은 도구
결과의 봉투였다 — `structuredContent` 없이 텍스트만 오는 응답에서 FastMCP 의
`{"result": "<json 문자열>"}` 한 겹을 벗기지 않고 있었다. 모델은 봉투 안을 읽으므로 답변은
그대로 나오고, 노드 id 를 파싱하는 쪽만 최상위에서 `result` 하나를 보고 0건을 낸다.
**"답이 나오니 잘 되는 줄 아는"** 정확히 그 모양이다. `_unwrap` 이 텍스트 경로에서도 벗기도록
고치고 단위 테스트로 고정했다.

**투영 질의에서 잡은 회귀도 하나 있다.** 첫 실행의 궤적이 0건이었다 — 에이전트가
`RETURN s.name, s.load_pct` 로 **투영만** 했기 때문이다. 회수용 동반 질의가 `RETURN` 뒤를
통째로 버리고 있어서, 되살렸을 때는 `ORDER BY load DESC` 가 사라진 **다른 순서**의 노드
3개가 왔다. 행 수가 같아 호출자는 눈치채지 못하고 엉뚱한 노드를 하이라이트한다. 투영을
유지하도록 고쳤고, 그 규칙을 contracts 와 테스트에 고정했다.

---

### 외부 CLI 백엔드 경로의 회귀 (2026-08-21)

위 검증은 전부 **내장 에이전트(`AGENT_BACKEND=deepagents`)** 경로였다. 공급망 시연
([`docs/scm-agent-demo.md`](../../docs/scm-agent-demo.md))을 `cliagents` 로 돌리면서 같은
증상이 **다른 원인으로** 재현됐다 — 도구 이름은 맞고 답변도 정상인데 궤적만 0건.

원인은 이번에도 봉투였지만 위치가 달랐다. 내장 경로는 MCP 클라이언트가 `_unwrap` 으로
벗겨서 도구 함수의 반환값을 주므로 `_emit_tool_side_effects` 가 알맹이를 본다. **외부 CLI 는
MCP 응답 텍스트를 그대로 중계**하므로 스튜디오는 `{"result": "<json>"}` 봉투가 씌워진
문자열을 받는다. `_extract_node_ids` 는 그것을 파싱해 `{"result": "…"}` 를 얻고, 값이
문자열이라 노드처럼 생긴 항목을 하나도 찾지 못한다.

같은 봉투가 **데이터소스 진행 칩**(`datasource_update`)도 비우고 있었다. `row_count` ·
`source` 가 전부 봉투 안이다. 게다가 `_DATASOURCE_TOOL_NAMES` 에는 MCP 경유 이름
(`ontology_query_datasource_sql` 등)이 아예 없어, 칩은 두 백엔드 모두에서 나오지 않았다.

**고친 것**

| 위치 | 내용 |
|---|---|
| `shared/kernel/mcp_client.py` | `unwrap_tool_result` · `unwrap_tool_text` 공개 이음매 추가. 봉투 해제 규칙은 여전히 이 파일 하나뿐이다 (FR-050) |
| `agent_session/service.py` | `_emit_tool_side_effects` 진입에서 봉투를 한 번 벗긴다. 두 백엔드가 같은 값을 본다 |
| `agent_session/service.py` | `_DATASOURCE_CHIP_TOOLS` 신설 — `answer_nods` 필터용 집합과 분리해 MCP 이름을 담는다 |
| `OntologyGraphPanel.vue` | 궤적 노드가 현재 엔티티 그래프에 없으면 `/api/graph/neighbors` 로 채운 뒤 하이라이트. 레이아웃이 끝난 뒤 화면을 맞추고, 확대 상한을 둔다 |

마지막 항목이 화면에서 가장 컸다. 엔티티 뷰는 그래프의 **일부**만 싣는다. 에이전트가 지나간
노드가 그 창 밖이면 이벤트도 오고 뷰 전환도 되는데 `.traversed` 는 0이다 — spec 이 요구하는
것은 이벤트가 아니라 **화면에 남는 궤적**이므로(US2), 없으면 가져와야 한다.

**실측 (2026-08-21, `AGENT_BACKEND=cliagents`, 스키마 `공급망 멀티에이전트`)**

| 확인한 것 | 고치기 전 | 고친 뒤 |
|---|---|---|
| `traversed_nodes` 이벤트 | 0회 | 1회, 노드 `…:5099` (실제 `PO-2026-0117` 노드) |
| `datasource_update` 칩 | 내용 없음 | `supplychain.scm_shipment` · `row_count=1` 등 4회 |
| 브라우저 cytoscape `.traversed` | 0 | **1** (`.faded` 159) |

단위 테스트로 고정했다 — `test_mcp_answer_tools.py` 의
`test_trajectory_survives_the_cli_relay_envelope` 외 2건. **기존 테스트는
`_extract_node_ids` 를 이미 벗겨진 payload 로 부르고 있어서** 이 회귀를 잡지 못했다. 새
테스트는 실제로 오는 문자열 모양으로 `_emit_tool_side_effects` 이음매를 통과시킨다.

---

## 헌법 개정 수반

`.specify/memory/constitution.md` 의 ontology-studio 절, "가상 클래스는 인스턴스를 저장하지
않는다" 항목에 다음 문장이 있다:

> 답변 에이전트는 데이터성 질문에서 `behavior_list` 를 먼저 호출해야 한다. 이것이 유일한
> 발견 경로다.

MCP 경유에서는 `graph://schema` 의 `binding_kind: virtual` 이 발견 경로다. **유일하다**는
서술이 사실이 아니게 되므로, 두 경로를 모두 적도록 고친다. 발견이 필요하다는 규칙 자체는
바뀌지 않는다.
