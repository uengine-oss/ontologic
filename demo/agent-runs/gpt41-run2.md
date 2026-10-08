### 질문

> PROD-001 제품은 어떤 원자재로 구성되어 있나?

모델 `gpt-4.1` · MCP `http://127.0.0.1:8100/mcp` · 도구 7개 · 시스템 프롬프트 5,030자 (서버가 제공)

에이전트는 도구를 **2회** 호출했다.

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
      "published_at": 1786937227.760473
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
      "… (총 10298자)
```

#### 2. `ontology_graph_cypher`

```json
{
  "query": "MATCH (p:_Entity:MfgProduct {product_id: $pid})<-[:REFERENCES_MFG_PRODUCT]-(b:_Entity:MfgProductBom)-[:REFERENCES_MFG_RAW_MATERIAL]->(m:_Entity:MfgRawMaterial) RETURN m.material_id AS material_id, m.material_name AS material_name, m.material_type AS material_type",
  "params": "{\"pid\": \"PROD-001\"}"
}
```

```json
{
  "rows": [
    {
      "material_id": "MAT-013",
      "material_name": "산업용 윤활유",
      "material_type": "화학물질"
    },
    {
      "material_id": "MAT-001",
      "material_name": "고탄소강 봉재",
      "material_type": "금속"
    },
    {
      "material_id": "MAT-011",
      "material_name": "베어링 볼 (Φ5mm)",
      "material_type": "금속"
    }
  ],
  "row_count": 3,
  "truncated": false
}
```

#### 최종 답변

PROD-001 제품은 다음과 같은 원자재로 구성되어 있습니다.

- 고탄소강 봉재 (금속)
- 베어링 볼 (Φ5mm) (금속)
- 산업용 윤활유 (화학물질)

근거:
- 그래프 탐색 결과, PROD-001 → MfgProductBom → MfgRawMaterial 관계를 따라 위 3개의 원자재(material_id: MAT-001, MAT-011, MAT-013)가 확인되었습니다.
- 총 3건의 원자재가 조회되었습니다.
