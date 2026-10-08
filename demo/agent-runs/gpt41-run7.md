### 질문

> '고정밀 베어링 A형' 을 생산하려면 어떤 원자재가 필요한가? 그 중 조달 리드타임이 가장 길어 공급 계획상 크리티컬 패스가 되는 부품과 공급업체를 알려줘.

모델 `gpt-4.1` · MCP `http://127.0.0.1:8100/mcp` · 도구 8개 · 시스템 프롬프트 5,030자 (서버가 제공)

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
  "query": "MATCH (p:_Entity:MfgProduct {product_id: 'PROD-001'})<-[:REFERENCES_MFG_PRODUCT]-(b:_Entity:MfgProductBom)-[:REFERENCES_MFG_RAW_MATERIAL]->(m:_Entity:MfgRawMaterial) RETURN b.bom_id AS bom_id, b.material_id AS material_id, b.quantity_required AS quantity_required, m.material_name AS material_name, m.material_type AS material_type, m.supplier_id AS supplier_id, m.material_id AS raw_material_id, m.unit_of_measure AS unit_of_measure, m._datasource_refs AS datasource_refs"
}
```

```json
{
  "rows": [
    {
      "bom_id": "BOM-001-02",
      "material_id": "MAT-011",
      "quantity_required": "24.0000",
      "material_name": "베어링 볼 (Φ5mm)",
      "material_type": "금속",
      "supplier_id": "SUP-007",
      "raw_material_id": "MAT-011",
      "unit_of_measure": "ea",
      "datasource_refs": null
    },
    {
      "bom_id": "BOM-001-03",
      "material_id": "MAT-013",
      "quantity_required": "0.0200",
      "material_name": "산업용 윤활유",
      "material_type": "화학물질",
      "supplier_id": "SUP-008",
      "raw_material_id": "MAT-013",
      "unit_of_measure": "L",
      "datasource_refs": null
    },
    {
      "bom_id": "BOM-001-01",
      "material_id": "MAT-001",
      "quantity_required": "0.5000",
      "material_name": "고탄소강 봉재",
      "material_type": "금속",
      "supplier_id": "SUP-001",
      "raw_material_id": "MAT-001",
      "unit_of_measure": "kg",
    … (총 977자)
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
  "sql": "SELECT material_id, supplier_id, MAX(lead_time_days) AS max_lead_time_days FROM manufacturing.mfg_daily_material_cost WHERE (material_id = 'MAT-011' AND supplier_id = 'SUP-007') OR (material_id = 'MAT-013' AND supplier_id = 'SUP-008') OR (material_id = 'MAT-001' AND supplier_id = 'SUP-001') GROUP BY material_id, supplier_id ORDER BY max_lead_time_days DESC",
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
  "sql": "SELECT material_id, supplier_id, MAX(lead_time_days) AS max_lead_time_days FROM manufacturing.mfg_daily_material_cost WHERE (material_id = 'MAT-011' AND supplier_id = 'SUP-007') OR (material_id = 'MAT-013' AND supplier_id = 'SUP-008') OR (material_id = 'MAT-001' AND supplier_id = 'SUP-001') GROUP BY material_id, supplier_id ORDER BY max_lead_time_days DESC LIMIT 3",
  "sou… (총 940자)
```

#### 최종 답변

질문: '고정밀 베어링 A형'을 생산하려면 어떤 원자재가 필요한가? 그 중 조달 리드타임이 가장 길어 공급 계획상 크리티컬 패스가 되는 부품과 공급업체를 알려줘.

1. 그래프 근거 (BOM 및 원자재):
- '고정밀 베어링 A형'(product_id: PROD-001)의 BOM에 포함된 원자재는 다음과 같습니다.
  - 베어링 볼 (Φ5mm) (material_id: MAT-011, 공급업체: SUP-007, 단위: ea, 소요량: 24)
  - 산업용 윤활유 (material_id: MAT-013, 공급업체: SUP-008, 단위: L, 소요량: 0.02)
  - 고탄소강 봉재 (material_id: MAT-001, 공급업체: SUP-001, 단위: kg, 소요량: 0.5)
- 이 정보는 MfgProduct, MfgProductBom, MfgRawMaterial 세 클래스의 관계를 따라 추출했습니다. (그래프 row 수: 3)

2. 데이터 근거 (조달 리드타임):
- 각 원자재별 최근 최대 조달 리드타임(일)은 다음과 같습니다. (manufacturing.mfg_daily_material_cost 테이블, 3행 집계)
  - 베어링 볼 (Φ5mm) / SUP-007: 14일
  - 산업용 윤활유 / SUP-008: 14일
  - 고탄소강 봉재 / SUP-001: 14일

3. 결론:
- 세 원자재 모두 최근 기준 최대 리드타임이 14일로 동일합니다.
- 따라서, 이 세 부품 모두가 공급계획상 크리티컬 패스가 될 수 있습니다. (특정 부품만이 유독 오래 걸리는 상황은 최근 데이터 기준으로 관찰되지 않습니다.)

요약:
- 필요한 원자재: 베어링 볼 (Φ5mm), 산업용 윤활유, 고탄소강 봉재
- 각 원자재의 공급업체: SUP-007, SUP-008, SUP-001
- 세 원자재 모두 리드타임 14일로, 모두가 크리티컬 패스가 될 수 있습니다.

(그래프 근거: BOM 및 원자재 노드 3건, 데이터 근거: mfg_daily_material_cost 테이블 3건 집계)
