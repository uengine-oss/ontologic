# 계약: DLQ·게이트 원인 코드

원천: `ontology-studio/backend/src/modules/quality/codes.py`. **추가만 한다** — 이름을 바꾸면 이미
쌓인 DLQ 항목이 어떤 그룹에도 속하지 않는다.

| 코드 | 종류 | 단계 | 의미 | 재처리 |
|---|---|---|---|---|
| `ID_MISSING` | hard | gate | 필수 식별자 결측 — 노드로 승격 안 함 | 원천·파서 수정 후 |
| `REL_ENDPOINT_MISSING` | hard | gate | 관계 양 끝 노드 없음 (파서 경로) | 끝점 적재 후 |
| `ONTO_CLASS_UNKNOWN` | hard | gate | 스키마에 없는 클래스 | 클래스 추가 또는 TBox 제안 승인 후 |
| `ONTO_DOMAIN` / `ONTO_RANGE` | hard | gate | 관계 정의역/공역 위반 | 관계 정의 수정 후 |
| `ONTO_PREDICATE_UNKNOWN` | hard | gate | 허용 어휘에 없는 술어 | 관계 추가 후 |
| `ONTO_PROPERTY_UNKNOWN` | hard | gate | 선언되지 않은 속성 | 속성 선언 후 |
| `ONTO_CARDINALITY` | hard | gate | 최대 연결 수 초과 | 기존 관계 정리 후 |
| `ONTO_INVALID_NAME` | hard | gate | 라벨·관계 이름 불가 문자열 | 이름 수정(수정 후 승인) |
| `PARSE_JSON` | hard | extract | 모델 출력 해석 실패(모든 샘플) | 청크 재추출 |
| `LOW_CONFIDENCE` | — | gate | S_c < 검수 하한 | 정책·스키마 조정 후 |
| `WRITE_FAILED` | — | write | Bolt 쓰기 오류 | 그래프 복구 후 |
| `PROP_DATATYPE` | soft | — | 타입 불일치 → 검수로 | — |
| `ENTITY_AMBIGUOUS` | soft | — | 해소 후보 차 < 0.15 → 검수로 | — |
| `PREDICATE_SYNONYM` | soft | — | 유사어 매핑 → 검수로 | — |
| `TBOX_PROPOSAL` | soft | — | 스키마 제안 → 항상 검수 | — |
| `SRC_NULL_RATIO` `SRC_RANGE` `SRC_UNIQUE` `SRC_IN_SET` `SRC_FK` | — | source | 원천 정형 검증 (row) | 원천 정제 후 — 현재 파일 재판정 |
| `SRC_TABLE_BLOCKED` | — | source | block 규칙 실패 → 테이블 전체 중단 | 원천 정제 후 테이블 재적재 |
| `IMPUTED` `LINK_PREDICTED` `SAME_AS_PROPOSAL` | soft | — | 추론 기반 제안 → 항상 검수 | — |
| `SHAPE_MIN_COUNT` `SHAPE_MAX_COUNT` `SHAPE_DATATYPE` `SHAPE_DISJOINT` | — | shape | 그래프 Shape 검증 | 데이터 수정 후 재검사(해소 시 자동 닫힘) |
| `ORPHAN_NODE` | — | lint | 고립 노드 | 언급 원문 재추출 |
| `ER_CONFLICT` | — | identity | SAME_AS 로 이어진 개체의 값 충돌 | 대표 값 선택 (원천 값은 보존) |

재처리(`POST /api/quality/dlq/redrive`): 현재 스키마·정책으로 **실패 단계부터** 다시 판단한다.
- 후보(payload.kind) → `pipeline.process`
- 파서 항목(payload.source = parser) → 같은 `batch_ingest` 재선별
- 추출 항목(stage = extract) → 청크 재추출

같은 사실은 fingerprint·MERGE 로 멱등이다. 시도 3회 이상은 화면에 한도로 표시된다.
