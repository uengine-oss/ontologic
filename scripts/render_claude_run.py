#!/usr/bin/env python3
"""`claude -p --output-format stream-json` 로그를 읽을 수 있는 기록으로 바꾼다.

원본 JSONL 은 이벤트가 한 줄씩 쌓인 형태라 사람이 훑기 어렵다. 그렇다고 요약만 남기면
"에이전트가 실제로 무엇을 호출했는가"라는 이 기록의 존재 이유가 사라지므로, **모든 도구
호출의 인자와 결과를 그대로** 옮기고 길이만 자른다.

사용법:
    claude -p "<질문>" --mcp-config mcp-config.json \
      --append-system-prompt "$(cat system-prompt.md)" \
      --allowed-tools "..." --output-format stream-json --verbose > run.jsonl
    uv run python scripts/render_claude_run.py run.jsonl > run.md
"""

from __future__ import annotations

import json
import sys


def clip(text: str, limit: int) -> str:
    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + f"\n… (총 {len(text):,}자)"


def render(path: str) -> str:
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    out: list[str] = []
    step = 0

    for row in rows:
        kind = row.get("type")

        if kind == "system" and row.get("subtype") == "init":
            out += [
                "## 실행 환경",
                "",
                f"- 모델: `{row.get('model')}`",
                f"- 세션: `{row.get('session_id')}`",
                f"- 사용 가능 도구: {len(row.get('tools', []))}개",
                "- MCP 서버:",
            ]
            for server in row.get("mcp_servers") or []:
                out.append(f"  - `{server.get('name')}` — **{server.get('status')}**")
            out += ["", "---", ""]

        elif kind == "assistant":
            for block in row["message"]["content"]:
                if block["type"] == "text" and block["text"].strip():
                    out += ["> " + line for line in block["text"].strip().splitlines()]
                    out.append("")
                elif block["type"] == "tool_use":
                    step += 1
                    out += [
                        f"### {step}. `{block['name']}`",
                        "",
                        "```json",
                        clip(json.dumps(block["input"], ensure_ascii=False, indent=2), 1400),
                        "```",
                        "",
                    ]

        elif kind == "user" and isinstance(row["message"].get("content"), list):
            for block in row["message"]["content"]:
                if block.get("type") != "tool_result":
                    continue
                content = block.get("content")
                if isinstance(content, list):
                    content = " ".join(part.get("text", "") for part in content)
                out += ["**결과**", "", "```json", clip(str(content), 1600), "```", ""]

        elif kind == "result":
            out += [
                "---",
                "",
                "## 최종 답변",
                "",
                row.get("result") or "",
                "",
                "---",
                "",
                f"턴 {row.get('num_turns')} · 소요 {row.get('duration_ms', 0) / 1000:.1f}s · "
                f"비용 ${row.get('total_cost_usd', 0):.4f} · 결과 `{row.get('subtype')}`",
                "",
            ]

    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    print(render(sys.argv[1]))
