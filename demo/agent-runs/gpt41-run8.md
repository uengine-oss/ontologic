### 질문

> '고정밀 베어링 A형' 생산에 필요한 원자재를 알려주고, 각 부품의 공급업체와 조달 리드타임을 조회해 공급 계획상 가장 크리티컬한 부품을 판단해줘.

모델 `gpt-4.1` · MCP `http://127.0.0.1:8100/mcp` · 도구 8개 · 시스템 프롬프트 5,030자 (서버가 제공)

에이전트는 도구를 **7회** 호출했다.

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
      "published_at": 1786944827.5956638
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
      … (총 11699자)
```

#### 2. `ontology_resolve_entity`

```json
{
  "text": "고정밀 베어링 A형",
  "class_name": "MfgProduct",
  "limit": 3
}
```

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

#### 3. `ontology_graph_cypher`

```json
{
  "query": "MATCH (p:_Entity:MfgProduct {product_id: 'PROD-001'})<-[:REFERENCES_MFG_PRODUCT]-(b:_Entity:MfgProductBom)-[:REFERENCES_MFG_RAW_MATERIAL]->(m:_Entity:MfgRawMaterial) RETURN b.bom_id AS bom_id, b.material_id AS material_id, b.quantity_required AS quantity_required, b.unit_of_measure AS unit_of_measure, m.material_id AS material_id, m.material_name AS material_name, m.supplier_id AS supplier_id, m.safety_stock_qty AS safety_stock_qty, m.unit_of_measure AS material_unit, m._datasource_refs AS datasource_refs"
}
```

```json
{
  "error": "{neo4j_code: Neo.ClientError.Statement.SyntaxError} {message: Multiple result columns with the same name are not supported (line 1, column 194 (offset: 193))\n\"MATCH (p:_Entity:MfgProduct {product_id: 'PROD-001'})<-[:REFERENCES_MFG_PRODUCT]-(b:_Entity:MfgProductBom)-[:REFERENCES_MFG_RAW_MATERIAL]->(m:_Entity:MfgRawMaterial) RETURN b.bom_id AS bom_id, b.material_id AS material_id, b.quantity_required AS quantity_required, b.unit_of_measure AS unit_of_measure, m.material_id AS material_id, m.material_name AS material_name, m.supplier_id AS supplier_id, m.safety_stock_qty AS safety_stock_qty, m.unit_of_measure AS material_unit, m._datasource_refs AS datasource_refs\"\n                                                                                                                                                                                                  ^} {gql_status: 4… (총 996자)
```

#### 4. `ontology_graph_cypher`

```json
{
  "query": "MATCH (p:_Entity:MfgProduct {product_id: 'PROD-001'})<-[:REFERENCES_MFG_PRODUCT]-(b:_Entity:MfgProductBom)-[:REFERENCES_MFG_RAW_MATERIAL]->(m:_Entity:MfgRawMaterial) RETURN b.bom_id AS bom_id, b.material_id AS bom_material_id, b.quantity_required AS quantity_required, b.unit_of_measure AS bom_unit_of_measure, m.material_id AS material_id, m.material_name AS material_name, m.supplier_id AS supplier_id, m.safety_stock_qty AS safety_stock_qty, m.unit_of_measure AS material_unit, m._datasource_refs AS datasource_refs"
}
```

```json
{
  "rows": [
    {
      "bom_id": "BOM-001-02",
      "bom_material_id": "MAT-011",
      "quantity_required": "24.0000",
      "bom_unit_of_measure": "ea",
      "material_id": "MAT-011",
      "material_name": "베어링 볼 (Φ5mm)",
      "supplier_id": "SUP-007",
      "safety_stock_qty": "50000.00",
      "material_unit": "ea",
      "datasource_refs": null
    },
    {
      "bom_id": "BOM-001-03",
      "bom_material_id": "MAT-013",
      "quantity_required": "0.0200",
      "bom_unit_of_measure": "L",
      "material_id": "MAT-013",
      "material_name": "산업용 윤활유",
      "supplier_id": "SUP-008",
      "safety_stock_qty": "300.00",
      "material_unit": "L",
      "datasource_refs": null
    },
    {
      "bom_id": "BOM-001-01",
      "bom_material_id": "MAT-001",
      "quantity_required": "0.5000",
      "bom_unit_of_measure": "kg",
      "material_id": "MAT-001",
      "material_… (총 2133자)
```

#### 5. `ontology_get_datasource_schema`

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

#### 6. `ontology_get_datasource_schema`

```json
{
  "class_name": "MfgRawMaterial"
}
```

```json
{
  "error": "'MfgRawMaterial' 은 데이터소스에 바인딩된 클래스가 아닙니다. graph://schema 에서 binding_kind 가 virtual 인 클래스를 고르세요."
}
```

#### 7. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT material_id, supplier_id, MAX(lead_time_days) AS max_lead_time_days FROM manufacturing.mfg_daily_material_cost WHERE material_id IN ('MAT-001','MAT-011','MAT-013') GROUP BY material_id, supplier_id ORDER BY max_lead_time_days DESC",
  "limit": 10
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
  "sql": "SELECT material_id, supplier_id, MAX(lead_time_days) AS max_lead_time_days FROM manufacturing.mfg_daily_material_cost WHERE material_id IN ('MAT-001','MAT-011','MAT-013') GROUP BY material_id, supplier_id ORDER BY max_lead_time_days DESC LIMIT 10",
  "source": {
    "datasource": "legacy"
  }
}
```

#### 최종 답변

조회 결과를 바탕으로 '고정밀 베어링 A형'(product_id: PROD-001) 생산에 필요한 원자재, 각 부품의 공급업체, 조달 리드타임, 그리고 공급 계획상 크리티컬한(가장 리드타임이 긴) 부품을 아래와 같이 정리합니다.

---

■ 1. 필요 원자재 및 공급업체

| 부품명              | material_id | 공급업체   | supplier_id | 필요수량 | 단위  | 조달 리드타임(최대, 일) |
|---------------------|-------------|------------|-------------|----------|-------|-------------------------|
| 고탄소강 봉재       | MAT-001     | SUP-001    | SUP-001     | 0.5      | kg    | 14                      |
| 베어링 볼 (Φ5mm)    | MAT-011     | SUP-007    | SUP-007     | 24       | ea    | 14                      |
| 산업용 윤활유       | MAT-013     | SUP-008    | SUP-008     | 0.02     | L     | 14                      |

- 그래프 근거: MfgProduct(PROD-001) → MfgProductBom(BOM-001-01,02,03) → MfgRawMaterial(MAT-001,011,013)
- 데이터 근거: manufacturing.mfg_daily_material_cost 테이블, 3행 집계

■ 2. 공급 계획상 크리티컬 부품

- 세 부품 모두 최대 조달 리드타임이 14일로 동일합니다.
- 따라서, 공급 계획상 가장 크리티컬한 부품은 "고탄소강 봉재(MAT-001)", "베어링 볼(MAT-011)", "산업용 윤활유(MAT-013)" 모두가 해당됩니다.
- 실제로는 추가적으로 재고, 품질, 공급 안정성 등도 고려해야 하지만, 리드타임 기준으로는 동등하게 크리티컬합니다.

---

※ 참고: 본 답변은 그래프 탐색(제품→BOM→원자재)과 데이터소스 집계(lead_time_days 최대값) 결과를 결합한 것입니다.
