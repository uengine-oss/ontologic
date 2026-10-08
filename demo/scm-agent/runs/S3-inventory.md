### [재고관리] 재고 에이전트 — S3-inventory

**안전재고 이탈 감시 → 커버일수 산출 → 대체 공급사 식별**

> 최신 스냅샷 기준으로 안전재고를 이탈한 원자재 품목을 찾고, 각 품목의 재고 커버일수와 운송중 수량을 알려줘. 가장 위험한 품목의 주 공급사와 대체 공급사도 함께 알려줘.

실행 경로 `ontology-studio /api/stream (AGENT_BACKEND=cliagents)` · 도구 호출 **10회** (오류 0) · 126.3s

#### 1. `Read`

```json
{
  "file_path": "/Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/scm-demo-S3-inventory-ef58aa60answer/.claude/skills/ontologic-agentic-rag/references/two-step-retrieval.md"
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
  "class_name": "StockDaily"
}
```

#### 4. `ontology_get_datasource_schema`

```json
{
  "class_name": "Item"
}
```

```json
{"result":"{\"class_name\": \"StockDaily\", \"description\": \"일별 재고 스냅샷. 키 (sku_code, snapshot_date). 품목(sku_code=item_id)의 창고별 재고 시계열. 속성: 스냅샷일, 품목, 창고, 가용재고(on_hand_qty), 예약수량(reserved_qty), 입고중수량(in_transit_qty), 일평균소요(avg_daily_usage). 안전재고 이탈·재고커버일수 판단의 원천이다.\", \"source\": {\"datasource\": \"scm_wms\", \"schema\": \"wms\", \"table\": \"stock_daily\"}, \"key_columns\": [\"sku_code\", \"snapshot_date\"], \"base_conditions\": [], \"columns\": [{\"property\": \"스냅샷일\", \"column\": \"snapshot_date\", \"type\": \"date\", \"description\": \"\"}, {\"property\": \"품목코드\", \"column\": \"sku_code\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"창고\", \"column\": \"warehouse_cd\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"가용재고\", \"column\": \"on_hand_qty\", \"type\": \"integer\", \"description\": \"\"}, {\"property\": \"예약수량\", \"column\": \"reserved_qty… (총 1288자)
```

```json
{"result":"{\"class_name\": \"Item\", \"description\": \"품목 마스터(원자재·완제품). 공급망 전체에서 참조되는 핵심 사물. 시스템별 키 표기가 다르다: ERP mst_item.item_id, WMS stock_daily.sku_code, 통관 decl_header.ref_item_code, CRM sku_code — 값 네임스페이스(ITM-…)는 동일. 속성: 품목명, 유형, HS코드(hs_code), 원산지, 표준원가, 안전재고(safety_stock), MOQ, 주공급사(primary_supplier_id)·대체공급사(alt_supplier_id).\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"mst_item\"}, \"key_columns\": [\"item_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"품목ID\", \"column\": \"item_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"품목명\", \"column\": \"item_name\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"유형\", \"column\": \"item_type\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"HS코드\", \"column\": \"hs_code\", \"type\": \"string\", \"description\": \"\"}, {\"property\"… (총 1719자)
```

#### 5. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT item_type, COUNT(*) AS cnt FROM erp.mst_item GROUP BY item_type ORDER BY cnt DESC"
}
```

#### 6. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT MAX(snapshot_date) AS latest_snapshot FROM wms.stock_daily"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"item_type\", \"cnt\"], \"rows\": [{\"item_type\": \"RAW\", \"cnt\": 30}, {\"item_type\": \"FG\", \"cnt\": 4}, {\"item_type\": \"SUB\", \"cnt\": 2}], \"row_count\": 3, \"truncated_for_agent\": false, \"truncated\": false, \"sql\": \"SELECT item_type, COUNT(*) AS cnt FROM erp.mst_item GROUP BY item_type ORDER BY cnt DESC LIMIT 500\", \"source\": {\"datasource\": \"scm_erp\"}}"}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"latest_snapshot\"], \"rows\": [{\"latest_snapshot\": \"2026-08-21\"}], \"row_count\": 1, \"truncated_for_agent\": false, \"truncated\": false, \"sql\": \"SELECT MAX(snapshot_date) AS latest_snapshot FROM wms.stock_daily LIMIT 500\", \"source\": {\"datasource\": \"scm_wms\"}}"}
```

#### 7. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT item_id, item_name, safety_stock, primary_supplier_id, alt_supplier_id FROM erp.mst_item WHERE item_type = 'RAW'",
  "limit": 50
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"item_id\", \"item_name\", \"safety_stock\", \"primary_supplier_id\", \"alt_supplier_id\"], \"rows\": [{\"item_id\": \"ITM-PCB-001\", \"item_name\": \"4층 메인보드 PCB 120x80\", \"safety_stock\": 6000, \"primary_supplier_id\": \"SUP-CN-003\", \"alt_supplier_id\": \"SUP-VN-002\"}, {\"item_id\": \"ITM-PCB-002\", \"item_name\": \"2층 서브보드 PCB 60x40\", \"safety_stock\": 8000, \"primary_supplier_id\": \"SUP-VN-002\", \"alt_supplier_id\": \"SUP-CN-003\"}, {\"item_id\": \"ITM-PCB-003\", \"item_name\": \"FPCB 카메라 모듈용\", \"safety_stock\": 5000, \"primary_supplier_id\": \"SUP-CN-003\", \"alt_supplier_id\": \"SUP-VN-002\"}, {\"item_id\": \"ITM-PCB-004\", \"item_name\": \"6층 HDI PCB 전원모듈\", \"safety_stock\": 4000, \"primary_supplier_id\": \"SUP-CN-003\", \"alt_supplier_id\": \"SUP-VN-002\"}, {\"item_id\": \"ITM-CON-001\", \"item_name\": \"보드투보드 커넥터 0.4mm 40P\… (총 3000자)
```

#### 8. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT sku_code, SUM(on_hand_qty) AS on_hand, SUM(in_transit_qty) AS in_transit, SUM(avg_daily_usage) AS daily_usage FROM wms.stock_daily WHERE snapshot_date = DATE '2026-08-21' GROUP BY sku_code",
  "limit": 200
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"sku_code\", \"on_hand\", \"in_transit\", \"daily_usage\"], \"rows\": [{\"sku_code\": \"ITM-PCB-001\", \"on_hand\": \"7695\", \"in_transit\": \"0\", \"daily_usage\": \"267.49\"}, {\"sku_code\": \"ITM-PCB-002\", \"on_hand\": \"10774\", \"in_transit\": \"0\", \"daily_usage\": \"401.48\"}, {\"sku_code\": \"ITM-PCB-003\", \"on_hand\": \"6364\", \"in_transit\": \"0\", \"daily_usage\": \"365.16\"}, {\"sku_code\": \"ITM-PCB-004\", \"on_hand\": \"724\", \"in_transit\": \"6000\", \"daily_usage\": \"284.69\"}, {\"sku_code\": \"ITM-CON-001\", \"on_hand\": \"35978\", \"in_transit\": \"0\", \"daily_usage\": \"1378.17\"}, {\"sku_code\": \"ITM-CON-002\", \"on_hand\": \"15227\", \"in_transit\": \"0\", \"daily_usage\": \"784.84\"}, {\"sku_code\": \"ITM-CON-003\", \"on_hand\": \"42239\", \"in_transit\": \"0\", \"daily_usage\": \"1134.78\"}, {\"sku_code\": \"I… (총 3000자)
```

#### 9. `ontology_get_datasource_schema`

```json
{
  "class_name": "Supplier"
}
```

```json
{"result":"{\"class_name\": \"Supplier\", \"description\": \"공급사(벤더) 마스터. 키 표기: ERP mst_supplier.supplier_id, WMS shipment.vendor_code — 값 동일(SUP-…). 속성: 상호, 국가·도시, 티어, 카테고리, 평가점수(eval_score), 리드타임(lead_time_days), 정시납품률(otd_rate), 인코텀즈, 통화.\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"mst_supplier\"}, \"key_columns\": [\"supplier_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"공급사ID\", \"column\": \"supplier_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"상호\", \"column\": \"supplier_name\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"국가\", \"column\": \"country\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"도시\", \"column\": \"city\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"티어\", \"column\": \"tier\", \"type\": \"integer\", \"description\": \"\"}, {\"proper… (총 1610자)
```

#### 10. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT supplier_id, supplier_name, country, city, tier, eval_score, lead_time_days, otd_rate FROM erp.mst_supplier WHERE supplier_id IN ('SUP-CN-003', 'SUP-VN-002')"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"supplier_id\", \"supplier_name\", \"country\", \"city\", \"tier\", \"eval_score\", \"lead_time_days\", \"otd_rate\"], \"rows\": [{\"supplier_id\": \"SUP-CN-003\", \"supplier_name\": \"Shenzhen Goldline PCB\", \"country\": \"China\", \"city\": \"Shenzhen\", \"tier\": 1, \"eval_score\": \"3.6\", \"lead_time_days\": 18, \"otd_rate\": \"0.874\"}, {\"supplier_id\": \"SUP-VN-002\", \"supplier_name\": \"Saigon Circuit Co.\", \"country\": \"Vietnam\", \"city\": \"Ho Chi Minh\", \"tier\": 1, \"eval_score\": \"4.3\", \"lead_time_days\": 12, \"otd_rate\": \"0.961\"}], \"row_count\": 2, \"truncated_for_agent\": false, \"truncated\": false, \"sql\": \"SELECT supplier_id, supplier_name, country, city, tier, eval_score, lead_time_days, otd_rate FROM erp.mst_supplier WHERE supplier_id IN ('SUP-CN-003', 'SUP-VN-002') LIMIT 500\", \"source\": {\"datasource\"… (총 917자)
```

#### 최종 답변

질문에 답하기 위해 먼저 워크플로우 문서와 그래프 스키마를 확인하겠습니다.이제 그래프 스키마를 확인하겠습니다.질문은 **공급망 지식지도** 스키마에 해당합니다. 관련 클래스가 명확합니다 — `Item`(품목, 안전재고·공급사, scm_erp), `StockDaily`(일별재고, on_hand·in_transit·avg_daily_usage, scm_wms), `Supplier`(공급사, scm_erp). 판단 개념 `SafetyStockBreach`(R6: on_hand < safety_stock), `StockCoverDays`(R5: on_hand ÷ avg_daily_usage)가 규칙을 정의합니다.

두 원천이 서로 다른 데이터소스(WMS/ERP)라 한 번의 SQL 조인이 안 되므로, 각 클래스 스키마를 받아 키로 결합하겠습니다.이제 실제 데이터를 조회합니다. 두 데이터소스가 분리돼 있으니, 먼저 원자재 품목의 유형값과 최신 스냅샷일을 확인하겠습니다.원자재는 `RAW` 유형 30개, 최신 스냅샷은 **2026-08-21**입니다. 이제 원자재 마스터와 최신 재고를 각각 집계합니다(창고 분산 대비 sku별 합산).원자재 30개 전부와 최신 재고가 매칭됐습니다. 안전재고 이탈(on_hand < safety_stock)을 판정한 결과 **ITM-PCB-004(6층 HDI PCB 전원모듈)** 한 품목이 이탈했습니다(재고 724 < 안전재고 4,000). 가장 위험한 이 품목의 공급사 정보를 조회하겠습니다.## 최신 스냅샷(2026-08-21) 원자재 안전재고 이탈 분석

**그래프 근거**: 「공급망 지식지도」 온톨로지에서 `Item`(품목 마스터, `scm_erp.erp.mst_item`)과 `StockDaily`(일별재고, `scm_wms.wms.stock_daily`)를 `sku_code = item_id` 키로 정합했습니다. 판정은 판단 개념 `SafetyStockBreach`의 규칙 R6(`on_hand_qty < safety_stock` → 이탈), `StockCoverDays`의 규칙 R5(`on_hand_qty ÷ avg_daily_usage`)를 따랐습니다. 두 원천이 다른 시스템(WMS/ERP)이라 SQL 조인이 안 되므로 각 테이블을 집계한 뒤 품목키로 결합했습니다.

**데이터 근거**: `mst_item` 원자재(RAW) 30개 전량 × `stock_daily` 2026-08-21 스냅샷(sku별 창고 합산, 30개 매칭) 대조.

### 안전재고를 이탈한 원자재 (1건)

| 품목 | 가용재고 | 안전재고 | 이탈량 | 재고 커버일수 | 운송중 수량 |
|---|---|---|---|---|---|
| **ITM-PCB-004** 6층 HDI PCB 전원모듈 | 724 | 4,000 | **-3,276** | **약 2.5일** | **6,000** |

- 재고 커버일수 = 가용재고 724 ÷ 일평균소요 284.69 ≈ **2.54일** (R5)
- 나머지 29개 원자재는 모두 안전재고 이상입니다. 다만 여유가 얇은 품목이 있습니다 — `ITM-CAP-002 탄탈 커패시터`(95 vs 80), `ITM-IND-001 파워 인덕터`(177 vs 150), `ITM-CON-002 USB-C 리셉터클`(15,227 vs 15,000)은 안전재고 턱걸이라 함께 감시할 대상입니다.

### 가장 위험한 품목: ITM-PCB-004 (6층 HDI PCB 전원모듈)

유일한 이탈 품목이자 커버일수가 2.5일에 불과합니다. 운송중 6,000개가 도착하면 안전재고(4,000)는 회복되나, 그 전까지 소진 리스크가 큽니다.

| 구분 | 공급사 | 국가/도시 | 티어 | 평가점수 | 리드타임 | 정시납품률 |
|---|---|---|---|---|---|---|
| **주 공급사** | SUP-CN-003 **Shenzhen Goldline PCB** | 중국 선전 | 1 | 3.6 | 18일 | 87.4% |
| **대체 공급사** | SUP-VN-002 **Saigon Circuit Co.** | 베트남 호치민 | 1 | 4.3 | 12일 | 96.1% |

**참고**: 대체 공급사(Saigon Circuit)가 주 공급사보다 리드타임 6일 짧고(12일 vs 18일), 정시납품률·평가점수도 모두 높습니다 — 긴급 대체소싱 시 조건이 오히려 유리합니다(`AlternateSourcingOption` R7 관점). 다만 운송중 6,000개가 곧 입고되므로, 대체 발주 여부는 그 ETA 확인 후 판단하는 것이 합리적입니다.

#### 채점

- PASS `ITM-PCB-004`
- PASS `커버\s*일수|cover`
- PASS `6,?000`
- PASS `Saigon Circuit|SUP-VN-002`

**결과: PASS**
