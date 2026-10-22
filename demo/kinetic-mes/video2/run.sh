#!/usr/bin/env bash
# 온보딩 영상 — 초기화 → Studio 재기동 → 캡처 → 합성
set -euo pipefail
cd "$(dirname "$0")"
S=../studio
$S/run_studio.sh stop || true; sleep 2
$S/run_studio.sh onboard
( $S/run_studio.sh start > $S/.run/start.out 2>&1 & )
for i in $(seq 1 60); do curl -sf -m2 localhost:8011/api/act/health >/dev/null && lsof -iTCP:8101 -sTCP:LISTEN >/dev/null && break; sleep 3; done
rm -rf /Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/default /Users/uengine/ontologic/ontology-studio/.cache/sandbox/uploads/설비대장.md
node capture.mjs
python3 build_video.py
