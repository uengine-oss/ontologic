"""시스템 등록 모델 (계약 §8) — 표시·소유 정보, 환경, 인증 종류, 스펙 입수(YAML·Swagger 2·WSDL), 연결 테스트,
어댑터 필요 시스템의 not_executable, 직접 모드 인증 주입(OAuth2 client credentials 토큰 캐시 포함)."""

from __future__ import annotations

import base64
import json
import urllib.parse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from conftest import _KEY, POLICY, SECRET, FakeGraph, auth, equipment
from app.main import create_app
from app.specs import detect_format, load_text, swagger2_to_openapi3, wsdl_operations
from app.store import Store

OP1 = dict(sub="op1", roles=["plant_operator"], plant="P1")
ADMIN = dict(sub="admin", roles=["kinetic_admin"])

SWAGGER2_YAML = """
swagger: "2.0"
info: {title: legacy erp, version: "1"}
host: erp.test
basePath: /api/v1
schemes: [http]
consumes: [application/json]
paths:
  /orders/{id}:
    parameters:
      - {name: id, in: path, required: true, type: string}
    get:
      operationId: getOrder
      summary: 주문 조회
      parameters:
        - {name: expand, in: query, type: boolean}
      responses:
        "200": {description: ok, schema: {$ref: "#/definitions/Order"}}
    post:
      operationId: updateOrder
      parameters:
        - {name: body, in: body, required: true, schema: {$ref: "#/definitions/Order"}}
      responses: {"200": {description: ok}}
  /upload:
    post:
      operationId: upload
      consumes: [application/x-www-form-urlencoded]
      parameters:
        - {name: note, in: formData, type: string, required: true}
      responses: {"200": {description: ok}}
definitions:
  Order:
    type: object
    properties:
      id: {type: string}
      qty: {type: integer}
      lines: {type: array, items: {$ref: "#/definitions/Line"}}
  Line: {type: object, properties: {sku: {type: string}}}
"""

OPENAPI_YAML = """
openapi: 3.0.3
info: {title: wms, version: "1"}
paths:
  /picks:
    post:
      operationId: createPick
      requestBody:
        content:
          application/json:
            schema: {type: object, properties: {sku: {type: string}}}
      responses: {"200": {description: ok}}
"""

WSDL = """<?xml version="1.0"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" name="SapPm">
  <wsdl:portType name="PmPort">
    <wsdl:operation name="CreateNotification"><wsdl:input message="x"/></wsdl:operation>
    <wsdl:operation name="CloseNotification"><wsdl:input message="y"/></wsdl:operation>
  </wsdl:portType>
  <wsdl:binding name="b" type="PmPort"><wsdl:operation name="CreateNotification"/></wsdl:binding>
</wsdl:definitions>"""

ECHO_SPEC = {"openapi": "3.0.3", "paths": {"/echo/{code}": {"post": {
    "operationId": "echo", "parameters": [{"name": "code", "in": "path", "required": True, "schema": {"type": "string"}}]}}}}


class Upstream:
    """가짜 하위 서비스들 + OAuth2 토큰 엔드포인트. 받은 요청을 그대로 기록한다."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.token_hits = 0
        self.token_fail = False
        self.token_forms: list[dict] = []
        self.expires_in = 3600

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        if host == "idp.test" and path == "/oauth/token":
            self.token_hits += 1
            form = dict(urllib.parse.parse_qsl(request.content.decode()))
            self.token_forms.append(form)
            if self.token_fail or form.get("client_secret") != "cs-value":
                return httpx.Response(401, json={"error": "invalid_client"})
            return httpx.Response(200, json={"access_token": f"tok-{self.token_hits}", "token_type": "Bearer",
                                             "expires_in": self.expires_in})
        if path == "/health":
            return httpx.Response(200 if host != "down.test" else 503, json={"ok": True})
        if path == "/openapi.yaml":
            return httpx.Response(200, text=SWAGGER2_YAML, headers={"content-type": "application/yaml"})
        if path == "/openapi.json":
            return httpx.Response(200, json=ECHO_SPEC)
        return httpx.Response(200, json={"code": path.rsplit("/", 1)[-1], "status": "DONE"})

    def calls(self, host: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == host and r.url.path.startswith("/echo/")]


ACTION = {
    "behavior_type": "action", "behavior_name": "touch", "class_name": "Equipment", "schema_id": "t",
    "description": "x", "key_property": "code",
    "parameters": json.dumps({"type": "object", "properties": {}}),
    "system": "sys-a", "operation_id": "echo", "arg_mapping": json.dumps({"path.code": "$this.code"}),
    "effect": "write", "confirm_threshold": 50, "max_targets": 50,
    "policy": json.dumps(POLICY, ensure_ascii=False), "writeback_property": "", "version": 1,
}
SOAP_ACTION = {**ACTION, "behavior_name": "notifySap", "system": "sap-pm", "operation_id": "CreateNotification"}


@pytest.fixture
def up():
    return Upstream()


@pytest.fixture
def env(monkeypatch):
    values = {"A_KEY": "key-value", "BASIC_CRED": "user:pa:ss", "BEARER_TOK": "bt-value", "OAUTH_SECRET": "cs-value"}
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("NOT_SET_ENV", raising=False)
    return values


def _client(tmp_path, up, *, direct=True):
    from app.config import Settings
    from conftest import ISSUER
    settings = Settings(db_url=f"sqlite:///{tmp_path}/k.db", issuer=ISSUER, internal_secret=SECRET,
                        public_base="http://kinetic.test", svc_direct=direct, catalog_refresh=3600)
    graph = FakeGraph({"Equipment": equipment()}, [ACTION, SOAP_ACTION])
    http = httpx.AsyncClient(transport=httpx.MockTransport(up.handler))
    return create_app(settings, graph=graph, http=http, key_resolver=lambda _t: _KEY.public_key(), refresh_loop=False)


@pytest.fixture
def c(tmp_path, up, env):
    with TestClient(_client(tmp_path, up)) as client:
        yield client


def reg(c, body, who=ADMIN):
    return c.post("/api/kinetic/systems", headers=auth(**who), json=body)


def run_one(c, code="EQ-101", action="touch"):
    p = c.post("/api/kinetic/plans/by-ids", headers=auth(**OP1),
               json={"class": "Equipment", "action": action, "ids": [code], "params": {}})
    if p.status_code != 200:
        return p, None
    return p, c.post(f"/api/kinetic/plans/{p.json()['id']}/execute", headers=auth(**OP1)).json()


# ── 스펙 입수 (단위) ──

def test_detect_and_convert_swagger2():
    doc, fmt = load_text(SWAGGER2_YAML)
    assert fmt == "swagger2"
    oas = swagger2_to_openapi3(doc)
    assert oas["openapi"].startswith("3") and oas["servers"] == [{"url": "http://erp.test/api/v1"}]
    get = oas["paths"]["/orders/{id}"]["get"]
    assert oas["paths"]["/orders/{id}"]["parameters"][0] == {"name": "id", "in": "path", "required": True,
                                                            "schema": {"type": "string"}}
    assert get["parameters"] == [{"name": "expand", "in": "query", "required": False, "schema": {"type": "boolean"}}]
    assert get["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/Order"}
    body = oas["paths"]["/orders/{id}"]["post"]["requestBody"]
    assert body["required"] and body["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/Order"
    assert oas["components"]["schemas"]["Order"]["properties"]["lines"]["items"] == {"$ref": "#/components/schemas/Line"}
    form = oas["paths"]["/upload"]["post"]["requestBody"]["content"]["application/x-www-form-urlencoded"]["schema"]
    assert form["properties"]["note"] == {"type": "string"} and form["required"] == ["note"]
    assert detect_format({"openapi": "3.1.0", "paths": {}}) == "openapi3"
    assert detect_format(WSDL) == "wsdl"
    assert detect_format('syntax = "proto3";\nservice Pm { rpc Create (A) returns (B); }') == "proto"
    assert detect_format("type Query { orders: [Order] }") == "graphql_sdl"
    assert detect_format('<edmx:Edmx Version="4.0"></edmx:Edmx>') == "odata_metadata"
    assert [o["operation_id"] for o in wsdl_operations(WSDL)] == ["CreateNotification", "CloseNotification"]


# ── 등록 모델 ──

def test_register_metadata_environments_and_switch(c):
    r = reg(c, {"name": "sys-a", "display_name": "설비보전 A", "owner_team": "보전팀", "contact": "pm@corp",
                "tags": ["mes", "core", "mes"], "icon": "cmms", "openapi": ECHO_SPEC, "retries": 1,
                "environments": [{"name": "dev", "base_url": "http://a-dev.test/"},
                                 {"name": "prod", "base_url": "http://a-prod.test"}],
                "active_environment": "dev"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["display_name"] == "설비보전 A" and s["owner_team"] == "보전팀" and s["contact"] == "pm@corp"
    assert s["tags"] == ["mes", "core"] and s["icon"] == "cmms" and s["protocol"] == "rest"
    assert s["spec_format"] == "openapi3" and s["executable"] and not s["adapter_required"]
    assert s["base_url"] == "http://a-dev.test" and s["active_environment"] == "dev" and s["retries"] == 1
    assert s["environments"] == [{"name": "dev", "base_url": "http://a-dev.test"},
                                 {"name": "prod", "base_url": "http://a-prod.test"}]
    assert s["auth"] == {"kind": "none"}
    # 환경 전환 = base_url 변경
    s = c.patch("/api/kinetic/systems/sys-a", headers=auth(**ADMIN), json={"active_environment": "prod"}).json()
    assert s["base_url"] == "http://a-prod.test" and s["active_environment"] == "prod"
    assert c.patch("/api/kinetic/systems/sys-a", headers=auth(**ADMIN),
                   json={"active_environment": "qa"}).json()["error"]["code"] == "invalid_params"
    # base_url 만 → 활성 환경 주소
    s = c.patch("/api/kinetic/systems/sys-a", headers=auth(**ADMIN), json={"base_url": "http://a-prod2.test"}).json()
    assert s["environments"][1] == {"name": "prod", "base_url": "http://a-prod2.test"}
    assert s["base_url"] == "http://a-prod2.test"
    # 다시 등록할 때 표시 정보를 안 주면 이전 값 유지 · 환경 없이 base_url 하나 = default
    s = reg(c, {"name": "sys-a", "base_url": "http://a.test", "openapi": ECHO_SPEC}).json()
    assert s["display_name"] == "설비보전 A" and s["environments"] == [{"name": "default", "base_url": "http://a.test"}]
    # 등록 시 environments + base_url → 같은 주소의 환경이 활성
    s = reg(c, {"name": "sys-b", "base_url": "http://b-prod.test",
                "environments": [{"name": "dev", "base_url": "http://b-dev.test"},
                                 {"name": "prod", "base_url": "http://b-prod.test"}]}).json()
    assert s["active_environment"] == "prod" and s["display_name"] == "sys-b" and s["icon"] == "generic"
    for bad in ({"environments": []}, {"environments": [{"name": "a b", "base_url": "http://x"}]},
                {"environments": [{"name": "a", "base_url": "ftp://x"}]}, {"tags": "x"}, {"icon": "Big Icon"},
                {"protocol": "corba"}, {"retries": 9}, {"spec_format": "raml"}):
        r = reg(c, {"name": "sys-c", "base_url": "http://c.test", **bad})
        assert r.status_code == 422, bad


def test_auth_kinds_validation_and_no_secret_values(c):
    h = auth(**ADMIN)
    ok = {
        "k-header": {"kind": "api_key", "secret_env": "A_KEY"},
        "k-query": {"kind": "api_key", "query_param": "apikey", "secret_env": "A_KEY"},
        "k-basic": {"kind": "basic", "secret_env": "BASIC_CRED"},
        "k-bearer": {"kind": "bearer", "secret_env": "BEARER_TOK"},
        "k-oauth": {"kind": "oauth2_client_credentials", "token_url": "http://idp.test/oauth/token",
                    "client_id": "kinetic-gateway", "client_secret_env": "OAUTH_SECRET", "scopes": ["aps.write"]},
    }
    for name, a in ok.items():
        r = reg(c, {"name": name, "base_url": f"http://{name}.test", "auth": a})
        assert r.status_code == 200, (name, r.text)
    systems = {s["name"]: s for s in c.get("/api/kinetic/systems", headers=auth(**OP1)).json()}
    assert systems["k-header"]["auth"] == {"kind": "api_key", "header": "X-API-Key", "query_param": None,
                                           "secret_env": "A_KEY"}
    assert systems["k-query"]["auth"]["query_param"] == "apikey" and systems["k-query"]["auth"]["header"] is None
    assert systems["k-basic"]["auth"] == {"kind": "basic", "header": "Authorization", "secret_env": "BASIC_CRED"}
    assert systems["k-oauth"]["auth"] == {"kind": "oauth2_client_credentials", "token_url": "http://idp.test/oauth/token",
                                          "client_id": "kinetic-gateway", "client_secret_env": "OAUTH_SECRET",
                                          "scopes": ["aps.write"]}
    dump = json.dumps(systems)
    for secret in ("key-value", "user:pa:ss", "bt-value", "cs-value"):
        assert secret not in dump
    bad = [
        {"kind": "api_key", "secret": "plain"},                         # 비밀 값을 직접
        {"kind": "api_key", "secret_env": "lower-case"},                # env 이름 아님
        {"kind": "api_key", "header": "X-K", "query_param": "k", "secret_env": "A_KEY"},
        {"kind": "basic"},                                              # secret_env 필수
        {"kind": "oauth2_client_credentials", "client_id": "x", "client_secret_env": "S"},       # token_url 없음
        {"kind": "oauth2_client_credentials", "token_url": "http://t", "client_secret_env": "S"},  # client_id 없음
        {"kind": "oauth2_client_credentials", "token_url": "http://t", "client_id": "x"},        # secret env 없음
        {"kind": "oauth2_client_credentials", "token_url": "http://t", "client_id": "x", "client_secret_env": "S",
         "client_secret": "raw"},
        {"kind": "digest"},
    ]
    for a in bad:
        r = c.post("/api/kinetic/systems", headers=h, json={"name": "k-bad", "base_url": "http://x.test", "auth": a})
        assert r.status_code == 422, a
    routes = {r["system"]: r for r in c.get("/api/kinetic/systems/routes", headers={"X-Kinetic-Internal": SECRET}).json()}
    assert routes["k-header"] | {} == {**routes["k-header"], "auth_kind": "api_key", "auth_header": "X-API-Key",
                                       "auth_value_env": "A_KEY", "auth_query_param": None}
    assert routes["k-query"]["auth_query_param"] == "apikey" and routes["k-query"]["auth_header"] is None \
        and routes["k-query"]["auth_value_env"] == "A_KEY"
    assert routes["k-basic"]["basic_env"] == "BASIC_CRED" and routes["k-basic"]["auth_value_env"] is None
    assert routes["k-bearer"]["auth_header"] == "Authorization" and routes["k-bearer"]["auth_value_env"] == "BEARER_TOK"
    assert routes["k-oauth"]["oauth2"] == {"token_url": "http://idp.test/oauth/token", "client_id": "kinetic-gateway",
                                           "client_secret_env": "OAUTH_SECRET", "scopes": ["aps.write"]}
    assert routes["k-oauth"]["auth_value_env"] is None and routes["k-oauth"]["retries"] == 2
    assert "cs-value" not in json.dumps(routes)


def test_spec_intake_yaml_swagger2_url_and_patch_upload(c):
    s = reg(c, {"name": "erp", "base_url": "http://erp.test", "openapi_text": SWAGGER2_YAML}).json()
    assert s["spec_format"] == "swagger2" and s["operations_count"] == 3 and s["protocol"] == "rest"
    ops = {o["operation_id"]: o for o in c.get("/api/kinetic/systems/erp/operations", headers=auth(**OP1)).json()}
    assert ops["getOrder"]["path"] == "/api/v1/orders/{id}" and ops["getOrder"]["method"] == "GET"  # basePath 반영
    assert [p["name"] for p in ops["getOrder"]["parameters"]] == ["id", "expand"]
    assert ops["updateOrder"]["request_body_schema"]["properties"]["lines"]["items"]["properties"]["sku"] == {"type": "string"}
    # base_url 이 basePath 를 이미 담고 있으면 두 번 붙이지 않는다
    s = reg(c, {"name": "erp2", "base_url": "http://erp.test/api/v1", "openapi_url": "http://erp.test/openapi.yaml"}).json()
    assert s["spec_format"] == "swagger2" and s["openapi_url"] == "http://erp.test/openapi.yaml"
    ops2 = {o["operation_id"]: o["path"] for o in c.get("/api/kinetic/systems/erp2/operations", headers=auth(**OP1)).json()}
    assert ops2["getOrder"] == "/orders/{id}"
    assert c.post("/api/kinetic/systems/erp2/refresh", headers=auth(**ADMIN)).json()["operations_count"] == 3
    # OpenAPI 3 YAML
    s = reg(c, {"name": "wms", "base_url": "http://wms.test", "openapi_text": OPENAPI_YAML}).json()
    assert s["spec_format"] == "openapi3" and s["operations_count"] == 1
    # PATCH 로 스펙 업로드 교체
    s = c.patch("/api/kinetic/systems/wms", headers=auth(**ADMIN), json={"openapi_text": json.dumps(ECHO_SPEC)}).json()
    assert s["operations_count"] == 1 and c.get("/api/kinetic/systems/wms/operations",
                                                headers=auth(**OP1)).json()[0]["operation_id"] == "echo"
    for bad in ("{not json: [", "just a string", "- a\n- b"):
        assert reg(c, {"name": "bad", "base_url": "http://b.test", "openapi_text": bad}).status_code == 422


def test_soap_registers_adapter_required_and_plan_not_executable(c):
    s = reg(c, {"name": "sap-pm", "display_name": "SAP PM", "base_url": "http://sap.test/sap/bc/srt",
                "openapi_text": WSDL, "icon": "sap"}).json()
    assert s["protocol"] == "soap" and s["spec_format"] == "wsdl"
    assert s["executable"] is False and s["adapter_required"] is True and s["operations_count"] == 2
    ops = c.get("/api/kinetic/systems/sap-pm/operations", headers=auth(**OP1)).json()
    assert {o["source"] for o in ops} == {"wsdl"}
    routes = c.get("/api/kinetic/systems/routes", headers={"X-Kinetic-Internal": SECRET}).json()
    assert "sap-pm" not in [r["system"] for r in routes]  # 게이트웨이는 어댑터 없는 시스템을 라우팅하지 않는다
    p, _ = run_one(c, action="notifySap")
    assert p.status_code == 422 and p.json()["error"]["code"] == "not_executable"
    # 명시 protocol (grpc·db_procedure) 은 http 아닌 주소도 받는다
    g = reg(c, {"name": "mes-grpc", "protocol": "grpc", "base_url": "grpc://mes:50051"}).json()
    assert g["adapter_required"] and g["base_url"] == "grpc://mes:50051"
    d = reg(c, {"name": "erp-db", "protocol": "db_procedure", "base_url": "jdbc:oracle:thin:@db:1521/ERP"}).json()
    assert d["protocol"] == "db_procedure" and not d["executable"]
    # odata 는 rest 처럼 실행 가능
    o = reg(c, {"name": "sys-a", "protocol": "odata", "base_url": "http://a.test", "openapi": ECHO_SPEC}).json()
    assert o["executable"] and o["protocol"] == "odata"
    p, run = run_one(c)
    assert p.status_code == 200 and run["status"] == "succeeded"


def test_systems_test_endpoint(c, up):
    h = auth(**ADMIN)
    assert c.post("/api/kinetic/systems/test", headers=auth(**OP1), json={"name": "x"}).status_code == 403
    r = c.post("/api/kinetic/systems/test", headers=h, json={
        "name": "erp", "base_url": "http://erp.test", "openapi_text": SWAGGER2_YAML,
        "auth": {"kind": "oauth2_client_credentials", "token_url": "http://idp.test/oauth/token", "client_id": "c",
                 "client_secret_env": "OAUTH_SECRET"}}).json()
    assert r["spec"] == {"ok": True, "format": "swagger2", "operations": 3,
                         "operation_ids": ["getOrder", "updateOrder", "upload"]}
    assert r["health"]["ok"] and r["health"]["http_status"] == 200 and isinstance(r["health"]["latency_ms"], int)
    assert r["health"]["url"] == "http://erp.test/health"
    assert r["auth"]["ok"] and r["auth"]["missing_env"] == [] and r["auth"]["required_env"] == ["OAUTH_SECRET"]
    assert r["ok"] and r["executable"] and up.token_hits == 0  # 값을 쓰지 않는다 — 토큰 요청도 없음
    assert "cs-value" not in json.dumps(r)
    r = c.post("/api/kinetic/systems/test", headers=h, json={
        "name": "down", "base_url": "http://down.test", "openapi_text": "{broken",
        "auth": {"kind": "api_key", "secret_env": "NOT_SET_ENV"}}).json()
    assert not r["spec"]["ok"] and r["spec"]["error"] and not r["health"]["ok"] and r["health"]["http_status"] == 503
    assert r["auth"] == {"ok": False, "kind": "api_key", "required_env": ["NOT_SET_ENV"], "missing_env": ["NOT_SET_ENV"],
                         "checked_in": "kinetic-action", "injected_by": "kinetic-action"}
    assert r["ok"] is False
    r = c.post("/api/kinetic/systems/test", headers=h, json={"name": "sap", "base_url": "http://sap.test",
                                                              "openapi_text": WSDL}).json()
    assert r["spec"]["format"] == "wsdl" and r["spec"]["operations"] == 2 and r["adapter_required"]
    assert c.get("/api/kinetic/systems", headers=h).json() == []  # 저장하지 않는다


# ── 직접 모드 인증 주입 ──

@pytest.mark.parametrize("auth_cfg,check", [
    ({"kind": "api_key", "secret_env": "A_KEY"}, lambda r: r.headers["x-api-key"] == "key-value"),
    ({"kind": "api_key", "header": "X-Corp-Key", "secret_env": "A_KEY"},
     lambda r: r.headers["x-corp-key"] == "key-value"),
    ({"kind": "api_key", "query_param": "apikey", "secret_env": "A_KEY"},
     lambda r: r.url.params["apikey"] == "key-value" and "x-api-key" not in r.headers),
    ({"kind": "basic", "secret_env": "BASIC_CRED"},
     lambda r: r.headers["authorization"] == "Basic " + base64.b64encode(b"user:pa:ss").decode()),
    ({"kind": "bearer", "secret_env": "BEARER_TOK"}, lambda r: r.headers["authorization"] == "Bearer bt-value"),
])
def test_direct_mode_injects_auth(c, up, auth_cfg, check):
    reg(c, {"name": "sys-a", "base_url": "http://a.test", "openapi": ECHO_SPEC, "auth": auth_cfg})
    _, run = run_one(c)
    assert run["status"] == "succeeded"
    (req,) = up.calls("a.test")
    assert check(req)
    stored = c.get(f"/api/kinetic/runs/{run['id']}", headers=auth(**OP1)).text
    assert "key-value" not in stored and "bt-value" not in stored


def test_direct_mode_oauth2_token_cached_and_failure(c, up):
    reg(c, {"name": "sys-a", "base_url": "http://a.test", "openapi": ECHO_SPEC,
            "auth": {"kind": "oauth2_client_credentials", "token_url": "http://idp.test/oauth/token",
                     "client_id": "kinetic-gateway", "client_secret_env": "OAUTH_SECRET", "scopes": ["aps.write", "x"]}})
    p = c.post("/api/kinetic/plans", headers=auth(**OP1),
               json={"class": "Equipment", "action": "touch", "where": [{"prop": "plant", "op": "=", "value": "P1"}],
                     "params": {}}).json()
    run = c.post(f"/api/kinetic/plans/{p['id']}/execute", headers=auth(**OP1)).json()
    assert run["status"] == "succeeded" and len(up.calls("a.test")) == 5
    assert up.token_hits == 1  # 5 대상 = 토큰 1번
    assert up.token_forms[0] == {"grant_type": "client_credentials", "client_id": "kinetic-gateway",
                                 "client_secret": "cs-value", "scope": "aps.write x"}
    assert {r.headers["authorization"] for r in up.calls("a.test")} == {"Bearer tok-1"}
    _, run2 = run_one(c, "EQ-102")
    assert run2["status"] == "succeeded" and up.token_hits == 1  # 캐시
    # health 도 같은 토큰
    assert c.get("/api/kinetic/systems/sys-a/health", headers=auth(**OP1)).json()["ok"] and up.token_hits == 1
    # 만료 60초 이내로 받은 토큰은 캐시하지 않는다(매번 갱신) + 토큰 엔드포인트 실패 → 대상 failed(auth_unavailable)
    state = c.app.state.service.dispatcher.auth
    state._tokens.clear()
    up.token_fail = True
    _, run3 = run_one(c, "EQ-104")
    t = run3["targets"][0]
    assert run3["status"] == "failed" and t["status"] == "failed" and "auth_unavailable" in t["error"]
    assert len(up.calls("a.test")) == 6  # 하위 서비스는 불리지 않았다
    up.token_fail, up.expires_in = False, 30
    run_one(c, "EQ-105")
    hits = up.token_hits
    run_one(c, "EQ-101")
    assert up.token_hits == hits + 1


def test_gateway_mode_does_not_inject_system_auth(tmp_path, up, env):
    with TestClient(_client(tmp_path, up, direct=False)) as c:
        reg(c, {"name": "sys-a", "base_url": "http://a.test", "openapi": ECHO_SPEC,
                "auth": {"kind": "oauth2_client_credentials", "token_url": "http://idp.test/oauth/token",
                         "client_id": "c", "client_secret_env": "OAUTH_SECRET"}})
        _, run = run_one(c)
        req = [r for r in up.requests if r.url.path.startswith("/svc/sys-a/echo/")]
        assert len(req) == 1 and "authorization" not in req[0].headers and up.token_hits == 0
        assert req[0].headers["x-kinetic-internal"] == SECRET
        r = c.post("/api/kinetic/systems/test", headers=auth(**ADMIN),
                   json={"name": "sys-a", "base_url": "http://a.test", "auth": {"kind": "bearer", "secret_env": "BEARER_TOK"}})
        assert r.json()["auth"]["injected_by"] == "api-gateway"


def test_store_migrates_pre_registration_model_table(tmp_path):
    url = f"sqlite:///{tmp_path}/old.db"
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE kinetic_systems (name VARCHAR(100) PRIMARY KEY, base_url TEXT NOT NULL, "
                          "openapi TEXT NOT NULL, auth_kind VARCHAR(20) NOT NULL, auth_header VARCHAR(100), "
                          "auth_secret_env VARCHAR(100), timeout_ms INTEGER NOT NULL, created_at VARCHAR(40) NOT NULL, "
                          "description TEXT, openapi_url TEXT, health_path VARCHAR(200), manual_ops TEXT, "
                          "updated_at VARCHAR(40))"))
        conn.execute(text("INSERT INTO kinetic_systems VALUES ('mock-mes','http://m','{}','api_key','X-API-Key',"
                          "'MES_KEY',5000,'t0','d',NULL,'/health','[]','t0')"))
    store = Store(url)
    row = store.get_system("mock-mes")
    assert row["base_url"] == "http://m" and row["protocol"] is None and row["environments"] is None
    from app.registry import _public
    pub = _public(row)
    assert pub["protocol"] == "rest" and pub["executable"] and pub["environments"] == [{"name": "default",
                                                                                         "base_url": "http://m"}]
    assert pub["auth"] == {"kind": "api_key", "header": "X-API-Key", "query_param": None, "secret_env": "MES_KEY"}
    Store(url)
