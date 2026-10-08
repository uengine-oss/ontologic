#!/usr/bin/env python3
"""SCM-Agent 데모 시나리오 러너 — ontology-studio 를 통해 6개 업무 도메인을 실행·기록·채점한다.

실행 경로는 **온톨로지 스튜디오**다 (`/api/stream?mode=answer`). 스튜디오가
`AGENT_BACKEND=cliagents` 로 떠 있으면 외부 CLI 에이전트(claude-code)가 스튜디오 도구를
MCP 로 호출한다 — **OpenAI API 키를 쓰지 않는다** (constitution VI · spec 004).

이 스크립트가 하는 일은 셋이다.

  1. SSE 이벤트(tool_start / tool_result / token / done)를 그대로 받아 적는다
  2. 심어 둔 골든 팩트(gen_supplychain_data.py)와 대조해 정답 여부를 채점한다
  3. 멀티에이전트 핸드오프: 앞 에이전트의 답을 뒤 에이전트의 입력으로 넘긴다 (A2A 순차)

선행 조건
---------
    # 1) 인프라
    docker compose (robo-postgres / robo-neo4j / robo-mindsdb)
    data-fabric :8004 · text2sql :8020
    # 2) 스튜디오 (CLI 에이전트 백엔드)
    cd ontology-studio && SANDBOX_BACKEND=local AGENT_BACKEND=cliagents \
      EXTERNAL_AGENT_ID=claude-code uv run uvicorn backend.src.host.main:app --port 8010
    # 3) 데이터·온톨로지
    psql < sql/01_supplychain_schema.sql; psql < sql/02_supplychain_data.sql
    uv run python demo/scm-agent/seed_scm_demo.py

출력: demo/scm-agent/runs/<scenario_id>.json / .md, summary.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

#: 실행마다 달라지는 꼬리표. 세션 재사용으로 인한 "기억으로 답하기"를 막는다.
RUN_STAMP = uuid.uuid4().hex[:8]

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
STUDIO = "http://127.0.0.1:8010"
TIMEOUT = 900

# ── 시나리오 정의 ─────────────────────────────────────────────────────────
# expect: 답변에 반드시 들어 있어야 하는 사실(정규식, 모두 일치해야 PASS)
SCENARIOS = [
    dict(
        id="S1-procurement", domain="조달", agent="조달 에이전트",
        title="납기 리스크 감시 → 계약 페널티 판정",
        question=(
            "발주 PO-2026-0117 의 납기 리스크를 점검해줘. 현재 선적 상태와 지연 일수, 지연 사유를 확인하고, "
            "이 발주의 공급사와 계약 조건(페널티·만기)을 함께 보고해줘."
        ),
        expect=[r"CUSTOMS_HOLD|세관|통관", r"9\s*일", r"원산지", r"Shenzhen Goldline|SUP-CN-003", r"CT-2025-011", r"2(\.0+)?\s*%"],
    ),
    dict(
        id="S2-customs", domain="수출입", agent="통관 에이전트",
        title="통관 보류 사유 규명 → HS 코드 검증 → 정정신고 문안",
        question=(
            "현재 통관 보류(HOLD) 또는 반려(REJECTED) 상태인 수출입 신고 건을 모두 찾아 사유를 정리하고, "
            "각 건에서 신고 HS 코드가 품목 마스터의 HS 코드와 일치하는지 검증해줘. 불일치 건은 정정신고 문안을 제안해줘."
        ),
        expect=[r"DCL-2026-00117", r"8536\.?69", r"8536\.?90", r"원산지증명|C/O", r"DCL-2026-0011[456]"],
    ),
    dict(
        id="S3-inventory", domain="재고관리", agent="재고 에이전트",
        title="안전재고 이탈 감시 → 커버일수 산출 → 대체 공급사 식별",
        question=(
            "최신 스냅샷 기준으로 안전재고를 이탈한 원자재 품목을 찾고, 각 품목의 재고 커버일수와 운송중 수량을 알려줘. "
            "가장 위험한 품목의 주 공급사와 대체 공급사도 함께 알려줘."
        ),
        expect=[r"ITM-PCB-004", r"커버\s*일수|cover", r"6,?000", r"Saigon Circuit|SUP-VN-002"],
    ),
    dict(
        id="S4-contract", domain="계약", agent="계약 에이전트",
        title="만기 임박 계약 감시 → 미결 발주 노출액 집계 → 갱신 우선순위",
        question=(
            "앞으로 60일 이내에 만기되는 공급 계약을 찾아줘. 자동갱신 여부, 페널티 조항, 리스크 조항을 정리하고, "
            "각 계약에 걸려 있는 미결(OPEN/PARTIAL/DELAYED) 발주 건수와 금액을 집계해서 갱신 우선순위를 제안해줘."
        ),
        expect=[r"CT-2025-011", r"자동\s*갱신[^\n]{0,20}(없|아니|미적용|X|false|불가)|auto_renew[^\n]{0,12}(false|False|0|아니)", r"PO-2026-0117|미결"],
    ),
    dict(
        id="S5-purchasing", domain="구매", agent="구매 에이전트",
        title="대체 소싱 비교표 → 발주서(PO) 초안 자동 생성",
        question=(
            "품목 ITM-PCB-004 를 긴급 대체 소싱하려고 해. 이 품목을 공급할 수 있는 주 공급사와 대체 공급사를 평점·리드타임·"
            "납기준수율로 비교표를 만들고, 대체 공급사 앞 발주서(PO) 초안을 작성해줘. "
            "수량은 안전재고 회복에 필요한 만큼, MOQ 를 지켜서."
        ),
        expect=[r"Saigon Circuit|SUP-VN-002", r"Shenzhen Goldline|SUP-CN-003", r"4\.3", r"12\s*일", r"MOQ|2,?000"],
    ),
    dict(
        id="S6-customer-support", domain="고객지원", agent="고객지원 에이전트",
        title="A2A 핸드오프 — 클레임 원인 역추적 → 고객 회신문 생성",
        handoff_from="S1-procurement",
        question=(
            "고객 클레임 TK-2026-0031 (납기 문의)에 답해야 해. 해당 고객과 주문(SO)의 내용, 납기 리스크 원인을 "
            "연결된 발주/선적까지 역추적해서 확인하고, 고객에게 보낼 회신 초안을 작성해줘. "
            "회신에는 원인, 현재 조치, 예상 납기 영향, 대안을 담아줘."
        ),
        expect=[r"아틀라스|CUS-004", r"SO-2026-0412", r"PO-2026-0117", r"SPC-200|ITM-FG-001", r"세관|통관|원산지"],
    ),
]


def _short(value, limit=600):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + f"… (총 {len(text)}자)"


def stream(prompt: str, session_id: str) -> tuple[list[dict], str, float]:
    """스튜디오 SSE 를 소비해 (이벤트, 최종답변, 경과초) 를 돌려준다."""
    url = f"{STUDIO}/api/stream?" + urllib.parse.urlencode(
        {"prompt": prompt, "session_id": session_id, "mode": "answer"})
    events: list[dict] = []
    answer = ""
    t0 = time.time()
    event_name = ""
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("event: "):
                event_name = line[7:].strip()
                continue
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            try:
                data = json.loads(payload)
            except ValueError:
                data = {"raw": payload}
            events.append({"event": event_name or "message", "data": data, "t": round(time.time() - t0, 2)})
            if event_name == "tool_start":
                print(f"  → {data.get('name')}({_short(data.get('args'), 120)})", flush=True)
            if event_name == "done":
                answer = data.get("text", "") or answer
    # done 이 비어 있으면 마지막 token 을 답으로 본다
    if not answer:
        toks = [e["data"].get("text", "") for e in events if e["event"] == "token"]
        answer = toks[-1] if toks else ""
    return events, answer, round(time.time() - t0, 1)


def run_one(sc: dict, prior: dict[str, dict], suffix: str = "") -> dict:
    user = sc["question"]
    if sc.get("handoff_from") and sc["handoff_from"] in prior:
        p = prior[sc["handoff_from"]]
        user = (f"[A2A 핸드오프] {p['agent']}가 먼저 조사한 결과를 전달한다:\n\n{p['answer'][:4000]}\n\n"
                f"---\n위 내용을 근거로 활용하되, 필요한 사실은 도구로 직접 확인하라.\n\n{sc['question']}")
    # **세션을 매번 새로 판다.** 같은 session_id 를 재사용하면 CLI 에이전트가 앞선 대화를
    # 기억해 도구를 부르지 않고 "앞서 조회한 결과로 …" 라고 답한다. 답은 맞지만 그것은
    # 이번 실행의 결과가 아니므로 기록이 거짓이 된다 — 실제로 그렇게 났다.
    session_id = f"scm-demo-{sc['id']}{suffix}-{RUN_STAMP}"
    events, answer, elapsed = stream(user, session_id)

    tool_starts = [e for e in events if e["event"] == "tool_start"]
    tool_results = [e for e in events if e["event"] == "tool_result"]
    errors = 0
    for e in tool_results:
        content = json.dumps(e["data"].get("content", ""), ensure_ascii=False)
        if '\\"status\\": \\"error\\"' in content or '"error"' in content.lower() and '"status": "ok"' not in content:
            errors += 1
    rec = dict(
        id=sc["id"], domain=sc["domain"], agent=sc["agent"], title=sc["title"], question=sc["question"],
        user_message=user, session_id=session_id, backend="ontology-studio /api/stream (AGENT_BACKEND=cliagents)",
        events=events, answer=answer, elapsed_s=elapsed,
        tool_calls=len(tool_starts), tool_errors=errors,
        tools_used=[e["data"].get("name") for e in tool_starts],
    )
    if sc.get("handoff_from"):
        rec["handoff_from"] = sc["handoff_from"]
    rec["checks"] = [dict(pattern=p, hit=bool(re.search(p, answer, re.I))) for p in sc["expect"]]
    # 도구를 한 번도 부르지 않았다면 조회로 얻은 답이 아니다. 사실이 맞더라도 이번 실행의
    # 근거가 없으므로 통과시키지 않는다 (constitution VII — 실행해서 검증한다).
    rec["queried"] = rec["tool_calls"] > 0
    rec["passed"] = rec["queried"] and all(c["hit"] for c in rec["checks"])
    return rec


def to_markdown(rec: dict) -> str:
    lines = [f"### [{rec['domain']}] {rec['agent']} — {rec['id']}", "", f"**{rec['title']}**", "",
             f"> {rec['question']}", ""]
    if rec.get("handoff_from"):
        lines += [f"_(A2A 핸드오프: `{rec['handoff_from']}` 의 결과를 입력으로 받음)_", ""]
    lines += [f"실행 경로 `{rec['backend']}` · 도구 호출 **{rec['tool_calls']}회** (오류 {rec['tool_errors']}) · "
              f"{rec['elapsed_s']}s", ""]
    step = 0
    for e in rec["events"]:
        if e["event"] == "tool_start":
            step += 1
            lines += [f"#### {step}. `{e['data'].get('name')}`", "", "```json",
                      json.dumps(e["data"].get("args", {}), ensure_ascii=False, indent=2), "```", ""]
        elif e["event"] == "tool_result":
            lines += ["```json", _short(e["data"].get("content", ""), 900), "```", ""]
    lines += ["#### 최종 답변", "", rec["answer"], "", "#### 채점", ""]
    if not rec.get("queried", True):
        lines.append("- FAIL 도구 호출 0회 — 조회 없이 답했다 (이번 실행의 근거 없음)")
    for c in rec["checks"]:
        lines.append(f"- {'PASS' if c['hit'] else 'FAIL'} `{c['pattern']}`")
    lines += ["", f"**결과: {'PASS' if rec['passed'] else 'FAIL'}**", ""]
    return "\n".join(lines)


def main(only: list[str] | None, repeat: int) -> int:
    RUNS.mkdir(exist_ok=True)
    prior: dict[str, dict] = {}
    summary = []
    for sc in SCENARIOS:
        if only and sc["id"] not in only:
            continue
        for r in range(repeat):
            suffix = "" if repeat == 1 else f"-r{r+1}"
            tag = sc["id"] + suffix
            print(f"\n=== {tag} [{sc['domain']}] {sc['title']} ===", flush=True)
            try:
                rec = run_one(sc, prior, suffix)
            except Exception as exc:
                rec = dict(id=sc["id"], domain=sc["domain"], agent=sc["agent"], title=sc["title"],
                           question=sc["question"], backend="ontology-studio", events=[],
                           answer=f"[실행 오류] {exc}", elapsed_s=0, tool_calls=0, tool_errors=0,
                           tools_used=[], checks=[], passed=False)
            (RUNS / f"{tag}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            (RUNS / f"{tag}.md").write_text(to_markdown(rec), encoding="utf-8")
            if r == 0:
                prior[sc["id"]] = rec
            summary.append({k: rec.get(k) for k in ("id", "domain", "agent", "title", "passed", "tool_calls",
                                                     "tool_errors", "elapsed_s", "tools_used", "queried")} | {"run": r + 1})
            print(f"  {'PASS' if rec['passed'] else 'FAIL'} · 도구 {rec['tool_calls']}회 · {rec['elapsed_s']}s")
    prev = []
    if (RUNS / "summary.json").exists() and only:
        try:
            prev = [s for s in json.loads((RUNS / "summary.json").read_text()) if s["id"] not in only]
        except Exception:
            prev = []
    allsum = prev + summary
    (RUNS / "summary.json").write_text(json.dumps(allsum, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(allsum)
    p = sum(1 for s in allsum if s["passed"])
    print(f"\n총 {n}건 중 PASS {p}건 ({(p / n * 100) if n else 0:.0f}%)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--repeat", type=int, default=1)
    a = ap.parse_args()
    sys.exit(main(a.only, a.repeat))
