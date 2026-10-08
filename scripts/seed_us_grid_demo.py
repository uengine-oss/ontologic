#!/usr/bin/env python
"""미국 전력망 예제 — 지리 위젯(O4·O5·O6)과 교차 필터를 보여 주는 데이터.

연구 보고서가 든 발전·송배전 시나리오를 **이 플랫폼에서 실제로 도는 형태**로 만든다.
데이터소스 없이 그래프에만 올린다 — 사용자가 고른 "Neo4j 모드" 그대로다.

    변전소(점)  ─REFERENCES_US_SUBSTATION─  송전선로(선)
        │                                        │
    발전량(시계열)                            정전구역(면)

지리 형상은 **속성값**이다. `path_geojson` 은 LineString, `boundary_geojson` 은 Polygon 이고
프로파일러가 값에서 형상을 알아본다 — SQL 타입 체계에 없는 타입이라 그 방법뿐이다.

    uv run python scripts/seed_us_grid_demo.py
    uv run python scripts/seed_us_grid_demo.py --clear
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ontology-studio"))

SCHEMA_GROUP = "미국 전력망"

#: 실제 주요 도시 좌표. 변전소를 이 근처에 흩는다.
CITIES = [
    ("CA", "Los Angeles", 34.05, -118.24), ("CA", "San Francisco", 37.77, -122.42),
    ("TX", "Houston", 29.76, -95.37), ("TX", "Dallas", 32.78, -96.80),
    ("NY", "New York", 40.71, -74.01), ("IL", "Chicago", 41.88, -87.63),
    ("AZ", "Phoenix", 33.45, -112.07), ("PA", "Philadelphia", 39.95, -75.17),
    ("FL", "Miami", 25.76, -80.19), ("WA", "Seattle", 47.61, -122.33),
    ("GA", "Atlanta", 33.75, -84.39), ("MA", "Boston", 42.36, -71.06),
    ("CO", "Denver", 39.74, -104.99), ("MI", "Detroit", 42.33, -83.05),
    ("MN", "Minneapolis", 44.98, -93.27), ("OH", "Columbus", 39.96, -83.00),
]

VOLTAGES = [500, 345, 230, 138]
PLANT_TYPES = ["가스복합", "석탄", "원자력", "태양광", "풍력"]


def _rng() -> random.Random:
    # 씨앗을 고정한다. 예제가 실행마다 달라지면 캡처와 문서가 어긋난다.
    return random.Random(20260819)


def build_rows() -> dict:
    rng = _rng()
    substations, lines, outages, outputs = [], [], [], []

    for i, (state, city, lat, lng) in enumerate(CITIES, start=1):
        for j in range(2):
            sid = f"SUB-{i:02d}{j}"
            substations.append({
                "substation_id": sid,
                "substation_name": f"{city} 변전소 {j + 1}호",
                "state": state,
                "city": city,
                "latitude": round(lat + rng.uniform(-0.35, 0.35), 4),
                "longitude": round(lng + rng.uniform(-0.35, 0.35), 4),
                "voltage_kv": rng.choice(VOLTAGES),
                "capacity_mw": round(rng.uniform(200, 1200), 1),
                "load_pct": round(rng.uniform(0.35, 0.98), 3),
                "commissioned_date": str(date(2005, 1, 1) + timedelta(days=rng.randint(0, 6500))),
            })

    # 선로는 가까운 변전소끼리 잇는다. 실제 계통처럼 보이게 거리로 고른다.
    for i, a in enumerate(substations):
        peers = sorted(
            (b for b in substations if b["substation_id"] != a["substation_id"]),
            key=lambda b: math.hypot(a["latitude"] - b["latitude"], a["longitude"] - b["longitude"]),
        )[:2]
        for k, b in enumerate(peers):
            load = round(rng.uniform(0.30, 1.05), 3)
            lines.append({
                "line_id": f"LN-{i:02d}{k}",
                "line_name": f"{a['city']}–{b['city']} 선로",
                "from_substation_id": a["substation_id"],
                "to_substation_id": b["substation_id"],
                "state": a["state"],
                "voltage_kv": a["voltage_kv"],
                "current_load_pct": load,
                "overloaded": "Y" if load > 0.8 else "N",
                # LineString — 프로파일러가 값에서 형상을 알아본다 (O5).
                "path_geojson": json.dumps({
                    "type": "LineString",
                    "coordinates": [
                        [a["longitude"], a["latitude"]],
                        [round((a["longitude"] + b["longitude"]) / 2 + rng.uniform(-0.4, 0.4), 4),
                         round((a["latitude"] + b["latitude"]) / 2 + rng.uniform(-0.4, 0.4), 4)],
                        [b["longitude"], b["latitude"]],
                    ],
                }),
            })

    # 정전 구역 — 변전소 주변의 사각형 폴리곤 (O6).
    for i, sub in enumerate(substations[:10]):
        d = round(rng.uniform(0.4, 1.1), 3)
        lo, la = sub["longitude"], sub["latitude"]
        outages.append({
            "event_id": f"OUT-{i:03d}",
            "state": sub["state"],
            "substation_id": sub["substation_id"],
            "severity_level": rng.choice(["경미", "주의", "심각"]),
            "cause": rng.choice(["낙뢰", "태풍", "설비고장", "수목접촉"]),
            "affected_customers": rng.randint(1200, 98000),
            "event_date": str(date(2025, 1, 1) + timedelta(days=rng.randint(0, 360))),
            "boundary_geojson": json.dumps({
                "type": "Polygon",
                "coordinates": [[[lo - d, la - d], [lo + d, la - d],
                                 [lo + d, la + d], [lo - d, la + d], [lo - d, la - d]]],
            }),
        })

    # 발전량 — 시간이 **키의 일부**라 O1(시계열)이 발동한다.
    start = date(2025, 1, 1)
    for sub in substations[:8]:
        ptype = rng.choice(PLANT_TYPES)
        for week in range(52):
            day = start + timedelta(days=week * 7)
            outputs.append({
                "output_id": f"{sub['substation_id']}-{day.isoformat()}",
                "output_date": day.isoformat(),
                "substation_id": sub["substation_id"],
                "state": sub["state"],
                "plant_type": ptype,
                "generation_mwh": round(rng.uniform(4000, 26000), 1),
                "co2_ton": round(rng.uniform(0, 9000), 1),
                "availability_pct": round(rng.uniform(0.72, 0.99), 3),
            })

    return {"UsSubstation": substations, "UsTransmissionLine": lines,
            "UsOutageArea": outages, "UsPlantOutput": outputs}


#: 클래스별 (키 컬럼, 설명). 키가 시계열 판정을 가른다 — `UsPlantOutput` 은 날짜가 키다.
#: 설명은 `이름 — 부연` 관례를 따른다. 화면이 앞부분을 **표시 이름**으로 쓰고 뒤는
#: 툴팁으로 돌린다. 클래스명(`UsSubstation`)만 띄우면 읽는 사람이 매번 번역해야 한다.
CLASSES = {
    "UsSubstation": (["substation_id"],
                     "변전소 — 위·경도를 가진 지점 자산. 용량과 부하율을 갖는다"),
    "UsTransmissionLine": (["line_id"],
                           "송전선로 — 변전소를 잇는 경로. 전압 등급과 부하율을 갖는다"),
    "UsOutageArea": (["event_id"],
                     "정전 영향 구역 — 낙뢰·태풍으로 생긴 면 단위 피해 범위"),
    "UsPlantOutput": (["output_date", "substation_id"],
                      "주간 발전 실적 — 변전소별 주 단위 발전량과 가용률"),
}

#: `join` 속성이 있어야 교차 필터와 `_datasource_refs` 가 성립한다.
RELATIONSHIPS = [
    ("REFERENCES_US_SUBSTATION", "UsTransmissionLine", "UsSubstation",
     "from_substation_id = substation_id"),
    ("REFERENCES_US_SUBSTATION", "UsOutageArea", "UsSubstation",
     "substation_id = substation_id"),
    ("REFERENCES_US_SUBSTATION", "UsPlantOutput", "UsSubstation",
     "substation_id = substation_id"),
]


def _properties(rows: list[dict], keys: list[str]) -> str:
    from backend.src.modules.ontology.schema_ontology import map_sql_type

    sample = rows[0]
    out = []
    for name, value in sample.items():
        if isinstance(value, bool):
            ptype = "boolean"
        elif isinstance(value, int):
            ptype = "integer"
        elif isinstance(value, float):
            ptype = "float"
        elif name.endswith("_date"):
            ptype = "date"
        else:
            ptype = "string"
        out.append({"name": name, "type": ptype, "key": name in keys})
    del map_sql_type
    return json.dumps(out, ensure_ascii=False)


def seed(clear: bool = False) -> int:
    from backend.src.modules.agent_session import session_store
    from backend.src.modules.ontology import publish
    from backend.src.modules.ontology.tools import get_driver, session_kwargs

    data = build_rows()

    existing = session_store.get_schema_by_name(SCHEMA_GROUP)
    schema_id = existing["id"] if existing else session_store.create_schema(
        SCHEMA_GROUP, "미국 전력망 지리 예제",
        intent="변전소·송전선로·정전구역·발전량을 지도와 추이로 본다",
        golden_questions=json.dumps([
            "과부하 구간이 있는 송전선로는 어디인가?",
            "주별 정전 피해 가구는 얼마나 되는가?",
            "발전 유형별 주간 발전량 추이는?",
        ], ensure_ascii=False),
    )
    if isinstance(schema_id, dict):
        schema_id = schema_id.get("id", schema_id)

    for klass, (keys, desc) in CLASSES.items():
        session_store.add_class_to_schema(
            schema_id, klass, desc, _properties(data[klass], keys))
    for name, frm, to, join in RELATIONSHIPS:
        session_store.add_relationship_to_schema(
            schema_id, name, frm, to, f"{frm} → {to}",
            json.dumps([{"name": "join", "description": join}], ensure_ascii=False))

    driver = get_driver()
    counts = {}
    with driver.session(**session_kwargs()) as s:
        for klass, rows in data.items():
            # 자기 라벨 범위만 지운다. 전역 삭제는 카탈로그까지 지운다 (constitution IV).
            s.run(f"MATCH (n:_Entity:`{klass}`) DETACH DELETE n")
            if clear:
                continue
            for row in rows:
                s.run(f"CREATE (n:_Entity:`{klass}`) SET n = $props", {"props": row})
            counts[klass] = len(rows)

        if not clear:
            for name, frm, to, join in RELATIONSHIPS:
                left, right = [x.strip() for x in join.split("=")]
                s.run(
                    f"MATCH (a:_Entity:`{frm}`), (b:_Entity:`{to}`) "
                    f"WHERE a.`{left}` = b.`{right}` MERGE (a)-[:`{name}`]->(b)")

    if clear:
        result = publish.unpublish(schema_id)
        print("철회:", result)
        return 0

    result = publish.publish(schema_id)
    if result.get("error"):
        print("[FAIL]", result["error"])
        return 1
    print("적재:", counts)
    print("발행:", result.get("counts"), "제약:", result.get("constraints_created"))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--clear", action="store_true", help="인스턴스와 발행을 지운다")
    a = p.parse_args()
    return seed(clear=a.clear)


if __name__ == "__main__":
    raise SystemExit(main())
