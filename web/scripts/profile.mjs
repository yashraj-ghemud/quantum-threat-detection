import { chromium } from '@playwright/test';
const [,, url, tab] = process.argv;
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--use-gl=swiftshader'] });
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
await p.addInitScript(() => { sessionStorage.setItem('qveris.booted', '1'); });
await p.goto(url); await p.waitForTimeout(2500);
const cdp = await p.context().newCDPSession(p);
await cdp.send('Profiler.enable'); await cdp.send('Profiler.setSamplingInterval', { interval: 200 });
await p.evaluate((t) => { [...document.querySelectorAll('[role=tab]')].find((b) => b.textContent.trim() === t).click(); }, tab);
await cdp.send('Profiler.start'); await new Promise((r) => setTimeout(r, 4000));
const { profile } = await cdp.send('Profiler.stop');
const self = new Map(); const byId = new Map(profile.nodes.map((n) => [n.id, n]));
const dt = profile.timeDeltas; const counts = new Map();
profile.samples.forEach((id, i) => counts.set(id, (counts.get(id) || 0) + (dt[i] || 0)));
for (const [id, t] of counts) { const n = byId.get(id); const k = `${n.callFrame.functionName || '(anon)'} ${n.callFrame.url.split('/').slice(-1)[0]}:${n.callFrame.lineNumber}`; self.set(k, (self.get(k) || 0) + t); }
console.log([...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, 18).map(([k, t]) => `${(t / 1000).toFixed(0).padStart(6)} ms  ${k}`).join('\n'));
await b.close();
