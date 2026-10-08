# Feature Specification: 추출 신뢰도 게이트 · HITL 검수 · 원천 오류 DLQ 재처리

**Feature Branch**: `013-extraction-confidence-hitl-quality`

**Created**: 2026-10-06

**Status**: 1~4단계 Implemented (2026-10-06)

**Input**: `docs/requirements/GraphRAG 온톨로지 구축 조사.pdf` 의 요구사항 2번(Entity·Relation·Property
자동 생성 범위와 사용자 검수(HITL) 체계)과 3번(원천 데이터 오류·불일치·누락 검증 규칙 및 재처리
메커니즘)을, 복합 신뢰도 S_c(LLM 일관성·원문 근거·스키마 정합성·그래프 지지도) 조사 내용을
기반으로 Ontology Studio 에 적용한다.

## 왜 이 스펙이 플랫폼 단위인가

- 그래프 인스턴스에 **새 출처 속성**(`_confidence/_run_id/_evidence_ref`)이 생긴다 —
  [`docs/graph-schema-contract.md`](../../docs/graph-schema-contract.md) 개정.
- ontological-db 와의 경계: 출처는 Bolt **트랜잭션 메타데이터**(`actor/source/reason`)로 넘기고
  ontological 의 감사·스탬프(spec 014)가 기록한다. Studio 는 그 내부 SQL 을 부르지 않는다.
- 헌법 ontology-studio 절에 규칙이 추가된다 — "추출한 지식은 후보로 쌓고, 신뢰도 게이트를
  지난 것만 그래프에 쓴다".

## 현재 코드 현실 — 조사 결과

- **CR-1** 문서 → 그래프 경로에 LLM 삼중주 추출이 없었다. 빌드 에이전트가 짠 정규식 파서 결과를
  `batch_ingest` 가 **검증 없이** MERGE 했다. id 가 없으면 `_source_id: ""` 하나로 합쳐졌고,
  끝점이 없는 관계도 성공으로 셌다.
- **CR-2** 어디서도 logprobs 를 쓰지 않는다. 기본 모델(`gpt-5.4*`)은 reasoning 계열이라 지원하지 않는다.
- **CR-3** 검수 패턴은 이미 있다 — 인과 가설(`causal_hypotheses.decision`, `causal_apply` 는
  에이전트 도구에서 제외), 역바인딩 후보(`auto|needs_review|no_match|conflict`).
- **CR-4** SHACL·DLQ·재처리·sameAs·인스턴스 신뢰도·잡 큐는 플랫폼 어디에도 없다. ontological 의
  SHACL(spec 006 T019)은 미구현이다.

## 아키텍처 결정

- **AD-1 스테이징은 Studio SQLite**(`triple_candidates`, `dlq_items`, `review_feedback`,
  `extraction_runs`, `quality_policy`). 그래프에는 통과한 것만 간다.
- **AD-2 그래프 쓰기 단일 진입점** `quality/ingest_gate.py`. Bolt + tx_metadata.
- **AD-3 S_c = G_onto × m_vocab × combine(S_llm, S_ground, S_graph)**
  ([contracts/confidence-score.md](contracts/confidence-score.md)). 3단 분기: ≥0.85 자동 적재,
  0.60~0.85 HITL, 미만·게이트 위반 DLQ.
- **AD-4 지시문은 `skills/triple-extract/SKILL.md`**. 파이썬은 허용 클래스·관계, 검수 예시,
  청크를 값 블록으로만 넘긴다.
- **AD-5 logprob 는 선택**(`QUALITY_EXTRACT_LOGPROBS=1` + 지원 모델). 없으면 α=0, 자기일관성
  S_freq 만 쓴다.
- **AD-6 사람 판단은 구조로 강제** — 검수 결정·DLQ 재처리는 에이전트 도구에 없다.
- **AD-7 TBox 제안은 항상 검수** — 점수로 자동 반영도 폐기도 하지 않는다. 승인 시 SQLite 스키마에
  반영하고 provenance(`manual/human`)를 남긴다. 발행·릴리스는 기존 경로(publish / release)를 탄다.
- **AD-8 파서 경로는 구조 위반만 막는다**(`quality/parser_screen.py`). 미등록 클래스는 막지 않는다.

## 구성요소별 자동화 범위 (요구사항 2 표 대응)

| 구성요소 | 자동화 | 검수 분기 | 구현 |
|---|---|---|---|
| Entity | 스키마 클래스 매칭 시 자동 | 엔터티 해소 1·2위 차 < 0.15 → `ENTITY_AMBIGUOUS` 검수 | `pipeline.default_resolve_margin` |
| Relation | 허용 술어·domain/range 강제 추출, S_c 3단 분기 | 0.60~0.85 → 원문 하이라이트 + 인접 서브그래프 검수 | `extraction.py`, `QualityPanel.vue` |
| Property | 선언 속성만, 타입 검사 | 타입 위반 → `PROP_DATATYPE` 자동 플래그 검수 | `gate.datatype_ok` |
| TBox | 제안만 | 항상 전문가 승인 | `pipeline._apply_tbox` |

## 검증 계층 (요구사항 3 표 대응)

| 계층 | 단계 | 검증 | 실패 시 |
|---|---|---|---|
| 추출·게이트 | **1단계 구현** | 식별자 결측, 클래스·술어 어휘, domain/range, 카디널리티, 라벨 문자열, 파싱 | DLQ(`ID_MISSING`, `ONTO_*`, `PARSE_JSON`, `LOW_CONFIDENCE`, `WRITE_FAILED`) |
| 원천 정형 | **2단계 구현** | not_null(비율)·between·unique·in_set·fk. CSV 는 파이썬(`expectations.evaluate_rows`), 바인딩 테이블은 집계 SQL(`compile_sql` → text2sql) | row: 실패 행만 DLQ(`SRC_*`) · block: 테이블 전체 중단(`SRC_TABLE_BLOCKED`). 재처리는 **현재 파일**을 다시 읽는다 |
| 시맨틱 그래프 | **2단계 구현** | 스키마에서 자동 생성한 Shape(required→min_count, type→datatype) + 사용자 규칙(max_count·min_rel·disjoint)을 읽기 전용 Cypher 로 (`shapes.py`) | DLQ(`SHAPE_*`), 재검사에서 해소되면 자동으로 닫힘. 고아 노드 린팅(`lint.py`, `ORPHAN_NODE`) → 재처리 = 원문 재추출 |
| 식별자 해소 | **3단계 구현** | 식별 속성 일치·법인 표기 정규화 이름·유사도 (`identity.py`) | ≥0.95 SAME_AS 자동, 0.80~0.95 검수(`SAME_AS_PROPOSAL`). 덮어쓰기 금지 — `_source_system/_source_key` 보존, 값 충돌은 DLQ(`ER_CONFLICT`), 사람이 고른 대표 값만 기록 |
| 누락 보정 | **3단계 구현** | 동일 개체 값 → 이웃 패턴 최빈값 → 클래스 기본값 (`imputation.py`) | 항상 검수(`IMPUTED`). (노드, 속성)당 제안 하나 |
| KGE | **4단계 구현** | 순수 파이썬 TransE (`kge.py`) — S_graph = (1−w)·경로 + w·KGE, 링크 예측(p≥0.7) | 예측은 항상 검수(`LINK_PREDICTED`). 판정 JSONL·학습 삼중주 TSV 내보내기 |

원인 코드 전체: [contracts/dlq-codes.md](contracts/dlq-codes.md).

## User Scenarios & Testing

### US1 — 문서에서 추출한 관계가 근거에 따라 갈린다 (P1, 구현)

**Acceptance**
1. 스키마가 허용하는 관계가 원문에 그대로 있고 3회 샘플 모두에서 나오면 자동 적재되고,
   그래프 관계에 `_confidence/_run_id/_evidence_ref` 가 붙는다.
2. 3회 중 1회만 나온 관계는 검수 큐로 가고 그래프에 없다.
3. 정의역을 어긴 관계는 `ONTO_DOMAIN` 으로 DLQ 에 간다.

### US2 — 검수자가 근거를 보고 판단한다 (P1, 구현)

1. 검수 화면에 원문 인용 하이라이트, 점수 분해(S_llm·S_ground·S_graph·G×m·S_c), 인접 서브그래프
   (후보 관계는 점선)가 함께 보인다.
2. 승인하면 게이트를 다시 거친 뒤 검수자 이름(`actor`)으로 그래프에 쓰인다.
3. 수정 후 승인은 수정본으로 게이트를 다시 거친다. 위반이면 쓰지 않고 이유를 보여 준다.
4. 기각한 사실은 재추출해도 되살아나지 않는다.
5. 판정은 다음 추출의 `[검수 예시]` 값으로 들어간다.

### US3 — DLQ 를 원인별로 보고 재처리한다 (P1, 구현)

1. DLQ 가 원인 코드별로 집계된다.
2. 스키마를 고친 뒤 재처리하면 **현재** 스키마·정책으로 다시 판단해 적재한다. 같은 사실은 MERGE.
3. 재처리 횟수가 쌓이고 3회 이상은 한도로 표시된다.

### US4 — 원천 정형 데이터 검증 (P2, 구현)
1. ERP 협력사 마스터 CSV 7행 → 키 결측·키 중복·범위·FK 실패 3행 격리, 4행 적재. block 규칙(사업자번호 결측 ≤20%)은 통과.
2. block 규칙이 실패하면 한 행도 쓰지 않는다.
### US5 — 그래프 Shape 검증·고아 노드 린팅 (P2, 구현)
1. 필수 속성 누락 노드가 `SHAPE_MIN_COUNT` 로 격리되고, 값이 채워진 뒤 재검사하면 자동으로 닫힌다.
2. 고립 노드 재처리는 그 노드를 언급한 원문을 재추출하고, 새 관계는 신뢰도 경로를 탄다.
### US6 — 다중 소스 식별자 해소 SAME_AS (P3, 구현)
1. ERP '(주)한빛전자' ↔ 문서 '한빛전자' 가 SAME_AS 로 이어지고, 두 노드의 신용점수(88/91)는 그대로 남는다.
2. 값 충돌은 DLQ 로 가고, 대표 값 선택은 `identity_preferences` 에만 기록된다.
### US7 — KGE 기반 S_graph, 학습셋 내보내기 (P4, 구현)
1. 학습 후 (공급사, SUPPLIES, 제품) 0.76 > (구매사, SUPPLIES, 제품) 0.16.

## Functional Requirements (1단계)

- **FR-001** 추출 결과는 `triple_candidates` 에 저장하고 그래프에는 `ingest_gate` 로만 쓴다.
- **FR-002** S_c 와 분기 임계값·가중치·결합 방식은 스키마별 정책으로 바꿀 수 있다
  (`GET|PUT /api/quality/policy/{schema_id}`), 가중치 합은 1.
- **FR-003** G_onto hard 위반은 점수와 무관하게 DLQ, soft 플래그는 자동 적재를 막고 검수로 보낸다.
- **FR-004** 사람의 결정은 fingerprint 로 보존한다.
- **FR-005** 검수 결정·DLQ 재처리는 HTTP(화면)로만 가능하다.
- **FR-006** `batch_ingest` 는 구조 위반 항목을 DLQ 로 격리하고 결과에 `quarantined` 로 보고한다
  (`INGEST_GATE=false` 로 끌 수 있다).

API: [contracts/review-api.md](contracts/review-api.md).

## Success Criteria

- **SC-001** 통합 검증(`ontology-studio/tests/integration_verify_quality.py`)이 실 그래프에서 전부
  통과한다 — 분기, 출처 속성, 승인 반영, 재처리 적재, MERGE 멱등. (Neo4j 2026-10-06 통과,
  ontological-db 는 미검증 — Bolt 게이트웨이 미기동)
- **SC-002** E2E(`tests/e2e_triple_review.spec.js`) 통과 — 검수 큐 → 승인 → DLQ 재처리.
- **SC-004** 2~4단계 통합 검증(`integration_verify_quality.py --stages`) 9항목 Neo4j 통과, 단위 65개.
- **SC-005** 데모 영상: `ontology-studio/demo/out/extraction-quality-hitl-demo.mp4`(1편), `extraction-quality-stages-demo.mp4`(2편).
- **SC-006** 증권 공시 문서 실측 (`uengine-platform/demo-securities/quality-eval/`, report.html):
  LLM 추출 사실 168건 중 92건(55%)이 틀림. 게이트 적용 시 자동 적재 17건 전부 맞음(사람 전수 확인),
  틀린 사실 자동 유입 92 → 0, 검수 비율 54%. 실험에서 찾은 개선 — 지시어 이름 금지·문서 머리말 전달·
  `ENTITY_GENERIC` 게이트(지시어 사실 43 → 13), 머리말을 근거로 인정, 문서 추출 내부 중복 SAME_AS.
  정형 상품 마스터 원천 오류 4/4 검출·오탐 0, 검수 후 마스터·설명서 위험등급 불일치 충돌 검출.
- **SC-007** 사용자 중심 화면(`frontend/src/features/quality/`: 한눈에 · 확인하기 · 데이터 넣기 · 보류함,
  세부는 '자세히 보기' 와 ⚙ 고급). E2E `tests/e2e_triple_review.spec.js` 통과.
- **SC-008** 구축 흐름 통합: 빌드 스킬 Phase 4(검수), 구축 화면 ‘검수’ 탭(`BuildReviewPanel`), 빌드 보고서
  `quality`(저장소 실측). 실제 Claude Code 에이전트 구축 실행에서 `extract_triples`·`table_ingest`·`quality_checkup`
  호출, 승인·재처리 0건, 보고서 검수 대기 15·보류 8 = 화면 숫자. 품질 화면은 검수 전용(데이터 넣기 제거).
- **SC-003** (측정 예정) 골든 문서 세트에서 자동 적재 구간 precision ≥ 0.9, HITL 비율, 골든
  퀘스천 정답률을 게이트 없는 기존 경로와 비교한다.
