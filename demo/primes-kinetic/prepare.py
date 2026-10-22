"""PriMES 반복 수주 — 온톨로지 준비 (Studio 정의 + 시스템 조회로 인스턴스 적재 + 발행).

인스턴스는 **등록된 PriMES 시스템의 조회 API**(키네틱 query 경로, GET 전용)로 읽어 그래프에 적재한다 —
데이터를 따로 옮기지 않는다. 액션은 사람이 Studio 「액션」 탭에서 설계하는 것과 같은 내용을 여기 적는다.

설계 원칙
- 대상은 **변하지 않는 기준 정보**: 수주 → 고객, 발주 → 원자재, 작업지시·금형 장착 → 고른 금형.
  방금 만든 수주는 그래프에 없으므로 수주 번호·id 는 파라미터로 넘긴다.
- **업무 규칙은 온톨로지 속성**: 고객의 승인 단조 설비, 원자재의 승인 공급처. 발주 정책이 승인 공급처를 강제한다.
- 쓰기 단계마다 **보상**: 수주 취소 · 발주 삭제 · 작업지시 취소 · 금형 탈착.

실행: ontology-studio 루트에서 env 를 맞춰 (`run_studio.sh prepare` 가 한다).
"""

import json
import os
import sys

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "kinetic-mes"))
import seed  # noqa: E402

from backend.src.modules.agent_session import session_store as ss  # noqa: E402
from backend.src.modules.ontology import publish  # noqa: E402

SCHEMA = "PriMES 반복 수주"
#: 업무 규칙 — 기존 PriMES 시연에서 사람이 가르친 판단을 온톨로지 속성으로 둔다
APPROVED_FORGE_EQUIPMENT = {"C001": "FM12"}          # 대성오토 → 단조는 FM12


def query(system: str, op: str, path: dict | None = None, q: dict | None = None) -> list:
    h = {"Authorization": f"Bearer {seed.token('studio.loader', ['kinetic_admin'])}"}
    r = httpx.post(f"{seed.KINETIC_API}/api/kinetic/systems/{system}/query", headers=h, timeout=30,
                   json={"operation_id": op, "path_params": path or {}, "query": q or {}})
    if r.status_code != 200:
        raise SystemExit(f'{system}.{op} → {r.status_code} {r.text[:300]}')
    body = r.json()
    if not body.get("ok"):
        raise SystemExit(f"{system}.{op} 조회 실패: {body}")
    d = body["data"]
    return d.get("items", d) if isinstance(d, dict) else d


def view(system: str, ctx: str, typ: str, **f) -> list:
    return query(system, f"{ctx}ListView", {"type": typ}, {"size": 500, **{f"f.{k}": v for k, v in f.items()}})


def load_instances() -> dict:
    """PriMES → 그래프. 시스템 레코드 id 를 `id` 로 둔다 (액션 경로 파라미터에 쓴다)."""
    customers = view("primes-masterdata", "masterdata", "customer")
    products = view("primes-masterdata", "masterdata", "product")
    boms = view("primes-masterdata", "masterdata", "bom")
    molds = view("primes-mold", "mold", "mold")
    equipments = view("primes-equipment", "equipment", "equipment")
    routings = view("primes-production", "production", "routing")
    sales_cust = [c for c in customers if str(c.get("customerType", "")).startswith("매출") or c["code"].startswith("C")]
    suppliers = [c for c in customers if c not in sales_cust]
    raws = [p for p in products if p["code"].startswith("RM-")]
    goods = [p for p in products if not p["code"].startswith(("RM-", "WIP-"))]
    with seed.driver() as d, d.session() as s:
        s.run("MATCH (n) WHERE any(l IN labels(n) WHERE l IN ['Customer','Supplier','Product','RawMaterial','Mold','Equipment']) "
              "DETACH DELETE n").consume()
        s.run("UNWIND $rows AS r CREATE (:Customer {id:r.id, code:r.code, name:r.name, approvedForgeEquipment:r.eq})",
              rows=[{**c, "eq": APPROVED_FORGE_EQUIPMENT.get(c["code"], "")} for c in sales_cust]).consume()
        s.run("UNWIND $rows AS r CREATE (:Supplier {id:r.id, code:r.code, name:r.name})", rows=suppliers).consume()
        s.run("UNWIND $rows AS r CREATE (:Product {id:r.id, code:r.code, name:r.name, unit:r.unit, unitPrice:toFloat(r.unitPrice)})",
              rows=goods).consume()
        s.run("UNWIND $rows AS r CREATE (:RawMaterial {id:r.id, code:r.code, name:r.name, unit:r.unit, "
              "unitPrice:toFloat(r.unitPrice), approvedSupplier:r.customerName})", rows=raws).consume()
        s.run("UNWIND $rows AS r CREATE (:Mold {id:r.id, code:r.code, name:r.name, status:r.status, cavity:toInteger(r.cavity), "
              "lifeShots:toInteger(r.lifeShots), remainingShots:toInteger(r.remainingShots), lifeStatus:r.lifeStatus, "
              "processCode:r.processCode, productCodes:r.productCodes, location:r.location, "
              "mountedWo:coalesce(r.mountedWo, ''), mountedEquipment:coalesce(r.equipmentCode, '')})", rows=molds).consume()
        s.run("UNWIND $rows AS r CREATE (:Equipment {id:r.id, code:r.code, name:r.name, status:r.status, processCode:r.processCode, line:r.line})",
              rows=equipments).consume()
        s.run("MATCH (c:Customer), (p:Product) WHERE p.code IN $pairs[c.name] MERGE (c)-[:ORDERS]->(p)",
              pairs={c["name"]: [p["code"] for p in goods if p.get("customerName") == c["name"]] for c in sales_cust}).consume()
        s.run("MATCH (m:RawMaterial), (s:Supplier) WHERE s.name = m.approvedSupplier MERGE (m)-[:SUPPLIED_BY]->(s)").consume()
        s.run("UNWIND $rows AS r MATCH (p:Product {code:r.parentCode}), (m:RawMaterial {code:r.childCode}) "
              "MERGE (p)-[x:REQUIRES]->(m) SET x.qtyPerUnit = toFloat(r.qty), x.unit = r.unit", rows=boms).consume()
        s.run("MATCH (m:Mold), (p:Product) WHERE m.productCodes CONTAINS p.code MERGE (m)-[:FORMS]->(p)").consume()
        s.run("UNWIND $rows AS r MATCH (p:Product {code:r.productCode}) UNWIND split(r.equipmentCodes, ',') AS ec "
              "MATCH (e:Equipment {code:trim(ec)}) MERGE (p)-[x:PROCESSED_ON {processCode:r.processCode, seq:toInteger(r.seq)}]->(e)",
              rows=[r for r in routings if r.get("equipmentCodes")]).consume()
        counts = {lbl: s.run(f"MATCH (n:{lbl}) RETURN count(n)").single()[0]
                  for lbl in ("Customer", "Supplier", "Product", "RawMaterial", "Mold", "Equipment")}
    return counts


def props(*rows) -> str:
    return json.dumps([dict(zip(("name", "type", "description"), r)) | ({"key": True} if i == 0 else {})
                       for i, r in enumerate(rows)], ensure_ascii=False)


def define() -> str:
    sch = ss.create_schema(SCHEMA, "PriMES 영업·구매·생산·금형을 묶은 반복 수주 온톨로지",
                           intent="대성오토의 반복 주문을 대화로 처리 — 수주, 부족 자재 발주, 금형 확인 후 작업지시, 필요하면 역순 취소",
                           golden_questions=json.dumps(["휠 허브 플랜지 단조 금형별 남은 타수는?",
                                                        "휠 허브 플랜지를 만드는 데 필요한 원자재와 공급업체는?"], ensure_ascii=False))
    sid = sch["id"]
    ss.update_schema_brief(sid, sch["intent"], json.dumps(sch["golden_questions"], ensure_ascii=False), json.dumps([
        "대성오토가 휠 허브 플랜지 1,200개를 10월 26일 납기로 주문했어. 수주 등록해 줘.",
        "이 수주 때문에 부족한 원자재를 승인 업체에 발주해 줘.",
        "이 수주의 단조 작업지시를 내 줘. 금형 수명이 모자라면 대안을 보여 주고 내가 고른 대로 진행해.",
        "방금 처리한 수주 건을 모두 취소해 줘."], ensure_ascii=False))
    ss.add_class_to_schema(sid, "Customer", "매출 고객 (PriMES 기준정보). 승인 단조 설비는 이 고객 주문의 단조 작업지시에 쓴다.", props(
        ("code", "string", "고객 코드"), ("name", "string", "고객명"), ("id", "string", "PriMES 레코드 id"),
        ("approvedForgeEquipment", "string", "승인 단조 설비 — 업무 규칙")))
    ss.add_class_to_schema(sid, "Supplier", "매입 공급처", props(("code", "string", ""), ("name", "string", ""), ("id", "string", "")))
    ss.add_class_to_schema(sid, "Product", "완제품 (판매 품목)", props(
        ("code", "string", "품목 코드"), ("name", "string", "품목명"), ("unit", "string", ""), ("unitPrice", "float", "판매 단가"),
        ("id", "string", "")))
    ss.add_class_to_schema(sid, "RawMaterial", "원자재. 승인 공급처로만 발주한다 — 최저가 업체가 아니다.", props(
        ("code", "string", ""), ("name", "string", ""), ("unit", "string", ""), ("unitPrice", "float", "기준 단가"),
        ("approvedSupplier", "string", "승인 공급처 — 업무 규칙"), ("id", "string", "")))
    ss.add_class_to_schema(sid, "Mold", "금형. 가용 타수 = 남은 타수 − 이 금형을 쓰는 발행(ISSUED) 작업지시 계획수량 × 캐비티당 1타. "
                                         "남은 타수는 변하므로 계획 전에 PriMES 금형 조회로 다시 확인한다.", props(
        ("code", "string", "금형 코드"), ("name", "string", ""), ("remainingShots", "int", "남은 타수 (적재 시점)"),
        ("lifeShots", "int", "수명 타수"), ("cavity", "int", ""), ("status", "string", ""), ("lifeStatus", "string", ""),
        ("processCode", "string", ""), ("id", "string", "PriMES 금형 id — 장착 경로에 쓴다"),
        ("mountedWo", "string", "현재 장착된 작업지시 (보상 시 이 장착으로 되돌린다)"), ("mountedEquipment", "string", "현재 장착 설비")))
    ss.add_class_to_schema(sid, "Equipment", "설비", props(
        ("code", "string", ""), ("name", "string", ""), ("status", "string", ""), ("processCode", "string", ""), ("line", "string", ""),
        ("id", "string", "")))
    for name, a, b, desc in (("ORDERS", "Customer", "Product", "고객이 주문하는 품목"),
                             ("SUPPLIED_BY", "RawMaterial", "Supplier", "승인 공급처"),
                             ("REQUIRES", "Product", "RawMaterial", "BOM — qtyPerUnit"),
                             ("FORMS", "Mold", "Product", "금형이 성형하는 품목"),
                             ("PROCESSED_ON", "Product", "Equipment", "라우팅 공정 설비")):
        ss.add_relationship_to_schema(sid, name, a, b, desc)

    ss.upsert_class_action(
        sid, "Customer", "placeRepeatOrder",
        description="이 고객의 수주를 PriMES 영업에 등록한다. 대상은 고객 코드(code, 예: C001)로 지정한다 — 레코드 id 가 아니다. "
                    "품목·수량·단가·납기를 받는다. 단가는 품목(Product) 판매 단가를 쓴다. 실행 결과의 응답 id·orderNo 가 이후 발주·작업지시의 수주 번호다.",
        parameters={"type": "object", "required": ["productCode", "productName", "qty", "unitPrice", "dueDate"], "properties": {
            "productCode": {"type": "string"}, "productName": {"type": "string"}, "qty": {"type": "number"},
            "unitPrice": {"type": "number"}, "dueDate": {"type": "string", "description": "YYYY-MM-DD"},
            "remark": {"type": "string"}}},
        key_property="code", effect="write", confirm_threshold=1, max_targets=1,
        steps=[{"name": "so", "title": "PriMES 수주 등록", "system": "primes-sales", "operation_id": "placeSalesOrder",
                "arg_mapping": {"body.customerCode": "$this.code", "body.customerName": "$this.name", "body.dueDate": "$params.dueDate",
                                "body.salesRep": "$actor.sub", "body.remark": "$params.remark",
                                "body.lines.0.productCode": "$params.productCode", "body.lines.0.productName": "$params.productName",
                                "body.lines.0.itemNo": "$params.productCode", "body.lines.0.qty": "$params.qty",
                                "body.lines.0.unitPrice": "$params.unitPrice", "body.lines.0.dueDate": "$params.dueDate"},
                "compensation": {"system": "primes-sales", "operation_id": "cancelSalesOrder",
                                 "arg_mapping": {"path.id": "$steps.so.response.id", "query.reason": "$cancel.reason"}}}],
        policy=[{"roles": ["sales_rep"], "description": "영업 담당이 수주를 등록한다"}])
    ss.upsert_class_action(
        sid, "RawMaterial", "orderMaterial",
        description="이 원자재를 PriMES 구매에 발주한다. 대상은 원자재 코드(예: RM-STL-45C). 공급처는 원자재의 승인 공급처(approvedSupplier)만 허용된다(정책 — 최저가 업체 아님). "
                    "수량 결정(필수): query_system(primes-purchase, getMaterialRequirements) 에서 이 원자재의 shortageQty 를 읽는다 — 방금 등록한 수주 번호가 orderNos 에 "
                    "아직 없으면 몇 초 뒤 다시 조회한다(이벤트 반영 지연). 수량은 shortageQty 를 500KG 단위로 올린 값, 단가는 원자재 unitPrice, 금액 = 수량 × 단가. "
                    "대상 원자재는 **이번 수주 품목의 BOM(Product -REQUIRES-> RawMaterial) 자재만** — 다른 수주 때문에 부족한 자재는 발주하지 않는다. "
                    "발주번호는 PO-YYYYMMDD-NNN, 발주일은 오늘, 납기는 따로 말이 없으면 오늘 + 3일(묻지 않는다).",
        parameters={"type": "object", "required": ["poNo", "orderDate", "dueDate", "supplierName", "qty", "unitPrice", "amount"], "properties": {
            "poNo": {"type": "string", "description": "PO-YYYYMMDD-NNN"}, "orderDate": {"type": "string"}, "dueDate": {"type": "string"},
            "supplierName": {"type": "string"}, "qty": {"type": "number"}, "unitPrice": {"type": "number"},
            "amount": {"type": "number"}, "remark": {"type": "string"}}},
        key_property="code", effect="write", confirm_threshold=1, max_targets=1,
        steps=[{"name": "po", "title": "PriMES 구매 발주", "system": "primes-purchase", "operation_id": "purchaseCreateRecord",
                "arg_mapping": {"path.type": "purchase-order", "body.orderNo": "$params.poNo", "body.orderDate": "$params.orderDate",
                                "body.dueDate": "$params.dueDate", "body.supplierName": "$params.supplierName",
                                "body.productCode": "$this.code", "body.productName": "$this.name", "body.qty": "$params.qty",
                                "body.receivedQty": {"$literal": 0}, "body.unitPrice": "$params.unitPrice",
                                "body.amount": "$params.amount", "body.status": "발주", "body.remark": "$params.remark"},
                "compensation": {"system": "primes-purchase", "operation_id": "purchaseDeleteRecord",
                                 "arg_mapping": {"path.type": "purchase-order", "path.id": "$steps.po.response.id"}}}],
        policy=[{"roles": ["production_planner"], "when": "params.supplierName == target.approvedSupplier",
                 "description": "승인 공급처로만 발주"}])
    ss.upsert_class_action(
        sid, "Mold", "issueForgingWorkOrder",
        description="이 금형으로 단조(FRG) 작업지시를 PriMES 생산에 발행하고 금형을 단조 설비에 장착한다. 대상은 금형 코드(예: FM540-2). 설비는 고객의 승인 단조 설비(approvedForgeEquipment). "
                    "계획 전 금형 가용 타수 확인(필수, 그래프 값은 낡을 수 있다): ① query_system(primes-mold, moldListView, path {type: mold}, query {q: 금형코드}) 의 remainingShots "
                    "② query_system(primes-production, productionListView, path {type: work-order}, query {f.moldCode: 금형코드, f.status: ISSUED, size: 200}) 의 planQty 합 = 이미 예약된 타수 "
                    "③ 가용 = remainingShots − 예약 (캐비티 1 = 1개당 1타). 가용 < 이번 수량이면 그 금형은 쓸 수 없다 — 같은 품목을 성형하는 다른 금형(대체 금형, 같은 방식으로 가용 계산), "
                    "분할 생산, 납기 조정을 숫자와 함께 제시하고 사람의 선택을 기다린 뒤, 고른 금형을 대상으로 계획한다. 생산관리자 승인이 필요하다.",
        parameters={"type": "object", "required": ["salesOrderId", "salesOrderNo", "customerName", "productCode", "productName",
                                                   "planQty", "startDate", "dueDate", "equipmentCode"], "properties": {
            "salesOrderId": {"type": "string"}, "salesOrderNo": {"type": "string"}, "customerName": {"type": "string"},
            "productCode": {"type": "string"}, "productName": {"type": "string"}, "planQty": {"type": "number"},
            "startDate": {"type": "string"}, "dueDate": {"type": "string"}, "equipmentCode": {"type": "string"},
            "remark": {"type": "string"}}},
        key_property="code", effect="write", confirm_threshold=0, max_targets=1,
        steps=[{"name": "wo", "title": "PriMES 단조 작업지시 발행", "system": "primes-production", "operation_id": "issueWorkOrder",
                "arg_mapping": {"body.productCode": "$params.productCode", "body.productName": "$params.productName",
                                "body.planQty": "$params.planQty", "body.startDate": "$params.startDate", "body.dueDate": "$params.dueDate",
                                "body.salesOrderId": "$params.salesOrderId", "body.salesOrderNo": "$params.salesOrderNo",
                                "body.customerName": "$params.customerName", "body.moldCode": "$this.code", "body.remark": "$params.remark",
                                "body.processes.0.processSeq": {"$literal": 10}, "body.processes.0.processCode": "FRG",
                                "body.processes.0.processName": "단조", "body.processes.0.equipmentCode": "$params.equipmentCode",
                                "body.processes.0.finalProcess": {"$literal": False}},
                "compensation": {"system": "primes-production", "operation_id": "cancelWorkOrders",
                                 "arg_mapping": {"body.ids": "$steps.wo.response.ids"}}},
               {"name": "mount", "title": "PriMES 금형 장착", "system": "primes-mold", "operation_id": "mountMold",
                "arg_mapping": {"path.id": "$this.id", "body.woNo": "$steps.wo.response.workOrders.0.woNo",
                                "body.equipmentCode": "$params.equipmentCode"},
                # 보상은 「떼기」가 아니라 **원래 상태로**: 실행 직전에 장착돼 있던 작업지시·설비로 다시 장착한다.
                # (무조건 탈착하면 이전 장착까지 풀린다 — 실측. 원래 장착이 없던 금형이면 이 보상은 실패해 사람 처리로 간다.)
                "compensation": {"system": "primes-mold", "operation_id": "mountMold",
                                 "arg_mapping": {"path.id": "$this.id", "body.woNo": "$before.mountedWo",
                                                 "body.equipmentCode": "$before.mountedEquipment"}}}],
        policy=[{"roles": ["production_planner"], "when": "target.status != '폐기'", "description": "생산관리가 발행 (폐기 금형 제외)"}])
    return sid


if __name__ == "__main__":
    print("instances:", load_instances())
    sid = define()
    r = publish.publish(sid)
    print(json.dumps({"schema_id": sid, "status": r["status"], "counts": r.get("counts"),
                      "kinetic_refresh": r.get("kinetic_refresh")}, ensure_ascii=False))
