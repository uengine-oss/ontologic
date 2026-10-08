### [구매] 구매 에이전트 — S5-purchasing

**대체 소싱 비교표 → 발주서(PO) 초안 자동 생성**

> 품목 ITM-PCB-004 를 긴급 대체 소싱하려고 해. 이 품목을 공급할 수 있는 주 공급사와 대체 공급사를 평점·리드타임·납기준수율로 비교표를 만들고, 대체 공급사 앞 발주서(PO) 초안을 작성해줘. 수량은 안전재고 회복에 필요한 만큼, MOQ 를 지켜서.

실행 경로 `ontology-studio /api/stream (AGENT_BACKEND=cliagents)` · 도구 호출 **8회** (오류 0) · 94.0s

#### 1. `Read`

```json
{
  "file_path": "/Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/scm-demo-S5-purchasing-ef58aa60answer/.claude/skills/ontologic-agentic-rag/references/two-step-retrieval.md"
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
  "command": "ls -la /Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/scm-demo-S5-purchasing-ef58aa60answer/output/ 2>/dev/null; echo \"---hints---\"; cat /Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/scm-demo-S5-purchasing-ef58aa60answer/output/_search_hints.json 2>/dev/null",
  "description": "Check output dir and search hints"
}
```

```json
Exit code 1
(empty)
---hints---
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
  "class_name": "Item"
}
```

#### 5. `ontology_get_datasource_schema`

```json
{
  "class_name": "Supplier"
}
```

```json
{"result":"{\"class_name\": \"Item\", \"description\": \"품목 마스터(원자재·완제품). 공급망 전체에서 참조되는 핵심 사물. 시스템별 키 표기가 다르다: ERP mst_item.item_id, WMS stock_daily.sku_code, 통관 decl_header.ref_item_code, CRM sku_code — 값 네임스페이스(ITM-…)는 동일. 속성: 품목명, 유형, HS코드(hs_code), 원산지, 표준원가, 안전재고(safety_stock), MOQ, 주공급사(primary_supplier_id)·대체공급사(alt_supplier_id).\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"mst_item\"}, \"key_columns\": [\"item_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"품목ID\", \"column\": \"item_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"품목명\", \"column\": \"item_name\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"유형\", \"column\": \"item_type\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"HS코드\", \"column\": \"hs_code\", \"type\": \"string\", \"description\": \"\"}, {\"property\"… (총 1719자)
```

```json
{"result":"{\"class_name\": \"Supplier\", \"description\": \"공급사(벤더) 마스터. 키 표기: ERP mst_supplier.supplier_id, WMS shipment.vendor_code — 값 동일(SUP-…). 속성: 상호, 국가·도시, 티어, 카테고리, 평가점수(eval_score), 리드타임(lead_time_days), 정시납품률(otd_rate), 인코텀즈, 통화.\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"mst_supplier\"}, \"key_columns\": [\"supplier_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"공급사ID\", \"column\": \"supplier_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"상호\", \"column\": \"supplier_name\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"국가\", \"column\": \"country\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"도시\", \"column\": \"city\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"티어\", \"column\": \"tier\", \"type\": \"integer\", \"description\": \"\"}, {\"proper… (총 1610자)
```

#### 6. `ontology_get_datasource_schema`

```json
{
  "class_name": "StockDaily"
}
```

```json
{"result":"{\"class_name\": \"StockDaily\", \"description\": \"일별 재고 스냅샷. 키 (sku_code, snapshot_date). 품목(sku_code=item_id)의 창고별 재고 시계열. 속성: 스냅샷일, 품목, 창고, 가용재고(on_hand_qty), 예약수량(reserved_qty), 입고중수량(in_transit_qty), 일평균소요(avg_daily_usage). 안전재고 이탈·재고커버일수 판단의 원천이다.\", \"source\": {\"datasource\": \"scm_wms\", \"schema\": \"wms\", \"table\": \"stock_daily\"}, \"key_columns\": [\"sku_code\", \"snapshot_date\"], \"base_conditions\": [], \"columns\": [{\"property\": \"스냅샷일\", \"column\": \"snapshot_date\", \"type\": \"date\", \"description\": \"\"}, {\"property\": \"품목코드\", \"column\": \"sku_code\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"창고\", \"column\": \"warehouse_cd\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"가용재고\", \"column\": \"on_hand_qty\", \"type\": \"integer\", \"description\": \"\"}, {\"property\": \"예약수량\", \"column\": \"reserved_qty… (총 1288자)
```

#### 7. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT i.item_id, i.item_name, i.item_type, i.unit, i.std_cost_usd, i.safety_stock, i.moq,\n       i.primary_supplier_id, i.alt_supplier_id,\n       ps.supplier_name AS primary_name, ps.country AS primary_country, ps.tier AS primary_tier,\n       ps.eval_score AS primary_eval, ps.lead_time_days AS primary_lt, ps.otd_rate AS primary_otd,\n       ps.incoterms AS primary_incoterms, ps.currency AS primary_ccy,\n       a.supplier_name AS alt_name, a.country AS alt_country, a.tier AS alt_tier,\n       a.eval_score AS alt_eval, a.lead_time_days AS alt_lt, a.otd_rate AS alt_otd,\n       a.incoterms AS alt_incoterms, a.currency AS alt_ccy\nFROM erp.mst_item i\nLEFT JOIN erp.mst_supplier ps ON i.primary_supplier_id = ps.supplier_id\nLEFT JOIN erp.mst_supplier a ON i.alt_supplier_id = a.supplier_id\nWHERE i.item_id = 'ITM-PCB-004'"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"item_id\", \"item_name\", \"item_type\", \"unit\", \"std_cost_usd\", \"safety_stock\", \"moq\", \"primary_supplier_id\", \"alt_supplier_id\", \"primary_name\", \"primary_country\", \"primary_tier\", \"primary_eval\", \"primary_lt\", \"primary_otd\", \"primary_incoterms\", \"primary_ccy\", \"alt_name\", \"alt_country\", \"alt_tier\", \"alt_eval\", \"alt_lt\", \"alt_otd\", \"alt_incoterms\", \"alt_ccy\"], \"rows\": [{\"item_id\": \"ITM-PCB-004\", \"item_name\": \"6층 HDI PCB 전원모듈\", \"item_type\": \"RAW\", \"unit\": \"EA\", \"std_cost_usd\": \"5.80\", \"safety_stock\": 4000, \"moq\": 2000, \"primary_supplier_id\": \"SUP-CN-003\", \"alt_supplier_id\": \"SUP-VN-002\", \"primary_name\": \"Shenzhen Goldline PCB\", \"primary_country\": \"China\", \"primary_tier\": 1, \"primary_eval\": \"3.6\", \"primary_lt\": 18, \"primary_otd\": \"0.874\", \"prima… (총 2134자)
```

#### 8. `ontology_query_datasource_sql`

```json
{
  "sql": "WITH latest AS (\n  SELECT MAX(snapshot_date) AS d FROM wms.stock_daily WHERE sku_code = 'ITM-PCB-004'\n)\nSELECT s.snapshot_date,\n       SUM(s.on_hand_qty) AS on_hand_total,\n       SUM(s.reserved_qty) AS reserved_total,\n       SUM(s.in_transit_qty) AS in_transit_total,\n       SUM(s.avg_daily_usage) AS avg_daily_usage_total\nFROM wms.stock_daily s, latest\nWHERE s.sku_code = 'ITM-PCB-004' AND s.snapshot_date = latest.d\nGROUP BY s.snapshot_date"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"snapshot_date\", \"on_hand_total\", \"reserved_total\", \"in_transit_total\", \"avg_daily_usage_total\"], \"rows\": [{\"snapshot_date\": \"2026-08-21\", \"on_hand_total\": \"724\", \"reserved_total\": \"121\", \"in_transit_total\": \"6000\", \"avg_daily_usage_total\": \"284.69\"}], \"row_count\": 1, \"truncated_for_agent\": false, \"truncated\": false, \"sql\": \"WITH latest AS (\\n  SELECT MAX(snapshot_date) AS d FROM wms.stock_daily WHERE sku_code = 'ITM-PCB-004'\\n)\\nSELECT s.snapshot_date,\\n       SUM(s.on_hand_qty) AS on_hand_total,\\n       SUM(s.reserved_qty) AS reserved_total,\\n       SUM(s.in_transit_qty) AS in_transit_total,\\n       SUM(s.avg_daily_usage) AS avg_daily_usage_total\\nFROM wms.stock_daily s, latest\\nWHERE s.sku_code = 'ITM-PCB-004' AND s.snapshot_date = latest.d\\nGROUP BY s.snapshot_date LIMIT 500\", \"source\"… (총 934자)
```

#### 최종 답변

구매·대체소싱 질문이네요. 그래프로 대상을 좁히고 데이터소스로 수치를 구하는 전형적인 두 단계 질문입니다. 먼저 워크플로우 문서와 검색 힌트를 확인하겠습니다.검색 힌트 파일은 없네요. 무방합니다. 이제 그래프 스키마를 한 번 읽고, 품목 ITM-PCB-004를 해소하겠습니다.스키마를 확인했습니다. 필요한 가상 클래스는 `Item`(품목 마스터), `Supplier`(공급사), `StockDaily`(재고)입니다. 세 클래스의 컬럼을 받아오겠습니다.이제 품목 마스터에서 ITM-PCB-004의 주/대체 공급사와 안전재고·MOQ를 가져오고, 두 공급사의 조건을 조인해서 한 번에 받아오겠습니다.주/대체 공급사 조건을 확보했습니다. 이제 안전재고 회복에 필요한 수량을 정하려면 현재 재고 포지션이 필요합니다. 최신 스냅샷의 재고를 (창고 합산으로) 조회하겠습니다.조회를 마쳤습니다. 계산 근거를 밝혀 정리합니다.

## 1. 대상 품목 — ITM-PCB-004

`erp.mst_item` 1행 기준: **6층 HDI PCB 전원모듈** (유형 RAW, 단위 EA, 표준원가 **$5.80/EA**), **안전재고 4,000 EA · MOQ 2,000 EA**, 주공급사 `SUP-CN-003` / 대체공급사 `SUP-VN-002`.

## 2. 공급사 비교 (주 vs 대체)

`erp.mst_supplier` 2행(주·대체 각 1행)을 조인해 가져온 값입니다.

| 항목 | **주 공급사** `SUP-CN-003` | **대체 공급사** `SUP-VN-002` | 우위 |
|---|---|---|---|
| 상호 | Shenzhen Goldline PCB (China) | Saigon Circuit Co. (Vietnam) | — |
| 티어 | Tier 1 | Tier 1 | 동일 |
| **평가점수(eval_score)** | 3.6 | **4.3** | 🟢 대체 |
| **리드타임(lead_time_days)** | 18일 | **12일** | 🟢 대체 (−6일) |
| **납기준수율(otd_rate)** | 87.4% | **96.1%** | 🟢 대체 (+8.7%p) |
| 인코텀즈 / 통화 | FOB / USD | FOB / USD | 동일 |

→ 대체 공급사 `SUP-VN-002`(Saigon Circuit Co.)가 **평점·리드타임·납기준수율 세 지표 모두에서 우위**입니다. 긴급 대체 소싱 대상으로 적합합니다.

## 3. 발주 수량 산정 (안전재고 회복 + MOQ 준수)

`wms.stock_daily` 최신 스냅샷(**2026-08-21**, 창고 합산 1행) 기준:

| 값 | 수량 |
|---|---|
| 가용재고(on_hand) | 724 EA |
| 예약수량(reserved) | 121 EA |
| 순가용(on_hand − reserved) | 603 EA |
| 안전재고 기준 | 4,000 EA |
| 일평균소요(avg_daily_usage) | 284.69 EA/일 |
| 입고중(in_transit) | 6,000 EA |

**계산식:**
- 안전재고 회복 필요량 = 안전재고 − 순가용 = 4,000 − 603 = **3,397 EA**
- MOQ(2,000) 배수로 올림 → 2 × 2,000 = **4,000 EA** ← 발주 수량

> ⚠️ **주의 — 입고중 6,000 EA:** 최신 스냅샷에 주공급사발(추정) 입고예정분 6,000 EA가 잡혀 있습니다. 이 물량이 정상 입고되면 재고는 안전재고를 넘어섭니다. 다만 주공급사의 리드타임 18일·OTD 87.4%를 고려하면 **긴급 대체 소싱은 이 입고분이 지연될 것을 전제**로 한 조치입니다. 만약 입고중 6,000 EA의 도착이 확정적이라면 이번 긴급 발주는 보류하거나 축소(최소 MOQ 2,000 EA)하는 것을 검토하십시오. 현재 순가용 603 EA는 **약 2.1일치**(603 ÷ 284.69) 소진분에 불과해 소진 임박 상태입니다.

---

## 4. 발주서(PO) 초안 — 대체 공급사 앞

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                  구 매 발 주 서 (PURCHASE ORDER)
                    ※ 긴급 대체 소싱 (EMERGENCY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PO 번호        : [발번 시 자동채번]
발주일         : 2026-08-21
우선순위       : URGENT (안전재고 이탈 대응)

■ 공급사 (SUPPLIER)
  공급사 ID    : SUP-VN-002
  상호         : Saigon Circuit Co.
  국가         : Vietnam
  인코텀즈     : FOB
  통화         : USD
  (참고) 평가점수 4.3 · 리드타임 12일 · 납기준수율 96.1%

■ 발주 품목 (ITEM)
  품목 ID      : ITM-PCB-004
  품목명       : 6층 HDI PCB 전원모듈
  유형/단위    : RAW / EA
  ┌──────────┬──────────┬─────────────┬──────────────┐
  │ 발주수량  │ 단위단가  │ 금액(USD)    │ 비고          │
  ├──────────┼──────────┼─────────────┼──────────────┤
  │ 4,000 EA │ $5.80 *  │ $23,200.00  │ MOQ 2,000 준수│
  │          │          │             │ (2×MOQ)       │
  └──────────┴──────────┴─────────────┴──────────────┘
  * 단가는 품목 표준원가(std_cost_usd) 기준. 대체공급사 계약단가
    확정 시 갱신 필요.

■ 납기 (DELIVERY)
  요청 납기    : 2026-09-02  (발주일 + 리드타임 12일)
  납품 조건    : FOB (Vietnam 선적항)

■ 수량 산정 근거
  안전재고 4,000 − 순가용 603(=on_hand 724 − reserved 121)
  = 필요량 3,397 EA → MOQ(2,000) 배수 올림 → 4,000 EA

■ 승인
  구매담당 ____________  승인권자 ____________
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### 근거 요약
- **그래프 근거**: `공급망 지식지도` 온톨로지의 `Item` → 주/대체 공급사 관계(`SUPPLIES` / `ALT_SUPPLIES`), 품목 `ITM-PCB-004`의 `primary_supplier_id=SUP-CN-003`, `alt_supplier_id=SUP-VN-002`.
- **데이터 근거**: `scm_erp.erp.mst_item`(1행) + `erp.mst_supplier`(주·대체 2행 조인), 재고는 `scm_wms.wms.stock_daily` 최신 스냅샷 2026-08-21(창고 합산 1행). 모두 조회 결과 그대로이며 원시 행을 끌어오지 않고 DB에서 집계했습니다.

두 가지 확인이 필요합니다 — (1) **입고중 6,000 EA의 도착 확실성**에 따라 발주 수량을 조정할지, (2) **대체공급사 계약단가**가 표준원가($5.80)와 다르면 PO 단가를 갱신할지. 원하시면 입고중 물량의 관련 PO/선적 상태(`PurchaseOrder`·`Shipment`)까지 추적해 드리겠습니다.

#### 채점

- PASS `Saigon Circuit|SUP-VN-002`
- PASS `Shenzhen Goldline|SUP-CN-003`
- PASS `4\.3`
- PASS `12\s*일`
- PASS `MOQ|2,?000`

**결과: PASS**
