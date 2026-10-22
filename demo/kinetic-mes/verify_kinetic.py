"""kinetic-action 종단 검증 — 공식 `mcp` 클라이언트(Streamable HTTP) + REST(승인·재시도) + mock 서비스 3개 관찰.

`setMaintenanceMode` 는 3단계 사가(MES → CMMS → APS). 10~14 는 다단계·취소(역순 보상)·자동 보상·레지스트리.
15~19 는 시스템 등록 모델(계약 §8): CMMS API 키·APS OAuth2 client credentials 를 게이트웨이가 주입, Swagger 2 YAML 업로드,
어댑터가 필요한 SOAP 시스템의 not_executable, 연결 테스트(`POST /systems/test`).

시작할 때 seed 를 다시 돌려 항상 같은 상태에서 시작한다. 시나리오마다 PASS/FAIL, 하나라도 실패하면 exit 1.

  KINETIC_MCP_URL   기본 http://localhost:8030/mcp  (게이트웨이: http://localhost:9000/mcp/kinetic/)
  KINETIC_API_URL   기본 http://localhost:8030       (게이트웨이: http://localhost:9000)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

import seed

MCP_URL = os.environ.get("KINETIC_MCP_URL", "http://localhost:8030/mcp")
API = seed.KINETIC_API
MES = seed.MOCK_MES
CMMS = seed.MOCK_CMMS
APS = seed.MOCK_APS
HOT = [{"prop": "temp", "op": ">", "value": 80}]
REASON = {"reason": "온도 80℃ 초과 — 점검"}

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


class Agent:
    """한 사용자(토큰)로 MCP 도구를 부르는 클라이언트."""

    def __init__(self, token: str):
        self.token = token

    async def call(self, tool: str, args: dict) -> tuple[bool, object]:
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {self.token}"}, timeout=60) as http:
            async with streamable_http_client(MCP_URL, http_client=http) as (read, write, *_):
                async with ClientSession(read, write) as s:
                    await s.initialize()
                    res = await s.call_tool(tool, args)
                    return bool(res.isError), json.loads(res.content[0].text)

    async def tools(self) -> list[str]:
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {self.token}"}, timeout=60) as http:
            async with streamable_http_client(MCP_URL, http_client=http) as (read, write, *_):
                async with ClientSession(read, write) as s:
                    await s.initialize()
                    return [t.name for t in (await s.list_tools()).tools]


def rest(method: str, path: str, token: str | None = None, **kw) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.request(method, f"{API}{path}", headers=headers, timeout=30, **kw)


def mes_calls() -> list[dict]:
    return httpx.get(f"{MES}/calls", timeout=10).json()


def svc_calls(url: str) -> list[dict]:
    return httpx.get(f"{url}/calls", timeout=10).json()


def all_calls() -> int:
    return sum(len(svc_calls(u)) for u in (MES, CMMS, APS))


def forward_codes(run_id: str) -> dict:
    """run 의 전진 호출(처리된 것)이 서비스별로 어떤 설비에 갔는지."""
    ok = lambda c: c["run"] == run_id and not c["failed"] and not c["duplicate"]  # noqa: E731
    return {
        "mes": sorted(c["code"] for c in svc_calls(MES) if ok(c) and c["body"]["status"] == "MAINTENANCE"),
        "cmms": sorted(c["code"] for c in svc_calls(CMMS) if ok(c) and c["operation"] == "createWorkOrder"),
        "aps": sorted(c["code"] for c in svc_calls(APS) if ok(c) and c["operation"] == "createReschedule"),
    }


def undo_timeline(run_id: str) -> list[tuple[float, str, str]]:
    """세 서비스가 기록한 보상 호출(처리된 것)을 시각순으로 — (at, 단계, 설비)."""
    ok = lambda c: c["run"] == run_id and not c["failed"] and not c["duplicate"]  # noqa: E731
    rows = [(c["at"], "mes", c["code"]) for c in svc_calls(MES) if ok(c) and c["body"]["status"] != "MAINTENANCE"]
    rows += [(c["at"], "cmms", c["code"]) for c in svc_calls(CMMS) if ok(c) and c["operation"] == "cancelWorkOrder"]
    rows += [(c["at"], "aps", c["code"]) for c in svc_calls(APS) if ok(c) and c["operation"] == "revertReschedule"]
    return sorted(rows)


def reset_demo_state() -> None:
    """설비 상태를 RUNNING 으로, 서비스 기록을 비운다 (정의·등록은 그대로)."""
    with seed.driver() as d, d.session() as s:
        s.run("MATCH (e:Equipment {demo:'kinetic-mes'}) SET e.status = 'RUNNING'").consume()
    seed.reset_services()


def wait_routes(token: str, timeout: float = 30) -> None:
    """게이트웨이가 새 시스템 라우트를 읽을 때까지 (route refresh 주기) health 로 기다린다."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all(rest("GET", f"/api/kinetic/systems/{n}/health", token).json().get("ok") for n, *_ in seed.SYSTEMS):
            return
        time.sleep(1)


def graph_status(codes: list[str]) -> dict:
    with seed.driver() as d, d.session() as s:
        rows = s.run("MATCH (e:Equipment {demo:'kinetic-mes'}) WHERE e.code IN $codes RETURN e.code AS c, e.status AS s",
                     codes=codes)
        return {r["c"]: r["s"] for r in rows}


async def scenarios() -> None:
    op = Agent(seed.token("kim.operator", ["plant_operator"], plant="P1"))
    viewer = Agent(seed.token("lee.viewer", ["viewer"], plant="P1"))
    approver = seed.token("park.manager", ["kinetic_approver"])
    admin = seed.token("admin", ["kinetic_admin"])
    # seed 가 시스템 인증(API 키·OAuth2)을 바꿨을 수 있다 — 게이트웨이가 새 라우트를 읽을 때까지(KINETIC_ROUTE_REFRESH)
    time.sleep(ROUTE_WAIT)
    wait_routes(op.token)

    # 1 ─ 토큰 없음 → 401 + resource_metadata
    r = httpx.post(MCP_URL, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                   headers={"Accept": "application/json, text/event-stream"}, timeout=10)
    www = r.headers.get("www-authenticate", "")
    check("1 토큰 없는 MCP 호출 → 401 + resource_metadata", r.status_code == 401 and "resource_metadata=" in www, www)

    # 2 ─ list_actions 가 정책 roles 로 걸러진다
    tools = await op.tools()
    _, mine = await op.call("list_actions", {"class": "Equipment"})
    _, theirs = await viewer.call("list_actions", {})
    check("2 운영자는 setMaintenanceMode 를 보고 viewer 는 아무것도 못 본다",
          "setMaintenanceMode" in [a["action"] for a in mine] and theirs == [] and len(tools) == 7
          and "compensate_run" in tools,
          f"tools={tools} operator={[a['action'] for a in mine]} viewer={theirs}")

    # 3 ─ temp > 80 plan → P1 허용, P2 거부(사유)
    _, plan = await op.call("plan_action", {"class": "Equipment", "action": "setMaintenanceMode",
                                            "where": HOT, "params": REASON})
    allowed = sorted(t["key"] for t in plan["allowed"])
    denied = {t["key"]: t["reason"] for t in plan["denied"]}
    check("3 plan(temp>80): P1 허용 · P2 거부(사유 포함)",
          allowed == ["EQ-101", "EQ-102", "EQ-104"] and sorted(denied) == ["EQ-201", "EQ-202"]
          and all(denied.values()), f"allowed={allowed} denied={denied}")

    # 4 ─ 실행 → mock-mes 는 P1 대상만 받음, run succeeded, 그래프 status 되쓰기
    if plan["requires_approval"]:
        rest("POST", f"/api/kinetic/plans/{plan['id']}/approve", approver, json={"note": "검증"})
    err, run = await op.call("execute_plan", {"plan_id": plan["id"]})
    received = sorted({c["code"] for c in mes_calls() if not c["failed"] and c["body"]["status"] == "MAINTENANCE"})
    status = graph_status(["EQ-101", "EQ-102", "EQ-104", "EQ-201"])
    check("4 실행: mock-mes 는 P1 대상만 · run succeeded · 그래프 status=MAINTENANCE",
          not err and run["status"] == "succeeded" and received == allowed
          and status == {"EQ-101": "MAINTENANCE", "EQ-102": "MAINTENANCE", "EQ-104": "MAINTENANCE",
                         "EQ-201": "RUNNING"}, f"run={run.get('status')} received={received} graph={status}")

    # 5 ─ 임계 초과 → 승인 없이 실행 거부 → REST 승인 → 실행
    _, big = await op.call("plan_action", {"class": "Equipment", "action": "setMaintenanceMode",
                                           "where": [{"prop": "temp", "op": ">", "value": 60}], "params": REASON})
    err1, body1 = await op.call("execute_plan", {"plan_id": big["id"]})
    self_approve = rest("POST", f"/api/kinetic/plans/{big['id']}/approve", op.token)
    ok_approve = rest("POST", f"/api/kinetic/plans/{big['id']}/approve", approver, json={"note": "5대 일괄 승인"})
    err2, run5 = await op.call("execute_plan", {"plan_id": big["id"]})
    check("5 임계 초과 plan: 승인 전 approval_required → 승인자 승인 → 실행 성공",
          big["requires_approval"] and len(big["allowed"]) == 5 and err1
          and body1["error"]["code"] == "approval_required" and self_approve.status_code == 403
          and ok_approve.json().get("status") == "approved" and not err2 and run5["status"] == "succeeded",
          f"allowed={len(big['allowed'])} first={body1.get('error', {}).get('code')} "
          f"self_approve={self_approve.status_code} run={run5.get('status')}")

    # 6 ─ 고장 주입 → partial → 복구 후 retry → succeeded
    httpx.post(f"{MES}/admin/fail", json={"codes": ["EQ-103"], "status": 503}, timeout=10)
    _, p6 = await op.call("plan_action_ids", {"class": "Equipment", "action": "setMaintenanceMode",
                                              "ids": ["EQ-103", "EQ-105"], "params": {"reason": "재점검"}})
    _, run6 = await op.call("execute_plan", {"plan_id": p6["id"]})
    first = run6["status"]
    httpx.post(f"{MES}/admin/fail", json={"codes": []}, timeout=10)
    retried = rest("POST", f"/api/kinetic/runs/{run6['id']}/retry", op.token).json()
    t103 = next(t for t in retried["targets"] if t["key"] == "EQ-103")
    check("6 EQ-103 고장 → run partial → 복구 후 retry → succeeded",
          first == "partial" and retried["status"] == "succeeded" and t103["attempts"] == 2,
          f"first={first} after_retry={retried['status']} EQ-103 attempts={t103['attempts']}")

    # 7 ─ 같은 plan 재실행 → 같은 run, 세 서비스 모두 추가 호출 0 · 멱등 키 중복 처리 없음
    before = all_calls()
    _, again = await op.call("execute_plan", {"plan_id": p6["id"]})
    after = all_calls()
    processed = [c["idempotency_key"] for u in (MES, CMMS, APS) for c in svc_calls(u)
                 if not c["failed"] and not c["duplicate"]]
    check("7 같은 plan 재실행 → 같은 run · 추가 호출 0 · 멱등 키 중복 처리 없음",
          again["id"] == run6["id"] and after == before and len(processed) == len(set(processed)),
          f"run={again['id']}=={run6['id']} calls {before}→{after} processed={len(processed)}")

    # 8 ─ routes 는 내부 헤더 없이는 403. 유효한 사용자 토큰을 붙인다 — 토큰이 없으면 게이트웨이 경유 시
    #     JWT 검사(401)에 먼저 걸려 "내부 전용" 차단을 검증하지 못한다.
    r8 = rest("GET", "/api/kinetic/systems/routes", op.token)
    check("8 /api/kinetic/systems/routes 내부 헤더 없음 → 403", r8.status_code == 403, str(r8.status_code))

    # 9 ─ 새 액션 발행 + 카탈로그 갱신 → list_actions 에 나타난다
    seed.publish_action(seed.RESUME_ACTION)
    n = rest("POST", "/api/kinetic/catalog/refresh", op.token).json()["actions"]
    _, listed = await op.call("list_actions", {"class": "Equipment"})
    names = sorted(a["action"] for a in listed)
    check("9 resumeOperation 발행 + 카탈로그 갱신 → list_actions 에 표시",
          n == 2 and names == ["resumeOperation", "setMaintenanceMode"], f"actions={n} listed={names}")

    # 10 ─ 3단계 실행: MES·CMMS·APS 가 각각 정확히 P1 대상만 받는다
    reset_demo_state()
    _, p10 = await op.call("plan_action", {"class": "Equipment", "action": "setMaintenanceMode",
                                           "where": HOT, "params": REASON})
    steps10 = sorted({c["step"] for c in p10["preview"]})
    rest("POST", f"/api/kinetic/plans/{p10['id']}/approve", approver, json={"note": "3단계 검증"})
    _, run10 = await op.call("execute_plan", {"plan_id": p10["id"]})
    got = forward_codes(run10["id"])
    p1 = ["EQ-101", "EQ-102", "EQ-104"]
    check("10 3단계 실행 → MES·CMMS·APS 각각 정확히 P1 대상 · 대상마다 단계 3개 성공",
          run10["status"] == "succeeded" and got == {"mes": p1, "cmms": p1, "aps": p1} and steps10 == ["aps", "cmms", "mes"]
          and all([st["status"] for st in t["steps"]] == ["succeeded"] * 3 for t in run10["targets"]),
          f"run={run10['status']} got={got} preview_steps={steps10}")

    # 11 ─ MCP compensate_run 으로 취소 → 대상 안에서는 APS → CMMS → MES, 대상끼리는 실행 완료 역순
    order = [t["key"] for t in sorted(run10["targets"], key=lambda t: t["finished_seq"], reverse=True)]
    err11, run11 = await op.call("compensate_run", {"run_id": run10["id"], "reason": "오판정 — 원래대로 되돌려"})
    expected = [(st, k) for k in order for st in ("aps", "cmms", "mes")]
    timeline = [(st, k) for _, st, k in undo_timeline(run10["id"])]
    seqs = [(c["target_key"], c["step"]) for c in sorted(run11.get("compensations", []), key=lambda c: c["seq"])]
    status11 = graph_status(p1)
    wo = {w["equipmentCode"]: w["status"] for w in
          httpx.get(f"{CMMS}/work-orders", headers=seed.cmms_headers(), timeout=10).json()}
    rs = {r["equipmentCode"]: r["status"] for r in
          httpx.get(f"{APS}/reschedules", headers=seed.aps_headers(), timeout=10).json()}
    _, again11 = await op.call("compensate_run", {"run_id": run10["id"]})
    check("11 compensate_run → 역순 보상(대상 내 APS→CMMS→MES, 대상은 완료 역순) · 그래프 RUNNING · 재취소 멱등",
          not err11 and run11["status"] == "compensated" and timeline == expected
          and seqs == [(k, st) for st, k in expected] and status11 == {k: "RUNNING" for k in p1}
          and set(wo.values()) == {"CANCELLED"} and set(rs.values()) == {"REVERTED"}
          and again11.get("compensations") == run11["compensations"],
          f"order={order} timeline={timeline} graph={status11} wo={wo} rs={rs}")

    # 12 ─ APS 고장(EQ-102) → 그 대상만 자동 보상(CMMS 취소 → MES 복원), 나머지 성공, run partial
    httpx.post(f"{APS}/admin/fail", json={"codes": ["EQ-102"], "operations": ["createReschedule"]},
               timeout=10).raise_for_status()
    _, p12 = await op.call("plan_action", {"class": "Equipment", "action": "setMaintenanceMode",
                                           "where": HOT, "params": REASON})
    rest("POST", f"/api/kinetic/plans/{p12['id']}/approve", approver, json={"note": "자동 보상 검증"})
    _, run12 = await op.call("execute_plan", {"plan_id": p12["id"]})
    httpx.post(f"{APS}/admin/fail", json={"codes": []}, timeout=10)
    by12 = {t["key"]: t for t in run12["targets"]}
    undo12 = [(st, k) for _, st, k in undo_timeline(run12["id"])]
    auto12 = [(c["target_key"], c["step"], c["trigger"]) for c in run12["compensations"]]
    status12 = graph_status(p1)
    check("12 APS 고장(EQ-102) → EQ-102 자동 보상(CMMS 취소→MES 복원) · 나머지 성공 · run partial",
          run12["status"] == "partial" and by12["EQ-102"]["status"] == "compensated"
          and by12["EQ-101"]["status"] == by12["EQ-104"]["status"] == "succeeded"
          and undo12 == [("cmms", "EQ-102"), ("mes", "EQ-102")]
          and auto12 == [("EQ-102", "cmms", "auto"), ("EQ-102", "mes", "auto")]
          and status12 == {"EQ-101": "MAINTENANCE", "EQ-102": "RUNNING", "EQ-104": "MAINTENANCE"},
          f"run={run12['status']} EQ-102={by12['EQ-102']['status']} undo={undo12} graph={status12}")

    # 13 ─ OpenAPI 에 없는 API 를 REST 로 수동 등록 → operations 에 source:'manual' · refresh 후에도 유지
    manual = {"operation_id": "getWorkOrder", "method": "GET", "path": "/work-orders/{id}",
              "summary": "작업지시 단건 조회 (OpenAPI 미기재)",
              "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}]}
    bad = rest("POST", "/api/kinetic/systems/mock-cmms/operations", admin, json={**manual, "parameters": []})
    added = rest("POST", "/api/kinetic/systems/mock-cmms/operations", admin, json=manual)
    refreshed = rest("POST", "/api/kinetic/systems/mock-cmms/refresh", admin)
    ops = {o["operation_id"]: o["source"] for o in
           rest("GET", "/api/kinetic/systems/mock-cmms/operations", op.token).json()}
    check("13 수동 API 등록 → operations 에 manual 로 표시 · 경로 변수 누락 422 · refresh 후 유지",
          bad.status_code == 422 and added.status_code == 200 and refreshed.status_code == 200
          and ops.get("getWorkOrder") == "manual" and ops.get("createWorkOrder") == "openapi",
          f"bad={bad.status_code} added={added.status_code} ops={ops}")

    # 14 ─ 시스템 health (게이트웨이 경유)
    health = {n: rest("GET", f"/api/kinetic/systems/{n}/health", op.token).json() for n, *_ in seed.SYSTEMS}
    check("14 시스템 health → 세 시스템 모두 ok",
          all(h.get("ok") and h.get("http_status") == 200 for h in health.values()),
          json.dumps({n: (h.get("ok"), h.get("http_status"), h.get("latency_ms")) for n, h in health.items()}))

    # 15 ─ mock-cmms 는 API 키가 있어야 한다: 키 없이 직접 → 401, kinetic 실행(게이트웨이가 X-API-Key 주입) → 성공
    reset_demo_state()
    direct = httpx.post(f"{CMMS}/work-orders", json={"equipmentCode": "EQ-101", "reason": "키 없이"}, timeout=10)
    direct_aps = httpx.post(f"{APS}/reschedules", json={"equipmentCode": "EQ-101"}, timeout=10)
    bad_token = httpx.post(f"{APS}/reschedules", json={"equipmentCode": "EQ-101"}, timeout=10,
                           headers={"Authorization": f"Bearer {op.token}"})  # 사용자 토큰(aud kinetic-action)은 안 된다
    cmms_sys = rest("GET", "/api/kinetic/systems/mock-cmms", op.token).json()
    _, p15 = await op.call("plan_action_ids", {"class": "Equipment", "action": "setMaintenanceMode",
                                               "ids": ["EQ-101"], "params": {"reason": "API 키 주입 검증"}})
    leaked = any(v for c in p15["preview"] for k, v in c["headers"].items()
                 if k.lower() in ("x-api-key", "authorization"))
    _, run15 = await op.call("execute_plan", {"plan_id": p15["id"]})
    steps15 = {st["name"]: (st["status"], st["http_status"]) for st in run15["targets"][0]["steps"]}
    cmms_auth = httpx.get(f"{CMMS}/admin/auth-stats", timeout=10).json()
    check("15 mock-cmms 키 없이 직접 → 401 · kinetic 실행은 게이트웨이가 X-API-Key 주입해 성공 · 비밀은 응답에 없음",
          direct.status_code == 401 and direct_aps.status_code == 401 and bad_token.status_code == 401
          and run15["status"] == "succeeded" and steps15.get("cmms") == ("succeeded", 200)
          and cmms_sys["auth"] == {"kind": "api_key", "header": "X-API-Key", "query_param": None,
                                   "secret_env": "CMMS_API_KEY"}
          and seed.CMMS_API_KEY not in json.dumps(cmms_sys) and not leaked and cmms_auth["accepted"] >= 1,
          f"direct cmms={direct.status_code} aps={direct_aps.status_code} user-token={bad_token.status_code} "
          f"run={run15['status']} steps={steps15} auth={cmms_sys['auth']} cmms_auth={cmms_auth}")

    # 16 ─ mock-aps 는 OAuth2 bearer: 게이트웨이가 dev-idp 에서 client credentials 토큰을 받아 주입, 캐시한다
    #      (게이트웨이 토큰 캐시는 프로세스 수명 동안 유지된다 — 이번 검증만의 token_url 질의 문자열로 캐시 키를 새로 만든 뒤
    #       3대 실행 → 토큰 발급 1회, 다음 run → 0회)
    base_auth = seed.SYSTEM_PROFILES["mock-aps"]["auth"]
    aps_auth = {**base_auth, "token_url": f"{base_auth['token_url']}?verify={int(time.time() * 1000)}"}
    rest("PATCH", "/api/kinetic/systems/mock-aps", admin, json={"auth": aps_auth}).raise_for_status()
    time.sleep(ROUTE_WAIT)  # 게이트웨이 KINETIC_ROUTE_REFRESH
    httpx.post(f"{seed.IDP}/oauth/stats/reset", timeout=10)
    reset_demo_state()
    _, p16 = await op.call("plan_action", {"class": "Equipment", "action": "setMaintenanceMode",
                                           "where": HOT, "params": REASON})
    rest("POST", f"/api/kinetic/plans/{p16['id']}/approve", approver, json={"note": "OAuth2 검증"})
    _, run16 = await op.call("execute_plan", {"plan_id": p16["id"]})
    stats1 = httpx.get(f"{seed.IDP}/oauth/stats", timeout=10).json()
    _, p16b = await op.call("plan_action_ids", {"class": "Equipment", "action": "setMaintenanceMode",
                                                "ids": ["EQ-103"], "params": {"reason": "캐시 재사용"}})
    _, run16b = await op.call("execute_plan", {"plan_id": p16b["id"]})
    stats2 = httpx.get(f"{seed.IDP}/oauth/stats", timeout=10).json()
    aps_ok = [st for t in run16["targets"] for st in t["steps"] if st["name"] == "aps" and st["status"] == "succeeded"]
    aps_auth_stats = httpx.get(f"{APS}/admin/auth-stats", timeout=10).json()
    rest("PATCH", "/api/kinetic/systems/mock-aps", admin,
         json={"auth": seed.SYSTEM_PROFILES["mock-aps"]["auth"]}).raise_for_status()
    check("16 mock-aps OAuth2 client credentials — 3대 실행 성공 · 토큰 발급 1회(캐시) · 다음 run 도 발급 0회",
          run16["status"] == "succeeded" and len(aps_ok) == 3 and stats1["issued"] == 1
          and stats1["token_requests"] == 1 and run16b["status"] == "succeeded" and stats2["token_requests"] == 1
          and aps_auth_stats["accepted"] >= 4,
          f"run={run16['status']} aps_ok={len(aps_ok)} idp after run={stats1} after 2nd run={stats2} "
          f"aps_auth={aps_auth_stats}")

    # 17 ─ Swagger 2.0 YAML 업로드 → OpenAPI 3 로 변환해 operation 등록 (basePath 반영)
    r17 = rest("POST", "/api/kinetic/systems", admin, json={
        "name": "legacy-erp", "display_name": "레거시 ERP", "owner_team": "ERP팀", "icon": "erp", "tags": ["erp"],
        "base_url": "http://localhost:8031", "openapi_text": SWAGGER2_YAML,
        "environments": [{"name": "dev", "base_url": "http://localhost:8031"},
                         {"name": "prod", "base_url": "https://erp.example.com"}]})
    s17 = r17.json()
    ops17 = {o["operation_id"]: o for o in rest("GET", "/api/kinetic/systems/legacy-erp/operations", op.token).json()}
    switched = rest("PATCH", "/api/kinetic/systems/legacy-erp", admin, json={"active_environment": "prod"}).json()
    rest("DELETE", "/api/kinetic/systems/legacy-erp", admin)
    check("17 Swagger 2.0 YAML 업로드 → swagger2 판별 · operation 3개(basePath /api/v2) · body 스키마 · 환경 전환",
          r17.status_code == 200 and s17["spec_format"] == "swagger2" and s17["operations_count"] == 3
          and ops17.get("getOrder", {}).get("path") == "/api/v2/orders/{orderId}"
          and (ops17.get("createOrder", {}).get("request_body_schema") or {}).get("properties", {}).get("qty")
          == {"type": "integer"} and switched.get("base_url") == "https://erp.example.com",
          f"status={r17.status_code} format={s17.get('spec_format')} ops={ {k: v['path'] for k, v in ops17.items()} } "
          f"switched={switched.get('base_url')}")

    # 18 ─ SOAP(WSDL) 시스템: 등록은 되지만 adapter_required · 그 시스템을 쓰는 액션 plan → 422 not_executable
    r18 = rest("POST", "/api/kinetic/systems", admin, json={
        "name": "sap-pm", "display_name": "SAP PM (SOAP)", "owner_team": "ERP팀", "icon": "sap",
        "base_url": "http://localhost:8031/sap/bc/srt", "openapi_text": WSDL})
    s18 = r18.json()
    seed.publish_action({**seed.RESUME_ACTION, "behavior_name": "notifySap", "description": "SAP PM 통지 (SOAP)",
                         "system": "sap-pm", "operation_id": "CreateNotification",
                         "arg_mapping": {"body.equipment": "$this.code"}})
    rest("POST", "/api/kinetic/catalog/refresh", op.token)
    p18 = rest("POST", "/api/kinetic/plans/by-ids", op.token,
               json={"class": "Equipment", "action": "notifySap", "ids": ["EQ-101"], "params": {"reason": "x"}})
    err18, mcp18 = await op.call("plan_action_ids", {"class": "Equipment", "action": "notifySap", "ids": ["EQ-101"],
                                                     "params": {"reason": "x"}})
    listed18 = [x["name"] for x in rest("GET", "/api/kinetic/systems", op.token).json()]
    with seed.driver() as d, d.session() as s:
        s.run("MATCH (:_OntologyClass {class_name:'Equipment'})-[:HAS_ACTION]->(a:_OntologyBehavior "
              "{behavior_name:'notifySap'}) DETACH DELETE a").consume()
    rest("DELETE", "/api/kinetic/systems/sap-pm", admin)
    rest("POST", "/api/kinetic/catalog/refresh", op.token)
    check("18 SOAP(WSDL) 등록 → protocol soap · executable false · adapter_required · plan → 422 not_executable",
          r18.status_code == 200 and s18["protocol"] == "soap" and s18["spec_format"] == "wsdl"
          and s18["executable"] is False and s18["adapter_required"] is True and s18["operations_count"] == 2
          and p18.status_code == 422 and p18.json()["error"]["code"] == "not_executable"
          and err18 and mcp18["error"]["code"] == "not_executable" and "sap-pm" in listed18,
          f"status={r18.status_code} protocol={s18.get('protocol')} adapter={s18.get('adapter_required')} "
          f"plan={p18.status_code} {p18.json().get('error', {}).get('code')} mcp={mcp18.get('error', {}).get('code')}")

    # 19 ─ 연결 테스트 (저장 안 함): 스펙 파싱 · health 직접 호출 · 인증 env 존재 여부(값은 보지 않음)
    before19 = [x["name"] for x in rest("GET", "/api/kinetic/systems", admin).json()]
    body19 = seed.system_body("mock-cmms", seed.MOCK_CMMS_FOR_KINETIC, "연결 테스트")
    t19 = rest("POST", "/api/kinetic/systems/test", admin, json={**body19, "name": "cmms-test"}).json()
    t19b = rest("POST", "/api/kinetic/systems/test", admin, json={
        "name": "nowhere", "base_url": "http://localhost:1", "openapi_text": "{broken",
        "auth": {"kind": "api_key", "secret_env": "KINETIC_VERIFY_NOT_SET"}}).json()
    t19c = rest("POST", "/api/kinetic/systems/test", op.token, json=body19)
    after19 = [x["name"] for x in rest("GET", "/api/kinetic/systems", admin).json()]
    check("19 POST /systems/test → spec·health·auth 결과 · 실패도 항목별 보고 · admin 전용 · 저장 안 함",
          t19.get("ok") and t19["spec"]["ok"] and t19["spec"]["operations"] >= 3 and t19["health"]["ok"]
          and t19["health"]["http_status"] == 200 and t19["auth"]["ok"] and t19["auth"]["missing_env"] == []
          and seed.CMMS_API_KEY not in json.dumps(t19)
          and t19b["ok"] is False and not t19b["spec"]["ok"] and not t19b["health"]["ok"]
          and t19b["auth"]["missing_env"] == ["KINETIC_VERIFY_NOT_SET"] and t19c.status_code == 403
          and before19 == after19,
          f"ok={t19.get('ok')} spec={t19.get('spec', {}).get('operations')} health={t19.get('health')} "
          f"auth={t19.get('auth')} bad={ {k: t19b[k].get('ok') for k in ('spec', 'health', 'auth')} }")


ROUTE_WAIT = float(os.environ.get("KINETIC_ROUTE_WAIT", "5"))

SWAGGER2_YAML = """
swagger: "2.0"
info: {title: legacy erp, version: "2.1"}
host: erp.example.com
basePath: /api/v2
schemes: [https]
paths:
  /orders/{orderId}:
    get:
      operationId: getOrder
      parameters:
        - {name: orderId, in: path, required: true, type: string}
      responses: {"200": {description: ok, schema: {$ref: "#/definitions/Order"}}}
  /orders:
    post:
      operationId: createOrder
      parameters:
        - {name: body, in: body, required: true, schema: {$ref: "#/definitions/Order"}}
      responses: {"201": {description: created}}
    get:
      operationId: listOrders
      parameters:
        - {name: limit, in: query, type: integer}
      responses: {"200": {description: ok}}
definitions:
  Order:
    type: object
    properties:
      orderId: {type: string}
      qty: {type: integer}
"""

WSDL = """<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" name="PmNotification">
  <wsdl:portType name="PmNotificationPort">
    <wsdl:operation name="CreateNotification"><wsdl:input message="tns:CreateIn"/></wsdl:operation>
    <wsdl:operation name="CloseNotification"><wsdl:input message="tns:CloseIn"/></wsdl:operation>
  </wsdl:portType>
</wsdl:definitions>
"""


def main() -> int:
    seed.main()
    try:
        asyncio.run(scenarios())
    except Exception:
        traceback.print_exc()
        check("시나리오 실행 중 예외", False)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} PASS" + (f" — 실패: {failed}" if failed else ""))
    return 1 if failed or len(RESULTS) < 19 else 0


if __name__ == "__main__":
    sys.exit(main())
