import { chromium } from '@playwright/test';
const [,, url, tab] = process.argv;
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--use-gl=swiftshader'] });
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
await p.addInitScript(() => { sessionStorage.setItem('qveris.booted', '1'); });
p.on('pageerror', (e) => console.log('pageerror', e.message));
await p.goto(url); await p.waitForTimeout(2500);
const t0 = Date.now();
await p.evaluate((t) => { [...document.querySelectorAll('[role=tab]')].find((b) => b.textContent.trim() === t).click(); }, tab);
console.log('click dispatched in', Date.now() - t0, 'ms');
for (let i = 0; i < 5; i++) {
  const s = Date.now();
  const r = await Promise.race([p.evaluate(() => new Promise((res) => requestAnimationFrame(() => res(1)))), new Promise((res) => setTimeout(() => res('timeout'), 8000))]);
  console.log('frame', i, r === 'timeout' ? 'TIMEOUT' : `${Date.now() - s} ms`);
}
await b.close();
