// node scripts/evshot.mjs url out.png "js-to-run-in-page" waitMs [fullpage]
import { chromium } from '@playwright/test';
const [,, url, out, js = '', wait = '3000', full = ''] = process.argv;
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--use-gl=swiftshader'] });
const p = await b.newPage({ viewport: { width: +(process.env.W || 1440), height: +(process.env.H || 900) }, isMobile: +(process.env.W || 1440) < 700, hasTouch: +(process.env.W || 1440) < 700 });
const logs = []; p.on('console', (m) => { if (m.type() === 'error') logs.push(m.text().slice(0, 200)); }); p.on('pageerror', (e) => logs.push('pageerror ' + e.message));
await p.addInitScript((theme) => { sessionStorage.setItem('qveris.booted', '1'); sessionStorage.setItem('qveris.film', '1'); if (theme) localStorage.setItem('qveris.prefs.v1', JSON.stringify({ theme })); }, process.env.THEME || '');
await p.goto(url); await p.waitForTimeout(2500);
for (const step of js.split(';;').filter(Boolean)) { await p.evaluate(step); await p.waitForTimeout(1200); }
await p.waitForTimeout(+wait);
if (full) { await p.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); } scrollTo(0, 0); }); await p.waitForTimeout(800); }
await p.screenshot({ path: out, fullPage: !!full, timeout: 60000 });
console.log(logs.join('\n') || 'no errors'); await b.close();
