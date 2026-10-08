#!/usr/bin/env python3
"""공급망 데모 데이터 생성기 — 결정적(seed 고정) SQL INSERT 를 만든다.

시나리오가 성립하도록 몇 가지 사실을 '심는다' (골든 팩트):
  G1 조달   : PO-2026-0117 (SUP-CN-003, PCB) 선적이 부산 세관 HOLD 로 9일 지연
  G2 수출입 : 그 선적의 신고서에 원산지증명(COO) 누락 + ITM-CON-002 HS 코드 불일치
  G3 재고   : ITM-PCB-004 가 안전재고 이탈, 커버일수 약 6일
  G4 계약   : CT-2025-011 (SUP-CN-003) 25일 후 만기, 자동갱신 없음, 페널티 2%
  G5 구매   : 대체 공급사 SUP-VN-002 (평점 4.3, 리드 12일, 납기준수 96%)
  G6 고객지원: 고객 CUS-004 의 SO-2026-0412 납기 리스크 + 클레임 TK-2026-0031

나머지는 분포를 따르는 배경 데이터다.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

random.seed(20260821)
TODAY = date(2026, 8, 21)
OUT = Path(__file__).parent / "sql" / "02_supplychain_data.sql"


def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    return "'" + str(v).replace("'", "''") + "'"


def ins(table, rows, cols):
    out = []
    for r in rows:
        out.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(q(r[c]) for c in cols)});")
    return "\n".join(out)


# ── 공급사 ────────────────────────────────────────────────────────────────
suppliers = [
    # id, name, country, city, tier, category, rating, lead, on_time, incoterms, currency
    ("SUP-KR-001", "대성전자부품", "Korea", "Ansan", 1, "커넥터", 4.6, 5, 0.985, "EXW", "KRW"),
    ("SUP-KR-002", "한빛정밀", "Korea", "Cheonan", 1, "사출", 4.4, 7, 0.972, "EXW", "KRW"),
    ("SUP-KR-003", "세진패키징", "Korea", "Incheon", 2, "포장재", 4.1, 4, 0.990, "EXW", "KRW"),
    ("SUP-CN-001", "Dongguan Precision Metal", "China", "Dongguan", 1, "금속가공", 4.0, 14, 0.931, "FOB", "USD"),
    ("SUP-CN-002", "Suzhou Cap-Tech", "China", "Suzhou", 2, "수동소자", 3.9, 16, 0.912, "FOB", "USD"),
    ("SUP-CN-003", "Shenzhen Goldline PCB", "China", "Shenzhen", 1, "PCB", 3.6, 18, 0.874, "FOB", "USD"),
    ("SUP-CN-004", "Ningbo Magnetics", "China", "Ningbo", 2, "자성부품", 4.2, 15, 0.945, "FOB", "USD"),
    ("SUP-VN-001", "Hanoi Cable Works", "Vietnam", "Hanoi", 1, "케이블", 4.3, 11, 0.958, "FOB", "USD"),
    ("SUP-VN-002", "Saigon Circuit Co.", "Vietnam", "Ho Chi Minh", 1, "PCB", 4.3, 12, 0.961, "FOB", "USD"),
    ("SUP-JP-001", "Kyoto Ceramics", "Japan", "Kyoto", 1, "세라믹", 4.8, 9, 0.992, "CIF", "JPY"),
    ("SUP-JP-002", "Osaka Semicon", "Japan", "Osaka", 1, "반도체", 4.7, 21, 0.968, "CIF", "JPY"),
    ("SUP-TW-001", "Hsinchu MCU Inc.", "Taiwan", "Hsinchu", 1, "반도체", 4.5, 20, 0.955, "FOB", "USD"),
    ("SUP-TW-002", "Taoyuan Display Parts", "Taiwan", "Taoyuan", 1, "디스플레이", 4.2, 13, 0.940, "FOB", "USD"),
    ("SUP-DE-001", "Rhein Sensorik GmbH", "Germany", "Stuttgart", 1, "센서", 4.9, 24, 0.980, "DAP", "EUR"),
    ("SUP-US-001", "Austin Power ICs", "USA", "Austin", 1, "반도체", 4.6, 26, 0.950, "FCA", "USD"),
    ("SUP-MY-001", "Penang Assembly Sdn", "Malaysia", "Penang", 2, "SMT외주", 4.0, 10, 0.930, "FOB", "USD"),
    ("SUP-TH-001", "Bangkok Plastics", "Thailand", "Bangkok", 2, "사출", 3.8, 12, 0.905, "FOB", "USD"),
    ("SUP-IN-001", "Pune Wire Harness", "India", "Pune", 2, "케이블", 3.7, 19, 0.890, "FOB", "USD"),
]
SUP_COLS = ["supplier_id", "supplier_name", "country", "city", "tier", "category", "rating",
            "avg_lead_days", "on_time_rate", "incoterms", "currency"]
suppliers = [dict(zip(SUP_COLS, s)) for s in suppliers]
SUP_BY_CAT = {}
for s in suppliers:
    SUP_BY_CAT.setdefault(s["category"], []).append(s["supplier_id"])

# ── 품목 ──────────────────────────────────────────────────────────────────
items = [
    # id, name, type, hs, origin, unit, cost, safety, moq, primary, alt
    ("ITM-PCB-001", "4층 메인보드 PCB 120x80", "RAW", "8534.00", "China", "EA", 3.20, 6000, 2000, "SUP-CN-003", "SUP-VN-002"),
    ("ITM-PCB-002", "2층 서브보드 PCB 60x40", "RAW", "8534.00", "Vietnam", "EA", 1.10, 8000, 5000, "SUP-VN-002", "SUP-CN-003"),
    ("ITM-PCB-003", "FPCB 카메라 모듈용", "RAW", "8534.00", "China", "EA", 2.45, 5000, 3000, "SUP-CN-003", "SUP-VN-002"),
    ("ITM-PCB-004", "6층 HDI PCB 전원모듈", "RAW", "8534.00", "China", "EA", 5.80, 4000, 2000, "SUP-CN-003", "SUP-VN-002"),
    ("ITM-CON-001", "보드투보드 커넥터 0.4mm 40P", "RAW", "8536.69", "Korea", "EA", 0.42, 20000, 10000, "SUP-KR-001", None),
    ("ITM-CON-002", "USB-C 리셉터클 24P", "RAW", "8536.90", "Korea", "EA", 0.38, 15000, 10000, "SUP-KR-001", None),
    ("ITM-CON-003", "FFC 커넥터 30P", "RAW", "8536.69", "Korea", "EA", 0.21, 25000, 10000, "SUP-KR-001", None),
    ("ITM-CAP-001", "MLCC 0402 1uF", "RAW", "8532.24", "China", "KEA", 1.90, 500, 200, "SUP-CN-002", "SUP-JP-001"),
    ("ITM-CAP-002", "탄탈 커패시터 100uF", "RAW", "8532.21", "Japan", "KEA", 45.00, 80, 20, "SUP-JP-001", None),
    ("ITM-IND-001", "파워 인덕터 4.7uH", "RAW", "8504.50", "China", "KEA", 12.00, 150, 50, "SUP-CN-004", None),
    ("ITM-MCU-001", "32bit MCU 120MHz", "RAW", "8542.31", "Taiwan", "EA", 2.10, 10000, 5000, "SUP-TW-001", "SUP-JP-002"),
    ("ITM-MCU-002", "BLE SoC", "RAW", "8542.31", "Taiwan", "EA", 1.75, 8000, 5000, "SUP-TW-001", None),
    ("ITM-PMC-001", "PMIC 전원관리 IC", "RAW", "8542.39", "USA", "EA", 1.30, 12000, 5000, "SUP-US-001", "SUP-JP-002"),
    ("ITM-PMC-002", "DC-DC 벅 컨버터 IC", "RAW", "8542.39", "Japan", "EA", 0.95, 12000, 5000, "SUP-JP-002", "SUP-US-001"),
    ("ITM-SEN-001", "6축 IMU 센서", "RAW", "9031.80", "Germany", "EA", 3.40, 3000, 1000, "SUP-DE-001", None),
    ("ITM-SEN-002", "온습도 센서", "RAW", "9025.80", "Germany", "EA", 1.20, 4000, 1000, "SUP-DE-001", None),
    ("ITM-DSP-001", "1.3인치 OLED 모듈", "RAW", "8524.11", "Taiwan", "EA", 4.90, 3000, 1000, "SUP-TW-002", None),
    ("ITM-DSP-002", "터치패널 5인치", "RAW", "8537.10", "Taiwan", "EA", 6.50, 2500, 1000, "SUP-TW-002", None),
    ("ITM-CAB-001", "USB-C 케이블 1m", "RAW", "8544.42", "Vietnam", "EA", 0.85, 15000, 5000, "SUP-VN-001", "SUP-IN-001"),
    ("ITM-CAB-002", "내부 와이어 하네스 8P", "RAW", "8544.30", "Vietnam", "EA", 0.60, 12000, 5000, "SUP-VN-001", "SUP-IN-001"),
    ("ITM-MTL-001", "알루미늄 방열판 CNC", "RAW", "7616.99", "China", "EA", 1.80, 6000, 2000, "SUP-CN-001", None),
    ("ITM-MTL-002", "SUS 브라켓", "RAW", "7326.90", "China", "EA", 0.70, 8000, 3000, "SUP-CN-001", None),
    ("ITM-MLD-001", "ABS 상부 하우징", "RAW", "3926.90", "Korea", "EA", 0.95, 10000, 5000, "SUP-KR-002", "SUP-TH-001"),
    ("ITM-MLD-002", "PC 하부 하우징", "RAW", "3926.90", "Korea", "EA", 1.05, 10000, 5000, "SUP-KR-002", "SUP-TH-001"),
    ("ITM-MLD-003", "실리콘 버튼", "RAW", "3926.90", "Thailand", "EA", 0.18, 20000, 10000, "SUP-TH-001", "SUP-KR-002"),
    ("ITM-CER-001", "세라믹 기판 96% Al2O3", "RAW", "6914.90", "Japan", "EA", 2.60, 3000, 1000, "SUP-JP-001", None),
    ("ITM-MAG-001", "페라이트 코어 EE25", "RAW", "8505.11", "China", "EA", 0.33, 15000, 5000, "SUP-CN-004", None),
    ("ITM-PKG-001", "개별 포장 박스", "RAW", "4819.10", "Korea", "EA", 0.25, 30000, 10000, "SUP-KR-003", None),
    ("ITM-PKG-002", "완충 트레이", "RAW", "3923.10", "Korea", "EA", 0.12, 30000, 10000, "SUP-KR-003", None),
    ("ITM-PKG-003", "수출용 카톤 (20EA)", "RAW", "4819.10", "Korea", "EA", 0.80, 5000, 2000, "SUP-KR-003", None),
    ("ITM-SUB-001", "전원모듈 SMT 반제품", "SUB", "8504.40", "Malaysia", "EA", 14.50, 2500, 1000, "SUP-MY-001", None),
    ("ITM-SUB-002", "센서보드 SMT 반제품", "SUB", "8543.70", "Malaysia", "EA", 9.80, 2500, 1000, "SUP-MY-001", None),
    ("ITM-FG-001", "스마트 전원 컨트롤러 SPC-200", "FG", "8537.10", "Korea", "EA", 48.00, 1500, 500, None, None),
    ("ITM-FG-002", "IoT 환경센서 게이트웨이 EG-10", "FG", "8517.62", "Korea", "EA", 39.00, 1200, 500, None, None),
    ("ITM-FG-003", "웨어러블 컨트롤 밴드 WB-3", "FG", "8517.62", "Korea", "EA", 27.00, 2000, 500, None, None),
    ("ITM-FG-004", "차량용 디스플레이 모듈 VD-5", "FG", "8528.59", "Korea", "EA", 62.00, 800, 300, None, None),
]
ITEM_COLS = ["item_id", "item_name", "item_type", "hs_code", "origin_country", "unit", "std_cost_usd",
             "safety_stock", "moq", "primary_supplier_id", "alt_supplier_id"]
items = [dict(zip(ITEM_COLS, i)) for i in items]
ITEM = {i["item_id"]: i for i in items}
RAW_ITEMS = [i for i in items if i["item_type"] in ("RAW", "SUB")]
FG_ITEMS = [i for i in items if i["item_type"] == "FG"]
ITEMS_BY_SUP = {}
for i in RAW_ITEMS:
    ITEMS_BY_SUP.setdefault(i["primary_supplier_id"], []).append(i["item_id"])

# ── 고객 ──────────────────────────────────────────────────────────────────
customers = [
    ("CUS-001", "노바텍 일렉트로닉스", "USA", "글로벌 OEM", "FOB", "NET60", 30),
    ("CUS-002", "헬리오스 디스플레이", "Korea", "글로벌 OEM", "EXW", "NET45", 14),
    ("CUS-003", "오리온 모바일 베트남법인", "Vietnam", "글로벌 OEM", "CIF", "NET60", 21),
    ("CUS-004", "아틀라스 오토모티브", "Germany", "티어1 자동차", "DAP", "NET90", 45),
    ("CUS-005", "루멘 스마트홈", "Japan", "ODM", "CIF", "NET30", 21),
    ("CUS-006", "퍼시픽 테크 디스트리뷰션", "Singapore", "유통", "FOB", "NET30", 14),
    ("CUS-007", "카이로스 헬스케어", "Netherlands", "ODM", "DAP", "NET45", 30),
    ("CUS-008", "브리즈 컨슈머", "Australia", "유통", "CIF", "NET30", 21),
]
CUS_COLS = ["customer_id", "customer_name", "country", "segment", "incoterms", "payment_terms", "sla_days"]
customers = [dict(zip(CUS_COLS, c)) for c in customers]

# ── 계약 ──────────────────────────────────────────────────────────────────
contracts = []
cid = 0
for s in suppliers:
    n = 2 if s["tier"] == 1 else 1
    for k in range(n):
        cid += 1
        start = date(2025, random.randint(1, 12), 1)
        end = start + timedelta(days=365 if k == 0 else 730)
        ctype = ["단가계약", "연간공급", "품질보증"][k % 3]
        status = "ACTIVE"
        if end < TODAY:
            status = "EXPIRED"
        elif (end - TODAY).days <= 60:
            status = "EXPIRING"
        contracts.append(dict(
            contract_id=f"CT-2025-{cid:03d}", supplier_id=s["supplier_id"], contract_type=ctype,
            start_date=start, end_date=end, auto_renew=random.random() < 0.5,
            penalty_rate=random.choice([0.5, 1.0, 1.5, 2.0]), price_lock=random.random() < 0.4,
            status=status, risk_clause=None,
        ))
# G4: CT-2025-011 → SUP-CN-003, 25일 후 만기, 자동갱신 없음
g4 = next(c for c in contracts if c["contract_id"] == "CT-2025-011")
g4.update(supplier_id="SUP-CN-003", contract_type="연간공급", start_date=date(2025, 9, 15),
          end_date=TODAY + timedelta(days=25), auto_renew=False, penalty_rate=2.0, price_lock=True,
          status="EXPIRING", risk_clause="납기 7일 초과 지연 시 건당 2% 페널티, 연속 2회 시 계약해지 가능")
# 재배정으로 계약이 사라진 공급사에는 계약 하나를 보충한다
for s_ in suppliers:
    if not any(c["supplier_id"] == s_["supplier_id"] for c in contracts):
        cid += 1
        contracts.append(dict(contract_id=f"CT-2025-{cid:03d}", supplier_id=s_["supplier_id"], contract_type="단가계약",
                              start_date=date(2025, 6, 1), end_date=date(2027, 5, 31), auto_renew=True, penalty_rate=1.0,
                              price_lock=False, status="ACTIVE", risk_clause=None))
CT_BY_SUP = {}
for c in contracts:
    CT_BY_SUP.setdefault(c["supplier_id"], []).append(c["contract_id"])
CT_COLS = ["contract_id", "supplier_id", "contract_type", "start_date", "end_date", "auto_renew",
           "penalty_rate", "price_lock", "status", "risk_clause"]

# ── 발주 / 라인 / 선적 / 통관 ────────────────────────────────────────────
pos, po_lines, shipments, decls = [], [], [], []
po_no = 0
ship_no = 0
decl_no = 0
buyers = ["김민수", "이서연", "박준호", "최지우"]
forwarders = {"SEA": ["Pan Ocean Logistics", "KMTC", "Evergreen"], "AIR": ["DHL Global", "KE Cargo"], "TRUCK": ["CJ대한통운"]}


def make_po(sup, order_date, planted=None):
    global po_no, ship_no, decl_no
    po_no += 1
    po_id = f"PO-2026-{po_no:04d}"
    lead = sup["avg_lead_days"]
    promised = order_date + timedelta(days=lead + random.randint(2, 6))
    domestic = sup["country"] == "Korea"
    item_ids = random.sample(ITEMS_BY_SUP[sup["supplier_id"]], k=min(len(ITEMS_BY_SUP[sup["supplier_id"]]), random.randint(1, 3)))
    total = 0.0
    lines = []
    for it in item_ids:
        qty = ITEM[it]["moq"] * random.randint(1, 4)
        price = round(ITEM[it]["std_cost_usd"] * random.uniform(0.93, 1.08), 4)
        total += qty * price
        lines.append((it, qty, price))
    # 상태
    late = random.random() > sup["on_time_rate"]
    if promised < TODAY - timedelta(days=3):
        status = "RECEIVED"
        delay = random.randint(2, 12) if late else 0
    elif promised <= TODAY + timedelta(days=10):
        status = "DELAYED" if late else random.choice(["OPEN", "PARTIAL"])
        delay = random.randint(3, 10) if late else 0
    else:
        status = "OPEN"
        delay = 0
    if planted:
        status, delay = planted["status"], planted["delay"]
    pos.append(dict(po_id=po_id, supplier_id=sup["supplier_id"], contract_id=random.choice(CT_BY_SUP[sup["supplier_id"]]),
                    order_date=order_date, promised_date=promised, status=status,
                    total_amount_usd=round(total, 2), buyer=random.choice(buyers),
                    priority="HIGH" if (planted or random.random() < 0.2) else "NORMAL"))
    for it, qty, price in lines:
        recv = qty if status == "RECEIVED" else (qty // 2 if status == "PARTIAL" else 0)
        po_lines.append(dict(po_id=po_id, item_id=it, qty_ordered=qty, qty_received=recv, unit_price_usd=price,
                             line_status="CLOSED" if status == "RECEIVED" else "OPEN"))
    # 선적 (국내는 TRUCK, 확정 이전 주문은 선적 없음)
    if status in ("RECEIVED", "PARTIAL", "DELAYED") or (status == "OPEN" and random.random() < 0.5):
        ship_no += 1
        mode = "TRUCK" if domestic else ("AIR" if random.random() < 0.25 else "SEA")
        etd = promised - timedelta(days=(1 if domestic else (4 if mode == "AIR" else lead // 2)))
        eta = promised
        atd = etd + timedelta(days=random.randint(0, 2))
        if status == "RECEIVED":
            ata = eta + timedelta(days=delay)
            sstatus = "DELIVERED"
        elif status == "DELAYED":
            ata = None
            sstatus = planted["ship_status"] if planted else random.choice(["IN_TRANSIT", "CUSTOMS_HOLD"])
        else:
            ata = None
            sstatus = "IN_TRANSIT" if atd <= TODAY else "BOOKED"
        reason = None
        if delay:
            reason = planted["reason"] if planted else random.choice(["선복 부족", "공급사 생산지연", "기상 악화", "서류 미비", "항만 적체"])
        sid = f"SHP-2026-{ship_no:04d}"
        shipments.append(dict(shipment_id=sid, po_id=po_id, supplier_id=sup["supplier_id"], mode=mode,
                              forwarder=random.choice(forwarders[mode]), etd=etd, eta=eta, atd=atd, ata=ata,
                              status=sstatus, delay_days=delay, delay_reason=reason,
                              bl_no=None if domestic else f"{mode[0]}BL{random.randint(100000, 999999)}"))
        if not domestic:
            for it, qty, price in lines:
                decl_no += 1
                hs = ITEM[it]["hs_code"]
                coo_req = sup["country"] in ("China", "Vietnam", "Taiwan", "Thailand", "Malaysia", "India")
                coo_att = True
                dstatus = "CLEARED" if sstatus == "DELIVERED" else ("FILED" if sstatus == "IN_TRANSIT" else "DRAFT")
                hold = None
                if sstatus == "CUSTOMS_HOLD":
                    dstatus = "HOLD"
                    coo_att = False
                    hold = "원산지증명서 미첨부 — FTA 협정세율 적용 보류"
                if planted and it == planted.get("hs_item"):
                    hs = planted["wrong_hs"]
                    hold = "HS 코드 불일치 (신고 8536.69 / 품목마스터 8536.90) 및 원산지증명 미첨부"
                decls.append(dict(decl_id=f"DCL-2026-{decl_no:05d}", shipment_id=sid, direction="IMPORT", item_id=it,
                                  declared_hs_code=hs, origin_country=sup["country"], fta_applied=coo_req,
                                  coo_required=coo_req, coo_attached=coo_att, invoice_value_usd=round(qty * price, 2),
                                  duty_rate=0.0 if coo_req and coo_att else 8.0, status=dstatus, hold_reason=hold,
                                  filed_date=atd if dstatus != "DRAFT" else None))
    return po_id


# 배경 발주 120건 (최근 150일)
PO_SUPPLIERS = [s for s in suppliers if s["supplier_id"] in ITEMS_BY_SUP]
for _ in range(118):
    sup = random.choice(PO_SUPPLIERS)
    make_po(sup, TODAY - timedelta(days=random.randint(1, 150)))

# G1/G2: PO-2026-0117 — 부산 세관 HOLD 9일 지연
sup_cn3 = next(s for s in suppliers if s["supplier_id"] == "SUP-CN-003")
g1_po = make_po(sup_cn3, TODAY - timedelta(days=28),
                planted=dict(status="DELAYED", delay=9, ship_status="CUSTOMS_HOLD",
                             reason="부산세관 서류심사 보류(원산지증명 미첨부)", hs_item=None))
# 강제로 PO-2026-0117 로 이름을 맞춘다 (118 + 1 = 119 이므로 바꿔 끼운다)
for coll in (pos, po_lines, shipments):
    for r in coll:
        if r["po_id"] == "PO-2026-0117":
            r["po_id"] = "__SWAP__"
    for r in coll:
        if r["po_id"] == g1_po:
            r["po_id"] = "PO-2026-0117"
    for r in coll:
        if r["po_id"] == "__SWAP__":
            r["po_id"] = g1_po
for r in pos:
    if r["po_id"] == "PO-2026-0117":
        r.update(contract_id="CT-2025-011", priority="HIGH", promised_date=TODAY - timedelta(days=4))
# 그 라인에 ITM-PCB-004 가 반드시 들어가게 한다
g1_lines = [l for l in po_lines if l["po_id"] == "PO-2026-0117"]
if not any(l["item_id"] == "ITM-PCB-004" for l in g1_lines):
    g1_lines[0]["item_id"] = "ITM-PCB-004"
    g1_lines[0]["qty_ordered"] = 6000
    g1_lines[0]["unit_price_usd"] = 5.62
g1_ship = next(s for s in shipments if s["po_id"] == "PO-2026-0117")
g1_ship.update(mode="SEA", forwarder="KMTC", eta=TODAY - timedelta(days=4), atd=TODAY - timedelta(days=13),
               status="CUSTOMS_HOLD", delay_days=9, bl_no="SBL778231")
# 기존 자동 생성 신고서 제거 후 심은 신고서로 교체
decls = [d for d in decls if d["shipment_id"] != g1_ship["shipment_id"]]
for idx, l in enumerate(g1_lines):
    decl_no += 1
    it = l["item_id"]
    decls.append(dict(decl_id=f"DCL-2026-{decl_no:05d}", shipment_id=g1_ship["shipment_id"], direction="IMPORT", item_id=it,
                      declared_hs_code=ITEM[it]["hs_code"], origin_country="China", fta_applied=True,
                      coo_required=True, coo_attached=False, invoice_value_usd=round(l["qty_ordered"] * l["unit_price_usd"], 2),
                      duty_rate=8.0, status="HOLD", hold_reason="한-중 FTA 원산지증명서(C/O) 미첨부 — 협정세율 적용 보류",
                      filed_date=TODAY - timedelta(days=5)))
# G2: 별도 수출 신고 — ITM-CON-002 HS 불일치 (대성전자 국내 → 수출 FG 에 포함, 여기선 수입 신고 중 하나를 꾸민다)
decl_no += 1
decls.append(dict(decl_id=f"DCL-2026-{decl_no:05d}", shipment_id=None, direction="EXPORT", item_id="ITM-CON-002",
                  declared_hs_code="8536.69", origin_country="Korea", fta_applied=True, coo_required=True,
                  coo_attached=True, invoice_value_usd=5700.00, duty_rate=0.0, status="REJECTED",
                  hold_reason="HS 코드 불일치: 신고 8536.69 / 품목마스터 8536.90 — 정정신고 필요", filed_date=TODAY - timedelta(days=2)))
# 수출 신고 배경 (완제품)
for k in range(40):
    decl_no += 1
    fg = random.choice(FG_ITEMS)
    decls.append(dict(decl_id=f"DCL-2026-{decl_no:05d}", shipment_id=None, direction="EXPORT", item_id=fg["item_id"],
                      declared_hs_code=fg["hs_code"], origin_country="Korea", fta_applied=random.random() < 0.7,
                      coo_required=True, coo_attached=True, invoice_value_usd=round(random.randint(300, 2000) * fg["std_cost_usd"] * 1.3, 2),
                      duty_rate=0.0, status=random.choice(["CLEARED", "CLEARED", "CLEARED", "FILED"]), hold_reason=None,
                      filed_date=TODAY - timedelta(days=random.randint(1, 120))))

PO_COLS = ["po_id", "supplier_id", "contract_id", "order_date", "promised_date", "status", "total_amount_usd", "buyer", "priority"]
POL_COLS = ["po_id", "item_id", "qty_ordered", "qty_received", "unit_price_usd", "line_status"]
SHP_COLS = ["shipment_id", "po_id", "supplier_id", "mode", "forwarder", "etd", "eta", "atd", "ata", "status", "delay_days", "delay_reason", "bl_no"]
DCL_COLS = ["decl_id", "shipment_id", "direction", "item_id", "declared_hs_code", "origin_country", "fta_applied", "coo_required",
            "coo_attached", "invoice_value_usd", "duty_rate", "status", "hold_reason", "filed_date"]

# ── 재고 일별 (90일 × 품목 × 창고) ───────────────────────────────────────
inv = []
for it in items:
    usage = max(1.0, it["safety_stock"] / random.uniform(12, 25))
    for wh in ("WH-ANSAN", "WH-BUSAN"):
        share = 0.65 if wh == "WH-ANSAN" else 0.35
        level = it["safety_stock"] * random.uniform(1.6, 2.4) * share
        for d in range(90, -1, -1):
            day = TODAY - timedelta(days=d)
            level -= usage * share * random.uniform(0.7, 1.3)
            if level < it["safety_stock"] * share * 1.1 and random.random() < 0.35:
                level += it["moq"] * share * random.randint(1, 2)
            level = max(0, level)
            on_hand = int(level)
            # G3: ITM-PCB-004 는 최근 10일 급락 → 안전재고 이탈
            if it["item_id"] == "ITM-PCB-004":
                if d <= 12:
                    on_hand = int((it["safety_stock"] * 0.95 - (12 - d) * usage * 0.9) * share)
                    on_hand = max(on_hand, int(60 * share))
            inv.append(dict(snapshot_date=day, item_id=it["item_id"], warehouse=wh, on_hand_qty=on_hand,
                            reserved_qty=int(on_hand * random.uniform(0.05, 0.3)),
                            in_transit_qty=0, avg_daily_usage=round(usage * share, 2)))
# ITM-PCB-004 운송중 = 6000 (G1 선적)
for r in inv:
    if r["item_id"] == "ITM-PCB-004" and r["warehouse"] == "WH-BUSAN" and r["snapshot_date"] >= TODAY - timedelta(days=13):
        r["in_transit_qty"] = 6000
INV_COLS = ["snapshot_date", "item_id", "warehouse", "on_hand_qty", "reserved_qty", "in_transit_qty", "avg_daily_usage"]

# ── 고객 주문 / 클레임 ───────────────────────────────────────────────────
sos, claims = [], []
for n in range(1, 150):
    cus = random.choice(customers)
    fg = random.choice(FG_ITEMS)
    od = TODAY - timedelta(days=random.randint(1, 120))
    req = od + timedelta(days=cus["sla_days"] + random.randint(0, 10))
    status = "DELIVERED" if req < TODAY - timedelta(days=2) else random.choice(["CONFIRMED", "IN_PRODUCTION", "SHIPPED"])
    sos.append(dict(so_id=f"SO-2026-{n:04d}", customer_id=cus["customer_id"], item_id=fg["item_id"], order_date=od,
                    requested_date=req, confirmed_date=req, qty=random.randint(300, 3000), status=status, risk_note=None))
# G6: SO-2026-0412 — 아틀라스 오토모티브, SPC-200, 납기 리스크 (PCB-004 부족)
sos.append(dict(so_id="SO-2026-0412", customer_id="CUS-004", item_id="ITM-FG-001", order_date=TODAY - timedelta(days=30),
                requested_date=TODAY + timedelta(days=9), confirmed_date=TODAY + timedelta(days=9), qty=2400, status="AT_RISK",
                risk_note="전원모듈 HDI PCB(ITM-PCB-004) 입고 지연 — PO-2026-0117 세관 보류"))
sos.append(dict(so_id="SO-2026-0418", customer_id="CUS-001", item_id="ITM-FG-001", order_date=TODAY - timedelta(days=20),
                requested_date=TODAY + timedelta(days=16), confirmed_date=TODAY + timedelta(days=16), qty=1800, status="IN_PRODUCTION",
                risk_note=None))
SO_COLS = ["so_id", "customer_id", "item_id", "order_date", "requested_date", "confirmed_date", "qty", "status", "risk_note"]

cats = ["납기문의", "품질불량", "수량오류", "RMA"]
for n in range(1, 31):
    so = random.choice(sos[:-2])
    claims.append(dict(ticket_id=f"TK-2026-{n:04d}", customer_id=so["customer_id"], so_id=so["so_id"], item_id=so["item_id"],
                       opened_date=so["order_date"] + timedelta(days=random.randint(3, 30)), category=random.choice(cats),
                       severity=random.choice(["LOW", "MEDIUM", "HIGH"]), status=random.choice(["OPEN", "CLOSED", "CLOSED"]),
                       root_cause=random.choice([None, "포장 파손", "SMT 납땜 불량", "선적 수량 착오", "운송 지연"]),
                       linked_po_id=None, linked_shipment_id=None))
claims.append(dict(ticket_id="TK-2026-0031", customer_id="CUS-004", so_id="SO-2026-0412", item_id="ITM-FG-001",
                   opened_date=TODAY - timedelta(days=1), category="납기문의", severity="HIGH", status="OPEN",
                   root_cause=None, linked_po_id="PO-2026-0117", linked_shipment_id=g1_ship["shipment_id"]))
TK_COLS = ["ticket_id", "customer_id", "so_id", "item_id", "opened_date", "category", "severity", "status", "root_cause",
           "linked_po_id", "linked_shipment_id"]

# ── 출력 ──────────────────────────────────────────────────────────────────
parts = ["SET search_path TO supplychain;",
         ins("scm_supplier", suppliers, SUP_COLS),
         ins("scm_item", items, ITEM_COLS),
         ins("scm_customer", customers, CUS_COLS),
         ins("scm_contract", contracts, CT_COLS),
         ins("scm_purchase_order", pos, PO_COLS),
         ins("scm_po_line", po_lines, POL_COLS),
         ins("scm_shipment", shipments, SHP_COLS),
         ins("scm_customs_declaration", decls, DCL_COLS),
         ins("scm_inventory_daily", inv, INV_COLS),
         ins("scm_customer_order", sos, SO_COLS),
         ins("scm_claim_ticket", claims, TK_COLS)]
OUT.write_text("\n\n".join(parts), encoding="utf-8")
print(f"suppliers={len(suppliers)} items={len(items)} customers={len(customers)} contracts={len(contracts)} "
      f"pos={len(pos)} po_lines={len(po_lines)} shipments={len(shipments)} decls={len(decls)} "
      f"inventory={len(inv)} so={len(sos)} claims={len(claims)}  G1 shipment={g1_ship['shipment_id']}")
