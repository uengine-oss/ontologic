// 온보딩 시연 — 장면별 정지화면 캡처. 시스템 등록 · 구축 · 질의 · 실행 · 취소 · 장애 보상을 **실제로** 돌린다.
// 사전: studio/run_studio.sh stop → onboard → start  (run.sh 가 한다)
import fs from 'fs';
import { chromium, STUDIO, sleep, log, pageText, nav, waitAgent, writeJson } from './lib.mjs';

const OUT = 'slides';
const SVC = { mes: 'http://localhost:8031/', cmms: 'http://localhost:8034/', aps: 'http://localhost:8035/' };
const INTENT = '설비 과열 같은 이상이 생겼을 때 운영자가 대화로 대상 설비를 찾고, 점검 전환을 생산관리(MES)·설비보전(CMMS)·생산계획(APS) 시스템에 한 번에 요청하며, 필요하면 취소해 원래대로 되돌린다.';
const GQ = ['1공장에서 온도가 80도를 넘는 설비는?', '지금 점검 중인 설비는 몇 대야?'];
const GC = ['온도가 80도를 넘는 설비를 모두 점검 모드로 바꿔 줘. 사유는 과열 점검.', '방금 점검 전환을 취소해 줘.'];

// FROM=15 node capture.mjs — 이미 구축된 상태에서 15번 장면부터만 (구축을 다시 돌리지 않고 뒷부분을 시험할 때)
const FROM = Number(process.env.FROM || 1);
if (FROM === 1) fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });
const slides = [];
const checks = [];
const add = (scene, file) => { let s = slides.find(x => x.scene === scene); if (!s) slides.push(s = { scene, files: [] }); s.files.push(file); };
const fname = (scene, name) => `s${String(scene).padStart(2, '0')}-${name}.png`;

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
const svc = await ctx.newPage();
const box = () => p.locator('textarea').last();
async function ask(text) { await box().fill(text); await box().press('Enter'); await waitAgent(p); }
async function newChat() {
  await nav(p, '질의·액션');
  await p.locator('[title$="워크스페이스 펼치기"]').first().click().catch(() => {});
  await sleep(300); await p.locator('.sidebar-new').click().catch(() => {}); await sleep(300);
  await p.locator('[title="워크스페이스 접기"]').click().catch(() => {}); await sleep(600);
}
async function consoles(scene, tag, expect) {
  for (const [k, url] of Object.entries(SVC)) {
    await svc.goto(url, { waitUntil: 'networkidle' });
    await shot(svc, scene, `${tag}-${k}`, expect[k] || [], 40);
  }
}

try {
  if (FROM === 1) {
  // ── 1 사건: 설비 대장 (업로드할 문서 그대로) ───────────────────────────
  const md = fs.readFileSync('../onboarding/설비대장.md', 'utf8');
  const rows = md.split('\n').filter(l => /^\| EQ-/.test(l)).map(l => l.split('|').slice(1, -1).map(c => c.trim()));
  await slide(1, 'ledger', `<div style="background:#5c1d1d;color:#ffd7d7;margin:-70px -90px 26px;padding:18px 32px;font-size:22px;font-weight:700">
    02:00 · 1공장 냉각수 라인 압력 저하 <span style="font-weight:400;font-size:15px;color:#f3b0b0;margin-left:10px">생산 설비 대장 (2026년 10월)</span></div>
    <table style="width:100%;border-collapse:collapse;font-size:17px">${['설비 코드', '설비 이름', '공장', '온도(℃)', '상태'].map(h => `<th style="text-align:left;color:#8aa0b6;padding:9px;border-bottom:1px solid #263447;font-weight:500">${h}</th>`).join('')}
    ${rows.map(r => `<tr style="${parseFloat(r[3]) > 80 ? 'color:#ffb4a8' : ''}">${r.map((c, i) => `<td style="padding:9px;border-bottom:1px solid #263447;${i === 3 && parseFloat(c) > 80 ? 'color:#ff6b5b;font-weight:700' : ''}">${c}</td>`).join('')}</tr>`).join('')}</table>`);

  // ── 2 왜 어려운가: 세 팀의 세 시스템 ──────────────────────────────────
  await consoles(2, 'console', {});

  // ── 3 되돌리기 ────────────────────────────────────────────────────────
  const stepBox = (t, c) => `<div style="background:${c};border-radius:12px;padding:20px 26px;font-size:24px;font-weight:700;min-width:250px;text-align:center">${t}</div>`;
  await slide(3, 'reverse', `<div class="k">점검 전환 — 앞으로 가는 길과 되돌리는 길</div>
    <div style="display:flex;gap:22px;align-items:center;margin-top:60px">${stepBox('① MES 상태 변경', '#1d4ed8')}<span style="font-size:34px">→</span>${stepBox('② CMMS 작업지시', '#c2410c')}<span style="font-size:34px">→</span>${stepBox('③ APS 일정 재배정', '#7c3aed')}</div>
    <div style="display:flex;gap:22px;align-items:center;margin-top:46px">${stepBox('상태 복원', '#1e3a8a')}<span style="font-size:34px">←</span>${stepBox('작업지시 취소', '#7c2d12')}<span style="font-size:34px">←</span>${stepBox('일정 원복', '#4c1d95')}</div>
    <div style="margin-top:46px;font-size:21px;color:#9fb3c8">중간에 하나라도 실패하면 시스템마다 상태가 엇갈린다 — 지금은 이 순서를 사람이 기억한다</div>`);

  // ── 4 온보딩 순서 ─────────────────────────────────────────────────────
  const chip = (n, t, s) => `<div style="display:flex;gap:18px;align-items:baseline;margin:15px 0"><b style="color:#ffb454;font-size:26px;width:40px">${n}</b><span style="font-size:27px">${t}</span><span style="font-size:19px;color:#8aa0b6">${s}</span></div>`;
  await slide(4, 'flow', `<div class="k">온보딩 순서</div><div style="margin-top:30px">
    ${chip(1, '시스템 등록', '마이크로서비스 · OpenAPI · 인증')}${chip(2, '문서·데이터 소스', '설비 대장')}
    ${chip(3, '의도 · 골든 퀘스천 · 골든 커맨드', '답해야 할 것과 실행해야 할 것')}${chip(4, '구축', '온톨로지 + 액션(단계·보상) 자동 설정 · 검증')}
    ${chip(5, '질의 · 액션', '묻고 · 시키고 · 승인하고 · 되돌린다')}</div>`);

  // ── 5~10 시스템 등록 ──────────────────────────────────────────────────
  await p.goto(STUDIO, { waitUntil: 'networkidle' });
  await nav(p, '시스템 등록');
  await p.locator('[data-testid=system-grid]').waitFor(); await sleep(1800);
  await shot(p, 5, 'grid', ['생산관리 MES', '생산계획 APS']);
  await p.locator('[data-testid=system-new]').click(); await sleep(700);
  await p.locator('[data-testid=system-display-name]').fill('설비보전 CMMS');
  await p.locator('[data-testid=system-name]').fill('mock-cmms');
  await p.getByPlaceholder('설비보전 — 정비 작업지시').fill('설비보전 — 정비 작업지시 생성·취소');
  await p.getByPlaceholder('설비보전팀').fill('설비보전팀');
  await p.getByPlaceholder('maint-ops@example.com').fill('maint-ops@factory.example');
  await p.getByPlaceholder('보전, 설비, P1').fill('보전, 설비, 작업지시');
  await p.locator('.sr-icon-opt[title=CMMS]').click();
  await shot(p, 6, 'basic', ['설비보전 CMMS', 'mock-cmms', '설비보전팀']);
  await p.locator('[data-testid=system-next]').click(); await sleep(700);
  await p.locator('[data-testid=system-spec-file]').setInputFiles('../onboarding/mock-cmms-openapi.json'); await sleep(1500);
  await shot(p, 7, 'spec', ['SOAP', 'gRPC']);
  await p.locator('[data-testid=system-next]').click(); await sleep(700);
  await p.locator('[data-testid=system-env-url-0]').fill('http://localhost:8034');
  await p.locator('[data-testid=system-next]').click(); await sleep(700);
  await p.locator('[data-testid=system-auth-kind]').selectOption('api_key'); await sleep(300);
  await p.getByPlaceholder('X-Api-Key').fill('X-API-Key');
  await p.getByPlaceholder('CMMS_API_KEY').fill('CMMS_API_KEY');
  await shot(p, 8, 'auth', ['X-API-Key', 'CMMS_API_KEY', '비밀 값은 저장하지 않습니다']);
  await p.locator('[data-testid=system-next]').click(); await sleep(700);
  await p.getByPlaceholder('/health').fill('/health');
  await p.locator('[data-testid=system-next]').click(); await sleep(700);
  await p.locator('[data-testid=system-test]').click();
  await p.locator('[data-testid=system-test-result]').waitFor({ timeout: 30000 }); await sleep(800);
  await shot(p, 9, 'test', ['operation 3개', '정상', '모두 있습니다']);
  await p.locator('[data-testid=system-submit]').click();
  await p.locator('[data-testid=system-detail]').waitFor({ timeout: 30000 }); await sleep(1200);
  await p.locator('[data-testid=operation-add-open]').click(); await sleep(500);
  await p.locator('[data-testid=operation-id]').fill('getWorkOrder');
  await p.locator('[data-testid=operation-method]').selectOption('GET');
  await p.locator('[data-testid=operation-path]').fill('/work-orders/{id}');
  await p.getByPlaceholder('작업지시 한 건 조회').fill('작업지시 한 건 조회 (스펙에 없는 API)');
  await p.getByRole('button', { name: '자동 추가' }).click(); await sleep(400);
  await p.locator('[data-testid=operation-submit]').click(); await sleep(2000);
  await shot(p, 10, 'detail', ['getWorkOrder', 'createWorkOrder', 'cancelWorkOrder', '직접 추가', '/svc/mock-cmms']);
  // 8 장면 보조 — 생산계획의 OAuth2 인증
  await p.getByText('‹ 목록').click().catch(() => {}); await sleep(800);
  await p.locator('[data-testid=system-card-mock-aps]').click(); await sleep(1500);
  await shot(p, 8, 'aps-oauth', ['OAuth2', 'APS_CLIENT_SECRET']);

  // ── 11~14 온톨로지 구축 ───────────────────────────────────────────────
  await nav(p, '온톨로지'); await sleep(800);
  await p.locator('input[type=file]').first().setInputFiles('../onboarding/설비대장.md'); await sleep(1500);
  await shot(p, 11, 'source-doc', ['설비대장.md']);
  for (const s of ['mock-mes', 'mock-cmms', 'mock-aps']) { await p.locator('[data-testid=brief-systems] .datasource-chip', { hasText: s }).click(); await sleep(250); }
  await p.locator('[data-testid=brief-systems]').scrollIntoViewIfNeeded(); await sleep(500);
  await shot(p, 11, 'source-systems', ['시스템 (서비스)', 'mock-cmms']);
  await p.getByRole('button', { name: '다음 →' }).click(); await sleep(600);
  await p.getByPlaceholder('새 스키마 이름 (선택, 예: 제조 운영 스키마)').fill('MES 설비 운영');
  await p.getByRole('button', { name: '다음 →' }).click(); await sleep(600);
  await p.getByPlaceholder(/내부 감사 담당자가/).fill(INTENT);
  for (let i = 0; i < GQ.length; i++) {
    if (!(await p.getByPlaceholder(`예: Golden Question ${i + 1}`).count())) { await p.locator('button', { hasText: /질문 추가|퀘스천 추가/ }).first().click().catch(() => {}); await sleep(300); }
    await p.getByPlaceholder(`예: Golden Question ${i + 1}`).fill(GQ[i]);
  }
  for (let i = 0; i < GC.length; i++) {
    if (!(await p.getByPlaceholder(`예: Golden Command ${i + 1}`).count())) { await p.locator('[data-testid=brief-golden-commands] .btn-inline-add').click(); await sleep(300); }
    await p.getByPlaceholder(`예: Golden Command ${i + 1}`).fill(GC[i]);
  }
  await p.locator('[data-testid=brief-golden-commands]').scrollIntoViewIfNeeded(); await sleep(400);
  await shot(p, 12, 'brief', [GQ[0], GC[0], GC[1]]);
  await p.getByRole('button', { name: '이 브리프로 구축 시작' }).click();
  log('구축 시작');
  const bt = Date.now();
  await sleep(50000);
  await shot(p, 13, 'building-1', ['구축'], 100);
  await sleep(50000);
  const tools = p.locator('text=/개 도구 사용됨/').last();
  await shot(p, 13, 'building-2', [], 100);
  await waitAgent(p, 1800000);
  log('구축 끝', (Date.now() - bt) / 1000, 's');
  await tools.click().catch(() => {}); await sleep(600);
  const toolText = await pageText(p);
  for (const t of ['system_operations', 'action_create', 'action_dry_run']) if (!toolText.includes(t)) log('경고: 도구 이력에 없음', t);
  await tools.click().catch(() => {}); await sleep(400);
  const report = p.locator('[data-testid=build-report-commands]').last();
  await report.waitFor({ timeout: 30000 });
  // 검증 기준: 두 커맨드 모두 액션에 이어지고 미검증이 없을 것 (취소 커맨드 문구는 에이전트 보고 방식에 따라 다르다)
  let rtxt = await report.innerText();
  if (rtxt.includes('미검증') && !rtxt.includes('만들어지지 않았습니다')) {
    // 사용자가 하듯이 한 번 더 요청한다 — 에이전트가 검증(dry-run)을 끝내지 않고 보고한 경우
    log('미검증 — 검증을 마저 요청');
    await ask('골든 커맨드 검증이 아직 미검증으로 남아 있어요. 액션을 발행하고 dry-run 으로 검증을 마저 해 주세요.');
    await p.locator('[data-testid=build-report-commands]').last().waitFor({ timeout: 60000 });
    rtxt = await p.locator('[data-testid=build-report-commands]').last().innerText();
  }
  if (rtxt.includes('만들어지지 않았습니다') || rtxt.includes('미검증')) {
    await p.screenshot({ path: 'FAIL-report.png' }); throw new Error('골든 커맨드가 액션·검증에 이어지지 않았다 — 구축을 다시 돌려야 한다'); }
  await zoom(p, p.locator('[data-testid=build-report-commands]').last(), 14, 'report', '구축 보고서 — 골든 커맨드 → 액션 → 단계 → 검증', [GC[0].slice(0, 10), GC[1].slice(0, 8)]);

  } else {
    await p.goto(STUDIO, { waitUntil: 'networkidle' });
    if (FROM === 14) {
      await nav(p, '온톨로지'); await sleep(2500);
      await zoom(p, p.locator('[data-testid=build-report-commands]').last(), 14, 'report', '구축 보고서 — 골든 커맨드 → 액션 → 단계 → 검증', [GC[0].slice(0, 10), GC[1].slice(0, 8)]);
    }
  }

  // ── 15 자동으로 설정된 액션 ───────────────────────────────────────────
  await p.getByText('정보', { exact: true }).click(); await sleep(600);
  await p.locator('.right-panel-scroll').getByText('MES 설비 운영').first().click(); await sleep(800);
  const eqRow = p.locator('.schema-class', { hasText: 'Equipment' }).first();
  await (await eqRow.count() ? eqRow.locator('button[title="데이터 연결"]') : p.locator('button[title="데이터 연결"]').first()).click({ force: true });
  await p.getByRole('button', { name: '액션', exact: true }).click(); await sleep(1200);
  await p.locator('[data-testid=class-actions-panel] button, [data-testid=class-actions-panel] .chip').filter({ hasText: /v\d/ }).first().click().catch(() => {});
  await sleep(1200);
  const steps = p.locator('[data-testid=action-step]');
  if ((await steps.count()) < 3) throw new Error(`액션 단계가 ${await steps.count()}개`);
  await steps.nth(0).scrollIntoViewIfNeeded(); await sleep(500);
  await shot(p, 15, 'steps-1', ['setEquipmentStatus', 'createWorkOrder']);
  await steps.nth(2).scrollIntoViewIfNeeded(); await sleep(500);
  await shot(p, 15, 'steps-2', ['revertReschedule', 'cancelWorkOrder']);

  // ── 16 질의 ───────────────────────────────────────────────────────────
  await newChat();
  await p.getByText('그래프', { exact: true }).click().catch(() => {});
  await ask(GQ[0]);
  await shot(p, 16, 'question', ['EQ-101', 'EQ-102', 'EQ-104']);

  // ── 17 커맨드 → 계획 ─────────────────────────────────────────────────
  await ask('공장 구분 없이 온도가 80도를 넘는 설비를 모두 점검 모드로 바꿔 줘. 사유는 냉각수 라인 이상에 따른 과열 점검.');
  let card = p.locator('[data-testid=kinetic-plan-card]').last();
  await card.waitFor({ timeout: 60000 }); await sleep(1200);
  await shot(p, 17, 'plan', ['허용 3건', '거부 2건']);
  await zoom(p, card, 17, 'plan-zoom', '실행 계획 — 허용 3 · 거부 2 · 호출 9건 (3대 × 3단계)', ['EQ-101', 'EQ-201', '9건']);

  // ── 18 승인 · 실행 ───────────────────────────────────────────────────
  await card.locator('[data-testid=kinetic-approve]').click();
  await p.locator('.kplan-approved').last().waitFor({ timeout: 30000 }); await sleep(800);
  await ask('공장장 승인이 났습니다. 실행해 주세요.');
  card = p.locator('[data-testid=kinetic-plan-card]').last();
  await p.locator('[data-testid=kinetic-run]').last().waitFor({ timeout: 60000 }); await sleep(2000);
  await zoom(p, p.locator('[data-testid=kinetic-run]').last(), 18, 'run', '실행 결과 — 설비마다 MES → CMMS → APS', ['성공', 'EQ-104', 'APS']);

  // ── 19 세 시스템의 기록 ──────────────────────────────────────────────
  await consoles(19, 'received', { mes: ['EQ-101', 'MAINTENANCE'], cmms: ['EQ-101', 'OPEN'], aps: ['EQ-101'] });
  // 생산계획 화면은 오더를 옮겨 갈 설비(EQ-2xx 일 수 있다)를 함께 보여 주므로 요청 대상 검사는 MES·CMMS 만
  for (const k of ['mes', 'cmms']) { await svc.goto(SVC[k]); if (/EQ-20\d/.test(await svc.locator('body').innerText())) throw new Error(`${k} 에 2공장 요청이 있다`); }

  // ── 20 취소 — 역순 보상 ──────────────────────────────────────────────
  await ask('냉각수 라인이 복구됐어. 방금 점검 전환을 취소해 줘.');
  await sleep(2000);
  const runEl = p.locator('[data-testid=kinetic-run]').last();
  await zoom(p, runEl, 20, 'compensation', '취소 — 보상 이력 (호출 순서)', ['보상 이력', 'revertReschedule', 'cancelWorkOrder']);

  // ── 21 시스템 쪽 원상 복구 ───────────────────────────────────────────
  await consoles(21, 'restored', { mes: ['RUNNING'], cmms: ['CANCELLED'], aps: ['REVERTED'] });

  // ── 22 장애 시 자동 보상 ─────────────────────────────────────────────
  await fetch(`${SVC.aps}admin/fail`, { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ codes: ['EQ-102'], operations: ['createReschedule'], status: 503 }) });
  await ask('다시 공장 구분 없이 온도가 80도를 넘는 설비를 모두 점검 모드로 바꿔 줘. 사유는 냉각수 재점검.');
  card = p.locator('[data-testid=kinetic-plan-card]').last();
  await card.locator('[data-testid=kinetic-approve]').waitFor({ timeout: 60000 });
  await card.locator('[data-testid=kinetic-approve]').click();
  await p.locator('.kplan-approved').last().waitFor({ timeout: 30000 }); await sleep(800);
  await ask('승인됐어요. 실행해 주세요.');
  await p.locator('[data-testid=kinetic-run]').last().waitFor({ timeout: 60000 }); await sleep(2000);
  await zoom(p, p.locator('[data-testid=kinetic-run]').last(), 22, 'auto-comp', '생산계획 장애 — EQ-102 만 앞 단계를 자동 보상', ['EQ-102', '자동']);
  await fetch(`${SVC.aps}admin/fail`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ codes: [], all: false }) });

  // ── 23 정리 ───────────────────────────────────────────────────────────
  const row = (b, t, s) => `<div style="display:flex;gap:22px;align-items:baseline;margin:17px 0;font-size:29px"><b style="color:#ffb454;min-width:150px">${b}</b><span>${t} <span style="font-size:20px;color:#9fb3c8">— ${s}</span></span></div>`;
  await slide(23, 'summary', `<div class="k">질문에서 행동까지, 그리고 되돌리기까지</div><div style="margin-top:28px">
    ${row('등록', '시스템은 데이터소스처럼', 'OpenAPI · 인증은 이름만 · 연결 테스트')}
    ${row('정의', '해야 할 일은 골든 커맨드로', '에이전트가 API 를 찾아 단계와 보상을 설정')}
    ${row('실행', '사람은 승인 지점에서', '정책으로 걸러진 계획 · 대상별 사가')}
    ${row('복구', '되돌리는 길까지 정의', '취소는 역순 보상 · 장애는 자동 보상')}</div>
    <div style="margin-top:36px;font-size:19px;color:#8aa0b6">Ontology Studio · 키네틱 액션 레이어</div>`);
} finally {
  slides.sort((a, b) => a.scene - b.scene);
  if (FROM === 1) writeJson('slides.json', slides); else writeJson(`slides-from${FROM}.json`, slides);
  fs.writeFileSync('checks.txt', checks.join('\n') + '\n');
  console.log(checks.join('\n'));
  await browser.close();
}
