// 온보딩 시연 공용 — 브라우저·검증 헬퍼
import { createRequire } from 'module';
import fs from 'fs';
const require = createRequire('/Users/uengine/ontologic/ontology-studio/package.json');
export const { chromium } = require('@playwright/test');
export const STUDIO = 'http://localhost:5183/';
export const sleep = ms => new Promise(r => setTimeout(r, ms));   // Node 타이머 — page.waitForTimeout 금지
const t0 = Date.now();
export const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s]`, ...a);

export async function pageText(page) {
  // 입력 칸 값은 innerText 에 없다 — 함께 본다
  return (await page.locator('body').innerText()) + '\n' +
    (await page.$$eval('input, textarea, select', els => els.map(e => e.value).join('\n')));
}

export async function nav(page, label) {
  await page.locator('.nav-item, nav button, aside button, a').filter({ hasText: label }).first().click();
  await sleep(1000);
}

export async function waitAgent(page, timeout = 900000) {
  await page.locator('.btn-stop').waitFor({ state: 'visible', timeout: 30000 }).catch(() => {});
  await page.locator('.btn-stop').waitFor({ state: 'detached', timeout });
  await sleep(1500);
}

export function writeJson(path, v) { fs.writeFileSync(path, JSON.stringify(v, null, 1)); }
