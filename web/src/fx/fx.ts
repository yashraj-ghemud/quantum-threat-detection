/* QVeris page FX (port of dashboard/web/fx.js to the app):
   spring-physics cursor with particle bursts, magnetic buttons, click ripples,
   3D tilt cards, scroll reveals and a scroll progress bar. Legacy WebGL scenes
   running in iframes forward their pointer through window.__qvFx (core.js
   bridgeCursor), so the cursor stays continuous across them. */

type Fx = { bridgeMove: (x: number, y: number) => void; bridgeDown: (x: number, y: number) => void; bridgeUp: () => void; bridgeHover: (v: number | boolean) => void };
declare global { interface Window { __qvFx?: Fx } }

const PALETTE = ['#8C84F0', '#6FA8F0', '#4FC3A1', '#E8B860', '#F4A77A'];
const INTERACTIVE = 'button, a, [role="tab"], [role="slider"], [role="option"], [role="switch"], select, input, textarea, label, summary, [data-cursor]';
const MAGNETIC = '.btn:not(.no-magnet), [data-magnetic]';
const TILT = '.qv-tilt';

let installed = false;
let cleanup: (() => void)[] = [];

export function installFx(opts: { cursor: boolean; reduced: boolean }) {
  uninstallFx();
  installed = true;
  const doc = document;
  const on = <K extends keyof DocumentEventMap>(t: K, fn: (e: DocumentEventMap[K]) => void, o: AddEventListenerOptions = { passive: true }) => {
    doc.addEventListener(t, fn as EventListener, o); cleanup.push(() => doc.removeEventListener(t, fn as EventListener, o));
  };
  const fine = matchMedia('(pointer: fine)').matches;
  const fx: Fx = { bridgeMove() {}, bridgeDown() {}, bridgeUp() {}, bridgeHover() {} };
  window.__qvFx = fx;
  cleanup.push(() => { if (window.__qvFx === fx) delete window.__qvFx; });

  // ------------------------------------------------------ scroll progress
  const bar = doc.createElement('div'); bar.id = 'qv-progress'; doc.body.appendChild(bar);
  cleanup.push(() => bar.remove());
  const onScroll = () => {
    const s = doc.scrollingElement || doc.documentElement;
    const max = s.scrollHeight - s.clientHeight;
    bar.style.transform = `scaleX(${max > 4 ? s.scrollTop / max : 0})`;
  };
  on('scroll', onScroll as any);

  // --------------------------------------------------------- reveal
  const io = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      const t = en.target as HTMLElement;
      const sib = t.parentElement ? Array.prototype.indexOf.call(t.parentElement.children, t) : 0;
      t.style.transitionDelay = Math.min(sib % 6, 5) * 55 + 'ms';
      t.classList.add('qv-in');
      io.unobserve(t);
    });
  }, { threshold: 0, rootMargin: '0px 0px -6% 0px' });
  const scan = (root: ParentNode) => {
    root.querySelectorAll?.('[data-reveal]').forEach((n) => {
      const el = n as HTMLElement;
      if (el.dataset.qvReveal) return;
      el.dataset.qvReveal = '1';
      if (opts.reduced) return;
      el.classList.add('qv-reveal');
      io.observe(el);
    });
  };
  const mo = new MutationObserver((muts) => muts.forEach((m) => m.addedNodes.forEach((n) => { if (n.nodeType === 1) scan((n as Element).parentElement || (n as Element)); })));
  mo.observe(doc.body, { childList: true, subtree: true });
  scan(doc.body);
  cleanup.push(() => { mo.disconnect(); io.disconnect(); });

  // ripple works even in reduced motion (it is feedback, not ambience)
  on('pointerdown', (e) => {
    const b = (e.target as Element)?.closest?.('.btn, button.chip') as HTMLElement | null;
    if (!b || opts.reduced) return;
    const rc = b.getBoundingClientRect(), s = Math.max(rc.width, rc.height) * 2.2;
    const rp = doc.createElement('span');
    rp.className = 'qv-ripple';
    rp.style.cssText = `width:${s}px;height:${s}px;left:${e.clientX - rc.left - s / 2}px;top:${e.clientY - rc.top - s / 2}px;`;
    if (getComputedStyle(b).position === 'static') b.style.position = 'relative';
    b.appendChild(rp);
    setTimeout(() => rp.remove(), 700);
  });
  if (opts.reduced) return;

  // ------------------------------------------------- magnetic + tilt
  let magnet: HTMLElement | null = null;
  const tilt = { el: null as HTMLElement | null, rx: 0, ry: 0, tx: 0, ty: 0 };
  on('pointermove', (e) => {
    if (e.pointerType !== 'mouse') return;
    const tgt = e.target as Element;
    const b = tgt?.closest?.(MAGNETIC) as HTMLElement | null;
    if (magnet && magnet !== b) { magnet.style.translate = ''; magnet = null; }
    if (b && !b.closest('.no-magnet-zone')) {
      magnet = b;
      const rc = b.getBoundingClientRect();
      const dx = e.clientX - (rc.left + rc.width / 2), dy = e.clientY - (rc.top + rc.height / 2);
      b.style.translate = `${dx * 0.16}px ${dy * 0.26 - 2}px`;
    }
    const t = tgt?.closest?.(TILT) as HTMLElement | null;
    if (tilt.el && tilt.el !== t) { tilt.el.style.transform = ''; tilt.el.classList.remove('qv-tilting'); tilt.el = null; tilt.rx = tilt.ry = 0; }
    if (!t) return;
    tilt.el = t; t.classList.add('qv-tilting');
    const rc = t.getBoundingClientRect();
    const px = (e.clientX - rc.left) / rc.width, py = (e.clientY - rc.top) / rc.height;
    const amp = Math.max(3, Math.min(10, 2400 / Math.max(rc.width, 1)));
    tilt.tx = (px - 0.5) * amp; tilt.ty = -(py - 0.5) * amp * 0.85;
    t.style.setProperty('--gx', px * 100 + '%'); t.style.setProperty('--gy', py * 100 + '%');
  });

  // ------------------------------------------------------------ cursor
  let dot: HTMLDivElement | null = null, ring: HTMLDivElement | null = null, canvas: HTMLCanvasElement | null = null, ctx: CanvasRenderingContext2D | null = null;
  const particles: { x: number; y: number; vx: number; vy: number; life: number; max: number; c: string; s: number; q: boolean }[] = [];
  const m = { x: innerWidth / 2, y: innerHeight / 2 }, r = { x: m.x, y: m.y, vx: 0, vy: 0 };
  const hover = { x: 0, v: 0, t: 0 }, press = { x: 0, v: 0, t: 0 };
  let visible = false, bridged = false, lastBridge = 0, busy = false;
  const useCursor = opts.cursor && fine;
  const el = (tag: string, id: string, css: string) => { const e = doc.createElement(tag); e.id = id; e.style.cssText = css; doc.body.appendChild(e); cleanup.push(() => e.remove()); return e; };
  const setVisible = (v: boolean) => { visible = v; if (dot && ring) { dot.style.opacity = v ? '1' : '0'; ring.style.opacity = v ? '1' : '0'; } };
  const move = (x: number, y: number, fromBridge: boolean) => {
    m.x = x; m.y = y;
    if (fromBridge) { bridged = true; lastBridge = performance.now(); } else if (performance.now() - lastBridge > 120) bridged = false;
    if (!visible) { r.x = x; r.y = y; setVisible(true); }
  };
  const down = (x: number, y: number) => {
    press.t = 1; press.v -= 6;
    for (let i = 0; i < 16; i++) {
      const a = Math.random() * Math.PI * 2, s = 90 + Math.random() * 260;
      particles.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 60, life: 0, max: 0.55 + Math.random() * 0.45,
        c: PALETTE[(Math.random() * PALETTE.length) | 0], s: 2 + Math.random() * 3.5, q: Math.random() < 0.3 });
    }
  };
  fx.bridgeMove = (x, y) => move(x, y, true);
  fx.bridgeDown = (x, y) => down(x, y);
  fx.bridgeUp = () => { press.t = 0; };
  fx.bridgeHover = (v) => { hover.t = v ? 1 : 0; };

  if (useCursor) {
    doc.documentElement.classList.add('qv-cursor');
    cleanup.push(() => doc.documentElement.classList.remove('qv-cursor'));
    dot = el('div', 'qv-dot', 'position:fixed;left:0;top:0;width:8px;height:8px;margin:-4px 0 0 -4px;border-radius:50%;background:var(--text-0);pointer-events:none;z-index:2147483646;opacity:0;transition:opacity .3s,background .3s;') as HTMLDivElement;
    ring = el('div', 'qv-ring', 'position:fixed;left:0;top:0;width:38px;height:38px;margin:-19px 0 0 -19px;border-radius:50%;border:1.5px solid rgba(140,132,240,.75);pointer-events:none;z-index:2147483645;opacity:0;transition:opacity .3s,border-color .3s,background .3s;background:rgba(140,132,240,.04);') as HTMLDivElement;
    canvas = el('canvas', 'qv-sparks', 'position:fixed;inset:0;pointer-events:none;z-index:2147483644;') as HTMLCanvasElement;
    ctx = canvas.getContext('2d');
    const size = () => { const d = Math.min(devicePixelRatio || 1, 2); canvas!.width = innerWidth * d; canvas!.height = innerHeight * d; ctx!.setTransform(d, 0, 0, d, 0, 0); };
    size(); addEventListener('resize', size); cleanup.push(() => removeEventListener('resize', size));
    on('pointermove', (e) => { if (e.pointerType === 'mouse') move(e.clientX, e.clientY, false); });
    on('pointerdown', (e) => { if (e.pointerType === 'mouse') down(e.clientX, e.clientY); });
    on('pointerup', () => { press.t = 0; });
    on('mouseleave' as any, () => setVisible(false));
    on('mouseover', (e) => {
      const t = e.target as Element;
      if (t && t.tagName === 'IFRAME' && !bridged) { setVisible(false); return; }
      if (t && t.tagName === 'CANVAS' && !t.closest('[data-cursor]')) { hover.t = 0; return; }
      hover.t = t?.closest?.(INTERACTIVE) ? 1 : 0;
      busy = !!t?.closest?.('[aria-busy="true"]');
    });
  }

  let last = performance.now(), raf = 0;
  const spring = (s: { x: number; v: number; t: number }, k: number, c: number, dt: number) => { s.v += (k * (s.t - s.x) - c * s.v) * dt; s.x += s.v * dt; };
  const loop = (now: number) => {
    raf = requestAnimationFrame(loop);
    const dt = Math.min(0.033, (now - last) / 1000); last = now;
    if (tilt.el) {
      const k = 1 - Math.exp(-dt * 14);
      tilt.rx += (tilt.tx - tilt.rx) * k; tilt.ry += (tilt.ty - tilt.ry) * k;
      tilt.el.style.transform = `perspective(900px) rotateX(${tilt.ry}deg) rotateY(${tilt.rx}deg) translateZ(4px)`;
    }
    if (!useCursor || !ring || !dot || !ctx) return;
    const k = 380, c = 30;
    r.vx += (k * (m.x - r.x) - c * r.vx) * dt; r.vy += (k * (m.y - r.y) - c * r.vy) * dt;
    r.x += r.vx * dt; r.y += r.vy * dt;
    spring(hover, 260, 22, dt); spring(press, 520, 26, dt);
    const speed = Math.hypot(r.vx, r.vy);
    const stretch = Math.min(speed / 2200, 0.45), ang = Math.atan2(r.vy, r.vx);
    const sc = 1 + hover.x * 0.75 - press.x * 0.25;
    ring.style.transform = `translate3d(${r.x}px,${r.y}px,0) rotate(${busy ? now / 300 : ang}rad) scale(${sc * (1 + stretch)},${sc * (1 - stretch * 0.6)})`;
    ring.style.borderStyle = busy ? 'dashed' : 'solid';
    ring.style.borderColor = hover.t ? 'rgba(111,168,240,.95)' : 'rgba(140,132,240,.75)';
    ring.style.background = hover.t ? 'rgba(111,168,240,.1)' : 'rgba(140,132,240,.04)';
    dot.style.transform = `translate3d(${m.x}px,${m.y}px,0) scale(${1 - hover.x * 0.5 + press.x * 0.6})`;
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.life += dt;
      if (p.life > p.max) { particles.splice(i, 1); continue; }
      p.vx *= 1 - 3.2 * dt; p.vy = p.vy * (1 - 3.2 * dt) + 520 * dt;
      p.x += p.vx * dt; p.y += p.vy * dt;
      const a = 1 - p.life / p.max;
      ctx.globalAlpha = a; ctx.fillStyle = p.c; ctx.strokeStyle = p.c;
      if (p.q) { ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(p.x, p.y, p.s * 1.8 * (1.4 - a), 0, 6.283); ctx.stroke(); }
      else { ctx.beginPath(); ctx.arc(p.x, p.y, p.s * a, 0, 6.283); ctx.fill(); }
    }
    ctx.globalAlpha = 1;
  };
  raf = requestAnimationFrame(loop);
  cleanup.push(() => cancelAnimationFrame(raf));
}

export function uninstallFx() {
  if (!installed) return;
  cleanup.forEach((f) => { try { f(); } catch { /* ignore */ } });
  cleanup = [];
  installed = false;
}
