# Ontology Studio 사업 전략 — BMC와 코드 현실의 대조

**작성일** 2026-08-02 · **범위** ontology-studio (제품) + ontologic (플랫폼)

이 문서는 사업안(BMC)을 그대로 옮겨 적은 것이 아니다. **BMC의 각 전제가 지금 코드에서
성립하는지 확인한 결과**를 함께 담았다. 확인 경로를 각 항목에 적었으므로, 코드가 바뀌면
같은 경로로 다시 확인하고 이 표를 고친다.

핵심 결론 세 줄:

- **MCP 연동은 이미 있다.** 사업안이 "핵심 차별점"으로 든 것 중 유일하게 구현이 끝난 항목이다.
- **Electron 로컬 앱은 없다.** 단, 같은 조직의 `robo-architect/desktop` 에 **동일 문제를 푼
  완성 구현(Electron + Podman, DMG 산출까지)** 이 있다. 새로 설계할 대상이 아니라 이식 대상이다.
- **시각화·리포트는 전무하다.** 차트 라이브러리도, export 경로도 없다. 여기가 진짜 신규 개발이다.

---

## 1. BMC 전제 vs 코드 현실

| BMC 전제 | 코드 현실 | 확인 경로 |
|---|---|---|
| "MCP 서버 연동으로 AI Agent 환각 최소화" | **있음.** `ontology-studio-answer` / `-build` 두 MCP 서버, build·answer·answer_nods 3모드 | `ontology-studio/backend/src/modules/ontology_mcp/server.py`, `agent_bridge_mcp/router.py:15` |
| "다운로드 한 번으로 로컬 작동" | **없음.** 현재 유일한 배포 경로는 `docker compose up` | `ontology-studio/docker-compose.yml`, `README.md` |
| "Electron 데스크톱 앱" | **없음** (ontology-studio 기준). 단 `robo-architect/desktop` 에 Electron+Podman 구현·DMG 존재 | `/Users/uengine/robo-architect/desktop/`, `specs/055-podman-desktop-runtime/spec.md` |
| "8GB RAM 미만 실행" | **기각됨.** 실측 idle 5.36 GiB(Electron 제외). 공식 스펙을 **권장 16GB / 최소 8GB** 로 변경 (§4-1) | `memory-footprint-measurement.md` |
| "온톨로지 자동 생성" | **부분.** 테이블구조→온톨로지 경로는 결정적(LLM 미호출), 문서→온톨로지는 LLM 기반 | constitution "ontology-studio 절", `modules/ontology/schema_ontology.py` · `doc_ontology.py` |
| "Text-to-SQL" | **있음** (별도 서비스). `neo4j-text2sql`, 기본 8020 | `installation.md` §8 |
| "시각화 / 차트" | **없음.** 프론트 의존성은 `cytoscape`(그래프 시각화) · `marked` 뿐. ECharts·Chart.js 없음 | `ontology-studio/frontend/package.json` |
| "PDF/리포트 export" | **없음.** 파일 다운로드(업로드한 원본 회수)만 있다 | `frontend/src/features/files/FilePanel.vue`, `ChatPanel.vue:151` |
| "RBAC / SSO / Audit / Multi-tenancy" | **없음.** 인증 계층 자체가 없다 | `backend/src/host/app.py` |

### 이 대조가 말하는 것

사업안은 세 덩어리로 나뉘고, 각각 난이도가 완전히 다르다.

1. **이미 된 것** — MCP, 온톨로지 구축, Text-to-SQL. 마케팅에서 지금 당장 쓸 수 있다.
2. **이식하면 되는 것** — 데스크톱 패키징. `robo-architect` 가 같은 문제(로컬 PC에서 Neo4j를
   포함한 스택을 Docker Desktop 없이 띄우기)를 이미 풀었다. 설계가 아니라 이식·검증 작업이다.
3. **새로 만들어야 하는 것** — 시각화, 리포트, 엔터프라이즈 계층. 이 중 **시각화·리포트가
   사업안이 말한 "신의 한 수"** 이고, 실제로 코드가 0인 유일한 킬러 기능이다.

우선순위는 3 → 2 → (엔터프라이즈)로 잡는다. 이유: 데스크톱 패키징은 **담을 내용이 확정된
뒤에** 해야 재작업이 없고, 시각화가 없는 상태로 앱을 배포하면 "SQL 결과를 표로 보는 도구"라는
PoC 인상을 굳히게 된다.

---

## 2. 비즈니스 모델 캔버스

사업안 원안을 유지하되, 코드에서 확인된 사실로 구체화한 부분에 **[확인]** 표시를 달았다.

| 항목 | 내용 |
|---|---|
| **1. 가치 제안** | **개발자/분석가**: 인프라 설치 없이 로컬에서 도는 온톨로지 기반 Text-to-SQL 구축 툴<br>**기업**: 사내 DB 메타데이터를 외부 유출 없이 MCP로 AI Agent에 연결 → 환각 최소화<br>**[확인]** MCP 측은 외부 클라이언트의 실데이터 조회가 기본 차단(`MCP_ALLOW_DATASOURCE_EXPANSION=false`)이라 "메타데이터만 노출" 주장을 코드로 뒷받침할 수 있다 — `docker-compose.yml` |
| **2. 고객 세그먼트** | **커뮤니티**: 데이터 엔지니어, AI 개발자, 분석가, 연구원<br>**엔터프라이즈**: 보안 민감 산업(금융/제조/의료), AI Agent 도입 추진 IT/DX 부서<br>**[추가]** 시각화·리포트 도입 시 **현업 비즈니스 사용자**가 3번째 세그먼트로 열린다 |
| **3. 채널** | 획득: GitHub, Hacker News, Product Hunt, Reddit(r/LocalLLaMA), 기술 블로그<br>전환: 기술 웨비나, 엔터프라이즈 데모, 온톨로지 구축 교육<br>**[확인]** 소개 영상 자산 보유 — `README.md` (youtu.be/SYODN9UFA7I) |
| **4. 고객 관계** | 커뮤니티: GitHub Issue/Discussion, Discord/Slack<br>엔터프라이즈: SLA 기술지원, 맞춤 온톨로지 설계 컨설팅 |
| **5. 핵심 활동** | 데스크톱 패키징 · MCP 고도화 · **시각화/리포트 신규 개발** · 문서화 · 커뮤니티 운영 · 엔터프라이즈 기능 개발과 B2B 영업 |
| **6. 핵심 자원** | **[확인]** 에이전트 스킬 패키지(`skills/<name>/SKILL.md` 단일 원천) — 도메인별 온톨로지 노하우를 배포 가능한 표준 패키지로 파는 구조가 이미 코드 계약에 있다<br>결정적 테이블→온톨로지 변환 알고리즘 · 커뮤니티 · 도메인 템플릿 |
| **7. 핵심 파트너** | Anthropic MCP 생태계, Cursor/Windsurf, LangChain<br>MindsDB, PostgreSQL/MySQL 커뮤니티, Neo4j<br>**[확인]** MindsDB·Neo4j는 파트너가 아니라 **런타임 의존성**이다 — 라이선스와 리소스 부담이 그대로 우리 것이 된다(§4-1 참조) |
| **8. 비용 구조** | 코어 개발 인건비 · 마케팅/문서화/커뮤니티 · B2B 지원과 교육 인프라<br>**[추가]** 데스크톱 배포 시 **코드사이닝 비용**(Apple Developer, Windows EV 인증서)이 상시 비용으로 발생 |
| **9. 수익 구조** | Enterprise License(사내 MCP 배포, RBAC, 대규모 DB 연결) · Professional Services(온톨로지 구축 컨설팅) · Education(워크숍) |

---

## 3. 오픈코어 경계 — 무엇이 무료이고 무엇이 유료인가

사업안 맹점 3)이 지적한 "무료 앱만 팀 내 공유하고 라이선스 안 사는" 우회를 막으려면,
경계가 **기능 이름이 아니라 코드 모듈 단위**로 나뉘어야 한다. 아래가 그 경계다.

원칙: **1인 1머신에서 완결되는 것은 전부 무료. 여러 사람·여러 머신을 엮는 순간 유료.**
이 선은 우회하기 어렵다. 팀이 공유하려면 반드시 중앙 서버가 필요하고, 그게 유료 제품이기 때문이다.

| 영역 | OSS (무료) | Enterprise (유료) |
|---|---|---|
| 실행 형태 | 데스크톱 앱 (1인 1머신) | 사내 서버 배포 (다중 사용자) |
| 온톨로지 구축 | 전체 기능 | 동일 + 조직 공용 스키마 저장소 |
| MCP 서버 | 로컬 stdio/HTTP, 단일 사용자 | 중앙 MCP 엔드포인트, 사용자별 토큰 |
| 인증 | 없음 (로컬) | **SSO(SAML/OIDC), RBAC** |
| 감사 | 로컬 로그 | **중앙 Audit Log, 질의 이력 보존** |
| 데이터소스 | 개인이 접근 가능한 DB | **중앙 커넥션 관리, 크리덴셜 볼팅** |
| 시각화 | ECharts 로컬 렌더링, 세션 한정 + **로컬 대시보드 파일** | **대시보드 중앙 저장·공유·권한, 스케줄 리포트** |
| 리포트 | 수동 1회 export (MD/HTML/PDF) | **정기 생성·배포(메일/슬랙), 템플릿 관리** |
| BI 연동 | 없음 (1회 내보내기는 OSS) | **Superset/Metabase 동기화, 온톨로지→Dataset** |
| 동시성 | 단일 세션 | **다중 동시 질의, 큐/워커** |
| 지원 | 커뮤니티 | SLA, 전담 지원 |

> **2026-08-19 개정.** 시각화·BI 두 행은 [`ontology-board-product.md`](ontology-board-product.md) §7
> 이 다시 그었다. 경계가 기능 이름이 아니라 **저장 위치**로 갈린다 — 대시보드 *파일*은 무료이고
> 대시보드 *서버*가 유료다. 요구사항은 [spec 011](../../specs/011-ontology-board/spec.md).

**우회 위험 재평가**: 사업안은 이 위험을 "가능성"으로만 봤으나, 위 경계에서는 우회 자체가
성립하지 않는다. 팀이 무료 데스크톱 앱을 각자 설치해 쓰는 것은 **의도된 사용**이고(그게 바이럴이다),
그 상태로는 스키마 공유·권한·감사·정기 리포트가 전혀 안 된다. 조직이 커질수록 유료로 가는
압력이 자동으로 생긴다. 막아야 할 것은 우회가 아니라, **유료 기능이 "있으면 좋은 것"에 머무는 것**이다.

---

## 4. 맹점에 대한 실행 대응

### 4-1. "8GB 미만" — 지금은 근거 없는 주장이다

**데스크톱에 반드시 들어가야 하는 구성 (사업 결정, 2026-08-02).** 이 목록은 선택이 아니다.
제품이 "질문하면 사내 DB에서 답이 나온다"를 성립시키려면 데이터소스 기반 동작이 필수이고,
그러려면 아래가 전부 한 머신에서 떠야 한다.

| 구성요소 | 역할 | 형태 |
|---|---|---|
| Neo4j | 온톨로지·지식그래프 저장 | 컨테이너 (JVM) |
| MindsDB | 데이터소스 페더레이션 엔진 | 컨테이너 (Python) |
| PostgreSQL | MindsDB에 연결되는 업무 DB | 컨테이너 |
| MySQL | MindsDB에 연결되는 업무 DB | 컨테이너 |
| data-fabric | 데이터소스 등록·메타데이터 추출 | 프로세스/컨테이너 |
| neo4j-text2sql | 자연어 → SQL 실행 | 프로세스/컨테이너 |
| ontology-studio backend | API·에이전트 세션·샌드박스 | 프로세스/컨테이너 |
| ontology-studio MCP | 외부 AI Agent 연결 | 프로세스/컨테이너 |
| Electron (Chromium) | 셸 + SPA + PDF 렌더 | 호스트 |

즉 `robo-architect` 의 core/analyzer optional pack 구분을 **그대로 가져올 수 없다.**
저기서 optional 이었던 mindsdb·fabric 계열이 여기서는 core 다. 패키징 구조는 이식하되
**팩 경계는 다시 그어야 한다.**

### 실측 결과 (2026-08-02) — **8GB는 성립하지 않는다**

측정 전문: [memory-footprint-measurement.md](memory-footprint-measurement.md).
필수 8종(컨테이너 4 + 프로세스 4)을 전부 띄우고 실측한 결과:

| 구성 | idle | 비고 |
|---|---|---|
| 컨테이너 4종 (neo4j 1.80 / mindsdb 1.06 / mysql 0.49 / postgres 0.04 GiB) | **3.96 GiB** | 호스트 프로세스 4종 0.59 GiB 포함 |
| + Docker Desktop 호스트 오버헤드 | **5.36 GiB** | `docker stats` 에 안 잡히는 별도 1.40 GiB |
| + Electron | **미측정** | 하한 참고값 0.43 GiB (창 없는 상태 기준, 과소평가) |

8GB 머신은 OS가 2~3GB를 먼저 쓴다. 측정된 그대로면 **7.36~8.36 GiB — Electron 없이 이미
경계에 걸린다.** Docker를 Podman으로 바꿔 1.4 GiB를 없애도 5.96~6.96 GiB이고, 여기에
Electron과 실부하가 얹힌다. **여유가 없다.**

### 실측이 뒤집은 가정 두 가지

- **Neo4j 힙은 이미 설정돼 있다.** 내가 "설정이 없어 호스트 RAM 비례로 잡힌다"고 쓴 것은
  틀렸다. `infra/docker-compose.robo-stack.yml:35-37` 에 힙 1G / 페이지캐시 512m 로 고정돼
  있고, 이는 미설정 시 권장값(힙 5100m + 캐시 6900m) 대비 **이미 4.5배 감량된 상태**다.
  여기서 더 짜는 것은 남은 레버가 아니다.
- **MindsDB 핸들러 제거는 헛다리다.** 핸들러 218개의 소스 총량이 14MB — 전체 1.06GiB의 1%
  수준이다. 실제 메모리는 **멀티프로세싱 워커 4개**(각 190~380MB)에서 나온다. 사업안이 든
  "불필요 모듈 최소화 커스텀 빌드"는 효과가 없고, 줄인다면 **워커 수**를 줄여야 한다(미확인).

### 그래서 남은 레버는 무엇인가

1. **Docker Desktop → Podman** (−1.4 GiB). 확실하고 가장 큰 단일 레버.
   `robo-architect` 가 이미 이 선택을 했고 이유도 같다.
2. **MindsDB 워커 수 축소** (효과 미확인, 조사 필요). 현재 1.06 GiB 중 대부분이 여기다.
3. **온디맨드 기동** — "필수 8종 상시 상주" 원칙을 깨고, 쓰지 않는 동안 내리는 방식.
4. **MindsDB 자체를 걷어내고** 경량 페더레이션을 직접 구현. 가장 큰 절감이지만 제품 범위를
   바꾸는 결정이라 사업 판단이 필요하다.

사업안이 든 **"백엔드를 Rust/Go로 재작성"은 실측이 기각한다.** Python 호스트 프로세스
4종 합계가 0.59 GiB로 전체의 15%뿐이다. 전부 0으로 만들어도 8GB 문제는 풀리지 않는다.

### 별건으로 발견된 문제

`mysql-sample` 이 `platform: linux/amd64` 로 고정돼 Apple Silicon 에서 **QEMU 에뮬레이션으로
돌고 있다**(다른 3개는 네이티브 arm64). 메모리 영향은 미분리지만, CPU 오버헤드는
`installation.md` 이슈 #12에서 이미 심각한 전례가 있다. arm64 네이티브 이미지 교체를
**안정성 항목**으로 별도 트래킹한다.

### 아직 측정 못 한 것 (전부 합계를 키우는 방향)

- **Electron 실측** — GUI 세션이 없는 환경이라 불가. 창을 띄운 상태로 재측정 필요.
- **무거운 부하 피크** — 이번엔 경량 COUNT 질의 1건(캐시 데워진 상태)뿐이라 idle 대비
  +43 MiB밖에 안 늘었다. 콜드스타트·동시질의·대용량 조인은 미측정. "부하 시에도 idle과
  비슷하다"고 일반화하면 안 된다.
- **Podman VM 실사용량** — robo-architect 의 Podman 머신은 6144MB **상한** 설정만 확인했고
  실사용량은 미측정. Podman이 Docker보다 가볍다는 것은 아직 이 측정으로 입증되지 않았다.

### 결정 — 권장 16GB / 최소 8GB (2026-08-02)

사업안의 "8GB RAM 미만 실행"은 **폐기한다.** 실측이 기각했고, 지킬 수 있다고 계속 말하면
첫 설치에서 신뢰를 잃는다. 공식 스펙은 다음과 같다.

| | 사양 | 근거 |
|---|---|---|
| **권장** | **16GB** | 실측 idle 5.36 GiB + Electron + 부하 여유. 개발자 머신의 사실상 표준 |
| **최소** | **8GB** | idle 은 뜨지만 여유가 거의 없다. 무거운 질의·동시 사용에서 스와핑 가능 |

최소 사양을 8GB로 남기는 이유: 실측 idle(Podman 기준 3.96 GiB) + OS 2~3GB 로 **뜨기는 뜬다.**
"안 된다"가 아니라 "권장은 16GB"가 정직한 표현이다. 다만 최소 사양 표기에는
**"MindsDB·Neo4j 를 포함한 전체 스택이 로컬에서 함께 구동됩니다"** 를 반드시 병기해,
사용자가 무엇 때문에 무거운지 알 수 있게 한다.

**카피 전략 수정**: "8GB 미만"을 무기로 쓰지 않는다. 대신 실제로 검증된 강점으로 바꾼다 —
**"클라우드 전송 없음. 설치 한 번으로 내 PC에서 끝난다."** 경량성이 아니라 **로컬 완결성과
데이터 비유출**이 진짜 차별점이고, 이건 측정이 필요 없는 구조적 사실이다.

여전히 감량은 추진한다(순서: Podman 전환 → MindsDB 워커 수 → 온디맨드 기동). 다만
**마케팅 약속이 아니라 엔지니어링 개선 항목**으로 다룬다. 재측정 후 수치가 좋아지면 그때
스펙을 내린다.

### 4-2. 온톨로지 생성 자동화 — 이미 절반은 풀려 있다

사업안은 "FK/PK만으로는 고품질 온톨로지가 안 나온다"고 봤고, 이는 맞다. 다만 현재 구현은
경로가 둘로 나뉘어 있다:

- **테이블 구조 → 온톨로지**: 결정적. LLM을 부르지 않는다 (플랫폼 계약 — constitution).
- **문서 → 온톨로지**: LLM 기반 추출.

사업안이 제안한 "80% 자동 + 20% UI 편집"의 UI 쪽은 이미 있다 —
`GoldenQuestionReviewPanel.vue`, `BindingCandidatePanel.vue`, `CausalEdgeReviewPanel.vue` 가
사용자 검토·수정 지점이다. 남은 일은 새 엔진이 아니라 **이 검토 UX의 정밀화**다.

### 4-3. 시장 교육 비용 — 카피 전략

"Ontology"를 전면에 두지 않는다. 제품 표면 문구는 결과 중심으로:

> "AI가 우리 회사 DB를 정확히 이해하게 만든다 — 질문하면 차트와 리포트까지"

'온톨로지'는 기술 문서와 개발자 채널에서만 쓴다. 시각화·리포트 기능이 이 전략의 전제다.
결과물이 표뿐이면 어떤 카피를 써도 "SQL 도구"로 읽힌다.

---

## 5. 시각화 · 리포트 아키텍처 결정

사업안의 2단계 전략(로컬 경량 / 서버 Superset)을 채택한다. 결정 사항:

**로컬 — Apache ECharts 채택.** 근거:
- 프론트가 이미 Vue 3이고 `cytoscape` 를 쓰고 있어 JS 시각화 라이브러리 추가에 마찰이 없다.
- 백엔드 렌더링이 없으므로 메모리 증가는 번들 크기 수준(수십 MB 이하).
- Superset은 로컬에서 제외한다. Flask+Redis+Celery+Postgres 의존성이 "설치 없이 로컬 실행"이라는
  가치 제안과 정면 충돌한다. 사업안 판단에 동의한다.

**차트 추천은 결정적 로직으로 만든다.** LLM에 차트 타입을 묻지 않는다. 이유:
- 플랫폼 계약이 이미 같은 원칙을 테이블→온톨로지 경로에 적용하고 있다(constitution).
- 데이터 형태(컬럼 타입·카디널리티·시계열 여부)만으로 결정 가능한 문제에 LLM을 부르면
  비결정성·지연·비용만 늘어난다.
- LLM은 차트 **선택**이 아니라 인사이트 **문장**에 쓴다.

**리포트 파이프라인**: 질의 결과(표) + ECharts 렌더 + LLM 요약 → Markdown → HTML → PDF.
PDF 생성은 이미 Electron/Chromium이 있는 환경에서는 별도 엔진이 필요 없다.

```text
[자연어 질의]
     ↓
[Text-to-SQL / behavior_invoke]  ← 기존, 구현됨
     ↓ 결과 JSON
[차트 추천 (결정적)]  ← 신규 (작업 5)
     ↓ 차트 스펙
[ECharts 렌더]        ← 신규 (작업 4)
     ↓
[리포트 조립 + LLM 인사이트] → MD / HTML / PDF   ← 신규 (작업 6)
```

엔터프라이즈에서는 여기에 Superset/Metabase 커넥터가 붙어, 온톨로지를 Superset Dataset으로
동기화하고 에이전트가 사내 공용 대시보드를 생성한다. **OSS에는 넣지 않는다** (§3 경계표).

---

## 6. 실행 로드맵

진행하면서 이 체크박스를 갱신한다. 각 작업의 산출물은 `docs/business/` 에 쌓는다
(향후 `biz-kit` 스킬의 자산이 된다).

- [x] **1. 사업 전략 문서화** → 이 문서
- [x] **2. '8GB 미만' 실측 검증** → `memory-footprint-measurement.md` — 결론: **기각**, 권장 16GB / 최소 8GB 로 확정
- [x] **3. speckit spec — 006 시각화 & 리포트** → [`specs/006-visualization-and-report/spec.md`](../../specs/006-visualization-and-report/spec.md) · 결정 요약 [`visualization-report-decisions.md`](visualization-report-decisions.md)
  - ⚠️ 선행 결함 발견: 잘림(truncation) 신호가 기본 설정에서 미탐 — 차트 이전에 고쳐야 한다 (spec FR-001~004)
  - ⚠️ 미결정 U-1: answer 모드 에이전트가 리포트 파일을 쓰는 것이 플랫폼 계약에 걸린다. 구현 전 판단 필요
- [x] **4. Electron 패키징** (robo-architect/desktop 이식, 팩 경계 재설계) — **앱 기동 확인 완료**, 증거 [`evidence/06-nav-rail/`](evidence/06-nav-rail/README.md)
  - 실행 중 결함 8개 발견·수정: VM 단일 실행 제약 · podman connection 미고정 · 크래시 루프 무한 대기 · 엉뚱한 로그 표시 · text2sql 실패가 부팅 전체를 죽임 · SELinux 볼륨 라벨 · Neo4j Browser 프레임 차단 · iframe 폭 붕괴
- [x] **4-1. 프론트엔드 통합 P0** — robo-data-frontend 데이터소스 화면을 같은 origin iframe 으로. 설계 [`frontend-integration-decisions.md`](frontend-integration-decisions.md)
  - 레일 4메뉴(온톨로지 구축 · 질문 응답 · 데이터소스 · Neo4j Browser), 데이터소스·Browser 는 2단부터 전체
  - 예제 postgres 등록 + 메타데이터 추출(schemas 2 / tables 13)까지 앱 안에서 확인
  - `robo-data-frontend` 서브모듈 핀을 125커밋 올림 (`d3d1f1c` → `origin/main`)
  - 설계 결정 완료 → [`desktop-packaging-decisions.md`](desktop-packaging-decisions.md)
  - 구현 완료 → `ontology-studio/desktop/` (셸·compose·패키징 스크립트·절차서)
  - **미완**: 영상 증거. 이 세션의 셸은 macOS GUI 앱을 띄우지 못한다. 사람이
    `ontology-studio/desktop/README.md` 의 **"직접 확인하는 법"** 절대로 실행해 녹화해야
    체크박스를 닫을 수 있다. 검증한 것/못한 것 목록도 같은 README 에 있다.
- [ ] **5. 선행 결함 수정** — 잘림 신호 미탐 버그 (spec FR-001~004)
- [ ] **6. ECharts 도입 + 차트 렌더링 컴포넌트** · 증거 필요
- [ ] **7. 자동 차트 추천 엔진 (결정적)** · 증거 필요
- [ ] **8. 리포트 생성 (MD/HTML/PDF export)** · 증거 필요
- [ ] **9. Enterprise 분리 설계** (RBAC/SSO/Audit/Superset)
  - 제품 기획 완료 → [`ontology-board-product.md`](ontology-board-product.md) ·
    스펙 → [spec 011](../../specs/011-ontology-board/spec.md)
  - 실측으로 드러난 선행 제약: MCP 표면의 행 예산이 **에이전트 기준**이다 —
    Cypher 20행(잘린 양을 알 수 없음) · SQL 30행. 기획서 §3 참조

> **순서 변경 근거**: "다운로드 한 번으로 로컬 실행"이 가치 제안의 1번이고, 그것이 성립하는지를
> 먼저 봐야 나머지 기능을 어디에 담을지 정해진다. 대가는 시각화·리포트가 들어갈 때 패키징을
> 한 번 더 손봐야 한다는 것 — 감수한다.

> **환경 제약 (2026-08-02 확인)**: 이 개발 세션의 셸은 **macOS GUI 앱을 띄우지 못한다**
> (`open` 이 exit 0 을 반환하나 프로세스가 남지 않음, TextEdit 으로 대조 확인). 따라서
> **Electron 앱의 실행 검증은 사람이 직접 해야 한다.** 반면 **Playwright headed Chromium 은
> 정상 동작**하므로 웹 UI 기반 증거(작업 6·7·8)는 자동 생성이 가능하다.

### 완료 판정 규칙 — 구현 작업은 영상 증거 없이 완료로 치지 않는다

문서·설계 작업(1·2·3·8)은 문서가 산출물이다. **구현 작업(4·5·6·7)은 다르다.**
"테스트가 통과했다"는 완료가 아니다 — 플랫폼 계약도 같은 말을 한다:
*"단위 테스트만 통과한 것을 동작한다고 보고하지 않는다"* (ontology-studio `CLAUDE.md`).

각 구현 작업의 완료 조건:

| 항목 | 요구 |
|---|---|
| 실행 증거 | **실제 UI 를 띄운 화면 녹화(mp4/webm)** 또는 단계별 스크린샷 |
| 생성 경로 | `ontology-studio/demo/` 의 기존 Playwright 파이프라인 재사용 (`playwright.config.js` 는 `HEADLESS=false` 로 헤디드 구동, `video`/`screenshot` 옵션 보유) |
| 보관 위치 | `docs/business/evidence/<작업번호>-<이름>/` — 영상 + 캡처 + 무엇을 보여주는지 적은 `README.md` |
| 실패 시 | 되지 않는 부분은 숨기지 말고 **그대로 녹화하고** 무엇이 안 되는지 적는다 |

이 규칙을 `biz-kit` 스킬에 그대로 넣는다. 사업 자료(투자·영업·데모)에서 재사용할 수 있는
형태로 남기는 것이 목적이므로, 증거는 개발자용 로그가 아니라 **화면 그 자체**여야 한다.

---

## 7. 아직 결정되지 않은 것

이 문서로 정할 수 없고, 사업 판단이 필요한 항목:

- **라이선스**: 현재 ontology-studio 저장소에 LICENSE 파일이 없다. 오픈코어를 하려면
  OSS 부분의 라이선스(Apache 2.0 / AGPL / BSL)를 먼저 정해야 한다. AGPL은 SaaS 우회를 막지만
  기업 도입 마찰이 크고, BSL은 오픈소스로 인정받지 못해 커뮤니티 반발이 있다.
- **가격 모델**: 사용자당 / 서버당 / 데이터소스당 중 무엇인지.
- **Enterprise 코드 위치**: 별도 비공개 저장소인지, 같은 저장소의 `ee/` 디렉터리인지.
- **데스크톱 코드사이닝 주체**: 조직 명의 Apple Developer 계정 유무.
