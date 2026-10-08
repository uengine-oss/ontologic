#!/usr/bin/env python3
"""ontological-db 백엔드에서 발행·조회가 동작하는지 실측한다 (constitution 원칙 0).

원칙 0 은 "애플리케이션 코드에 저장소 분기가 없다 — 바뀌는 것은 `NEO4J_URI` 와 자격증명
뿐"이라고 말한다. 이 스크립트는 그 주장을 **같은 코드로 두 번째 백엔드를 돌려** 확인한다.

두 백엔드의 능력이 실제로 다르다는 점이 이 시험의 요점이다:

    db.labels / relationshipTypes / propertyKeys   양쪽 다 지원
    SHOW CONSTRAINTS / SHOW INDEXES                Neo4j 만 (ontological 은 SyntaxError)
    db.schema.visualization / nodeTypeProperties   Neo4j 만 (procedure 없음)
    CREATE CONSTRAINT                              양쪽 다 지원

그래서 코드가 분기하는 대신 **능력을 시도해 보고 안 되면 발행 레지스트리로 메우도록**
돼 있다. 여기서 확인하는 것은 그 대체 경로가 실제로 같은 답을 내놓는가다.

사용법:
    NEO4J_URI=bolt://localhost:7687 NEO4J_USER=dev NEO4J_PASSWORD= \
    NEO4J_DATABASE=ontologic_probe SESSION_DB_PATH=<시드된 sqlite> \
      uv run python scripts/verify_ontological_backend.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ontology-studio"))

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        failures.append(f"{label} — {detail}")
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not ok else ""))


def main() -> int:
    from backend.src.modules.agent_session import session_store
    from backend.src.modules.ontology import publish
    from backend.src.modules.ontology.tools import get_driver, session_kwargs
    from backend.src.modules.ontology_runtime import graph_schema

    print(f"URI      = {os.environ.get('NEO4J_URI')}")
    print(f"DATABASE = {os.environ.get('NEO4J_DATABASE')}  (ontological 에서는 그래프 이름)")
    print()

    # --- 0. 능력 확인 — 무엇이 다른지 먼저 기록한다 --------------------------------
    print("0. 이 백엔드가 지원하는 스키마 API")
    driver = get_driver()
    caps: dict[str, bool] = {}
    for name, query in [
        ("db.labels", "CALL db.labels() YIELD label RETURN count(label) AS c"),
        ("SHOW CONSTRAINTS", "SHOW CONSTRAINTS YIELD name RETURN count(name) AS c"),
        ("db.schema.nodeTypeProperties",
         "CALL db.schema.nodeTypeProperties() YIELD nodeLabels RETURN count(nodeLabels) AS c"),
        ("db.schema.visualization",
         "CALL db.schema.visualization() YIELD nodes RETURN count(nodes) AS c"),
    ]:
        try:
            with driver.session(**session_kwargs()) as session:
                session.run(query).single()
            caps[name] = True
        except Exception:  # noqa: BLE001
            caps[name] = False
        print(f"       {name:32} {'지원' if caps[name] else '미지원'}")
    print()

    # --- 1. 발행 -------------------------------------------------------------------
    print("1. 발행 (SQLite → 그래프)")
    schema = session_store.get_schema_by_name("제조 하이브리드")
    if not schema:
        print("   [FAIL] 시드된 스키마 그룹이 없습니다. SESSION_DB_PATH 를 확인하세요.")
        return 1

    result = publish.publish(schema["id"])
    check("발행 성공", result.get("status") == "ok", json.dumps(result, ensure_ascii=False)[:200])
    print(f"       {result['counts']}")
    check("가상 클래스 제약 생성", len(result.get("constraints_created", [])) > 0,
          str(result.get("constraints_created")))

    # --- 2. 런타임 조회 -------------------------------------------------------------
    print("\n2. 런타임 리더 (그래프만)")
    models = graph_schema.published_models()
    check("모델이 보임", len(models) == 1, str(models))

    classes = {c["class_name"]: c for c in graph_schema.list_classes()}
    check("클래스 8개 이상", len(classes) >= 8, f"{len(classes)}개")
    virtual = [c for c in classes.values() if c.get("binding_kind") == "virtual"]
    check("가상 클래스 식별됨", len(virtual) >= 3, f"{len(virtual)}개")

    # 핵심 — 인스턴스가 0건인 가상 클래스가 그래프 스키마 API 에 등재됐는가
    labels = graph_schema.graph_labels()
    check("db.labels() 가 동작", bool(labels), str(len(labels)))
    equip = "MfgDailyEquipment"
    check(f"{equip} 이 스키마 API 에 등재", equip in labels,
          f"labels={sorted(labels)[:8]}")
    check(f"{equip} 이 클래스 목록에 있음", equip in classes)

    with driver.session(**session_kwargs()) as session:
        count = session.run(f"MATCH (n:{equip}) RETURN count(n) AS c").single()["c"]
    check(f"{equip} 인스턴스 0건 (SC-001)", count == 0, f"count={count}")

    # --- 3. 바인딩 상세 (JIT 경로) ---------------------------------------------------
    print("\n3. JIT 바인딩 조회")
    binding = graph_schema.get_binding(equip)
    check("바인딩 조회됨", binding is not None)
    if binding:
        check("컬럼 매핑 보존", len(binding["column_map"]) > 5, str(len(binding["column_map"])))
        check("출처 보존", binding["table_name"] == "mfg_daily_equipment",
              binding.get("table_name", ""))

    rels = graph_schema.list_relationships()
    check("관계 보존", len(rels) >= 9, f"{len(rels)}개")

    # --- 4. 자격증명 미포함 -----------------------------------------------------------
    print("\n4. 발행물에 자격증명 없음")
    with driver.session(**session_kwargs()) as session:
        blob = json.dumps(
            # `properties()` 는 ontological-db 에 없다. 노드를 그대로 받아 드라이버가
            # 풀게 한다 — 이 스크립트도 이식 가능해야 한다.
            [dict(r["n"]) for r in session.run(
                "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH '_Ontology') "
                "RETURN n")],
            ensure_ascii=False, default=str,
        )
    for secret in ("password", "postgres123", "12345strategy"):
        check(f"'{secret}' 없음", secret not in blob)

    # --- 5. 멱등 ---------------------------------------------------------------------
    print("\n5. 멱등")
    publish.publish(schema["id"])
    again = graph_schema.list_classes()
    check("다시 발행해도 클래스 수 동일", len(again) == len(classes),
          f"{len(classes)} -> {len(again)}")

    print("\n" + "=" * 66)
    print("능력 요약:", {k: ("O" if v else "X") for k, v in caps.items()})
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for item in failures:
            print("  - " + item)
        return 1
    print("ontological-db 백엔드에서 발행·조회가 동작한다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
