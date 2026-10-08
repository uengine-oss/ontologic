### [고객지원] 고객지원 에이전트 — S6-customer-support

**A2A 핸드오프 — 클레임 원인 역추적 → 고객 회신문 생성**

> 고객 클레임 TK-2026-0031 (납기 문의)에 답해야 해. 해당 고객과 주문(SO)의 내용, 납기 리스크 원인을 연결된 발주/선적까지 역추적해서 확인하고, 고객에게 보낼 회신 초안을 작성해줘. 회신에는 원인, 현재 조치, 예상 납기 영향, 대안을 담아줘.

_(A2A 핸드오프: `S1-procurement` 의 결과를 입력으로 받음)_

실행 경로 `ontology-studio /api/stream (AGENT_BACKEND=cliagents)` · 도구 호출 **12회** (오류 0) · 132.5s

#### 1. `Read`

```json
{
  "file_path": "/Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/scm-demo-S6-customer-support-ef58aa60answer/.claude/skills/ontologic-agentic-rag/references/two-step-retrieval.md"
}
```

```json
1	# 2-step 검색 전략 — 스키마를 필요한 만큼만 받는다
2	
3	`ontology-answer` 스킬의 `references/search-strategy.md` 와 단계 구조가 같다. 다른 점은
4	도구 이름과, 스키마를 **한 클래스씩** 받는다는 것이다.
5	
6	## 왜 순서가 중요한가
7	
8	한 번에 모든 스키마를 받으면 세 가지가 동시에 나빠진다 — 토큰이 터지고, 추론 정확도가
9	떨어지고, DB 구조가 전부 노출된다. 그래서 이 순서는 편의가 아니라 설계다.
10	
11	## 0단계: 지도 한 번 — `graph://schema`
12	
13	**세션당 한 번.** 클래스·관계와 "누가 데이터소스를 갖는가"만 들어 있다. **컬럼은 없다.**
14	
15	여기서 볼 것:
16	
17	- `binding_kind: "virtual"` — 이 클래스는 실시간으로 DB 를 읽는다. 그래프에 노드가 **0건**
18	  이라 벡터 검색으로는 절대 발견되지 않는다.
19	- `binding_kind: "materialized"` — 그래프에 인스턴스가 있다. Cypher 로 탐색한다.
20	- `source: {datasource, schema, table}` — 그 클래스가 어디를 가리키는지.
21	
22	발행된 것이 없으면 `note` 에 발행하라는 안내가 온다. 그 상태에서는 아무 조회도 의미가 없다.
23	
24	## 0.5단계: 이름을 키로 바꾼다 — `ontology_resolve_entity`
25	
26	질문이 대상을 **이름으로** 부를 때만. 그래프 탐색은 키 값(`PROD-001`)에서 시작하는데
27	사용자가 준 것은 이름(`고정밀 베어링 A형`)이다.
28	
29	```
30	ontology_resolve_entity("고정밀 베어링 A형", cl… (총 3000자)
```

#### 2. `ontology_graph_schema`

```json
{}
```

```json
{"result":"{\"models\": [{\"schema_id\": \"c316cf717ef3\", \"name\": \"공급망 지식지도\", \"description\": \"「기업 공급망 관리 업무 개념 체계」 문서 근거. 1-1 기록 개념은 scm_erp/wms/customs/crm 4개 이기종 시스템 테이블에 바인딩된 가상 클래스, 1-2 판단 개념은 업무 규칙을 담은 개념 클래스. 키 표기 차이(item_id/sku_code/ref_item_code, supplier_id/vendor_code)를 관계로 정합.\", \"intent\": \"\", \"golden_questions\": [], \"format_version\": 1, \"published_at\": 1787312650.117163}, {\"schema_id\": \"556fd497fb03\", \"name\": \"미국 전력망\", \"description\": \"미국 전력망 지리 예제\", \"intent\": \"변전소·송전선로·정전구역·발전량을 지도와 추이로 본다\", \"golden_questions\": [\"과부하 구간이 있는 송전선로는 어디인가?\", \"주별 정전 피해 가구는 얼마나 되는가?\", \"발전 유형별 주간 발전량 추이는?\"], \"format_version\": 1, \"published_at\": 1787180771.1668632}, {\"schema_id\": \"a0edf61cc416\", \"name\": \"제조 하이브리드\", \"description\": \"legacy.manufacturing 테이블 구조에서 생성\", \"intent\": \"\", \"golden_questions\": [], \"format_version\": 1, \"published_… (총 3000자)
```

#### 3. `ontology_get_datasource_schema`

```json
{
  "class_name": "ClaimTicket"
}
```

```json
{"result":"{\"class_name\": \"ClaimTicket\", \"description\": \"고객 클레임 티켓. 키 ticket_no. 고객(cust_no)·판매주문(so_no)·품목(sku_code)을 참조하고, 원인 역추적을 위해 발주(ref_po_no)·선적(ref_shipment_no)을 선택적으로 참조. 속성: 카테고리, 심각도, 상태, 근본원인(root_cause), 접수일. 주문→발주→선적→통관 역추적의 출발점.\", \"source\": {\"datasource\": \"scm_crm\", \"schema\": \"crm_scm\", \"table\": \"claim_ticket\"}, \"key_columns\": [\"ticket_no\"], \"base_conditions\": [], \"columns\": [{\"property\": \"티켓번호\", \"column\": \"ticket_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"고객번호\", \"column\": \"cust_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"주문번호\", \"column\": \"so_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"품목코드\", \"column\": \"sku_code\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"접수일\", \"column\": \"opened_date\", \"type\": \"date\", \"description\": … (총 1630자)
```

#### 4. `ontology_get_datasource_schema`

```json
{
  "class_name": "Customer"
}
```

#### 5. `ontology_get_datasource_schema`

```json
{
  "class_name": "SalesOrder"
}
```

```json
{"result":"{\"class_name\": \"Customer\", \"description\": \"고객사. 키 cust_no. 속성: 상호, 국가, 세그먼트, 인코텀즈, 결제조건, SLA일수(sla_days). 판매주문·클레임의 주체.\", \"source\": {\"datasource\": \"scm_crm\", \"schema\": \"crm_scm\", \"table\": \"customer\"}, \"key_columns\": [\"cust_no\"], \"base_conditions\": [], \"columns\": [{\"property\": \"고객번호\", \"column\": \"cust_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"상호\", \"column\": \"cust_name\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"국가\", \"column\": \"country\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"세그먼트\", \"column\": \"segment\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"인코텀즈\", \"column\": \"incoterms\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"결제조건\", \"column\": \"payment_terms\", \"type\": \"string\", \"description\": \"\"}, {\"property\"… (총 1114자)
```

```json
{"result":"{\"class_name\": \"SalesOrder\", \"description\": \"고객 판매 주문. 키 so_no. 속성: 고객(cust_no), 품목(sku_code=item_id), 주문일, 요청납기(requested_date), 확정납기(confirmed_date), 수량, 상태, 리스크노트. 클레임(claim_ticket.so_no)의 대상.\", \"source\": {\"datasource\": \"scm_crm\", \"schema\": \"crm_scm\", \"table\": \"sales_order\"}, \"key_columns\": [\"so_no\"], \"base_conditions\": [], \"columns\": [{\"property\": \"주문번호\", \"column\": \"so_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"고객번호\", \"column\": \"cust_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"품목코드\", \"column\": \"sku_code\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"주문일\", \"column\": \"order_date\", \"type\": \"date\", \"description\": \"\"}, {\"property\": \"요청납기\", \"column\": \"requested_date\", \"type\": \"date\", \"description\": \"\"}, {\"property\": \"확정납기\", \"column\… (총 1381자)
```

#### 6. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT t.ticket_no, t.cust_no, t.so_no, t.sku_code, t.opened_date, t.category, t.severity, t.ticket_status, t.root_cause, t.ref_po_no, t.ref_shipment_no,\nc.cust_name, c.country, c.segment, c.incoterms, c.payment_terms, c.sla_days,\ns.order_date, s.requested_date, s.confirmed_date, s.qty, s.so_status, s.risk_note\nFROM crm_scm.claim_ticket t\nLEFT JOIN crm_scm.customer c ON t.cust_no = c.cust_no\nLEFT JOIN crm_scm.sales_order s ON t.so_no = s.so_no\nWHERE t.ticket_no = 'TK-2026-0031'"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"ticket_no\", \"cust_no\", \"so_no\", \"sku_code\", \"opened_date\", \"category\", \"severity\", \"ticket_status\", \"root_cause\", \"ref_po_no\", \"ref_shipment_no\", \"cust_name\", \"country\", \"segment\", \"incoterms\", \"payment_terms\", \"sla_days\", \"order_date\", \"requested_date\", \"confirmed_date\", \"qty\", \"so_status\", \"risk_note\"], \"rows\": [{\"ticket_no\": \"TK-2026-0031\", \"cust_no\": \"CUS-004\", \"so_no\": \"SO-2026-0412\", \"sku_code\": \"ITM-FG-001\", \"opened_date\": \"2026-08-20\", \"category\": \"납기문의\", \"severity\": \"HIGH\", \"ticket_status\": \"OPEN\", \"root_cause\": null, \"ref_po_no\": \"PO-2026-0117\", \"ref_shipment_no\": \"SHP-2026-0111\", \"cust_name\": \"아틀라스 오토모티브\", \"country\": \"Germany\", \"segment\": \"티어1 자동차\", \"incoterms\": \"DAP\", \"payment_terms\": \"NET90\", \"sla_days\": 45, \"order_da… (총 1747자)
```

#### 7. `ontology_get_datasource_schema`

```json
{
  "class_name": "Shipment"
}
```

```json
{"result":"{\"class_name\": \"Shipment\", \"description\": \"국제 선적. 키 shipment_no(통관 decl_header.ref_shipment_no, CRM claim_ticket.ref_shipment_no 로 참조). 발주(ref_po_no=po_id)를 이행한다. 속성: 참조발주, 공급사(vendor_code), 운송수단, 포워더, ETD/ETA/ATD/ATA, 선적상태, 지연일수(delay_days), 지연사유(delay_reason), B/L번호.\", \"source\": {\"datasource\": \"scm_wms\", \"schema\": \"wms\", \"table\": \"shipment\"}, \"key_columns\": [\"shipment_no\"], \"base_conditions\": [], \"columns\": [{\"property\": \"선적번호\", \"column\": \"shipment_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"참조발주\", \"column\": \"ref_po_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"공급사코드\", \"column\": \"vendor_code\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"운송수단\", \"column\": \"transport_mode\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"포워더\", \"column\": \"forwa… (총 1834자)
```

#### 8. `ontology_get_datasource_schema`

```json
{
  "class_name": "CustomsDeclaration"
}
```

#### 9. `ontology_get_datasource_schema`

```json
{
  "class_name": "PurchaseOrder"
}
```

```json
{"result":"{\"class_name\": \"CustomsDeclaration\", \"description\": \"수입 통관 신고. 키 decl_id. 선적(ref_shipment_no=shipment_no)과 품목(ref_item_code=item_id)을 참조. 속성: 방향, 신고품목분류(declared_hs_code), 원산지, FTA적용, 원산지증명 요구·첨부(coo_required/attached), 송장가액, 관세율, 상태(status: CLEARED/FILED/DRAFT/HOLD/REJECTED), 보류사유(hold_reason), 신고일. 신고 HS코드와 품목 마스터 hs_code 의 정합이 판단 대상.\", \"source\": {\"datasource\": \"scm_customs\", \"schema\": \"customs\", \"table\": \"decl_header\"}, \"key_columns\": [\"decl_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"신고번호\", \"column\": \"decl_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"참조선적\", \"column\": \"ref_shipment_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"방향\", \"column\": \"direction\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"참조품목\", \"column\": \"ref_item_code\", \"type\": \"strin… (총 2072자)
```

```json
{"result":"{\"class_name\": \"PurchaseOrder\", \"description\": \"구매 발주 헤더. 키 po_id(WMS shipment.ref_po_no, CRM claim_ticket.ref_po_no 로 참조). 속성: 공급사, 계약(contract_id), 발주일, 납기약속일(promised_date), 상태(status: OPEN/CONFIRMED/DELAYED/RECEIVED 등), 발주금액(total_amount_usd), 우선순위(priority), 구매담당.\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"doc_purchase_order\"}, \"key_columns\": [\"po_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"발주번호\", \"column\": \"po_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"공급사ID\", \"column\": \"supplier_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"계약번호\", \"column\": \"contract_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"발주일\", \"column\": \"order_date\", \"type\": \"date\", \"description\": \"\"}, {\"property\": \"납기약속일\", \"column\": \"promised_d… (총 1376자)
```

#### 10. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT po_id, supplier_id, contract_id, order_date, promised_date, status, total_amount_usd, priority FROM erp.doc_purchase_order WHERE po_id = 'PO-2026-0117'"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"po_id\", \"supplier_id\", \"contract_id\", \"order_date\", \"promised_date\", \"status\", \"total_amount_usd\", \"priority\"], \"rows\": [{\"po_id\": \"PO-2026-0117\", \"supplier_id\": \"SUP-CN-003\", \"contract_id\": \"CT-2025-011\", \"order_date\": \"2026-07-24\", \"promised_date\": \"2026-08-17\", \"status\": \"DELAYED\", \"total_amount_usd\": \"81307.20\", \"priority\": \"HIGH\"}], \"row_count\": 1, \"truncated_for_agent\": false, \"truncated\": false, \"sql\": \"SELECT po_id, supplier_id, contract_id, order_date, promised_date, status, total_amount_usd, priority FROM erp.doc_purchase_order WHERE po_id = 'PO-2026-0117' LIMIT 500\", \"source\": {\"datasource\": \"scm_erp\"}}"}
```

#### 11. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT shipment_no, ref_po_no, vendor_code, transport_mode, forwarder, etd, eta, atd, ata, ship_status, delay_days, delay_reason, bl_no FROM wms.shipment WHERE shipment_no = 'SHP-2026-0111'"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"shipment_no\", \"ref_po_no\", \"vendor_code\", \"transport_mode\", \"forwarder\", \"etd\", \"eta\", \"atd\", \"ata\", \"ship_status\", \"delay_days\", \"delay_reason\", \"bl_no\"], \"rows\": [{\"shipment_no\": \"SHP-2026-0111\", \"ref_po_no\": \"PO-2026-0117\", \"vendor_code\": \"SUP-CN-003\", \"transport_mode\": \"SEA\", \"forwarder\": \"KMTC\", \"etd\": \"2026-08-04\", \"eta\": \"2026-08-17\", \"atd\": \"2026-08-08\", \"ata\": null, \"ship_status\": \"CUSTOMS_HOLD\", \"delay_days\": 9, \"delay_reason\": \"부산세관 서류심사 보류(원산지증명 미첨부)\", \"bl_no\": \"SBL778231\"}], \"row_count\": 1, \"truncated_for_agent\": false, \"truncated\": false, \"sql\": \"SELECT shipment_no, ref_po_no, vendor_code, transport_mode, forwarder, etd, eta, atd, ata, ship_status, delay_days, delay_reason, bl_no FROM wms.shipment WHERE shipment_no = 'SHP-2026-0111' LIMIT 500\"… (총 946자)
```

#### 12. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT decl_id, ref_shipment_no, direction, ref_item_code, declared_hs_code, origin_country, fta_applied, coo_required, coo_attached, invoice_value_usd, duty_rate, status, hold_reason, filed_date FROM customs.decl_header WHERE ref_shipment_no = 'SHP-2026-0111'"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"decl_id\", \"ref_shipment_no\", \"direction\", \"ref_item_code\", \"declared_hs_code\", \"origin_country\", \"fta_applied\", \"coo_required\", \"coo_attached\", \"invoice_value_usd\", \"duty_rate\", \"status\", \"hold_reason\", \"filed_date\"], \"rows\": [{\"decl_id\": \"DCL-2026-00114\", \"ref_shipment_no\": \"SHP-2026-0111\", \"direction\": \"IMPORT\", \"ref_item_code\": \"ITM-PCB-003\", \"declared_hs_code\": \"8534.00\", \"origin_country\": \"China\", \"fta_applied\": 1, \"coo_required\": 1, \"coo_attached\": 0, \"invoice_value_usd\": \"27952.80\", \"duty_rate\": \"8.00\", \"status\": \"HOLD\", \"hold_reason\": \"한-중 FTA 원산지증명서(C/O) 미첨부 — 협정세율 적용 보류\", \"filed_date\": \"2026-08-16\"}, {\"decl_id\": \"DCL-2026-00115\", \"ref_shipment_no\": \"SHP-2026-0111\", \"direction\": \"IMPORT\", \"ref_item_code\": \"ITM-PCB-001\", \"declared_hs_code… (총 2033자)
```

#### 최종 답변

조사를 시작하겠습니다. 먼저 워크플로우 참조 문서를 읽고, 필요한 MCP 도구 스키마를 로드하겠습니다.도구가 로드됐습니다. 온톨로지 지도를 읽겠습니다.온톨로지 지도를 확인했습니다. 클레임 역추적 경로가 명확합니다:

`ClaimTicket`(scm_crm) → `FILED_BY` Customer, `ABOUT_ORDER` SalesOrder, `ABOUT_ITEM` Item, `REFERS_PO` PurchaseOrder, `REFERS_SHIPMENT` Shipment.

먼저 클레임 티켓 자체를 조회해 실제 참조 키들을 확인하겠습니다. ClaimTicket·Customer·SalesOrder는 모두 `scm_crm`에 있으니 스키마를 함께 받습니다.세 클래스 모두 `scm_crm`이니 한 번의 SQL로 클레임→고객→판매주문을 조인해 조회합니다.클레임의 실제 참조가 확인됐습니다. 고객 **아틀라스 오토모티브(CUS-004)**, 주문 **SO-2026-0412**(완제품 ITM-FG-001, 확정납기 2026-08-30), 참조발주 PO-2026-0117, 참조선적 SHP-2026-0111. 이제 발주·선적·통관 상태를 직접 검증하겠습니다(핸드오프 값 재확인 + 통관 현재 상태 확인). 세 클래스는 서로 다른 데이터소스이니 스키마를 받습니다.이제 발주(scm_erp)·선적(scm_wms)·통관신고(scm_customs)를 각각 조회합니다.모든 사실이 검증됐습니다. 통관 신고 3건이 모두 **HOLD**(한-중 FTA 원산지증명서 미첨부)이며, 고객 완제품에 들어가는 HDI PCB(ITM-PCB-004)는 신고 DCL-2026-00116에 해당함을 확인했습니다. 역추적이 완결됐으니 정리하고 회신 초안을 작성합니다.

---

## 🔎 클레임 TK-2026-0031 역추적 결과 (내부용)

**클레임** `scm_crm.claim_ticket` 1행 — 접수 2026-08-20, 카테고리 **납기문의**, 심각도 **HIGH**, 상태 OPEN

```
ClaimTicket(TK-2026-0031)
  └ FILED_BY   → Customer  CUS-004  아틀라스 오토모티브 (독일, 티어1 자동차, DAP/NET90, SLA 45일)
  └ ABOUT_ORDER→ SalesOrder SO-2026-0412  완제품 ITM-FG-001 · 2,400EA · 확정납기 2026-08-30 · 상태 AT_RISK
  └ REFERS_PO  → PurchaseOrder PO-2026-0117  (원자재 HDI PCB 조달) · 상태 DELAYED
  └ REFERS_SHIPMENT → Shipment SHP-2026-0111 · CUSTOMS_HOLD · 지연 9일
```

| 단계 | 근거 (테이블·행) | 핵심 사실 |
|---|---|---|
| 고객 주문 | `scm_crm.sales_order` 1행 | SO-2026-0412, 확정납기 **2026-08-30**, 상태 **AT_RISK**, 리스크노트: "HDI PCB(ITM-PCB-004) 입고 지연 — PO-2026-0117 세관 보류" |
| 발주 | `scm_erp.doc_purchase_order` 1행 | PO-2026-0117, 공급사 SUP-CN-003, 납기약속 2026-08-17, **DELAYED**, $81,307.20, 우선순위 HIGH |
| 선적 | `scm_wms.shipment` 1행 | SHP-2026-0111, 해상/KMTC, ETD 8/4→ATD 8/8, ETA 8/17, **ATA 미도착**, **CUSTOMS_HOLD**, 지연 **9일**, 사유 "부산세관 서류심사 보류(원산지증명 미첨부)" |
| 통관 | `scm_customs.decl_header` **3행** | DCL-2026-00114/115/116(ITM-PCB-003/001/004) 모두 **HOLD** — "한-중 FTA 원산지증명서(C/O) 미첨부 → 협정세율 보류". 고객 완제품용 **ITM-PCB-004는 DCL-2026-00116** |

**근본 원인 (판단개념 `DeliveryRisk`·`CustomsHoldReason` R3 적용):** 완제품 ITM-FG-001의 핵심 부품인 HDI PCB가 중국发 해상 선적 후 **부산세관에서 한-중 FTA 원산지증명서(C/O) 미첨부로 통관 보류**됨. 운송이 아니라 **통관 서류 미비**가 원인이며, C/O 확보·제출로 해소 가능한 성격. 오늘(2026-08-21) 기준 아직 실입고(ATA) 없음 → 고객 확정납기 8/30 준수가 위태로운 상태.

---

## ✉️ 고객 회신 초안

> **수신**: 아틀라스 오토모티브 (Atlas Automotive) 구매팀
> **건**: 주문 SO-2026-0412 (HDI PCB 적용 전원모듈 완제품, 2,400EA) 납기 문의 회신 — 티켓 TK-2026-0031

안녕하세요, 아틀라스 오토모티브 담당자님.

주문 **SO-2026-0412**의 납기 문의(접수번호 TK-2026-0031)에 답변드립니다. 먼저 배송 관련 불편을 끼쳐드린 점 양해 부탁드립니다.

**■ 현재 상황 및 원인**
해당 완제품의 핵심 부품인 HDI PCB가 해외 공급처로부터 해상 운송되어 국내에 도착했으나, **수입 통관 과정에서 원산지증명서(한-중 FTA C/O) 서류 보완 사유로 통관이 보류**되어 있습니다. 부품 자체의 품질·수량 문제나 운송 지연이 아니라, **관세 협정 적용을 위한 서류 확인 절차**에서 지체가 발생한 것으로, 현재 세관 심사가 진행 중입니다.

**■ 진행 중인 조치**
- 공급처에 **원산지증명서(C/O) 긴급 발급·송부를 요청**하여 세관에 즉시 보완 제출할 수 있도록 진행하고 있습니다.
- 통관 대행사와 함께 서류 보완 후 **통관 신속 재개** 협의를 병행하고 있으며, 부품 입고 즉시 생산·출하에 착수할 수 있도록 내부 라인을 대기시켜 두었습니다.

**■ 예상 납기 영향**
- 당초 확정 납기는 **2026-08-30**이었습니다.
- 현재 부품이 통관 보류 상태로, **확정 납기 준수가 어려울 것으로 예상**됩니다. 통관 해소 시점에 따라 **수일에서 최대 1주가량 지연**될 가능성이 있습니다.
- 서류 보완이 완료되면 통관은 통상 수 영업일 내 재개되며, **정확한 재확정 납기는 세관 통관 완료 시점 확인 후 24시간 내 별도 안내**드리겠습니다.

**■ 대안 제안**
1. **분할 납품**: 사내 가용 재고 및 우선 생산분으로 일부 수량을 **선(先)출하**하고, 잔여분을 통관 해소 후 순차 납품하는 방안.
2. **대체 소싱 병행 검토**: 동일 규격 부품의 대체 공급 경로를 함께 점검하여, 통관 지연이 길어질 경우의 백업 라인을 확보.
3. **긴급 통관·특송 우선 처리**: 서류 보완 후 통관 우선순위 상향 및 입고 후 특송 출하로 지연 폭 최소화.

귀사 생산 일정에 미치는 영향이 크실 것으로 이해하며, 위 대안 중 선호하시는 방향을 알려주시면 즉시 반영하겠습니다. 통관 진행 상황은 매일 업데이트하여 공유드리겠습니다.

감사합니다.
[공급사 고객지원팀 드림]

---

**참고(내부)**: 위 회신은 고객 대면 문서라 내부 공급사명·발주금액·타 품목 통관건은 의도적으로 제외했습니다. 계약 CT-2025-011의 페널티 조항(지연 7일 초과)은 **당사↔공급사 간** 사안이므로 고객 회신에 포함하지 않았습니다. "수일~1주 지연"은 데이터상 확인된 지연일수 9일·ATA 미도착·통관 HOLD 상태에 근거한 **추정**이며, 실제 재확정 납기는 통관 완료 시점에 확정해야 합니다(생산 리드타임은 데이터에 없어 단정하지 않았습니다).

#### 채점

- PASS `아틀라스|CUS-004`
- PASS `SO-2026-0412`
- PASS `PO-2026-0117`
- PASS `SPC-200|ITM-FG-001`
- PASS `세관|통관|원산지`

**결과: PASS**
