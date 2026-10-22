"""가짜 CMMS(설비보전) — 정비 작업지시 API 와 관찰·고장 주입용 관리 API. MES 와 다른 팀이 운영하는 독립 서비스라는 설정.

- `POST /work-orders` (operationId `createWorkOrder`) `{equipmentCode, reason, requestedBy}` → `{id, status:'OPEN', …}`
- `POST /work-orders/{id}/cancel` (`cancelWorkOrder`) `{reason}` → `{id, status:'CANCELLED', …}`
- `GET /work-orders` (`listWorkOrders`). `GET /work-orders/{id}` 은 OpenAPI 에 없는 API — 수동 등록 시연용.
- `Idempotency-Key` 가 같은 요청은 다시 처리하지 않고 처음 응답을 돌려준다 (`duplicate: true` 로 기록).
- `GET /health`, `GET /calls`, `POST /admin/fail {codes, all, status, operations}`, `POST /admin/reset`, 콘솔 `/`.
- **인증**: 업무 API(`/work-orders…`)는 API 키 헤더 `X-API-Key` 가 env `CMMS_API_KEY`(기본 `cmms-demo-key`) 와
  같아야 한다 — 아니면 401. `/health`·`/openapi.json`·관리·관찰 API·콘솔은 공개 (운영 콘솔 흉내).
"""

from __future__ import annotations

import hmac
import html
import os
import time

import uvicorn
from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="mock-cmms", version="1.0.0")

API_KEY = os.environ.get("CMMS_API_KEY", "cmms-demo-key")
PROTECTED = ("/work-orders",)
AUTH_STATS = {"accepted": 0, "rejected": 0}


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """업무 API 만 보호한다 (X-API-Key)."""
    if request.url.path.startswith(PROTECTED):
        key = request.headers.get("x-api-key") or ""
        if not hmac.compare_digest(key.encode(), API_KEY.encode()):
            AUTH_STATS["rejected"] += 1
            return JSONResponse({"detail": "unauthorized: missing or invalid X-API-Key"}, status_code=401,
                                headers={"WWW-Authenticate": 'ApiKey header="X-API-Key"'})
        AUTH_STATS["accepted"] += 1
    return await call_next(request)

STATE: dict = {"calls": [], "processed": {}, "fail_codes": set(), "fail_all": False, "fail_status": 503,
               "fail_ops": set(), "orders": {}, "seq": 0}


def _ms(t: float | None) -> str:
    if not t:
        return ""
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t * 1000) % 1000:03d}"


def _should_fail(op: str, code: str) -> bool:
    """operations 만 주면 그 operation 전체, codes 도 주면 그 설비만."""
    if STATE["fail_ops"] and op not in STATE["fail_ops"]:
        return False
    return STATE["fail_all"] or code in STATE["fail_codes"] or (bool(STATE["fail_ops"]) and not STATE["fail_codes"])


class WorkOrderIn(BaseModel):
    equipmentCode: str
    reason: str | None = None
    requestedBy: str | None = None


class CancelIn(BaseModel):
    reason: str | None = None


class WorkOrder(BaseModel):
    id: str
    equipmentCode: str
    status: str
    reason: str | None = None
    requestedBy: str | None = None
    created_at: float
    cancelled_at: float | None = None
    cancel_reason: str | None = None


class FailSpec(BaseModel):
    codes: list[str] = []
    all: bool = False
    status: int = 503
    operations: list[str] = []


def _receive(op: str, code: str, body: dict, key: str | None, run: str | None, internal: str | None,
             order_id: str | None = None):
    """요청 기록 + 고장 주입 + 멱등 키 확인. 처리해야 하면 (rec, None), 아니면 (rec, 응답)."""
    rec = {"operation": op, "code": code, "order_id": order_id, "body": body, "idempotency_key": key, "run": run,
           "internal_header": internal is not None, "at": time.time(), "duplicate": False, "failed": False,
           "result": None}
    STATE["calls"].append(rec)
    if _should_fail(op, code):
        rec["failed"] = True
        return rec, JSONResponse({"detail": f"injected failure for {op} {code}"}, status_code=STATE["fail_status"])
    if key and key in STATE["processed"]:
        rec["duplicate"] = True
        return rec, STATE["processed"][key]
    return rec, None


@app.post("/work-orders", operation_id="createWorkOrder", response_model=WorkOrder, summary="정비 작업지시 생성")
def create_work_order(body: WorkOrderIn, idempotency_key: str | None = Header(default=None),
                      x_kinetic_run: str | None = Header(default=None),
                      x_kinetic_internal: str | None = Header(default=None)):
    rec, early = _receive("createWorkOrder", body.equipmentCode, body.model_dump(), idempotency_key, x_kinetic_run,
                          x_kinetic_internal)
    if early is not None:
        return early
    STATE["seq"] += 1
    wo = {"id": f"WO-{STATE['seq']:04d}", "equipmentCode": body.equipmentCode, "status": "OPEN",
          "reason": body.reason, "requestedBy": body.requestedBy, "created_at": rec["at"], "cancelled_at": None,
          "cancel_reason": None, "idempotency_key": idempotency_key}
    STATE["orders"][wo["id"]] = wo
    rec.update(order_id=wo["id"], result="OPEN")
    result = {k: v for k, v in wo.items() if k != "idempotency_key"}
    if idempotency_key:
        STATE["processed"][idempotency_key] = result
    return result


@app.post("/work-orders/{id}/cancel", operation_id="cancelWorkOrder", response_model=WorkOrder,
          summary="정비 작업지시 취소")
def cancel_work_order(id: str, body: CancelIn | None = Body(default=None),
                      idempotency_key: str | None = Header(default=None),
                      x_kinetic_run: str | None = Header(default=None),
                      x_kinetic_internal: str | None = Header(default=None)):
    wo = STATE["orders"].get(id)
    if wo is None:
        raise HTTPException(404, f"work order {id} not found")
    body = body or CancelIn()
    rec, early = _receive("cancelWorkOrder", wo["equipmentCode"], body.model_dump(), idempotency_key, x_kinetic_run,
                          x_kinetic_internal, id)
    if early is not None:
        return early
    wo.update(status="CANCELLED", cancelled_at=rec["at"], cancel_reason=body.reason)
    rec["result"] = "CANCELLED"
    result = {k: v for k, v in wo.items() if k != "idempotency_key"}
    if idempotency_key:
        STATE["processed"][idempotency_key] = result
    return result


@app.get("/work-orders", operation_id="listWorkOrders", response_model=list[WorkOrder], summary="작업지시 목록")
def list_work_orders():
    return [{k: v for k, v in wo.items() if k != "idempotency_key"} for wo in STATE["orders"].values()]


@app.get("/work-orders/{id}", include_in_schema=False)
def get_work_order(id: str):
    """OpenAPI 에 싣지 않은 API — kinetic-action 레지스트리의 수동 등록 시연용."""
    wo = STATE["orders"].get(id)
    if wo is None:
        raise HTTPException(404, f"work order {id} not found")
    return {k: v for k, v in wo.items() if k != "idempotency_key"}


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True, "service": "mock-cmms"}


@app.get("/calls", include_in_schema=False)
def calls():
    return STATE["calls"]


@app.get("/admin/auth-stats", include_in_schema=False)
def auth_stats():
    return AUTH_STATS


_BADGE = {"OPEN": "open", "CANCELLED": "cancel"}
_OP = {"createWorkOrder": "작업지시 생성", "cancelWorkOrder": "작업지시 취소"}


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def console():
    """CMMS 운영 콘솔 흉내 — 작업지시 현황과 받은 요청을 시각(밀리초)과 함께 보여 준다 (시연 화면용)."""
    e = html.escape
    orders = "".join(
        f"<tr class='{_BADGE.get(w['status'], '')}'><td class='code'>{e(w['id'])}</td>"
        f"<td class='code'>{e(w['equipmentCode'])}</td><td><span class='b {_BADGE.get(w['status'], '')}'>"
        f"{e(w['status'])}</span></td><td>{e(w['reason'] or '')}</td><td>{e(w['requestedBy'] or '')}</td>"
        f"<td class='t'>{_ms(w['created_at'])}</td><td class='t'>{_ms(w['cancelled_at'])}</td>"
        f"<td>{e(w['cancel_reason'] or '')}</td><td class='key'>{e(w.get('idempotency_key') or '')}</td></tr>"
        for w in STATE["orders"].values())
    calls = "".join(
        f"<tr class='{'fail' if c['failed'] else 'dup' if c['duplicate'] else ''}'><td class='t'>{_ms(c['at'])}</td>"
        f"<td>{_OP.get(c['operation'], c['operation'])}</td><td class='code'>{e(c['code'])}</td>"
        f"<td class='code'>{e(c.get('order_id') or '')}</td>"
        f"<td>{'실패' if c['failed'] else '중복 무시' if c['duplicate'] else e(c['result'] or '')}</td>"
        f"<td class='key'>{e(c.get('idempotency_key') or '')}</td></tr>"
        for c in STATE["calls"])
    open_n = sum(w["status"] == "OPEN" for w in STATE["orders"].values())
    cancel_n = sum(w["status"] == "CANCELLED" for w in STATE["orders"].values())
    return f"""<!doctype html><meta charset="utf-8"><title>CMMS 정비 작업지시</title>
<style>body{{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;background:#fbf7f2;margin:0;color:#2b2118}}
header{{background:linear-gradient(90deg,#8a4b08,#b8660f);color:#fff;padding:18px 28px;font-size:22px;font-weight:700;
border-bottom:4px solid #f0b050}}header small{{font-weight:400;opacity:.85;margin-left:12px;font-size:15px}}
main{{padding:20px 28px}}h2{{font-size:17px;margin:18px 0 10px;color:#6b3a06}}
table{{width:100%;border-collapse:collapse;background:#fff;font-size:15px;box-shadow:0 1px 3px #0002}}
th,td{{padding:10px 12px;border-bottom:1px solid #eee3d6;text-align:left}}th{{background:#f6ece0;font-size:13px;color:#7a5a3a}}
.code{{font-family:Menlo,monospace;font-weight:700}}.key{{font-family:Menlo,monospace;font-size:11px;color:#998}}
.t{{font-family:Menlo,monospace;font-size:13px}}.b{{padding:3px 10px;border-radius:12px;font-size:13px;font-weight:700}}
.b.open{{background:#e3f4e1;color:#1d6b2a}}.b.cancel{{background:#fde4e1;color:#a32116}}
tr.cancel td{{color:#8a8078}}.fail td{{color:#b3261e}}.dup td{{color:#aaa}}
.empty{{color:#999;text-align:center;padding:30px}}.sum{{font-size:16px;margin:0}}</style>
<header>CMMS · 설비보전 · 정비 작업지시<small>보전팀 운영 콘솔 — /work-orders</small></header>
<main><p class="sum">작업지시 {len(STATE['orders'])}건 · 진행(OPEN) {open_n} · 취소(CANCELLED) {cancel_n}</p>
<h2>작업지시 현황</h2>
<table><tr><th>작업지시</th><th>설비</th><th>상태</th><th>사유</th><th>요청자</th><th>생성 시각</th><th>취소 시각</th>
<th>취소 사유</th><th>멱등 키</th></tr>{orders or "<tr><td colspan='9' class='empty'>작업지시가 없습니다</td></tr>"}</table>
<h2>받은 요청 (시각 순)</h2>
<table><tr><th>시각</th><th>요청</th><th>설비</th><th>작업지시</th><th>결과</th><th>멱등 키</th></tr>
{calls or "<tr><td colspan='6' class='empty'>받은 요청이 없습니다</td></tr>"}</table></main>"""


@app.post("/admin/fail", include_in_schema=False)
def fail(spec: FailSpec):
    STATE.update(fail_codes=set(spec.codes), fail_all=spec.all, fail_status=spec.status, fail_ops=set(spec.operations))
    return {"codes": sorted(STATE["fail_codes"]), "all": spec.all, "status": spec.status,
            "operations": sorted(STATE["fail_ops"])}


@app.post("/admin/reset", include_in_schema=False)
def reset():
    STATE.update(calls=[], processed={}, fail_codes=set(), fail_all=False, fail_status=503, fail_ops=set(),
                 orders={}, seq=0)
    AUTH_STATS.update(accepted=0, rejected=0)
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8034")))
