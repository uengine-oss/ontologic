# 계약 — WidgetKind → Superset viz_type

**방향**: 이 기능이 **내보내는** 계약. Superset `POST /api/v1/chart/` 가 받는 형태.

**적용 조건**: 위젯의 클래스가 **가상(RDB 바인딩)** 일 때만. Superset 은 Neo4j 를 읽지 못한다.
materialized 위젯은 제외하고 사유를 낸다 (AD-9, FR-071).

---

## 대응표

| WidgetKind | `viz_type` | 필수 `form_data` |
|---|---|---|
| `timeseries_line` | `echarts_timeseries_line` | `x_axis`, `metrics[]`, `groupby[]`, `time_grain_sqla` |
| `bar` | `echarts_timeseries_bar` | `x_axis`, `metrics[]`, `orientation: "vertical"` |
| `bar_h` | `echarts_timeseries_bar` | 같음 + `orientation: "horizontal"` |
| `pie` | `pie` | `groupby[]`, `metric` |
| `box_plot` | `box_plot` | `columns[]`, `groupby[]`, `whiskerOptions` |
| `treemap` | `treemap_v2` | `groupby[]` (계층 순서), `metric` |
| `sunburst` | `sunburst_v2` | `columns[]`, `metric` |
| `word_cloud` | `word_cloud` | `series`, `metric` |
| `heatmap` | `heatmap_v2` | `x_axis`, `groupby`, `metric` |
| `scatter` | `echarts_timeseries_scatter` | `x_axis`, `metrics[]` |
| `kpi` | `big_number_total` | `metric`, `subheader` |
| `kpi_group` | (분해) | KPI 개수만큼 `big_number_total` 차트로 **분해한다** |
| `pivot_table` | `pivot_table_v2` | `groupbyRows[]`, `groupbyColumns[]`, `metrics[]` |
| `geo_point` | `deck_scatter` | `spatial{latCol,lonCol}`, `point_radius_fixed`, `color_picker` |
| `geo_path` | `deck_path` | `line_column`, `line_type: "geojson"`, `color_picker` |
| `geo_polygon` | `deck_polygon` | `geojson`, `fill_color_picker` |
| `table` | `table` | `groupby[]`, `metrics[]` \| `all_columns[]` |

`kpi_group` 만 1:1 이 아니다 — Superset 에 "여러 큰 숫자" 위젯이 없으므로 분해한다.
분해된 차트는 `slice_name` 에 지표명을 덧붙인다.

---

## 페이로드 형태

```json
{
  "slice_name": "송전선로 구간별 실시간 부하율",
  "viz_type": "deck_path",
  "datasource_id": null,
  "datasource_type": "table",
  "params": "{\"viz_type\":\"deck_path\",\"line_column\":\"path_geojson\",\"line_type\":\"geojson\",\"metric\":{\"aggregate\":\"AVG\",\"column\":{\"column_name\":\"current_load_pct\"},\"expressionType\":\"SIMPLE\",\"label\":\"평균 부하율(%)\"}}"
}
```

**속성명이 아니라 컬럼명을 쓴다.** `ObjectProfile.properties[].column` 이 그 값이다 — 온톨로지
속성명(`가동률`)을 넣으면 Superset 이 찾지 못한다.

---

## 우리가 채우지 않는 것

| 필드 | 왜 |
|---|---|
| `datasource_id` | Superset 안의 Dataset id 다. 우리는 Superset 의 상태를 모른다 |
| 접속정보 | 갖고 있지 않다 (AD-1). 애초에 채울 수 없다 |

`datasource_id` 는 `null` 로 두고 **`{datasource, schema, table}` 를 함께 낸다.** 받는 쪽이
그 조합으로 Dataset 을 찾거나 만든다. Dataset 자동 생성·동기화는 Enterprise 범위다.

---

## 제외 사유

| `reason` | 언제 |
|---|---|
| `materialized_not_exportable` | 클래스가 materialized — Superset 이 Neo4j 를 못 읽는다 |
| `no_superset_equivalent` | WidgetKind 에 대응이 없다 (현재 없음, 목록 확장 시 대비) |
| `missing_column_mapping` | 속성에 물리 컬럼이 없다 |

**제외는 조용히 하지 않는다** — `excluded[]` 에 위젯 id 와 사유를 담아 UI 가 위젯 위에 표시한다.
