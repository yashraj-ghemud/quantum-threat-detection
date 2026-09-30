// Usage: node scripts/flow.mjs <url> <w> <h> step1 step2 ...
// steps: click:<text> | clickSel:<css> | wait:<ms> | shot:<path> | fullshot:<path> | scroll:<px> | scrollall | fill:<css>=<text> | key:<key>
import { chromium } from '@playwright/test';
const [,, url, w = '1440', h = '900', ...steps] = process.argv;
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
const ctx = await browser.newContext({ viewport: { width: +w, height: +h }, deviceScaleFactor: 1, hasTouch: +w < 700, isMobile: +w < 700 });
const page = await ctx.newPage();
const logs = [];
page.on('console', (m) => { const t = m.text(); if (m.type() === 'error' || (m.type() === 'warning' && !/GPU stall|THREE.Clock|GL Driver/.test(t))) logs.push(`${m.type()}: ${t.slice(0, 300)}`); });
page.on('pageerror', (e) => logs.push(`pageerror: ${e.message}`));
await page.addInitScript(() => { try { sessionStorage.setItem('qveris.booted', '1'); } catch {} });
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
for (const s of steps) {
  const i = s.indexOf(':'); const cmd = i < 0 ? s : s.slice(0, i), arg = i < 0 ? '' : s.slice(i + 1);
  try {
    if (cmd === 'click') await page.getByText(arg, { exact: false }).first().click({ timeout: 8000 });
    else if (cmd === 'tab') await page.getByRole('tab', { name: arg, exact: true }).first().click({ timeout: 8000 });
    else if (cmd === 'btn') await page.getByRole('button', { name: arg }).first().click({ timeout: 8000 });
    else if (cmd === 'clickSel') await page.locator(arg).first().click({ timeout: 8000 });
    else if (cmd === 'wait') await page.waitForTimeout(+arg);
    else if (cmd === 'shot') await page.screenshot({ path: arg });
    else if (cmd === 'fullshot') { await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); } scrollTo(0, 0); }); await page.waitForTimeout(900); await page.screenshot({ path: arg, fullPage: true }); }
    else if (cmd === 'scroll') { await page.evaluate((y) => scrollTo(0, y), +arg); await page.waitForTimeout(700); }
    else if (cmd === 'fill') { const [sel, text] = arg.split('='); await page.locator(sel).first().fill(text); }
    else if (cmd === 'key') await page.keyboard.press(arg);
  } catch (e) { logs.push(`step ${s} failed: ${e.message.split('\n')[0]}`); }
}
console.log(logs.slice(0, 40).join('\n') || 'no console errors');
await browser.close();
