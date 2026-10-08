# 계약 — 에이전트 도구 (`dashboard` 모드)

**방향**: 이 기능이 **제공하는** 계약. 내장 에이전트와 외부 CLI 에이전트가 함께 쓴다.

**어디에 올리는가**: `agent_bridge_mcp` 의 **새 `dashboard` 모드 엔드포인트**.
읽기 전용 `ontology_mcp` 서버에 올리지 않는다 — spec 004 **FR-013** 이 명시적으로 금지한다:

> 이 서버는 기존 읽기 전용 검색 서버(`ontology_mcp`)와 **별개**여야 한다. 그 서버의 보안 경계를
> 넓히면 안 된다.

확장 지점은 이미 있다 — `agent_bridge_mcp/router.py:14` 의
`_MODES = ("build", "answer", "answer_nods", "brief_draft")` 에 `"dashboard"` 를 더하고,
`server.py:tools_for()` 에 분기를 더한다. 엔드포인트는 `{MOUNT_PREFIX}/dashboard`.

**같은 함수 객체**를 내장 경로(`service.py` 의 `_DASHBOARD_MODE_TOOLS`)와 브리지가 공유해야
한다 (spec 004 FR-011).

---

## 도구 셋 — 셋뿐이다

### `dashboard_get(dashboard_id) -> dict`

현재 `DashboardSpec` 과 위젯별 해소 판정. 읽기.

### `widget_recommend(class_name, schema_name="", hint="") -> dict`

결정적 매핑 엔진을 부른다. **에이전트가 위젯을 고르는 것이 아니라, 엔진에게 물어보는 것이다**
(AD-2). 반환은 `{primary, secondary[], profile_summary}`.

### `dashboard_patch(dashboard_id, patch, dry_run=True) -> dict`

`DashboardSpec` 의 패치. **`dry_run` 기본값이 `True`** 다.

```
{ "valid": bool, "diff": [...], "errors": [{"path": "...", "reason": "..."}] }
```

검증 항목 (FR-051):
- 참조하는 클래스가 `graph://schema` 에 있다
- 참조하는 속성이 그 클래스의 `property_names` / `column_map` 에 있다
- `widget_kind` ∈ 닫힌 목록
- `filters[].param_key` 가 `params` 에 있다
- 결과 문서가 불변식을 만족한다 (자격증명 키 없음, 질의문 없음)

하나라도 어기면 **적용하지 않고** `errors` 를 낸다.

---

## 올리지 않는 것

| 도구 | 왜 |
|---|---|
| `execute` (임의 코드 실행) | FR-050. "바이브코딩"은 코드 실행이 아니라 **스펙 패치**다 |
| `sandbox_write` / `sandbox_read` | 같은 이유. 파일 경로는 서버가 정한다 |
| `neo4j_cypher` (쓰기) | 대시보드는 그래프를 바꾸지 않는다 |
| 데이터소스 쓰기 도구 일체 | 없다 |

`answer` 모드의 "쓰기 도구 없음" 경계는 **건드리지 않는다** (FR-083). 새 모드를 만들어 넓힌다 —
constitution 의 *"모드별 권한을 넓히지 않는다. MCP 엔드포인트는 모드마다 분리하고"* 를 그대로
따르는 형태다.

---

## 지시문

`skills/dashboard-edit/SKILL.md` **하나**가 원천이다 (FR-055).

- 파이썬에서 프롬프트 문장을 조립하지 않는다 — constitution *"지시문과 값을 섞지 않는다"*
- 선택된 위젯·클래스·프로파일은 **값**이므로 라벨 블록으로 전달한다
- 두 에이전트 백엔드가 `skill_registry` 를 통해 같은 파일을 읽는다 (spec 005)

스킬이 반드시 담아야 하는 것:

1. **권한 경계** — 위젯을 직접 고르지 말고 `widget_recommend` 를 부를 것. 코드 실행 도구가
   없다는 것. 그래프를 바꾸지 않는다는 것
2. **`dry_run` 규율** — 항상 먼저 `dry_run=True` 로 부르고 diff 를 사용자에게 보인 뒤 승인을 받을 것
3. **도구가 없으면 시작하지 말 것** — 기존 스킬들과 같은 전제 점검 절
