# SCM-Agent 데모 — 공급망 업무 멀티 에이전트 실행 기록

이 폴더는 **「AI 에이전트 기반 기업 공급망 관리 업무 지능화 시스템 상용화」**
(2026-AI응용제품-06-53) 사업계획서의 근거 자료다. 설계 설명이 아니라 **실행 기록**이다.

여섯 개 공급망 업무 도메인(계약·구매·조달·수출입·재고관리·고객지원)의 질문을, 온톨로지
스튜디오의 에이전트가 **호출 순서를 지시받지 않은 채** 스스로 도구를 골라 답했다. 그 과정과
결과를 그대로 옮겼다.

- 실행 기록(도구 인자·결과 원본): [`runs/`](runs/)
- 채점 요약: [`runs/summary.json`](runs/summary.json)
- 영상·스틸: [`video/`](video/) — 본편 `SCM-Agent-Suite-데모.mp4` (7분 46초, 1600×900, 한국어 내레이션), 자막 내장본, `.srt`
- 시연 결과 해설: [`../../docs/scm-agent-demo.md`](../../docs/scm-agent-demo.md)

---

## 실행 환경 (2026-08-21 실측)

| 구성 | 값 |
|---|---|
| 그래프 | Neo4j `2025.11.2-community`, bolt **7688** |
| 업무 시스템 | **4종** — ERP·관세(PostgreSQL 5433) / WMS·CRM(MySQL 3307) |
| 연계 계층 | data-fabric **8004** → MindsDB **47334** 등록 + Neo4j 카탈로그 적재 |
| 질의 실행 | neo4j-text2sql **8020** |
| 에이전트 | **ontology-studio 8010**, `AGENT_BACKEND=cliagents` / `EXTERNAL_AGENT_ID=claude-code` |
| **LLM API 키** | **사용하지 않음** — CLI 에이전트가 자기 모델을 들고 온다 (spec 004) |
| 온톨로지 | `공급망 지식지도` — 클래스 **20개**(바인딩 11 / 개념 9), 관계 **35개**, 그래프 인스턴스 **0건** |

에이전트 백엔드가 `cliagents` 라는 점이 중요하다. 스튜디오가 자기 도구를 MCP 로 내주고,
외부 CLI 에이전트가 그것을 호출한다. `OPENAI_API_KEY` 는 이 경로에 관여하지 않는다.

## 데이터셋 — 네 개 시스템에 흩어져 있다

수출 제조 중견기업(전자부품)의 공급망을 모사한다. 스키마와 생성기는 이 폴더에 있다
([`sql/`](sql/), [`gen_supplychain_data.py`](gen_supplychain_data.py) — 시드 고정, 재현 가능).

**중요 — 한 스키마에 다 넣지 않는다.** 데이터 패브릭이 하는 일은 한 스키마의 테이블을 읽는
것이 아니라 서로 다른 시스템에 흩어진 것을 잇는 것이다. 한곳에 모으면 연계 계층은 아무 일도
하지 않는 셈이 되고, 시연이 증명하는 것도 없어진다.

| 시스템 | DB | 테이블 | 담는 개념 | 키 표기 |
|---|---|---|---|---|
| **ERP** 구매·조달 | PostgreSQL `erp` | 5 | 공급사·품목·계약·발주·발주라인 | `supplier_id`, `item_id` |
| **관세·통관** | PostgreSQL `customs` | 1 | 통관신고 | `ref_shipment_no`, `ref_item_code` |
| **WMS** 창고·운송 | MySQL `wms` | 2 | 선적·일별재고 | `vendor_code`, `sku_code` |
| **CRM** 고객관리 | MySQL `crm_scm` | 3 | 고객·주문·클레임 | `cust_no`, `sku_code` |

**키 표기를 통일하지 않았다.** 같은 품목을 ERP 는 `item_id`, WMS·CRM 은 `sku_code`, 통관은
`ref_item_code` 로 부르고, 통관 시스템에는 외래키가 아예 없다. 그 단절을 잇는 것이 온톨로지의
일이다.

**그래프에 저장하는 인스턴스는 0건이다.** 11개 기록 클래스가 모두 데이터소스 바인딩(가상
클래스)이고, 조회 시점에 원본에서 인출한다.

### 심어 둔 사실 (골든 팩트)

채점 기준이 되도록 여섯 개 사실을 데이터에 심었다. 에이전트에게는 알려주지 않았다.

| 코드 | 사실 |
|---|---|
| G1 | `PO-2026-0117`(Shenzhen Goldline PCB) 선적 `SHP-2026-0111` 이 부산세관 **통관 보류, 9일 지연** |
| G2 | 그 선적 신고 3건에 **원산지증명(C/O) 미첨부**, 별건 `DCL-2026-00117` 은 **HS 코드 불일치**(신고 8536.69 / 마스터 8536.90) |
| G3 | `ITM-PCB-004`(6층 HDI PCB) **안전재고 이탈**, 운송중 6,000개가 곧 그 묶인 선적 |
| G4 | 계약 `CT-2025-011` **25일 후 만기·자동갱신 없음·납기 7일 초과 시 건당 2% 페널티** |
| G5 | 대체 공급사 `SUP-VN-002`(Saigon Circuit) 평점 4.3 · 리드 12일 · 납기준수 96.1% |
| G6 | 고객 `CUS-004` 주문 `SO-2026-0412` 납기 리스크, 클레임 `TK-2026-0031` |

여섯 사실은 **한 사건에서 파생된다.** 통관에 묶인 선적 하나가 조달·수출입·재고·구매·고객지원
다섯 업무에 동시에 나타난다. 도메인을 가로지르는 연결을 만드는 것이 지식 계층이고, 그것이
이 데모가 확인하려는 것이다.

## 결과 요약

| # | 도메인 | 에이전트가 한 일 | 도구 | 오류 | 시간 | 조회 시스템 | 채점 |
|---|---|---|---:|---:|---:|---|:--:|
| S1 | 조달 | 납기 리스크 감시 → 계약 페널티 판정 | 9 | 0 | 81s | ERP, WMS | PASS |
| S2 | 수출입 | 통관 보류 규명 → HS 코드 검증 → 정정신고 문안 | 6 | 0 | 63s | 관세, ERP | PASS |
| S3 | 재고관리 | 안전재고 이탈 → 커버일수 → 대체 공급사 | 10 | 0 | 126s | ERP, WMS | PASS |
| S4 | 계약 | 만기 임박 계약 → 미결 발주 노출액 → 갱신 우선순위 | 7 | 0 | 98s | ERP | PASS |
| S5 | 구매 | 대체 소싱 비교표 → 발주서(PO) 초안 생성 | 8 | 0 | 94s | ERP, WMS | PASS |
| S6 | 고객지원 | **A2A 핸드오프** — 클레임 역추적 → 고객 회신문 | 12 | 0 | 133s | **4종 전부** | PASS |
| | **합계** | | **52** | **0** | **596s** | | **6/6** |

채점 규칙이 둘이다.

1. 심어 둔 골든 팩트를 답변에서 찾는다 (시나리오당 4~6개 정규식, **전부** 맞아야 통과).
2. **도구 호출이 0회면 통과시키지 않는다.** 사실이 맞더라도 이번 실행이 조회한 것이 아니기
   때문이다 — 세션을 재사용했더니 에이전트가 기억으로 답하면서 도구 0회로 6/6 PASS 가 났다.

규칙은 [`run_scenarios.py`](run_scenarios.py) 의 `SCENARIOS[].expect` 와 `rec["queried"]` 에 있다.

상세 분석은 [`docs/scm-agent-demo.md`](../../docs/scm-agent-demo.md) 에 있다. 구성 순서와
첫 시도를 되돌린 이유는 [`ARCHITECTURE.md`](ARCHITECTURE.md) 에 있다.

## 보드 시각화

같은 지식지도에서 대시보드를 자동 구성한다. **8/8 위젯이 데이터를 그린다.**

```bash
python3 demo/scm-agent/run_board_scenarios.py --schema "공급망 지식지도"
```

| 위젯 | 클래스 | 규칙 |
|---|---|---|
| timeseries_line ×5 | `StockDaily` `Shipment` `PurchaseOrder` `SalesOrder` `CustomsDeclaration` | O1 |
| table | `ClaimTicket` | O10 |
| heatmap ×2 | `Supplier` `Item` | O8 |

위젯 종류는 사람이 고르지 않는다 — 객체 유형이 정한다 (spec 011).

## 재현 절차

```bash
# 0) 인프라
docker compose -f infra/docker-compose.yml up -d      # robo-postgres 5433 / robo-neo4j 7688 / robo-mindsdb 47334

# 1) 데이터셋 적재
python3 demo/scm-agent/gen_supplychain_data.py        # 결정적 생성 (seed 20260821)
docker exec -i robo-postgres psql -U postgres -d meetingroom < demo/scm-agent/sql/01_supplychain_schema.sql
docker exec -i robo-postgres psql -U postgres -d meetingroom < demo/scm-agent/sql/02_supplychain_data.sql

# 2) 연계 계층 — 네 시스템을 각각 등록
cd data-fabric/backend && .venv/bin/uvicorn app.main:app --port 8004 &
cd neo4j-text2sql && uv run uvicorn app.main:app --port 8020 &
#    scm_erp(postgres/erp) · scm_customs(postgres/customs) · scm_wms(mysql/wms) · scm_crm(mysql/crm_scm)
#    각각 POST /api/datasources 후 POST /api/datasources/{name}/extract-metadata-sync {"schemas":[...]}
#    주의: MySQL 적재는 charset 을 명시한다 — 안 하면 한글이 이중 인코딩된다
#      docker exec -i robo-mysql-sample sh -c 'mysql --default-character-set=utf8mb4 -uroot -p"$MYSQL_ROOT_PASSWORD"' < sql/04_wms_crm_mysql.sql

# 3) 지식 계층 — **문서에서** 온톨로지를 만든다 (카탈로그에서 만들지 않는다)
#    docs/공급망관리-개념체계.md 를 업로드하고 구축 모드로 실행한다.
#    build_context 에 4개 데이터소스와 골든 퀘스천 6개를 함께 넘긴다.
#    POST /api/upload  →  GET /api/stream?mode=build&build_context={...}
#    끝나면 POST /api/schema/{id}/publish

# 4) 에이전트 계층 — 스튜디오 (API 키 없이)
SANDBOX_BACKEND=local AGENT_BACKEND=cliagents EXTERNAL_AGENT_ID=claude-code \
  uv run uvicorn backend.src.host.main:app --host 127.0.0.1 --port 8010 &

# 5) 시나리오 실행 + 채점
python3 demo/scm-agent/run_scenarios.py               # runs/*.md, summary.json

# 6) 영상 (화면 녹화 + 한국어 내레이션)
cd ontology-studio/frontend && STUDIO_PORT=8010 npm run dev -- --port 5174 &
node demo/scm-agent/record_demo.js                    # video/raw/*.webm, video/shots/*.png
uv run --with pillow python demo/scm-agent/build_video.py   # video/*.mp4 + .srt
```

## 영상

| 파일 | 내용 |
|---|---|
| `video/SCM-Agent-Suite-데모.mp4` | 본편 **7분 46초** · 1600×900 H.264 · 한국어 내레이션(AAC) |
| `video/SCM-Agent-Suite-데모-자막포함.mp4` | 위와 동일 + 한국어 자막 트랙 내장 |
| `video/SCM-Agent-Suite-데모.srt` | 자막 |
| `video/shots/` | 장면별 스틸 |
| `video/raw/` | 장면별 원본 녹화 (webm) |

구성 — 타이틀 카드와 실제 화면이 번갈아 나온다. 화면은 재연이 아니라 그 자리에서 실행된
결과이며, 내레이션 길이에 맞추기 위해 배속한 구간에는 우하단에 배속 배수를 표시했다.

| # | 장면 | 원본 녹화 |
|---|---|---:|
| 1 | 이기종 4개 시스템 연계 — 데이터 패브릭 카탈로그 | 10s |
| 2 | 공급망 지식지도 — 기록 개념과 판단 개념 | 20s |
| 3 | [조달] 납기 리스크 감시 → 계약 페널티 판정 | 102s |
| 4 | [수출입] 통관 보류 규명 → HS 코드 검증 → 정정신고 | 105s |
| 5 | [재고관리] 안전재고 이탈 → 커버일수 → 대체 공급사 | 143s |
| 6 | [구매] 대체 소싱 비교표 → 발주서(PO) 초안 생성 | 139s |
| 7 | [고객지원] 클레임 원인 역추적 → 고객 회신문 생성 | 171s |
| 8 | 보드 — 같은 지식지도에서 자동 구성한 대시보드 | 25s |

**내레이션 엔진**은 OpenAI TTS(`gpt-4o-mini-tts`, voice `nova`)가 기본이다. 스크립트가
시작 전에 키를 한 번 찔러 보고, 거부되면(만료·권한) macOS `say` 로 떨어진다 — 첫 문장에서
401 로 죽는 대신 완성본을 낸다. 키를 갱신했다면 `build_video.py` 만 다시 돌리면 된다.

> 이 키는 **내레이션에만** 쓴다. 데모 실행 자체(에이전트·MCP·질의)는 LLM API 키를 쓰지
> 않는다. 그것이 시연의 요점이다 (spec 004).

## 파일

| 파일 | 역할 |
|---|---|
| `sql/01_supplychain_schema.sql` | 공급망 11개 테이블 DDL |
| `gen_supplychain_data.py` | 결정적 데이터 생성기 (골든 팩트 포함) |
| `seed_scm_demo.py` | 카탈로그 → 온톨로지 클래스·관계·behavior·발행 |
| `run_scenarios.py` | 스튜디오 SSE 로 6개 시나리오 실행 + 채점 |
| `record_demo.js` | Playwright 로 실제 UI 구동·녹화 |
| `narration.json` | 한국어 내레이션 대본 |
| `build_video.py` | TTS 합성 + 타이틀 카드 + 영상 조립 + 자막 |
| `runs/` | 실행 원본 기록 (도구 인자·결과 그대로) |
| `video/` | 영상·스틸·자막 |
