/* ==========================================================================
   QVeris page FX: runs in the Streamlit page itself (injected once by the
   story scene). Adds a spring-physics cursor with particle bursts, magnetic
   buttons, click ripples, 3D tilt cards, scroll reveals and a progress bar.
   Everything is skipped under prefers-reduced-motion.
   ========================================================================== */
(function () {
  if (window.__qvFx) return;
  var doc = document;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var fine = window.matchMedia('(pointer: fine)').matches;
  var fx = (window.__qvFx = {
    bridgeMove: function () {}, bridgeDown: function () {}, bridgeUp: function () {}, bridgeHover: function () {},
  });
  if (reduce) return;

  var PALETTE = ['#8C84F0', '#6FA8F0', '#4FC3A1', '#E8B860', '#F4A77A'];
  var INTERACTIVE = 'button, a, [role="tab"], [role="slider"], [role="option"], [data-baseweb="select"], input, textarea, label, summary, [data-testid="stMetric"], [data-testid="stExpander"] details > summary';

  // ------------------------------------------------------------ cursor ---
  var dot, ring, label, canvas, ctx, particles = [];
  var m = { x: innerWidth / 2, y: innerHeight / 2 }, r = { x: m.x, y: m.y, vx: 0, vy: 0 };
  var hover = { x: 0, v: 0, t: 0 }, press = { x: 0, v: 0, t: 0 }, visible = false, bridged = false, lastBridge = 0;

  function el(tag, id, css) { var e = doc.createElement(tag); e.id = id; e.style.cssText = css; doc.body.appendChild(e); return e; }
  function initCursor() {
    doc.documentElement.classList.add('qv-cursor');
    dot = el('div', 'qv-dot', 'position:fixed;left:0;top:0;width:8px;height:8px;margin:-4px 0 0 -4px;border-radius:50%;background:#1E2440;pointer-events:none;z-index:2147483646;opacity:0;transition:opacity .3s,background .3s;');
    ring = el('div', 'qv-ring', 'position:fixed;left:0;top:0;width:38px;height:38px;margin:-19px 0 0 -19px;border-radius:50%;border:1.5px solid rgba(140,132,240,.75);pointer-events:none;z-index:2147483645;opacity:0;transition:opacity .3s,border-color .3s,background .3s;background:rgba(140,132,240,.04);backdrop-filter:blur(1px);');
    canvas = el('canvas', 'qv-sparks', 'position:fixed;inset:0;pointer-events:none;z-index:2147483644;');
    ctx = canvas.getContext('2d');
    sizeCanvas();
    addEventListener('resize', sizeCanvas);
    doc.addEventListener('pointermove', function (e) { if (e.pointerType === 'mouse') move(e.clientX, e.clientY, false); }, { passive: true });
    doc.addEventListener('pointerdown', function (e) { if (e.pointerType === 'mouse') down(e.clientX, e.clientY); }, { passive: true });
    doc.addEventListener('pointerup', up, { passive: true });
    doc.addEventListener('mouseleave', function () { setVisible(false); });
    doc.addEventListener('mouseover', function (e) {
      var t = e.target;
      if (t && t.tagName === 'IFRAME' && !bridged) { setVisible(false); return; }
      hover.t = t && t.closest && t.closest(INTERACTIVE) ? 1 : 0;
    }, { passive: true });
    requestAnimationFrame(loop);
  }
  function sizeCanvas() { var d = Math.min(devicePixelRatio || 1, 2); canvas.width = innerWidth * d; canvas.height = innerHeight * d; ctx.setTransform(d, 0, 0, d, 0, 0); }
  function setVisible(v) { visible = v; if (dot) { dot.style.opacity = v ? 1 : 0; ring.style.opacity = v ? 1 : 0; } }
  function move(x, y, fromBridge) {
    m.x = x; m.y = y;
    if (fromBridge) { bridged = true; lastBridge = performance.now(); } else if (performance.now() - lastBridge > 120) bridged = false;
    if (!visible) { r.x = x; r.y = y; setVisible(true); }
  }
  function down(x, y) {
    press.t = 1; press.v -= 6;
    for (var i = 0; i < 16; i++) {
      var a = Math.random() * Math.PI * 2, s = 90 + Math.random() * 260;
      particles.push({ x: x, y: y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 60, life: 0, max: 0.55 + Math.random() * 0.45,
        c: PALETTE[(Math.random() * PALETTE.length) | 0], s: 2 + Math.random() * 3.5, q: Math.random() < 0.3 });
    }
  }
  function up() { press.t = 0; }
  fx.bridgeMove = function (x, y) { move(x, y, true); };
  fx.bridgeDown = function (x, y) { down(x, y); };
  fx.bridgeUp = up;
  fx.bridgeHover = function (v) { hover.t = v ? 1 : 0; };

  function spring(s, k, c, dt) { s.v += (k * (s.t - s.x) - c * s.v) * dt; s.x += s.v * dt; }
  var last = performance.now();
  function loop(now) {
    requestAnimationFrame(loop);
    var dt = Math.min(0.033, (now - last) / 1000); last = now;
    // Ring trails the pointer on a slightly under-damped spring.
    var k = 380, c = 30;
    r.vx += (k * (m.x - r.x) - c * r.vx) * dt; r.vy += (k * (m.y - r.y) - c * r.vy) * dt;
    r.x += r.vx * dt; r.y += r.vy * dt;
    spring(hover, 260, 22, dt); spring(press, 520, 26, dt);
    var speed = Math.sqrt(r.vx * r.vx + r.vy * r.vy);
    var stretch = Math.min(speed / 2200, 0.45), ang = Math.atan2(r.vy, r.vx);
    var sc = 1 + hover.x * 0.75 - press.x * 0.25;
    ring.style.transform = 'translate3d(' + r.x + 'px,' + r.y + 'px,0) rotate(' + ang + 'rad) scale(' + (sc * (1 + stretch)) + ',' + (sc * (1 - stretch * 0.6)) + ')';
    ring.style.borderColor = hover.t ? 'rgba(111,168,240,.95)' : 'rgba(140,132,240,.75)';
    ring.style.background = hover.t ? 'rgba(111,168,240,.1)' : 'rgba(140,132,240,.04)';
    dot.style.transform = 'translate3d(' + m.x + 'px,' + m.y + 'px,0) scale(' + (1 - hover.x * 0.5 + press.x * 0.6) + ')';
    // Click sparks: pastel particles with gravity and drag.
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    for (var i = particles.length - 1; i >= 0; i--) {
      var p = particles[i];
      p.life += dt;
      if (p.life > p.max) { particles.splice(i, 1); continue; }
      p.vx *= 1 - 3.2 * dt; p.vy = p.vy * (1 - 3.2 * dt) + 520 * dt;
      p.x += p.vx * dt; p.y += p.vy * dt;
      var a = 1 - p.life / p.max;
      ctx.globalAlpha = a; ctx.fillStyle = p.c; ctx.strokeStyle = p.c;
      if (p.q) { ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(p.x, p.y, p.s * 1.8 * (1.4 - a), 0, 6.283); ctx.stroke(); }
      else { ctx.beginPath(); ctx.arc(p.x, p.y, p.s * a, 0, 6.283); ctx.fill(); }
    }
    ctx.globalAlpha = 1;
    tiltStep(dt);
  }

  // ------------------------------------------- magnetic buttons + ripple ---
  var magnet = null;
  doc.addEventListener('pointermove', function (e) {
    var b = e.target && e.target.closest && e.target.closest('.stButton button, .stDownloadButton button, .stFormSubmitButton button');
    if (magnet && magnet !== b) { magnet.style.transform = ''; magnet = null; }
    if (!b) return;
    magnet = b;
    var rc = b.getBoundingClientRect();
    var dx = e.clientX - (rc.left + rc.width / 2), dy = e.clientY - (rc.top + rc.height / 2);
    b.style.transform = 'translate(' + dx * 0.18 + 'px,' + dy * 0.3 + 'px) translateY(-2px)';
  }, { passive: true });
  doc.addEventListener('pointerdown', function (e) {
    var b = e.target && e.target.closest && e.target.closest('button');
    if (!b) return;
    var rc = b.getBoundingClientRect(), s = Math.max(rc.width, rc.height) * 2.2;
    var rp = doc.createElement('span');
    rp.className = 'qv-ripple';
    rp.style.cssText = 'width:' + s + 'px;height:' + s + 'px;left:' + (e.clientX - rc.left - s / 2) + 'px;top:' + (e.clientY - rc.top - s / 2) + 'px;';
    if (getComputedStyle(b).position === 'static') b.style.position = 'relative';
    b.style.overflow = 'hidden';
    b.appendChild(rp);
    setTimeout(function () { rp.remove(); }, 700);
  }, { passive: true });

  // ---------------------------------------------------------- 3D tilt ---
  var TILT = '[data-testid="stMetric"], .qv-tilt';
  var tilt = { el: null, rx: 0, ry: 0, tx: 0, ty: 0, gx: 50, gy: 50 };
  doc.addEventListener('pointermove', function (e) {
    var t = e.target && e.target.closest && e.target.closest(TILT);
    if (tilt.el && tilt.el !== t) { tilt.el.style.transform = ''; tilt.el.classList.remove('qv-tilting'); tilt.el = null; tilt.rx = tilt.ry = 0; }
    if (!t) return;
    tilt.el = t; t.classList.add('qv-tilting');
    var rc = t.getBoundingClientRect();
    var px = (e.clientX - rc.left) / rc.width, py = (e.clientY - rc.top) / rc.height;
    tilt.tx = (px - 0.5) * 14; tilt.ty = -(py - 0.5) * 12; tilt.gx = px * 100; tilt.gy = py * 100;
  }, { passive: true });
  function tiltStep(dt) {
    if (!tilt.el) return;
    var k = 1 - Math.exp(-dt * 14);
    tilt.rx += (tilt.tx - tilt.rx) * k; tilt.ry += (tilt.ty - tilt.ry) * k;
    tilt.el.style.transform = 'perspective(800px) rotateX(' + tilt.ry + 'deg) rotateY(' + tilt.rx + 'deg) translateZ(6px)';
    tilt.el.style.setProperty('--gx', tilt.gx + '%'); tilt.el.style.setProperty('--gy', tilt.gy + '%');
  }

  // ------------------------------------------------------ scroll reveal ---
  var REVEAL = '[data-testid="stElementContainer"], [data-testid="stHorizontalBlock"], [data-testid="stExpander"], [data-testid="stTabs"]';
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      var t = en.target;
      var sib = t.parentElement ? Array.prototype.indexOf.call(t.parentElement.children, t) : 0;
      t.style.transitionDelay = Math.min(sib % 6, 5) * 55 + 'ms';
      t.classList.add('qv-in');
      io.unobserve(t);
    });
  }, { threshold: 0, rootMargin: '0px 0px -6% 0px' }); // any overlap: tall blocks must reveal too
  function scan(root) {
    var list = (root.querySelectorAll ? root.querySelectorAll(REVEAL) : []);
    Array.prototype.forEach.call(list, function (n) {
      if (n.dataset.qvReveal) return;
      n.dataset.qvReveal = '1';
      // Never transform an ancestor of an iframe: it would break the hero's
      // sticky/fixed positioning and WebGL hit-testing.
      if (n.querySelector('iframe') || n.closest('.qv-hero-wrap') || n.classList.contains('qv-hero-wrap')) return;
      n.classList.add('qv-reveal');
      io.observe(n);
    });
  }
  new MutationObserver(function (muts) {
    muts.forEach(function (mu) { mu.addedNodes.forEach(function (n) { if (n.nodeType === 1) scan(n.parentElement || n); }); });
  }).observe(doc.body, { childList: true, subtree: true });
  scan(doc.body);

  // --------------------------------------------------- scroll progress ---
  var bar = el('div', 'qv-progress', '');
  function onScroll(e) {
    var s = e && e.target && e.target.scrollHeight ? e.target : doc.scrollingElement;
    // Only the page's main scroller drives the bar, not tables or code blocks.
    if (!s || s.scrollHeight <= s.clientHeight + 4 || s.clientHeight < innerHeight * 0.6) return;
    bar.style.transform = 'scaleX(' + (s.scrollTop / (s.scrollHeight - s.clientHeight)) + ')';
  }
  doc.addEventListener('scroll', onScroll, true);

  if (fine) initCursor();
})();
