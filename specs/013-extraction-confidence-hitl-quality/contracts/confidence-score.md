# 계약: 복합 신뢰도 S_c

구현: `ontology-studio/backend/src/modules/quality/confidence.py`(순수 함수), `pipeline.evaluate`.

```
S_c = G_onto × m_vocab × combine(S_llm, S_ground, S_graph)
```

| 지표 | 식 | 입력 | 비고 |
|---|---|---|---|
| S_logprob | exp(mean(log p_i)) — 항목 JSON 구간 토큰만 | chat.completions logprobs | `QUALITY_EXTRACT_LOGPROBS=1` + 지원 모델일 때만 |
| S_freq | count / M | M회 샘플 | 기본 M=3 |
| S_llm | α·S_logprob + (1-α)·S_freq | | logprob 없으면 S_freq. 파서 경로는 1 |
| S_ground | e^{-λd} × (½·어휘 근거 + ½·정규화 cos) | 청크 텍스트, 임베딩 | d = 주어·목적어 **가장 가까운** 출현 쌍 사이 단어 수. cos 는 [0.15, 0.60] → [0,1] 로 늘린다. 임베딩 실패 시 cos 자리에 어휘 근거 |
| S_graph | 같은 관계가 이미 있으면 1; 2~3홉 경로가 있으면 max(prior, 1-e^{-Σ∏conf}); 없으면 prior | Bolt 읽기 | 기록 없는 엣지 conf=0.7, prior 기본 0.5 |
| G_onto | hard 위반 없으면 1 | 스키마(SQLite) | `gate.check` |
| m_vocab | 술어 유사어 매핑 점수 (정확·표기 정규화면 1) | difflib + 관계 설명 | 1 미만이면 `PREDICATE_SYNONYM` soft |

결합:
- linear: Σ w_i·S_i (기본 w = 0.3 / 0.5 / 0.2)
- harmonic: 1 / Σ (w_i / S_i). 한 지표가 0 이면 0.

분기:

| 조건 | 결과 |
|---|---|
| hard 위반 | DLQ (첫 코드가 reason_code) |
| S_c < review_threshold(0.60) | DLQ `LOW_CONFIDENCE` |
| S_c ≥ auto_threshold(0.85) 이고 soft 없음 | 자동 적재 |
| 그 외 | 검수 대기 |
| kind = tbox, hard 없음 | 항상 검수 대기 |

## 실측으로 바꾼 것 (2026-10-06 Neo4j 통합 검증)

1. 처음에는 "양 끝이 그래프에 있는데 우회 경로가 없음"을 prior 의 절반으로 깎았다. 이미 적재된
   사실을 다시 추출하면 S_c 가 0.85 아래로 떨어져 검수로 갔다. → 같은 관계가 이미 있으면 1,
   경로 없음은 prior 로 바꿨다.
2. 거리 d 를 첫 출현끼리 쟀다. 주어가 청크에 여러 번 나오면 같은 문장 안의 관계가 감쇠로
   검수에 떨어졌다. → 가장 가까운 출현 쌍으로 바꿨다.
