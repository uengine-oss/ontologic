# Feature Specification: 키네틱 액션 레이어 — 온톨로지 객체에 대한 행위 호출

**Feature Branch**: `014-kinetic-action-layer`

**Created**: 2026-10-21

**Status**: Implemented — 브라우저·LLM act 모드 E2E 검증·시연 영상 (2026-10-22)

**Input**: 사용자 질의가 조회에서 끝나지 않고 **행위**로 이어져야 한다 — "P1 공장에서 온도 80℃ 넘는 설비
전부 점검 모드로 바꿔". 조건에 맞는 엔티티 인스턴스를 고르고, 각 인스턴스에 대해 **등록된 마이크로서비스
API** 를 호출해 분산된 운영 시스템(MES·ERP·SCM)에서 액션을 수행한다. 호출에는 인스턴스 단위 실행 권한이
걸려야 한다.

## 왜 이 스펙이 플랫폼 단위인가

- 그래프 발행 레지스트리에 **새 관계** `(:_OntologyClass)-[:HAS_ACTION]->(:_OntologyBehavior {behavior_type:'action'})`
  가 생긴다 — [`docs/graph-schema-contract.md`](../../ontology-studio/docs/graph-schema-contract.md) 개정.
- **새 서비스** `kinetic-action` 과 기존 `api-gateway` 의 인증·동적 라우트 확장.
- Ontology Studio 에 액션 정의 UI 와 채팅 `act` 모드.

## 현재 코드 현실 — 조사 결과

- **CR-1** 행위 개념이 셋이다 ([ontology-metamodel-direction.md](../../docs/ontology-metamodel-direction.md) §3).
  Studio `_OntologyBehavior` 는 파라미터 SQL(조회 전용)이고 판별자가 없다. domain-layer `:Behavior(rest_api)` 는
  단건 REST 호출이지만 권한·감사·재시도·다건 대상이 없다. ontological-db 의 `og_define_action` 은 DB 내부
  Cypher 쓰기다.
- **CR-2** Studio 의 answer 에이전트와 `ontology_mcp` 는 읽기 전용이다. 행위를 실행할 경로가 없다.
- **CR-3** `api-gateway`(Spring Cloud Gateway) 는 정적 라우트뿐 — 인증·재시도·서킷브레이커가 없다.
- **CR-4** Studio 에는 사용자 인증이 없다. data-secure-guard 는 데이터소스 단위 RBAC 이다.

## 아키텍처 결정

- **AD-1 Ontological DB 는 순수 DB 로 둔다.** 키네틱 기능을 DB 엔진(프로시저·CALL 확장·outbox) 에 넣지 않는다.
  행위는 운영 시스템의 일이고, DB 가 외부 시스템 호출의 트랜잭션 경계를 떠안으면 계층이 무너진다.
  그래프는 대상 선정을 위한 **읽기**와, 선택적 결과 기록(일반 Bolt 쓰기)에만 쓴다.
- **AD-2 정의는 Studio, 실행은 `kinetic-action`.** Studio 가 액션을 클래스에 정의하고 그래프에 발행한다.
  `kinetic-action` 은 그래프만 읽고 Studio 의 SQLite 를 모른다 (spec 010 의 "읽는 쪽은 그래프만 본다" 원칙).
- **AD-3 에이전트 게이트웨이(agentgateway)를 쓰지 않고 기존 API Gateway 를 확장한다.**
  - 남향(kinetic → 마이크로서비스)은 결정론적 실행기의 REST 호출이다 — 서비스 등록·라우팅·서비스 인증·
    재시도·서킷브레이커는 일반 API Gateway 의 일이다. OpenAPI→MCP 변환은 호출자가 LLM 일 때만 의미가 있다.
  - 북향 MCP 서버는 `kinetic-action` 하나다 — 페더레이션이 필요 없다. Streamable HTTP 는 HTTP+SSE 라
    Spring Cloud Gateway(WebFlux) 로 프록시된다.
  - agentgateway 기능 중 필요한 것만 직접 넣는다:

    | 기능 | 위치 |
    |---|---|
    | 권한별 도구 필터, 도구 단위 인가 | kinetic-action 정책 엔진 (`list_actions`) |
    | RFC 9728 보호 리소스 메타데이터, 401 `WWW-Authenticate` | kinetic-action + api-gateway entry point |
    | JWT 검증 | api-gateway (oauth2-resource-server) + kinetic-action 재검증 |
    | MCP 세션 고정 | 회피 — stateless Streamable HTTP, plan/run 은 DB |
    | MCP 의미 트레이스 | kinetic-action OTel span |
    | 주체 단위 레이트리밋 | api-gateway, 영향 범위는 `max_targets`/`confirm_threshold` |
- **AD-4 인스턴스 단위 실행 권한은 kinetic-action 자체 정책 (CEL).** 규칙 `{roles, when}` 의 OR, 기본 거부.
  `when` 은 `actor`(JWT 클레임) × `target`(인스턴스 속성) × `params` 의 CEL 식. 게이트웨이는 엔티티 속성을
  모르므로 인스턴스 판정은 실행기만 할 수 있다.
- **AD-5 plan → (승인) → execute 두 단계.** 에이전트는 plan 까지만 스스로 만들 수 있다. 허용 대상 수가
  `confirm_threshold` 를 넘으면 사람 승인(REST, Studio UI)이 필요하고 승인 도구는 MCP 에 노출하지 않는다.
  실행 직전에 대상과 정책을 다시 평가한다(TOCTOU).
- **AD-6 대상 선정은 구조화 필터.** 에이전트가 쓴 Cypher 를 받지 않는다. `where:[{prop, op, value}]` 를
  서버가 파라미터화 Cypher 로 바꾼다 — 주입과 범위 우회를 막는다.
- **AD-7 마이크로서비스는 내부 경로로만.** `/svc/<system>/**` 는 `X-Kinetic-Internal` 비밀이 있을 때만
  통과한다. 원시 서비스 API 가 에이전트에게 열리면 인스턴스 정책을 건너뛰는 우회로가 된다.
- **AD-8 대상별 독립 실행.** 분산 트랜잭션을 흉내 내지 않는다. 대상별 `Idempotency-Key`, 부분 성공 보고,
  재시도 한도 초과 시 `dead`(사람 처리). 사가 보상은 `compensate` 메타데이터만 두고 이후 단계로 미룬다.

## 기능 요구사항

- **FR-001** Studio 는 클래스에 액션을 정의·수정·삭제할 수 있다 (대상 시스템·operation·인자 매핑·파라미터
  스키마·정책·임계치). `class_behaviors` 에 `behavior_type` 판별자를 추가하고 기존 행은 `'sql'`.
- **FR-002** 발행은 액션을 계약 §1 형태로 그래프에 쓴다. 재발행 시 이전 액션 노드를 지운다.
- **FR-003** kinetic-action 은 서비스 레지스트리에 시스템(OpenAPI)을 등록하고 operation 목록을 제공한다.
- **FR-004** `list_actions` 는 호출자에게 적용 가능한 정책 규칙이 있는 액션만 보인다.
- **FR-005** `plan_action` 은 대상을 고르고 대상별 허용/거부(사유)·호출 미리보기·승인 필요 여부를 돌려준다.
- **FR-006** 승인이 필요한 plan 은 approver 역할의 REST 승인 없이는 실행되지 않는다.
- **FR-007** `execute_plan` 은 plan 작성자만, TTL 안에서, 대상·정책 재평가 후 대상별로 호출한다. 같은 plan 의
  재실행은 기존 run 을 돌려준다.
- **FR-008** 실패 대상은 재시도할 수 있고 한도를 넘으면 `dead` 가 된다.
- **FR-009** 모든 plan·승인·거부·실행은 감사 기록에 남는다.
- **FR-010** api-gateway 는 `/mcp/kinetic/**`, `/api/kinetic/**` 에 JWT 를 요구하고, `/svc/**` 를 동적 라우트로
  서비스에 연결한다 (비밀 헤더·서비스 인증 주입·재시도·서킷브레이커·타임아웃).
- **FR-011** Studio 채팅 `act` 모드는 plan 을 카드로 보여 주고 승인·실행을 사람이 누를 수 있게 한다.

- **FR-012** 액션은 여러 시스템에 걸친 **단계(steps)** 로 정의하고 단계마다 보상(compensation)을 둔다. 대상 하나가
  사가 하나다 — 중간 단계가 실패하면 앞 단계를 역순으로 자동 보상한다.
- **FR-013** 사용자가 "취소해"라고 하면 실행된 run 을 **역순**(대상은 완료 역순, 대상 안에서는 단계 역순)으로 보상한다.
  보상 호출 순서는 run 의 `compensations` 에 그대로 남는다.
- **FR-014** Studio 에 **시스템 등록** 메뉴가 있다 — 마이크로서비스를 데이터소스처럼 등록한다 (OpenAPI 가져오기,
  수동 API 등록, 상태 확인, 스펙 다시 읽기, 삭제). 등록하면 api-gateway 의 `/svc/<이름>` 경로가 생긴다.
- **FR-015** 질문과 행위는 **한 채팅**(질의·액션)에서 한다. 메뉴를 나누지 않는다.
- **FR-016** 온톨로지 구축에 **골든 커맨드**를 준다. 구축 에이전트는 등록된 시스템의 API 를 탐색해 커맨드마다 액션
  (단계·보상·정책 포함)을 만들고 dry-run 계획으로 검증한다 — 골든 퀘스천이 조회를 검증하듯이.

## 온보딩 흐름 (이 스펙이 겨냥하는 사용 방식)

```
시스템 등록(MES·설비보전·생산계획) → 데이터소스/문서 등록 → 의도 + 골든 퀘스천 + 골든 커맨드
  → 구축(클래스·인스턴스·액션 자동 설정) → 발행 → 질의·액션 채팅: 질문 → 커맨드 → 승인 → 실행 → 취소(역순 보상)
```

## 성공 기준

- **SC-001** 데모 `demo/kinetic-mes/verify_kinetic.py` 9개 시나리오 통과 (계약 문서 참조).
- **SC-002** 다른 공장 설비에 대한 실행은 0건이 서비스에 도달한다.
- **SC-003** 같은 plan 을 두 번 실행해도 서비스 수신 건수가 늘지 않는다.
- **SC-004** `/svc/**` 를 비밀 없이 부르면 403, 기존 api-gateway 라우트는 인증 없이 동작한다.

## 범위 밖

- Ontological DB 엔진·Bolt·포털 변경
- 데이터소스 가상 클래스(인스턴스가 그래프에 없는 클래스) 대상 액션 — 대상 선정이 그래프 인스턴스 기준이다
- 다중 대상 전체를 묶는 분산 트랜잭션(2PC) — 대상별 사가로 대신한다
- 시맨틱 라우팅·벡터 도구 가지치기
- Studio 사용자 인증(SSO) — 지금은 설정된 토큰이 행위 주체다
- data-secure-guard 연동 (역할 이름만 공유)

## 참고

- 계약: [contracts/kinetic-api.md](contracts/kinetic-api.md)
- 계획: [plan.md](plan.md) · 작업: [tasks.md](tasks.md)
