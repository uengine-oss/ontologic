// 리허설 2 — 온톨로지 구축: 문서 + 시스템 + 의도·골든 퀘스천·골든 커맨드 → 구축 에이전트
import { chromium, STUDIO, sleep, log, pageText, nav, waitAgent } from './lib.mjs';
const OUT = 'rehearsal';
const INTENT = '설비 과열 같은 이상이 생겼을 때 운영자가 대화로 대상 설비를 찾고, 점검 전환을 생산관리(MES)·설비보전(CMMS)·생산계획(APS) 시스템에 한 번에 요청하며, 필요하면 취소해 원래대로 되돌린다.';
const GQ = ['1공장에서 온도가 80도를 넘는 설비는?', '지금 점검 중인 설비는 몇 대야?'];
const GC = ['온도가 80도를 넘는 설비를 모두 점검 모드로 바꿔 줘. 사유는 과열 점검.', '방금 점검 전환을 취소해 줘.'];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
const snap = async n => { await p.screenshot({ path: `${OUT}/${n}.png` }); log(n); };
await p.goto(STUDIO, { waitUntil: 'networkidle' });
await nav(p, '온톨로지');
await sleep(1000);
await p.locator('input[type=file]').first().setInputFiles('../onboarding/설비대장.md');
await sleep(1500);
for (const s of ['mock-mes', 'mock-cmms', 'mock-aps']) {
  await p.locator('[data-testid=brief-systems] .datasource-chip', { hasText: s }).click(); await sleep(300);
}
await snap('r2-01-source');
await p.getByRole('button', { name: '다음 →' }).click(); await sleep(800);
await p.getByPlaceholder('새 스키마 이름 (선택, 예: 제조 운영 스키마)').fill('MES 설비 운영');
await snap('r2-02-target');
await p.getByRole('button', { name: '다음 →' }).click(); await sleep(800);
await p.locator('textarea').filter({ hasText: '' }).first().fill(INTENT).catch(async () => {
  await p.getByPlaceholder(/내부 감사 담당자가/).fill(INTENT); });
for (let i = 0; i < GQ.length; i++) {
  let inp = p.getByPlaceholder(`예: Golden Question ${i + 1}`);
  if (!(await inp.count())) { await p.locator('button', { hasText: /질문 추가|퀘스천 추가|\+/ }).first().click().catch(() => {}); await sleep(300); }
  inp = p.getByPlaceholder(`예: Golden Question ${i + 1}`);
  await inp.fill(GQ[i]);
}
for (let i = 0; i < GC.length; i++) {
  let inp = p.getByPlaceholder(`예: Golden Command ${i + 1}`);
  if (!(await inp.count())) { await p.locator('[data-testid=brief-golden-commands] .btn-inline-add').click(); await sleep(300); }
  inp = p.getByPlaceholder(`예: Golden Command ${i + 1}`);
  await inp.fill(GC[i]);
}
await sleep(500);
await snap('r2-03-intent');
const t = await pageText(p);
console.log('intent filled:', t.includes('과열'), 'GQ2:', t.includes(GQ[1]), 'GC2:', t.includes(GC[1]));
await p.getByRole('button', { name: '이 브리프로 구축 시작' }).click();
log('build started');
const start = Date.now();
let i = 0;
const timer = setInterval(async () => { i++; await p.screenshot({ path: `${OUT}/r2-build-${String(i).padStart(2, '0')}.png` }).catch(() => {}); }, 60000);
await waitAgent(p, 1800000);
clearInterval(timer);
log('build done secs', (Date.now() - start) / 1000);
await snap('r2-04-build-done');
console.log((await p.locator('body').innerText()).slice(-3000));
await b.close();
