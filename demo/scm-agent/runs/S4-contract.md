### [계약] 계약 에이전트 — S4-contract

**만기 임박 계약 감시 → 미결 발주 노출액 집계 → 갱신 우선순위**

> 앞으로 60일 이내에 만기되는 공급 계약을 찾아줘. 자동갱신 여부, 페널티 조항, 리스크 조항을 정리하고, 각 계약에 걸려 있는 미결(OPEN/PARTIAL/DELAYED) 발주 건수와 금액을 집계해서 갱신 우선순위를 제안해줘.

실행 경로 `ontology-studio /api/stream (AGENT_BACKEND=cliagents)` · 도구 호출 **7회** (오류 0) · 98.2s

#### 1. `Skill`

```json
{
  "skill": "ontologic-agentic-rag"
}
```

```json
Launching skill: ontologic-agentic-rag
```

#### 2. `Read`

```json
{
  "file_path": "/Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/scm-demo-S4-contract-ef58aa60answer/.claude/skills/ontologic-agentic-rag/references/two-step-retrieval.md"
}
```

#### 3. `ontology_graph_schema`

```json
{}
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

```json
{"result":"{\"models\": [{\"schema_id\": \"c316cf717ef3\", \"name\": \"공급망 지식지도\", \"description\": \"「기업 공급망 관리 업무 개념 체계」 문서 근거. 1-1 기록 개념은 scm_erp/wms/customs/crm 4개 이기종 시스템 테이블에 바인딩된 가상 클래스, 1-2 판단 개념은 업무 규칙을 담은 개념 클래스. 키 표기 차이(item_id/sku_code/ref_item_code, supplier_id/vendor_code)를 관계로 정합.\", \"intent\": \"\", \"golden_questions\": [], \"format_version\": 1, \"published_at\": 1787312650.117163}, {\"schema_id\": \"556fd497fb03\", \"name\": \"미국 전력망\", \"description\": \"미국 전력망 지리 예제\", \"intent\": \"변전소·송전선로·정전구역·발전량을 지도와 추이로 본다\", \"golden_questions\": [\"과부하 구간이 있는 송전선로는 어디인가?\", \"주별 정전 피해 가구는 얼마나 되는가?\", \"발전 유형별 주간 발전량 추이는?\"], \"format_version\": 1, \"published_at\": 1787180771.1668632}, {\"schema_id\": \"a0edf61cc416\", \"name\": \"제조 하이브리드\", \"description\": \"legacy.manufacturing 테이블 구조에서 생성\", \"intent\": \"\", \"golden_questions\": [], \"format_version\": 1, \"published_… (총 3000자)
```

#### 4. `ontology_get_datasource_schema`

```json
{
  "class_name": "Contract"
}
```

```json
{"result":"{\"class_name\": \"Contract\", \"description\": \"공급 계약. 키 contract_id. 속성: 공급사, 계약유형, 시작·종료일(end_date), 자동갱신(auto_renew), 페널티율(penalty_rate), 단가고정(price_lock), 상태(status: ACTIVE/EXPIRING/EXPIRED), 리스크조항(risk_clause). 발주(PurchaseOrder.contract_id)가 이 계약을 근거로 발생한다.\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"doc_contract\"}, \"key_columns\": [\"contract_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"계약번호\", \"column\": \"contract_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"공급사ID\", \"column\": \"supplier_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"계약유형\", \"column\": \"contract_type\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"시작일\", \"column\": \"start_date\", \"type\": \"date\", \"description\": \"\"}, {\"property\": \"종료일\", \"column\": \"end_date\", \"ty… (총 1563자)
```

#### 5. `ontology_get_datasource_schema`

```json
{
  "class_name": "PurchaseOrder"
}
```

```json
{"result":"{\"class_name\": \"PurchaseOrder\", \"description\": \"구매 발주 헤더. 키 po_id(WMS shipment.ref_po_no, CRM claim_ticket.ref_po_no 로 참조). 속성: 공급사, 계약(contract_id), 발주일, 납기약속일(promised_date), 상태(status: OPEN/CONFIRMED/DELAYED/RECEIVED 등), 발주금액(total_amount_usd), 우선순위(priority), 구매담당.\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"doc_purchase_order\"}, \"key_columns\": [\"po_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"발주번호\", \"column\": \"po_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"공급사ID\", \"column\": \"supplier_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"계약번호\", \"column\": \"contract_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"발주일\", \"column\": \"order_date\", \"type\": \"date\", \"description\": \"\"}, {\"property\": \"납기약속일\", \"column\": \"promised_d… (총 1376자)
```

#### 6. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT status, COUNT(*) AS cnt, MIN(end_date) AS min_end, MAX(end_date) AS max_end FROM erp.doc_contract GROUP BY status ORDER BY status"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"status\", \"cnt\", \"min_end\", \"max_end\"], \"rows\": [{\"status\": \"ACTIVE\", \"cnt\": 15, \"min_end\": \"2026-12-01\", \"max_end\": \"2027-12-01\"}, {\"status\": \"EXPIRED\", \"cnt\": 10, \"min_end\": \"2026-01-01\", \"max_end\": \"2026-08-01\"}, {\"status\": \"EXPIRING\", \"cnt\": 6, \"min_end\": \"2026-09-01\", \"max_end\": \"2026-10-01\"}], \"row_count\": 3, \"truncated_for_agent\": false, \"truncated\": false, \"sql\": \"SELECT status, COUNT(*) AS cnt, MIN(end_date) AS min_end, MAX(end_date) AS max_end FROM erp.doc_contract GROUP BY status ORDER BY status LIMIT 500\", \"source\": {\"datasource\": \"scm_erp\"}}"}
```

#### 7. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT c.contract_id, c.supplier_id, c.contract_type, c.end_date, c.status,\n       c.auto_renew, c.penalty_rate, c.price_lock, c.risk_clause,\n       COUNT(po.po_id) FILTER (WHERE po.status IN ('OPEN','PARTIAL','DELAYED')) AS open_po_cnt,\n       COALESCE(SUM(po.total_amount_usd) FILTER (WHERE po.status IN ('OPEN','PARTIAL','DELAYED')), 0) AS open_po_amount_usd\nFROM erp.doc_contract c\nLEFT JOIN erp.doc_purchase_order po ON po.contract_id = c.contract_id\nWHERE c.end_date BETWEEN DATE '2026-08-21' AND DATE '2026-10-20'\nGROUP BY c.contract_id, c.supplier_id, c.contract_type, c.end_date, c.status,\n         c.auto_renew, c.penalty_rate, c.price_lock, c.risk_clause\nORDER BY open_po_amount_usd DESC"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"contract_id\", \"supplier_id\", \"contract_type\", \"end_date\", \"status\", \"auto_renew\", \"penalty_rate\", \"price_lock\", \"risk_clause\", \"open_po_cnt\", \"open_po_amount_usd\"], \"rows\": [{\"contract_id\": \"CT-2025-011\", \"supplier_id\": \"SUP-CN-003\", \"contract_type\": \"연간공급\", \"end_date\": \"2026-09-15\", \"status\": \"EXPIRING\", \"auto_renew\": 0, \"penalty_rate\": \"2.00\", \"price_lock\": 1, \"risk_clause\": \"납기 7일 초과 지연 시 건당 2% 페널티, 연속 2회 시 계약해지 가능\", \"open_po_cnt\": 2, \"open_po_amount_usd\": \"166594.20\"}, {\"contract_id\": \"CT-2025-026\", \"supplier_id\": \"SUP-US-001\", \"contract_type\": \"단가계약\", \"end_date\": \"2026-10-01\", \"status\": \"EXPIRING\", \"auto_renew\": 0, \"penalty_rate\": \"0.50\", \"price_lock\": 0, \"risk_clause\": null, \"open_po_cnt\": 2, \"open_po_amount_usd\": \"20535.50\"}, {\"contract_… (총 2935자)
```

#### 최종 답변

그래프에 "공급망 지식지도" 모델이 발행돼 있고, 이 질문에 필요한 두 가상 클래스가 모두 `scm_erp` 에 바인딩돼 있습니다. `Contract` 와 `PurchaseOrder` 의 컬럼을 받겠습니다.SQL 로 집계하기 전에, 이 데모 데이터의 계약 만기일이 어느 시점에 몰려 있는지부터 확인하겠습니다(오늘=2026-08-21 기준 "60일 이내"를 정확히 걸기 위해).오늘(2026-08-21) 기준 60일 이내 = **2026-08-21 ~ 2026-10-20**. `EXPIRING` 6건(9/01~10/01)이 이 창에 들어옵니다. 이제 계약 조항과 미결 발주 집계를 한 번에 조인하겠습니다.조회 결과에 근거해 정리합니다.

## 60일 이내(2026-08-21 ~ 2026-10-20) 만기 공급 계약 — 6건

**그래프 근거**: `공급망 지식지도` 모델의 `Contract`(가상 클래스, `scm_erp.erp.doc_contract`) ↔ `PurchaseOrder`(`scm_erp.erp.doc_purchase_order`), 관계 `UNDER_CONTRACT` (조인키 `contract_id`). 갱신 순위 규칙은 판단 개념 `RenewalPriority`(R8): **미결 발주 노출액 합계 큰 순**.
**데이터 근거**: `erp.doc_contract` LEFT JOIN `erp.doc_purchase_order`, 미결 = `status IN (OPEN, PARTIAL, DELAYED)`. 만기 창에 걸린 계약 6건(모두 status=EXPIRING).

| 계약 | 공급사 | 만기일 | 자동갱신 | 페널티율 | 단가고정 | 리스크조항 | 미결 발주 | 미결 금액(USD) |
|---|---|---|---|---|---|---|---|---|
| CT-2025-011 | SUP-CN-003 | 2026-09-15 | ❌ 없음 | 2.0% | ✅ | **납기 7일 초과 지연 시 건당 2% 페널티, 연속 2회 시 계약해지 가능** | 2건 | **166,594.20** |
| CT-2025-026 | SUP-US-001 | 2026-10-01 | ❌ 없음 | 0.5% | ❌ | 없음 | 2건 | 20,535.50 |
| CT-2025-024 | SUP-DE-001 | 2026-09-01 | ❌ 없음 | 0.5% | ✅ | 없음 | 2건 | 18,482.40 |
| CT-2025-005 | SUP-KR-003 | 2026-10-01 | ❌ 없음 | 1.5% | ❌ | 없음 | 1건 | 9,834.80 |
| CT-2025-020 | SUP-TW-001 | 2026-09-01 | ✅ 있음 | 2.0% | ✅ | 없음 | 0건 | 0 |
| CT-2025-030 | SUP-IN-001 | 2026-09-01 | ❌ 없음 | 2.0% | ❌ | 없음 | 0건 | 0 |

*미결 금액 합계 = 215,446.90 USD (5건에 발주 존재, CT-2025-011 이 전체의 77%).*

## 갱신 우선순위 제안

**RenewalPriority(R8) 규칙(미결 노출액 순)에 자동갱신·리스크조항 강도를 가중해 조정**했습니다.

**🔴 1순위 — CT-2025-011 (SUP-CN-003)** · 즉시 착수
- 미결 노출액 $166,594(전체의 77%)로 압도적, **자동갱신 없음** → 방치 시 9/15 만기 후 공급 공백.
- 유일하게 **강한 리스크조항**(연속 2회 지연 시 **계약해지 가능**) + 페널티 2% + 단가고정. 만기도 가장 임박한 축.
- → 만기 25일 전. 재협상/연장 협상을 가장 먼저.

**🟠 2순위 — CT-2025-026 (SUP-US-001)** · 미결 2건 $20,536, 자동갱신 없음, 10/01 만기. 노출액 2위 + 자동갱신 부재.

**🟠 3순위 — CT-2025-024 (SUP-DE-001)** · 미결 2건 $18,482, 자동갱신 없음, **9/01 만기(가장 임박)**. 금액은 근소하게 낮지만 만기가 빨라 실무상 2순위와 병행 착수 권장.

**🟡 4순위 — CT-2025-005 (SUP-KR-003)** · 미결 1건 $9,835, 자동갱신 없음, 10/01 만기.

**🟢 5순위 — CT-2025-030 (SUP-IN-001)** · 미결 0건이나 **자동갱신 없음** + 페널티 2%. 노출액은 없지만 만기 후 자동 소멸하므로 신규 발주 예정이면 갱신 확인 필요.

**⚪ 최하위 — CT-2025-020 (SUP-TW-001)** · **유일하게 자동갱신 ✅** + 미결 0건. 별도 조치 없이 자동 연장되므로 사실상 모니터링만.

### 유의점
- 상태 컬럼상 6건 모두 이미 `EXPIRING` 으로 표시돼 있어, 만기 임박이 시스템에도 반영된 상태입니다.
- 페널티/리스크 조항이 명시적으로 채워진 계약은 **CT-2025-011 한 건뿐**이고, 나머지는 `risk_clause` 가 비어 있어(페널티율만 존재) 지연 리스크 노출은 CT-2025-011에 집중돼 있습니다.
- 금액은 `total_amount_usd` 기준 미결(OPEN/PARTIAL/DELAYED) 발주 합계이며, 결과는 truncate 없이 전체 6건입니다.

#### 채점

- PASS `CT-2025-011`
- PASS `자동\s*갱신[^\n]{0,20}(없|아니|미적용|X|false|불가)|auto_renew[^\n]{0,12}(false|False|0|아니)`
- PASS `PO-2026-0117|미결`

**결과: PASS**
