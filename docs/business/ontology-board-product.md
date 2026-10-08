# Ontologic Board — 온톨로지 객체에서 대시보드를 만드는 제품 (2026-08-19)

`ontology-studio-strategy.md` §3 경계표와 §6 로드맵 **9. Enterprise 분리 설계** 가 자리를
비워 두었고, [`specs/006-visualization-and-report/spec.md`](../../specs/006-visualization-and-report/spec.md)
가 *"대시보드 저장·공유 / BI 커넥터 / 드릴다운"* 을 `## Out of Scope` 로 밀어 두었다.
이 문서는 그 자리를 하나의 제품으로 세운 결정 기록이다.

명세 전문이 아니라 **무엇을 정했고 왜 그렇게 정했는지**만 담는다. 요구사항·규칙표·수용 기준은
[`specs/011-ontology-board/spec.md`](../../specs/011-ontology-board/spec.md) 에 있다.

입력은 *"발전 및 송배전 도메인 특화 아파치 슈퍼셋 위젯-객체 유형 AI 자동 매핑 체계 연구 보고서"*
이고, 이 문서는 그 보고서를 **이 플랫폼의 실제 계약 위에서 성립하는 형태로 다시 쓴 것**이다.

> **제품명은 잠정이다.** "Ontologic Board" 는 Ontology Studio 와 나란히 놓기 위한 작업명이다.

---

## 1. 왜 지금인가

전략 §1 대조표가 사업안의 전제를 셋으로 나눴고, **시각화·리포트가 코드 0인 유일한 항목**이었다.
006 이 그 공백의 앞쪽 절반 — 질의 결과에 딸려 나오는 세션 한정 차트 — 을 설계했다. 뒤쪽 절반은
비어 있다. 그리고 그 뒤쪽이 **현업 사용자가 실제로 사는 물건**이다. 아무도 "질문할 때마다 차트가
뜨는 채팅"을 사려고 예산을 세우지 않는다. 대시보드를 사려고 세운다.

동시에 spec 010 이 조용히 큰 것을 만들어 놨다 — **스튜디오 없이 온톨로지를 읽고 데이터소스까지
확장하는 MCP 표면**이다. [`agentic-rag-walkthrough.md`](../agentic-rag-walkthrough.md) 는 그
표면만으로 에이전트가 그래프 탐색 → JIT 스키마 → DB 집계를 스스로 밟는 것을 실측으로 남겼다.

**이 제품의 착상은 여기서 나온다.** 워크스루의 호출 순서를 LLM 이 매번 재발견하게 두지 않고,
**코드가 결정적으로 밟으면 그것이 곧 대시보드다.**

---

## 2. 제품 정의 — 세 겹

Ontology Studio 와 같은 셸 안에서 도는 자매 제품.

| 겹 | 하는 일 | 원칙 |
|---|---|---|
| **매핑 엔진** | MCP 로 읽은 온톨로지 지도와 JIT 스키마에서 객체 유형을 판정하고 위젯·축 매핑을 낸다 | **결정적.** LLM 은 위젯을 고르지 않는다 |
| **위지윅 빌더** | 좌(객체 팔레트)·중(그리드 캔버스)·우(인스펙터). 클래스를 끌어다 놓으면 위젯이 즉시 배치되고, 그려진 차트의 요소를 클릭하면 그 요소의 인스펙터가 열린다 | 드래그·클릭이 1급 조작 |
| **바이브코딩** | 선택된 위젯/요소가 에이전트의 컨텍스트가 된다. "이 막대를 지역별로 쪼개줘" | 에이전트는 코드가 아니라 **검증된 스펙 패치**를 낸다 |

---

## 3. 왜 MCP 위에 올리는가 — 이 제품의 가장 중요한 결정

대시보드 백엔드는 Neo4j 드라이버도 DB 커넥션도 갖지 않는다. `ontology-studio-search` MCP 서버에
**클라이언트로 붙어** 도구를 호출한다. 호출 주체는 LLM 이 아니라 **코드**다.

| 대시보드 기능 | MCP 호출 | 워크스루 대응 |
|---|---|---|
| 객체 팔레트 | `resources/read graph://schema` | 전 시나리오 1단계 |
| 클래스를 캔버스에 드롭 → 컬럼 확보 | `ontology_get_datasource_schema(class)` | 시나리오 1 ③ · 3 ② |
| Neo4j 위젯 데이터 | `ontology_graph_cypher(query, params)` | 시나리오 1 ② · 2 ② |
| 데이터소스 위젯 데이터 | `ontology_query_datasource_sql(sql, limit)` | 시나리오 1 ④ · 3 ③ |
| 필터 값을 이름으로 찾기 | `ontology_resolve_entity(text, class_name)` | 시나리오 7 ① |

### 얻는 것 ① — 자격증명을 아예 갖지 않는다

MCP 표면이 이미 보장하는 것을 대시보드가 코드 한 줄 없이 상속한다.

- 카탈로그 라벨(`DataSource`/`Schema`/`Table`/`Column`)과 발행 레지스트리(`_Ontology*`) Cypher 는
  **서버가 거부한다** — 전자는 평문 password, 후자는 `sql_template` 을 갖는다
  ↳ `ontology_mcp/runtime_adapters.py:34-46`
- SQL 은 **발행 바인딩된 테이블만** 참조 가능하고 데이터소스는 바인딩에서 유도된다(호출자가 못 고른다)
- `pii` 컬럼은 응답에서 제거되고, `LIMIT` 은 서버가 적용하며, 표면 전체가 읽기 전용이다

constitution 원칙 V 를 **설계로** 만족한다. 직접 붙었다면 이 전부를 다시 구현하고 다시
검증해야 했고, 회귀 시 유출로 이어졌을 것이다.

### 얻는 것 ② — OSS→Enterprise 전환이 설정 변경이다

전략 §3 은 Enterprise 를 *"중앙 MCP 엔드포인트, 사용자별 토큰"* 으로 정의했다. 대시보드가 MCP
클라이언트이므로 로컬 stdio → 중앙 HTTP + 토큰 전환에 **코드 변경이 없다.** 경계가 배포 구성으로
갈린다.

### 치르는 값 — 행 예산이 에이전트 기준이다 (실측)

MCP 표면은 **LLM 컨텍스트를 위해** 치수가 잡혀 있다. 2026-08-19 `제조 하이브리드` 에서 실측:

| 경로 | 실제 존재 | 요청 | **돌려받은 행** | `row_count` | 상한 출처 |
|---|---|---|---|---|---|
| `ontology_graph_cypher` | 33 | (제한 인자 없음) | **20** | **20 — 참값 아님** | `MCP_MAX_RESULTS` 기본 20 |
| `ontology_query_datasource_sql` | 3,510 | `limit=200` | **30** | 200 (참값) | `DATASOURCE_AGENT_ROW_PREVIEW` 기본 30 |

두 경로의 차이가 중요하다. **SQL 경로는 잘린 양을 알려주지만 Cypher 경로는 알려주지 않는다.**
`row_count` 가 잘린 뒤의 수라서, 호출자는 20건이 전부인지 33건 중 20건인지 구분할 수 없다.
`truncated: true` 플래그만 있다. 이것은 spec 006 CR-3 이 지적한 결함과 같은 종류가 MCP 표면에서
반복되는 것이다.

대응은 §8 AD-10 에 적었다. 요지는 셋이다 — **규칙이 먼저 집계로 줄이고**, 총계는 **별도 count
질의**로 얻고(1행이라 상한과 무관, 실측 확인), 그래도 모자라면 대시보드는 **자기 설정의 MCP
인스턴스**에 붙는다.

---

## 4. 객체 유형 ↔ 위젯 매핑

보고서 §3 의 전력 특화 객체 유형표를 **MCP 응답에서 판정 가능한 신호**로 다시 쓴 것.
전력 도메인 어휘는 어디에도 하드코딩되지 않는다 — 전력 대시보드가 나오는 이유는 온톨로지 자체가
전력 모델이기 때문이다. 제조 온톨로지를 물리면 제조 대시보드가 나온다.

| # | 객체 유형 | 판정 신호 | 위젯 | 보고서 대응 |
|---|---|---|---|---|
| O1 | 시계열 관측 | `temporal` 1 + `numeric` ≥1 + 인스턴스 ≥3 | `timeseries_line` | 센서 시계열 태그 |
| O2 | 분포·상태 | `categorical` 1 + `numeric` 연속(고유값 ≫ 범주수) | `box_plot` | 설비 진동/상태 |
| O3 | 계층 자산 | `categorical` ≥2 이고 카디널리티 단조 증가, **또는** 자기참조 관계 존재 | `treemap` / `sunburst` | 설비 계층 마스터 |
| O4 | 공간 점 | 위·경도 속성 쌍 (이름 패턴 + 값 범위 ±90/±180) | `geo_point` | 변전소·개폐소 |
| O5 | 공간 경로 | GeoJSON `LineString` 또는 WKT `LINESTRING` | `geo_path` | 송·배전선로 |
| O6 | 공간 면 | GeoJSON `Polygon`/`MultiPolygon` | `geo_polygon` | 정전 영향 구역 |
| O7 | 비정형 텍스트 | `string` 평균 길이 > 40 이고 고유값 ≈ 인스턴스 수 | `word_cloud` + `table` | 정비·경보 로그 |
| O8 | 매트릭스 | `categorical` 2 (각 k ≤ 15) + `numeric` 1 | `pivot_table` / `heatmap` | 설비 건전도 매트릭스 |
| O9 | 단일 지표 | 인스턴스 1 + `numeric` 1~6 | `kpi` / `kpi_group` | — |
| O10 | 그 외 | | **`table` (폴백 — 억지로 그리지 않는다)** | — |

속성 역할 판정과 가드 G1–G6 은 **spec 006 의 것을 그대로 승계한다.** 새 매핑표를 만들지 않는다.
이 표는 006 의 R1–R13 위에 **객체 유형 축과 공간·계층·텍스트 위젯을 더한 것**이다.
`identifier` 판정에는 MCP 가 주는 `native_key` / `key_columns` / `column_map[].reference` 가
그대로 쓰인다.

판정 근거(`rule: "O5"`, `reason`)는 **사용자에게 보여준다** — 자동으로 정해진 위젯은 왜 그
모양인지 말할 수 있어야 신뢰된다.

---

## 5. Superset 대응표 — 그리고 그 한계

| WidgetKind | Superset `viz_type` | 핵심 `form_data` |
|---|---|---|
| `timeseries_line` | `echarts_timeseries_line` | `x_axis`, `metrics`, `groupby`, `time_grain_sqla` |
| `bar` / `bar_h` | `echarts_timeseries_bar` | `x_axis`, `metrics`, `orientation` |
| `pie` | `pie` | `groupby`, `metric` |
| `box_plot` | `box_plot` | `columns`, `groupby`, `whiskerOptions` |
| `treemap` | `treemap_v2` | `groupby[]`, `metric` |
| `sunburst` | `sunburst_v2` | `columns[]`, `metric` |
| `word_cloud` | `word_cloud` | `series`, `metric` |
| `heatmap` | `heatmap_v2` | `x_axis`, `groupby`, `metric` |
| `scatter` | `echarts_timeseries_scatter` | `x_axis`, `metrics` |
| `kpi` | `big_number_total` | `metric`, `subheader` |
| `pivot_table` | `pivot_table_v2` | `groupbyRows`, `groupbyColumns`, `metrics` |
| `geo_point` | `deck_scatter` | `spatial`, `point_radius_fixed`, `color_picker` |
| `geo_path` | `deck_path` | `line_column`, `line_type`, `color_picker` |
| `geo_polygon` | `deck_polygon` | `geojson`, `fill_color_picker` |
| `table` | `table` | `groupby`, `metrics`, `all_columns` |

**한계를 먼저 적는다. Superset 은 Neo4j 를 읽지 못한다.**

- 가상 클래스(RDB 바인딩) 위젯 → 내보내기 성립. 보고서 §6-2 의 payload 예시가 여기 산출물이다
- **materialized(Neo4j) 위젯 → 내보낼 수 없다.** UI 가 그 사실을 위젯마다 표시한다

사용자가 고른 기본 경로가 Neo4j 모드이므로, **첫 대시보드는 대체로 내보낼 수 없다**는 뜻이다.
이것을 숨기면 영업 자리에서 터진다. 내보내기는 "RDB 에 바인딩된 온톨로지를 가진 고객"의 기능으로
포지셔닝한다.

---

## 6. 전력 도메인 시나리오

보고서 §5 를 이 플랫폼의 호출 순서로 다시 쓴 것. 각 시나리오는 **Ontology Studio 가 어떤 문서로
이 모델을 만들었는가**에서 시작한다 — 표준(IEC 61850/CIM) 어휘 매핑은 쓰지 않는다.

### 6-1. 터빈 축진동 이상 탐지 (O1 + O2)

*입력 문서*: 설비 태그 명세서(Excel), 운전 기준서(PDF). 스튜디오가 `설비`, `센서관측` 클래스와
`관측대상` 관계를 만든다.

```
1. resources/read graph://schema              → 센서관측 이 materialized 임을 확인
2. ontology_graph_cypher(RETURN n LIMIT 200)  → 값에서 타입 추론: 측정시각=temporal, 진동값=numeric
3. 매핑 엔진                                    → O1 판정 → timeseries_line
4. ontology_graph_cypher(집계 Cypher)          → 서버가 avg() 로 집계, 일→주 승격으로 20점 이하
5. 같은 프로파일로 O2 판정                       → box_plot 보조 위젯 자동 병렬 추천
```

보고서의 *"동일한 수치 컬럼을 box_plot 의 입력값으로 매핑하는 보조 차트를 병렬로 자동 추천"* 이
그대로 성립한다 — 한 클래스가 O1 과 O2 를 **동시에** 만족하기 때문이다.

### 6-2. 송전선로 부하 지도 (O5)

*입력 문서*: 선로 대장(Excel), 계통도(PDF), 경로 GeoJSON.

```
1. resources/read graph://schema
2. ontology_graph_cypher(RETURN n LIMIT 200)  → 경로형상 값이 GeoJSON LineString 임을 감지
3. 매핑 엔진                                    → O5 판정 → geo_path
4. 색상 = 부하율, 굵기 = 전압등급 (인스펙터에서 포인트 클릭으로 조정)
```

**타일 서버를 쓰지 않는다.** ECharts `geo` 에 GeoJSON 을 `registerMap` 으로 등록해 경계 위에
`lines` 시리즈를 얹는다. 외부 네트워크 0 — 006 R12 의 기각 사유를 정면으로 회피한다(§8 AD-5).

### 6-3. 설비 계층 정비비 (O3)

*입력 문서*: 자산 계층 마스터, 정비 실적 대장.

```
1. resources/read graph://schema              → 자산 클래스에 자기참조 관계 존재
2. ontology_graph_cypher(카디널리티 샘플)       → 호기 < 계통 < 설비 단조 증가 확인
3. 매핑 엔진                                    → O3 판정 → treemap, groupby 순서 = 카디널리티 오름차순
4. ontology_graph_cypher(sum(정비비) 집계)
```

`groupby` 계층 순서를 **카디널리티 오름차순으로 자동 결정**한다. 보고서는 이 순서를 사람이 아는
것으로 전제했지만, 여기서는 데이터에서 나온다.

---

## 7. 오픈코어 경계 개정안

전략 §3 표의 시각화·리포트·BI 3행을 아래로 대체한다. 원칙(*"1인 1머신에서 완결되는 것은 전부
무료"*)은 유지된다 — 대시보드 **파일**은 무료이고 대시보드 **서버**가 유료다.

| 영역 | OSS (개인용 축소판) | Enterprise |
|---|---|---|
| 대시보드 | 로컬 파일로 저장·열기, 1인 1머신 | **중앙 저장소, 공유, 버전, 폴더/권한** |
| 위젯 자동 매핑 | 전체 규칙 | 동일 |
| 위지윅 편집·바이브코딩 | 전체 기능 (로컬 에이전트) | 동일 + 조직 공용 템플릿 |
| MCP 연결 | 로컬 stdio/HTTP, 단일 사용자 | **중앙 엔드포인트, 사용자별 토큰, 전용 행 예산** |
| 새로고침 | 수동 | **스케줄 새로고침, 캐시, 배포(메일/슬랙)** |
| 인증·감사 | 없음 | **SSO/RBAC, 감사 로그** |
| BI 연동 | 없음 | **Superset/Metabase 내보내기·동기화** |

우회 위험: 무료판으로 만든 대시보드 파일을 사람끼리 주고받는 것은 **의도된 사용**이다(그게
바이럴이다). 그 상태로는 공유 권한·정기 갱신·감사가 전혀 안 된다.

---

## 8. 아키텍처 결정 요약

| | 결정 | 근거 |
|---|---|---|
| **AD-1** | 애플리케이션은 **MCP 클라이언트**. 코드가 도구를 직접 부른다 | §3 |
| **AD-2** | 위젯 선택은 결정적. LLM 은 문구·순서·라벨 제안에만 | 006 AD-1, constitution |
| **AD-3** | 집계는 서버(Cypher/SQL)가. 클라이언트 재집계 금지 | 006 AD-5, 001 FR-028 |
| **AD-4** | materialized 클래스의 **타입은 값 추론**으로 채운다 | 실측: `graph://schema` 는 `property_names` 만 주고 타입이 없다 |
| **AD-5** | 지도는 **타일 없이** ECharts `geo` + GeoJSON | 006 R12 의 기각 사유(외부 네트워크)를 회피 |
| **AD-6** | 정본은 텍스트 `DashboardSpec`. 자격증명 0 | 009 의 텍스트 패키지 원칙 |
| **AD-7** | 프론트는 ontology-studio 안. 차트 래퍼는 robo-data-frontend 에서 이식 | 바이브코딩은 채팅·캔버스가 한 런타임이어야 성립 |
| **AD-8** | 읽기는 `ontology_mcp`, **쓰기는 agent-bridge MCP 의 새 `dashboard` 모드** | spec 004 **FR-013** — 읽기 전용 서버의 보안 경계를 넓히지 않는다 |
| **AD-9** | Superset 은 내보내기 타깃. 가상 클래스에서만 성립 | §5 |
| **AD-10** | 행 예산 20/30 은 **집계로 흡수**하고, 총계는 별도 count 질의로, 부족하면 전용 MCP 프로파일 | §3 실측 |

### AD-4 를 정한 과정 (실측)

`MfgProduct`(materialized) 의 `graph://schema` 엔트리 원문:

```json
{"class_name": "MfgProduct", "binding_kind": "materialized",
 "property_names": ["created_date","is_active","lead_time_days","min_order_qty",
                    "product_category","product_id","product_name","unit_cost","unit_price"],
 "property_source": "graph_schema_api", "native": true, "native_key": ["product_id"]}
```

**타입이 없다.** 그리고 `ontology_get_datasource_schema` 는 가상 클래스 전용이라
*"binding_kind 가 virtual 인 클래스를 고르세요"* 로 거절한다 (`runtime_adapters.py:348`).

| 선택지 | 판정 |
|---|---|
| `graph://schema` 에 타입을 싣는다 | **기각** — 지도에 모든 클래스의 모든 컬럼이 실린다. 이 설계가 없애려는 바로 그 토큰 과부하 |
| **노드를 통째로 RETURN 해 값에서 추론** | **채택** — constitution 원칙 0 이 `properties(n)` 대신 명시한 형태. 계약 변경 0. 실측 동작 확인 |
| MCP 에 `ontology_get_class_profile` 추가 | **미결정** — 표면이 일관돼지지만 spec 010 FR-016(플래그 off 시 도구 정확히 4개) 때문에 010 개정 수반 |

### AD-10 의 세 갈래

1. **규칙이 먼저 줄인다.** time_grain 승격(일→주→월), 범주 상위 N + 기타. 이건 BI 설계로도
   옳다 — 006 R5·R8 이 *"시리즈가 너무 많으면 표"* 라고 한 것과 같은 정신이다.
2. **총계는 별도 count 질의로 얻는다.** `RETURN count(n)` 은 1행이라 상한과 무관하다(실측 확인).
   그래야 배지에 *"33건 중 20건"* 이라고 정직하게 쓸 수 있다.
3. **그래도 모자라면 전용 MCP 인스턴스.** `MCP_MAX_RESULTS` 를 올린 프로파일로 대시보드만
   붙인다. 에이전트용 인스턴스 값은 건드리지 않는다 — AD-1 덕분에 엔드포인트만 다르면 된다.

---

## 9. 로드맵과 완료 판정

전략 §6 의 규칙을 승계한다. **구현 작업은 영상 증거 없이 완료로 치지 않는다.**

- [x] 0. 실측 조사 → 이 문서 §3·§8
- [ ] 1. speckit spec 011 → [`specs/011-ontology-board/spec.md`](../../specs/011-ontology-board/spec.md)
- [ ] 2. MCP 클라이언트 + 프로파일러 (`modules/board/mcp_client.py`, `profile.py`)
- [ ] 3. 매핑 엔진 O1~O10 (`widget_map.py`) · 단위 테스트
- [ ] 4. 쿼리 생성기 Cypher/SQL (`query_gen.py`) — 필터는 params, `CALL` 금지
- [ ] 5. ECharts 래퍼 이식 + 그리드 캔버스 · **영상 증거**
- [ ] 6. 인스펙터(포인트 클릭 편집) · **영상 증거**
- [ ] 7. 바이브코딩 (`dashboard` 모드 + `skills/dashboard-edit/SKILL.md`) · **영상 증거**
- [ ] 8. `DashboardSpec` 저장·열기 · Superset 내보내기
- [ ] 9. Enterprise 분리 (중앙 저장소·RBAC·스케줄)

증거는 `ontology-studio/demo/` 의 Playwright headed 파이프라인으로 만들고
`docs/business/evidence/<번호>-<이름>/` 에 보관한다.

---

## 10. 아직 결정되지 않은 것

- **제품명.** "Ontologic Board" 는 작업명이다.
- **지도용 GeoJSON 의 출처.** 대한민국 행정경계를 번들할 것인가(라이선스·용량), 온톨로지 속성에서
  읽을 것인가. 후자는 시도 단위 경계가 데이터에 없으면 성립하지 않는다.
- **`ontology_get_class_profile` 도구화** (AD-4 3안) — spec 010 개정 수반.
- **`ontology_graph_cypher` 의 per-call `limit` 인자** (AD-10 3안의 대안) — SQL 도구와 대칭이
  되어 표면이 일관돼지지만 역시 010 개정 수반.
- **가격 모델과 라이선스** — 전략 §7 의 미결정 항목이 그대로 걸린다.
