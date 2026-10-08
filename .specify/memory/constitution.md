# Ontologic Platform Constitution

이 문서는 **ontologic 플랫폼 전체**가 지켜야 하는 계약을 고정한다. 구성원 프로젝트는
각각 별도 git 서브모듈이지만 하나의 Neo4j 그래프와 하나의 루트 `.env` 를 공유하므로,
계약은 서브모듈 안이 아니라 여기에 있어야 한다.

공유 그래프에 직접 관여하는 구성원: `data-fabric`(writer) · `neo4j-text2sql` ·
`domain-layer` · `ontology-studio`. 나머지 서브모듈(`api-gateway`, `agent-scheduler`,
`data-secure-guard`, `infra`, `robo-data-*` 등)은 카탈로그를 직접 읽지 않지만, 루트 `.env`
와 포트 규약(원칙 VI)은 동일하게 적용된다.

내용은 추측이 아니라 **소스 코드와 실제 그래프에서 확인한 사실**이다. 각 항목에 확인
경로를 적었으니, 계약이 바뀌었는지 의심되면 같은 방법으로 재확인한다.

## 참조 문서

| 문서 | 내용 |
|---|---|
| [`docs/catalog-schema.md`](../../docs/catalog-schema.md) | 카탈로그 그래프 **실측 스냅샷** — 노드·속성·제약·divergence 의 근거와 재확인 방법 |
| [`scripts/inspect_catalog.py`](../../scripts/inspect_catalog.py) | 아래 계약이 현재 그래프와 여전히 일치하는지 자동 검사 |
| [`installation.md`](../../installation.md) | 서비스 포트·기동 순서·알려진 이슈 |

원칙(무엇을 지킬 것인가)은 이 문서에, 근거(실제로 어떻게 생겼는가)는
`docs/catalog-schema.md` 에 둔다. 사실이 바뀌면 그 문서를 갱신하고, 규칙이 바뀌면 이
문서를 갱신한다. 같은 표를 두 곳에 두지 않는다.

```bash
uv run --with neo4j python scripts/inspect_catalog.py     # ontologic 루트에서
```

검사 스크립트는 루트 `.env` 를 직접 읽고 서브모듈을 import 하지 않는다. 계약이 전 서비스에
걸쳐 있으므로, 특정 서브모듈이 없거나 의존성이 설치되지 않은 상태에서도 돌아가야 한다.

---

## Core Principles

### 0. 그래프 저장소는 두 가지다 — Neo4j 와 ontological-db

이 문서에서 "Neo4j" 라고 적힌 곳은 **그래프 저장소**를 뜻한다. 플랫폼은 두 가지 위에서
돌 수 있고, 둘 다 정식 모드다.

| 모드 | 그래프 | 콘솔 | 선택 |
|---|---|---|---|
| 기본 | Neo4j 5 | Neo4j Browser (게이트웨이 `/browser/`) | 아무 설정 없음 |
| ontological | ontological-db (PostgreSQL + 확장) | ontological 포털 (`:7474`) | `ONTOLOGY_STUDIO_GRAPH=ontological` · `docker-compose.ontological.yml` |

**두 모드의 공통점이 이 설계의 요점이다.** 애플리케이션 코드에는 저장소 분기가 없다.
ontological-db 가 같은 **Bolt 프로토콜**을 말하고 같은 `neo4j` 드라이버가 붙으므로,
바뀌는 것은 `NEO4J_URI` 와 자격증명뿐이다. 그래서 아래 모든 원칙은 두 모드에 **그대로**
적용된다 — I 의 "카탈로그가 단일 진실 원천" 도, IV 의 "전역 삭제 금지" 도 저장소가
무엇이든 같다.

다른 점은 셋뿐이고, 전부 배선이지 규칙이 아니다.

- **자격증명이 PostgreSQL 롤이다.** Neo4j 사용자 저장소가 없다 — psql 로 못 보는 행은
  Bolt 로도 못 본다.
- **콘솔이 다르다.** 포털은 프레임 가드를 내보내지 않고 서버가 DB 에 붙으므로, 프록시도
  자동 로그인도 필요 없다. 프런트엔드 **빌드 시점**에 정해진다(`VITE_GRAPH_CONSOLE`).
- **ontological 스택에 Neo4j 는 어디에도 없다.** "정의해 두고 안 띄우는" 것이 아니라
  없다. 게이트웨이 이미지조차 Neo4j Browser 프록시 블록이 삭제된 채로 구워진다 —
  남겨 두면 nginx 가 기동 시 `neo4j` 이름을 풀지 못해 게이트웨이가 통째로 죽고,
  `/api/gateway/**` 뒤의 서비스가 전부 함께 죽는다. (2026-08-16 실측)

> 확인: `docker compose -f docker-compose.ontological.yml config --services` 에 neo4j 가
> 없다 · `podman ... ps` 에 `-neo4j-1` 컨테이너가 없다 ·
> `uv run --with neo4j python tests/graph_backend/neo4j_compat_probe.py` 가 두 저장소
> 모두에서 통과한다

### I. 카탈로그는 인제스천 이후 그래프가 단일 진실 원천이다

data-fabric 이 소스 DB 를 introspect 해서 그래프에 구조를 적재한다
(`POST /api/datasources/{name}/extract-metadata-sync`). 그 이후 테이블 구조를 알아야
하는 코드는 **소스 DB 를 다시 조회하지 않고 그래프를 읽는다.**

- 카탈로그를 소비하는 서비스는 DB 자격증명을 보유하지 않는다. 데이터소스는 **이름으로만**
  지칭한다.
- 실데이터 조회는 neo4j-text2sql `POST /text2sql/direct-sql` 을 거친다
  (SQL 가드·행 상한·MindsDB dialect 처리를 그대로 활용).
- 구조를 알기 위해 `information_schema` 를 다시 뒤지지 않는다. 카탈로그가 이미 그 일을
  했고, 두 경로가 생기면 어긋난다.

> 근거: [`docs/catalog-schema.md` — 그래프 모양](../../docs/catalog-schema.md)

#### 온톨로지 **모델**은 카탈로그가 아니다 — 원천은 스튜디오, 그래프에는 발행한다

카탈로그(`:DataSource`/`:Schema`/`:Table`/`:Column`)의 writer 는 data-fabric 하나다. 온톨로지
모델(클래스·관계·바인딩·behavior)은 **다른 것**이고, 원천은 ontology-studio 의 저장소다.

런타임 MCP 는 스튜디오가 떠 있지 않은 환경에서 돌아야 하므로, 모델을 그래프에 **발행**한다
(`POST /api/schema/{id}/publish`). 규칙:

- 발행물은 `_Ontology*` 접두 라벨만 쓴다. domain-layer 가 같은 그래프에 `:OntologySchema` ·
  `:OntologyType` · `:OntologyBehavior` 를 쓰고 있어, 접두가 없으면 두 온톨로지가 섞인다.
- 발행물에 **자격증명을 싣지 않는다.** 카탈로그의 `:DataSource` 가 평문 password 를 갖는
  것과 대조된다 — 발행은 그것을 복제하지 않는다.
- 발행·철회는 **자기 라벨 범위만** 건드린다. 카탈로그와 다른 그룹을 지우지 않는다.
- 클래스 **존재**의 권위는 `db.labels()` 다 — 두 백엔드가 모두 구현하고, 둘 다 인스턴스가
  0건인 클래스를 포함하는 유일한 조회이기 때문이다. 다만 그 목록에는 카탈로그·text2sql·
  analyzer·domain-layer 의 라벨이 섞여 있으므로 **발행 레지스트리와 교집합**을 취한다.
- 가상 클래스는 **앵커 노드 없이** 제약 선언만으로 그래프 스키마에 등재한다. 인스턴스 0건
  (원칙 VII · spec 001 SC-001)이 유지돼야 한다.

**두 백엔드에서 실제로 갈리는 지점** (2026-08-17 실측, `scripts/verify_ontological_backend.py`)

"저장소 분기가 없다"는 것은 *분기문을 쓰지 않는다*는 뜻이지 *능력이 같다*는 뜻이 아니다.
아래는 ontological-db 에 **없는** 것들이고, 코드는 분기 대신 **시도하고 안 되면 대체**한다.

| 쓰지 말 것 | 대신 | 이유 |
|---|---|---|
| `SHOW CONSTRAINTS` / `SHOW INDEXES` | `db.labels()` + 발행 레지스트리 | 파서가 받지 않는다 |
| `db.schema.visualization()` / `nodeTypeProperties()` | 발행 레지스트리 | 프로시저가 없다 |
| `properties(n)` | 노드를 통째로 RETURN | 함수가 없다 (`keys()` 는 있다) |
| `n[k]` 동적 속성 접근 | 선언된 속성명으로 정적 접근 | jsonb→integer 캐스트 오류 |

- **클래스는 `_Entity` 의 하위 타입으로 먼저 선언한 뒤 제약을 건다.** ontological-db 에는
  진짜 타입 시스템이 있어, 제약이 클래스를 루트 타입으로 만들면 그 뒤로
  `(:_Entity:Class)` 인스턴스가 **영구히 거부**된다. 발행이 순서를 지킨다.
- **그래프를 여는 모든 경로는 `NEO4J_DATABASE` 를 넘긴다** (`tools.session_kwargs()`).
  Neo4j 에서는 데이터베이스, ontological-db 에서는 **그래프**를 고른다. 넘기지 않으면 서버
  기본 그래프만 쓰게 되고, 자체 세션을 여는 스크립트가 **다른 그래프에 써 버린다** — 실제로
  겪었다.

> 근거: [`docs/graph-schema-contract.md`](../../docs/graph-schema-contract.md) ·
> [spec 010](../../specs/010-graph-published-ontology-mcp/spec.md)

### II. 노드 정체성 규칙을 지키고, Table 은 항상 데이터소스로 함께 필터링한다

`:Table` 의 제약은 `(db, schema, name)` 3-튜플인데 writer 의 MERGE 키는 `(name, schema)`
2-튜플이다. **서로 다른 DB 에 같은 `schema.table` 이 있으면 같은 노드로 합쳐진다.**

- 테이블을 조회할 때 `(t.datasource = $ds OR t.db = $ds)` 를 항상 함께 쓴다.
- `:Column` 의 정체성은 `fqn = f"{schema}.{table}.{column}".lower()` 이며 소문자다.

> 근거: [`docs/catalog-schema.md` — 정체성과 제약](../../docs/catalog-schema.md)

### III. 읽을 때는 두 표기를 모두 받는다 (COALESCE 필수)

두 서비스가 같은 그래프에 **다른 속성명**으로 쓰고 읽는다. 한쪽만 읽으면 값이 있는데도
비어 보인다. divergence 전체 목록과 실측치는
[`docs/catalog-schema.md` — 속성명 divergence](../../docs/catalog-schema.md) 에 있다.

```cypher
coalesce(c.type, c.dtype, '')                      AS sql_type
coalesce(c.primary_key, c.is_primary_key, false)   AS primary_key
WHERE (t.datasource = $ds OR t.db = $ds)
```

- 외래키는 `REFERENCES` / `FK_TO` / `FK_TO_TABLE` 세 형태를 모두 시도하고 중복을 제거한다.
  어느 서비스가 먼저 부팅했는지에 따라 존재하는 형태가 달라진다.
- 쓰기는 **data-fabric 표기를 따른다** (`type`, `primary_key`, `REFERENCES`). writer 가
  하나여야 divergence 가 더 늘지 않는다.
- HTTP 응답 정규화는 서비스별로 **한 곳에서만** 한다. ontology-studio 는
  `datafabric_client._normalize_column()` 이다. 호출부마다 재발명하지 않는다.
- **새 divergence 를 발견하면 `docs/catalog-schema.md` 의 표에 추가한다.** 표에 없는
  divergence 는 다음 사람이 똑같이 하루를 잃는다.

### IV. 카탈로그를 지우는 전역 삭제를 하지 않는다

`MATCH (n) DETACH DELETE n` 류의 전역 삭제는 **데이터 패브릭 카탈로그까지 지운다.**
ontology-studio 의 `POST /api/neo4j/clear-all` 이 그렇고, 실제로 전체 E2E 스위트 실행 후
카탈로그가 사라져 재추출이 필요했다.

- 테스트·스크립트에서 전역 삭제를 쓰지 않는다. 만든 것만 지운다.
- 온톨로지 인스턴스만 지우려면 `(:_Entity)` 처럼 라벨로 범위를 좁힌다.
- SQLite 에 있는 상태(ontology-studio 의 바인딩·behavior)는 Neo4j 삭제로 지워지지 않는다.
  별도로 지운다.
- **스키마 그룹 삭제는 엔티티를 남긴다.** `DELETE /api/schemas/{id}` 는 그룹만 지우므로,
  같은 빌드를 다시 돌리면 앞선 실행의 노드 위에 쌓인다. 정리하려면 `DELETE
  /api/schema/classes/{name}` 으로 **클래스를 먼저** 지운다(이쪽이 `(:_Entity:<Class>)` 를
  함께 지운다). 실제로 이 누적 때문에 노드 수가 두 배로 보고된 적이 있다.
  ↳ `tests/e2e_doc_build_compare.spec.js` · `demo/prep_state_narrow.py`

### V. `:DataSource` 는 자격증명을 평문으로 보유한다 — 밖으로 내보내지 않는다

`:DataSource` 노드에 `host` / `port` / `user` / `password` 가 평문으로 저장되고,
data-fabric 의 `GET /api/datasources/{name}/connection` 은 비밀번호를 그대로 반환한다.

- 외부로 나가는 응답에는 `{datasource, schema, table}` 수준만 노출한다. 접속 정보와 내부
  SQL 은 넣지 않는다.
- MCP·공개 API 표면은 sanitize 를 통과해야 한다.
- 로그에 접속 정보를 남기지 않는다. 실행한 SQL 과 행 수만 남긴다.

### VI. 환경 설정의 단일 진실 원천은 루트 `.env` 다

모든 Python 서브모듈이 bare `load_dotenv()` 를 호출하고, 이는 CWD 에서 상위로 올라가며
`.env` 를 찾는다.

- **서브모듈 안에 `.env` 를 만들면 루트 `.env` 를 가린다.** `docker-compose.yml` 이
  서브모듈 기준 `env_file: - .env` 를 쓰는 경우에만 로컬 파일을 두고, 그 파일은
  **compose 전용 상위집합**으로 유지한다.
- `TEXT2SQL_BASE_URL` 은 루트 `.env` 에서 라우터 접두사를 **포함**한다
  (`http://host:8020/text2sql`). 반면 `TEXT2SQL_URL` / `TEXT2SQL_API_URL` 은 접미사 없는
  origin 이다. 전체 경로를 직접 만드는 코드는 두 형태를 모두 받아야 한다. 그러지 않으면
  `/text2sql/text2sql/...` 404 → 조용한 폴백 → **"카탈로그에 컬럼이 없다"는 엉뚱한 증상**이
  된다. 실제로 이 버그가 있었다.
- **같은 함정이 서비스마다 반복된다.** `DOMAIN_LAYER_URL`(별칭 `WHATIF_API_URL`, 기본
  `http://127.0.0.1:8001`)도 라우터 접두사 `/whatif` 를 포함해 적을 수 있다. 전체 경로를
  만드는 코드는 origin 형과 접두사 포함형을 **모두** 받아야 하고, 그 정규화는 서비스별로
  **한 곳**에만 둔다. 목 트랜스포트는 잘못 조립한 URL 도 그대로 받아주므로, 이 정규화는
  **조립된 문자열을 직접 단언하는 단위 테스트**가 있어야 의미가 있다.
  ↳ `ontology-studio` 의 `settings._origin_without_router_prefix()` ·
  `causal_client.analyze_url()` · `test_causal_client.py`
- `localhost` 대신 `127.0.0.1` 을 쓴다. `localhost` 가 `::1` 로 먼저 해석되는데 일부
  서비스는 IPv4 로만 바인딩해 원인 불명의 `ReadError` 가 난다.
- **api-gateway(9000)를 경유하지 않는다.** 기본 응답 타임아웃 30초가 MindsDB view
  질의(10~25초)를 끊는다. 8004 / 8020 을 직접 호출한다.
- MindsDB 는 `LIMIT 1000` 근처에서 연결을 끊는다. 행 상한 기본값 500 의 이유다.
- `AGENT_BACKEND`(`deepagents` 기본 / `cliagents`)와 `EXTERNAL_AGENT_ID`(`claude-code` /
  `codex`)는 **ontology-studio 소유**다. 기본값이면 기존 내장 에이전트가 그대로 돌고,
  `cliagents` 로 바꾸면 외부 CLI 가 스튜디오 도구를 MCP 로 호출한다. 외부 CLI 경로는
  `OPENAI_API_KEY` 를 쓰지 않는다 — CLI 가 자기 모델을 들고 온다.
  ↳ [spec 004](../../specs/004-pluggable-agent-backend/spec.md)
- **바인드 주소를 접속 주소로 쓰지 않는다.** `BACKEND_HOST=0.0.0.0` 은 서버가 어디에 붙는지를
  말할 뿐이고, 그 값을 그대로 URL 에 넣으면 클라이언트가 접속하지 못한다. 자기 자신을 가리키는
  URL 을 만들 때는 `127.0.0.1` 로 치환한다.

### VII. 통합 경로는 실제로 실행해서 검증한다

단위 테스트는 목 트랜스포트를 쓰므로 **우리가 만든 URL 을 그대로 받아준다.** 위 VI 의
접두사 버그는 단위 테스트를 전부 통과한 상태에서 통합 검증이 잡아냈다.

- 단위 테스트만 통과한 것을 "동작한다"고 보고하지 않는다.
- E2E 픽스처는 등록만 되고 **메타데이터가 없는 데이터소스를 건너뛰어야** 한다.
  첫 번째를 무조건 고르면 모든 스펙이 조용히 skip 되어 초록불로 보이지만 아무것도
  검증하지 못한다.
- 스크린샷으로 증거를 남길 때는 CSS 트랜지션이 끝난 뒤 찍는다. opacity 가 200ms 동안
  변하므로 단언 직후의 캡처는 비활성처럼 보인다.

### VIII. 호스트 포트는 최소로 점유한다 — 서비스 간 통신은 컨테이너 네트워크 안에서 끝낸다

이 플랫폼은 **설치본**으로 배포된다. 사용자의 머신에는 이미 다른 것들이 돌고 있고, 우리가
여는 포트 하나하나가 충돌 표면이자 보안 표면이다. 서비스가 늘어날 때마다 호스트 포트가
하나씩 늘어나는 구조는 그 자체로 결함이다.

**규칙**

- 서비스끼리만 쓰는 통신은 **compose 네트워크 안에서 서비스 이름으로** 한다.
  `127.0.0.1:<published>` 로 나갔다 들어오지 않는다.
- 컨테이너에 `ports:` 를 새로 추가하려면 **호스트에서 직접 접근해야 하는 이유**를 그 자리에
  주석으로 남긴다. "디버깅이 편해서" 는 이유가 아니다 — 그 용도는
  `podman exec` / `podman port` 로 충분하다.
- 프론트엔드와 API 는 **같은 오리진**에 둔다. 브라우저가 보는 포트가 하나여야 CORS 설정도,
  사용자가 기억할 주소도 하나로 유지된다.
- 호스트에 여는 것은 전부 `127.0.0.1` 에 바인딩한다. `0.0.0.0` 은 같은 네트워크의 다른
  기기에 스택을 통째로 공개한다.

**불가피하게 남는 것** (없앨 수 없는 이유가 프로토콜·제품에 있는 경우만)

| 무엇 | 왜 호스트에 남는가 |
|---|---|
| 앱 로컬 오리진 | 앱 창이 접속하는 주소다. 호스트 포트가 아니면 존재할 수 없다. |
| Neo4j Bolt | 호스트 프로세스인 studio 백엔드가 **bolt 프로토콜**로 붙는다. 경로 기반 HTTP 게이트웨이로는 대신할 수 없다. |
| MCP 서버 | 외부 AI 클라이언트가 설정 파일에 **손으로 적는** 주소다(그래서 sticky). |

**왜 studio 백엔드는 컨테이너로 못 넣는가** — `AGENT_BACKEND=cliagents` 가 PATH 의
`claude`/`codex` 와 그 CLI 의 `$HOME` 인증 상태에 의존하기 때문이다. 이것이 호스트에
남는 한 위 표의 Bolt 도 함께 남는다. 둘은 한 묶음이다.

*확인 경로*: `ontology-studio/desktop/resources/backend/compose.yml` 의 `ports:` 선언과
`desktop/src/main/ports.js` 의 claim 목록. 이 둘의 개수가 곧 점유 표면이다.

---

## 구성원 프로젝트별 규칙

플랫폼 계약에서 파생되지만 한 프로젝트 안에서만 의미가 있는 규칙이다.

### ontology-studio

#### 테이블 구조 → 온톨로지 경로는 결정적이다 (LLM 금지)

카탈로그에 이미 구조가 있으면 LLM 을 부르지 않는다. 같은 카탈로그는 항상 같은 온톨로지를
만든다.

| 카탈로그 | 온톨로지 |
|---|---|
| 테이블 | 클래스 (`mfg_daily_equipment` → `MfgDailyEquipment`, PascalCase) |
| 컬럼 | 속성 (타입 → `string\|integer\|float\|boolean\|date`) |
| 기본키 | `key_columns` |
| 외래키 | 관계 유형 (`REFERENCES_<TARGET_TABLE>`, UPPER_SNAKE) |

- 클래스명은 영문 PascalCase, 관계 유형명은 영문 UPPER_SNAKE_CASE — 빌드 에이전트가 쓰는
  규약과 같아야 한다. 생성된 온톨로지가 손으로 만든 것과 이질적으로 보이면 안 된다.
- **모든 컬럼이 속성이 된다.** domain-layer 는 PK 와 `*_id` 를 뺐지만, 여기서는
  `column_map` 이 곧 조회 허용 목록이므로 빼면 질의로 도달할 수 없다. 참조 컬럼은 숨기는
  대신 `reference: true` 로 표시한다.
- 생성된 클래스는 기본적으로 **가상 클래스로 바인딩**한다.
- 쓰기 전에 `dry_run` 으로 계획을 반환할 수 있어야 한다.

> 이식 원본: `domain-layer/app/services/schema_extractor.py`

#### 가상 클래스는 인스턴스를 저장하지 않는다

데이터소스에 바인딩된 클래스는 Neo4j 에 인스턴스를 **0 건** 유지한다. 질의 시점에
behavior 가 실제 SQL 로 확장된다.

- `batch_ingest` / `entity_create` 대상이 아니다.
- 따라서 노드 통계(`vector_search` · `graph_stats` · `ontology_list_schemas`)에 보이지
  않는다. **답변 에이전트는 데이터성 질문에서 가상 클래스를 먼저 발견해야 한다.** 발견
  경로는 질의 경로에 따라 둘이다 (spec 012):
  - 표준 MCP 경유 — `graph://schema` 의 `binding_kind: virtual` (기본 경로)
  - 내장 도구 경유 — `graph_stats` 의 `virtual_classes`, 그리고 `behavior_list`
  둘 중 무엇도 부르지 않고 낸 "데이터가 없다" 는 답은 오답이다.
- 그래프 UI 는 인스턴스 개수 대신 `가상` 을 표시한다. 0 으로 표시하면 "데이터가 없다"로
  오독된다.

#### SQL 파라미터는 이스케이프하지 않고 타입으로 렌더한다

- `integer` / `float` 은 강제 변환 → 주입이 구조적으로 불가능.
- `string` 에 `'` `"` `` ` `` `;` `\` `--` `/*` `*/` 또는 제어문자가 있으면 **거부**한다.
- 따옴표가 정당하게 필요하면 `escaped_string` 을 **명시적으로** 선택한다. doubling 이
  일어나는 유일한 곳이며, 코드 리뷰에서 그 단어로 눈에 띈다.
- `LIMIT` 은 호출자가 정하지 못한다. `min(요청, behavior.max_rows, DATASOURCE_MAX_ROWS)`.
- SQL 은 바인딩에 선언된 테이블만 참조할 수 있고, **생성 시점과 호출 시점 모두** 검사한다.

domain-layer 의 `value.replace("'", "''")` 후 문자열 연결 방식은 복사하지 않는다.

> 참조: `domain-layer/app/routers/ontology.py:4610` (복사하지 않을 패턴)

#### 통계로 발견한 관계는 단언이 아니라 가설이다

인과 발견(전략 2)은 온톨로지에 관계를 만들 수 있지만, 그 관계는 FK·문서에서 온 관계와 **같은
층에 두지 않는다.** Granger 검정은 역인과와 공통원인을 가리지 못하므로 산출물은 가설이고,
사람이 승인한 것만 관계가 된다.

- 관계명 접두사로 갈린다 — FK 유래 `REFERENCES_*`(단언) vs 통계 유래 `INFLUENCES_*`(가설).
  관계 properties 에 `hypothesis: true` 와 method·lag·p_value·p_value_adjusted 를 싣는다.
- **다중비교 보정이 필수다.** 변수 20개면 쌍이 190개이고 α=0.05 에서 우연히 ~10개가 "유의"
  해진다. Benjamini–Hochberg 로 보정하고, **검정 횟수와 보정 방법을 저장까지** 가져간다 —
  보정 p-value 는 몇 번의 검정에 대한 것인지 없이는 해석할 수 없다.
- 기존 하이브리드 엔진은 **아무것도 찾지 못했을 때** 기여도 분해로 폴백한다
  (`causal_analysis.py:433` `if not edges and try_var:`). "찾지 못했다" 는 무관한 변수들의
  정상 결과이므로, 이 폴백은 잡음에서 엣지를 만들어낸다 — 실측: 독립 난수 5개를 섞으면
  decomposition 엣지 20개. 분해형은 호출자가 `deterministic` 이라고 **명시한 쌍만** 유의로
  판정한다.
- 통계 엔진은 **복사하지 않고 domain-layer 에 위임한다** —
  `POST /whatif/analyze-matrix`(무상태: `schema_id` 없음, 그래프 쓰기 없음, LLM 없음).
  1,000줄 넘는 통계 코드를 두 벌로 만들면 원칙 III 이 경고하는 divergence 가 그대로 재현된다.
  온톨로지 쓰기는 ontology-studio 가 단독으로 갖는다.

#### 엔티티↔테이블 매칭에서 문서는 테이블의 부분집합을 기술한다

역바인딩(전략 1)의 점수는 컬럼 겹침이 주 신호이고 이름 유사도는 **가장 약한 신호**다. 문서가
한글 도메인 용어를 쓰고 컬럼은 영문 약어이면 이름 유사도가 **0** 이며, 그것이 정상이다.

- 테이블 컬럼 대비 커버리지(precision)를 커버리지(coverage)와 **동등하게 가중하지 않는다.**
  문서는 테이블의 부분집합을 기술하므로 — 실측: 7속성 vs 13컬럼 — 동등 가중하면 명백한 정답이
  `needs_review` 로 떨어진다. precision 은 넓은 테이블 방지용 **하한**으로만 쓴다.
- 한글 클래스명을 식별자로 변환할 때 `가-힣` 를 **보존한다.** 전략 1 은 문서의 용어로 클래스를
  만들므로 한글이 예외가 아니라 표준이다. non-ASCII 를 제거하면 모든 관계가 같은 이름이 된다.

#### 에이전트 백엔드는 도구와 프롬프트를 공유한다

내장 에이전트(`deepagents`)와 외부 CLI 에이전트(`cliagents`)는 교체 가능하지만, **같은 도구
구현과 같은 프롬프트 파일**을 써야 한다. 갈라지면 한쪽에서 고친 것이 다른 쪽에 반영되지 않고,
그 사실을 아무도 모른다. ↳ [spec 004](../../specs/004-pluggable-agent-backend/spec.md)

- 도구를 **다시 구현하지 않는다.** MCP 브리지는 내장 에이전트가 쓰는 함수 객체를 그대로
  등록한다. 테스트가 객체 동일성으로 이를 강제한다.
- 프롬프트는 `skills/<name>/SKILL.md` 하나가 원천이다. 두 경로가 그 파일을 읽는다.
  `.cache/` 아래 배포 사본을 고치면 다음 실행에 덮어써진다.
- **모드별 권한을 넓히지 않는다.** MCP 엔드포인트는 모드마다 분리하고, `answer` 에는 쓰기
  도구를 올리지 않는다 — 내장 에이전트가 가진 권한과 정확히 같아야 한다.
- 읽기 전용 검색 서버(`ontology_mcp`)에 mutation 도구를 얹지 않는다. 그 서버의 `TOOL_NAMES`
  는 보안 경계다. 에이전트용 도구는 별도 모듈(`agent_bridge_mcp`)에 둔다.
- 그 서버에 **읽기 전용** 도구를 더할 때도 `TOOL_NAMES` 는 건드리지 않는다. 라이브 데이터에
  닿는 것은 `DATASOURCE_TOOL_NAMES` 에 두고 `MCP_ALLOW_DATASOURCE_EXPANSION` 으로 잠근다 —
  꺼진 상태의 표면이 이전과 **정확히 같아야** 한다 (spec 001 SC-006).
- 외부 Cypher 표면은 `:DataSource`·`:Schema`·`:Table`·`:Column` 과 `_Ontology*` 를 **차단**
  한다. 앞의 넷은 평문 자격증명을, 뒤는 `sql_template` 을 갖는다. `labels(n)` 문자열 비교
  우회도 함께 막는다 — 라벨 문법만 막으면 그냥 돌아간다.
- 런타임 리더(`ontology_runtime`)는 스튜디오 저장소를 import 하지 않는다. 규율로는 유지되지
  않으므로 import 그래프를 검사하는 테스트가 강제한다.
- **CLI 가 못 하는 일은 숨기지 않는다.** 헤드리스 입력을 받지 못하는 에이전트(Codex)에
  실행 중 지시를 보내면 큐에 넣고 버리는 대신 거부를 반환한다.

#### 스킬은 배포 가능한 표준 패키지다

프롬프트를 파이썬 패키지 안에 두면 그 지시문은 **스튜디오를 실행하는 사람만** 쓸 수 있다. 같은
방법론을 자기 에이전트에서 쓰려는 사용자에게 줄 것이 없어진다.
↳ [spec 005](../../specs/005-portable-agent-skills/spec.md)

- 형식은 **agentskills.io 표준**을 따른다 — 폴더 하나 = 스킬 하나, `SKILL.md` + 프론트매터,
  폴더 이름과 `name` 일치. 우리만 아는 규격을 만들지 않는다. 내장 경로가 쓰는 deepagents 도
  같은 규격을 구현하고 있으므로 이는 발명이 아니라 **합류**다.
- 스킬 목록은 **폴더 스캔**으로 결정한다. 이름을 코드에 하드코딩하면 스킬을 늘릴 때마다 코드를
  고쳐야 하고, 그 목록이 두 번째 진실 원천이 된다.
- 형식이 잘못된 폴더는 **거부하고 지목**한다. 조용히 건너뛰면 스킬이 하나 사라진 채로 동작하고
  아무도 모른다.
- 본문이 길면 **참조 자료로 나눈다.** 나눌 때는 옮기는 것이지 다시 쓰는 것이 아니다. 본문은
  각 참조 자료를 **언제 읽는지** 지목해야 한다 — 목록만 나열하면 읽히지 않는다.
- **양쪽 경로가 참조 자료를 실제로 읽을 수 있어야 한다.** 한쪽만 세부를 못 읽으면 같은 스킬을
  쓰고도 결과가 갈린다. 내장 경로의 파일 도구는 샌드박스 범위이므로, 스킬 폴더를 샌드박스로
  동기화하지 않으면 이 조건이 깨진다.
- 배포본(플러그인 / 폴더 복사)은 **저장소의 그 폴더 그대로**다. 배포용으로 가공한 사본을 두면
  원천이 둘이 된다.

#### 지시문과 값을 섞지 않는다

백엔드가 에이전트에게 넘기는 것은 **값**이다. 지시문이 아니다.

- 구축 의도·골든 퀘스천·데이터소스·검토 피드백은 값이므로 백엔드가 넘긴다. "이 질문들에
  답할 수 있도록 구축하세요" 같은 문장은 지시문이므로 **스킬에 있어야 한다.** 둘을 파이썬
  문자열로 함께 조립하면 프롬프트 단일 원천이 절반만 지켜진다.
- 경로 매핑도 값이다. 외부 CLI 는 **호스트에서** 돌고 내장 경로는 샌드박스에서 도므로 작업
  경로가 다르다. 그 매핑은 **값 블록 한 개**로 주입하고, 설명 문장을 붙이지 않는다. 명시하지
  않으면 존재하지 않는 경로로 파서를 짠다.
- 스킬은 자기가 받을 항목과 **빠졌을 때 무엇을 할지**를 본문에 갖는다. 그래야 폼이 없는
  단독 실행에서도 같은 절차가 성립한다. 그 판정을 코드에 두면 세 번째 지시문 원천이 된다.


#### 추출한 지식은 후보로 쌓고, 신뢰도 게이트를 지난 것만 그래프에 쓴다

LLM·파서가 문서에서 뽑은 엔터티·관계·속성은 **바로 그래프에 쓰지 않는다.** 환각과 허위 관계가
그래프에 섞이면 나중에 어느 것이 근거 있는 사실인지 가릴 수 없다.
↳ [spec 013](../../specs/013-extraction-confidence-hitl-quality/spec.md) ·
`ontology-studio/backend/src/modules/quality/`

- 문서 추출의 그래프 쓰기는 `quality/ingest_gate.py` **한 곳**이다. 트랜잭션 메타데이터에
  `actor / source / reason` 을 싣고, 노드·엣지에 `_confidence / _run_id / _evidence_ref` 를 남긴다.
  이 경로는 Bolt 만 쓴다 — ontological-db 내부 SQL 을 부르지 않는다.
- 복합 신뢰도 S_c 가 하한 미만이거나 스키마 게이트(G_onto)를 어기면 **DLQ 로 격리**한다.
  버리지 않는다 — 원인 코드와 함께 남기고, 규칙을 고친 뒤 재처리한다. 원인 코드는 **추가만**
  한다(`quality/codes.py`). 이름을 바꾸면 이미 쌓인 항목이 고아가 된다.
- **검수 결정(승인·기각·수정)과 DLQ 재처리는 에이전트 도구로 주지 않는다.** `causal_apply` 와
  같은 이유 — 사람의 판단을 프롬프트가 아니라 구조로 강제한다.
- 사람이 승인해도 **스키마를 어기는 사실은 쓰지 않는다.** 스키마를 먼저 고친다.
- 사람이 내린 결정은 재추출이 덮지 않는다. 후보는 (스키마, 종류, 주어, 술어, 목적어)
  fingerprint 로 식별한다.
- 스키마(TBox) 변경 제안은 점수와 무관하게 **항상 전문가 검수**로 간다. 자동 반영도, 점수 미달
  폐기도 하지 않는다.
- **검수는 온톨로지 구축의 한 단계다.** 빌드 스킬(`ontology-build`)의 Phase 4 가 `quality_checkup` 을
  호출하고, 사람의 판단은 구축 화면의 ‘검수’ 탭(같은 저장소)에서 한다. 데이터를 넣는 경로는 구축
  대화뿐이다 — 품질 화면에 별도의 적재 경로를 두지 않는다(두 경로는 반드시 어긋난다).
  문장 추출은 `extract_triples`, 표는 `table_ingest`(원천 점검 규칙 포함)로 넣는다.
- 빌드 보고서의 검수 건수는 **백엔드가 저장소에서 읽어 붙인다**(`build_report.quality`). 에이전트가
  적은 숫자를 화면에 그대로 보이지 않는다.
- `batch_ingest`(정규식 파서 경로)는 **구조 위반만** 막는다 — 식별자 결측, 끝점 없는 관계,
  선언된 관계의 정의역·공역 위반. 미등록 클래스는 막지 않는다: 빌드 에이전트가 데이터에서
  스키마를 만드는 흐름이 그것을 전제로 한다.

---

## Governance

- 이 constitution 은 카탈로그·데이터소스 관련 코드의 리뷰 기준이다. 위반이 필요하다면
  먼저 이 문서를 고치고, 왜 바뀌었는지 근거(소스 위치 또는 실측)를 남긴다.
- 계약 위반이 의심되면 `scripts/inspect_catalog.py` 로 재확인한다. 추측으로 고치지 않는다.
- 서브모듈이 자기 안에 별도 constitution 을 두지 않는다. 여기에 프로젝트별 절을 추가한다.
  두 개가 생기면 어느 쪽이 맞는지 아무도 모른다.
- 각 서브모듈의 `openspec/` 은 변경 단위(proposal/design/spec/tasks)를 다루고, 이
  constitution 은 그 변경들이 공통으로 지켜야 할 계약을 다룬다.

**Version**: 2.2.0 | **Ratified**: 2026-07-30 | **Last Amended**: 2026-08-02

> 2.2.0 — [005 이식 가능한 에이전트 스킬 패키지](../../specs/005-portable-agent-skills/spec.md)
> 의 계획 단계에서 확인한 사실을 반영했다. **개정이 구현보다 먼저 온다** — Governance 규칙대로,
> 프롬프트 원천 위치를 바꾸는 변경이므로 코드를 고치기 전에 이 문서를 고친다. 아래 규칙은 005 가
> 구현되는 시점의 상태를 규정한다.
>
> 세 가지가 바뀌었다. (1) 프롬프트 원천이 `agent_session/skills/*.md` 에서
> `skills/<name>/SKILL.md` 로 이동한다 — 파이썬 패키지 내부는 사용자가 가져갈 수 있는 단위가
> 아니다. (2) "스킬은 배포 가능한 표준 패키지다" 절 신설 — agentskills.io 규격, 폴더 스캔,
> 참조 자료 분할, 배포본 무가공. (3) "지시문과 값을 섞지 않는다" 절 신설.
>
> (3)의 근거가 이번 조사에서 가장 뼈아프다. 2.1.0 이 "프롬프트는 하나가 원천이다" 라고 못박은
> 상태에서도 `_compose_build_prompt` 가 `[연결 데이터소스]`·`[Golden Question]`·`[완료 기준]` 의
> **지시문 문장을 파이썬에서 조립**하고 있었다. 스킬 파일만 세어서는 이 위반이 보이지 않는다.
> 규칙을 "프롬프트 파일이 하나" 가 아니라 "지시문은 스킬에, 값은 코드에" 로 다시 적는 이유다.
>
> 2.1.0 — [003 입력 조합별 온톨로지 구축 전략](../../specs/003-ontology-build-strategies/spec.md)
> 구현에서 확인한 사실을 반영했다. 원칙 VI 에 `DOMAIN_LAYER_URL` 접두사 함정을 추가(같은
> 종류의 버그가 서비스마다 반복된다). ontology-studio 절에 두 항목 추가 — "통계로 발견한
> 관계는 가설이다"(가설/단언 분리, BH 보정, 잡음 폴백 차단, 통계 엔진 위임)와
> "문서는 테이블의 부분집합을 기술한다"(precision 은 하한, 한글 보존). 세 항목 모두 단위
> 테스트가 전부 통과한 상태에서 **실행으로만** 드러난 결함이 근거다 (원칙 VII).
>
> 2.0.0 — 범위를 Ontology Studio 에서 ontologic 플랫폼 전체로 넓혔다. 카탈로그 실측
> 스냅샷은 `docs/catalog-schema.md` 로 분리하고 여기서 링크로 참조한다. 프로젝트별 규칙은
> 별도 절로 옮겼다.
