# Implementation Plan: 키네틱 액션 레이어

**Spec**: [spec.md](spec.md) · **Contract**: [contracts/kinetic-api.md](contracts/kinetic-api.md)

## 구성

```
사용자/에이전트 (Studio 채팅 act 모드 · 외부 MCP 클라이언트)
      │ MCP(Streamable HTTP) + JWT
      ▼
api-gateway :9000  ── /mcp/kinetic/** · /api/kinetic/**  (JWT · 레이트리밋)
      ▼
kinetic-action :8030 (FastAPI + MCP stateless)
  카탈로그(그래프의 _OntologyBehavior{action}) · 서비스 레지스트리(OpenAPI)
  대상 선정(구조화 where → Cypher, Bolt 읽기) · CEL 정책 · plan/승인/execute · 이력·감사
      │  X-Kinetic-Internal · Idempotency-Key
      ▼
api-gateway /svc/<system>/**  (동적 라우트 · 서비스 인증 · Retry · CircuitBreaker)
      ▼
MES / ERP / SCM 마이크로서비스
```

## 구성요소별 작업 위치

| 구성요소 | 위치 | 스택 |
|---|---|---|
| 실행기 | `kinetic-action/` (신규) | Python 3.12 · uv · FastAPI · mcp · neo4j · cel-python · SQLAlchemy |
| 게이트웨이 | `api-gateway/` (확장) | Spring Cloud Gateway 2021.0.x · oauth2-resource-server · resilience4j |
| 정의·UI·act 모드 | `ontology-studio/` (확장) | FastAPI · SQLite · Vue |
| 데모 | `demo/kinetic-mes/` (신규) | dev IdP · mock MES · seed · verify |

## 포트

| 서비스 | 포트 |
|---|---|
| api-gateway | 9000 |
| kinetic-action | 8030 |
| mock MES (데모) | 8031 |
| dev IdP (데모) | 8032 |
| 데모 Neo4j | 7690 (bolt) · 7477 (http) |
| 데모 Postgres | 5440 |

## 위험과 대응

| 위험 | 대응 |
|---|---|
| 에이전트가 조건을 넓게 잡아 대량 실행 | `max_targets` 거부, `confirm_threshold` 초과 시 사람 승인, plan 카드에 대상 목록 |
| 에이전트가 원시 서비스 API 를 직접 호출 | `/svc/**` 비밀 헤더, MCP 에 서비스 도구 미노출 |
| plan 후 대상 속성 변경 (TOCTOU) | 실행 직전 재조회·재평가, 정책 잃은 대상 `skipped` |
| 재시도로 인한 중복 실행 | 대상별 `Idempotency-Key`, plan 재실행은 기존 run 반환 |
| Studio 무인증 | 설정 토큰 = 주체 (명시적 TODO), 승인 역할 분리 |
