# 프론트엔드 통합 — 사업 결정과 근거

**작성일** 2026-08-02 · **대상** `ontology-studio/desktop` + `robo-data-frontend`
**관련 문서** [`ontology-studio-strategy.md`](ontology-studio-strategy.md) §3·§5·§6 ·
[`desktop-packaging-decisions.md`](desktop-packaging-decisions.md) ·
[`specs/006-visualization-and-report/spec.md`](../../specs/006-visualization-and-report/spec.md)

기술 설계는 [`ontology-studio/desktop/docs/frontend-integration.md`](../../ontology-studio/desktop/docs/frontend-integration.md)
에 있다. 이 문서는 **왜 그렇게 정했는가**만 다룬다.

이 문서의 모든 사실 주장에는 확인 경로(`파일:줄`)가 붙어 있다. 확인하지 못한 것은
§7 에 **미확인**으로 모아 두었고, 본문에서 사실처럼 쓰지 않았다.

---

## 0. 결론 요약

| # | 결정 | 한 줄 근거 |
|---|---|---|
| 1 | federation 불일치는 **버그가 아니라 낡은 서브모듈 핀**이다. 포크도 설정 주입도 없다 | `ontologic` 이 `robo-data-frontend` 를 `main` 보다 **111 커밋 뒤진** 조상 커밋에 고정해 두었다 |
| 2 | 통합 방식은 **같은 origin iframe**. Module Federation 은 채택하지 않는다 | 두 프론트의 빌드 툴체인이 vite 5 ↔ vite 8 로 3 메이저 벌어져 있다. iframe 은 이 결합이 0 이다 |
| 3 | 1차 통합 화면은 **데이터소스 탭 하나**. 스키마 탭은 2차 | 데이터소스는 이미 데스크톱 core 팩에 있는 백엔드(data-fabric)만 쓴다. 스키마는 없는 서비스(robo-data-catalog 5503)를 요구한다 |
| 4 | 데스크톱에 **api-gateway 를 넣지 않는다**는 결정을 유지한다. 셸이 경로 접두사만 갈아끼운다 | 게이트웨이 라우트를 실측한 결과 **전부 순수 접두사 rewrite** 였다. Spring 을 띄울 이유가 없고, 띄우면 constitution VI 의 30초 타임아웃 함정을 들여온다 |
| 5 | **spec 006 의 ECharts 결정은 유지한다.** 단 버전을 6.0.0 으로 고정하고 문구 하나를 정정한다 | robo-data-frontend 의 ECharts 는 *다른 SPA 의 다른 화면* 것이다. spec 006 이 요구하는 "채팅 답변에 차트가 뜬다"는 여전히 코드 0 이다 |
| 6 | 통합되는 화면은 전부 **OSS** 다 | §3 경계 기준은 "1인 1머신에서 완결되는가"이고, 데이터소스 등록·메타데이터 증강·스키마 확인은 전부 여기 해당한다 |

---

## 1. 사업 요구와 현재 상태

요구는 셋이다.

1. Ontology Studio 데스크톱 앱 안에서 **데이터소스 등록 · 메타데이터 증강 · 데이터 스키마 확인**
2. 한 번 고치면 **ontologic · robo-architect · ontology-studio** 세 곳에 반영
3. robo-architect 의 "Legacy/Analysis 메뉴" 방식이 참고 모델

### 확인한 현재 상태

| 항목 | 상태 | 확인 경로 |
|---|---|---|
| ontology-studio 자체 프론트에 데이터소스 등록 화면 | **없다.** 기능은 `chat` · `files` · `ontology` · `session` 4개뿐 | `ontology-studio/frontend/src/features/` |
| ontology-studio 프론트 의존성 | `cytoscape` · `marked` · `vue` **3개** | `ontology-studio/frontend/package.json:11-15` |
| ontology-studio **백엔드**의 데이터소스 API | **읽기 전용은 이미 있다** — 목록·스키마·테이블·컬럼·샘플. **등록·삭제·메타데이터 추출은 없다** | `backend/src/modules/ontology/datasource_api.py:43-105` |
| robo-data-frontend 의 데이터소스 화면 | **있다.** 등록·연결테스트·메타데이터 추출까지 | `src/features/datasources/` (`main` 브랜치) |
| robo-architect 의 통합 방식 | Module Federation 리모트를 **런타임 `import()`** 로 호스트 DOM 에 마운트. iframe 아님 | `robo-architect-main-build/frontend/src/features/analysis/ui/AnalysisPanel.vue:58,74` |

즉 요구 1 의 절반(읽기)은 스튜디오 백엔드에 이미 있고 화면만 없다. 나머지 절반(쓰기 —
등록·추출)은 백엔드도 화면도 없으며, **둘 다 robo-data-frontend + data-fabric 에 있다.**

---

## 2. federation 불일치의 정체 — 조사 결과

조사 과제였던 "`ontologic/robo-data-frontend/vite.config.ts` 에는 `exposes` 가 없는데
robo-architect 가 번들한 산출물에는 `remoteEntry.js` 가 있다"는 불일치는 **완전히 해명됐다.**

### 사실

```
ontologic 이 고정한 커밋   d3d1f1c   ← exposes 없음
robo-data-frontend main    1c0a0f4   ← exposes 있음
git rev-list --left-right --count d3d1f1c...main  →  0    111
```

- `d3d1f1c` 는 `main` 의 **직계 조상**이다. 갈라진 브랜치가 아니다. 뒤진 것뿐이다.
- `exposes` 는 커밋 **`7ec5772 feat(unified): fork 통합 1단계 — 단일 소스 + isEmbedded 스위치`**
  에서 도입됐다. 제목이 말하듯 **"세 곳 동시 반영"은 이미 상류에서 착수된 작업**이다.
- `main` 의 설정: `filename: 'remoteEntry.js'`, `exposes: { './remote-app': './src/bootstrap.ts' }`,
  `shared: { vue: {singleton}, pinia: {singleton} }`, `base: process.env.ANALYZER_BASE || '/'`
  ↳ `git show main:vite.config.ts` 12-29행
- **robo-architect 의 빌드 스크립트는 vite config 를 바꿔치기하지 않는다.** `npm run build:docker`
  (= 그냥 `vite build`) 를 부르고 산출물을 복사할 뿐이다.
  ↳ `robo-architect/desktop/scripts/build-runtime.sh:96-108`

### 결론

**불일치가 아니라 관리 부채다.** ontologic 저장소가 서브모듈 핀을 111 커밋째 갱신하지 않았다.
`git submodule update --remote robo-data-frontend` 한 번이면 `exposes` 를 포함한 최신 상태가 된다.

### 이것이 요구 2("세 곳 동시 반영")에 주는 답

**서브모듈 공유는 성립한다. 다만 지금은 성립하지 않고 있다.** 이유는 구조가 아니라 운영이다.

| 저장소 | robo-data-frontend 보유 형태 | 상태 |
|---|---|---|
| `ontologic` | 서브모듈 | ✅ 등록됨. 단 **111 커밋 뒤진 핀** |
| `robo-architect` (`/Users/uengine/robo-architect`) | **없음.** `.gitmodules` 에 `open-pencil`·`cliagents` 만 | ❌ 소스 부재. 31MB 빌드 산출물만 untracked 로 존재 |
| `robo-architect-main-build` (형제 워크트리) | 서브모듈 `robo-analyzer/robo-data-frontend`, branch=main | ✅ 유일하게 정상 |
| `ontology-studio` | 없음 | — (이 문서가 정하는 것) |

**커밋 핀 때문에 사실상 따로 노는 것이 맞다.** 다만 그것은 서브모듈 모델의 한계가 아니라
갱신을 안 한 결과다. 아래 §5 의 운영 규칙으로 해소한다.

### 부수적으로 발견한 결함 (robo-architect 측 — 우리가 고치지 않는다)

이식하면서 **반복하면 안 되는 것**이므로 기록한다.

- `build-runtime.sh:96-108` 이 `ANALYZER_BASE` 를 **export 하지 않는다.** 그래서 산출물이
  `base='/'` 로 구워졌고, `/analyzer/` 에 마운트되면 Monaco 워커(`/assets/editor.worker-*.js`)와
  NVL 레이아웃 워커(`/assets/CoseBilkentLayout.worker-*.js`)가 **호스트 루트로 요청을 보내
  SPA 의 index.html 을 받는다.** vite.config.ts 의 주석은 이 값을 주입하기로 되어 있다고 적고 있다.
- `/Users/uengine/robo-architect/frontend` 에는 federation 플러그인도 `features/analysis/` 도
  **없다.** 그 체크아웃에서 빌드하면 Analysis 탭이 없는 호스트가 나온다. 동작하는 조합은
  `robo-architect-main-build` 에만 있다.

→ 이 두 가지는 **"MF 는 이미 검증된 길"이라는 인상이 과장임**을 보여 준다. §3 의 판단 근거 중 하나다.

---

## 3. 통합 방식 — 4개 대안 비교

이 제품의 제약 넷을 기준으로 평가한다.

- **C1 단일 origin** — 셸이 한 origin(`127.0.0.1:17900`)에 SPA 를 서빙하고 `/api` 를 프록시한다.
  CSP 는 설정돼 있지 않다. ↳ `ontology-studio/desktop/src/main/webserver.js:144-176`, `index.js:75-79`
- **C2 메모리 예산** — 실측 idle 5.36 GiB, "여유가 없다". ↳ 전략 §4-1
- **C3 세 곳 동시 반영** — 요구 2
- **C4 오픈코어 경계** — §3 경계표. OSS 산출물이 Enterprise 코드를 끌고 오면 안 된다

### 비교표

| | ① Module Federation | ② 같은 origin iframe | ③ 소스 레벨 통합 | ④ 별도 창/탭 |
|---|---|---|---|---|
| **툴체인 결합** | **강함.** 두 빌드가 같은 federation 플러그인·같은 vue/pinia 싱글턴을 공유해야 한다 | **없음.** 각자 자기 vite 로 빌드 | 최대. 한 빌드로 합침 | 없음 |
| **vite 버전 (실측)** | studio **8.0.3** ↔ analyzer **^5.1.4** — 3 메이저 차 | 무관 | 충돌 해소 필수 | 무관 |
| **vue/pinia 싱글턴** | studio 는 **pinia·vue-router 를 안 쓴다.** 싱글턴 공유 대상이 사실상 vue 하나 | 불필요 | 강제 통일 | 불필요 |
| **C2 메모리** | 리모트가 **호스트 힙에 영구 상주**. `unmount()` 해도 모듈 캐시는 남는다 | 문서 컨텍스트가 분리돼 **iframe 제거 시 회수**. 대신 Vue 런타임 2벌 | 1벌 | 렌더러 프로세스 추가 (가장 큼) |
| **C1 단일 origin** | 필요 | **이 제약이 iframe 의 최대 약점(cross-origin)을 없앤다** | 필요 없음 | 새 창은 origin 은 같으나 창이 둘 |
| **C3 세 곳 반영** | 서브모듈 공유 O | 서브모듈 공유 O | **불가.** 합치는 순간 포크된다 | 서브모듈 공유 O |
| **상류 수정량** | 0 (계약이 이미 있다) | **1커밋** — `?embedded=1` 쿼리 지원 | 대규모 | 0 |
| **스타일/전역 충돌** | 있음. analyzer 는 `cssCodeSplit:false` 로 **CSS 를 한 덩어리**로 낸다 | **0.** 문서가 분리된다 | 최대 | 0 |
| **"앱 안에서" 요구 충족** | 완전 | 완전 | 완전 | **절반** |
| **검증된 전례** | robo-architect 에 있으나 §2 대로 **깨진 상태**(worker 경로, 소스 부재) | 없음 | 없음 | 흔함 |

### 결정 2 — **② 같은 origin iframe 을 채택한다**

근거를 순서대로 든다.

**1) 툴체인 결합이 이 결정의 전부다.** Module Federation 은 호스트와 리모트가 같은
`@originjs/vite-plugin-federation` 위에서 동작해야 한다. analyzer 는 `vite ^5.1.4` +
`@vitejs/plugin-vue ^5.0.4` 로 빌드된다(`git show main:package.json`). studio 프론트는
**vite 8.0.3** + `@vitejs/plugin-vue ^6` 이다(`node_modules/vite/package.json`). 이 플러그인이
vite 8 에서 동작하는지는 **미확인**이며(§7 U-1), 동작하지 않으면 **스튜디오 프론트 전체를
vite 5 로 내려야 한다.** 프론트 하나 끼우려고 호스트의 빌드 시스템을 3 메이저 되돌리는 것은
비례하지 않는다.

**2) 메모리 예산이 iframe 쪽이다.** 전략 §4-1 이 "여유가 없다"고 못박은 제품이다.
MF 리모트는 한 번 `import()` 하면 호스트 렌더러 힙에 남고, `unmount()` 는 Vue 앱만 파괴할 뿐
모듈 그래프는 회수하지 않는다. iframe 은 DOM 에서 떼면 문서 전체가 회수된다. **쓰지 않는
동안 내리는 방식**은 §4-1 이 든 감량 레버 3번과 같은 원리다.

**3) 상류 수정이 1커밋이고, 그 1커밋이 세 곳 모두에 이득이다.** iframe 경로는 `embedded`
플래그를 mount 옵션으로 받을 수 없으므로 **URL 쿼리(`?embedded=1&features=datasources`)에서도
읽도록** `src/main.ts` 를 고쳐야 한다. `isEmbedded` 는 이미 `bootstrap.ts:37` 의
`app.provide('isEmbedded', ...)` 하나로 구현돼 있고, 소비처가 3곳뿐이다. MF 경로는 그대로 두고
쿼리 경로를 **추가**하는 변경이므로 robo-architect 를 깨뜨리지 않는다. 요구 2 에 정확히 부합한다.

**4) MF 의 "이미 검증됐다"는 근거가 약하다.** §2 가 밝혔듯 robo-architect 의 analyzer 팩은
worker 경로가 깨진 채로 번들돼 있고, README 스스로 *"analyzer 팩은 end-to-end 로 검증되지
않았다"* 고 적고 있다(`robo-architect/desktop/README.md:208-209`). 참고 모델로는 유효하나
**검증된 자산은 아니다.**

**5) 격리가 실제 값이 있다.** analyzer 는 `cssCodeSplit: false` 로 빌드된다
(`vite.config.ts:99`) — 즉 bpmn-js·dmn-js·vue-flow·NVL 의 CSS 까지 **한 스타일시트**로 나온다.
이것을 스튜디오 문서에 주입하면 스튜디오의 62KB `styles.css` 와 충돌 표면이 생긴다.
iframe 은 이 문제가 존재하지 않는다.

### ①·③·④ 를 버리는 이유 (요약)

- **①** — 위 1)·2). 다만 **버리지 않고 v2 로 남긴다.** U-1 이 "vite 8 에서 동작한다"로 해소되고,
  화면 간 상태 공유(예: 스튜디오 채팅에서 데이터소스를 선택)가 실제 요구로 올라오면 재검토한다.
- **③** — C3 를 정면으로 위반한다. 합치는 순간 세 저장소가 각자의 사본을 갖게 된다.
  vite 5→8, vue 3.4→3.5, pinia/vue-router 도입까지 얹힌다. 사업 요구 2 와 양립 불가.
- **④** — "데스크톱 앱 안에서"라는 요구 1 을 절반만 만족한다. 새 `BrowserWindow` 는
  렌더러 프로세스를 하나 더 만들어 C2 에 가장 불리하다. 단 **디버깅 탈출구**로는 남긴다
  (메뉴 → 데이터소스 관리자를 새 창으로).

---

## 4. 어떤 화면을 먼저 넣는가

### 갈라야 하는 이유 — 데스크톱 스택에 없는 백엔드가 대부분이다

robo-data-frontend 는 **모든 HTTP 를 `/api/gateway/**` 상대 경로로** 보낸다. 소스에 직접
서비스 포트를 부르는 곳은 없다(`src/shared/services/http.ts:14-19`). 그런데 각 접두사는
서로 다른 서비스로 간다. 데스크톱 core 팩은 neo4j · mindsdb · data-fabric · neo4j-text2sql
넷뿐이다(패키징 결정 §3).

| 화면 | 게이트웨이 접두사 | 실제 서비스 | 데스크톱 core 팩에 있나 |
|---|---|---|---|
| **datasources** | `/data-fabric` | data-fabric **8004** | ✅ **있다** |
| **schema** (스키마 확인·설명 편집) | `/robo` | robo-data-catalog **5503** | ❌ 없다 |
| **text2sql** | `/text2sql` | neo4j-text2sql | ✅ 있다 |
| graph (코드 그래프) | `/robo` | robo-data-catalog 5503 · robo-analyzer 5502 | ❌ 없다 |
| upload (코드 업로드) | `/antlr` `/robo` | ANTLR 8081 · robo-analyzer 5502 | ❌ 없다 |
| ontology · object-explorer · domain | `/ontology` | domain-layer **8002** | ❌ 없다 |
| olap / whatif / security / lineage / glossary | 각각 | 8007 / 8005 / 8006 / … | ❌ 없다 |

↳ 라우팅 근거: `api-gateway/src/main/resources/application.yml:46-198` (전부 실측)

### 결정 3 — 우선순위

| 순위 | 화면 | 사업 요구 충족 | 추가로 필요한 것 |
|---|---|---|---|
| **P0** | **datasources 탭 하나** | **데이터소스 등록** ✅ · **메타데이터 증강(1차: extract-metadata)** ✅ | 없음. core 팩 그대로 |
| **P1** | **schema 탭** | **데이터 스키마 확인** ✅ · **메타데이터 증강(2차: 테이블/컬럼 설명 편집·LLM 보강)** ✅ | **robo-data-catalog(5503) 를 core 팩에 추가.** Dockerfile 이 없어 새로 써야 한다 |
| **넣지 않음** | graph · upload · olap · whatif · security · lineage · glossary · object-explorer · domain | — | 5502·8081·8002·8005·8006·8007 을 전부 끌고 온다. 메모리 예산(C2)과 제품 정의 양쪽에 반한다 |

**P0 만으로 사업 요구 3개 중 2개가 닫힌다.** 그리고 P0 은 백엔드를 하나도 안 늘린다 —
이것이 P0/P1 을 가르는 이유다.

**P1 의 비용은 낮다.** robo-data-catalog 의 런타임 의존성은 **Neo4j 하나**다
(`robo-data-catalog/config/settings.py:20-24`, `requirements.txt`). 메타데이터 LLM 보강용
langchain/openai 가 있지만 선택이다. 컨테이너 idle 은 미측정(§7 U-3).

### 왜 "스튜디오 프론트에 직접 만든다"가 아닌가

스튜디오 백엔드에는 이미 읽기 전용 데이터소스 API 가 있다
(`datasource_api.py:43-105`). 여기에 등록/추출 엔드포인트를 더하고 스튜디오 프론트에
화면을 만드는 선택지가 존재한다. **채택하지 않는다** — 그 순간 같은 화면이 두 벌이 되고,
사업 요구 2(세 곳 동시 반영)가 첫날부터 깨진다. 이미 있는 화면을 **재사용하는 것이 요구
자체**다.

---

## 5. 세 곳 동시 반영을 실제로 성립시키는 운영 규칙

구조(서브모듈 공유)는 성립한다. 깨지는 지점은 **핀 갱신**이다. §2 가 그 증거다.

| 규칙 | 내용 |
|---|---|
| **원천은 `robo-data-frontend` 의 `main` 하나** | 세 저장소 모두 같은 URL 의 서브모듈로 붙인다. 소스를 복사하지 않는다 |
| **핀은 올린다** | ontologic 은 `d3d1f1c` → `main` 으로 갱신한다. 111 커밋을 미루면 어느 시점에 되돌릴 수 없어진다 |
| **화면을 고칠 때는 상류에 커밋한다** | 통합 때문에 필요한 수정(`?embedded=` 쿼리, `MainLayout` 무조건 호출 등)은 전부 `robo-data-frontend` 에 넣는다. 셸 쪽에 우회를 만들지 않는다 |
| **robo-architect 를 깨지 않는다** | 상류 변경은 전부 **추가**여야 한다. `mount()` 계약(`bootstrap.ts:29-32`)과 MF `exposes` 는 그대로 둔다 |
| **호환 표면은 두 개뿐** | ① `mount(el, {embedded, projectRoot, neo4j})` (MF 호스트용) ② URL 쿼리 (iframe 호스트용). 셋째를 만들지 않는다 |

**robo-architect 가 지금 이 서브모듈을 안 갖고 있다는 점**은 이 규칙의 예외가 아니라 대상이다.
동작하는 조합이 형제 워크트리에만 있는 상태(§2 표)는 그 자체가 정리 항목이며, ontologic 이
결정할 수 있는 범위 밖이므로 **미결 항목**으로 남긴다(§7 U-5).

---

## 6. spec 006 의 ECharts 결정 — 유지한다

### 충돌처럼 보이는 것

- 전략 §5 와 spec 006 은 *"ECharts 를 신규 도입한다"* 고 정했다. spec 006 은 근거로
  *"`echarts`/`chart.js` 는 `package-lock.json` 전이 의존성까지 뒤져도 **0건**"* 을 들었다
  (spec.md:40-41).
- 그런데 `robo-data-frontend` 에는 **`echarts` 가 이미 있다.** 락파일 실측 **정확히 6.0.0**
  (`git show main:package.json`, `package-lock.json` `echarts-6.0.0.tgz`).

### 판단 — **결정은 흔들리지 않는다.** 근거 셋

**1) spec 006 이 요구하는 것은 그 ECharts 가 아니다.** robo-data-frontend 의 차트는
`src/shared/charts/{Bar,Line,Pie,Map}Chart.vue` 이고, 소비처는 `object-explorer` 와 `domain`
화면이다 — **둘 다 §4 에서 "넣지 않음"으로 분류한 화면**이고, 둘 다 데스크톱에 없는
domain-layer(8002)를 요구한다. spec 006 이 요구하는 것은 **스튜디오 채팅 답변에 차트가
자동으로 뜨는 것**(US1)이고, 그것은 `ontology-studio/frontend/src/features/chat/` 의 일이다.
iframe 통합은 채팅 화면에 차트를 넣어 주지 않는다.

**2) spec 006 의 사실 진술만 범위가 틀렸다.** "0건"은 **ontology-studio 프론트 한정**으로
읽어야 맞다. 플랫폼 전체로는 0건이 아니다. → **문구를 정정한다**(아래).

**3) 오히려 spec 006 의 미결 하나가 실측으로 좁혀졌다.** U-3 *"ECharts 번들을 어떻게 넣을
것인가 — 전체 / tree-shaking. 실측이 필요하다"*. robo-architect 가 번들한 산출물에서
ECharts 를 포함한 청크는 **`ChartRenderer-CIOEC9ZK.js` 2.9MB** 이고, 이는 **minify 를 끈
상태**(`vite.config.ts:98` `minify: false`)의 크기다. 그리고 그 청크는 **lazy** 다 — 진입
번들에 없다. 즉 *"전체 번들이면 프론트 자산이 수 MB 늘어난다"* 는 우려는 **디스크 기준으로는
사실이고, 런타임 메모리 기준으로는 차트를 처음 그릴 때까지 0** 이다.

### spec 006 에 반영할 개정 (별건 작업)

| # | 개정 내용 |
|---|---|
| 1 | §현재 코드 현실 40-41행 — "echarts 0건"의 범위를 **ontology-studio 프론트**로 한정 명시. 플랫폼에는 robo-data-frontend 에 6.0.0 이 있다는 사실을 병기 |
| 2 | Assumptions 의 ECharts 항목에 **버전 `6.0.0` 고정**을 추가. 같은 조직이 두 메이저를 유지할 이유가 없고, 나중에 두 프론트가 만나면 그때 비용이 된다 |
| 3 | U-3 을 **부분 해소**로 내린다. 실측 하한(lazy 청크, unminified 2.9MB)을 기록하고, 남은 미결은 "minify 를 켠 크기"로 좁힌다 |

**폐기하지 않는다.** 폐기하면 채팅 답변의 차트가 사라지고, 그것이 전략 §4-3 카피
*"질문하면 차트와 리포트까지"* 의 전부다.

---

## 7. 오픈코어 경계 — 통합 화면은 전부 OSS

§3 의 기준은 하나다: *"1인 1머신에서 완결되는 것은 전부 무료. 여러 사람·여러 머신을 엮는
순간 유료."*

| 화면 | 판정 | 근거 |
|---|---|---|
| **데이터소스 등록** | **OSS** | §3 경계표: 데이터소스 OSS = *"개인이 접근 가능한 DB"*. Enterprise 는 *"중앙 커넥션 관리, 크리덴셜 볼팅"* — 등록 화면 자체가 아니라 **중앙화**가 유료 선이다 |
| **메타데이터 증강** | **OSS** | 온톨로지 구축 = *"전체 기능"* 이 OSS. Enterprise 는 *"조직 공용 스키마 저장소"* |
| **데이터 스키마 확인** | **OSS** | 같음. 읽기 전용 조회에 유료로 가둘 선이 없다 |
| (넣지 않는) security 화면 | **Enterprise** | RBAC/감사는 §3 표에서 명시적으로 Enterprise. §4 에서 이미 제외했고, 이 판정이 그 제외를 이중으로 뒷받침한다 |

### 경계에서 주의할 것 — constitution V

`:DataSource` 노드는 **`host`/`port`/`user`/`password` 를 평문으로 보유**하고,
data-fabric 의 `GET /api/datasources/{name}/connection` 은 **비밀번호를 그대로 반환한다**
(constitution 원칙 V).

데스크톱에서 이것이 허용되는 이유는 **1인 1머신 + 127.0.0.1 바인드**뿐이다
(`webserver.js:180` `server.listen(ports.web, '127.0.0.1')`). 따라서:

- 데이터소스 화면을 통합한다고 해서 **바인드 주소를 넓히지 않는다.**
- Enterprise(서버 배포)로 같은 화면을 옮기는 순간 **크리덴셜 볼팅이 선행 조건**이 된다.
  §3 표가 이미 그렇게 적어 두었다. 이 문서는 그것을 재확인할 뿐이다.

---

## 8. 아직 결정되지 않은 것 / 미확인

**미확인을 사실처럼 쓰지 않기 위해 여기 모았다.**

| # | 항목 | 왜 미결·미확인인가 |
|---|---|---|
| **U-1** | `@originjs/vite-plugin-federation@^1.4.1` 이 **vite 8 에서 동작하는가** | 확인하지 않았다. 이것이 "예"로 밝혀지면 §3 의 1번 근거가 약해지고 MF(v2)가 다시 열린다. 검증 방법은 기술 문서에 적었다 |
| **U-2** | iframe 안에서 analyzer 의 **`base` 경로 문제가 재현되는가** | robo-architect 산출물은 `base='/'` 로 구워져 worker 경로가 깨진다(§2). `/analyzer/` 하위 서빙 시 `ANALYZER_BASE` 주입으로 해소될 것으로 보이나 **실제 빌드로 확인하지 않았다** |
| **U-3** | **robo-data-catalog(5503) 컨테이너의 idle 메모리** | 측정하지 않았다. P1 을 core 팩에 넣을지의 판단 근거가 되므로 넣기 전에 측정한다. Dockerfile 도 아직 없다 |
| **U-4** | `MainLayout.vue:27-33` 이 **마운트마다 무조건** `POST /robo/graph/` 를 부르는 것을 어떻게 끌 것인가 | P0(datasources 단독)에서도 이 호출이 나가고, catalog 5503 이 없으면 에러가 화면에 뜬다. 상류 수정이 필요하다는 것은 확정. 방법은 미정 |
| **U-5** | `robo-architect` 본 체크아웃에 서브모듈이 없고 동작 조합이 **형제 워크트리에만** 있는 상태를 누가 정리하는가 | 다른 프로젝트의 저장소 운영 문제다. ontologic 이 결정할 범위 밖 |
| **U-6** | 데이터소스 화면이 **스튜디오 온톨로지 빌드 흐름과 어떻게 이어지는가** | 지금은 화면을 띄우는 것까지만 정했다. "등록한 데이터소스로 바로 온톨로지를 만든다"는 연결은 별도 설계다 |
| **U-7** | 두 프론트가 **장기적으로 한 벌이 되어야 하는가** | 이 문서는 v1 만 정한다. `7ec5772` 의 "fork 통합 1단계"라는 제목은 상류가 이미 그 방향을 보고 있음을 시사하나, 그 로드맵을 확인하지 못했다 |

---

## 9. 완료 판정

전략 §6 의 규칙이 그대로 적용된다 — **구현 작업은 영상 증거 없이 완료로 치지 않는다.**

이 통합에서 영상이 반드시 보여야 하는 장면:

1. 데스크톱 앱 메뉴에서 **데이터소스 관리자**를 여는 순간
2. 데이터소스를 **실제로 등록**하고 연결 테스트가 통과하는 순간
3. **메타데이터 추출**을 실행하고 테이블/컬럼이 채워지는 순간
4. (P1) 스키마 탭에서 **테이블 설명을 편집**하고 저장되는 순간
5. 되지 않는 화면이 있다면 **그대로 녹화하고** 무엇이 안 되는지 적는다 (전략 §6 규칙)

보관 위치는 `docs/business/evidence/<작업번호>-frontend-integration/`.
