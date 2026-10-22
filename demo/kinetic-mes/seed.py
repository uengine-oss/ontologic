"""데모 시드 — 그래프(인스턴스 + 발행된 액션) · mock 서비스 3개 초기화 · 서비스 등록 · 카탈로그 갱신.

`setMaintenanceMode` 는 3단계 사가다 (계약 §1.3): MES 설비 상태 MAINTENANCE → CMMS 정비 작업지시 → APS 일정 재배정.
단계마다 보상(되돌리기)이 있다 — 실패 시 자동 역순 보상, `POST /runs/{id}/compensate` 로 취소.

액션은 Studio 없이 **계약 그래프 모양 그대로** 직접 발행한다
(specs/014-kinetic-action-layer/contracts/kinetic-api.md §1). JSON 값은 문자열로 직렬화한다.
지우는 범위는 이 데모가 만든 것(`demo:'kinetic-mes'` 노드, schema_id `demo-kinetic-mes`)뿐이다.
"""

from __future__ import annotations

import json
import os

import httpx
from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("KINETIC_NEO4J_URI", "bolt://localhost:7690")
NEO4J_USER = os.environ.get("KINETIC_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("KINETIC_NEO4J_PASSWORD", "kineticdemo")
KINETIC_API = os.environ.get("KINETIC_API_URL", "http://localhost:8030").rstrip("/")
IDP = os.environ.get("DEV_IDP_URL", "http://localhost:8032").rstrip("/")
MOCK_MES = os.environ.get("MOCK_MES_URL", "http://localhost:8031").rstrip("/")
MOCK_CMMS = os.environ.get("MOCK_CMMS_URL", "http://localhost:8034").rstrip("/")
MOCK_APS = os.environ.get("MOCK_APS_URL", "http://localhost:8035").rstrip("/")
# kinetic-action(직접 모드) 또는 api-gateway(게이트웨이 모드)가 서비스에 닿는 주소 = 레지스트리 base_url.
# 기본은 호스트에서 닿는 localhost — compose 안의 kinetic-action 이 직접 부르면 http://mock-mes:8031 등으로.
MOCK_MES_FOR_KINETIC = os.environ.get("MOCK_MES_URL_FOR_KINETIC", "http://localhost:8031").rstrip("/")
MOCK_CMMS_FOR_KINETIC = os.environ.get("MOCK_CMMS_URL_FOR_KINETIC", "http://localhost:8034").rstrip("/")
MOCK_APS_FOR_KINETIC = os.environ.get("MOCK_APS_URL_FOR_KINETIC", "http://localhost:8035").rstrip("/")
SYSTEMS = [
    ("mock-mes", MOCK_MES, MOCK_MES_FOR_KINETIC, "생산관리(MES) — 설비 상태"),
    ("mock-cmms", MOCK_CMMS, MOCK_CMMS_FOR_KINETIC, "설비보전(CMMS) — 정비 작업지시"),
    ("mock-aps", MOCK_APS, MOCK_APS_FOR_KINETIC, "생산계획(APS) — 일정 재배정"),
]
# 시스템 인증 (계약 §8) — 비밀 값은 등록하지 않고 환경변수 **이름**만. 값은 게이트웨이(또는 직접 모드 kinetic-action)
# 프로세스 env 에 있다: CMMS_API_KEY (mock-cmms 의 X-API-Key), APS_CLIENT_SECRET (dev-idp client kinetic-gateway).
CMMS_API_KEY = os.environ.get("CMMS_API_KEY", "cmms-demo-key")            # verify 가 서비스를 직접 볼 때만 쓴다
APS_CLIENT_SECRET = os.environ.get("APS_CLIENT_SECRET", "aps-demo-secret")
APS_TOKEN_URL_FOR_KINETIC = os.environ.get("APS_TOKEN_URL_FOR_KINETIC", f"{IDP}/oauth/token")
SYSTEM_PROFILES = {
    "mock-mes": {"display_name": "생산관리 MES", "owner_team": "생산기술팀", "contact": "mes-ops@demo.local",
                 "icon": "mes", "tags": ["mes", "production", "demo"], "auth": {"kind": "none"}},
    "mock-cmms": {"display_name": "설비보전 CMMS", "owner_team": "설비보전팀", "contact": "cmms-ops@demo.local",
                  "icon": "cmms", "tags": ["cmms", "maintenance", "demo"],
                  "auth": {"kind": "api_key", "header": "X-API-Key", "secret_env": "CMMS_API_KEY"}},
    "mock-aps": {"display_name": "생산계획 APS", "owner_team": "생산계획팀", "contact": "aps-ops@demo.local",
                 "icon": "aps", "tags": ["aps", "planning", "demo"],
                 "auth": {"kind": "oauth2_client_credentials", "token_url": APS_TOKEN_URL_FOR_KINETIC,
                          "client_id": "kinetic-gateway", "client_secret_env": "APS_CLIENT_SECRET",
                          "scopes": ["aps.write"]}},
}
SCHEMA_ID = "demo-kinetic-mes"

EQUIPMENT = [
    ("EQ-101", "프레스 1호", "P1", 85.0), ("EQ-102", "용접 로봇 A", "P1", 92.5),
    ("EQ-103", "도장 부스", "P1", 70.0), ("EQ-104", "컨베이어 3", "P1", 81.2),
    ("EQ-105", "CNC 5축", "P1", 65.0), ("EQ-201", "프레스 2호", "P2", 88.0),
    ("EQ-202", "열처리로", "P2", 95.0), ("EQ-203", "검사기", "P2", 60.0),
]

POLICY = [{"roles": ["plant_operator"], "when": "target.plant == actor.plant", "description": "담당 공장 설비만"}]

MAINTENANCE_STEPS = [
    {"name": "mes", "title": "MES 설비 상태 변경", "system": "mock-mes", "operation_id": "setEquipmentStatus",
     "arg_mapping": {"path.code": "$this.code", "body.status": "MAINTENANCE", "body.reason": "$params.reason",
                     "body.requestedBy": "$actor.sub"},
     "compensation": {"system": "mock-mes", "operation_id": "setEquipmentStatus",
                      "arg_mapping": {"path.code": "$this.code", "body.status": "$before.status",
                                      "body.reason": "$cancel.reason", "body.requestedBy": "$actor.sub"}}},
    {"name": "cmms", "title": "정비 작업지시 생성", "system": "mock-cmms", "operation_id": "createWorkOrder",
     "arg_mapping": {"body.equipmentCode": "$this.code", "body.reason": "$params.reason",
                     "body.requestedBy": "$actor.sub"},
     "compensation": {"system": "mock-cmms", "operation_id": "cancelWorkOrder",
                      "arg_mapping": {"path.id": "$steps.cmms.response.id", "body.reason": "$cancel.reason"}}},
    {"name": "aps", "title": "생산 일정 재배정", "system": "mock-aps", "operation_id": "createReschedule",
     "arg_mapping": {"body.equipmentCode": "$this.code"},
     "compensation": {"system": "mock-aps", "operation_id": "revertReschedule",
                      "arg_mapping": {"path.id": "$steps.aps.response.id"}}},
]

MAINTENANCE_ACTION = {
    "behavior_type": "action", "behavior_name": "setMaintenanceMode", "class_name": "Equipment",
    "schema_id": SCHEMA_ID,
    "description": "설비를 점검(MAINTENANCE) 모드로 전환한다 — MES 상태 변경, CMMS 정비 작업지시, APS 일정 재배정을 "
                   "차례로 요청하고, 중간에 실패하면 앞 단계를 되돌린다. 사유(reason)를 반드시 적는다.",
    "parameters": {"type": "object", "properties": {"reason": {"type": "string", "description": "전환 사유"}},
                   "required": ["reason"]},
    "key_property": "code", "system": "mock-mes", "operation_id": "setEquipmentStatus",  # steps 가 있으면 무시(표시용)
    "arg_mapping": MAINTENANCE_STEPS[0]["arg_mapping"], "steps": MAINTENANCE_STEPS,
    "effect": "write", "confirm_threshold": 2, "max_targets": 50, "policy": POLICY,
    "compensate": "resumeOperation", "writeback_property": "status", "version": 2,
}

RESUME_ACTION = {  # 단일 단계(구 형식) 액션 — steps 없음
    **{k: v for k, v in MAINTENANCE_ACTION.items() if k != "steps"}, "behavior_name": "resumeOperation",
    "description": "점검 모드 설비를 가동(RUNNING) 상태로 되돌린다.",
    "arg_mapping": {"path.code": "$this.code", "body.status": "RUNNING", "body.reason": "$params.reason",
                    "body.requestedBy": "$actor.sub"},
    "compensate": "setMaintenanceMode", "version": 1,
}

_JSON_FIELDS = ("parameters", "arg_mapping", "policy", "steps")


def _props(action: dict) -> dict:
    return {k: json.dumps(v, ensure_ascii=False) if k in _JSON_FIELDS else v for k, v in action.items()}


def driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def publish_action(action: dict) -> None:
    """액션 하나를 계약 모양으로 발행(같은 이름이면 교체)."""
    with driver() as d, d.session() as s:
        s.run(
            "MERGE (m:_OntologyModel {schema_id:$sid}) "
            "MERGE (m)-[:HAS_CLASS]->(c:_OntologyClass {class_name:$cls}) "
            "WITH c OPTIONAL MATCH (c)-[:HAS_ACTION]->(old:_OntologyBehavior {behavior_name:$name}) DETACH DELETE old "
            "WITH DISTINCT c CREATE (c)-[:HAS_ACTION]->(a:_OntologyBehavior) SET a = $props",
            sid=action["schema_id"], cls=action["class_name"], name=action["behavior_name"], props=_props(action),
        ).consume()


def seed_graph() -> None:
    with driver() as d, d.session() as s:
        s.run("MATCH (n {demo:'kinetic-mes'}) DETACH DELETE n").consume()
        s.run("MATCH (m:_OntologyModel {schema_id:$sid}) OPTIONAL MATCH (m)-[:HAS_CLASS]->(c) "
              "OPTIONAL MATCH (c)-[:HAS_ACTION]->(a) DETACH DELETE a, c, m", sid=SCHEMA_ID).consume()
        s.run("UNWIND ['P1','P2'] AS p CREATE (:Plant {code:p, name:p + ' 공장', demo:'kinetic-mes'})").consume()
        s.run("UNWIND $rows AS r MATCH (p:Plant {code:r[2], demo:'kinetic-mes'}) "
              "CREATE (e:Equipment {code:r[0], name:r[1], plant:r[2], temp:r[3], status:'RUNNING', demo:'kinetic-mes'})"
              "-[:LOCATED_IN]->(p)", rows=[list(e) for e in EQUIPMENT]).consume()
        s.run("MERGE (m:_OntologyModel {schema_id:$sid}) SET m.name = 'kinetic MES 데모' "
              "MERGE (m)-[:HAS_CLASS]->(:_OntologyClass {class_name:'Plant'})", sid=SCHEMA_ID).consume()
    publish_action(MAINTENANCE_ACTION)


def token(sub: str, roles: list[str], **claims) -> str:
    r = httpx.post(f"{IDP}/token", json={"sub": sub, "roles": roles, **claims}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def system_body(name: str, base: str, desc: str) -> dict:
    """레지스트리 등록 본문 (계약 §8) — 표시·소유 정보, 환경(dev = 이 주소), 인증(env 이름만)."""
    return {"name": name, "base_url": base, "openapi_url": f"{base}/openapi.json", "timeout_ms": 5000,
            "description": desc, "health_path": "/health", "protocol": "rest", "retries": 2,
            "environments": [{"name": "dev", "base_url": base}], "active_environment": "dev",
            **SYSTEM_PROFILES[name]}


def register_systems() -> list[dict]:
    """세 시스템 등록 (같은 이름이면 교체 — 수동 등록 operation 은 레지스트리가 유지)."""
    admin = token("admin", ["kinetic_admin"])
    out = []
    for name, _, base, desc in SYSTEMS:
        r = httpx.post(f"{KINETIC_API}/api/kinetic/systems", headers={"Authorization": f"Bearer {admin}"}, timeout=20,
                       json=system_body(name, base, desc))
        r.raise_for_status()
        out.append(r.json())
    return out


def cmms_headers() -> dict:
    """mock-cmms 업무 API 를 (관찰용으로) 직접 볼 때의 헤더."""
    return {"X-API-Key": CMMS_API_KEY}


def aps_headers() -> dict:
    """mock-aps 업무 API 를 (관찰용으로) 직접 볼 때의 헤더 — dev-idp client credentials 토큰."""
    r = httpx.post(f"{IDP}/oauth/token", timeout=10,
                   data={"grant_type": "client_credentials", "client_id": "kinetic-gateway",
                         "client_secret": APS_CLIENT_SECRET, "scope": "aps.read"})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def register_system() -> dict:
    """하위 호환 (studio/prepare_studio.py) — 세 시스템을 등록하고 mock-mes 를 돌려준다."""
    return register_systems()[0]


def reset_services() -> None:
    for _, url, _, _ in SYSTEMS:
        httpx.post(f"{url}/admin/reset", timeout=10).raise_for_status()


def refresh_catalog() -> int:
    admin = token("admin", ["kinetic_admin"])
    r = httpx.post(f"{KINETIC_API}/api/kinetic/catalog/refresh", headers={"Authorization": f"Bearer {admin}"},
                   timeout=20)
    r.raise_for_status()
    return r.json()["actions"]


def main() -> None:
    seed_graph()
    reset_services()
    systems = register_systems()
    n = refresh_catalog()
    print(f"시드 완료: 설비 {len(EQUIPMENT)}대, 시스템 "
          + ", ".join(f"{s['name']}(operations {s['operations_count']})" for s in systems) + f", 카탈로그 액션 {n}개")


if __name__ == "__main__":
    main()
