# 에이전트 실행 로그 원본

[`docs/agentic-rag-walkthrough.md`](../../docs/agentic-rag-walkthrough.md) 가 정리한 내용의
**원자료**다. 정리본은 읽기 쉽게 줄인 것이므로, "에이전트가 실제로 무슨 인자로 무엇을
호출했는가"를 확인하려면 여기를 본다.

전부 **ontology-studio 백엔드가 꺼진 상태**에서 `SESSION_DB_PATH=/nonexistent/none.db` 로
실행했다. 에이전트가 본 온톨로지는 그래프에 발행된 것뿐이다.

## 파일

| 파일 | 내용 |
|---|---|
| `claude-run-raw.jsonl` | Claude Code `-p` 원본 스트림 (86KB, 이벤트 50건) |
| `claude-opus-run.md` | 위를 사람이 읽게 렌더한 것 |
| `gpt41-run1..8.md` | OpenAI 하네스 실행 기록 (시나리오 1~7) |
| `system-prompt.md` | MCP 서버가 제공한 시스템 프롬프트 — 두 에이전트에 **같은 것**을 줬다 |
| `mcp-config.json` | Claude Code 에 넘긴 MCP 설정 |
| `text2sql.log` · `mcp-server.log` | 서버측 로그 |

## 재현

```bash
# 0) 발행 (스튜디오가 켜져 있을 때 한 번)
uv run python scripts/seed_hybrid_demo.py --datasource legacy

# 1) MCP 서버만 (스튜디오는 꺼도 된다)
cd ontology-studio
SESSION_DB_PATH=/nonexistent/none.db MCP_TRANSPORT=http MCP_PORT=8100 \
  MCP_ALLOW_DATASOURCE_EXPANSION=true uv run python -m backend.src.modules.ontology_mcp

# 2-a) OpenAI 하네스
set -a && . ../.env && set +a
uv run python ../scripts/agentic_rag_session.py --question "…" --out run.md

# 2-b) Claude Code 헤드리스 — 전체 스트림 캡처
cd ../demo/agent-runs
claude -p "<질문>" \
  --mcp-config mcp-config.json \
  --append-system-prompt "$(cat system-prompt.md)" \
  --allowed-tools "mcp__ontologic__ontology_resolve_entity,mcp__ontologic__ontology_graph_cypher,mcp__ontologic__ontology_get_datasource_schema,mcp__ontologic__ontology_query_datasource_sql,ListMcpResourcesTool,ReadMcpResourceTool" \
  --output-format stream-json --verbose > claude-run-raw.jsonl

uv run python ../../scripts/render_claude_run.py claude-run-raw.jsonl > claude-opus-run.md
```

## 로그를 볼 때 알아 둘 것

- `claude-run-raw.jsonl` 의 `init` 이벤트에 `ontology-studio-build` / `ontology-studio-answer`
  가 **`status=failed`** 로 찍혀 있다. 정상이다 — 그 둘은 루트 `.mcp.json` 이 가리키는
  스튜디오 백엔드(:8000) 브리지이고, 이 시험은 그 백엔드를 **일부러 꺼 둔** 상태다.
  이번 시험 대상인 `ontologic` 서버만 `connected` 다. 이 한 줄이 "스튜디오 없이 동작한다"의
  가장 직접적인 증거다.
- Claude Code 는 이 환경에서 도구를 지연 로딩하므로 첫 호출이 `ToolSearch` 다. MCP 도구를
  쓰기 전 스키마를 가져오는 단계이며 온톨로지 조회와는 무관하다.
- `graph://schema` 는 MCP **리소스**다. Claude Code 는 `ReadMcpResourceTool` 로 직접 읽고,
  OpenAI 하네스는 리소스 개념이 없어 `read_graph_schema` 라는 얇은 래퍼로 감싼다
  (`scripts/agentic_rag_session.py`). 두 로그에서 이 단계의 이름이 다른 이유다.
