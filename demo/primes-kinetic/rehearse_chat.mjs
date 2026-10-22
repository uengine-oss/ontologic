// 리허설 — 커맨드만으로 반복 수주 처리 (질의·액션 채팅)
import { chromium, STUDIO, sleep, log, nav, waitAgent } from '../kinetic-mes/video2/lib.mjs';
const OUT = 'rehearsal';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
await p.goto(STUDIO, { waitUntil: 'networkidle' });
await nav(p, '질의·액션');
await p.locator('[title$="워크스페이스 펼치기"]').first().click().catch(() => {}); await sleep(300);
await p.locator('.sidebar-new').click().catch(() => {}); await sleep(300);
await p.locator('[title="워크스페이스 접기"]').click().catch(() => {}); await sleep(600);
const box = () => p.locator('textarea').last();
let n = 0;
async function say(text) {
  n++; await box().fill(text); const t = Date.now(); await box().press('Enter'); await waitAgent(p, 900000);
  const msgs = await p.locator('.msg-assistant, .message.assistant, [class*=assistant]').allInnerTexts().catch(() => []);
  const body = await p.locator('body').innerText();
  log(`#${n} (${((Date.now() - t) / 1000).toFixed(0)}s) ${text}`);
  console.log('---- AI ----\n' + body.split(text).pop().slice(0, 1800) + '\n');
  await p.screenshot({ path: `${OUT}/c${String(n).padStart(2, '0')}.png` });
}
async function approveLast() {
  const card = p.locator('[data-testid=kinetic-plan-card]').last();
  await card.locator('[data-testid=kinetic-approve]').click();
  await p.locator('.kplan-approved').last().waitFor({ timeout: 30000 }); log('승인 클릭'); await sleep(800);
}
await say('휠 허브 플랜지 단조 금형별 남은 타수는?');
await say('대성오토가 휠 허브 플랜지 1,200개를 10월 26일 납기로 주문했어. 수주 등록해 줘.');
await say('응, 실행해.');
await say('이 수주 때문에 부족한 원자재를 승인 업체에 발주해 줘.');
await say('응, 실행해.');
await say('이 수주의 단조 작업지시를 내 줘. 금형 수명이 모자라면 대안을 보여 주고 내가 고른 대로 진행해.');
await say('대체 금형으로 진행해 줘.');
if (await p.locator('[data-testid=kinetic-approve]').count()) { await approveLast(); await say('생산관리자 승인이 났어. 실행해.'); }
await say('방금 처리한 수주 건을 모두 취소해 줘.');
await b.close();
