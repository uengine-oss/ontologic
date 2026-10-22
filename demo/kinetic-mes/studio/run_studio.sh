#!/usr/bin/env bash
# 영상·수동 시연용 Ontology Studio — 데모 그래프(7690)와 키네틱 스택(api-gateway 9000)에 붙인다.
#   ./run_studio.sh prepare   그래프 초기화 + Studio 에 액션 정의·발행
#   ./run_studio.sh start     백엔드 8011 · 프론트 5183 기동 (토큰 새로 발급)
#   ./run_studio.sh onboard   온보딩 시연 초기화 — 그래프 전부 비움 · CMMS 미등록 · 새 Studio 저장소 (start 전에)
#   ./run_studio.sh stop
# 사용자의 평소 Studio(sessions.db, 8000·8010/5173)와 섞이지 않게 SQLite·포트를 따로 쓴다.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
STUDIO="$(cd "$DEMO/../../ontology-studio" && pwd)"
RUN="$HERE/.run"; mkdir -p "$RUN"

tok() { (cd "$DEMO" && uv run python -c "import seed,sys; print(seed.token(sys.argv[1], sys.argv[2].split(','), plant='P1'))" "$1" "$2"); }

export SESSION_DB_PATH="${SESSION_DB_PATH:-$RUN/sessions.db}"
export NEO4J_URI=bolt://localhost:7690 NEO4J_USER=neo4j NEO4J_PASSWORD=kineticdemo
export KINETIC_URL=http://127.0.0.1:9000 KINETIC_MCP_URL=http://127.0.0.1:9000/mcp/kinetic/
export KINETIC_NEO4J_URI=bolt://localhost:7690 MOCK_MES_URL_FOR_KINETIC=http://localhost:8031
export AGENT_BACKEND=deepagents SANDBOX_BACKEND=local BACKEND_PORT=8011
# act 모드의 읽기 도구는 온톨로지 MCP 를 거친다 — 평소 8100 과 겹치지 않게 8101.
# 실행 역할 목록 — 구축 에이전트가 정책 역할 이름을 지어내지 않게 (IdP 의 역할을 그대로 적는다)
export KINETIC_ROLE_CATALOG="${KINETIC_ROLE_CATALOG:-}"
[ -n "$KINETIC_ROLE_CATALOG" ] || export KINETIC_ROLE_CATALOG='[{"role":"plant_operator","description":"공장 설비 운영자 — 자기 공장 설비만 다룬다","claims":["plant"]},{"role":"kinetic_approver","description":"공장장 — 실행 계획 승인"},{"role":"kinetic_admin","description":"시스템 등록 관리자"}]'
export MCP_PORT=8101 MCP_TRANSPORT=http MCP_ALLOW_DATASOURCE_EXPANSION=true

case "${1:-start}" in
  prepare)
    rm -f "$SESSION_DB_PATH"*
    export KINETIC_STUDIO_TOKEN="$(tok park.manager kinetic_approver,kinetic_admin)"
    (cd "$STUDIO" && uv run python "$HERE/prepare_studio.py")
    ;;
  onboard)
    rm -f "$SESSION_DB_PATH"*
    (cd "$DEMO" && uv run python "$HERE/onboard_reset.py")
    ;;
  start)
    # 화면(승인 카드·시스템 등록)은 공장장 박 과장(승인자 + 레지스트리 관리자), 채팅 에이전트는
    # P1 운영자 김 대리로 행동한다.
    export KINETIC_STUDIO_TOKEN="$(tok park.manager kinetic_approver,kinetic_admin)"
    export KINETIC_AGENT_TOKEN="$(tok "${AGENT_SUB:-kim.operator}" "${AGENT_ROLES:-plant_operator}")"  # PriMES 데모 등은 env 로 바꾼다
    ( cd "$STUDIO" && nohup uv run ontology-studio-mcp > "$RUN/mcp.log" 2>&1 & echo $! > "$RUN/mcp.pid" )
    ( cd "$STUDIO" && nohup uv run ontology-studio-backend > "$RUN/backend.log" 2>&1 & echo $! > "$RUN/backend.pid" )
    ( cd "$STUDIO/frontend" && VITE_API_BASE=http://localhost:8011 nohup npx vite --port 5183 --strictPort > "$RUN/frontend.log" 2>&1 & echo $! > "$RUN/frontend.pid" )
    for i in $(seq 1 60); do curl -sf -m2 localhost:8011/api/act/health >/dev/null && break; sleep 2; done
    curl -s localhost:8011/api/act/health; echo
    ;;
  stop)
    for p in mcp backend frontend; do [ -f "$RUN/$p.pid" ] && kill "$(cat "$RUN/$p.pid")" 2>/dev/null || true; done
    pkill -f "vite --port 5183" 2>/dev/null || true
    for port in 8011 8101; do lsof -t -iTCP:$port -sTCP:LISTEN | xargs kill 2>/dev/null || true; done
    ;;
esac
