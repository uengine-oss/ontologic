### 질문

> 일별 매출(mfg_daily_sales) 테이블에서 매출 총액을 구해줘.

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

#### 2. `ontology_get_datasource_schema`

```json
{
  "class_name": "MfgDailySales"
}
```

```json
{
  "error": "'MfgDailySales' 은 데이터소스에 바인딩된 클래스가 아닙니다. graph://schema 에서 binding_kind 가 virtual 인 클래스를 고르세요."
}
```

#### 최종 답변

질문하신 "mfg_daily_sales" 테이블(혹은 이에 해당하는 MfgDailySales 클래스)은 현재 발행된 온톨로지(그래프)에서 데이터소스에 바인딩된 클래스가 아닙니다. 즉, "MfgDailySales"라는 이름의 가상 클래스가 존재하지 않거나, 데이터 테이블과 연결되어 있지 않아 직접 집계할 수 없습니다.

현재 데이터소스에 바인딩된 일별 데이터 클래스는 다음과 같습니다:
- MfgDailyEquipment (설비별 일별 데이터)
- MfgDailyProcessMetrics (공정별 일별 메트릭)
- MfgDailyQualityIssue (품질 이슈)

만약 "mfg_daily_sales" 테이블이 실제로 존재한다면, 온톨로지에 해당 테이블이 바인딩되어 발행되어야 집계가 가능합니다. 온톨로지에 바인딩된 클래스만 조회할 수 있으며, 그 외의 테이블은 접근할 수 없습니다.

추가로, 온톨로지에 "MfgDailySales" 클래스가 바인딩되어 있지 않은 이유는 다음과 같을 수 있습니다:
1. 온톨로지 설계 시 해당 테이블이 포함되지 않았거나,
2. 아직 발행되지 않았거나,
3. 데이터소스 확장 권한(MCP_ALLOW_DATASOURCE_EXPANSION)이 활성화되어 있지 않을 수 있습니다.

따라서, "mfg_daily_sales" 테이블의 매출 총액을 집계하려면 먼저 온톨로지에 해당 테이블이 바인딩되어야 합니다.
