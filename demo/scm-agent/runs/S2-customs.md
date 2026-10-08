### [수출입] 통관 에이전트 — S2-customs

**통관 보류 사유 규명 → HS 코드 검증 → 정정신고 문안**

> 현재 통관 보류(HOLD) 또는 반려(REJECTED) 상태인 수출입 신고 건을 모두 찾아 사유를 정리하고, 각 건에서 신고 HS 코드가 품목 마스터의 HS 코드와 일치하는지 검증해줘. 불일치 건은 정정신고 문안을 제안해줘.

실행 경로 `ontology-studio /api/stream (AGENT_BACKEND=cliagents)` · 도구 호출 **6회** (오류 0) · 63.1s

#### 1. `Read`

```json
{
  "file_path": "/Users/uengine/ontologic/ontology-studio/.cache/sandbox/sessions/scm-demo-S2-customs-ef58aa60answer/.claude/skills/ontologic-agentic-rag/references/two-step-retrieval.md"
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
  "class_name": "CustomsDeclaration"
}
```

#### 4. `ontology_get_datasource_schema`

```json
{
  "class_name": "Item"
}
```

```json
{"result":"{\"class_name\": \"CustomsDeclaration\", \"description\": \"수입 통관 신고. 키 decl_id. 선적(ref_shipment_no=shipment_no)과 품목(ref_item_code=item_id)을 참조. 속성: 방향, 신고품목분류(declared_hs_code), 원산지, FTA적용, 원산지증명 요구·첨부(coo_required/attached), 송장가액, 관세율, 상태(status: CLEARED/FILED/DRAFT/HOLD/REJECTED), 보류사유(hold_reason), 신고일. 신고 HS코드와 품목 마스터 hs_code 의 정합이 판단 대상.\", \"source\": {\"datasource\": \"scm_customs\", \"schema\": \"customs\", \"table\": \"decl_header\"}, \"key_columns\": [\"decl_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"신고번호\", \"column\": \"decl_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"참조선적\", \"column\": \"ref_shipment_no\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"방향\", \"column\": \"direction\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"참조품목\", \"column\": \"ref_item_code\", \"type\": \"strin… (총 2072자)
```

```json
{"result":"{\"class_name\": \"Item\", \"description\": \"품목 마스터(원자재·완제품). 공급망 전체에서 참조되는 핵심 사물. 시스템별 키 표기가 다르다: ERP mst_item.item_id, WMS stock_daily.sku_code, 통관 decl_header.ref_item_code, CRM sku_code — 값 네임스페이스(ITM-…)는 동일. 속성: 품목명, 유형, HS코드(hs_code), 원산지, 표준원가, 안전재고(safety_stock), MOQ, 주공급사(primary_supplier_id)·대체공급사(alt_supplier_id).\", \"source\": {\"datasource\": \"scm_erp\", \"schema\": \"erp\", \"table\": \"mst_item\"}, \"key_columns\": [\"item_id\"], \"base_conditions\": [], \"columns\": [{\"property\": \"품목ID\", \"column\": \"item_id\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"품목명\", \"column\": \"item_name\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"유형\", \"column\": \"item_type\", \"type\": \"string\", \"description\": \"\"}, {\"property\": \"HS코드\", \"column\": \"hs_code\", \"type\": \"string\", \"description\": \"\"}, {\"property\"… (총 1719자)
```

#### 5. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT decl_id, ref_shipment_no, direction, ref_item_code, declared_hs_code, origin_country, fta_applied, coo_required, coo_attached, invoice_value_usd, duty_rate, status, hold_reason, filed_date FROM customs.decl_header WHERE status IN ('HOLD', 'REJECTED') ORDER BY status, decl_id"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"decl_id\", \"ref_shipment_no\", \"direction\", \"ref_item_code\", \"declared_hs_code\", \"origin_country\", \"fta_applied\", \"coo_required\", \"coo_attached\", \"invoice_value_usd\", \"duty_rate\", \"status\", \"hold_reason\", \"filed_date\"], \"rows\": [{\"decl_id\": \"DCL-2026-00114\", \"ref_shipment_no\": \"SHP-2026-0111\", \"direction\": \"IMPORT\", \"ref_item_code\": \"ITM-PCB-003\", \"declared_hs_code\": \"8534.00\", \"origin_country\": \"China\", \"fta_applied\": 1, \"coo_required\": 1, \"coo_attached\": 0, \"invoice_value_usd\": \"27952.80\", \"duty_rate\": \"8.00\", \"status\": \"HOLD\", \"hold_reason\": \"한-중 FTA 원산지증명서(C/O) 미첨부 — 협정세율 적용 보류\", \"filed_date\": \"2026-08-16\"}, {\"decl_id\": \"DCL-2026-00115\", \"ref_shipment_no\": \"SHP-2026-0111\", \"direction\": \"IMPORT\", \"ref_item_code\": \"ITM-PCB-001\", \"declared_hs_code… (총 2497자)
```

#### 6. `ontology_query_datasource_sql`

```json
{
  "sql": "SELECT item_id, item_name, hs_code, origin_country FROM erp.mst_item WHERE item_id IN ('ITM-PCB-003', 'ITM-PCB-001', 'ITM-PCB-004', 'ITM-CON-002')"
}
```

```json
{"result":"{\"status\": \"ok\", \"columns\": [\"item_id\", \"item_name\", \"hs_code\", \"origin_country\"], \"rows\": [{\"item_id\": \"ITM-PCB-001\", \"item_name\": \"4층 메인보드 PCB 120x80\", \"hs_code\": \"8534.00\", \"origin_country\": \"China\"}, {\"item_id\": \"ITM-PCB-003\", \"item_name\": \"FPCB 카메라 모듈용\", \"hs_code\": \"8534.00\", \"origin_country\": \"China\"}, {\"item_id\": \"ITM-PCB-004\", \"item_name\": \"6층 HDI PCB 전원모듈\", \"hs_code\": \"8534.00\", \"origin_country\": \"China\"}, {\"item_id\": \"ITM-CON-002\", \"item_name\": \"USB-C 리셉터클 24P\", \"hs_code\": \"8536.90\", \"origin_country\": \"Korea\"}], \"row_count\": 4, \"truncated_for_agent\": false, \"truncated\": false, \"sql\": \"SELECT item_id, item_name, hs_code, origin_country FROM erp.mst_item WHERE item_id IN ('ITM-PCB-003', 'ITM-PCB-001', 'ITM-PCB-004', 'ITM-CON-002') LIMIT 500\", \"source\": {\"datasource\": \"scm_erp… (총 906자)
```

#### 최종 답변

통관 신고 데이터를 조회하기 전에, 먼저 워크플로우 문서와 검색 힌트를 확인하고 그래프 스키마를 파악하겠습니다.그래프 스키마를 먼저 확인하겠습니다.스키마를 파악했습니다. `CustomsDeclaration`(통관 신고, scm_customs.customs.decl_header)과 `Item`(품목 마스터, scm_erp.erp.mst_item) 두 가상 클래스를 대조하면 됩니다. 두 클래스의 컬럼 스키마를 받겠습니다.두 클래스가 서로 다른 데이터소스(scm_customs, scm_erp)에 있어 단일 SQL 조인이 어려울 수 있습니다. 먼저 HOLD/REJECTED 신고 건을 조회하겠습니다.HOLD 3건, REJECTED 1건을 찾았습니다. 참조 품목 4개의 마스터 HS 코드를 조회해 대조하겠습니다.조회가 완료되었습니다. 두 데이터소스(통관 `scm_customs.customs.decl_header`, 품목 `scm_erp.erp.mst_item`)를 대조한 결과를 정리합니다.

---

## 1. 통관 보류(HOLD)·반려(REJECTED) 상태 신고 건 — 총 4건

`customs.decl_header` 에서 `status ∈ {HOLD, REJECTED}` (4행, 잘림 없음)

| 신고번호 | 방향 | 품목 | 상태 | 사유 |
|---|---|---|---|---|
| DCL-2026-00114 | IMPORT | ITM-PCB-003 (FPCB 카메라 모듈용) | **HOLD** | 한-중 FTA 원산지증명서(C/O) 미첨부 — 협정세율 적용 보류 |
| DCL-2026-00115 | IMPORT | ITM-PCB-001 (4층 메인보드 PCB) | **HOLD** | 한-중 FTA 원산지증명서(C/O) 미첨부 — 협정세율 적용 보류 |
| DCL-2026-00116 | IMPORT | ITM-PCB-004 (6층 HDI PCB) | **HOLD** | 한-중 FTA 원산지증명서(C/O) 미첨부 — 협정세율 적용 보류 |
| DCL-2026-00117 | EXPORT | ITM-CON-002 (USB-C 리셉터클 24P) | **REJECTED** | HS 코드 불일치 — 정정신고 필요 |

**사유 유형별 정리**
- **원산지증명 미비 (HOLD 3건)**: DCL-2026-00114/115/116 — 모두 동일 선적 `SHP-2026-0111`(중국발 수입)에 묶여 있고, `coo_required=1`인데 `coo_attached=0`. FTA 적용(8% 협정세율)을 받으려면 C/O 첨부가 필수인데 누락되어 보류. (온톨로지 규칙 R3의 '원산지증명 미비' 사유에 해당)
- **품목분류 오류 (REJECTED 1건)**: DCL-2026-00117 — HS 코드 불일치로 반려.

---

## 2. 신고 HS 코드 ↔ 품목 마스터 HS 코드 정합 검증

규칙 R4(`HsCodeConformity`): `CustomsDeclaration.ref_item_code = Item.item_id` 로 조인, `declared_hs_code = Item.hs_code` 면 CONFORM.

| 신고번호 | 품목 | 신고 HS | 마스터 HS | 판정 |
|---|---|---|---|---|
| DCL-2026-00114 | ITM-PCB-003 | 8534.00 | 8534.00 | ✅ CONFORM |
| DCL-2026-00115 | ITM-PCB-001 | 8534.00 | 8534.00 | ✅ CONFORM |
| DCL-2026-00116 | ITM-PCB-004 | 8534.00 | 8534.00 | ✅ CONFORM |
| DCL-2026-00117 | ITM-CON-002 | **8536.69** | **8536.90** | ❌ **MISMATCH** |

**HS 코드가 원인인 보류/반려는 DCL-2026-00117 단 1건**입니다. HOLD 3건은 HS 코드는 정상이며, 사유는 오직 C/O 미첨부입니다. (즉 3건은 정정신고가 아니라 원산지증명서 보완 제출로 해소됩니다.)

---

## 3. 불일치 건 정정신고 문안 제안 — DCL-2026-00117

> **통관 신고 정정 신청서 (안)**
>
> - **신고번호**: DCL-2026-00117 (수출 / EXPORT)
> - **대상 품목**: ITM-CON-002 「USB-C 리셉터클 24P」 (원산지: 한국)
> - **정정 항목**: 품목분류(HS 코드)
> - **정정 전 (당초 신고)**: `8536.69`
> - **정정 후 (정정 요청)**: `8536.90`
> - **정정 사유**: 당사 품목 마스터(ERP `mst_item`) 상 해당 품목의 확정 품목분류는 HS 8536.90 이나, 최초 신고 시 8536.69 로 오기재되었습니다. 세번 오분류에 따른 반려(REJECTED) 건으로, 품목 마스터 기준값에 맞추어 8536.90 으로 정정 신고합니다.
> - **첨부**: 품목 규격서 / 품목 마스터 등록내역 (HS 8536.90 근거)
> - **비고**: 송장가액 USD 5,700.00, 관세율 신고값 0.00%(수출), FTA 적용 대상. 정정 후 세번 변경에 따른 세율·요건 재검토 필요 여부 확인 요망.

> ℹ️ 참고: 8536.69(플러그·소켓류)와 8536.90(기타 접속기기)은 같은 8536 호 내 소호 차이입니다. 최종 세번은 품목 마스터 기준(8536.90)을 따르되, 실제 정정신고 제출 전 관세사·품목분류 사전심사 결과와 한 번 더 대조하시길 권합니다.

---

**근거**
- 그래프: `CustomsDeclaration —CLASSIFIES→ Item` (조인 `ref_item_code = item_id`), 판단 규칙 `CustomsHoldReason`(R3)·`HsCodeConformity`(R4).
- 데이터: `scm_customs.customs.decl_header` 4행(HOLD 3·REJECTED 1) + `scm_erp.erp.mst_item` 4행. 두 이기종 시스템을 품목 키(ITM-…)로 대조.

#### 채점

- PASS `DCL-2026-00117`
- PASS `8536\.?69`
- PASS `8536\.?90`
- PASS `원산지증명|C/O`
- PASS `DCL-2026-0011[456]`

**결과: PASS**
