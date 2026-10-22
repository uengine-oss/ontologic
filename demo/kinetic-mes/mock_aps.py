"""가짜 APS(생산계획) — 일정 재배정 API 와 관찰·고장 주입용 관리 API. MES·CMMS 와 다른 팀이 운영하는 독립 서비스라는 설정.

- `POST /reschedules` (operationId `createReschedule`) `{equipmentCode}` → `{id, equipmentCode, moved_orders:[…], status:'APPLIED'}`
  (점검 들어가는 설비에 걸린 생산 오더를 대체 설비로 옮긴다)
- `POST /reschedules/{id}/revert` (`revertReschedule`) → `{id, status:'REVERTED', …}` (옮긴 오더를 원래 설비로)
- `GET /reschedules` (`listReschedules`).
- `Idempotency-Key` 가 같은 요청은 다시 처리하지 않고 처음 응답을 돌려준다 (`duplicate: true` 로 기록).
- `GET /health`, `GET /calls`, `POST /admin/fail {codes, all, status, operations}`, `POST /admin/reset`, 콘솔 `/`.
- **인증**: 업무 API(`/reschedules…`)는 OAuth2 bearer 토큰이 필요하다 — dev-idp `POST /oauth/token`
  client credentials 로 받은 RS256 JWT (`aud: mock-aps`, iss = dev-idp) 를 dev-idp JWKS 로 검증, 아니면 401.
  `/health`·`/openapi.json`·관리·관찰 API·콘솔은 공개 (운영 콘솔 흉내). env `APS_JWKS_URL`·`APS_ISSUER`·`APS_AUDIENCE`.
"""

from __future__ import annotations

import html
import os
import time

import jwt
import uvicorn
from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="mock-aps", version="1.0.0")

JWKS_URL = os.environ.get("APS_JWKS_URL", "http://localhost:8032/.well-known/jwks.json")
ISSUER = os.environ.get("APS_ISSUER", "http://localhost:8032")
AUDIENCE = os.environ.get("APS_AUDIENCE", "mock-aps")
_JWKS = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=300)
PROTECTED = ("/reschedules",)
AUTH_STATS = {"accepted": 0, "rejected": 0}


def _unauthorized(reason: str) -> JSONResponse:
    AUTH_STATS["rejected"] += 1
    return JSONResponse({"detail": f"unauthorized: {reason}"}, status_code=401,
                        headers={"WWW-Authenticate": 'Bearer realm="mock-aps", error="invalid_token"'})


@app.middleware("http")
async def require_bearer(request: Request, call_next):
    """업무 API 만 보호한다. 토큰은 dev-idp JWKS 로 서명·iss·aud·exp 를 검증."""
    if not request.url.path.startswith(PROTECTED):
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return _unauthorized("missing bearer token")
    token = header[7:].strip()
    try:
        key = _JWKS.get_signing_key_from_jwt(token).key
        jwt.decode(token, key, algorithms=["RS256"], audience=AUDIENCE, issuer=ISSUER)
    except jwt.PyJWKClientConnectionError:
        return JSONResponse({"detail": "token verification unavailable (JWKS)"}, status_code=503)
    except jwt.PyJWTError as exc:
        return _unauthorized(type(exc).__name__)
    AUTH_STATS["accepted"] += 1
    return await call_next(request)

STATE: dict = {"calls": [], "processed": {}, "fail_codes": set(), "fail_all": False, "fail_status": 503,
               "fail_ops": set(), "reschedules": {}, "seq": 0}

# 설비별로 걸려 있는 생산 오더와 대체 설비 (데모 고정값)
ALTERNATE = {"EQ-101": "EQ-201", "EQ-102": "EQ-105", "EQ-103": "EQ-203", "EQ-104": "EQ-103", "EQ-105": "EQ-102",
             "EQ-201": "EQ-101", "EQ-202": "EQ-104", "EQ-203": "EQ-103"}


def _ms(t: float | None) -> str:
    if not t:
        return ""
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t * 1000) % 1000:03d}"


def _should_fail(op: str, code: str) -> bool:
    """operations 만 주면 그 operation 전체, codes 도 주면 그 설비만."""
    if STATE["fail_ops"] and op not in STATE["fail_ops"]:
        return False
    return STATE["fail_all"] or code in STATE["fail_codes"] or (bool(STATE["fail_ops"]) and not STATE["fail_codes"])


class RescheduleIn(BaseModel):
    equipmentCode: str
    reason: str | None = None
    workOrder: str | None = None


class MovedOrder(BaseModel):
    order: str
    from_equipment: str
    to_equipment: str


class Reschedule(BaseModel):
    id: str
    equipmentCode: str
    moved_orders: list[MovedOrder]
    status: str
    workOrder: str | None = None
    applied_at: float
    reverted_at: float | None = None


class FailSpec(BaseModel):
    codes: list[str] = []
    all: bool = False
    status: int = 503
    operations: list[str] = []


def _receive(op: str, code: str, body: dict, key: str | None, run: str | None, internal: str | None,
             resched_id: str | None = None):
    """요청 기록 + 고장 주입 + 멱등 키 확인. 처리해야 하면 (rec, None), 아니면 (rec, 응답)."""
    rec = {"operation": op, "code": code, "reschedule_id": resched_id, "body": body, "idempotency_key": key,
           "run": run, "internal_header": internal is not None, "at": time.time(), "duplicate": False,
           "failed": False, "result": None}
    STATE["calls"].append(rec)
    if _should_fail(op, code):
        rec["failed"] = True
        return rec, JSONResponse({"detail": f"injected failure for {op} {code}"}, status_code=STATE["fail_status"])
    if key and key in STATE["processed"]:
        rec["duplicate"] = True
        return rec, STATE["processed"][key]
    return rec, None


def _public(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "idempotency_key"}


@app.post("/reschedules", operation_id="createReschedule", response_model=Reschedule, summary="생산 일정 재배정")
def create_reschedule(body: RescheduleIn, idempotency_key: str | None = Header(default=None),
                      x_kinetic_run: str | None = Header(default=None),
                      x_kinetic_internal: str | None = Header(default=None)):
    rec, early = _receive("createReschedule", body.equipmentCode, body.model_dump(), idempotency_key, x_kinetic_run,
                          x_kinetic_internal)
    if early is not None:
        return early
    STATE["seq"] += 1
    code = body.equipmentCode
    to = ALTERNATE.get(code, "EQ-ALT")
    moved = [{"order": f"PO-{code[-3:]}{i}", "from_equipment": code, "to_equipment": to} for i in (1, 2)]
    r = {"id": f"RS-{STATE['seq']:04d}", "equipmentCode": code, "moved_orders": moved, "status": "APPLIED",
         "workOrder": body.workOrder, "applied_at": rec["at"], "reverted_at": None,
         "idempotency_key": idempotency_key}
    STATE["reschedules"][r["id"]] = r
    rec.update(reschedule_id=r["id"], result="APPLIED")
    if idempotency_key:
        STATE["processed"][idempotency_key] = _public(r)
    return _public(r)


@app.post("/reschedules/{id}/revert", operation_id="revertReschedule", response_model=Reschedule,
          summary="일정 재배정 원복")
def revert_reschedule(id: str, body: dict | None = Body(default=None),
                      idempotency_key: str | None = Header(default=None),
                      x_kinetic_run: str | None = Header(default=None),
                      x_kinetic_internal: str | None = Header(default=None)):
    r = STATE["reschedules"].get(id)
    if r is None:
        raise HTTPException(404, f"reschedule {id} not found")
    rec, early = _receive("revertReschedule", r["equipmentCode"], body or {}, idempotency_key, x_kinetic_run,
                          x_kinetic_internal, id)
    if early is not None:
        return early
    r.update(status="REVERTED", reverted_at=rec["at"])
    rec["result"] = "REVERTED"
    if idempotency_key:
        STATE["processed"][idempotency_key] = _public(r)
    return _public(r)


@app.get("/reschedules", operation_id="listReschedules", response_model=list[Reschedule], summary="재배정 목록")
def list_reschedules():
    return [_public(r) for r in STATE["reschedules"].values()]


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True, "service": "mock-aps"}


@app.get("/calls", include_in_schema=False)
def calls():
    return STATE["calls"]


@app.get("/admin/auth-stats", include_in_schema=False)
def auth_stats():
    return AUTH_STATS


_OP = {"createReschedule": "일정 재배정", "revertReschedule": "재배정 원복"}


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def console():
    """APS 계획 콘솔 흉내 — 재배정 현황과 받은 요청을 시각(밀리초)과 함께 보여 준다 (시연 화면용)."""
    e = html.escape
    rows = "".join(
        f"<tr class='{'rev' if r['status'] == 'REVERTED' else ''}'><td class='code'>{e(r['id'])}</td>"
        f"<td class='code'>{e(r['equipmentCode'])}</td>"
        f"<td>{'<br>'.join(e(m['order']) + ' → ' + e(m['to_equipment']) for m in r['moved_orders'])}</td>"
        f"<td><span class='b {'rev' if r['status'] == 'REVERTED' else 'ok'}'>{e(r['status'])}</span></td>"
        f"<td class='t'>{_ms(r['applied_at'])}</td><td class='t'>{_ms(r['reverted_at'])}</td>"
        f"<td class='key'>{e(r.get('idempotency_key') or '')}</td></tr>"
        for r in STATE["reschedules"].values())
    calls = "".join(
        f"<tr class='{'fail' if c['failed'] else 'dup' if c['duplicate'] else ''}'><td class='t'>{_ms(c['at'])}</td>"
        f"<td>{_OP.get(c['operation'], c['operation'])}</td><td class='code'>{e(c['code'])}</td>"
        f"<td class='code'>{e(c.get('reschedule_id') or '')}</td>"
        f"<td>{'실패' if c['failed'] else '중복 무시' if c['duplicate'] else e(c['result'] or '')}</td>"
        f"<td class='key'>{e(c.get('idempotency_key') or '')}</td></tr>"
        for c in STATE["calls"])
    applied = sum(r["status"] == "APPLIED" for r in STATE["reschedules"].values())
    reverted = sum(r["status"] == "REVERTED" for r in STATE["reschedules"].values())
    return f"""<!doctype html><meta charset="utf-8"><title>APS 일정 재배정</title>
<style>body{{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;background:#f1f7f5;margin:0;color:#14302a}}
header{{background:#0f4d43;color:#e8fff8;padding:16px 28px;font-size:22px;font-weight:700;display:flex;align-items:baseline;
gap:14px}}header .tag{{background:#2bb39a;color:#05302a;border-radius:4px;padding:2px 8px;font-size:13px}}
header small{{font-weight:400;opacity:.8;font-size:15px}}
main{{padding:20px 28px}}h2{{font-size:17px;margin:18px 0 10px;color:#0f4d43}}
table{{width:100%;border-collapse:collapse;background:#fff;font-size:15px;border:1px solid #cfe3dd}}
th,td{{padding:10px 12px;border-bottom:1px solid #e1eeea;text-align:left;vertical-align:top}}
th{{background:#dff0eb;font-size:13px;color:#2f5a52}}
.code{{font-family:Menlo,monospace;font-weight:700}}.key{{font-family:Menlo,monospace;font-size:11px;color:#8a9a96}}
.t{{font-family:Menlo,monospace;font-size:13px}}.b{{padding:3px 10px;border-radius:4px;font-size:13px;font-weight:700}}
.b.ok{{background:#d4f3ea;color:#0b6b57}}.b.rev{{background:#ece6fb;color:#5a3fb0}}
tr.rev td{{color:#7d8a87}}.fail td{{color:#b3261e}}.dup td{{color:#aaa}}
.empty{{color:#999;text-align:center;padding:30px}}.sum{{font-size:16px;margin:0}}</style>
<header><span class="tag">APS</span>생산계획 · 일정 재배정<small>계획팀 운영 콘솔 — /reschedules</small></header>
<main><p class="sum">재배정 {len(STATE['reschedules'])}건 · 적용(APPLIED) {applied} · 원복(REVERTED) {reverted}</p>
<h2>재배정 현황</h2>
<table><tr><th>재배정</th><th>설비</th><th>옮긴 생산 오더</th><th>상태</th><th>적용 시각</th><th>원복 시각</th><th>멱등 키</th></tr>
{rows or "<tr><td colspan='7' class='empty'>재배정이 없습니다</td></tr>"}</table>
<h2>받은 요청 (시각 순)</h2>
<table><tr><th>시각</th><th>요청</th><th>설비</th><th>재배정</th><th>결과</th><th>멱등 키</th></tr>
{calls or "<tr><td colspan='6' class='empty'>받은 요청이 없습니다</td></tr>"}</table></main>"""


@app.post("/admin/fail", include_in_schema=False)
def fail(spec: FailSpec):
    STATE.update(fail_codes=set(spec.codes), fail_all=spec.all, fail_status=spec.status, fail_ops=set(spec.operations))
    return {"codes": sorted(STATE["fail_codes"]), "all": spec.all, "status": spec.status,
            "operations": sorted(STATE["fail_ops"])}


@app.post("/admin/reset", include_in_schema=False)
def reset():
    STATE.update(calls=[], processed={}, fail_codes=set(), fail_all=False, fail_status=503, fail_ops=set(),
                 reschedules={}, seq=0)
    AUTH_STATS.update(accepted=0, rejected=0)
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8035")))
