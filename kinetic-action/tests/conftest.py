"""테스트 공통: RSA 키·토큰, 가짜 그래프, 가짜 마이크로서비스(httpx MockTransport)."""

from __future__ import annotations

import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.targeting import build_query, match_filter

ISSUER = "http://idp.test"
SECRET = "s3cret"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(sub="op1", roles=("plant_operator",), **claims) -> str:
    now = int(time.time())
    payload = {"sub": sub, "roles": list(roles), "iss": ISSUER, "aud": "kinetic-action",
               "iat": now, "exp": now + 3600, **claims}
    return jwt.encode(payload, _KEY, algorithm="RS256")


def auth(sub="op1", roles=("plant_operator",), **claims) -> dict:
    return {"Authorization": f"Bearer {token(sub, roles, **claims)}"}


POLICY = [{"roles": ["plant_operator"], "when": "target.plant == actor.plant", "description": "담당 공장 설비만"}]

ACTION = {
    "behavior_type": "action", "behavior_name": "setMaintenanceMode", "class_name": "Equipment",
    "schema_id": "demo", "description": "설비를 점검 모드로", "key_property": "code",
    "parameters": json.dumps({"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}),
    "system": "mock-mes", "operation_id": "setEquipmentStatus",
    "arg_mapping": json.dumps({"path.code": "$this.code", "body.status": "MAINTENANCE",
                               "body.reason": "$params.reason", "body.requestedBy": "$actor.sub"}),
    "effect": "write", "confirm_threshold": 3, "max_targets": 50,
    "policy": json.dumps(POLICY, ensure_ascii=False), "writeback_property": "status", "version": 1,
}

OPENAPI = {
    "openapi": "3.1.0", "info": {"title": "mes", "version": "1"},
    "paths": {"/equipment/{code}/status": {"post": {
        "operationId": "setEquipmentStatus", "summary": "상태 변경",
        "parameters": [{"name": "code", "in": "path", "required": True, "schema": {"type": "string"}}],
        "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Body"}}}},
    }}},
    "components": {"schemas": {"Body": {"type": "object", "properties": {"status": {"type": "string"}}}}},
}


class FakeGraph:
    """GraphReader 가짜. find 는 실제 build_query 로 검증을 거친 뒤 파이썬으로 필터한다."""

    def __init__(self, nodes: dict[str, list[dict]], actions: list[dict]):
        self.nodes = nodes
        self.actions = actions
        self.writes: list[tuple] = []

    async def load_actions(self):
        return [dict(a) for a in self.actions]

    async def find(self, label, filters, limit, *, classes, key_property=None, ids=None):
        build_query(label, filters, limit, classes=classes, key_property=key_property, ids=ids)
        out = []
        for i, n in enumerate(self.nodes.get(label, [])):
            eid = f"4:{label}:{i}"
            if all(match_filter(n, f) for f in filters):
                if ids is not None and (str(n.get(key_property)) if key_property else eid) not in ids:
                    continue
                out.append((eid, dict(n)))
        return out[:limit]

    async def set_property(self, label, key_property, key, prop, value):
        self.writes.append((label, key, prop, value))
        for n in self.nodes.get(label, []):
            if str(n.get(key_property)) == key:
                n[prop] = value


def equipment():
    return [
        {"code": "EQ-101", "plant": "P1", "temp": 85, "status": "RUNNING"},
        {"code": "EQ-102", "plant": "P1", "temp": 92, "status": "RUNNING"},
        {"code": "EQ-103", "plant": "P1", "temp": 70, "status": "RUNNING"},
        {"code": "EQ-201", "plant": "P2", "temp": 88, "status": "RUNNING"},
        {"code": "EQ-104", "plant": "P1", "temp": 81, "status": "RUNNING"},
        {"code": "EQ-105", "plant": "P1", "temp": 95, "status": "RUNNING"},
    ]


class FakeService:
    """가짜 mock-mes. Idempotency-Key 로 중복을 걸러 실제 처리 횟수를 센다."""

    def __init__(self):
        self.calls: list[dict] = []
        self.fail: set[str] = set()
        self.seen: dict[str, dict] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/openapi.json"):
            return httpx.Response(200, json=OPENAPI)
        code = request.url.path.rstrip("/").split("/")[-2]
        self.calls.append({"url": str(request.url), "headers": dict(request.headers),
                           "body": json.loads(request.content or b"null")})
        if code in self.fail:
            return httpx.Response(503, json={"detail": "down"})
        key = request.headers.get("idempotency-key")
        if key in self.seen:
            return httpx.Response(200, json=self.seen[key])
        body = json.loads(request.content)
        self.seen[key] = {"code": code, "status": body["status"]}
        return httpx.Response(200, json=self.seen[key])


@pytest.fixture
def svc():
    return FakeService()


@pytest.fixture
def graph():
    return FakeGraph({"Equipment": equipment()}, [ACTION])


@pytest.fixture
def settings(tmp_path):
    return Settings(db_url=f"sqlite:///{tmp_path}/k.db", issuer=ISSUER, internal_secret=SECRET,
                    public_base="http://kinetic.test", svc_direct=True, catalog_refresh=3600)


@pytest.fixture
def client(settings, graph, svc):
    http = httpx.AsyncClient(transport=httpx.MockTransport(svc.handler))
    app = create_app(settings, graph=graph, http=http, key_resolver=lambda _t: _KEY.public_key(),
                     refresh_loop=False)
    with TestClient(app) as c:
        r = c.post("/api/kinetic/systems", headers=auth("admin", ["kinetic_admin"]),
                   json={"name": "mock-mes", "base_url": "http://mes.test", "openapi": OPENAPI})
        assert r.status_code == 200, r.text
        c.app_state = app.state
        yield c
