### 질문

> '고정밀 베어링 A형' 생산에 필요한 원자재를 알려주고, 각 부품의 공급업체와 조달 리드타임을 조회해 공급 계획상 가장 크리티컬한 부품을 판단해줘.

모델 `gpt-4.1` · MCP `http://127.0.0.1:8100/mcp` · 도구 8개 · 시스템 프롬프트 6,360자 (서버가 제공)

에이전트는 도구를 **5회** 호출했다.

#### 1. `read_graph_schema`

```json
{}
```

```json
{
  "models": [
    {
      "schema_id": "a0edf61cc416",
      "name": "제조 하이브리드",
      "description": "legacy.manufacturing 테이블 구조에서 생성",
      "intent": "",
      "golden_questions": [],
      "format_version": 1,
      "published_at": 1786955809.895652
    }
  ],
  "classes": [
    {
      "schema_name": "제조 하이브리드",
      "class_name": "MfgDailyEquipment",
      "description": "Mfg daily equipment (manufacturing.mfg_daily_equipment)",
      "binding_kind": "virtual",
      "property_names": [
        "status_date",
        "equipment_id",
        "equipment_name",
        "step_id",
        "status",
        "operating_hours",
        "idle_hours",
        "maintenance_hours",
        "breakdown_hours",
        "breakdown_count",
        "mtbf_hours",
        "mttr_hours",
        "utilization_rate"
      ],
      "property_source": "published_registry",
      "native": true,
      "… (총 11712자)
```

#### 2. `ontology_resolve_entity`

```json
{
  "text": "고정밀 베어링 A형",
  "class_name": "MfgProduct"
}
```

```json
{
  "query": "고정밀 베어링 A형",
  "matches": [
    {
      "class_name": "MfgProduct",
      "properties": {
        "created_date": "2024-01-01",
        "is_active": "Y",
        "lead_time_days": 5,
        "min_order_qty": 100,
        "product_category": "자동차부품",
        "product_id": "PROD-001",
        "product_name": "고정밀 베어링 A형",
        "unit_cost": "28000.00",
        "unit_price": "45000.00"
      },
      "matched_by": "lexical"
    }
  ],
  "count": 1,
  "key_columns": {
    "MfgProduct": [
      "product_id"
    ]
  },
  "note": "벡터 검색을 쓸 수 없습니다: {neo4j_code: Neo.ClientError.Statement.ArgumentError} {message: cypher error: there is no index named 'entity_embedding_"
}
```

#### 3. `ontology_graph_cypher`

```json
{
  "query": "MATCH (p:_Entity:MfgProduct {product_id: 'PROD-001'})<-[:REFERENCES_MFG_PRODUCT]-(b:_Entity:MfgProductBom)-[:REFERENCES_MFG_RAW_MATERIAL]->(m:_Entity:MfgRawMaterial) RETURN b.material_id AS material_id, b.quantity_required AS quantity_required, m.material_name AS material_name, m.supplier_id AS supplier_id"
}
```

```json
{
  "rows": [
    {
      "material_id": "MAT-001",
      "quantity_required": "0.5000",
      "material_name": "고탄소강 봉재",
      "supplier_id": "SUP-001"
    },
    {
      "material_id": "MAT-011",
      "quantity_required": "24.0000",
      "material_name": "베어링 볼 (Φ5mm)",
      "supplier_id": "SUP-007"
    },
    {
      "material_id": "MAT-013",
      "quantity_required": "0.0200",
      "material_name": "산업용 윤활유",
      "supplier_id": "SUP-008"
    }
  ],
  "row_count": 3,
  "truncated": false,
  "_datasource_refs": [
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
      "from_class": "MfgProduct",
      "class": "MfgDailyQualityIssue",
  … (총 1541자)
```

#### 4. `ontology_get_datasource_schema`

```json
{
  "class_name": "MfgDailyMaterialCost"
}
```

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
      "c… (총 2147자)
```

#### 5. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT material_id, supplier_id, MAX(lead_time_days) AS max_lead_time_days FROM manufacturing.mfg_daily_material_cost WHERE material_id IN ('MAT-001','MAT-011','MAT-013') GROUP BY material_id, supplier_id ORDER BY max_lead_time_days DESC",
  "limit": 3
}
```

```json
{
  "status": "ok",
  "columns": [
    "material_id",
    "supplier_id",
    "max_lead_time_days"
  ],
  "rows": [
    {
      "material_id": "MAT-011",
      "supplier_id": "SUP-007",
      "max_lead_time_days": 14
    },
    {
      "material_id": "MAT-013",
      "supplier_id": "SUP-008",
      "max_lead_time_days": 14
    },
    {
      "material_id": "MAT-001",
      "supplier_id": "SUP-001",
      "max_lead_time_days": 14
    }
  ],
  "row_count": 3,
  "truncated_for_agent": false,
  "truncated": false,
  "sql": "SELECT material_id, supplier_id, MAX(lead_time_days) AS max_lead_time_days FROM manufacturing.mfg_daily_material_cost WHERE material_id IN ('MAT-001','MAT-011','MAT-013') GROUP BY material_id, supplier_id ORDER BY max_lead_time_days DESC LIMIT 3",
  "source": {
    "datasource": "legacy"
  }
}
```

#### 최종 답변

조회 결과를 바탕으로 '고정밀 베어링 A형' 생산에 필요한 원자재, 각 부품의 공급업체, 그리고 조달 리드타임(최대값 기준)은 다음과 같습니다.

■ 원자재 및 공급업체, 리드타임

| 원자재명           | 부품 ID   | 공급업체 ID | 최대 조달 리드타임(일) |
|--------------------|-----------|-------------|------------------------|
| 고탄소강 봉재      | MAT-001   | SUP-001     | 14                     |
| 베어링 볼 (Φ5mm)   | MAT-011   | SUP-007     | 14                     |
| 산업용 윤활유      | MAT-013   | SUP-008     | 14                     |

■ 크리티컬 부품 판단

- 세 부품 모두 최대 조달 리드타임이 14일로 동일합니다.
- 따라서, 공급 계획상 리드타임 기준으로는 세 부품 모두가 동등하게 크리티컬(병목) 요소가 될 수 있습니다.
- 실제로는 추가적으로 재고 수준, 품질 점수, 공급 안정성 등을 함께 고려해야 하지만, 본 조회에서는 리드타임 기준으로만 판단하였습니다.

■ 근거

- 그래프 탐색: '고정밀 베어링 A형'(product_id=PROD-001)의 BOM을 통해 원자재(MAT-001, MAT-011, MAT-013)와 각 공급업체(SUP-001, SUP-007, SUP-008) 추출
- 데이터 근거: manufacturing.mfg_daily_material_cost 테이블에서 각 원자재-공급업체별 최대 lead_time_days(조달 리드타임) 집계, 총 3행

추가적으로 품질 점수나 최근 조달 이슈 등 다른 기준이 필요하다면 말씀해 주세요.
