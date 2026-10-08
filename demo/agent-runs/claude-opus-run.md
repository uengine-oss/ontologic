## 실행 환경

- 모델: `claude-opus-4-8[1m]`
- 세션: `3740b6e9-1174-48b3-94cc-884496c172db`
- 사용 가능 도구: 38개
- MCP 서버:
  - `plugin:code-review-graph:code-review-graph` — **pending**
  - `ontology-studio-build` — **failed**
  - `ontology-studio-answer` — **failed**
  - `ontologic` — **connected**
  - `claude.ai Gmail` — **needs-auth**
  - `claude.ai Google Drive` — **pending**
  - `claude.ai Google Calendar` — **needs-auth**

---

> 도구를 먼저 확인하고 로드하겠습니다. 온톨로지 조회 도구와 MCP 리소스 읽기 도구 스키마를 가져오겠습니다.

### 1. `ToolSearch`

```json
{
  "query": "select:mcp__ontologic__ontology_resolve_entity,mcp__ontologic__ontology_graph_cypher,mcp__ontologic__ontology_get_datasource_schema,mcp__ontologic__ontology_query_datasource_sql,ReadMcpResourceTool,ListMcpResourcesTool",
  "max_results": 10
}
```

**결과**

```json
     
```

> 도구가 준비됐습니다. 먼저 온톨로지 스키마 지도를 한 번 읽겠습니다.

### 2. `ReadMcpResourceTool`

```json
{
  "server": "ontologic",
  "uri": "graph://schema"
}
```

**결과**

```json
{"contents":[{"uri":"graph://schema","mimeType":"text/plain","text":"{\n  \"models\": [\n    {\n      \"schema_id\": \"a0edf61cc416\",\n      \"name\": \"제조 하이브리드\",\n      \"description\": \"legacy.manufacturing 테이블 구조에서 생성\",\n      \"intent\": \"\",\n      \"golden_questions\": [],\n      \"format_version\": 1,\n      \"published_at\": 1786944827.5956638\n    }\n  ],\n  \"classes\": [\n    {\n      \"schema_name\": \"제조 하이브리드\",\n      \"class_name\": \"MfgDailyEquipment\",\n      \"description\": \"Mfg daily equipment (manufacturing.mfg_daily_equipment)\",\n      \"binding_kind\": \"virtual\",\n      \"property_names\": [\n        \"status_date\",\n        \"equipment_id\",\n        \"equipment_name\",\n        \"step_id\",\n        \"status\",\n        \"operating_hours\",\n        \"idle_hours\",\n        \"maintenance_hours\",\n        \"breakdown_hours\",\n        \"breakdown_count\",\n        \"mtbf_hours\",\n        \"mttr_hours\",\n        \"utilization_rate\"\n      ],\n      \"property_source\": \"published_registry\",\n      \"native\": true,\n      \"native_key\": [\n        \"status_date\"\n      ],\n      \"behavior_count\": 1,\n      \"source\": {\n        \"datasource\": \"legacy\",\n        \"schema\": \"manufacturing\",\n        \"table\": \"mfg_daily_equipment\"\n      },\n      \"key_columns\": [\n        \"status_date\",\n        \"equipment_id\"\n      ]\n    },\n    {\n      \"schema_name\": \"제조 하이브리드\",\n      \"class_name\": \"MfgDailyMaterialCost\",\n      \"description\": \"Mfg daily material cost (manufacturing.mfg_daily_material_cost)\",\n  
… (총 13,180자)
```

> 스키마를 파악했습니다. '고정밀 베어링 A형'을 캐노니컬 키로 변환하겠습니다.

### 3. `mcp__ontologic__ontology_resolve_entity`

```json
{
  "text": "고정밀 베어링 A형",
  "class_name": "MfgProduct"
}
```

**결과**

```json
{
  "query": "고정밀 베어링 A형",
  "matches": [
    {
      "class_name": "MfgProduct",
      "properties": {
        "min_order_qty": 100,
        "is_active": "Y",
        "lead_time_days": 5,
        "product_id": "PROD-001",
        "unit_cost": "28000.00",
        "created_date": "2024-01-01",
        "unit_price": "45000.00",
        "product_name": "고정밀 베어링 A형",
        "product_category": "자동차부품"
      },
      "matched_by": "lexical"
    }
  ],
  "count": 1,
  "key_columns": {
    "MfgProduct": [
      "product_id"
    ]
  }
}
```

> `PROD-001`로 확인됐습니다. 이제 BOM을 따라 원자재와 공급업체를 그래프에서 조회하겠습니다.

### 4. `mcp__ontologic__ontology_graph_cypher`

```json
{
  "query": "MATCH (p:_Entity:MfgProduct {product_id: $pid})<-[:REFERENCES_MFG_PRODUCT]-(b:_Entity:MfgProductBom)-[:REFERENCES_MFG_RAW_MATERIAL]->(m:_Entity:MfgRawMaterial)\nRETURN m.material_id AS material_id, m.material_name AS material_name, m.material_type AS material_type, m.supplier_id AS supplier_id, m.safety_stock_qty AS safety_stock_qty, m.unit_of_measure AS uom, b.quantity_required AS qty_required\nORDER BY material_id",
  "params": "{\"pid\": \"PROD-001\"}"
}
```

**결과**

```json
{
  "rows": [
    {
      "material_id": "MAT-001",
      "material_name": "고탄소강 봉재",
      "material_type": "금속",
      "supplier_id": "SUP-001",
      "safety_stock_qty": "5000.00",
      "uom": "kg",
      "qty_required": "0.5000"
    },
    {
      "material_id": "MAT-011",
      "material_name": "베어링 볼 (Φ5mm)",
      "material_type": "금속",
      "supplier_id": "SUP-007",
      "safety_stock_qty": "50000.00",
      "uom": "ea",
      "qty_required": "24.0000"
    },
    {
      "material_id": "MAT-013",
      "material_name": "산업용 윤활유",
      "material_type": "화학물질",
      "supplier_id": "SUP-008",
      "safety_stock_qty": "300.00",
      "uom": "L",
      "qty_required": "0.0200"
    }
  ],
  "row_count": 3,
  "truncated": false,
  "_datasource_refs": [
    {
      "from_class": "MfgProduct",
      "class": "MfgDailyQualityIssue",
      "datasource": "legacy",
      "schema": "manufacturing",
      "table": "mfg_daily_quality_issue",
      "via_relationship": "REFERENCES_MFG_PRODUCT",
      "join_on": "product_id = product_id"
    },
    {
      "from_class": "MfgProduct",
      "class": "MfgDailyProcessMetrics",
      "datasource": "legacy",
      "schema": "manufacturing",
      "table": "mfg_daily_process_metrics",
      "via_relationship": "REFERENCES_MFG_PRODUCT",
      "join_on": "product_id = product_id"
    },
    {
      "from_class": "MfgRawMaterial",
      "class": "MfgDailyMaterialCost",
      "datasource": "legacy",
      "schema": "manufacturing",
      "table": "mfg_daily_material_cost",
      "via_relationship": "REFERENCES_MFG_RAW_MATERIAL",
      "jo
… (총 1,782자)
```

> 원자재 3종과 공급업체를 확보했습니다. 조달 리드타임은 `MfgDailyMaterialCost` 가상 클래스에 있으니 스키마를 받겠습니다.

### 5. `mcp__ontologic__ontology_get_datasource_schema`

```json
{
  "class_name": "MfgDailyMaterialCost"
}
```

**결과**

```json
{
  "class_name": "MfgDailyMaterialCost",
  "description": "Mfg daily material cost (manufacturing.mfg_daily_material_cost)",
  "source": {
    "datasource": "legacy",
    "schema": "manufacturing",
    "table": "mfg_daily_material_cost"
  },
  "key_columns": [
    "cost_date",
    "material_id",
    "supplier_id"
  ],
  "base_conditions": [],
  "columns": [
    {
      "property": "cost_date",
      "column": "cost_date",
      "type": "date",
      "description": ""
    },
    {
      "property": "material_id",
      "column": "material_id",
      "type": "string",
      "description": ""
    },
    {
      "property": "supplier_id",
      "column": "supplier_id",
      "type": "string",
      "description": ""
    },
    {
      "property": "unit_price",
      "column": "unit_price",
      "type": "float",
      "description": ""
    },
    {
      "property": "purchase_qty",
      "column": "purchase_qty",
      "type": "float",
      "description": ""
    },
    {
      "property": "purchase_amount",
      "column": "purchase_amount",
      "type": "float",
      "description": ""
    },
    {
      "property": "consumption_qty",
      "column": "consumption_qty",
      "type": "float",
      "description": ""
    },
    {
      "property": "consumption_amount",
      "column": "consumption_amount",
      "type": "float",
      "description": ""
    },
    {
      "property": "stock_qty",
      "column": "stock_qty",
      "type": "float",
      "description": ""
    },
    {
      "property": "stock_value",
      "column": "stock_value",
      "type": "float",
      "
… (총 2,147자)
```

> 리드타임과 재고 수준을 DB에서 집계하겠습니다.

### 6. `mcp__ontologic__ontology_query_datasource_sql`

```json
{
  "sql": "SELECT material_id, supplier_id,\n       COUNT(*) AS rows_n,\n       AVG(lead_time_days) AS avg_lead,\n       MAX(lead_time_days) AS max_lead,\n       MIN(lead_time_days) AS min_lead,\n       AVG(stock_qty) AS avg_stock,\n       AVG(consumption_qty) AS avg_consumption,\n       AVG(price_change_pct) AS avg_price_change,\n       AVG(quality_score) AS avg_quality\nFROM manufacturing.mfg_daily_material_cost\nWHERE material_id IN ('MAT-001','MAT-011','MAT-013')\nGROUP BY material_id, supplier_id\nORDER BY avg_lead DESC"
}
```

**결과**

```json
{
  "status": "ok",
  "columns": [
    "material_id",
    "supplier_id",
    "rows_n",
    "avg_lead",
    "max_lead",
    "min_lead",
    "avg_stock",
    "avg_consumption",
    "avg_price_change",
    "avg_quality"
  ],
  "rows": [
    {
      "material_id": "MAT-013",
      "supplier_id": "SUP-008",
      "rows_n": 365,
      "avg_lead": "8.2164383561643836",
      "max_lead": 14,
      "min_lead": 2,
      "avg_stock": "662.4568802739726027",
      "avg_consumption": "261.9635536986301370",
      "avg_price_change": "0.00010794520547945205",
      "avg_quality": "97.4988219178082192"
    },
    {
      "material_id": "MAT-011",
      "supplier_id": "SUP-007",
      "rows_n": 365,
      "avg_lead": "7.8657534246575342",
      "max_lead": 14,
      "min_lead": 2,
      "avg_stock": "112008.639885479452",
      "avg_consumption": "361.1603008219178082",
      "avg_price_change": "0.000052328767123287671233",
      "avg_quality": "97.4097260273972603"
    },
    {
      "material_id": "MAT-001",
      "supplier_id": "SUP-001",
      "rows_n": 365,
      "avg_lead": "7.7643835616438356",
      "max_lead": 14,
      "min_lead": 2,
      "avg_stock": "11223.591952602740",
      "avg_consumption": "264.3310838356164384",
      "avg_price_change": "0.00087753424657534247",
      "avg_quality": "97.4339178082191781"
    }
  ],
  "row_count": 3,
  "truncated_for_agent": false,
  "truncated": false,
  "sql": "SELECT material_id, supplier_id,\n       COUNT(*) AS rows_n,\n       AVG(lead_time_days) AS avg_lead,\n       MAX(lead_time_days) AS max_lead,\n       MIN(lead_time_days) AS m
… (총 2,003자)
```

> 조회를 모두 마쳤습니다. 그래프(BOM·공급업체)와 데이터소스(리드타임·재고)를 결합한 결과입니다.
> 
> ## '고정밀 베어링 A형' (PROD-001) 원자재 조달 분석
> 
> ### 1. 소요 원자재 및 공급업체 — 그래프 근거
> `MfgProduct(PROD-001)` → `MfgProductBom` → `MfgRawMaterial` 경로, BOM 3건.
> 
> | 원자재 | 유형 | 소요량(제품당) | 공급업체 | 안전재고 |
> |---|---|---|---|---|
> | MAT-001 고탄소강 봉재 | 금속 | 0.5 kg | SUP-001 | 5,000 kg |
> | MAT-011 베어링 볼 (Φ5mm) | 금속 | 24 ea | SUP-007 | 50,000 ea |
> | MAT-013 산업용 윤활유 | 화학물질 | 0.02 L | SUP-008 | 300 L |
> 
> ### 2. 조달 리드타임 및 재고 — 데이터소스 근거
> `legacy.manufacturing.mfg_daily_material_cost`, 자재별 365행(1년치) 집계.
> 
> | 원자재 | 평균 리드타임 | 최대 | 평균 재고 | 일평균 소비 | **재고 커버일수** |
> |---|---|---|---|---|---|
> | MAT-013 윤활유 | **8.2일** | 14일 | 662 L | 262 L | **≈ 2.5일** |
> | MAT-011 베어링 볼 | 7.9일 | 14일 | 112,009 ea | 361 ea | ≈ 310일 |
> | MAT-001 고탄소강 | 7.8일 | 14일 | 11,224 kg | 264 kg | ≈ 42.5일 |
> 
> *(재고 커버일수 = 평균재고 ÷ 일평균소비, 조회된 집계값에서 산출)*
> 
> ### 3. 판단 — 가장 크리티컬한 부품: **MAT-013 산업용 윤활유 (공급업체 SUP-008)**
> 
> 근거는 두 지표가 동시에 최악이라는 점입니다:
> 
> - **리드타임이 가장 길다** — 평균 8.2일, 최대 14일(3종 중 최장).
> - **재고 완충이 압도적으로 얇다** — 재고 커버가 **약 2.5일**에 불과한데, 이는 재보충 리드타임(평균 8.2일)을 **크게 밑돕니다.** 즉 발주 후 입고 전에 재고가 소진되어 결품이 날 수 있는 유일한 자재입니다.
> - 반면 베어링 볼(약 310일)·고탄소강(약 42일)은 리드타임 대비 재고 완충이 수십 배라 조달 리스크가 사실상 없습니다.
> 
> 윤활유는 소요량 자체는 작지만(0.02 L/제품), **재고 회복 속도가 리드타임을 따라가지 못하는 구조**여서 공급 계획상 최우선 관리·안전재고 상향 대상입니다.
> 
> ---
> 
> 참고로, `mfg_daily_material_cost`에는 `base_conditions`가 없어 필터 없는 전체 모집단(각 자재 1년 365일)을 집계했으며, 리드타임·재고 수치는 위 SQL 집계 결과를 그대로 인용했습니다.

---

## 최종 답변

조회를 모두 마쳤습니다. 그래프(BOM·공급업체)와 데이터소스(리드타임·재고)를 결합한 결과입니다.

## '고정밀 베어링 A형' (PROD-001) 원자재 조달 분석

### 1. 소요 원자재 및 공급업체 — 그래프 근거
`MfgProduct(PROD-001)` → `MfgProductBom` → `MfgRawMaterial` 경로, BOM 3건.

| 원자재 | 유형 | 소요량(제품당) | 공급업체 | 안전재고 |
|---|---|---|---|---|
| MAT-001 고탄소강 봉재 | 금속 | 0.5 kg | SUP-001 | 5,000 kg |
| MAT-011 베어링 볼 (Φ5mm) | 금속 | 24 ea | SUP-007 | 50,000 ea |
| MAT-013 산업용 윤활유 | 화학물질 | 0.02 L | SUP-008 | 300 L |

### 2. 조달 리드타임 및 재고 — 데이터소스 근거
`legacy.manufacturing.mfg_daily_material_cost`, 자재별 365행(1년치) 집계.

| 원자재 | 평균 리드타임 | 최대 | 평균 재고 | 일평균 소비 | **재고 커버일수** |
|---|---|---|---|---|---|
| MAT-013 윤활유 | **8.2일** | 14일 | 662 L | 262 L | **≈ 2.5일** |
| MAT-011 베어링 볼 | 7.9일 | 14일 | 112,009 ea | 361 ea | ≈ 310일 |
| MAT-001 고탄소강 | 7.8일 | 14일 | 11,224 kg | 264 kg | ≈ 42.5일 |

*(재고 커버일수 = 평균재고 ÷ 일평균소비, 조회된 집계값에서 산출)*

### 3. 판단 — 가장 크리티컬한 부품: **MAT-013 산업용 윤활유 (공급업체 SUP-008)**

근거는 두 지표가 동시에 최악이라는 점입니다:

- **리드타임이 가장 길다** — 평균 8.2일, 최대 14일(3종 중 최장).
- **재고 완충이 압도적으로 얇다** — 재고 커버가 **약 2.5일**에 불과한데, 이는 재보충 리드타임(평균 8.2일)을 **크게 밑돕니다.** 즉 발주 후 입고 전에 재고가 소진되어 결품이 날 수 있는 유일한 자재입니다.
- 반면 베어링 볼(약 310일)·고탄소강(약 42일)은 리드타임 대비 재고 완충이 수십 배라 조달 리스크가 사실상 없습니다.

윤활유는 소요량 자체는 작지만(0.02 L/제품), **재고 회복 속도가 리드타임을 따라가지 못하는 구조**여서 공급 계획상 최우선 관리·안전재고 상향 대상입니다.

---

참고로, `mfg_daily_material_cost`에는 `base_conditions`가 없어 필터 없는 전체 모집단(각 자재 1년 365일)을 집계했으며, 리드타임·재고 수치는 위 SQL 집계 결과를 그대로 인용했습니다.

---

턴 7 · 소요 70.6s · 비용 $0.8353 · 결과 `success`

