import { chromium } from '@playwright/test';
const [,, url = 'http://127.0.0.1:5173/playground', tab = 'Channel'] = process.argv;
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--use-gl=swiftshader'] });
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
await p.addInitScript(() => { sessionStorage.setItem('qveris.booted', '1'); });
p.on('pageerror', (e) => console.log('pageerror', e.message));
p.on('console', (m) => { if (m.type() === 'error') console.log('err', m.text().slice(0, 300)); });
await p.goto(url); await p.waitForTimeout(2500);
if (tab) await p.getByRole('tab', { name: tab, exact: true }).click({ timeout: 5000 });
if (process.argv[4]) { await p.getByRole('button', { name: process.argv[4] }).first().click({ timeout: 5000 }); await p.waitForTimeout(3000); await p.screenshot({ path: process.argv[5] }); }
for (let i = 0; i < 5; i++) {
  const t0 = Date.now();
  const r = await Promise.race([p.evaluate(() => new Promise((res) => requestAnimationFrame(() => res(1)))), new Promise((res) => setTimeout(() => res('timeout'), 5000))]);
  console.log('frame', i, r === 'timeout' ? 'TIMEOUT' : `${Date.now() - t0} ms`);
}
await b.close();
