# 계약: 품질 API (`/api/quality`)

구현: `ontology-studio/backend/src/modules/quality/api.py`. 화면: `frontend/src/features/quality/QualityPanel.vue`.

| 메서드 | 경로 | 본문 / 쿼리 | 설명 |
|---|---|---|---|
| GET | `/policy/{schema_id}` | | 스키마별 정책 |
| PUT | `/policy/{schema_id}` | `{policy: {...}}` | 부분 갱신, 검증 실패 422 |
| POST | `/extract` | `{schema_id, text? \| filename?, session_id?, doc?, samples?, max_chunks?}` | 추출 → 분기. 실행 통계 반환 |
| GET | `/candidates` | `schema_id, status=pending, kind?, limit, offset` | status 는 쉼표 구분 다중 |
| GET | `/candidates/{id}` | | |
| GET | `/candidates/{id}/neighborhood` | | 주어·목적어 1홉 서브그래프 (Bolt 읽기) |
| POST | `/candidates/{id}/decide` | `{decision: approve\|reject\|edit, reviewer, edit?}` | 게이트 재검사 후 적재. 위반 422 |
| POST | `/candidates/bulk-decide` | `{ids, decision: approve\|reject, reviewer}` | |
| GET | `/dlq` | `schema_id, status=open, reason_code?` | 항목 + 코드별 개수 |
| POST | `/dlq/redrive` | `{ids}` 또는 `{schema_id, reason_code?}` | outcome: ingested / queued_for_review / reextracted / still_failing / skipped |
| POST | `/dlq/{id}/discard` | | 후보는 rejected 로 |
| GET | `/summary` | `schema_id` | 상태별·코드별 개수, 정책, 최근 실행 |
| GET | `/codes` | | 원인 코드 설명, hard/soft 집합 |

에이전트 도구(build 모드): `extract_triples(source, schema_name, samples)`, `quality_report(schema_name)`.
`decide` / `redrive` / `discard` 는 에이전트 도구에 **없다**.

`edit` 형식:
- 관계: `{subject: {name}, predicate, object: {name, class?}}`
- 속성: `{value}`
- 엔터티: `{subject: {name, class}}`
- TBox: `{tbox: {name, description}}`

## 2~4단계

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET/POST/DELETE | `/rules` | 원천(source)·형상(shape) 사용자 규칙 |
| POST | `/source/preview` | CSV 컬럼·앞 행 |
| POST | `/source/ingest` | `{schema_id, filename, session_id, mapping, dry_run}` 원천 검증 → 적재 |
| POST | `/source/check-table` | 바인딩 테이블 집계 SQL 검증 (text2sql 경유) |
| GET | `/shapes` · POST `/shapes/run` | 생성된 Shape 목록 · 실행 |
| POST | `/lint` | 고립 노드 린팅 |
| POST | `/identity/run` · GET `/identity/clusters` | SAME_AS 해소 · 클러스터(원천별 값·대표 값) |
| POST | `/identity/conflicts/{dlq_id}/resolve` | `{value, source}` 대표 값 선택 |
| POST | `/impute` | 누락 보정 + KGE 링크 예측 제안 (모두 검수) |
| POST | `/kge/train` · GET `/kge` · GET `/kge/score` | TransE 학습 · 상태 · (h, r, t) 점수 |
| GET | `/export/feedback.jsonl` · `/export/kge-triples.tsv` | 학습 데이터 내보내기 |
| GET | `/reports` | 검증 보고서 이력 |
