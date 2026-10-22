import json
from datetime import datetime, timedelta, timezone

from conftest import ACTION, SECRET, auth

OP1 = dict(sub="op1", roles=["plant_operator"], plant="P1")
APPROVER = dict(sub="boss", roles=["kinetic_approver"])
HOT = [{"prop": "temp", "op": ">", "value": 80}]
PARAMS = {"reason": "과열"}


def plan(client, where=HOT, who=OP1, **extra):
    return client.post("/api/kinetic/plans", headers=auth(**who),
                       json={"class": "Equipment", "action": "setMaintenanceMode", "where": where,
                             "params": PARAMS, **extra})


def test_401_has_resource_metadata(client):
    for r in (client.get("/api/kinetic/actions"), client.post("/mcp", json={})):
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthenticated"
        assert 'resource_metadata="http://kinetic.test/.well-known/oauth-protected-resource"' in r.headers["www-authenticate"]
    bad = client.get("/api/kinetic/actions", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401
    meta = client.get("/.well-known/oauth-protected-resource").json()
    assert meta["resource"] == "http://kinetic.test" and meta["bearer_methods_supported"] == ["header"]


def test_list_actions_filtering(client):
    r = client.get("/api/kinetic/actions", headers=auth(**OP1))
    assert [a["action"] for a in r.json()] == ["setMaintenanceMode"]
    assert client.get("/api/kinetic/actions?class=Plant", headers=auth(**OP1)).json() == []
    assert client.get("/api/kinetic/actions", headers=auth("v", ["viewer"])).json() == []


def test_routes_requires_internal_header(client):
    assert client.get("/api/kinetic/systems/routes").status_code == 403
    assert client.get("/api/kinetic/systems/routes", headers={"X-Kinetic-Internal": "wrong"}).status_code == 403
    r = client.get("/api/kinetic/systems/routes", headers={"X-Kinetic-Internal": SECRET})
    assert r.json() == [{"id": "svc-mock-mes", "system": "mock-mes", "path_prefix": "/svc/mock-mes",
                         "uri": "http://mes.test", "auth_header": None, "auth_value_env": None, "timeout_ms": 10000,
                         "auth_kind": "none", "auth_query_param": None, "basic_env": None, "oauth2": None, "login_token": None,
                         "retries": 2}]


def test_registry_admin_only_and_operations(client):
    r = client.post("/api/kinetic/systems", headers=auth(**OP1), json={"name": "x", "base_url": "http://x"})
    assert r.status_code == 403
    ops = client.get("/api/kinetic/systems/mock-mes/operations", headers=auth(**OP1)).json()
    assert ops[0]["operation_id"] == "setEquipmentStatus" and ops[0]["method"] == "POST"
    assert ops[0]["request_body_schema"]["properties"]["status"]["type"] == "string"  # $ref 펼침
    systems = client.get("/api/kinetic/systems", headers=auth(**OP1)).json()
    assert systems[0]["operations_count"] == 1 and "openapi" not in systems[0]


def test_plan_allowed_denied_and_approval_gate(client, svc):
    p = plan(client).json()
    assert sorted(t["key"] for t in p["allowed"]) == ["EQ-101", "EQ-102", "EQ-104", "EQ-105"]
    assert [t["key"] for t in p["denied"]] == ["EQ-201"] and p["denied"][0]["reason"]
    assert p["requires_approval"] and p["status"] == "awaiting_approval"  # 4 > 3
    call = p["preview"][0]
    assert call["url"].startswith("http://mes.test/equipment/") and call["body"]["requestedBy"] == "op1"
    assert "X-Kinetic-Internal" not in call["headers"]
    r = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1))
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_required"
    assert client.post(f"/api/kinetic/plans/{p['id']}/approve", headers=auth(**OP1)).status_code == 403
    a = client.post(f"/api/kinetic/plans/{p['id']}/approve", headers=auth(**APPROVER), json={"note": "ok"}).json()
    assert a["status"] == "approved"
    run = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1)).json()
    assert run["status"] == "succeeded" and len(svc.calls) == 4
    h = svc.calls[0]["headers"]
    assert h["x-kinetic-internal"] == SECRET and h["x-kinetic-run"] == run["id"]
    assert h["idempotency-key"].startswith(p["id"] + ":")
    assert client.get(f"/api/kinetic/plans/{p['id']}", headers=auth(**OP1)).json()["status"] == "executed"


def test_execute_without_approval_under_threshold_and_writeback(client, svc, graph):
    p = plan(client, where=[{"prop": "code", "op": "in", "value": ["EQ-101", "EQ-201"]}]).json()
    assert p["status"] == "planned" and not p["requires_approval"]
    run = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1)).json()
    assert run["status"] == "succeeded" and [t["key"] for t in run["targets"]] == ["EQ-101"]
    assert graph.writes == [("Equipment", "EQ-101", "status", "MAINTENANCE")]


def test_owner_check(client):
    p = plan(client, where=[{"prop": "code", "op": "=", "value": "EQ-101"}]).json()
    r = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth("op2", ["plant_operator"], plant="P1"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_plan_owner"


def test_plan_ttl(client):
    p = plan(client, where=[{"prop": "code", "op": "=", "value": "EQ-101"}]).json()
    store = client.app_state.service.store
    doc = store.get_plan(p["id"])
    doc["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    store.save_plan(doc)
    r = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1))
    assert r.status_code == 409 and r.json()["error"]["code"] == "plan_expired"
    assert client.get(f"/api/kinetic/plans/{p['id']}", headers=auth(**OP1)).json()["status"] == "expired"


def test_reevaluation_skips_target_that_lost_policy(client, graph, svc):
    p = plan(client, where=[{"prop": "code", "op": "in", "value": ["EQ-101", "EQ-102"]}]).json()
    assert len(p["allowed"]) == 2
    graph.nodes["Equipment"][1]["plant"] = "P2"  # EQ-102 가 다른 공장으로 이관됨
    run = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1)).json()
    by = {t["key"]: t for t in run["targets"]}
    assert by["EQ-101"]["status"] == "succeeded"
    assert by["EQ-102"]["status"] == "skipped" and "재평가" in by["EQ-102"]["error"]
    assert len(svc.calls) == 1


def test_idempotent_reexecute(client, svc):
    p = plan(client, where=[{"prop": "code", "op": "=", "value": "EQ-101"}]).json()
    r1 = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1)).json()
    r2 = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1)).json()
    assert r1["id"] == r2["id"] and len(svc.calls) == 1


def test_retry_then_dead(client, svc):
    p = plan(client, where=[{"prop": "code", "op": "in", "value": ["EQ-101", "EQ-102"]}]).json()
    svc.fail = {"EQ-102"}
    run = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1)).json()
    assert run["status"] == "partial"
    run = client.post(f"/api/kinetic/runs/{run['id']}/retry", headers=auth(**OP1)).json()
    assert {t["key"]: t["status"] for t in run["targets"]}["EQ-102"] == "failed"
    run = client.post(f"/api/kinetic/runs/{run['id']}/retry", headers=auth(**OP1)).json()
    t = {t["key"]: t for t in run["targets"]}["EQ-102"]
    assert t["status"] == "dead" and t["attempts"] == 3 and run["status"] == "partial"
    n = len(svc.calls)
    client.post(f"/api/kinetic/runs/{run['id']}/retry", headers=auth(**OP1))
    assert len(svc.calls) == n  # dead 는 더 시도하지 않는다
    # 재시도마다 새 시도 번호 (계약 §1.3 `<plan>:<target>:<step>:a<n>`)
    keys = {c["headers"]["idempotency-key"] for c in svc.calls if "EQ-102" in c["url"]}
    assert keys == {f"{p['id']}:EQ-102:main:a{n}" for n in (1, 2, 3)}


def test_retry_recovers(client, svc):
    p = plan(client, where=[{"prop": "code", "op": "=", "value": "EQ-101"}]).json()
    svc.fail = {"EQ-101"}
    run = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1)).json()
    assert run["status"] == "failed"
    svc.fail = set()
    run = client.post(f"/api/kinetic/runs/{run['id']}/retry", headers=auth(**OP1)).json()
    assert run["status"] == "succeeded" and run["targets"][0]["attempts"] == 2


def test_errors(client):
    r = plan(client, where=[{"prop": "temp`) DELETE n", "op": "=", "value": 1}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_filter"
    r = client.post("/api/kinetic/plans", headers=auth(**OP1),
                    json={"class": "Equipment", "action": "setMaintenanceMode", "where": HOT, "params": {}})
    assert r.json()["error"]["code"] == "invalid_params"
    r = client.post("/api/kinetic/plans", headers=auth(**OP1), json={"class": "Nope", "action": "x"})
    assert r.status_code == 404
    r = client.post("/api/kinetic/plans", headers=auth("v", ["viewer"]),
                    json={"class": "Equipment", "action": "setMaintenanceMode", "params": PARAMS})
    assert r.status_code == 403


def test_too_many_targets(client, graph):
    graph.actions[0] = {**ACTION, "max_targets": 2}
    client.post("/api/kinetic/catalog/refresh", headers=auth(**OP1))
    r = plan(client)
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_many_targets"


def test_by_ids_and_threshold_zero(client, graph):
    graph.actions[0] = {**ACTION, "confirm_threshold": 0}
    assert client.post("/api/kinetic/catalog/refresh", headers=auth(**OP1)).json() == {"actions": 1}
    r = client.post("/api/kinetic/plans/by-ids", headers=auth(**OP1),
                    json={"class": "Equipment", "action": "setMaintenanceMode", "ids": ["EQ-103"], "params": PARAMS})
    p = r.json()
    assert [t["key"] for t in p["allowed"]] == ["EQ-103"] and p["requires_approval"]


def test_catalog_refresh_adds_action(client, graph):
    graph.actions.append({**ACTION, "behavior_name": "resume", "policy": json.dumps([{"roles": []}]),
                          "arg_mapping": "[]"})
    assert client.post("/api/kinetic/catalog/refresh", headers=auth(**OP1)).json() == {"actions": 2}
    names = [a["action"] for a in client.get("/api/kinetic/actions", headers=auth("v", ["viewer"])).json()]
    assert names == ["resume"]


def test_audit_trail(client):
    p = plan(client).json()
    client.post(f"/api/kinetic/plans/{p['id']}/approve", headers=auth(**APPROVER))
    client.post(f"/api/kinetic/plans/{p['id']}/execute", headers={**auth(**OP1), "X-Request-Id": "req-1"})
    events = client.get(f"/api/kinetic/audit?plan_id={p['id']}", headers=auth(**APPROVER)).json()
    assert [e["event"] for e in events] == ["plan", "approve", "execute"]
    assert events[2]["request_id"] == "req-1" and events[1]["actor_sub"] == "boss"


def test_empty_plan_is_not_executed_and_summary_exposes_key(client, svc):
    # 레코드 id 같은 엉뚱한 값으로 대상을 지정하면 허용 0건 — 실행하지 않는다 (빈 「실패」 run 을 남기지 않는다)
    p = plan(client, where=[{"prop": "code", "op": "in", "value": ["915be3fb-d7aa-475d-afea-1b51c27d701d"]}]).json()
    assert p["allowed"] == []
    r = client.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1))
    assert r.status_code == 409 and r.json()["error"]["code"] == "nothing_to_execute" and svc.calls == []
    acts = client.get("/api/kinetic/actions", headers=auth(**OP1)).json()
    assert acts and all(a["key_property"] for a in acts)


def test_list_runs_is_per_actor_and_latest_first(client, svc):
    p1 = plan(client, where=[{"prop": "code", "op": "=", "value": "EQ-101"}]).json()
    client.post(f"/api/kinetic/plans/{p1['id']}/execute", headers=auth(**OP1))
    p2 = plan(client, where=[{"prop": "code", "op": "=", "value": "EQ-102"}]).json()
    client.post(f"/api/kinetic/plans/{p2['id']}/execute", headers=auth(**OP1))
    mine = client.get("/api/kinetic/runs", headers=auth(**OP1)).json()
    assert [r["targets"] for r in mine] == [["EQ-102"], ["EQ-101"]] and all(r["cancellable"] for r in mine)
    assert client.get("/api/kinetic/runs", headers=auth("op2", ["plant_operator"], plant="P1")).json() == []
