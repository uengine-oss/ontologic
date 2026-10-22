// 리허설 3 — 질의·액션: 질문 → 커맨드 → 승인 → 실행 → 취소(역순 보상)
import { chromium, STUDIO, sleep, log, nav, waitAgent } from './lib.mjs';
const OUT = 'rehearsal';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
const snap = async n => { await p.screenshot({ path: `${OUT}/${n}.png` }); log(n); };
await p.goto(STUDIO, { waitUntil: 'networkidle' });
await nav(p, '질의·액션');
await p.locator('[title$="워크스페이스 펼치기"]').first().click().catch(() => {});
await sleep(400);
await p.locator('.sidebar-new').click().catch(() => {});
await sleep(400);
await p.locator('[title="워크스페이스 접기"]').click().catch(() => {});
await sleep(800);
const box = p.locator('textarea').last();
async function ask(text, name) {
  await box.fill(text); const t = Date.now(); await box.press('Enter'); await waitAgent(p);
  log(name, 'secs', (Date.now() - t) / 1000); await snap(name);
}
await ask('1공장에서 온도가 80도를 넘는 설비는?', 'r3-01-question');
await ask('온도가 80도를 넘는 설비를 모두 점검 모드로 바꿔 줘. 사유는 냉각수 라인 이상에 따른 과열 점검.', 'r3-02-plan');
const card = p.locator('[data-testid=kinetic-plan-card]').last();
await card.waitFor({ timeout: 60000 });
console.log('PLAN CARD:', (await card.innerText()).slice(0, 700));
await card.locator('[data-testid=kinetic-approve]').click();
await p.locator('.kplan-approved').last().waitFor({ timeout: 30000 }); await sleep(800);
await snap('r3-03-approved');
await ask('공장장 승인이 났습니다. 실행해 주세요.', 'r3-04-run');
console.log('RUN CARD:', (await p.locator('[data-testid=kinetic-plan-card]').last().innerText()).slice(0, 1200));
await ask('방금 점검 전환을 취소해 줘. 냉각수 라인이 복구됐어.', 'r3-05-cancel');
const last = p.locator('[data-testid=kinetic-plan-card]').last();
console.log('AFTER CANCEL CARD:', (await last.innerText()).slice(0, 2000));
console.log('LAST AI:', (await p.locator('body').innerText()).slice(-1500));
await b.close();
