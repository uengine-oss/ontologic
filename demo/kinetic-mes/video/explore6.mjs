import { createRequire } from 'module';
const require = createRequire('/Users/uengine/ontologic/ontology-studio/package.json');
const { chromium } = require('@playwright/test');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
async function waitAgent() {
  await p.locator('.btn-stop').waitFor({ state: 'visible', timeout: 30000 }).catch(() => {});
  await p.locator('.btn-stop').waitFor({ state: 'detached', timeout: 600000 });
  await sleep(1500);
}
await p.goto('http://localhost:5183/', { waitUntil: 'networkidle' });
await p.locator('text=액션 실행').first().click();
await sleep(800);
// 새 대화로 시작 — 접힌 사이드바를 펴서 + 를 누르고 다시 접는다
await p.locator('[title$="워크스페이스 펼치기"]').first().click();
await sleep(500);
await p.locator('.sidebar-new').click();
await sleep(500);
await p.locator('[title="워크스페이스 접기"]').click().catch(()=>{});
await sleep(800);
const box = p.locator('textarea').last();
await box.fill('온도가 80도를 넘는 설비를 모두 점검 모드로 바꿔 주세요. 사유는 냉각수 라인 이상에 따른 과열 점검입니다.');
let t0 = Date.now(); await box.press('Enter'); await waitAgent(); console.log('plan secs', (Date.now() - t0) / 1000);
const card = p.locator('[data-testid=kinetic-plan-card]').last();
await card.waitFor({ timeout: 60000 }); await sleep(1500);
await card.screenshot({ path: 'explore/30-card.png' });
await card.locator('[data-testid=kinetic-approve]').click();
await p.locator('.kplan-approved').last().waitFor({ timeout: 30000 });
await sleep(1000); await card.screenshot({ path: 'explore/31-card-approved.png' });
await box.fill('공장장 승인이 났습니다. 실행해 주세요.');
t0 = Date.now(); await box.press('Enter'); await waitAgent(); console.log('exec secs', (Date.now() - t0) / 1000);
const run = p.locator('[data-testid=kinetic-run]').last();
await run.waitFor({ timeout: 60000 }).catch(e => console.log('no run card', e.message));
await sleep(3000);
await p.screenshot({ path: 'explore/32-run.png' });
if (await run.count()) { await run.scrollIntoViewIfNeeded(); await p.locator('[data-testid=kinetic-plan-card]').last().screenshot({ path: 'explore/33-run-card.png' }); }
console.log((await p.locator('.chat-messages, main').first().innerText()).slice(-1200));
await b.close();
