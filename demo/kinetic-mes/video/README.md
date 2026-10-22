# 키네틱 액션 시연 영상 — 설비 과열 점검 전환

`키네틱-액션-설비점검-시연.mp4` (4분 45초, 1920×1080, 14장면) · 자막 `키네틱-액션-설비점검-시연.srt`

정지화면 방식이다 — 브라우저를 벽시계로 녹화하지 않고 장면마다 캡처한 뒤, 장면 길이를 나레이션 음성의
실측 길이로 맞춰 합친다. 실행 자체는 캡처 중에 **실제로 한 건** 돈다 (LLM act 모드 → 계획 → 공장장 승인 →
실행 → MES 수신).

## 재생성

```bash
# 0) 스택: demo/kinetic-mes compose(neo4j·mock-mes·dev-idp) + kinetic-action 8030 + api-gateway 9000
cd demo/kinetic-mes/studio
./run_studio.sh prepare      # 그래프 초기화 + Studio 에 액션 정의·발행 (처음 한 번)
./run_studio.sh start        # Studio 백엔드 8011 · 온톨로지 MCP 8101 · 프론트 5183
cd .. && uv run python studio/reset_run.py     # 설비 RUNNING · MES 기록 비우기

# 1) 음성 (대본을 고쳤을 때만)
cd video
/Users/uengine/process-gpt/services/completion/.venv/bin/python \
  /Users/uengine/process-gpt/.claude/skills/process-gpt-demo/scripts/gen_narration_openai.py \
  --script narration.json --out-dir narration --voice marin --env-file /Users/uengine/process-gpt/.env

# 2) 캡처 (화면 검증 실패 시 FAIL-*.png 를 남기고 멈춘다) → 3) 합성
node capture.mjs && python3 build_video.py
```

## 검증 (2026-10-22)

- CP-A 금지 표현 0 · 제외 대상 0 · 도입부 인프라 용어 0 (`check_narration.py`)
- CP-B `checks.txt` 19장 전부 통과 — 계획 허용 3·거부 2(사유 「담당 공장 설비만」), 승인됨, run succeeded,
  MES 수신 정확히 3건(2공장 0건), 그래프 MAINTENANCE 3대
- CP-C 디코드 오류 0 · 영상 트랙 계산값 = 음성 277.7초 (마지막 정리 화면이 약 8초 더 남는다)
