<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/011-ontology-board/plan.md`
<!-- SPECKIT END -->

# ontologic

여러 서비스를 git 서브모듈로 묶은 데이터·온톨로지 플랫폼. 서브모듈은 각각 별도 저장소지만
**하나의 Neo4j 그래프와 하나의 루트 `.env` 를 공유**한다. 그래서 서비스 경계를 넘는 계약은
서브모듈이 아니라 여기에 있다.

## 반드시 먼저 읽을 것

**`.specify/memory/constitution.md`** — 플랫폼 계약. 카탈로그(Neo4j)를 읽거나 쓰는 코드,
데이터소스 연동, 환경 설정, 포트를 건드리기 전에 읽는다. 소스와 실측 그래프에서 확인한
사실만 담았고 각 항목에 확인 경로가 있다. 서브모듈별 규칙은 그 문서의 **"구성원 프로젝트별
규칙"** 절에 있다.

가장 자주 사고가 나는 지점:

- 서브모듈 안에 `.env` 를 만들면 루트 `.env` 를 **가린다.** (constitution VI)
- `Column.type` / `Column.dtype` 처럼 **같은 값을 두 표기로 쓰는 곳**이 있다. 읽을 때
  COALESCE 한다. (constitution III)
- 전역 삭제(`MATCH (n) DETACH DELETE n`)는 **데이터 패브릭 카탈로그까지 지운다.**
  (constitution IV)
- 스키마 그룹만 지우면 **Neo4j 엔티티가 남아** 다음 실행에 누적된다. 클래스를 먼저 지운다.
  (constitution IV)
- 에이전트는 `AGENT_BACKEND` 로 내장/외부 CLI 를 교체할 수 있다. 두 경로는 **같은 도구
  구현과 같은 프롬프트 파일**을 써야 한다. (constitution — ontology-studio 절, spec 004)

## 문서

| 문서 | 내용 |
|---|---|
| `.specify/memory/constitution.md` | 플랫폼 계약 (리뷰 기준) |
| `docs/catalog-schema.md` | 카탈로그 그래프 실측 스냅샷과 재확인 방법 |
| `docs/graph-schema-contract.md` | 온톨로지 모델을 그래프에 발행하고 런타임이 읽는 계약 |
| `docs/agentic-rag-walkthrough.md` | MCP 로 agentic RAG 를 실제 수행한 기록 (8개 시나리오·2개 에이전트·토큰 실측) |
| `demo/agent-runs/` | 위 기록의 원본 로그 (도구 호출 인자·결과 그대로) |
| `docs/scm-agent-demo.md` | 공급망 6개 업무 도메인 멀티 에이전트 시연 기록 (연구과제 근거 자료) |
| `demo/scm-agent/` | 위 시연의 데이터셋·실행 스크립트·원본 로그·영상 |
| `demo/scm-agent/ARCHITECTURE.md` | 시연 구성 순서(문서→온톨로지→연계→바인딩)와 첫 구성을 되돌린 이유 |
| `installation.md` | 서비스 포트·기동 순서·알려진 이슈 |
| `specs/` | speckit 기능 스펙 (플랫폼 단위) |

서브모듈 안의 `openspec/` 은 그 저장소에 국한된 변경 단위를 다룬다. 여러 서비스에 걸치는
변경은 루트 `specs/` 에서 관리한다.

## 검증

```bash
uv run --with neo4j python scripts/inspect_catalog.py        # 카탈로그 계약이 여전히 유효한가
uv run --with neo4j python scripts/probe_graph_schema_api.py # 그래프 스키마 API 계약
uv run python scripts/verify_ontological_backend.py          # ontological-db 에서도 도는가
./start-all-services.sh                                      # 전체 기동
```

계약 위반이 의심되면 추측으로 고치지 않고 위 스크립트로 재확인한다.
