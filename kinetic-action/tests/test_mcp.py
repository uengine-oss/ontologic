"""MCP(stateless, JSON 응답) — tools/list 8개 고정, list_actions 는 호출자 정책으로 거른다."""

import json

from conftest import auth

H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
     "MCP-Protocol-Version": "2025-06-18"}


def rpc(client, method, params=None, who=None, path="/mcp"):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post(path, headers={**H, **(who or {})}, content=json.dumps(body))


def call(client, who, name, args):
    r = rpc(client, "tools/call", {"name": name, "arguments": args}, who)
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    return res.get("isError", False), json.loads(res["content"][0]["text"])


def test_tools_list_fixed(client):
    r = rpc(client, "tools/list", who=auth("v", ["viewer"]), path="/mcp/")
    tools = {t["name"]: t for t in r.json()["result"]["tools"]}
    assert set(tools) == {"list_actions", "plan_action", "plan_action_ids", "execute_plan", "get_plan", "get_run",
                          "list_runs", "compensate_run", "query_system"}
    assert "GET" in tools["query_system"]["description"] and "plan_action" in tools["query_system"]["description"]
    assert "되돌려" in tools["compensate_run"]["description"]
    assert "class" in tools["plan_action"]["inputSchema"]["properties"]
    assert "Studio" in tools["plan_action"]["description"]


def test_list_actions_and_plan_via_mcp(client):
    op = auth("op1", ["plant_operator"], plant="P1")
    err, items = call(client, op, "list_actions", {"class": "Equipment"})
    assert not err and [a["action"] for a in items] == ["setMaintenanceMode"]
    err, items = call(client, auth("v", ["viewer"]), "list_actions", {})
    assert items == []
    err, p = call(client, op, "plan_action", {"class": "Equipment", "action": "setMaintenanceMode",
                                              "where": [{"prop": "temp", "op": ">", "value": 80}],
                                              "params": {"reason": "과열"}})
    assert not err and p["requires_approval"] and len(p["denied"]) == 1
    err, body = call(client, op, "execute_plan", {"plan_id": p["id"]})
    assert err and body["error"]["code"] == "approval_required"
