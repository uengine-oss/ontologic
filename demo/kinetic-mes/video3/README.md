# 하이라이트 우선 편집 — 액션하는 온톨로지

`액션하는-온톨로지-하이라이트-온보딩.mp4` (4분 51초, 20장면) · 자막 `.srt`

구성: 질문(「질문만이 아니라 액션까지?」) → **활용 하이라이트**(질의 → 커맨드·계획 → 승인·실행 → 세 시스템 기록 →
취소 역순 보상 → 장애 자동 보상) → **어떻게 가능했나** → 시스템 등록 → 구축(문서·골든 커맨드) → 자동 설정된 액션 → 정리.

화면은 `../video2/slides` 의 실제 캡처를 재배치했고(도입 슬라이드만 `hook.mjs` 로 새로), 음성은 ElevenLabs.

```bash
node hook.mjs
ELEVENLABS_API_KEY=... ELEVENLABS_VOICE_ID=1PdAOcPlPTz12RwMyFVp python3 gen_elevenlabs.py   # 키는 env 로만
python3 build_video.py
```
