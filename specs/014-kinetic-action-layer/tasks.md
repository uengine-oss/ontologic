# Tasks: 키네틱 액션 레이어

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Updated**: 2026-10-21

체크된 항목은 동작하며 테스트나 데모 검증으로 덮여 있다.

## Phase 0 — 계약
- [x] T001 공통 계약 `contracts/kinetic-api.md` (발행 형태·REST·MCP·인증·남향 헤더)

## Phase 1 — kinetic-action
- [x] T010 카탈로그: 그래프의 `HAS_ACTION` 액션 적재·주기 갱신·수동 갱신
- [x] T011 서비스 레지스트리: 시스템 등록, OpenAPI → operation, 라우트 원천(내부 헤더)
- [x] T012 JWT 검증, RFC 9728 메타데이터, 401 헤더
- [x] T013 구조화 where → 파라미터화 Cypher (주입 차단)
- [x] T014 CEL 정책: 도구 노출·인스턴스 판정·기본 거부
- [x] T015 plan: 허용/거부·미리보기·TTL·승인 게이트
- [x] T016 execute: 작성자·재평가·대상별 호출·멱등성·부분 성공
- [x] T017 retry → dead, writeback(선택)
- [x] T018 감사 기록
- [x] T019 MCP stateless 도구 6종

## Phase 2 — api-gateway
- [x] T020 북향 라우트 `/mcp/kinetic/**`, `/api/kinetic/**`, well-known (SSE 무버퍼)
- [x] T021 JWT (경로 한정) + RFC 9728 entry point
- [x] T022 `/svc/**` 비밀 헤더 검사
- [x] T023 동적 라우트 (주기 갱신, 서비스 인증 주입, Retry, CircuitBreaker, 타임아웃)
- [x] T024 주체 단위 인메모리 레이트리밋

## Phase 3 — Ontology Studio (단위 테스트 944 통과, UI·LLM 은 T043 에서 검증)
- [x] T030 `class_behaviors.behavior_type` 판별자 + 마이그레이션
- [x] T031 `class_actions` 저장·검증
- [x] T032 발행 `HAS_ACTION`, 재발행 정리, 카탈로그 갱신 통지
- [x] T033 빌드 에이전트 도구 `action_create/list/delete`
- [x] T034 kinetic 클라이언트·REST 프록시 (시스템·operation·plan·승인·실행)
- [x] T035 채팅 `act` 모드 + `skills/ontology-act`
- [x] T036 UI: 클래스 액션 탭, plan 카드

## Phase 4 — 데모·검증
- [x] T040 `demo/kinetic-mes` (dev IdP · mock MES · seed · compose)
- [x] T041 `verify_kinetic.py` 9개 시나리오 — 직접 경로
- [x] T042 `verify_kinetic.py` — api-gateway 경유
- [x] T043 Studio UI 로 질의 → plan 카드 → 승인 → 결과 — 실제 LLM act 모드·브라우저로 검증, 시연 영상 `demo/kinetic-mes/video` (act 모드 다음 턴이 plan id 를 잃던 문제 수정: `service.py` 새 스레드 분기에서 act 제외)

## Phase 5 — 사가·시스템 등록·온보딩 (2026-10-22)
- [x] T060 계약 §1.3 steps·보상, §3 레지스트리 확장, §7 데모 서비스 3종
- [x] T061 kinetic-action: 다단계 실행·자동 보상·역순 취소·재시도 시도 번호
- [x] T062 kinetic-action: 시스템 CRUD·수동 API·스펙 재조회·상태 확인
- [x] T063 mock-cmms · mock-aps + verify 시나리오 10~14
- [x] T064 Studio: 질의·액션 메뉴 통합
- [x] T065 Studio: 시스템 등록 메뉴
- [x] T066 Studio: 액션 단계·보상 편집기, 카드에 단계·보상 이력, 취소 버튼, compensate_run
- [x] T067 Studio: 골든 커맨드 — 구축 마법사·시스템 탐색 도구·액션 자동 설정·dry-run 검증
- [x] T069 계약 §8 등록 모델 — 인증 방식·OAuth2 토큰·Swagger2/YAML·연결 테스트·비 REST 등록
- [x] T068 온보딩 전체 시연 영상 — `demo/kinetic-mes/video2` (7분 14초, 실제 등록·구축·실행·취소·장애 보상)

## 이후 (not yet)
- [ ] T054 시스템 등록 직후 게이트웨이 라우트 반영 지연(갱신 주기만큼) — 등록 시 게이트웨이에 갱신 통지 또는 첫 호출 404 재시도
- [ ] T051 Studio SSO 와 사용자별 토큰
- [ ] T052 데이터소스 가상 클래스 대상 선정 (text2sql 경유)
- [ ] T053 이벤트 규칙(watch agent) → 액션 트리거
