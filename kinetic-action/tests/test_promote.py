"""기존 시스템 승격 (계약 §9) — login_token 인증, 조회 경로 `POST /systems/{name}/query`, 배열 인자 매핑."""

from __future__ import annotations

import base64
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import _KEY, POLICY, SECRET, FakeGraph, auth, equipment
from app.config import Settings
from app.main import create_app
from app.mapping import build_call
from app.errors import KineticError
from app.sysauth import jwt_exp

ADMIN = dict(sub="admin", roles=["kinetic_admin"])
OP1 = dict(sub="op1", roles=["plant_operator"], plant="P1")
VIEWER = dict(sub="viewer", roles=[])


def fake_jwt(exp: float | None, n: int) -> str:
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    payload = {"sub": "guest", "n": n, **({"exp": int(exp)} if exp is not None else {})}
    return f"{b64({'alg': 'HS256'})}.{b64(payload)}.sig"


ERP_SPEC = {"openapi": "3.0.1", "paths": {
    "/api/mold/views/{model}": {"get": {"operationId": "moldListView", "parameters": [
        {"name": "model", "in": "path", "required": True, "schema": {"type": "string"}},
        {"name": "size", "in": "query", "schema": {"type": "integer"}}]}},
    "/api/mold/page": {"get": {"operationId": "moldPage"}},
    "/api/text": {"get": {"operationId": "plainText"}},
    "/api/orders": {"post": {"operationId": "createOrder"}},
}}


class Erp:
    """가짜 PriMES — JSON 로그인으로 토큰을 주고, 그 토큰만 받는다."""

    def __init__(self):
        self.logins: list[dict] = []
        self.calls: list[httpx.Request] = []
        self.valid: set[str] = set()
        self.exp_in: float | None = 3600
        self.plain_token = False
        self.login_status = 200
        self.items = 3
        self.reject_all = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/auth/login":
            body = json.loads(request.content)
            self.logins.append(body)
            if self.login_status != 200 or body.get("password") != "pw-value":
                return httpx.Response(self.login_status if self.login_status != 200 else 401,
                                      json={"message": "bad credentials"})
            n = len(self.logins)
            tok = f"opaque-{n}" if self.plain_token else fake_jwt(
                None if self.exp_in is None else time.time() + self.exp_in, n)
            self.valid.add(tok)
            return httpx.Response(200, json={"token": tok, "user": {"loginId": body.get("loginId")}})
        self.calls.append(request)
        tok = (request.headers.get("authorization") or "")[len("Bearer "):]
        if path.startswith("/svc/"):
            tok = "gateway"  # 게이트웨이 모드: 인증은 게이트웨이 몫
        elif tok not in self.valid or self.reject_all:
            return httpx.Response(401, json={"message": "expired"})
        if path.startswith("/svc/erp/api/mold/views/") or path.startswith("/api/mold/views/"):
            return httpx.Response(200, json=[{"moldCode": f"FM540-{i}", "shots": 100 * i} for i in range(1, self.items + 1)])
        if path.endswith("/api/mold/page"):
            return httpx.Response(200, json={"content": [{"i": i} for i in range(self.items)], "totalElements": self.items})
        if path.endswith("/api/text"):
            return httpx.Response(200, text="hello")
        if path.endswith("/api/orders"):
            return httpx.Response(200, json={"id": "WO-1", "body": json.loads(request.content or b"null")})
        return httpx.Response(404, json={})


LOGIN_AUTH = {"kind": "login_token", "token_url": "http://erp.test/api/auth/login", "login_body": {"tenant": "standard"},
              "username_env": "ERP_LOGIN_ID", "password_env": "ERP_PASSWORD", "token_path": "token"}

ARRAY_ACTION = {
    "behavior_type": "action", "behavior_name": "createOrder", "class_name": "Equipment", "schema_id": "t",
    "description": "x", "key_property": "code",
    "parameters": json.dumps({"type": "object", "properties": {"qty": {"type": "integer"}}}),
    "system": "erp", "operation_id": "createOrder",
    "arg_mapping": json.dumps({"body.lines.0.productCode": "$this.code", "body.lines.0.qty": "$params.qty",
                               "body.lines.1.productCode": "SPARE", "body.processes.1.equipmentCode": "$this.code"}),
    "effect": "write", "confirm_threshold": 50, "max_targets": 50,
    "policy": json.dumps(POLICY, ensure_ascii=False), "writeback_property": "", "version": 1,
}


@pytest.fixture
def erp():
    return Erp()


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ERP_LOGIN_ID", "guest")
    monkeypatch.setenv("ERP_PASSWORD", "pw-value")


def make(tmp_path, erp, *, direct=True, max_items=500, actions=()):
    settings = Settings(db_url=f"sqlite:///{tmp_path}/k.db", issuer="http://idp.test", internal_secret=SECRET,
                        public_base="http://kinetic.test", svc_direct=direct, catalog_refresh=3600,
                        svc_base="http://gw.test/svc", query_max_items=max_items)
    graph = FakeGraph({"Equipment": equipment()}, list(actions))
    http = httpx.AsyncClient(transport=httpx.MockTransport(erp.handler))
    return create_app(settings, graph=graph, http=http, key_resolver=lambda _t: _KEY.public_key(), refresh_loop=False)


@pytest.fixture
def c(tmp_path, erp, env):
    with TestClient(make(tmp_path, erp, actions=[ARRAY_ACTION])) as client:
        r = client.post("/api/kinetic/systems", headers=auth(**ADMIN),
                        json={"name": "erp", "base_url": "http://erp.test", "openapi": ERP_SPEC, "auth": LOGIN_AUTH})
        assert r.status_code == 200, r.text
        yield client


def q(c, body, who=OP1, name="erp"):
    return c.post(f"/api/kinetic/systems/{name}/query", headers=auth(**who), json=body)


# ── 9.1 login_token 등록 ──

def test_login_token_registration_public_and_route(c):
    h = auth(**ADMIN)
    s = c.get("/api/kinetic/systems/erp", headers=h).json()
    assert s["auth"] == {"kind": "login_token", "token_url": "http://erp.test/api/auth/login",
                         "login_body": {"tenant": "standard"}, "username_field": "loginId", "username_env": "ERP_LOGIN_ID",
                         "password_field": "password", "password_env": "ERP_PASSWORD", "token_path": "token",
                         "header": "Authorization", "scheme": "Bearer", "ttl_seconds": 1800}
    (route,) = c.get("/api/kinetic/systems/routes", headers={"X-Kinetic-Internal": SECRET}).json()
    assert route["auth_kind"] == "login_token" and route["auth_header"] is None and route["oauth2"] is None
    assert route["login_token"] == {k: v for k, v in s["auth"].items() if k != "kind"}
    assert "pw-value" not in json.dumps(route) and "guest" not in json.dumps(route)
    t = c.post("/api/kinetic/systems/test", headers=h,
               json={"name": "x", "base_url": "http://erp.test", "auth": {**LOGIN_AUTH, "password_env": "NOT_SET_ENV"}})
    assert t.json()["auth"]["required_env"] == ["ERP_LOGIN_ID", "NOT_SET_ENV"]
    assert t.json()["auth"]["missing_env"] == ["NOT_SET_ENV"]


@pytest.mark.parametrize("bad", [
    {"password": "1234"},                                   # 최상위 비밀 값
    {"login_body": {"tenant": "s", "password": "1234"}},    # login_body 안 비밀 값
    {"login_body": {"loginId": "guest"}},                   # 아이디는 env 로
    {"login_body": {"nested": {"secret": "x"}}},
    {"username_env": "guest"},                              # env 이름이 아님
    {"password_env": "1234!@#$"},
    {"token_url": "ftp://x"},
    {"token_path": "a..b"},
    {"ttl_seconds": 5},
    {"login_body": "tenant=standard"},
])
def test_login_token_validation_rejects_secrets_and_bad_fields(c, bad):
    r = c.post("/api/kinetic/systems", headers=auth(**ADMIN),
               json={"name": "erp2", "base_url": "http://erp.test", "auth": {**LOGIN_AUTH, **bad}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_params", r.text


# ── 9.1 직접 모드 로그인·캐시·갱신·401 재로그인·실패 ──

def test_direct_login_cached_and_injected(c, erp):
    for _ in range(3):
        r = q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}})
        assert r.json()["ok"], r.text
    assert len(erp.logins) == 1
    assert erp.logins[0] == {"tenant": "standard", "loginId": "guest", "password": "pw-value"}
    tokens = {r.headers["authorization"] for r in erp.calls}
    assert len(tokens) == 1 and next(iter(tokens)).startswith("Bearer ")


def test_direct_login_refreshes_by_jwt_exp_and_ttl(c, erp):
    erp.exp_in = 30  # exp 가 60초 안 → 캐시하지 않는다
    q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}})
    q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}})
    assert len(erp.logins) == 2
    tok = c.app.state.service.dispatcher.auth._tokens
    tok.clear()
    erp.exp_in = 7200
    q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}})
    (valid_until,) = [v[1] for v in tok.values()]
    assert 7200 - 60 - 5 < valid_until - time.time() <= 7200 - 60
    # JWT 가 아니면 ttl_seconds(기본 1800)
    tok.clear()
    erp.plain_token = True
    q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}})
    (valid_until,) = [v[1] for v in tok.values()]
    assert 1800 - 60 - 5 < valid_until - time.time() <= 1800 - 60
    assert jwt_exp("opaque") is None and jwt_exp(fake_jwt(123, 1)) == 123


def test_direct_401_relogins_once_and_retries(c, erp):
    q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}})
    erp.valid.clear()  # 서버가 토큰을 무효화 (재시작 등)
    r = q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}}).json()
    assert r["ok"] and r["http_status"] == 200 and len(erp.logins) == 2
    assert [x.headers["authorization"] == erp.calls[0].headers["authorization"] for x in erp.calls] == [True, True, False]
    # 재로그인 후에도 401 이면 한 번만 다시 — 그대로 401 을 돌려준다
    erp.reject_all = True
    r = q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}}).json()
    assert r["ok"] is False and r["http_status"] == 401 and len(erp.logins) == 3


def test_direct_login_failure_is_auth_unavailable(c, erp):
    erp.login_status = 500
    r = q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}}).json()
    assert r["ok"] is False and r["http_status"] is None and r["error"] == "auth_unavailable: 로그인 실패: HTTP 500"
    assert erp.calls == []  # 하위 서비스는 불리지 않았다
    assert "pw-value" not in json.dumps(r)


def test_direct_login_missing_env_is_auth_unavailable(c, erp, monkeypatch):
    monkeypatch.delenv("ERP_PASSWORD")
    r = q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}}).json()
    assert r["error"] == "auth_unavailable: 로그인 env 없음: ERP_PASSWORD" and erp.logins == []


def test_action_dispatch_array_body_with_login_token_and_relogin(c, erp):
    q(c, {"operation_id": "moldPage"})
    erp.valid.clear()  # 실행 때 401 → 재로그인 후 재시도
    p = c.post("/api/kinetic/plans/by-ids", headers=auth(**OP1),
               json={"class": "Equipment", "action": "createOrder", "ids": ["EQ-101"], "params": {"qty": 3}})
    assert p.status_code == 200, p.text
    expected = {"lines": [{"productCode": "EQ-101", "qty": 3}, {"productCode": "SPARE"}],
                "processes": [None, {"equipmentCode": "EQ-101"}]}
    assert p.json()["preview"][0]["body"] == expected  # 미리보기도 배열
    run = c.post(f"/api/kinetic/plans/{p.json()['id']}/execute", headers=auth(**OP1)).json()
    assert run["status"] == "succeeded", run
    posts = [r for r in erp.calls if r.method == "POST"]
    assert len(posts) == 2 and json.loads(posts[-1].content) == expected and len(erp.logins) == 2
    assert posts[0].headers["idempotency-key"] == posts[1].headers["idempotency-key"]
    assert "pw-value" not in c.get(f"/api/kinetic/runs/{run['id']}", headers=auth(**OP1)).text


# ── 9.2 조회 경로 ──

def test_query_get_only_with_path_and_query_params(c, erp):
    r = q(c, {"operation_id": "moldListView", "path_params": {"model": "mold/x y"}, "query": {"size": 20, "on": True}},
          who=VIEWER)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] and out["http_status"] == 200 and out["truncated"] is False and isinstance(out["latency_ms"], int)
    assert out["data"][0]["moldCode"] == "FM540-1"
    req = erp.calls[-1]
    assert req.method == "GET" and req.url.raw_path.decode() == "/api/mold/views/mold%2Fx%20y?size=20&on=true"
    assert req.headers["x-kinetic-internal"] == SECRET
    audit = c.get("/api/kinetic/audit", headers=auth(**ADMIN)).json()
    ev = [a for a in audit if a["event"] == "query"][-1]
    assert ev["actor_sub"] == "viewer" and json.loads(ev["detail"])["operation_id"] == "moldListView"
    assert json.loads(ev["detail"])["system"] == "erp"


def test_query_errors(c):
    r = q(c, {"operation_id": "createOrder"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_readonly"
    assert q(c, {"operation_id": "nope"}).json()["error"]["code"] == "not_found"
    assert q(c, {"operation_id": "moldListView"}, name="ghost").status_code == 404
    r = q(c, {"operation_id": "moldListView"})
    assert r.status_code == 422 and "model" in r.json()["error"]["message"]
    assert q(c, {"operation_id": "moldListView", "path_params": {"model": "m"}, "query": {"x": {"a": 1}}}).status_code == 422
    assert c.post("/api/kinetic/systems/erp/query", json={"operation_id": "moldListView"}).status_code == 401
    c.post("/api/kinetic/systems", headers=auth(**ADMIN),
           json={"name": "sap", "base_url": "http://sap.test", "protocol": "soap"})
    r = q(c, {"operation_id": "x"}, name="sap")
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_executable"


def test_query_truncates_arrays_and_paged_shapes(tmp_path, erp, env):
    erp.items = 7
    with TestClient(make(tmp_path, erp, max_items=5)) as c:
        c.post("/api/kinetic/systems", headers=auth(**ADMIN),
               json={"name": "erp", "base_url": "http://erp.test", "openapi": ERP_SPEC, "auth": LOGIN_AUTH})
        out = q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}}).json()
        assert out["truncated"] is True and len(out["data"]) == 5
        out = q(c, {"operation_id": "moldPage"}).json()
        assert out["truncated"] is True and len(out["data"]["content"]) == 5 and out["data"]["totalElements"] == 7
        erp.items = 2
        out = q(c, {"operation_id": "moldPage"}).json()
        assert out["truncated"] is False and len(out["data"]["content"]) == 2
        out = q(c, {"operation_id": "plainText"}).json()
        assert out["data"] == "hello" and out["truncated"] is False


def test_query_through_gateway(tmp_path, erp, env):
    with TestClient(make(tmp_path, erp, direct=False)) as c:
        c.post("/api/kinetic/systems", headers=auth(**ADMIN),
               json={"name": "erp", "base_url": "http://erp.test", "openapi": ERP_SPEC, "auth": LOGIN_AUTH})
        out = q(c, {"operation_id": "moldListView", "path_params": {"model": "mold"}, "query": {"size": 1}}).json()
        assert out["ok"], out
        req = erp.calls[-1]
        assert str(req.url) == "http://gw.test/svc/erp/api/mold/views/mold?size=1"
        assert req.headers["x-kinetic-internal"] == SECRET and "authorization" not in req.headers
        assert erp.logins == []  # 게이트웨이 모드: 로그인은 게이트웨이가


def test_operations_method_filter(c):
    ops = c.get("/api/kinetic/systems/erp/operations?method=get", headers=auth(**OP1)).json()
    assert {o["operation_id"] for o in ops} == {"moldListView", "moldPage", "plainText"}
    assert len(c.get("/api/kinetic/systems/erp/operations", headers=auth(**OP1)).json()) == 4


def test_query_system_mcp_tool(c):
    H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
         "MCP-Protocol-Version": "2025-06-18", **auth(**OP1)}
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "query_system", "arguments": {
        "system": "erp", "operation_id": "moldListView", "path_params": {"model": "mold"}}}}
    res = c.post("/mcp", headers=H, content=json.dumps(body)).json()["result"]
    assert not res.get("isError") and json.loads(res["content"][0]["text"])["data"][0]["moldCode"] == "FM540-1"
    body["params"]["arguments"] = {"system": "erp", "operation_id": "createOrder"}
    res = c.post("/mcp", headers=H, content=json.dumps(body)).json()["result"]
    assert res["isError"] and json.loads(res["content"][0]["text"])["error"]["code"] == "not_readonly"


# ── 9.3 배열 인자 매핑 (단위) ──

OP = {"method": "POST", "path": "/x/{id}"}


def test_array_mapping_builds_lists():
    call = build_call(OP, {"path.id": "1", "body.lines.0.productCode": "A", "body.lines.2.productCode": "C",
                           "body.lines.0.qty": {"$literal": 2}, "body.processes.1.equipmentCode": "$this.code",
                           "body.tags.0": "t0", "body.meta.a": "b"}, {"this": {"code": "EQ-1"}})
    assert call["body"] == {"lines": [{"productCode": "A", "qty": 2}, None, {"productCode": "C"}],
                            "processes": [None, {"equipmentCode": "EQ-1"}], "tags": ["t0"], "meta": {"a": "b"}}
    # 최상위 배열 본문
    assert build_call(OP, {"path.id": "1", "body.0.a": 1, "body.1.a": 2}, {})["body"] == [{"a": 1}, {"a": 2}]


def test_array_mapping_into_literal_does_not_mutate_catalog():
    lit = {"$literal": [{"productCode": "X"}]}
    mapping = {"path.id": "1", "body.lines": lit, "body.lines.1.productCode": "Y"}
    assert build_call(OP, mapping, {})["body"] == {"lines": [{"productCode": "X"}, {"productCode": "Y"}]}
    assert lit == {"$literal": [{"productCode": "X"}]}


@pytest.mark.parametrize("mapping", [
    {"body.lines.a": 1, "body.lines.0": 2},
    {"body.lines.0": 1, "body.lines.a": 2},
    {"body.a": 1, "body.0": 2},
    {"body.lines.5000.x": 1},
])
def test_array_mapping_conflicts_are_invalid(mapping):
    with pytest.raises(KineticError) as e:
        build_call({"method": "POST", "path": "/x"}, mapping, {})
    assert e.value.code == "invalid_params"
