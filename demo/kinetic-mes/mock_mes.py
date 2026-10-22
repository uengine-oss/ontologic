"""가짜 MES — 설비 상태 변경 API 하나와 관찰·고장 주입용 관리 API.

- `POST /equipment/{code}/status` (operationId `setEquipmentStatus`)
- `Idempotency-Key` 가 같은 요청은 다시 처리하지 않고 처음 응답을 돌려준다 (`duplicate: true` 로 기록).
- `GET /calls` 받은 요청 기록, `GET /health`, `POST /admin/fail` 고장 주입
  (`{codes, all, status, operations}` — operations 가 있으면 그 operation 만), `POST /admin/reset` 초기화.
"""

from __future__ import annotations

import html
import os
import time

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="mock-mes", version="1.0.0")

STATE: dict = {"calls": [], "processed": {}, "fail_codes": set(), "fail_all": False, "fail_status": 503,
               "fail_ops": set(), "equipment": {}}


def _ms(t: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t * 1000) % 1000:03d}"


def _should_fail(op: str, code: str) -> bool:
    """operations 만 주면 그 operation 전체, codes 도 주면 그 설비만."""
    if STATE["fail_ops"] and op not in STATE["fail_ops"]:
        return False
    return STATE["fail_all"] or code in STATE["fail_codes"] or (bool(STATE["fail_ops"]) and not STATE["fail_codes"])


class StatusChange(BaseModel):
    status: str
    reason: str | None = None
    requestedBy: str | None = None


class StatusResult(BaseModel):
    code: str
    status: str
    reason: str | None = None
    requestedBy: str | None = None
    at: float


class FailSpec(BaseModel):
    codes: list[str] = []
    all: bool = False
    status: int = 503
    operations: list[str] = []


@app.post("/equipment/{code}/status", operation_id="setEquipmentStatus", response_model=StatusResult,
          summary="설비 상태 변경")
def set_status(code: str, body: StatusChange, idempotency_key: str | None = Header(default=None),
               x_kinetic_run: str | None = Header(default=None), x_kinetic_internal: str | None = Header(default=None)):
    rec = {"operation": "setEquipmentStatus", "code": code, "body": body.model_dump(), "idempotency_key": idempotency_key, "run": x_kinetic_run,
           "internal_header": x_kinetic_internal is not None, "at": time.time(), "duplicate": False, "failed": False}
    STATE["calls"].append(rec)
    if _should_fail("setEquipmentStatus", code):
        rec["failed"] = True
        return JSONResponse({"detail": f"injected failure for {code}"}, status_code=STATE["fail_status"])
    if idempotency_key and idempotency_key in STATE["processed"]:
        rec["duplicate"] = True
        return STATE["processed"][idempotency_key]
    result = {"code": code, "status": body.status, "reason": body.reason, "requestedBy": body.requestedBy,
              "at": rec["at"]}
    STATE["equipment"][code] = body.status
    if idempotency_key:
        STATE["processed"][idempotency_key] = result
    return result


@app.get("/equipment/{code}", operation_id="getEquipment", summary="설비 상태 조회")
def get_equipment(code: str):
    if code not in STATE["equipment"]:
        raise HTTPException(404, "unknown")
    return {"code": code, "status": STATE["equipment"][code]}


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True, "service": "mock-mes"}


@app.get("/calls", include_in_schema=False)
def calls():
    return STATE["calls"]


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def console():
    """MES 운영 콘솔 흉내 — 받은 상태 변경 요청을 표로 보여 준다 (시연 화면용)."""
    rows = "".join(
        f"<tr class='{'fail' if c['failed'] else 'dup' if c['duplicate'] else ''}'>"
        f"<td class='t'>{_ms(c['at'])}</td><td class='code'>{html.escape(c['code'])}</td>"
        f"<td><b>{html.escape(c['body'].get('status') or '')}</b></td><td>{html.escape(c['body'].get('reason') or '')}</td>"
        f"<td>{html.escape(c['body'].get('requestedBy') or '')}</td>"
        f"<td class='key'>{html.escape(c.get('idempotency_key') or '')}</td>"
        f"<td>{'실패' if c['failed'] else '중복 무시' if c['duplicate'] else '처리'}</td></tr>"
        for c in STATE["calls"])
    empty = "<tr><td colspan='7' class='empty'>받은 요청이 없습니다</td></tr>"
    return f"""<!doctype html><meta charset="utf-8"><title>MES 설비 상태 변경 수신</title>
<style>body{{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;background:#f4f6f9;margin:0;color:#1d2330}}
header{{background:#203a5c;color:#fff;padding:18px 28px;font-size:22px;font-weight:700}}
header small{{font-weight:400;opacity:.8;margin-left:12px;font-size:15px}}
main{{padding:24px 28px}}table{{width:100%;border-collapse:collapse;background:#fff;font-size:16px;box-shadow:0 1px 3px #0002}}
th,td{{padding:12px 14px;border-bottom:1px solid #e3e7ee;text-align:left}}th{{background:#eef2f7;font-size:14px;color:#556}}
.code{{font-family:Menlo,monospace;font-weight:700}}.key{{font-family:Menlo,monospace;font-size:12px;color:#778}}
.fail td{{color:#b3261e}}.dup td{{color:#999}}.empty{{color:#999;text-align:center;padding:40px}}
.sum{{margin:0 0 14px;font-size:17px}}.t{{font-family:Menlo,monospace;font-size:14px}}</style>
<header>MES · 설비 상태 변경 수신 기록<small>외부 요청 API /equipment/{{code}}/status</small></header>
<main><p class="sum">받은 요청 {len(STATE['calls'])}건</p>
<table><tr><th>시각</th><th>설비</th><th>요청 상태</th><th>사유</th><th>요청자</th><th>멱등 키</th><th>처리</th></tr>
{rows or empty}</table></main>"""


@app.post("/admin/fail", include_in_schema=False)
def fail(spec: FailSpec):
    STATE.update(fail_codes=set(spec.codes), fail_all=spec.all, fail_status=spec.status, fail_ops=set(spec.operations))
    return {"codes": sorted(STATE["fail_codes"]), "all": spec.all, "status": spec.status,
            "operations": sorted(STATE["fail_ops"])}


@app.post("/admin/reset", include_in_schema=False)
def reset():
    STATE.update(calls=[], processed={}, fail_codes=set(), fail_all=False, fail_status=503, fail_ops=set(),
                 equipment={})
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8031")))
