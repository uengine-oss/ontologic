// 리허설 — 등록 시스템만 소스로 PriMES 온톨로지 구축 (골든 퀘스천·골든 커맨드)
import { chromium, STUDIO, sleep, log, pageText, nav, waitAgent } from '../kinetic-mes/video2/lib.mjs';
const OUT = 'rehearsal';
const INTENT = '영업·생산관리 담당자가 대화로 대성오토의 반복 주문을 처리한다. 수주를 등록하고, 그 수주 때문에 부족한 원자재를 승인 업체에 발주하고, 단조 작업지시를 내기 전에 금형 남은 수명을 확인해 모자라면 대안을 사람에게 묻고 고른 대로 작업지시를 발행하며 금형을 장착한다. 필요하면 처리한 건을 역순으로 취소한다.';
const GQ = ['휠 허브 플랜지 단조 금형별 남은 타수는?', '휠 허브 플랜지를 만드는 데 필요한 원자재와 공급업체는?'];
const GC = ['대성오토가 휠 허브 플랜지 1,200개를 10월 26일 납기로 주문했어. 수주 등록해 줘.',
  '이 수주 때문에 부족한 원자재를 승인 업체에 발주해 줘.',
  '이 수주의 단조 작업지시를 내 줘. 금형 수명이 모자라면 대안을 보여 주고 내가 고른 대로 진행해.',
  '방금 처리한 수주 건을 모두 취소해 줘.'];
export { INTENT, GQ, GC };
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
const snap = async n => { await p.screenshot({ path: `${OUT}/${n}.png` }); log(n); };
await p.goto(STUDIO, { waitUntil: 'networkidle' });
await nav(p, '온톨로지'); await sleep(1000);
for (const s of ['primes-sales', 'primes-purchase', 'primes-production', 'primes-mold', 'primes-masterdata', 'primes-equipment']) {
  await p.locator('[data-testid=brief-systems] .datasource-chip', { hasText: s }).click(); await sleep(200);
}
await snap('b01-source');
await p.getByRole('button', { name: '다음 →' }).click(); await sleep(600);
await p.getByPlaceholder('새 스키마 이름 (선택, 예: 제조 운영 스키마)').fill('PriMES 반복 수주');
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
await snap('b02-brief');
const t = await pageText(p);
console.log('filled', GC.every(c => t.includes(c)));
await p.getByRole('button', { name: '이 브리프로 구축 시작' }).click();
const t0 = Date.now(); let i = 0;
const timer = setInterval(() => { i++; p.screenshot({ path: `${OUT}/b-build-${String(i).padStart(2, '0')}.png` }).catch(() => {}); }, 90000);
await waitAgent(p, 3600000);
clearInterval(timer);
log('build secs', (Date.now() - t0) / 1000);
await snap('b03-done');
const rep = p.locator('[data-testid=build-report-commands]').last();
console.log('REPORT:', (await rep.count()) ? await rep.innerText() : 'NO REPORT');
await b.close();
