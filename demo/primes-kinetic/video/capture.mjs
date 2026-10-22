// PriMES 반복 수주 — 커맨드만으로 (Process GPT 없이 Ontology Studio 단독). 장면별 정지화면 캡처, 실행은 실제로 한 번.
//   사전: ../run_studio.sh start (Studio 8011/5183), PriMES :8080 기동
import fs from 'fs';
import { chromium, STUDIO, sleep, log, pageText, nav, waitAgent, writeJson } from '../../kinetic-mes/video2/lib.mjs';

const OUT = 'slides';
const MES = 'http://localhost:8080/primes';
// FROM=17 node capture.mjs — 앞 장면은 두고 17번부터 다시 (slides.json 에 합친다)
const FROM = Number(process.env.FROM || 1);
if (FROM === 1) fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });
const slides = [];
const checks = [];
const add = (scene, file) => { let s = slides.find(x => x.scene === scene); if (!s) slides.push(s = { scene, files: [] }); s.files.push(file); };
const fname = (scene, name) => `s${String(scene).padStart(2, '0')}-${name}.png`;
const facts = {};   // 대본에 쓸 실제 값
async function shot(page, scene, name, must = [], minLen = 150) {
  const t = await pageText(page);
  for (const m of must) if (!t.includes(m)) { await page.screenshot({ path: `FAIL-${name}.png` }); throw new Error(`장면 ${scene} '${name}': '${m}' 없음`); }
  if (t.length < minLen) throw new Error(`장면 ${scene} '${name}': 빈 화면 (${t.length}자)`);
  await page.screenshot({ path: `${OUT}/${fname(scene, name)}` });
  add(scene, fname(scene, name)); checks.push(`✓ ${fname(scene, name)} (${t.length}자 ${must.join('·')})`); log('shot', fname(scene, name));
}

// 요소 확대 — 어두운 틀 가운데 크게. widen 이면 찍는 동안 화면에 고정해 넓힌다 (좁은 채팅 칸에서 열이 잘리는 문제)
async function zoom(page, loc, scene, name, title, must = [], widen = true) {
  const txt = await loc.innerText();
  for (const m of must) if (!txt.includes(m)) { await page.screenshot({ path: `FAIL-${name}.png` }); throw new Error(`확대 ${name}: '${m}' 없음`); }
  if (widen) await loc.evaluate(el => { el.dataset.prevStyle = el.getAttribute('style') || '';
    Object.assign(el.style, { position: 'fixed', left: '20px', top: '10px', width: '1000px', maxWidth: 'none', zIndex: 99999, overflow: 'visible',
      background: '#141a24', padding: '14px 16px', borderRadius: '10px', boxSizing: 'border-box' });  // 투명하면 뒤 화면이 비친다
    el.querySelectorAll('.ds-table-scroll').forEach(w => { w.style.overflow = 'visible'; }); });
  else await loc.scrollIntoViewIfNeeded();
  await sleep(300);
  const buf = await loc.screenshot();
  if (widen) await loc.evaluate(el => { el.setAttribute('style', el.dataset.prevStyle); el.querySelectorAll('.ds-table-scroll').forEach(w => { w.style.overflow = ''; }); });
  await frame(scene, name, title, `<img src="data:image/png;base64,${buf.toString('base64')}">`);
  checks.push(`✓ ${fname(scene, name)} (확대 ${txt.length}자 ${must.join('·')})`);
}

let ctx;
async function frame(scene, name, title, inner, css = '') {
  const f = await ctx.newPage();
  await f.setContent(`<!doctype html><meta charset="utf-8"><style>
    html,body{margin:0;width:1280px;height:720px;background:#0b1018;color:#e8eef5;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif}
    .t{color:#9fb3c8;font-size:20px;padding:22px 36px 0}.w{display:flex;align-items:center;justify-content:center;height:640px}
    img{max-width:1200px;max-height:610px;border-radius:10px;box-shadow:0 8px 40px #000a}${css}</style>
    <div class="t">${title}</div><div class="w">${inner}</div>`);
  await f.screenshot({ path: `${OUT}/${fname(scene, name)}` }); await f.close();
  add(scene, fname(scene, name)); log('frame', fname(scene, name));
}

async function slide(scene, name, html) {
  const f = await ctx.newPage();
  await f.setContent(`<!doctype html><meta charset="utf-8"><style>
    html,body{margin:0;width:1280px;height:720px;background:#0b1018;color:#e8eef5;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif}
    .k{font-size:18px;color:#7aa7d6;letter-spacing:.08em}.box{padding:70px 90px}</style><div class="box">${html}</div>`);
  await f.screenshot({ path: `${OUT}/${fname(scene, name)}` }); await f.close();
  add(scene, fname(scene, name)); checks.push(`✓ ${fname(scene, name)} (슬라이드)`); log('slide', fname(scene, name));
}

const browser = await chromium.launch();
ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
const p = await ctx.newPage();
const mes = await ctx.newPage();
const box = () => p.locator('textarea').last();
async function say(text) { await box().fill(text); await box().press('Enter'); await waitAgent(p, 900000); log('said', text.slice(0, 30)); }
const lastCard = () => p.locator('[data-testid=kinetic-plan-card]').last();
const lastAI = async () => (await p.locator('body').innerText()).split('\n➤')[0];
async function mesLogin() {
  await mes.goto(`${MES}/login`, { waitUntil: 'load' }); await sleep(1200);
  const i = mes.locator('.login input, form input');
  await i.nth(0).fill('standard'); await i.nth(1).fill('guest'); await i.nth(2).fill('1234!@#$');
  await mes.locator('button:has-text("로그인")').first().click(); await sleep(2500);
}
async function mesScreen(path) { await mes.goto(`${MES}${path}`, { waitUntil: 'load' }); await sleep(3500); }

try {
  if (FROM === 1) {
  // ── 1 질문 ────────────────────────────────────────────────────────────
  await slide(1, 'hook', `<div class="k">PriMES · ONTOLOGY STUDIO · 키네틱 액션</div>
    <h1 style="font-size:50px;line-height:1.4;margin:28px 0 36px">프로세스를 그리지 않고,<br><span style="color:#ffb454">대화 한 줄</span>로 반복 수주를 처리한다면?</h1>
    <div style="font-size:23px;color:#cfdbe8">수주 → 자재 발주 → 금형 확인 → 작업지시 → 필요하면 되돌리기</div>`);
  // ── 2 사건 ────────────────────────────────────────────────────────────
  await slide(2, 'case', `<div class="k">반복 주문</div>
    <div style="font-size:34px;margin:26px 0 30px;line-height:1.5">대성오토 · 휠 허브 플랜지 <b style="color:#ffb454">1,200개</b> · 납기 10월 26일</div>
    <div style="font-size:22px;color:#cfdbe8;line-height:1.9">· 수주 등록 — 영업 화면<br>· 원자재 소요 확인과 발주 — 구매 화면 두 개<br>· 단조 작업지시와 금형 지정 — 생산·금형 화면<br>
    · 그리고 예외 하나: 단조 금형 FM540-1 의 남은 수명이 이번 물량에 모자란다</div>`);

  // ── 3 질의 ────────────────────────────────────────────────────────────
  await p.goto(STUDIO, { waitUntil: 'networkidle' });
  await nav(p, '질의·액션');
  await p.locator('[title$="워크스페이스 펼치기"]').first().click().catch(() => {}); await sleep(300);
  await p.locator('.sidebar-new').click().catch(() => {}); await sleep(300);
  await p.locator('[title="워크스페이스 접기"]').click().catch(() => {}); await sleep(600);
  await p.getByText('그래프', { exact: true }).click().catch(() => {});
  await say('휠 허브 플랜지 단조 금형별 남은 타수는?');
  await shot(p, 3, 'question', ['FM540-1', 'FM540-2']);

  // ── 4 수주 ────────────────────────────────────────────────────────────
  await say('대성오토가 휠 허브 플랜지 1,200개를 10월 26일 납기로 주문했어. 수주 등록해 줘.');
  await lastCard().waitFor({ timeout: 60000 }); await sleep(1000);
  await zoom(p, lastCard(), 4, 'order-plan', '수주 등록 계획 — 대상: 고객 대성오토(C001)', ['C001', 'placeRepeatOrder']);
  await say('응, 실행해.');
  await sleep(1500);
  let t = await lastAI();
  facts.orderNo = (t.match(/SO-\d{8}-\d{4}/g) || []).pop();
  if (!facts.orderNo) throw new Error('수주 번호를 못 찾음');
  await shot(p, 4, 'order-done', [facts.orderNo]);
  // ── 5 PriMES 수주 화면 ────────────────────────────────────────────────
  await mesLogin();
  await mesScreen('/m/sales/sales-orders');
  await shot(mes, 5, 'mes-order', [facts.orderNo]);

  // ── 6 발주 ────────────────────────────────────────────────────────────
  await say('이 수주 때문에 부족한 원자재를 승인 업체에 발주해 줘.');
  await lastCard().waitFor({ timeout: 60000 }); await sleep(1000);
  t = await lastAI();
  facts.poQty = (t.match(/([\d,]+)\s*KG/g) || []).slice(0, 3).join(' / ');
  await shot(p, 6, 'po-plan', ['RM-STL-45C', '포스강재']);
  await say('응, 실행해.');
  await sleep(1500);
  t = await lastAI();
  facts.poNo = (t.match(/PO-\d{8}-\d{3}/g) || []).pop();
  await mesScreen('/m/purchase/po-manage');
  await shot(mes, 6, 'mes-po', facts.poNo ? [facts.poNo] : ['포스강재']);

  // ── 7 규칙: 최저가 업체 ──────────────────────────────────────────────
  await say('잠깐, 단가가 더 싼 대한특수강으로 500KG 더 발주하면 안 돼?');
  await sleep(1000);
  const denyCard = lastCard();
  if (await denyCard.count() && (await denyCard.innerText()).includes('대한특수강') || (await denyCard.innerText()).includes('승인 공급처')) {
    await zoom(p, denyCard, 7, 'policy-deny', '정책 — 승인 공급처로만 발주', ['승인 공급처']);
  } else {
    await shot(p, 7, 'policy-answer', ['승인']);
  }

  // ── 8 작업지시: 금형 확인 ────────────────────────────────────────────
  await say('이 수주의 단조 작업지시를 내 줘. 금형 수명이 모자라면 대안을 보여 주고 내가 고른 대로 진행해.');
  await sleep(1000);
  await shot(p, 8, 'mold-check', ['FM540-1', 'FM540-2']);
  t = await lastAI();
  facts.moldText = t.slice(-1200);
  // ── 9 선택 → 승인 대기 ───────────────────────────────────────────────
  await say('대체 금형 FM540-2로 진행해 줘.');
  await lastCard().waitFor({ timeout: 60000 }); await sleep(1000);
  await zoom(p, lastCard(), 9, 'wo-plan', '단조 작업지시 계획 — 대체 금형 FM540-2 · 생산관리자 승인 필요', ['FM540-2', '승인']);
  // ── 10 승인 → 실행 ───────────────────────────────────────────────────
  await lastCard().locator('[data-testid=kinetic-approve]').click();
  await p.locator('.kplan-approved').last().waitFor({ timeout: 30000 }); await sleep(800);
  await say('생산관리자 승인이 났어. 실행해.');
  await p.locator('[data-testid=kinetic-run]').last().waitFor({ timeout: 60000 }); await sleep(1500);
  await zoom(p, p.locator('[data-testid=kinetic-run]').last(), 10, 'wo-run', '실행 — 작업지시 발행 → 금형 장착', ['성공']);
  t = await lastAI();
  facts.woNo = (t.match(/\b26\d{2}-\d{4}\b/g) || []).pop();
  // ── 11 PriMES 작업지시·금형 ──────────────────────────────────────────
  await mesScreen('/m/production/work-orders');
  await shot(mes, 11, 'mes-wo', facts.woNo ? [facts.woNo] : ['FM540-2']);
  await mesScreen('/m/mold/mold-life');
  await shot(mes, 11, 'mes-mold', ['FM540-2']);

  // ── 12 모두 취소 ─────────────────────────────────────────────────────
  await say('방금 처리한 수주 건을 모두 취소해 줘.');
  await sleep(1500);
  await shot(p, 12, 'cancel', ['취소']);
  // ── 13 PriMES 원상 복구 ──────────────────────────────────────────────
  await mesScreen('/m/sales/sales-orders');
  await shot(mes, 13, 'mes-order-cancelled', [facts.orderNo]);
  await mesScreen('/m/mold/mold-life');
  await shot(mes, 13, 'mes-mold-restored', ['FM540-2']);

  // ── 14 어떻게 가능했나 ───────────────────────────────────────────────
  const row = (b, x) => `<div style="display:flex;gap:20px;margin:15px 0;font-size:27px"><b style="color:#ffb454;min-width:200px">${b}</b><span>${x}</span></div>`;
  await slide(14, 'how', `<div class="k">어떻게 가능했나</div><div style="margin-top:26px">
    ${row('시스템 등록', 'PriMES 마이크로서비스 여섯 개 — OpenAPI · 로그인 토큰')}${row('온톨로지', '시스템 조회 API 에서 고객·품목·금형·설비를 적재')}
    ${row('액션', '수주 · 발주 · 작업지시+금형 장착 — 단계마다 보상')}${row('정책', '승인 공급처 · 역할 · 생산관리자 승인')}</div>`);
  // ── 15·16 시스템 등록 ────────────────────────────────────────────────
  await nav(p, '시스템 등록');
  await p.locator('[data-testid=system-grid]').waitFor(); await sleep(1800);
  await shot(p, 15, 'grid', ['PriMES 영업', 'PriMES 금형']);
  await p.locator('[data-testid=system-card-primes-mold]').click(); await sleep(1800);
  await shot(p, 16, 'mold-system', ['로그인', 'mountMold']);
  } else {
    await p.goto(STUDIO, { waitUntil: 'networkidle' });
  }
  // ── 17 온톨로지 ─────────────────────────────────────────────────────
  const row = (b, x) => `<div style="display:flex;gap:20px;margin:15px 0;font-size:27px"><b style="color:#ffb454;min-width:200px">${b}</b><span>${x}</span></div>`;
  await nav(p, '질의·액션');
  await p.getByText('그래프', { exact: true }).click().catch(() => {});
  await p.getByText('스키마', { exact: true }).click().catch(() => {}); await sleep(2500);
  await shot(p, 17, 'schema-graph', ['온톨로지 그래프'], 100);
  // ── 18·19 액션 정의 ─────────────────────────────────────────────────
  await p.getByText('정보', { exact: true }).click(); await sleep(600);
  await p.locator('.right-panel-scroll').getByText('PriMES 반복 수주').first().click().catch(() => {}); await sleep(900);
  const moldRow = p.locator('.schema-class', { hasText: 'Mold' }).first();
  await moldRow.locator('button[title="데이터 연결"]').click({ force: true });
  await p.getByRole('button', { name: '액션', exact: true }).click(); await sleep(1200);
  await p.locator('[data-testid=class-actions-panel] button').filter({ hasText: /v\d/ }).first().click().catch(() => {}); await sleep(1200);
  const steps = p.locator('[data-testid=action-step]');
  await steps.nth(0).scrollIntoViewIfNeeded(); await sleep(400);
  await shot(p, 18, 'mold-action', ['issueWorkOrder', 'cancelWorkOrders']);
  await steps.nth(1).scrollIntoViewIfNeeded(); await sleep(400);
  await shot(p, 18, 'mold-action-mount', ['mountMold', '$before.mountedWo']);
  await p.getByRole('button', { name: '닫기' }).click().catch(() => {}); await sleep(500);
  const rmRow = p.locator('.schema-class', { hasText: 'RawMaterial' }).first();
  await rmRow.locator('button[title="데이터 연결"]').click({ force: true });
  await p.getByRole('button', { name: '액션', exact: true }).click(); await sleep(1200);
  await p.locator('[data-testid=class-actions-panel] button').filter({ hasText: /v\d/ }).first().click().catch(() => {}); await sleep(1200);
  await p.evaluate(() => { const el = [...document.querySelectorAll('*')].find(e => e.textContent.trim().startsWith('정책 (규칙은 OR')); el?.scrollIntoView({ block: 'start' }); });
  await sleep(600);
  await shot(p, 19, 'po-policy', ['params.supplierName == target.approvedSupplier']);
  // ── 20 정리 ─────────────────────────────────────────────────────────
  await slide(20, 'summary', `<div class="k">정리</div><div style="margin-top:28px">
    ${row('시스템', '기존 마이크로서비스를 그대로 등록')}${row('규칙', '프롬프트가 아니라 온톨로지 속성·정책에')}
    ${row('사람', '예외의 선택과 승인에만')}${row('복구', '되돌리는 길까지 정의 — 원래 상태로')}</div>`);
} finally {
  if (FROM > 1 && fs.existsSync('slides.json')) {
    const prev = JSON.parse(fs.readFileSync('slides.json', 'utf8')).filter(s => s.scene < FROM);
    slides.push(...prev);
  }
  slides.sort((a, b) => a.scene - b.scene);
  writeJson('slides.json', slides);
  if (FROM === 1) writeJson('facts.json', facts);
  fs.writeFileSync('checks.txt', checks.join('\n') + '\n');
  console.log(checks.join('\n'));
  console.log(JSON.stringify(facts, null, 1));
  await browser.close();
}
