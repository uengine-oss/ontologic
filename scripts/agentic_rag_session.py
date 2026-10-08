#!/usr/bin/env python3
"""MCP 에 붙은 LLM 에이전트가 스스로 도구를 골라 답하게 하고, 그 과정을 기록한다.

이 스크립트는 **검증이 아니라 시연**이다. 앞선 검증들은 도구를 우리가 직접 순서대로
불러서 결과를 확인했다. 여기서는 순서를 정해 주지 않는다 — 도구 목록과 프롬프트만 주고
LLM 이 알아서 그래프를 훑고, 필요한 스키마를 필요한 시점에 받아, SQL 로 집계하는지 본다.

그것이 이 MCP 가 노린 것이기 때문이다. 2-step JIT 전달은 사람이 파이프라인을 짜 주면
당연히 동작한다. 진짜 질문은 **에이전트가 그 순서를 스스로 밟는가** 이다.

지시문은 서버의 MCP 프롬프트(`ontologic_agentic_rag`)를 그대로 쓴다. 여기에 힌트를 더
적으면 무엇이 프롬프트 덕이고 무엇이 이 스크립트 덕인지 구분할 수 없게 된다.

사용법
------
    # 1) MCP 서버를 띄운다 (스튜디오는 꺼져 있어도 된다)
    cd ontology-studio
    SESSION_DB_PATH=/nonexistent/none.db MCP_TRANSPORT=http MCP_PORT=8100 \
      MCP_ALLOW_DATASOURCE_EXPANSION=true uv run python -m backend.src.modules.ontology_mcp

    # 2) 에이전트를 돌린다
    uv run python ../scripts/agentic_rag_session.py \
        --question "제품 PROD-001 의 라우팅에 포함된 공정 중 가동률이 가장 낮았던 설비와 그 일자는?"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import textwrap

DEFAULT_MCP_URL = os.environ.get("ONTOLOGY_STUDIO_MCP_URL", "http://127.0.0.1:8100") + "/mcp"
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gpt-4.1")

#: 도구 호출 상한. 하이브리드 질문은 5~6회 안에 끝나야 한다는 것이 스킬의 예산이고,
#: 넘어가면 그 자체가 관찰 결과다(대개 JIT 단계를 건너뛰고 컬럼을 추측한 경우).
MAX_STEPS = 12


def _short(value, limit: int = 600) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + f"… (총 {len(text)}자)"


class Transcript:
    """사람이 읽을 기록. 마크다운으로 그대로 떨어뜨린다."""

    def __init__(self, question: str, model: str, mcp_url: str) -> None:
        self.question = question
        self.model = model
        self.mcp_url = mcp_url
        self.steps: list[dict] = []
        self.answer = ""
        self.tools: list[str] = []
        self.prompt_chars = 0

    def record(self, name: str, args: dict, result: str) -> None:
        self.steps.append({"name": name, "args": args, "result": result})

    def to_markdown(self) -> str:
        lines = [
            f"### 질문",
            "",
            f"> {self.question}",
            "",
            f"모델 `{self.model}` · MCP `{self.mcp_url}` · 도구 {len(self.tools)}개 · "
            f"시스템 프롬프트 {self.prompt_chars:,}자 (서버가 제공)",
            "",
            f"에이전트는 도구를 **{len(self.steps)}회** 호출했다.",
            "",
        ]
        for i, step in enumerate(self.steps, 1):
            lines += [
                f"#### {i}. `{step['name']}`",
                "",
                "```json",
                json.dumps(step["args"], ensure_ascii=False, indent=2),
                "```",
                "",
                "```json",
                _short(step["result"], 900),
                "```",
                "",
            ]
        lines += ["#### 최종 답변", "", self.answer, ""]
        return "\n".join(lines)


async def run(question: str, mcp_url: str, model: str) -> Transcript:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from openai import OpenAI

    transcript = Transcript(question, model, mcp_url)
    client = OpenAI()

    async with streamablehttp_client(mcp_url) as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            listed = await session.list_tools()
            transcript.tools = sorted(t.name for t in listed.tools)

            # 시스템 프롬프트는 **서버가 준다.** 이 스크립트가 지시를 보태지 않는다.
            prompt = await session.get_prompt("ontologic_agentic_rag")
            system = "\n\n".join(
                m.content.text for m in prompt.messages if hasattr(m.content, "text")
            )
            transcript.prompt_chars = len(system)

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": (t.description or "")[:1024],
                        "parameters": t.inputSchema,
                    },
                }
                for t in listed.tools
            ]

            # 리소스는 OpenAI 도구가 아니므로, 에이전트가 읽을 수 있도록 도구 하나로 감싼다.
            # 내용은 서버가 만든 것 그대로다.
            tools.append({
                "type": "function",
                "function": {
                    "name": "read_graph_schema",
                    "description": "Read the graph://schema resource — the published "
                                   "ontology map (classes, relationships, which classes "
                                   "are datasource-backed). No columns.",
                    "parameters": {"type": "object", "properties": {}},
                },
            })

            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ]

            for _ in range(MAX_STEPS):
                completion = client.chat.completions.create(
                    model=model, messages=messages, tools=tools, temperature=0,
                )
                choice = completion.choices[0].message
                messages.append(choice.model_dump(exclude_none=True))

                if not choice.tool_calls:
                    transcript.answer = choice.content or ""
                    break

                for call in choice.tool_calls:
                    name = call.function.name
                    args = json.loads(call.function.arguments or "{}")
                    print(f"  → {name}({_short(args, 160)})")

                    if name == "read_graph_schema":
                        content = await session.read_resource("graph://schema")
                        payload = content.contents[0].text
                    else:
                        outcome = await session.call_tool(name, args)
                        payload = outcome.content[0].text if outcome.content else "{}"

                    transcript.record(name, args, payload)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": payload,
                    })
            else:
                transcript.answer = f"[도구 호출 {MAX_STEPS}회 상한에 도달해 중단했습니다]"

    return transcript


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question",
        default="제품 PROD-001 의 라우팅에 포함된 공정 중 "
                "가동률이 가장 낮았던 설비와 그 일자는?",
    )
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out", help="마크다운 기록을 쓸 경로")
    args = parser.parse_args()

    print(f"질문: {args.question}")
    print(f"MCP : {args.mcp_url}\n")

    transcript = asyncio.run(run(args.question, args.mcp_url, args.model))

    print("\n" + "=" * 70)
    print(textwrap.fill(transcript.answer, 100))
    print("=" * 70)
    print(f"도구 호출 {len(transcript.steps)}회: "
          f"{' → '.join(s['name'] for s in transcript.steps)}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(transcript.to_markdown())
        print(f"기록: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
