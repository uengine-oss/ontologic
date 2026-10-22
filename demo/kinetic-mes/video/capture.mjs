// 키네틱 액션 시연 — 장면별 정지화면 캡처. 실행은 실제로 한 건 돌린다 (영상 안에서 계획·승인·실행).
// 벽시계로 녹화하지 않는다: 장면 길이는 build_video.py 가 narration/durations.json 에서 가져온다.
//   cd demo/kinetic-mes && uv run python studio/reset_run.py && cd video && node capture.mjs
import { createRequire } from 'module';
import fs from 'fs';
const require = createRequire('/Users/uengine/ontologic/ontology-studio/package.json');
const { chromium } = require('@playwright/test');

const STUDIO = 'http://localhost:5183/';
const MES = 'http://localhost:8031/';
const IDP = 'http://localhost:8032';
const KINETIC = 'http://localhost:8030';
const NEO4J_HTTP = 'http://localhost:7477/db/neo4j/tx/commit';
const OUT = 'slides';
const REQUEST = '온도가 80도를 넘는 설비를 모두 점검 모드로 바꿔 주세요. 사유는 냉각수 라인 이상에 따른 과열 점검입니다.';
const EXECUTE = '공장장 승인이 났습니다. 실행해 주세요.';

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });
const slides = [];            // [{scene, files:[...]}]
const checks = [];            // 화면 검증 기록
const sleep = ms => new Promise(r => setTimeout(r, ms));   // Node 타이머 — page.waitForTimeout 금지
const t0 = Date.now();
const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s]`, ...a);

function add(scene, file) {
  let s = slides.find(x => x.scene === scene);
  if (!s) slides.push(s = { scene, files: [] });
  s.files.push(file);
}

async function shot(page, scene, name, mustContain = [], minLen = 200) {
  // 입력 칸의 값은 innerText 에 잡히지 않는다 — 값도 함께 본다
  const body = (await page.locator('body').innerText()) + '\n' +
    (await page.$$eval('input, textarea, select', els => els.map(e => e.value).join('\n')));
  for (const m of mustContain) {
    if (!body.includes(m)) {
      await page.screenshot({ path: `FAIL-${name}.png` });
      throw new Error(`장면 ${scene} '${name}': 화면에 '${m}' 가 없다`);
    }
  }
  if (body.length < minLen) throw new Error(`장면 ${scene} '${name}': 빈 화면 (${body.length}자)`);
  const file = `s${String(scene).padStart(2, '0')}-${name}.png`;
  await page.screenshot({ path: `${OUT}/${file}` });
  add(scene, file);
  checks.push(`✓ ${file} (${body.length}자${mustContain.length ? ', ' + mustContain.join('·') : ''})`);
  log('shot', file);
}

// 요소 확대 장면 — 요소를 찍어 어두운 틀 가운데 크게 놓는다 (표가 작아 읽히지 않는 문제)
async function zoom(page, locator, scene, name, title, mustContain = []) {
  const txt = await locator.innerText();
  for (const m of mustContain) if (!txt.includes(m)) throw new Error(`확대 ${name}: '${m}' 없음`);
  // 채팅 칸이 좁아 사유 열이 잘린다 — 찍는 동안만 카드를 화면에 고정해 넓힌다 (부모의 overflow 를 벗어나게)
  await locator.evaluate(el => { el.dataset.prevStyle = el.getAttribute('style') || '';
    Object.assign(el.style, { position: 'fixed', left: '20px', top: '20px', width: '980px', maxWidth: 'none', zIndex: 99999, maxHeight: '680px', overflow: 'visible' });
    el.querySelectorAll('.ds-table-scroll').forEach(w => { w.style.overflow = 'visible'; }); });
  await sleep(300);
  const buf = await locator.screenshot();
  await locator.evaluate(el => { el.setAttribute('style', el.dataset.prevStyle);
    el.querySelectorAll('.ds-table-scroll').forEach(w => { w.style.overflow = ''; }); });
  const frame = await page.context().newPage();
  await frame.setContent(`<!doctype html><meta charset="utf-8"><style>
    html,body{margin:0;width:1280px;height:720px;background:#0b1018;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif}
    .t{color:#9fb3c8;font-size:20px;padding:22px 36px 0;letter-spacing:.02em}
    .w{display:flex;align-items:center;justify-content:center;height:640px}
    img{max-width:1180px;max-height:600px;border-radius:10px;box-shadow:0 8px 40px #000a}</style>
    <div class="t">${title}</div><div class="w"><img src="data:image/png;base64,${buf.toString('base64')}"></div>`);
  const file = `s${String(scene).padStart(2, '0')}-${name}.png`;
  await frame.screenshot({ path: `${OUT}/${file}` });
  await frame.close();
  add(scene, file);
  checks.push(`✓ ${file} (확대, ${txt.length}자${mustContain.length ? ', ' + mustContain.join('·') : ''})`);
  log('zoom', file);
}

async function token(sub, roles, plant) {
  const r = await fetch(`${IDP}/token`, { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ sub, roles, plant }) });
  return (await r.json()).access_token;
}

async function equipmentStatus() {
  const r = await fetch(NEO4J_HTTP, { method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Basic ' + Buffer.from('neo4j:kineticdemo').toString('base64') },
    body: JSON.stringify({ statements: [{ statement:
      "MATCH (e:Equipment {demo:'kinetic-mes'}) RETURN e.code, e.name, e.plant, e.temp, e.status ORDER BY e.code" }] }) });
  return (await r.json()).results[0].data.map(d => d.row);
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
const p = await ctx.newPage();
const mes = await ctx.newPage();

async function waitAgent() {
  await p.locator('.btn-stop').waitFor({ state: 'visible', timeout: 30000 }).catch(() => {});
  await p.locator('.btn-stop').waitFor({ state: 'detached', timeout: 600000 });
  await sleep(1500);
}

try {
  // ── 준비: 액션 실행 모드 · 새 대화 ─────────────────────────────────────
  await p.goto(STUDIO, { waitUntil: 'networkidle' });
  await p.locator('text=액션 실행').first().click();
  await sleep(800);
  await p.locator('[title$="워크스페이스 펼치기"]').first().click();
  await sleep(400);
  await p.locator('.sidebar-new').click();
  await sleep(400);
  await p.locator('[title="워크스페이스 접기"]').click().catch(() => {});
  await sleep(600);

  // ── 1 사건: 그래프에 있는 실제 설비 온도로 만든 현황판 ────────────────
  const eq0 = await equipmentStatus();
  const inc = await ctx.newPage();
  await inc.setContent(`<!doctype html><meta charset="utf-8"><style>
    body{margin:0;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;background:#0f1520;color:#dfe7f1}
    .bar{background:#5c1d1d;color:#ffd7d7;padding:18px 32px;font-size:22px;font-weight:700}
    .bar small{font-weight:400;font-size:15px;margin-left:12px;color:#f3b0b0}
    .w{padding:20px 32px}table{width:100%;border-collapse:collapse;font-size:17px}
    td,th{padding:11px 12px;border-bottom:1px solid #263447;text-align:left}th{color:#8aa0b6;font-size:14px;font-weight:500}
    .hot td{color:#ffb4a8}.hot .t{font-weight:700;color:#ff6b5b}code{font-family:Menlo,monospace}</style>
    <div class="bar">02:00 · 1공장 냉각수 라인 압력 저하<small>설비 온도 현황 (그래프 인스턴스)</small></div>
    <div class="w"><table><tr><th>설비</th><th>이름</th><th>공장</th><th>온도(℃)</th><th>상태</th></tr>
    ${eq0.map(r => `<tr class="${r[3] > 80 ? 'hot' : ''}"><td><code>${r[0]}</code></td><td>${r[1]}</td><td>${r[2]}</td><td class="t">${r[3]}</td><td>${r[4]}</td></tr>`).join('')}
    </table></div>`);
  await shot(inc, 1, 'incident', ['냉각수', 'EQ-101', 'EQ-202'], 100);
  await inc.close();

  // ── 2 왜 어려운가: 생산관리 시스템은 따로 있다 ──────────────────────────
  await mes.goto(MES, { waitUntil: 'networkidle' });
  await shot(mes, 2, 'mes-empty', ['받은 요청 0건', '받은 요청이 없습니다'], 50);

  // ── 3 업무 지도: 그래프 · 클래스와 속성 ─────────────────────────────────
  await p.getByText('그래프', { exact: true }).click();
  await p.getByText('스키마', { exact: true }).click();
  await sleep(2500);
  await shot(p, 3, 'graph', ['온톨로지 그래프', '액션 실행']);  // 그래프는 캔버스라 클래스명이 DOM 에 없다
  await p.getByText('정보', { exact: true }).click();
  await p.getByText('MES 설비 운영').click();
  await sleep(1000);
  await shot(p, 3, 'classes', ['Equipment', 'temp', 'plant', 'status']);

  // ── 4 행위를 지도에 붙인다: 액션 탭 ───────────────────────────────────
  await p.locator('button[title="데이터 연결"]').nth(0).click({ force: true });
  await p.getByRole('button', { name: '액션', exact: true }).click();
  await sleep(1200);
  await p.getByText('setMaintenanceMode').first().click();
  await sleep(1500);
  await p.getByText('setMaintenanceMode v1').first().scrollIntoViewIfNeeded();
  await shot(p, 4, 'action-top', ['setMaintenanceMode', 'mock-mes']);
  await p.getByText('인자 매핑 (arg_mapping)').scrollIntoViewIfNeeded();
  await p.evaluate(() => { const el = [...document.querySelectorAll('*')].find(e => e.textContent.trim() === '인자 매핑 (arg_mapping)'); el?.scrollIntoView({ block: 'start' }); });
  await sleep(800);
  await shot(p, 4, 'action-mapping', ['$this.code', '$params.reason']);

  // ── 5 규칙은 정의에: 정책 · 승인 임계치 ────────────────────────────────
  await p.evaluate(() => { const el = [...document.querySelectorAll('*')].find(e => e.textContent.trim().startsWith('정책 (규칙은 OR')); el?.scrollIntoView({ block: 'start' }); });
  await sleep(800);
  await shot(p, 5, 'policy', ['target.plant == actor.plant', '승인 임계치']);

  // ── 6 원래 시스템에서 실행: 시스템 · operation ─────────────────────────
  await p.evaluate(() => { const el = [...document.querySelectorAll('label, div, span')].find(e => e.textContent.trim() === '시스템'); el?.scrollIntoView({ block: 'start' }); });
  await sleep(800);
  await shot(p, 6, 'system', ['mock-mes', 'setEquipmentStatus']);

  // ── 7 요청 ────────────────────────────────────────────────────────────
  await p.getByRole('button', { name: '닫기' }).click().catch(() => {});
  await p.getByText('그래프', { exact: true }).click();
  await sleep(800);
  const box = p.locator('textarea').last();
  await box.fill(REQUEST);
  await sleep(500);
  await shot(p, 7, 'request', ['액션 실행']);

  // ── 8 에이전트가 계획을 세운다 ─────────────────────────────────────────
  await box.press('Enter');
  log('요청 전송');
  await sleep(4000);
  await shot(p, 8, 'thinking', ['온도가 80도를 넘는']);
  await waitAgent();
  log('계획 완료');
  const card = p.locator('[data-testid=kinetic-plan-card]').last();
  await card.waitFor({ timeout: 60000 });
  await sleep(1500);
  const tools = p.locator('text=/개 도구 사용됨/').last();
  await tools.click();                 // 끝나면 도구 목록이 접힌다 — 펼쳐서 보여 준다
  await sleep(800);
  await tools.scrollIntoViewIfNeeded();
  await shot(p, 8, 'tools', ['list_actions', 'plan_action']);

  // ── 9 계획 카드 ───────────────────────────────────────────────────────
  await card.scrollIntoViewIfNeeded();
  await shot(p, 9, 'plan', ['허용 3건', '거부 2건']);
  await zoom(p, card, 9, 'plan-zoom', '실행 계획 — 허용 3건 · 거부 2건', ['EQ-101', 'EQ-201', '담당 공장 설비만']);

  // ── 10 사람의 승인 ────────────────────────────────────────────────────
  await card.locator('[data-testid=kinetic-approve]').click();
  await p.locator('.kplan-approved').last().waitFor({ timeout: 30000 });
  await sleep(1000);
  await zoom(p, card, 10, 'approved', '공장장 승인 — 에이전트에게는 승인 도구가 없다', ['승인됨']);

  // ── 11 실행 ───────────────────────────────────────────────────────────
  await box.fill(EXECUTE);
  await box.press('Enter');
  log('실행 요청');
  await waitAgent();
  const run = p.locator('[data-testid=kinetic-run]').last();
  await run.waitFor({ timeout: 60000 });
  await sleep(2500);
  await shot(p, 11, 'run', ['succeeded']);
  const runCard = p.locator('[data-testid=kinetic-plan-card]').last();
  await runCard.scrollIntoViewIfNeeded();
  await zoom(p, runCard, 11, 'run-zoom', '실행 결과 — 대상별 요청 3건', ['성공', 'EQ-104']);

  // ── 12 생산관리 시스템 쪽 ─────────────────────────────────────────────
  await mes.reload({ waitUntil: 'networkidle' });
  await shot(mes, 12, 'mes-received', ['받은 요청 3건', 'EQ-101', 'EQ-102', 'EQ-104']);
  const mesBody = await mes.locator('body').innerText();
  if (/EQ-20\d/.test(mesBody)) throw new Error('2공장 설비 요청이 MES 에 도달했다');

  // ── 13 기록이 남는다: 지도 상태 + 감사 기록 ────────────────────────────
  const approver = await token('park.manager', ['kinetic_approver']);
  let audit;
  for (let i = 0; i < 3 && !Array.isArray(audit); i++) {
    const r = await fetch(`${KINETIC}/api/kinetic/audit`, { headers: { authorization: `Bearer ${approver}` } });
    audit = await r.json();
    if (!Array.isArray(audit)) { log('audit 응답', r.status, JSON.stringify(audit).slice(0, 200)); await sleep(1500); }
  }
  const planEv = audit.filter(e => e.event === 'plan').at(-1);
  const evs = audit.filter(e => e.plan_id === planEv.plan_id);
  const eq = await equipmentStatus();
  const label = { plan: '계획', approve: '승인', execute: '실행', reject: '반려', retry: '재시도' };
  const rec = await ctx.newPage();
  await rec.setContent(`<!doctype html><meta charset="utf-8"><style>
    body{margin:0;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;background:#0f1520;color:#dfe7f1}
    h1{font-size:22px;margin:0;padding:20px 32px;background:#16202e;border-bottom:1px solid #263447}
    h1 small{font-size:14px;color:#8aa0b6;margin-left:10px;font-weight:400}
    .g{display:grid;grid-template-columns:1fr 1fr;gap:22px;padding:22px 32px}
    h2{font-size:16px;color:#8aa0b6;margin:0 0 10px}
    table{width:100%;border-collapse:collapse;font-size:15px}td,th{padding:9px 10px;border-bottom:1px solid #263447;text-align:left}
    th{color:#8aa0b6;font-weight:500;font-size:13px}.m{color:#ffb454;font-weight:700}.r{color:#7ee2a8}
    code{font-family:Menlo,monospace;font-size:13px;color:#b9c9da}</style>
    <h1>실행 기록 조회<small>계획 ${planEv.plan_id}</small></h1>
    <div class="g"><div><h2>그래프의 설비 상태</h2><table><tr><th>설비</th><th>이름</th><th>공장</th><th>온도</th><th>상태</th></tr>
    ${eq.map(r => `<tr><td><code>${r[0]}</code></td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td><td class="${r[4] === 'MAINTENANCE' ? 'm' : 'r'}">${r[4]}</td></tr>`).join('')}</table></div>
    <div><h2>감사 기록</h2><table><tr><th>시각(UTC)</th><th>사건</th><th>주체</th><th>내용</th></tr>
    ${evs.map(e => { const d = e.detail ? JSON.parse(e.detail) : {}; const c = e.event === 'plan' ? `허용 ${d.allowed} · 거부 ${d.denied}` : e.event === 'execute' ? `${d.status} · ${e.run_id}` : ''; return `<tr><td>${e.ts.slice(11, 19)}</td><td><b>${label[e.event] || e.event}</b></td><td>${e.actor_sub || ''}</td><td><code>${c}</code></td></tr>`; }).join('')}</table></div></div>`);
  await shot(rec, 13, 'record', ['MAINTENANCE', 'park.manager', 'kim.operator', '승인']);
  if (eq.filter(r => r[4] === 'MAINTENANCE').length !== 3) throw new Error('MAINTENANCE 가 3대가 아니다');

  // ── 14 정리 ───────────────────────────────────────────────────────────
  const end = await ctx.newPage();
  await end.setContent(`<!doctype html><meta charset="utf-8"><style>
    body{margin:0;height:720px;display:flex;flex-direction:column;justify-content:center;padding:0 110px;box-sizing:border-box;
    background:#0b1018;color:#e8eef5;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif}
    .k{font-size:18px;color:#7aa7d6;letter-spacing:.08em;margin-bottom:26px}
    .row{display:flex;gap:22px;align-items:baseline;margin:16px 0;font-size:30px}.row b{color:#ffb454;min-width:150px}
    .s{font-size:22px;color:#9fb3c8}.f{margin-top:40px;font-size:20px;color:#8aa0b6}</style>
    <div class="k">질문에서 행동까지</div>
    <div class="row"><b>규칙</b><span>업무 지도에 적는다 <span class="s">— 담당 공장 설비만, 두 대를 넘으면 승인</span></span></div>
    <div class="row"><b>실행</b><span>원래 시스템에 맡긴다 <span class="s">— 등록된 요청 창구, 설비마다 멱등 키</span></span></div>
    <div class="row"><b>판단</b><span>사람이 필요한 지점에서 <span class="s">— 계획을 보고 승인, 모든 단계가 기록</span></span></div>
    <div class="f">Ontology Studio · 키네틱 액션 레이어</div>`);
  await end.screenshot({ path: `${OUT}/s14-summary.png` });
  add(14, 's14-summary.png');
  checks.push('✓ s14-summary.png (정리 슬라이드)');
} finally {
  slides.sort((a, b) => a.scene - b.scene);
  fs.writeFileSync('slides.json', JSON.stringify(slides, null, 1));
  fs.writeFileSync('checks.txt', checks.join('\n') + '\n');
  console.log(checks.join('\n'));
  await browser.close();
}
