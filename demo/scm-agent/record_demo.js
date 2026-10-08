/**
 * SCM-Agent 데모 화면 녹화 — 온톨로지 스튜디오 실제 UI 를 Playwright 로 구동하고 녹화한다.
 *
 * 재연이 아니다. 화면에 보이는 답은 스튜디오가 `AGENT_BACKEND=cliagents` 로 그 자리에서
 * 실행한 결과이며, 같은 질문을 run_scenarios.py 가 API 로 돌려 채점 기록을 남긴다.
 *
 *   node demo/scm-agent/record_demo.js [--only S1-procurement,S3-inventory]
 *
 * 산출물: demo/scm-agent/video/raw/*.webm (장면별), shots/*.png (스틸)
 */
const { chromium } = require(require.resolve('@playwright/test', { paths: [require('path').join(__dirname, '..', '..', 'ontology-studio')] }));
const fs = require('fs');
const path = require('path');

const UI = process.env.STUDIO_UI || 'http://localhost:5174';
const OUT = path.join(__dirname, 'video');
const RAW = path.join(OUT, 'raw');
const SHOTS = path.join(OUT, 'shots');

const SCENES = [
  {
    id: 'S0-catalog',
    kind: 'tour',
    title: '이기종 4개 시스템 연계 — 데이터 패브릭 카탈로그',
  },
  {
    id: 'SM-map',
    kind: 'map',
    title: '공급망 지식지도 — 기록 개념과 판단 개념',
  },
  {
    id: 'S1-procurement',
    kind: 'ask',
    title: '[조달] 납기 리스크 감시 → 계약 페널티 판정',
    question:
      '발주 PO-2026-0117 의 납기 리스크를 점검해줘. 현재 선적 상태와 지연 일수, 지연 사유를 확인하고, ' +
      '이 발주의 공급사와 계약 조건(페널티·만기)을 함께 보고해줘.',
  },
  {
    id: 'S2-customs',
    kind: 'ask',
    title: '[수출입] 통관 보류 규명 → HS 코드 검증 → 정정신고',
    question:
      '현재 통관 보류(HOLD) 또는 반려(REJECTED) 상태인 수출입 신고 건을 모두 찾아 사유를 정리하고, ' +
      '각 건에서 신고 HS 코드가 품목 마스터의 HS 코드와 일치하는지 검증해줘. 불일치 건은 정정신고 문안을 제안해줘.',
  },
  {
    id: 'S3-inventory',
    kind: 'ask',
    title: '[재고관리] 안전재고 이탈 → 커버일수 → 대체 공급사',
    question:
      '최신 스냅샷 기준으로 안전재고를 이탈한 원자재 품목을 찾고, 각 품목의 재고 커버일수와 운송중 수량을 알려줘. ' +
      '가장 위험한 품목의 주 공급사와 대체 공급사도 함께 알려줘.',
  },
  {
    id: 'S5-purchasing',
    kind: 'ask',
    title: '[구매] 대체 소싱 비교표 → 발주서(PO) 초안 생성',
    question:
      '품목 ITM-PCB-004 를 긴급 대체 소싱하려고 해. 이 품목을 공급할 수 있는 주 공급사와 대체 공급사를 평점·리드타임·' +
      '납기준수율로 비교표를 만들고, 대체 공급사 앞 발주서(PO) 초안을 작성해줘. 수량은 안전재고 회복에 필요한 만큼, MOQ 를 지켜서.',
  },
  {
    id: 'S6-customer-support',
    kind: 'ask',
    title: '[고객지원] 클레임 원인 역추적 → 고객 회신문 생성',
    question:
      '고객 클레임 TK-2026-0031 (납기 문의)에 답해야 해. 해당 고객과 주문(SO)의 내용, 납기 리스크 원인을 ' +
      '연결된 발주/선적까지 역추적해서 확인하고, 고객에게 보낼 회신 초안을 작성해줘. ' +
      '회신에는 원인, 현재 조치, 예상 납기 영향, 대안을 담아줘.',
  },
  {
    id: 'SB-board',
    kind: 'board',
    title: '보드 — 같은 지식지도에서 자동 구성한 대시보드',
  },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function typeHumanly(locator, text) {
  // 한 글자씩 치면 한국어 IME 없이도 자연스러운 타이핑처럼 보인다.
  await locator.click();
  await locator.type(text, { delay: 12 });
}

async function selectSchema(page, name) {
  // 그래프 패널은 기본이 '전체 스키마' 라 다른 모델까지 함께 그린다. 이 데모의 대상만
  // 남겨야 화면이 사실을 말한다.
  const sel = page.locator('.schema-select-wide, .class-filter-select').first();
  if (await sel.count()) {
    await sel.selectOption({ label: name }).catch(() => {});
    await sleep(2500);
  }
}

async function gotoView(page, label) {
  const btn = page.locator('.nav-rail-btn', { hasText: label }).first();
  await btn.click();
  await sleep(1200);
}

async function recordScene(browser, scene) {
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    recordVideo: { dir: RAW, size: { width: 1600, height: 900 } },
    locale: 'ko-KR',
  });
  const page = await ctx.newPage();
  const started = Date.now();
  const marks = [];
  const mark = (label) => marks.push({ label, t: Math.round((Date.now() - started) / 100) / 10 });

  await page.goto(UI, { waitUntil: 'domcontentloaded' });
  await sleep(3000);
  mark('open');

  if (scene.kind === 'tour') {
    await gotoView(page, '데이터소스');
    mark('datasources');
    await sleep(4000);
    await page.screenshot({ path: path.join(SHOTS, `${scene.id}-datasources.png`) });
    // 네 개 시스템을 차례로 펼친다 — 이 데모의 요점이 "흩어져 있다"는 것이므로
    // 하나만 보여 주면 화면이 그 사실을 말해 주지 못한다.
    for (const name of ['scm_erp', 'scm_wms', 'scm_customs', 'scm_crm']) {
      const ds = page.locator(`text=${name}`).first();
      if (!(await ds.count())) continue;
      await ds.click().catch(() => {});
      await sleep(2600);
      await page.screenshot({ path: path.join(SHOTS, `${scene.id}-${name}.png`) });
      mark(name);
    }
    await sleep(1500);
  } else if (scene.kind === 'map') {
    // 지식지도 자체를 보여 준다 — 개념 노드와 바인딩 노드가 함께 있는 그림.
    await gotoView(page, '질문 응답');
    await sleep(2000);
    await selectSchema(page, '공급망 지식지도');
    const schemaTab = page.locator('.view-mode-btn', { hasText: '스키마' }).first();
    if (await schemaTab.count()) { await schemaTab.click().catch(() => {}); }
    await sleep(3500);
    mark('schema-view');
    await page.screenshot({ path: path.join(SHOTS, `${scene.id}-schema.png`) });
    // 레이아웃을 바꿔 관계가 보이게 한다
    const layout = page.locator('.layout-select').first();
    if (await layout.count()) {
      await layout.selectOption({ label: 'Force (CoSE)' }).catch(() => {});
      await sleep(4500);
      await page.screenshot({ path: path.join(SHOTS, `${scene.id}-layout.png`) });
    }
    mark('layout');
    await sleep(3000);
  } else if (scene.kind === 'board') {
    await gotoView(page, '대시보드');
    mark('dashboard-list');
    await sleep(3000);
    await page.screenshot({ path: path.join(SHOTS, `${scene.id}-list.png`) });
    // 목록만 찍으면 위젯이 하나도 안 보인다. 카드를 열어야 대시보드가 나온다.
    // **제목으로 찾지 않는다** — 대시보드를 다시 구성하면 제목이 달라지고, 선택자가
    // 조용히 빗나가 목록 화면만 녹화된다. 실제로 그렇게 났다.
    const card = page.locator('.dashboard-card, [class*="dash"][class*="card"]').first();
    if (await card.count()) {
      await card.click().catch(() => {});
    } else {
      // 클래스 이름을 모르면 위젯 수 표기가 있는 카드를 고른다.
      await page.locator('text=/위젯\\s*\\d+개/').first().click().catch(() => {});
    }
    // 위젯은 각각 질의를 돌려서 그린다 — 여덟 개가 다 그려질 때까지 기다린다.
    const deadline = Date.now() + 4 * 60 * 1000;
    while (Date.now() < deadline) {
      const drawn = await page.locator('canvas, .widget-chart, .echarts-for-react').count();
      if (drawn >= 4) break;
      await sleep(2000);
    }
    await sleep(6000);
    mark('widgets');
    await page.screenshot({ path: path.join(SHOTS, `${scene.id}-board.png`) });
    for (let i = 0; i < 5; i += 1) {
      await page.mouse.wheel(0, 420);
      await sleep(1300);
    }
    await page.screenshot({ path: path.join(SHOTS, `${scene.id}-board-scrolled.png`) });
    mark('scrolled');
    await sleep(2500);
  } else {
    await gotoView(page, '질문 응답');
    mark('answer-mode');
    await sleep(1500);
    await selectSchema(page, '공급망 지식지도');
    const box = page.locator('.chat-input-bar textarea').first();
    await typeHumanly(box, scene.question);
    await page.screenshot({ path: path.join(SHOTS, `${scene.id}-question.png`) });
    mark('typed');
    await sleep(800);
    await page.locator('.btn-send').first().click();
    mark('sent');

    // 스트리밍이 끝날 때까지 기다린다. 중단 버튼이 나타났다 사라지면 끝이고,
    // 버튼을 놓치더라도 본문 길이가 더 늘지 않으면 끝난 것으로 본다.
    const deadline = Date.now() + 12 * 60 * 1000;
    let sawStop = false;
    let lastLen = 0;
    let stable = 0;
    while (Date.now() < deadline) {
      const streaming = await page.locator('.btn-stop').count();
      if (streaming) sawStop = true;
      const len = (await page.locator('body').innerText().catch(() => '')).length;
      if (len === lastLen) stable += 1; else stable = 0;
      lastLen = len;
      if (sawStop && !streaming) break;
      if (!sawStop && stable > 20 && len > 600) break;   // 30초 이상 변화 없음
      await sleep(1500);
    }
    mark('answered');
    await sleep(2500);
    // 답변 전체를 보여 주기 위해 아래로 훑는다
    for (let i = 0; i < 6; i += 1) {
      await page.mouse.wheel(0, 420);
      await sleep(900);
    }
    await page.screenshot({ path: path.join(SHOTS, `${scene.id}-answer.png`), fullPage: false });
    mark('scrolled');
    await sleep(1500);
  }

  const video = page.video();
  await ctx.close();
  const src = await video.path();
  const dest = path.join(RAW, `${scene.id}.webm`);
  fs.renameSync(src, dest);
  const meta = { id: scene.id, title: scene.title, file: path.basename(dest), marks,
                 duration_s: Math.round((Date.now() - started) / 100) / 10 };
  fs.writeFileSync(path.join(RAW, `${scene.id}.json`), JSON.stringify(meta, null, 2));
  console.log(`[rec] ${scene.id} ${meta.duration_s}s → ${dest}`);
  return meta;
}

(async () => {
  const onlyArg = process.argv.find((a) => a.startsWith('--only='));
  const only = onlyArg ? onlyArg.split('=')[1].split(',') : null;
  fs.mkdirSync(RAW, { recursive: true });
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch({ headless: process.env.HEADLESS !== 'false' });
  const metas = [];
  for (const scene of SCENES) {
    if (only && !only.includes(scene.id)) continue;
    try {
      metas.push(await recordScene(browser, scene));
    } catch (err) {
      console.error(`[rec] ${scene.id} 실패: ${err.message}`);
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'scenes.json'), JSON.stringify(metas, null, 2));
  console.log(`\n장면 ${metas.length}개 녹화 완료 → ${RAW}`);
})();
