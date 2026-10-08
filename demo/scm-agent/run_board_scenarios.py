#!/usr/bin/env python3
"""보드 시나리오 러너 — 답을 표와 문장이 아니라 **위젯**으로 그린다.

`run_scenarios.py` 는 질의응답 모드로 답을 받아 채점한다. 그것만으로는 결과가 텍스트다.
이 러너는 같은 골든 퀘스천을 **대시보드 문맥**에서 물어, 답과 함께 어떤 위젯이 그려졌는지를
기록한다 (spec 011).

  1. `POST /api/board/compose`            발행 모델 하나에서 대시보드를 구성 (SSE)
  2. `POST /api/board/dashboards/{id}/ask` 그 대시보드 문맥에서 질문
  3. 위젯 종류·근거·행 수를 기록

선행 조건: 온톨로지가 그래프에 발행돼 있고 MCP(8100)와 스튜디오(8010)가 떠 있을 것.

  python3 demo/scm-agent/run_board_scenarios.py --schema "공급망 지식지도"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "runs-board"
STUDIO = "http://127.0.0.1:8010"

#: 문서 5절의 골든 퀘스천. 보드에서 묻는다 — 답이 어떤 위젯으로 그려지는지가 관심사다.
QUESTIONS = [
    ("Q1-조달", "발주 PO-2026-0117 의 납기 리스크는 어떤 상태이며 계약상 페널티 발동 요건을 충족하는가?"),
    ("Q2-수출입", "통관이 보류·반려된 신고 건의 사유는 무엇이며 신고 품목분류 코드가 품목 마스터와 일치하는가?"),
    ("Q3-재고", "안전재고를 이탈한 품목은 무엇이고 재고커버일수는 며칠이며 대체 공급사는 누구인가?"),
    ("Q4-계약", "만기가 60일 이내인 계약별 미결 발주 노출액을 집계해서 갱신 우선순위를 보여줘."),
    ("Q5-구매", "공급사별 납기준수율과 평가점수를 비교해서 보여줘."),
    ("Q6-고객지원", "고객 클레임 TK-2026-0031 의 원인을 주문에서 통관까지 역추적하면 무엇이 나오는가?"),
]


def post(path: str, body: dict, timeout: int = 900):
    req = urllib.request.Request(
        STUDIO + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def get(path: str, timeout: int = 120):
    with urllib.request.urlopen(STUDIO + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sse_lines(path: str, body: dict, timeout: int = 1800):
    """SSE 응답을 (event, data) 로 흘린다. compose 가 진행을 스트리밍한다."""
    req = urllib.request.Request(
        STUDIO + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    event = ""
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: "):
                try:
                    yield event or "message", json.loads(line[6:])
                except ValueError:
                    yield event or "message", {"raw": line[6:]}


def compose(schema_name: str) -> dict:
    print(f"[1] 대시보드 구성 — 모델 '{schema_name}'", flush=True)
    spec = None
    for event, data in sse_lines("/api/board/compose", {"schema_name": schema_name, "use_agent": True}):
        kind = data.get("kind") or event
        if kind in ("progress", "step", "status", "log"):
            msg = data.get("message") or data.get("text") or ""
            if msg:
                print(f"    · {msg[:110]}", flush=True)
        elif kind == "error":
            raise RuntimeError(data.get("message", "compose 실패"))
        elif kind in ("done", "result", "spec"):
            spec = data.get("spec") or data.get("dashboard") or data
    if not spec:
        raise RuntimeError("compose 가 스펙을 돌려주지 않았습니다")
    return spec


def main(schema_name: str) -> int:
    OUT.mkdir(exist_ok=True)

    spec = compose(schema_name)
    widgets = spec.get("widgets") or []
    dash_id = spec.get("id") or spec.get("dashboard_id") or ""
    print(f"    위젯 {len(widgets)}개 · 대시보드 {dash_id or '(미저장)'}")
    kinds: dict[str, int] = {}
    for w in widgets:
        kinds[w.get("widget_kind", "?")] = kinds.get(w.get("widget_kind", "?"), 0) + 1
    print("    종류:", ", ".join(f"{k}×{v}" for k, v in sorted(kinds.items())))
    (OUT / "dashboard.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    # 대시보드를 저장해야 ask 가 그 문맥을 읽는다.
    if not dash_id:
        dash_id = spec.get("name") or schema_name
    try:
        post(f"/api/board/dashboards/{urllib.parse.quote(dash_id)}", spec, timeout=120)
    except Exception:
        pass

    print(f"\n[2] 골든 퀘스천 {len(QUESTIONS)}건")
    records = []
    for qid, question in QUESTIONS:
        print(f"\n=== {qid} ===\n    {question[:80]}", flush=True)
        t0 = time.time()
        try:
            raw = post(f"/api/board/dashboards/{urllib.parse.quote(dash_id)}/ask",
                       {"question": question}, timeout=900)
            data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            data = {"error": f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}"}
        except Exception as exc:                                  # noqa: BLE001
            data = {"error": str(exc)[:300]}
        elapsed = round(time.time() - t0, 1)

        widget = data.get("widget") or {}
        rec = {
            "id": qid, "question": question, "elapsed_s": elapsed,
            "widget_kind": widget.get("widget_kind") or data.get("widget_kind") or "",
            "class_name": widget.get("class_name") or data.get("class_name") or "",
            "rule": widget.get("rule") or data.get("rule") or "",
            "row_count": data.get("row_count") or len(data.get("rows") or []),
            "answer": data.get("answer") or data.get("text") or "",
            "error": data.get("error", ""),
            "raw": data,
        }
        records.append(rec)
        if rec["error"]:
            print(f"    실패: {rec['error'][:160]}")
        else:
            print(f"    위젯 {rec['widget_kind'] or '(없음)'} · 클래스 {rec['class_name'] or '-'} "
                  f"· {rec['row_count']}행 · {elapsed}s")
        (OUT / f"{qid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2, default=str),
                                         encoding="utf-8")

    drawn = sum(1 for r in records if r["widget_kind"])
    (OUT / "summary.json").write_text(json.dumps(
        [{k: r[k] for k in ("id", "widget_kind", "class_name", "rule", "row_count", "elapsed_s", "error")}
         for r in records], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n위젯이 그려진 질문 {drawn}/{len(records)}건 → {OUT}")
    return 0


if __name__ == "__main__":
    import urllib.parse
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", default="공급망 지식지도")
    a = ap.parse_args()
    sys.exit(main(a.schema))
