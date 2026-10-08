#!/usr/bin/env python
"""한전 전남 계통 예제 — 온톨로지 앱이 쓰는 업무 객체·연결·행위.

미국 전력망 예제(`seed_us_grid_demo.py`)와 같은 방식이지만 **한전 업무 어휘**로 쓴다.
클래스 이름과 속성 이름이 한국어라, 화면에 뜨는 목록·표 머리글·객체 상세가 그대로
업무 용어가 된다 — 영어 컬럼명을 매번 머릿속에서 번역하지 않아도 된다.

    변전소(점) ─송전선로(선)─ 변전소(점)
       │  │  │
       │  │  └ 정전이력(면)
       │  └── 배전선로 · 설비
       └───── 신재생발전(주간 실적)

여기에 **업무행위** 클래스를 하나 더 둔다. 객체 유형마다 어떤 일을 할 수 있는지를
데이터로 적어 두면, 화면은 고른 객체의 유형을 보고 버튼을 알아서 배치한다 —
버튼 목록을 화면에 박아 두면 객체가 늘 때마다 화면을 고쳐야 한다.

    uv run python scripts/seed_jeonnam_grid_demo.py
    uv run python scripts/seed_jeonnam_grid_demo.py --clear
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

SCHEMA_GROUP = "한전 전남 계통"

#: 전남 시·군 실제 좌표. 변전소를 이 근처에 둔다. (지사, 시군, 위도, 경도)
AREAS = [
    ("나주지사", "나주", 35.0160, 126.7108), ("목포지사", "목포", 34.8118, 126.3922),
    ("여수지사", "여수", 34.7604, 127.6622), ("순천지사", "순천", 34.9506, 127.4872),
    ("광양지사", "광양", 34.9407, 127.6959), ("무안지사", "무안", 34.9903, 126.4816),
    ("영암지사", "영암", 34.8000, 126.6967), ("해남지사", "해남", 34.5734, 126.5989),
    ("고흥지사", "고흥", 34.6111, 127.2850), ("보성지사", "보성", 34.7714, 127.0800),
    ("화순지사", "화순", 35.0644, 126.9866), ("담양지사", "담양", 35.3211, 126.9881),
    ("장성지사", "장성", 35.3018, 126.7889), ("영광지사", "영광", 35.2772, 126.5120),
    ("함평지사", "함평", 35.0658, 126.5169), ("강진지사", "강진", 34.6420, 126.7672),
    ("장흥지사", "장흥", 34.6816, 126.9070), ("완도지사", "완도", 34.3111, 126.7550),
    ("진도지사", "진도", 34.4867, 126.2634), ("신안지사", "신안", 34.8332, 126.3517),
]

VOLTAGES = [345, 154, 66, 22]
#: 전남은 태양광·풍력이 몰려 있다. 계통 포화와 역조류가 이 지역의 실제 현안이다.
RENEWABLE_TYPES = ["태양광", "육상풍력", "해상풍력", "바이오매스"]
EQUIP_TYPES = ["주변압기", "가스절연개폐장치", "차단기", "피뢰기", "리클로저"]
MAKERS = ["효성중공업", "LS일렉트릭", "현대일렉트릭", "일진전기"]
OUTAGE_CAUSES = ["낙뢰", "태풍", "설비고장", "수목접촉", "조류접촉", "작업오류"]
GRADES = ["양호", "주의", "요주의", "불량"]


def _short(name: str) -> str:
    """'나주제2변전소' → '나주제2'. 선로 이름이 길어지면 계통도에서 겹친다."""
    return name.replace("변전소", "")


def _rng() -> random.Random:
    # 씨앗을 고정한다. 예제가 실행마다 달라지면 캡처와 문서가 어긋난다.
    return random.Random(20260910)


def build_rows() -> dict:
    rng = _rng()
    subs, lines, feeders, equips, outages, renewables = [], [], [], [], [], []

    for i, (branch, city, lat, lng) in enumerate(AREAS, start=1):
        n_sub = 2 if i <= 8 else 1          # 큰 지사는 변전소가 둘이다
        for j in range(n_sub):
            code = f"SS-{i:02d}{j}"
            name = f"{city}변전소" if j == 0 else f"{city}제{j + 1}변전소"
            renew = round(rng.uniform(0, 260), 1)
            subs.append({
                "변전소_id": code,
                "변전소명": name,
                "지사": branch,
                "시군": city,
                "위도": round(lat + rng.uniform(-0.06, 0.06), 4),
                "경도": round(lng + rng.uniform(-0.06, 0.06), 4),
                "전압_kv": rng.choice(VOLTAGES),
                "설비용량_mva": round(rng.uniform(60, 480), 1),
                "부하율": round(rng.uniform(0.38, 0.97), 3),
                "신재생연계_mw": renew,
                "연계여유_mw": round(max(0.0, rng.uniform(0, 180) - renew * 0.4), 1),
                "준공일": str(date(1998, 1, 1) + timedelta(days=rng.randint(0, 9500))),
            })

    # 송전선로 — 가까운 변전소끼리 잇는다. 계통도의 선이 곧 이 행들이다.
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(subs):
        peers = sorted(
            (b for b in subs if b["변전소_id"] != a["변전소_id"]),
            key=lambda b: math.hypot(a["위도"] - b["위도"], a["경도"] - b["경도"]),
        )[:2]
        for k, b in enumerate(peers):
            pair = tuple(sorted((a["변전소_id"], b["변전소_id"])))
            if pair in seen:
                continue
            seen.add(pair)
            load = round(rng.uniform(0.28, 1.04), 3)
            kv = max(a["전압_kv"], b["전압_kv"])
            lines.append({
                "선로_id": f"TL-{i:02d}{k}",
                # 같은 시군에 변전소가 둘이면 "나주–나주" 가 된다. 변전소 이름으로 잇는다.
                "선로명": f"{_short(a['변전소명'])}–{_short(b['변전소명'])} T/L",
                "기점변전소_id": a["변전소_id"],
                "종점변전소_id": b["변전소_id"],
                "전압_kv": kv,
                "선로부하율": load,
                "과부하여부": "Y" if load > 0.85 else "N",
                "긍장_km": round(math.hypot(a["위도"] - b["위도"], a["경도"] - b["경도"]) * 111, 1),
                "회선수": rng.choice([1, 2, 2, 4]),
                # LineString — 프로파일러가 값에서 형상을 알아본다.
                "경로_geojson": json.dumps({
                    "type": "LineString",
                    "coordinates": [
                        [a["경도"], a["위도"]],
                        [round((a["경도"] + b["경도"]) / 2 + rng.uniform(-0.05, 0.05), 4),
                         round((a["위도"] + b["위도"]) / 2 + rng.uniform(-0.05, 0.05), 4)],
                        [b["경도"], b["위도"]],
                    ],
                }),
            })

    # 배전선로(피더) — 변전소에서 나가 고객에게 닿는다.
    for i, sub in enumerate(subs):
        for k in range(rng.randint(2, 4)):
            load = round(rng.uniform(0.31, 0.99), 3)
            feeders.append({
                "배전선로_id": f"DL-{i:02d}{k}",
                "배전선로명": f"{sub['시군']}{'ABCD'[k]}선로",
                "변전소_id": sub["변전소_id"],
                "시군": sub["시군"],
                "고객수": rng.randint(420, 9800),
                "부하율": load,
                "연간정전시간_분": round(rng.uniform(3, 78), 1),
                "지중화여부": "Y" if rng.random() < 0.28 else "N",
            })

    # 설비 — 점검 주기가 있는 자산. 점검 요청 행위가 여기서 출발한다.
    for i, sub in enumerate(subs):
        for k in range(rng.randint(2, 4)):
            cycle = rng.choice([6, 12, 24])
            last = date(2025, 1, 1) + timedelta(days=rng.randint(0, 600))
            # 유형을 한 번만 뽑는다. 두 번 뽑으면 이름과 유형이 어긋난다.
            etype = rng.choice(EQUIP_TYPES)
            equips.append({
                "설비_id": f"EQ-{i:02d}{k}",
                "설비명": f"{sub['변전소명']} {etype} {k + 1}호",
                "설비유형": etype,
                "변전소_id": sub["변전소_id"],
                "제조사": rng.choice(MAKERS),
                "설치일": str(date(2001, 1, 1) + timedelta(days=rng.randint(0, 8000))),
                "최근점검일": str(last),
                "점검주기_월": cycle,
                "상태등급": rng.choice(GRADES),
                "경과년수": rng.randint(1, 24),
            })

    # 정전이력 — 면(폴리곤)으로 남는 사건.
    for i, sub in enumerate(subs[:14]):
        d = round(rng.uniform(0.05, 0.18), 3)
        lo, la = sub["경도"], sub["위도"]
        outages.append({
            "정전_id": f"OT-{i:03d}",
            "변전소_id": sub["변전소_id"],
            "시군": sub["시군"],
            "원인": rng.choice(OUTAGE_CAUSES),
            "심각도": rng.choice(["경미", "주의", "심각"]),
            "영향고객수": rng.randint(240, 21000),
            "복구시간_분": rng.randint(12, 420),
            "발생일": str(date(2025, 3, 1) + timedelta(days=rng.randint(0, 500))),
            "구역_geojson": json.dumps({
                "type": "Polygon",
                "coordinates": [[[lo - d, la - d], [lo + d, la - d],
                                 [lo + d, la + d], [lo - d, la + d], [lo - d, la - d]]],
            }),
        })

    # 신재생발전 — 날짜가 키의 일부라 시계열 위젯이 발동한다.
    start = date(2025, 1, 6)
    for sub in subs[:10]:
        rtype = rng.choice(RENEWABLE_TYPES)
        for week in range(52):
            day = start + timedelta(days=week * 7)
            renewables.append({
                "발전_id": f"{sub['변전소_id']}-{day.isoformat()}",
                "발전일": day.isoformat(),
                "변전소_id": sub["변전소_id"],
                "시군": sub["시군"],
                "발전유형": rtype,
                "발전량_mwh": round(rng.uniform(900, 14000), 1),
                "이용률": round(rng.uniform(0.11, 0.42), 3),
                "역조류시간_h": round(rng.uniform(0, 46), 1),
            })

    return {"변전소": subs, "송전선로": lines, "배전선로": feeders,
            "설비": equips, "정전이력": outages, "신재생발전": renewables,
            "업무행위": build_behaviors()}


# ---------------------------------------------------------------------------
# 업무행위 — 객체 유형이 할 수 있는 일. 화면은 이 표를 읽어 버튼을 배치한다.
# ---------------------------------------------------------------------------

def _behavior(bid, target, name, desc, kind, ref, icon, mapping):
    return {"행위_id": bid, "대상유형": target, "행위명": name, "설명": desc,
            "실행유형": kind, "실행대상": ref, "아이콘": icon,
            "입력매핑": json.dumps(mapping, ensure_ascii=False)}


def build_behaviors() -> list[dict]:
    """행위는 실제로 도는 것만 적는다. 돌지 않는 버튼은 없느니만 못하다."""
    return [
        _behavior("BH-001", "변전소", "증설 검토 요청",
                  "부하율이 임계를 넘은 변전소를 증설 대상으로 올려 다부서 검토를 시작한다",
                  "process", "grid_expansion_review_process", "activity",
                  {"대상": "변전소명", "근거": "부하율"}),
        _behavior("BH-002", "변전소", "계통제약 발전 조정",
                  "선로 제약으로 출력을 줄여야 할 때 조정 지시를 만든다",
                  "process", "sub_constraint_gen", "bolt",
                  {"대상": "변전소명", "근거": "전압_kv"}),
        _behavior("BH-003", "변전소", "분산전원 연계 검토",
                  "태양광·풍력 접속 요청을 이 변전소의 연계 여유로 판단한다",
                  "process", "sub_ppa_connect", "grid",
                  {"대상": "변전소명", "근거": "연계여유_mw"}),
        _behavior("BH-004", "변전소", "일일 수요예측·발전계획",
                  "이 변전소가 물린 구역의 수요를 예측해 다음 날 발전계획을 세운다",
                  "process", "sub_demand_forecast", "chart",
                  {"대상": "변전소명", "근거": "설비용량_mva"}),

        _behavior("BH-011", "송전선로", "경과지 선정 검토",
                  "과부하 선로를 보강할 신설 경과지를 다부서가 함께 고른다",
                  "process", "sub_route_selection", "grid",
                  {"대상": "선로명", "근거": "선로부하율"}),
        _behavior("BH-012", "송전선로", "장기 송변전설비계획 반영",
                  "이 선로의 부하 추세를 장기 설비계획 검토로 넘긴다",
                  "process", "sub_ltp_plan", "folder",
                  {"대상": "선로명", "근거": "전압_kv"}),

        _behavior("BH-021", "배전선로", "순시·결함 조치 지시",
                  "정전이 잦은 배전선로에 순시를 배정하고 결함을 조치한다",
                  "process", "sub_line_patrol", "shield",
                  {"대상": "배전선로명", "근거": "연간정전시간_분"}),
        _behavior("BH-022", "배전선로", "배전공사 설계·감리",
                  "지중화·증설 공사를 설계하고 시공 감리까지 건다",
                  "process", "sub_dist_construction", "edit",
                  {"대상": "배전선로명", "근거": "고객수"}),

        _behavior("BH-031", "설비", "점검 요청",
                  "점검 주기가 지난 설비의 점검을 요청한다 — 승인·작업지시로 이어진다",
                  "process", "sub_line_patrol", "shield",
                  {"대상": "설비명", "근거": "최근점검일"}),
        _behavior("BH-032", "설비", "기자재 수급계획 반영",
                  "노후 설비 교체 물량을 전력기자재 수급계획에 올린다",
                  "process", "sub_material_plan", "folder",
                  {"대상": "설비명", "근거": "경과년수"}),

        _behavior("BH-041", "정전이력", "복구 지시",
                  "정전 신고를 접수해 복구 지시를 내리고 진행을 추적한다",
                  "process", "sub_outage_response", "bolt",
                  {"대상": "시군", "근거": "영향고객수"}),

        _behavior("BH-051", "신재생발전", "접속 용량 검토",
                  "발전 실적과 역조류 시간을 근거로 추가 접속 여력을 판단한다",
                  "process", "sub_ppa_connect", "grid",
                  {"대상": "발전유형", "근거": "역조류시간_h"}),
    ]


#: 클래스별 (키 속성, 설명). 키가 시계열 판정을 가른다 — 신재생발전은 날짜가 키다.
#: 설명은 `이름 — 부연` 관례를 따른다. 화면이 앞부분을 표시 이름으로 쓴다.
CLASSES = {
    "변전소": (["변전소_id"],
             "변전소 — 위·경도를 가진 지점 자산. 설비용량·부하율·신재생 연계량을 갖는다"),
    "송전선로": (["선로_id"],
              "송전선로 — 변전소를 잇는 경로. 전압 등급과 선로 부하율을 갖는다"),
    "배전선로": (["배전선로_id"],
              "배전선로 — 변전소에서 고객으로 나가는 피더. 고객수와 정전 시간을 갖는다"),
    "설비": (["설비_id"],
           "설비 — 변전소 안의 주요 기기. 점검 주기와 상태 등급을 갖는다"),
    "정전이력": (["정전_id"],
             "정전이력 — 원인·심각도·영향 고객이 남은 면 단위 사건"),
    "신재생발전": (["발전일", "변전소_id"],
              "신재생발전 — 변전소별 주간 발전 실적과 역조류 시간"),
    "업무행위": (["행위_id"],
             "업무행위 — 객체 유형이 할 수 있는 일. 화면이 이 표를 읽어 버튼을 배치한다"),
}

#: `join` 속성이 있어야 교차 필터와 참조가 성립한다.
RELATIONSHIPS = [
    ("연결_변전소", "송전선로", "변전소", "기점변전소_id = 변전소_id"),
    ("소속_변전소", "배전선로", "변전소", "변전소_id = 변전소_id"),
    ("설치_변전소", "설비", "변전소", "변전소_id = 변전소_id"),
    ("발생_변전소", "정전이력", "변전소", "변전소_id = 변전소_id"),
    ("연계_변전소", "신재생발전", "변전소", "변전소_id = 변전소_id"),
]


def _properties(rows: list[dict], keys: list[str]) -> str:
    sample = rows[0]
    out = []
    for name, value in sample.items():
        if isinstance(value, bool):
            ptype = "boolean"
        elif isinstance(value, int):
            ptype = "integer"
        elif isinstance(value, float):
            ptype = "float"
        elif name.endswith("일") or name.endswith("_date"):
            ptype = "date"
        else:
            ptype = "string"
        out.append({"name": name, "type": ptype, "key": name in keys})
    return json.dumps(out, ensure_ascii=False)


def seed(clear: bool = False) -> int:
    from backend.src.modules.agent_session import session_store
    from backend.src.modules.ontology import publish
    from backend.src.modules.ontology.tools import get_driver, session_kwargs

    data = build_rows()

    existing = session_store.get_schema_by_name(SCHEMA_GROUP)
    schema_id = existing["id"] if existing else session_store.create_schema(
        SCHEMA_GROUP, "한전 전남본부 계통 예제",
        intent="변전소·송전선로·배전선로·설비·정전이력·신재생발전을 지도와 계통도로 보고, 객체마다 업무 행위를 건다",
        golden_questions=json.dumps([
            "과부하 구간이 있는 송전선로는 어디인가?",
            "신재생 연계 여유가 부족한 변전소는 어디인가?",
            "점검 주기가 지난 설비는 어느 변전소에 있는가?",
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
            # 자기 라벨 범위만 지운다. 전역 삭제는 카탈로그까지 지운다.
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
