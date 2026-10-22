"""다단계(사가) 액션 · 자동 보상 · 취소 · 재시도 · 레지스트리 확장 · compensate_run (계약 §1.3, §3, §4)."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from conftest import _KEY, POLICY, FakeGraph, auth, equipment
from app.catalog import Action, InvalidSteps, parse_steps
from app.errors import KineticError
from app.main import create_app
from app.mapping import build_call, resolve
from app.store import Store

OP1 = dict(sub="op1", roles=["plant_operator"], plant="P1")
ADMIN = dict(sub="admin", roles=["kinetic_admin"])
APPROVER = dict(sub="boss", roles=["kinetic_approver"])

STEPS = [
    {"name": "mes", "title": "MES 설비 상태 변경", "system": "mock-mes", "operation_id": "setEquipmentStatus",
     "arg_mapping": {"path.code": "$this.code", "body.status": "MAINTENANCE", "body.reason": "$params.reason"},
     "compensation": {"system": "mock-mes", "operation_id": "setEquipmentStatus",
                      "arg_mapping": {"path.code": "$this.code", "body.status": "$before.status",
                                      "body.reason": "$cancel.reason"}}},
    {"name": "cmms", "title": "정비 작업지시 생성", "system": "mock-cmms", "operation_id": "createWorkOrder",
     "arg_mapping": {"body.equipmentCode": "$this.code", "body.reason": "$params.reason"},
     "compensation": {"system": "mock-cmms", "operation_id": "cancelWorkOrder",
                      "arg_mapping": {"path.id": "$steps.cmms.response.id", "body.reason": "$cancel.reason"}}},
    {"name": "aps", "title": "생산 일정 재배정", "system": "mock-aps", "operation_id": "createReschedule",
     "arg_mapping": {"body.equipmentCode": "$this.code", "body.workOrder": "$steps.cmms.response.id"},
     "compensation": {"system": "mock-aps", "operation_id": "revertReschedule",
                      "arg_mapping": {"path.id": "$steps.aps.response.id"}}},
]

SAGA = {
    "behavior_type": "action", "behavior_name": "setMaintenanceMode", "class_name": "Equipment",
    "schema_id": "demo", "description": "점검 전환 (MES→CMMS→APS)", "key_property": "code",
    "parameters": json.dumps({"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}),
    "steps": json.dumps(STEPS, ensure_ascii=False), "effect": "write", "confirm_threshold": 10, "max_targets": 50,
    "policy": json.dumps(POLICY, ensure_ascii=False), "writeback_property": "status", "version": 2,
}


def _op(op_id, method, path, params=()):
    return {method: {"operationId": op_id, "parameters": [
        {"name": p, "in": "path", "required": True, "schema": {"type": "string"}} for p in params]}}


SPECS = {
    "mes.test": {"openapi": "3.1.0", "paths": {"/equipment/{code}/status": _op("setEquipmentStatus", "post",
                                                                              "", ["code"])}},
    "cmms.test": {"openapi": "3.1.0", "paths": {
        "/work-orders": {**_op("createWorkOrder", "post", ""), **_op("listWorkOrders", "get", "")},
        "/work-orders/{id}/cancel": _op("cancelWorkOrder", "post", "", ["id"])}},
    "aps.test": {"openapi": "3.1.0", "paths": {
        "/reschedules": _op("createReschedule", "post", ""),
        "/reschedules/{id}/revert": _op("revertReschedule", "post", "", ["id"])}},
}


class FakeSystems:
    """가짜 MES·CMMS·APS. 호출 순서를 `log` 에 남기고 Idempotency-Key 로 중복을 거른다."""

    def __init__(self):
        self.log: list[dict] = []
        self.fail: set[tuple[str, str]] = set()  # (operationId, 설비코드)
        self.down: set[str] = set()
        self.seen: dict[str, dict] = {}
        self.records: dict[str, dict] = {}
        self.n = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if path == "/openapi.json":
            return httpx.Response(200, json=SPECS[host])
        if path == "/health":
            return httpx.Response(503 if host in self.down else 200, json={"ok": host not in self.down})
        body = json.loads(request.content or b"null")
        parts = path.strip("/").split("/")
        if host == "mes.test":
            op, code = "setEquipmentStatus", parts[1]
        elif parts[-1] in ("cancel", "revert"):
            op = "cancelWorkOrder" if host == "cmms.test" else "revertReschedule"
            code = self.records[parts[1]]["equipmentCode"]
        else:
            op = "createWorkOrder" if host == "cmms.test" else "createReschedule"
            code = body["equipmentCode"]
        key = request.headers.get("idempotency-key")
        self.log.append({"op": op, "code": code, "key": key, "body": body, "path": path,
                         "run": request.headers.get("x-kinetic-run")})
        if (op, code) in self.fail:
            return httpx.Response(503, json={"detail": "down"})
        if key in self.seen:
            return httpx.Response(200, json=self.seen[key])
        if op == "setEquipmentStatus":
            res = {"code": code, "status": body["status"]}
        elif op in ("createWorkOrder", "createReschedule"):
            self.n += 1
            rid = f"{'WO' if op == 'createWorkOrder' else 'RS'}-{self.n}"
            self.records[rid] = {"id": rid, "equipmentCode": code, "status": "OPEN" if op == "createWorkOrder" else "APPLIED"}
            res = dict(self.records[rid])
        else:
            rec = self.records[parts[1]]
            rec["status"] = "CANCELLED" if op == "cancelWorkOrder" else "REVERTED"
            res = dict(rec)
        self.seen[key] = res
        return httpx.Response(200, json=res)

    def ops(self, code=None):
        return [(c["op"], c["code"]) for c in self.log if code is None or c["code"] == code]


@pytest.fixture
def systems():
    return FakeSystems()


@pytest.fixture
def sgraph():
    return FakeGraph({"Equipment": equipment()}, [dict(SAGA)])


@pytest.fixture
def sc(settings, sgraph, systems):
    http = httpx.AsyncClient(transport=httpx.MockTransport(systems.handler))
    app = create_app(settings, graph=sgraph, http=http, key_resolver=lambda _t: _KEY.public_key(), refresh_loop=False)
    with TestClient(app) as c:
        for name, host in (("mock-mes", "mes.test"), ("mock-cmms", "cmms.test"), ("mock-aps", "aps.test")):
            r = c.post("/api/kinetic/systems", headers=auth(**ADMIN),
                       json={"name": name, "base_url": f"http://{host}", "openapi_url": f"http://{host}/openapi.json",
                             "description": f"{name} 서비스"})
            assert r.status_code == 200, r.text
        c.app_state = app.state
        yield c


def run_ids(c, ids, who=OP1):
    p = c.post("/api/kinetic/plans/by-ids", headers=auth(**who),
               json={"class": "Equipment", "action": "setMaintenanceMode", "ids": ids, "params": {"reason": "과열"}})
    assert p.status_code == 200, p.text
    p = p.json()
    r = c.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**who))
    assert r.status_code == 200, r.text
    return p, r.json()


def tgt(run, key):
    return next(t for t in run["targets"] if t["key"] == key)


# ── 카탈로그 · 매핑 ──

def test_parse_steps_validation_and_legacy():
    assert [s.name for s in parse_steps(json.dumps(STEPS))] == ["mes", "cmms", "aps"]
    for bad in ([{**STEPS[0], "name": "Mes"}], [STEPS[0], STEPS[0]], [{"name": "x", "system": "s"}],
                [{**STEPS[0], "compensation": {"system": "s"}}], {"a": 1}):
        with pytest.raises(InvalidSteps):
            parse_steps(json.dumps(bad))
    legacy = Action.from_props({"class_name": "E", "behavior_name": "a", "system": "s", "operation_id": "o",
                                "arg_mapping": '{"path.x": "$this.x"}'})
    assert [(s.name, s.system, s.operation_id, s.compensation) for s in legacy.steps] == [("main", "s", "o", None)]
    assert legacy.summary()["steps"] == [{"name": "main", "title": "a", "system": "s", "operation_id": "o",
                                          "compensable": False}]


def test_invalid_steps_action_is_ignored(sc, sgraph):
    sgraph.actions.append({**SAGA, "behavior_name": "broken", "steps": json.dumps([STEPS[0], STEPS[0]])})
    assert sc.post("/api/kinetic/catalog/refresh", headers=auth(**OP1)).json() == {"actions": 1}
    summary = sc.get("/api/kinetic/actions", headers=auth(**OP1)).json()[0]
    assert [(s["name"], s["compensable"]) for s in summary["steps"]] == [("mes", True), ("cmms", True), ("aps", True)]
    assert summary["system"] == "mock-mes" and summary["operation_id"] == "setEquipmentStatus"


def test_steps_before_cancel_resolution():
    ctx = {"this": {"code": "EQ-1", "status": "MAINTENANCE"}, "before": {"status": "RUNNING"},
           "steps": {"cmms": {"id": "WO-7", "items": [{"n": 3}]}}, "cancel": {"reason": "취소"}}
    assert resolve("$steps.cmms.response.id", ctx) == "WO-7"
    assert resolve("$steps.cmms.response.items.0.n", ctx) == 3
    assert resolve("$before.status", ctx) == "RUNNING" and resolve("$cancel.reason", ctx) == "취소"
    for bad in ("$steps.aps.response.id", "$steps.cmms.response.nope", "$steps.cmms.id"):
        with pytest.raises(KineticError):
            resolve(bad, ctx)
    call = build_call({"method": "POST", "path": "/w/{id}/cancel"}, {"path.id": "$steps.cmms.response.id"},
                      {**ctx, "preview": True})
    assert call["path"] == "/w/<$steps.cmms.response.id>/cancel"


# ── plan 미리보기 · 실행 ──

def test_preview_is_target_x_step(sc):
    p = sc.post("/api/kinetic/plans/by-ids", headers=auth(**OP1),
                json={"class": "Equipment", "action": "setMaintenanceMode", "ids": ["EQ-101", "EQ-102"],
                      "params": {"reason": "과열"}}).json()
    assert [(c["target_key"], c["step"]) for c in p["preview"]] == [
        (k, s) for k in ("EQ-101", "EQ-102") for s in ("mes", "cmms", "aps")]
    aps = p["preview"][2]
    assert aps["url"] == "http://aps.test/reschedules" and aps["compensable"]
    assert aps["body"] == {"equipmentCode": "EQ-101", "workOrder": "<$steps.cmms.response.id>"}
    assert aps["headers"]["Idempotency-Key"] == f"{p['id']}:EQ-101:aps:a1"


def test_three_step_success(sc, systems, sgraph):
    p, run = run_ids(sc, ["EQ-101", "EQ-102"])
    assert run["status"] == "succeeded" and run["compensations"] == [] and run["cancel"] is None
    for key in ("EQ-101", "EQ-102"):
        t = tgt(run, key)
        assert [s["status"] for s in t["steps"]] == ["succeeded"] * 3 and t["before"]["status"] == "RUNNING"
        assert systems.ops(key) == [("setEquipmentStatus", key), ("createWorkOrder", key), ("createReschedule", key)]
        aps = next(c for c in systems.log if c["code"] == key and c["op"] == "createReschedule")
        assert aps["body"]["workOrder"] == t["steps"][1]["response"]["id"]  # $steps 응답이 다음 단계로
        assert aps["key"] == f"{p['id']}:{key}:aps:a1" and aps["run"] == run["id"]
    assert sorted(t["finished_seq"] for t in run["targets"]) == [1, 2]
    assert sorted(sgraph.writes) == [("Equipment", k, "status", "MAINTENANCE") for k in ("EQ-101", "EQ-102")]


def test_failure_at_step3_compensates_in_reverse(sc, systems, sgraph):
    systems.fail = {("createReschedule", "EQ-102")}
    p, run = run_ids(sc, ["EQ-101", "EQ-102"])
    t = tgt(run, "EQ-102")
    assert t["status"] == "compensated" and t["compensated_by"] == "auto" and t["error"].startswith("aps:")
    assert systems.ops("EQ-102") == [("setEquipmentStatus", "EQ-102"), ("createWorkOrder", "EQ-102"),
                                     ("createReschedule", "EQ-102"), ("cancelWorkOrder", "EQ-102"),
                                     ("setEquipmentStatus", "EQ-102")]
    restore = systems.log[-1] if systems.log[-1]["code"] == "EQ-102" else \
        [c for c in systems.log if c["code"] == "EQ-102"][-1]
    assert restore["body"]["status"] == "RUNNING" and "자동 보상" in restore["body"]["reason"]
    assert restore["key"] == f"{p['id']}:EQ-102:mes:a1:c"
    assert [(c["seq"], c["step"], c["trigger"], c["status"]) for c in run["compensations"]] == [
        (1, "cmms", "auto", "succeeded"), (2, "mes", "auto", "succeeded")]
    assert [s["compensation"]["status"] for s in t["steps"][:2]] == ["succeeded", "succeeded"]
    assert t["steps"][2]["status"] == "failed" and t["steps"][2]["compensation"] is None
    assert run["status"] == "partial" and tgt(run, "EQ-101")["status"] == "succeeded"
    assert [w[1] for w in sgraph.writes] == ["EQ-101"]  # 자동 보상된 대상은 되쓰기 없음


def test_compensation_failure_is_dead(sc, systems):
    systems.fail = {("createReschedule", "EQ-101"), ("cancelWorkOrder", "EQ-101")}
    _, run = run_ids(sc, ["EQ-101"])
    t = run["targets"][0]
    assert t["status"] == "dead" and run["status"] == "failed"
    assert [(c["step"], c["status"]) for c in run["compensations"]] == [("cmms", "failed"), ("mes", "succeeded")]


def test_step1_failure_nothing_to_compensate(sc, systems):
    systems.fail = {("setEquipmentStatus", "EQ-101")}
    _, run = run_ids(sc, ["EQ-101"])
    t = run["targets"][0]
    assert t["status"] == "failed" and [s["status"] for s in t["steps"]] == ["failed", "skipped", "skipped"]
    assert run["compensations"] == [] and systems.ops() == [("setEquipmentStatus", "EQ-101")]


# ── 취소 ──

def _comp_ops(systems, run_id):
    return [(c["op"], c["code"]) for c in systems.log if c["run"] == run_id and
            (c["op"] in ("cancelWorkOrder", "revertReschedule") or
             (c["op"] == "setEquipmentStatus" and c["body"]["status"] != "MAINTENANCE"))]


def test_cancel_reverse_order_across_targets(sc, systems, sgraph):
    p, run = run_ids(sc, ["EQ-101", "EQ-102", "EQ-104"])
    order = [t["key"] for t in sorted(run["targets"], key=lambda t: t["finished_seq"], reverse=True)]
    assert sc.post(f"/api/kinetic/runs/{run['id']}/compensate", headers=auth("op2", ["plant_operator"], plant="P1"),
                   json={}).status_code == 403
    r = sc.post(f"/api/kinetic/runs/{run['id']}/compensate", headers=auth(**OP1), json={"reason": "오판정 — 원복"})
    assert r.status_code == 200, r.text
    run2 = r.json()
    expected = [(op, k) for k in order for op in ("revertReschedule", "cancelWorkOrder", "setEquipmentStatus")]
    assert _comp_ops(systems, run["id"]) == expected
    assert [(c["seq"], c["target_key"], c["step"], c["trigger"]) for c in run2["compensations"]] == [
        (i + 1, k, s, "cancel") for i, (k, s) in enumerate((k, s) for k in order for s in ("aps", "cmms", "mes"))]
    assert run2["status"] == "compensated" and all(t["status"] == "compensated" for t in run2["targets"])
    assert run2["cancel"]["actor_sub"] == "op1" and run2["cancel"]["reason"] == "오판정 — 원복"
    mes_restore = [c for c in systems.log if c["op"] == "setEquipmentStatus" and c["body"]["status"] == "RUNNING"]
    assert {c["body"]["reason"] for c in mes_restore} == {"오판정 — 원복"}
    assert all(c["key"].endswith(":mes:a1:c") for c in mes_restore)
    assert [w for w in sgraph.writes if w[3] == "RUNNING"] == [("Equipment", k, "status", "RUNNING") for k in order]
    # 재취소 = 기존 결과, 추가 호출 없음 (approver 도 취소 가능)
    n = len(systems.log)
    again = sc.post(f"/api/kinetic/runs/{run['id']}/compensate", headers=auth(**APPROVER)).json()
    assert again["compensations"] == run2["compensations"] and len(systems.log) == n
    events = [e["event"] for e in sc.get(f"/api/kinetic/audit?plan_id={p['id']}", headers=auth(**APPROVER)).json()]
    assert events == ["plan", "execute", "compensate"]
    r = sc.post(f"/api/kinetic/runs/{run['id']}/retry", headers=auth(**OP1))
    assert r.status_code == 409


def test_cancel_by_approver_after_partial_run(sc, systems):
    systems.fail = {("createReschedule", "EQ-102")}
    _, run = run_ids(sc, ["EQ-101", "EQ-102"])
    systems.fail = set()
    run2 = sc.post(f"/api/kinetic/runs/{run['id']}/compensate", headers=auth(**APPROVER)).json()
    cancel = [c for c in run2["compensations"] if c["trigger"] == "cancel"]
    assert [(c["target_key"], c["step"]) for c in cancel] == [("EQ-101", s) for s in ("aps", "cmms", "mes")]
    assert run2["status"] == "compensated" and run2["cancel"]["reason"] == "사용자 취소"
    assert tgt(run2, "EQ-102")["compensated_by"] == "auto"


def test_cancel_skips_step_without_compensation_and_partial(sc, sgraph, systems):
    steps = [dict(STEPS[0]), dict(STEPS[1]), {k: v for k, v in STEPS[2].items() if k != "compensation"}]
    sgraph.actions[0] = {**SAGA, "steps": json.dumps(steps)}
    sc.post("/api/kinetic/catalog/refresh", headers=auth(**OP1))
    p = sc.post("/api/kinetic/plans/by-ids", headers=auth(**OP1),
                json={"class": "Equipment", "action": "setMaintenanceMode", "ids": ["EQ-101", "EQ-102"],
                      "params": {"reason": "x"}}).json()
    assert [c["compensable"] for c in p["preview"][:3]] == [True, True, False]
    run = sc.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1)).json()
    systems.fail = {("cancelWorkOrder", "EQ-101")}
    run2 = sc.post(f"/api/kinetic/runs/{run['id']}/compensate", headers=auth(**OP1), json={"reason": "r"}).json()
    t1 = tgt(run2, "EQ-101")
    assert [s["compensation"]["status"] for s in t1["steps"]] == ["succeeded", "failed", "none"]
    assert t1["status"] == "dead" and tgt(run2, "EQ-102")["status"] == "compensated"
    assert run2["status"] == "partially_compensated"
    assert all(c["step"] != "aps" for c in run2["compensations"])  # 보상 없는 단계는 호출 순서에 없다


# ── 재시도 ──

def test_retry_after_auto_compensation_uses_new_attempt(sc, systems):
    systems.fail = {("createReschedule", "EQ-101")}
    p, run = run_ids(sc, ["EQ-101"])
    assert run["targets"][0]["status"] == "compensated"
    systems.fail = set()
    run = sc.post(f"/api/kinetic/runs/{run['id']}/retry", headers=auth(**OP1)).json()
    t = run["targets"][0]
    assert run["status"] == "succeeded" and t["attempts"] == 2 and t["compensated_by"] is None
    keys = [c["key"] for c in systems.log]
    pid = p["id"]
    assert keys == [f"{pid}:EQ-101:mes:a1", f"{pid}:EQ-101:cmms:a1", f"{pid}:EQ-101:aps:a1",
                    f"{pid}:EQ-101:cmms:a1:c", f"{pid}:EQ-101:mes:a1:c",
                    f"{pid}:EQ-101:mes:a2", f"{pid}:EQ-101:cmms:a2", f"{pid}:EQ-101:aps:a2"]
    # 재시도로 만들어진 작업지시가 취소 대상이다 (a2 응답)
    run = sc.post(f"/api/kinetic/runs/{run['id']}/compensate", headers=auth(**OP1)).json()
    cancel = next(c for c in systems.log if c["key"] == f"{pid}:EQ-101:cmms:a2:c")
    assert cancel["path"] == f"/work-orders/{t['steps'][1]['response']['id']}/cancel"


def test_retry_cap_dead(sc, systems):
    systems.fail = {("createWorkOrder", "EQ-101")}
    _, run = run_ids(sc, ["EQ-101"])
    for _ in range(3):
        run = sc.post(f"/api/kinetic/runs/{run['id']}/retry", headers=auth(**OP1)).json()
    t = run["targets"][0]
    assert t["status"] == "dead" and t["attempts"] == 3
    assert sum(c["op"] == "createWorkOrder" for c in systems.log) == 3


# ── 레지스트리 ──

def test_registry_crud_manual_ops_refresh_health(sc, systems):
    h = auth(**ADMIN)
    s = sc.get("/api/kinetic/systems/mock-cmms", headers=auth(**OP1)).json()
    assert s["route"] == "/svc/mock-cmms" and s["description"] == "mock-cmms 서비스" and s["health_path"] == "/health"
    assert {o["operation_id"]: o["source"] for o in s["operations"]} == {
        "createWorkOrder": "openapi", "listWorkOrders": "openapi", "cancelWorkOrder": "openapi"}
    assert s["openapi_url"] == "http://cmms.test/openapi.json" and s["auth_secret_env"] is None
    assert sc.patch("/api/kinetic/systems/mock-cmms", headers=auth(**OP1), json={}).status_code == 403
    s = sc.patch("/api/kinetic/systems/mock-cmms", headers=h,
                 json={"description": "설비보전", "timeout_ms": 3000, "health_path": "/health"}).json()
    assert s["description"] == "설비보전" and s["timeout_ms"] == 3000 and s["updated_at"] >= s["created_at"]
    # 수동 operation
    bad = sc.post("/api/kinetic/systems/mock-cmms/operations", headers=h,
                  json={"operation_id": "getWorkOrder", "method": "GET", "path": "/work-orders/{id}"})
    assert bad.status_code == 422
    assert sc.post("/api/kinetic/systems/mock-cmms/operations", headers=h,
                   json={"operation_id": "x", "method": "TRACE", "path": "/x"}).status_code == 422
    op = sc.post("/api/kinetic/systems/mock-cmms/operations", headers=h,
                 json={"operation_id": "getWorkOrder", "method": "get", "path": "/work-orders/{id}",
                       "summary": "작업지시 조회", "parameters": [{"name": "id", "in": "path"}]}).json()
    assert op["source"] == "manual" and op["method"] == "GET" and op["parameters"][0]["required"]
    ops = sc.get("/api/kinetic/systems/mock-cmms/operations", headers=auth(**OP1)).json()
    assert {o["operation_id"] for o in ops} >= {"getWorkOrder", "createWorkOrder"}
    s = sc.post("/api/kinetic/systems/mock-cmms/refresh", headers=h).json()  # 수동 등록분 유지
    assert s["operations_count"] == 4
    assert sc.delete("/api/kinetic/systems/mock-cmms/operations/createWorkOrder", headers=h).status_code == 409
    assert sc.delete("/api/kinetic/systems/mock-cmms/operations/getWorkOrder", headers=h).json() == {"deleted": True}
    assert sc.get("/api/kinetic/systems/mock-cmms", headers=h).json()["operations_count"] == 3
    # health (직접 모드)
    ok = sc.get("/api/kinetic/systems/mock-aps/health", headers=auth(**OP1)).json()
    assert ok["ok"] and ok["http_status"] == 200 and isinstance(ok["latency_ms"], int) and ok["checked_at"]
    systems.down = {"aps.test"}
    down = sc.get("/api/kinetic/systems/mock-aps/health", headers=auth(**OP1)).json()
    assert not down["ok"] and down["http_status"] == 503
    # 다시 등록해도 수동 등록분·created_at 유지
    sc.post("/api/kinetic/systems/mock-cmms/operations", headers=h,
            json={"operation_id": "ping", "method": "GET", "path": "/ping"})
    created = sc.get("/api/kinetic/systems/mock-cmms", headers=h).json()["created_at"]
    again = sc.post("/api/kinetic/systems", headers=h, json={"name": "mock-cmms", "base_url": "http://cmms.test",
                                                              "openapi_url": "http://cmms.test/openapi.json"}).json()
    assert again["operations_count"] == 4 and again["created_at"] == created
    # 삭제 — 쓰는 액션 목록을 알려 준다
    d = sc.delete("/api/kinetic/systems/mock-aps", headers=h).json()
    assert d == {"deleted": True, "used_by": ["Equipment.setMaintenanceMode"]}
    assert sc.get("/api/kinetic/systems/mock-aps", headers=h).status_code == 404
    assert sc.post("/api/kinetic/systems", headers=h, json={"name": "routes", "base_url": "http://x"}).status_code == 422
    p = sc.post("/api/kinetic/plans/by-ids", headers=auth(**OP1),
                json={"class": "Equipment", "action": "setMaintenanceMode", "ids": ["EQ-101"], "params": {"reason": "x"}})
    assert p.status_code == 404  # 단계 시스템이 없으면 plan 불가


def test_store_migrates_old_systems_table(tmp_path):
    url = f"sqlite:///{tmp_path}/old.db"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE kinetic_systems (name VARCHAR(100) PRIMARY KEY, base_url TEXT NOT NULL, "
                       "openapi TEXT NOT NULL, auth_kind VARCHAR(20) NOT NULL, auth_header VARCHAR(100), "
                       "auth_secret_env VARCHAR(100), timeout_ms INTEGER NOT NULL, created_at VARCHAR(40) NOT NULL)"))
        c.execute(text("INSERT INTO kinetic_systems VALUES ('mock-mes','http://m','{}','none',NULL,NULL,5000,'t0')"))
    store = Store(url)
    row = store.get_system("mock-mes")
    assert row["base_url"] == "http://m" and row["manual_ops"] is None and "health_path" in row
    Store(url)  # 두 번째 시작도 문제없음


# ── MCP ──

def test_mcp_compensate_run(sc, systems):
    from test_mcp import call
    _, run = run_ids(sc, ["EQ-101", "EQ-102"])
    err, body = call(sc, auth("v", ["viewer"]), "compensate_run", {"run_id": run["id"]})
    assert err and body["error"]["code"] == "not_plan_owner"
    err, body = call(sc, auth(**OP1), "compensate_run", {"run_id": run["id"], "reason": "되돌려 줘"})
    assert not err and body["status"] == "compensated" and len(body["compensations"]) == 6
    assert body["cancel"]["reason"] == "되돌려 줘"
    err, body = call(sc, auth(**OP1), "compensate_run", {"run_id": "run_nope"})
    assert err and body["error"]["code"] == "not_found"
