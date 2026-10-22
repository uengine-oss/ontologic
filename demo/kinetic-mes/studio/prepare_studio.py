"""영상용 준비 — 그래프 초기화 + Studio(별도 SQLite)에 스키마·클래스·액션을 만들고 Studio 코드로 발행한다.

시드 스크립트가 직접 넣던 액션 레지스트리는 지우고, **Studio 가 발행한 액션만** 카탈로그에 남긴다.
실행은 `run_studio.sh prepare` 가 ontology-studio 루트에서 env 를 맞춰 부른다.
"""

import json
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import seed  # noqa: E402

from backend.src.modules.agent_session import session_store as ss  # noqa: E402
from backend.src.modules.ontology import publish  # noqa: E402

SCHEMA = "MES 설비 운영"


def reset_graph() -> None:
    """설비·공장 인스턴스를 처음 상태로, 발행 레지스트리는 전부 비운다."""
    seed.seed_graph()
    with seed.driver() as d, d.session() as s:
        s.run("MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH '_Ontology') DETACH DELETE n").consume()
    ensure_systems()


def ensure_systems() -> list[str]:
    """세 시스템(mock-mes · mock-cmms · mock-aps) 중 레지스트리에 **없는 것만** 등록한다 (admin 토큰).

    이미 있는 시스템은 건드리지 않는다 — 시연 중 「시스템 등록」 화면에서 고친 설명·설정을 덮지 않게.
    mock-cmms 의 수동 API `getWorkOrder`(OpenAPI 에 없는 `GET /work-orders/{id}`)는 지워 둔다 —
    시연에서 「API 추가」로 직접 등록해 보이기 위해서다.
    """
    admin = seed.token("admin", ["kinetic_admin"])
    headers = {"Authorization": f"Bearer {admin}"}
    base = f"{seed.KINETIC_API}/api/kinetic"
    existing = {s["name"] for s in httpx.get(f"{base}/systems", headers=headers, timeout=20).json()}
    added = []
    for name, _, svc_base, desc in seed.SYSTEMS:
        if name in existing:
            continue
        # 인증(계약 §8)까지 담은 본문 — 인증 없이 등록하면 CMMS·APS 업무 API 가 401 을 낸다
        r = httpx.post(f"{base}/systems", headers=headers, timeout=20, json=seed.system_body(name, svc_base, desc))
        r.raise_for_status()
        added.append(name)
    httpx.delete(f"{base}/systems/mock-cmms/operations/getWorkOrder", headers=headers, timeout=20)
    return added


def define_in_studio() -> str:
    sch = ss.create_schema(SCHEMA, "공장 설비의 상태와 점검을 다루는 온톨로지",
                           intent="설비 이상 시 점검 전환을 MES·CMMS·APS 에 요청하고, 필요하면 되돌린다",
                           golden_questions=json.dumps(["온도가 80도를 넘는 설비는 어떤 것들이야?"], ensure_ascii=False))
    sid = sch["id"]
    ss.update_schema_brief(
        sid, sch["intent"], json.dumps(sch["golden_questions"], ensure_ascii=False),
        json.dumps(["온도가 80도를 넘는 설비를 점검 모드로 바꿔 줘 (사유 포함)", "방금 점검 전환을 취소해 줘"],
                   ensure_ascii=False),
    )
    ss.add_class_to_schema(sid, "Plant", "공장", json.dumps([
        {"name": "code", "type": "string", "key": True, "description": "공장 코드"},
        {"name": "name", "type": "string", "description": "공장 이름"}], ensure_ascii=False))
    ss.add_class_to_schema(sid, "Equipment", "생산 설비", json.dumps([
        {"name": "code", "type": "string", "key": True, "description": "설비 코드"},
        {"name": "name", "type": "string", "description": "설비 이름"},
        {"name": "plant", "type": "string", "description": "소속 공장 코드"},
        {"name": "temp", "type": "float", "description": "현재 온도(℃)"},
        {"name": "status", "type": "string", "description": "가동 상태 RUNNING/MAINTENANCE"}], ensure_ascii=False))
    # 계약 §1.3 의 3단계 사가 — MES 상태 변경 → CMMS 작업지시 → APS 일정 재배정, 단계마다 보상.
    # 단계 정의의 원천은 seed.MAINTENANCE_STEPS (kinetic-action 검증 스크립트와 같은 값).
    ss.upsert_class_action(
        sid, "Equipment", "setMaintenanceMode",
        steps=seed.MAINTENANCE_STEPS,
        description="설비를 점검(MAINTENANCE) 모드로 전환한다 — MES 상태 변경, CMMS 정비 작업지시, "
                    "APS 일정 재배정을 차례로 요청하고, 중간에 실패하면 앞 단계를 역순으로 되돌린다. "
                    "사유를 반드시 적는다. 운영자는 담당 공장 설비만 전환할 수 있다.",
        parameters={"type": "object", "properties": {"reason": {"type": "string", "description": "전환 사유"}},
                    "required": ["reason"]},
        key_property="code",
        effect="write", confirm_threshold=2, max_targets=20,
        policy=seed.POLICY,
        writeback_property="status",
        golden_command="온도가 80도를 넘는 설비를 점검 모드로 바꿔 줘 (사유 포함)",
    )
    return sid


if __name__ == "__main__":
    reset_graph()
    sid = define_in_studio()
    r = publish.publish(sid)
    print(json.dumps({"schema_id": sid, "status": r["status"], "counts": r.get("counts"),
                      "kinetic_refresh": r.get("kinetic_refresh")}, ensure_ascii=False))
