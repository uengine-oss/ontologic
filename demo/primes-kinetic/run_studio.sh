#!/usr/bin/env bash
# PriMES 키네틱 데모용 Studio — kinetic-mes 의 run_studio.sh 를 PriMES 신원·역할·저장소로 띄운다.
#   ./run_studio.sh reset    그래프 비움 + PriMES 시스템 등록 + 새 Studio 저장소
#   ./run_studio.sh prepare  인스턴스 적재(PriMES 조회) + 액션 정의 + 발행 (reset 뒤, start 전)
#   ./run_studio.sh start | stop
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
S="$HERE/../kinetic-mes/studio/run_studio.sh"
mkdir -p "$HERE/.run"
export SESSION_DB_PATH="$HERE/.run/sessions.db"
export AGENT_SUB=kim.planner AGENT_ROLES=sales_rep,production_planner
export KINETIC_ROLE_CATALOG='[{"role":"sales_rep","description":"영업 담당 — 수주 등록·변경·취소"},{"role":"production_planner","description":"생산관리 — 자재 발주, 작업지시 발행·취소, 금형 장착"},{"role":"kinetic_approver","description":"생산관리자 — 실행 계획 승인"},{"role":"kinetic_admin","description":"시스템 등록 관리자"}]'
case "${1:-start}" in
  reset) "$S" stop || true; sleep 2; rm -f "$SESSION_DB_PATH"*
         rm -rf /Users/uengine/ontologic/ontology-studio/.cache/sandbox/uploads/*   # 앞 데모의 업로드가 섞이지 않게
         (cd "$HERE/../kinetic-mes" && uv run python "$HERE/reset.py") ;;
  prepare) export KINETIC_STUDIO_TOKEN="$(cd "$HERE/../kinetic-mes" && uv run python -c "import seed;print(seed.token('park.manager',['kinetic_approver','kinetic_admin']))")"
         (cd /Users/uengine/ontologic/ontology-studio && uv run python "$HERE/prepare.py") ;;
  start) ( "$S" start > "$HERE/.run/start.out" 2>&1 & )
         for i in $(seq 1 60); do curl -sf -m2 localhost:8011/api/act/health >/dev/null && lsof -iTCP:8101 -sTCP:LISTEN >/dev/null && break; sleep 3; done
         curl -s localhost:8011/api/act/health; echo ;;
  stop)  "$S" stop ;;
esac
