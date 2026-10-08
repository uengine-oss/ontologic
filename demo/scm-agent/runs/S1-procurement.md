### [조달] 조달 에이전트 — S1-procurement

**납기 리스크 감시 → 계약 페널티 판정**

> 발주 PO-2026-0117 의 납기 리스크를 점검해줘. 현재 선적 상태와 지연 일수, 지연 사유를 확인하고, 이 발주의 공급사와 계약 조건(페널티·만기)을 함께 보고해줘.

실행 경로 `ontology-studio /api/stream (AGENT_BACKEND=cliagents)` · 도구 호출 **9회** (오류 0) · 81.4s

#### 1. `Read`

```json
{
  "file_path": "/Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/scm-demo-S1-procurement-ef58aa60answer/.claude/skills/ontologic-agentic-rag/references/two-step-retrieval.md"
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

#### 2. `Bash`

```json
{
  "command": "ls -la /Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/scm-demo-S1-procurement-ef58aa60answer/output/ 2>/dev/null && echo \"---HINTS---\" && cat /Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/scm-demo-S1-procurement-ef58aa60answer/output/_search_hints.json 2>/dev/null",
  "description": "Check output dir and search hints"
}
```

```json
Exit code 1
(empty)
---HINTS---
```

#### 3. `ontology_graph_schema`

```json
{}
```

```json
{"result":"{\"models\": [{\"schema_id\": \"c316cf717ef3\", \"name\": \"공급망 지식지도\", \"description\": \"「기업 공급망 관리 업무 개념 체계」 문서 근거. 1-1 기록 개념은 scm_erp/wms/customs/crm 4개 이기종 시스템 테이블에 바인딩된 가상 클래스, 1-2 판단 개념은 업무 규칙을 담은 개념 클래스. 키 표기 차이(item_id/sku_code/ref_item_code, supplier_id/vendor_code)를 관계로 정합.\", \"intent\": \"\", \"golden_questions\": [], \"format_version\": 1, \"published_at\": 1787312650.117163}, {\"schema_id\": \"556fd497fb03\", \"name\": \"미국 전력망\", \"description\": \"미국 전력망 지리 예제\", \"intent\": \"변전소·송전선로·정전구역·발전량을 지도와 추이로 본다\", \"golden_questions\": [\"과부하 구간이 있는 송전선로는 어디인가?\", \"주별 정전 피해 가구는 얼마나 되는가?\", \"발전 유형별 주간 발전량 추이는?\"], \"format_version\": 1, \"published_at\": 1787180771.1668632}, {\"schema_id\": \"a0edf61cc416\", \"name\": \"제조 하이브리드\", \"description\": \"legacy.manufacturing 테이블 구조에서 생성\", \"intent\": \"\", \"golden_questions\": [], \"format_version\": 1, \"published_… (총 3000자)
```

#### 4. `ontology_get_datasource_schema`

```json
{
  "class_name": "PurchaseOrder"
}
```

#### 5. `ontology_get_datasource_schema`

```json
{
  "class_name": "Shipment"
}
```

```json
{"result":"{\"class_name\": \"PurchaseOrder\", \"description\": \"구매 발주 헤더. 키 po_id(WMS shipment.ref_po_no, CRM claim_ticket.ref_po_no 로 참조). 속성: 공급사, 계약(contract_id), 발주일, 납기약속일(promised_date), 상태(status: OPEN/CONFIRMED/DELAYED/RECEIVED 등), 발주금액(total_amount_usd), 우선순위(priority), 구매담당.\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"doc_purchase_order\"}, \"key_columns\": [\"po_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"발주번호\", \"column\": \"po_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"공급사ID\", \"column\": \"supplier_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"계약번호\", \"column\": \"contract_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"발주일\", \"column\": \"order_date\", \"type\": \"date\", \"description\": \"\"}, {\"property\": \"납기약속일\", \"column\": \"promised_d… (총 1376자)
```

```json
{"result":"{\"class_name\": \"Shipment\", \"description\": \"국제 선적. 키 shipment_no(통관 decl_header.ref_shipment_no, CRM claim_ticket.ref_shipment_no 로 참조). 발주(ref_po_no=po_id)를 이행한다. 속성: 참조발주, 공급사(vendor_code), 운송수단, 포워더, ETD/ETA/ATD/ATA, 선적상태, 지연일수(delay_days), 지연사유(delay_reason), B/L번호.\", \"source\": {\"datasource\": \"scm_wms\", \"schema\": \"wms\", \"table\": \"shipment\"}, \"key_columns\": [\"shipment_no\"], \"base_conditions\": [], \"columns\": [{\"property\": \"선적번호\", \"column\": \"shipment_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"참조발주\", \"column\": \"ref_po_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"공급사코드\", \"column\": \"vendor_code\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"운송수단\", \"column\": \"transport_mode\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"포워더\", \"column\": \"forwa… (총 1834자)
```

#### 6. `ontology_get_datasource_schema`

```json
{
  "class_name": "Supplier"
}
```

#### 7. `ontology_get_datasource_schema`

```json
{
  "class_name": "Contract"
}
```

```json
{"result":"{\"class_name\": \"Supplier\", \"description\": \"공급사(벤더) 마스터. 키 표기: ERP mst_supplier.supplier_id, WMS shipment.vendor_code — 값 동일(SUP-…). 속성: 상호, 국가·도시, 티어, 카테고리, 평가점수(eval_score), 리드타임(lead_time_days), 정시납품률(otd_rate), 인코텀즈, 통화.\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"mst_supplier\"}, \"key_columns\": [\"supplier_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"공급사ID\", \"column\": \"supplier_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"상호\", \"column\": \"supplier_name\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"국가\", \"column\": \"country\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"도시\", \"column\": \"city\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"티어\", \"column\": \"tier\", \"type\": \"integer\", \"description\": \"\"}, {\"proper… (총 1610자)
```

```json
{"result":"{\"class_name\": \"Contract\", \"description\": \"공급 계약. 키 contract_id. 속성: 공급사, 계약유형, 시작·종료일(end_date), 자동갱신(auto_renew), 페널티율(penalty_rate), 단가고정(price_lock), 상태(status: ACTIVE/EXPIRING/EXPIRED), 리스크조항(risk_clause). 발주(PurchaseOrder.contract_id)가 이 계약을 근거로 발생한다.\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"doc_contract\"}, \"key_columns\": [\"contract_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"계약번호\", \"column\": \"contract_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"공급사ID\", \"column\": \"supplier_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"계약유형\", \"column\": \"contract_type\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"시작일\", \"column\": \"start_date\", \"type\": \"date\", \"description\": \"\"}, {\"property\": \"종료일\", \"column\": \"end_date\", \"ty… (총 1563자)
```

#### 8. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT po.po_id, po.supplier_id, po.contract_id, po.order_date, po.promised_date, po.status AS po_status, po.total_amount_usd, po.priority,\n       s.supplier_name, s.country, s.city, s.tier, s.eval_score, s.lead_time_days, s.otd_rate, s.incoterms, s.currency,\n       c.contract_type, c.start_date, c.end_date, c.auto_renew, c.penalty_rate, c.price_lock, c.status AS contract_status, c.risk_clause\nFROM erp.doc_purchase_order po\nLEFT JOIN erp.mst_supplier s ON po.supplier_id = s.supplier_id\nLEFT JOIN erp.doc_contract c ON po.contract_id = c.contract_id\nWHERE po.po_id = 'PO-2026-0117'"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"po_id\", \"supplier_id\", \"contract_id\", \"order_date\", \"promised_date\", \"po_status\", \"total_amount_usd\", \"priority\", \"supplier_name\", \"country\", \"city\", \"tier\", \"eval_score\", \"lead_time_days\", \"otd_rate\", \"incoterms\", \"currency\", \"contract_type\", \"start_date\", \"end_date\", \"auto_renew\", \"penalty_rate\", \"price_lock\", \"contract_status\", \"risk_clause\"], \"rows\": [{\"po_id\": \"PO-2026-0117\", \"supplier_id\": \"SUP-CN-003\", \"contract_id\": \"CT-2025-011\", \"order_date\": \"2026-07-24\", \"promised_date\": \"2026-08-17\", \"po_status\": \"DELAYED\", \"total_amount_usd\": \"81307.20\", \"priority\": \"HIGH\", \"supplier_name\": \"Shenzhen Goldline PCB\", \"country\": \"China\", \"city\": \"Shenzhen\", \"tier\": 1, \"eval_score\": \"3.6\", \"lead_time_days\": 18, \"otd_rate\": \"0.874\", \"incoterm… (총 1932자)
```

#### 9. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT shipment_no, ref_po_no, vendor_code, transport_mode, forwarder, etd, eta, atd, ata, ship_status, delay_days, delay_reason, bl_no\nFROM wms.shipment\nWHERE ref_po_no = 'PO-2026-0117'"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"shipment_no\", \"ref_po_no\", \"vendor_code\", \"transport_mode\", \"forwarder\", \"etd\", \"eta\", \"atd\", \"ata\", \"ship_status\", \"delay_days\", \"delay_reason\", \"bl_no\"], \"rows\": [{\"shipment_no\": \"SHP-2026-0111\", \"ref_po_no\": \"PO-2026-0117\", \"vendor_code\": \"SUP-CN-003\", \"transport_mode\": \"SEA\", \"forwarder\": \"KMTC\", \"etd\": \"2026-08-04\", \"eta\": \"2026-08-17\", \"atd\": \"2026-08-08\", \"ata\": null, \"ship_status\": \"CUSTOMS_HOLD\", \"delay_days\": 9, \"delay_reason\": \"부산세관 서류심사 보류(원산지증명 미첨부)\", \"bl_no\": \"SBL778231\"}], \"row_count\": 1, \"truncated_for_agent\": false, \"truncated\": false, \"sql\": \"SELECT shipment_no, ref_po_no, vendor_code, transport_mode, forwarder, etd, eta, atd, ata, ship_status, delay_days, delay_reason, bl_no\\nFROM wms.shipment\\nWHERE ref_po_no = 'PO-2026-0117' LIMIT 500\… (총 947자)
```

#### 최종 답변

먼저 워크플로우 참조 문서를 읽고 필요한 MCP 도구 스키마를 로드하겠습니다.도구가 모두 로드됐습니다. 검색 힌트 파일은 없네요. 이제 온톨로지 지도를 한 번 읽겠습니다.온톨로지 지도를 파악했습니다. 이 질문은 **공급망 지식지도**의 4개 가상 클래스에 걸쳐 있습니다:
- `PurchaseOrder`(발주) → `Shipment`(선적, `ref_po_no=po_id`)
- `PurchaseOrder.supplier_id` → `Supplier`(공급사)
- `PurchaseOrder.contract_id` → `Contract`(계약: 페널티율·만기)

모두 `virtual`(가상) 클래스라 그래프 노드가 없고 키 값으로 SQL 조인해야 합니다. `PO-2026-0117`은 이미 `po_id` 키 형식이므로, 네 클래스의 컬럼 스키마를 받겠습니다.4개 클래스 중 3개(`PurchaseOrder`·`Supplier`·`Contract`)는 `scm_erp` 데이터소스에, `Shipment`는 `scm_wms`에 있습니다. 데이터소스가 다르므로 두 개의 SQL로 나눠 DB가 조인·조회하게 합니다.조회를 마쳤습니다. 발주·공급사·계약(scm_erp)과 선적(scm_wms) 데이터가 모두 확인됐고, 온톨로지의 판단 개념(`DeliveryRisk`·`PenaltyTrigger`)을 적용해 정리합니다.

---

## 📦 발주 PO-2026-0117 납기 리스크 점검

### 판정: 🔴 **DELAYED (지연 확정) — 납기 리스크 高**

발주 상태가 이미 `DELAYED`이고, 선적 지연일수 9일이 납기약속일(2026-08-17)을 넘긴 데다 오늘(2026-08-21) 기준 실입고(ATA)가 아직 없습니다. 온톨로지 `DeliveryRisk` 규칙(발주 status=DELAYED, 또는 지연일수>0/ETA 초과 → 리스크)에 정확히 해당합니다.

### 1) 선적 현황 — `scm_wms.shipment` 1행 (SHP-2026-0111)

| 항목 | 값 |
|---|---|
| 선적번호 / B/L | SHP-2026-0111 / SBL778231 |
| 운송·포워더 | 해상(SEA), KMTC |
| ETD → ATD | 2026-08-04 → 실제 2026-08-08 (출항 4일 지연) |
| ETA → ATA | 2026-08-17 → **미도착(ATA 없음)** |
| 선적상태 | **CUSTOMS_HOLD** (통관 보류) |
| **지연일수** | **9일** |
| **지연사유** | **부산세관 서류심사 보류 — 원산지증명(C/O) 미첨부** |

> 지연 원인은 운송이 아니라 **통관 서류 미비**입니다. 원산지증명 첨부로 즉시 해소 가능한 성격이라, 서류 보완이 시급합니다.

### 2) 공급사 — `scm_erp.mst_supplier` (SUP-CN-003)

| 항목 | 값 |
|---|---|
| 공급사 | **Shenzhen Goldline PCB** (중국 선전) |
| 티어 / 평가점수 | Tier 1 / **3.6** (다소 낮음) |
| 정시납품률(OTD) | **87.4%** |
| 리드타임 | 18일 |
| 인코텀즈 / 통화 | FOB / USD |

### 3) 계약 조건 — `scm_erp.doc_contract` (CT-2025-011)

| 항목 | 값 |
|---|---|
| 계약유형 | 연간공급 |
| 기간(만기) | 2025-09-15 ~ **2026-09-15** → **만기 약 25일 남음** |
| 계약상태 | **EXPIRING (만기 임박)** |
| 자동갱신 | **아니오** |
| 단가고정 | 예 |
| **페널티율** | **2.0%** |
| **리스크조항** | **"납기 7일 초과 지연 시 건당 2% 페널티, 연속 2회 시 계약해지 가능"** |

### ⚠️ 페널티 노출 (온톨로지 `PenaltyTrigger` R1·R2)

- **발동 요건 충족**: 실지연 **9일 > 계약 임계 7일** → 페널티 조항 발동 상태
- **노출액 = 발주금액 × 페널티율 = $81,307.20 × 2.0% ≈ $1,626.14**

### 종합 조치 제언
1. **원산지증명(C/O) 즉시 보완** → 부산세관 CUSTOMS_HOLD 해소가 최우선 (지연 근본원인).
2. **페널티 청구 근거 확보** — 이미 임계(7일) 초과. 약 **$1,626** 청구 가능하며, HIGH 우선순위 건.
3. **계약 갱신 검토** — CT-2025-011은 **25일 뒤 만기 + 자동갱신 없음 + EXPIRING** 상태. 이번 지연(연속 2회 시 해지 조항)과 공급사 저조한 평가점수(3.6)를 함께 놓고 갱신 협상 조건을 재검토하세요.

---
**근거**: 그래프 지도 `공급망 지식지도`의 `PurchaseOrder→Shipment(ref_po_no=po_id)`, `→Supplier(supplier_id)`, `→Contract(contract_id)` 조인 경로. 데이터는 `scm_erp`(발주·공급사·계약, 1행)와 `scm_wms.shipment`(선적, 1행)에서 조회. 페널티 노출액은 위 계산식(발주금액×페널티율)으로 산출한 파생값입니다.

#### 채점

- PASS `CUSTOMS_HOLD|세관|통관`
- PASS `9\s*일`
- PASS `원산지`
- PASS `Shenzhen Goldline|SUP-CN-003`
- PASS `CT-2025-011`
- PASS `2(\.0+)?\s*%`

**결과: PASS**
