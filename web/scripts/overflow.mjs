import { chromium } from '@playwright/test';
const [,, url, w = '1440', h = '900'] = process.argv;
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--use-gl=swiftshader'] });
const p = await b.newPage({ viewport: { width: +w, height: +h }, isMobile: +w < 700, hasTouch: +w < 700 });
await p.addInitScript(() => sessionStorage.setItem('qveris.booted', '1'));
await p.goto(url); await p.waitForTimeout(4500);
await p.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); } });
await p.waitForTimeout(1200);
const res = await p.evaluate(() => {
  const W = document.documentElement.clientWidth; const out = [];
  document.querySelectorAll('body *').forEach((el) => { const r = el.getBoundingClientRect(); if (r.right > W + 1 && r.width > 0) {
    let par = el.parentElement, clipped = false; while (par) { const o = getComputedStyle(par).overflowX; if ((o === 'auto' || o === 'hidden' || o === 'scroll') && par.getBoundingClientRect().right <= W + 1) { clipped = true; break; } par = par.parentElement; }
    if (!clipped) out.push(`${el.tagName.toLowerCase()}.${String(el.className?.baseVal ?? el.className).slice(0, 50)} right=${Math.round(r.right)} w=${Math.round(r.width)}`); } });
  return { W, sw: document.documentElement.scrollWidth, out: out.slice(0, 15) };
});
console.log(JSON.stringify(res, null, 1)); await b.close();
