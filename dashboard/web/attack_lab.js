/* ==========================================================================
   QVeris Attack Lab v2: a persistent, data-driven scene
   --------------------------------------------------------------------------
   The iframe is built once and never reloads. Every Streamlit rerun
   publishes { config, result } on the data bus (see _web.publish):

     config   what the widgets say right now (attack type, intensity,
              signature length, shots, seed, message, digest)
     result   the last measured run, with the config it was run with

   While config differs from the last result, the scene shows the CONFIGURED
   attack using the exact rules in src/attacks/*.py (theory, clearly
   labelled). When a new result arrives it plays the MEASURED film: the real
   per-element outcomes, shot counts, anomaly score against the real
   thresholds, the real evidence and the real verdict (a miss plays as a miss).
   See docs/animation_storyboard.md section 6.1.
   ========================================================================== */

const CH = QV.channel || 'lab';
const KMAX = 24;
const F = { START: 0, STREAM: 1.0, MEASURE: 5.2, DETECT: 7.6, VERDICT: 9.2 };
const TYPE_NAMES = {
  NONE: 'legitimate session', FORGERY: 'forgery', IMPERSONATION: 'impersonation', REPLAY: 'replay',
  UNAUTHORIZED_VERIFICATION: 'intercept-resend', CHANNEL_MANIPULATION: 'channel manipulation',
};

// ---- what each attack does, straight from src/attacks/*.py -----------------
function theory(c) {
  const n = c.n, I = +c.intensity, k = Math.max(0, Math.round(n * I));
  switch (c.type) {
    case 'FORGERY': return { k, lines: [`k = round(n·I) = round(${n}·${I.toFixed(2)}) = ${k} elements substituted`,
      'forged states stay pure (|b| = 1) but point the wrong way', `expected mismatch ≈ k/2n = ${(k / 2 / n).toFixed(3)}`] };
    case 'IMPERSONATION': return { k, lines: [`k = round(n·I) = ${k} elements signed with Mallory’s key`,
      'genuine eigenstates, but from the wrong key table', `expected mismatch ≈ k/2n = ${(k / 2 / n).toFixed(3)}`] };
    case 'REPLAY': return { k: 0, lines: ['quantum states identical to the recorded session: 0 extra mismatches',
      `staleness ∝ I · sequence offset = max(1, int(10·I)) = ${Math.max(1, Math.floor(10 * I))}`,
      I >= 0.5 ? 'I ≥ 0.5: cross-message replay (message id changed)' : 'I < 0.5: same-message replay'] };
    case 'UNAUTHORIZED_VERIFICATION': return { k, lines: [`k = round(n·I) = ${k} elements intercepted and re-sent`,
      'Eve guesses the basis: wrong 2/3 of the time, and half of those flip', `expected mismatch ≈ I/3 = ${(I / 3).toFixed(3)} + access-control check`] };
    case 'CHANNEL_MANIPULATION': return { k: n, lines: [`every element depolarized with p = I = ${I.toFixed(2)}`,
      `Bloch length → 1 − p = ${(1 - I).toFixed(2)} · purity → (1 + (1−p)²)/2 = ${((1 + (1 - I) ** 2) / 2).toFixed(3)}`,
      'majority vote over shots still reads the right eigenvalue until p ≈ 1'] };
    default: return { k: 0, lines: ['baseline channel: depolarizing p = 0.02 on every session',
      'Bloch length 0.98: the detector must beat this imperfection', 'expected: all elements verify'] };
  }
}

const cfgKey = (c) => (c ? [c.type, (+c.intensity).toFixed(2), c.n, c.shots || '', c.seed || '', c.message || ''].join('|') : '');
function hash(i, s = 0) { const x = Math.sin((i + 1) * 12.9898 + s * 78.233) * 43758.5453; return x - Math.floor(x); }

(async function main() {
  await fontsReady();
  const $ = (id) => document.getElementById(id);
  const view = $('view');
  const stage = createStage($('stage'), { fogNear: 30, fogFar: 115, maxDpr: 1.5 });
  const { scene, camera } = stage;
  bridgeCursor();
  const bus = makeBus(CH);
  $('title').textContent = QV.title || 'ATTACK LAB';

  // ---------------------------------------------------------------- world --
  const dust = makeDust(stage, 600, [54, 14, 40], 8);
  scene.add(dust.points);
  const alice = makeStation(PAL.lav, 'ALICE', 'signer');
  const bob = makeStation(PAL.mint, 'BOB', 'verifier');
  alice.group.position.set(-8, 0, 0); bob.group.position.set(8, 0, 0);
  scene.add(alice.group, bob.group);
  const OA = V3(-8, alice.orbY, 0), OB = V3(8, bob.orbY, 0);
  const curve = new THREE.CatmullRomCurve3([OA, V3(-4.5, 3.25, 0.3), V3(0, 3.55, 0), V3(4.5, 3.25, -0.3), OB]);
  const fiber = makeFiber(curve);
  scene.add(fiber.group);
  const eve = makeEve(stage);
  scene.add(eve.group);
  const EVE_POS = V3(0, 1.3, 3.0);
  const mallory = makeStation(PAL.coral, 'MALLORY', 'poses as alice');
  mallory.group.position.set(-5, -4.2, 5.2);
  scene.add(mallory.group);
  const MO = V3(-5, mallory.orbY, 5.2);
  const mCurve = new THREE.CatmullRomCurve3([MO, V3(-4, 3.6, 3), curve.getPoint(0.3)]);
  const mFiber = makeFiber(mCurve, { radius: 0.05, color: PAL.coral });
  scene.add(mFiber.group);
  const eveBloch = makeBloch(0.42, { color: PAL.coral, arrowColor: PAL.coral });
  scene.add(eveBloch);
  let card = makeCard('', '0'.repeat(64));
  scene.add(card.group);
  const fog = makePoints(stage, 320, { size: 0.1 });
  const FR = rng(4), fogBase = [];
  for (let i = 0; i < 320; i++) {
    fogBase.push({ u: FR(), r: 0.2 + FR() * 1.1, a: FR() * 6.28, s: 0.5 + FR() * 1.5 });
    const c = new THREE.Color(i % 2 ? PAL.coral : PAL.peach);
    fog.col.set([c.r, c.g, c.b], i * 3); fog.sz[i] = 0.6 + FR();
  }
  scene.add(fog.points);

  // Free particle emitter for one-off events (swaps, collapses, arrivals).
  const EMN = 700;
  const EM = makePoints(stage, EMN, { size: 0.09 });
  scene.add(EM.points);
  const emP = [];
  function emit(p, color, count = 14, speed = 2.2, life = 0.9, grav = 3) {
    const c = new THREE.Color(color);
    for (let i = 0; i < count && emP.length < EMN; i++) {
      const d = V3(Math.random() - 0.5, Math.random() - 0.3, Math.random() - 0.5).normalize().multiplyScalar(speed * (0.4 + Math.random()));
      emP.push({ p: p.clone(), v: d, c, life: 0, max: life * (0.6 + Math.random() * 0.6), g: grav });
    }
  }
  function stepEmitter(dt) {
    for (let i = emP.length - 1; i >= 0; i--) {
      const e = emP[i]; e.life += dt;
      if (e.life > e.max) { emP.splice(i, 1); continue; }
      e.v.y -= e.g * dt; e.v.multiplyScalar(1 - 1.5 * dt); e.p.addScaledVector(e.v, dt);
    }
    for (let i = 0; i < EMN; i++) {
      const e = emP[i];
      if (!e) { EM.alpha[i] = 0; continue; }
      EM.pos[i * 3] = e.p.x; EM.pos[i * 3 + 1] = e.p.y; EM.pos[i * 3 + 2] = e.p.z;
      EM.col[i * 3] = e.c.r; EM.col[i * 3 + 1] = e.c.g; EM.col[i * 3 + 2] = e.c.b;
      EM.alpha[i] = 0.9 * (1 - e.life / e.max);
    }
    EM.commit();
  }

  // ---- qubit stream + Bob's measurement rack (rebuilt when n changes) -----
  const qubits = [], ghosts = [], slots = [];
  const rackGroup = new THREE.Group();
  scene.add(rackGroup);
  const RAINN = 900;
  const RAIN = makePoints(stage, RAINN, { size: 0.06 });
  scene.add(RAIN.points);
  let K = 0;
  function slotPos(i, k) {
    const th = Math.PI * (0.3 + (k > 1 ? i / (k - 1) : 0.5) * 0.62);
    return V3(8 + Math.cos(th) * 3.6, 0, Math.sin(th) * 3.6);
  }
  const plinthGeo = new THREE.CylinderGeometry(0.22, 0.27, 0.16, 24);
  const tubeGeo = new THREE.CylinderGeometry(0.075, 0.075, 1, 16, 1, true);
  const fillGeo = new THREE.CylinderGeometry(0.06, 0.06, 1, 12);
  const glassMat = new THREE.MeshPhysicalMaterial({ color: 0xEEF1FA, transparent: true, opacity: 0.35, roughness: 0.05, clearcoat: 1, depthWrite: false, side: THREE.DoubleSide });
  function buildRack(k) {
    for (const q of qubits.concat(ghosts)) scene.remove(q);
    qubits.length = 0; ghosts.length = 0;
    while (rackGroup.children.length) rackGroup.remove(rackGroup.children[0]);
    slots.length = 0;
    K = k;
    for (let i = 0; i < k; i++) {
      const p = slotPos(i, k);
      const g = new THREE.Group();
      g.position.copy(p);
      const plinth = new THREE.Mesh(plinthGeo, MAT.ceramic(0xE9E8F6));
      plinth.position.y = 0.08; plinth.castShadow = true; plinth.receiveShadow = true;
      const tubes = [-0.12, 0.12].map((dx) => { const t = new THREE.Mesh(tubeGeo, glassMat); t.position.set(dx, 0.7, 0); return t; });
      const fills = [PAL.mint, PAL.coral].map((c, j) => { const f = new THREE.Mesh(fillGeo, MAT.glow(c, 0.5)); f.position.set(j ? 0.12 : -0.12, 0.2, 0); f.scale.y = 0.001; return f; });
      const tag = new THREE.Sprite(MAT.sprite(ketTexture('|0>'), 0.9));
      tag.scale.set(0.42, 0.25, 1); tag.position.y = 2.15;
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.025, 8, 48), MAT.glow(PAL.mint, 1.5));
      ring.rotation.x = Math.PI / 2; ring.position.y = 0.18;
      g.add(plinth, ...tubes, ...fills, tag, ring);
      rackGroup.add(g);
      slots.push({ g, fills, tag, ring, p });
      const q = makeQubit(0.24, PAL.sky, PAL.lav);
      scene.add(q); qubits.push(q);
      const gq = makeQubit(0.2, PAL.coral, PAL.coral);
      gq.userData.shell.material.opacity = 0.14;
      scene.add(gq); ghosts.push(gq);
    }
  }

  // ---- verdict machinery ---------------------------------------------------
  const cage = makeCage(PAL.mint, 1.9);
  scene.add(cage.group);
  const NSH = 170;
  const shardMesh = new THREE.InstancedMesh(new THREE.TetrahedronGeometry(0.15, 0),
    new THREE.MeshPhysicalMaterial({ color: PAL.obsidian, metalness: 0.55, roughness: 0.2, clearcoat: 1, emissive: PAL.coral, emissiveIntensity: 1.2 }), NSH);
  shardMesh.castShadow = true; shardMesh.frustumCulled = false; shardMesh.visible = false;
  scene.add(shardMesh);
  const shards = [];
  const embers = makeBurst(stage, 420, PAL.coral, 31, 9);
  const embers2 = makeBurst(stage, 260, PAL.gold, 32, 6);
  scene.add(embers.points, embers2.points);
  const pillar = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 40, 32, 1, true),
    new THREE.MeshBasicMaterial({ color: PAL.mint, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
  scene.add(pillar);
  const shockF = makeShockwave(PAL.mint); shockF.rotation.x = -Math.PI / 2; scene.add(shockF);
  const shockV = makeShockwave(PAL.coral); scene.add(shockV);
  const flash = makeFlash(PAL.mint); scene.add(flash);
  const beamMat = MAT.glow(PAL.mint, 3.5);
  const beams = [];
  for (let i = 0; i < KMAX; i++) { const b = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 1, 8), beamMat); b.visible = false; scene.add(b); beams.push(b); }
  const beacon = makeShockwave(PAL.peach); scene.add(beacon);
  const seal = makeGlyph('✓', { size: 1.4, font: `700 110px ${FONT_HEAD}`, color: CSS.mint, ring: CSS.mint });
  scene.add(seal);
  const doc = makeDocCard(3.8, 2.5);
  scene.add(doc.mesh);
  const gauge = makeGauge(1.1);
  gauge.group.position.set(8.4, 5.9, 0.6);
  scene.add(gauge.group);

  // ---- camera ----------------------------------------------------------------
  const controls = new OrbitControls(camera, stage.renderer.domElement);
  Object.assign(controls, { enableDamping: true, dampingFactor: 0.06, enableZoom: false, enablePan: false, minPolarAngle: 0.25, maxPolarAngle: 1.45 });
  let userCam = false;
  controls.addEventListener('start', () => { userCam = true; $('hint').classList.add('used'); });
  const camBase = { pos: V3(0, 8, 22), tgt: V3(0, 2.5, 0), fov: 36 };
  function camTo(pos, tgt, fov, dt, k = 2.2) {
    const a = 1 - Math.exp(-dt * k);
    camBase.pos.lerp(pos, a); camBase.tgt.lerp(tgt, a); camBase.fov += (fov - camBase.fov) * a;
  }

  // ---- state -----------------------------------------------------------------
  let cfg = { type: 'NONE', intensity: 0, n: 8, shots: 128, seed: 42, message: 'transfer 100 to bob', digest: '' };
  let res = null, resKey = '', filmT = -1, lastResId = null;
  const S = { aggro: new Spring(0, 60, 0.7), size: new Spring(0.5, 60, 0.6), wob: new Spring(0, 40, 0.8) };
  let plan = [];       // per visual slot: {label, dir, affected, rDir, rLen, match, pp, pm}
  let destroy = null;  // live state of the capture sequence
  let evTyped = -1;
  const slowS = new Spring(1, 90, 1);
  const isMeasured = () => !!res && resKey === cfgKey(cfg) && filmT >= 0;

  const eigenDir = (label) => blochToScene(EIGEN[label] || EIGEN['|+>']).normalize();
  // Build the per-slot plan from the config (theory) or the result (measured).
  function buildPlan(measured) {
    const c = measured ? res.config : cfg;
    const n = c.n, k = Math.min(n, KMAX), th = theory(c);
    const els = measured && res.elements && res.elements.length ? res.elements : null;
    const out = [];
    for (let i = 0; i < k; i++) {
      const idx = Math.floor((i * n) / k); // each slot stands for n/k elements
      const e = els ? els[idx] : null;
      const label = e ? e.label : EIGEN_LABELS[Math.floor(hash(idx, c.seed || 1) * 6)];
      const dir = eigenDir(label);
      const affected = c.type === 'CHANNEL_MANIPULATION' ? true
        : c.type === 'REPLAY' || c.type === 'NONE' ? false
        : hash(idx, 7 + (c.seed || 0)) < th.k / n;
      const wrongLabel = EIGEN_LABELS[(EIGEN_LABELS.indexOf(label) + 1 + Math.floor(hash(idx, 3) * 5)) % 6];
      let rDir = dir.clone(), rLen = c.type === 'CHANNEL_MANIPULATION' ? 1 - c.intensity : 0.98;
      if (affected && (c.type === 'FORGERY' || c.type === 'IMPERSONATION')) rDir = eigenDir(wrongLabel);
      if (affected && c.type === 'UNAUTHORIZED_VERIFICATION' && hash(idx, 5) < 2 / 3) rDir = eigenDir(wrongLabel);
      let pp = clamp((1 + rDir.dot(dir) * rLen) / 2, 0, 1), match = pp >= 0.5;
      if (e) {
        match = !!e.match; pp = e.p0 != null ? e.p0 : pp;
        rLen = Math.sqrt(Math.max(2 * (e.purity ?? 1) - 1, 0));
        if (!match && rDir.dot(dir) > 0.5) rDir = eigenDir(wrongLabel);
        if (match) rDir = dir.clone();
      }
      out.push({ label, dir, affected: affected || (!!e && !match), rDir, rLen, match, pp, pm: 1 - pp });
    }
    if (measured && !els) { // spread the measured mismatch count over the affected slots first
      const mis = Math.round((res.mismatch_rate || 0) * k);
      const order = out.map((o, i) => [o.affected ? 0 : 1, hash(i, 9), i]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map((x) => x[2]);
      out.forEach((o) => { o.match = true; o.pp = 0.97; o.pm = 0.03; });
      order.slice(0, mis).forEach((i) => { const o = out[i]; o.match = false; o.affected = true; o.pp = 0.28; o.pm = 0.72; if (o.rDir.dot(o.dir) > 0.5) o.rDir = o.dir.clone().negate(); });
    }
    return out;
  }

  function onData(d) {
    if (d.config) cfg = Object.assign({}, cfg, d.config);
    if (d.result && d.result.id !== lastResId) {
      res = d.result; lastResId = res.id; resKey = cfgKey(res.config);
      filmT = 0; destroy = null; evTyped = -1; userCam = false; $('hint').classList.remove('used');
    } else if (!d.result) { res = null; resKey = ''; filmT = -1; }
    const c = isMeasured() ? res.config : cfg;
    const k = Math.min(c.n, KMAX);
    if (k !== K) buildRack(k);
    plan = buildPlan(isMeasured());
    renderHud();
  }
  let cardKey = '';
  function syncCard() {
    const c = isMeasured() ? res.config : cfg;
    const key = (c.message || '') + '|' + (c.digest || '') + '|' + c.type;
    if (key === cardKey) return;
    cardKey = key;
    scene.remove(card.group);
    card = makeCard(c.message || '', (c.digest || '').padEnd(64, '·'));
    card.group.scale.setScalar(0.6);
    card.group.position.set(-8, 5.3, 0.6);
    card.draw((c.message || '').length, c.digest ? 1 : 0, 1, '');
    scene.add(card.group);
  }

  // ---------------------------------------------------------------- HUD ----
  const fmt = (x, d = 4) => (x == null || isNaN(x) ? 'n/a' : Number(x).toFixed(d));
  function renderHud() {
    const m = isMeasured();
    const c = m ? res.config : cfg;
    $('sub').textContent = `${TYPE_NAMES[c.type] || c.type}${c.type !== 'NONE' ? ` · I = ${(+c.intensity).toFixed(2)}` : ''} · n = ${c.n}`;
    $('theory').classList.toggle('dim', m);
    $('th-head').textContent = m ? 'RULES OF THIS RUN' : res ? 'CONFIG CHANGED · run it to measure' : 'CONFIGURED · theory, not measured yet';
    $('th-lines').innerHTML = theory(c).lines.map((l) => `<div>${l}</div>`).join('') +
      (c.n > KMAX ? `<div class="note">${KMAX} slots shown, each ≈ ${(c.n / KMAX).toFixed(1)} elements</div>` : '');
    $('metrics').classList.toggle('on', !!res);
    $('replay').style.display = res ? '' : 'none';
    if (!res) return;
    const scale = Math.max(res.anomaly || 0, res.critical || 0, res.threshold || 0, 1e-6) * 1.25;
    meter('m-anom', res.anomaly, scale, [[res.threshold, CSS.peach], [res.critical, CSS.coral]].filter((x) => x[0] != null));
    meter('m-mis', res.mismatch_rate, 1, []);
    meter('m-ver', res.verification, 1, []);
    $('m-stale').textContent = m ? '' : 'last measured run · config has changed since';
    const V = verdictOf(res), vEl = $('verdict');
    vEl.className = 'verdict ' + { THREAT: 'bad', SUSPICIOUS: 'warn', CLEAR: 'ok', MISSED: 'miss' }[V] + (m ? '' : ' show');
    vEl.querySelector('b').textContent = res.classification || '—';
    vEl.querySelector('span').textContent = { THREAT: 'attack detected and contained', SUSPICIOUS: 'flagged for review', CLEAR: 'session verified', MISSED: 'attack passed undetected' }[V];
    if (!m) $('evidence').textContent = [res.reason].concat(res.evidence || []).filter(Boolean).join('  ·  ').slice(0, 260);
  }
  function meter(id, v, max, marks) {
    const el = $(id);
    el.querySelector('b').textContent = fmt(v, 4);
    el.dataset.v = v == null ? 0 : clamp(v / max);
    el.querySelector('.m').innerHTML = marks.map(([x, c]) => `<i style="left:${clamp(x / max) * 100}%;background:${c}"></i>`).join('');
  }
  function verdictOf(r) {
    const cls = (r.classification || '').toUpperCase();
    if (cls === 'THREAT') return 'THREAT';
    if (cls === 'SUSPICIOUS') return 'SUSPICIOUS';
    return r.config.type !== 'NONE' ? 'MISSED' : 'CLEAR';
  }
  $('replay').addEventListener('click', () => {
    if (!res) return;
    cfg = Object.assign({}, cfg, res.config);
    filmT = 0; destroy = null; evTyped = -1; userCam = false;
    const k = Math.min(res.config.n, KMAX); if (k !== K) buildRack(k);
    plan = buildPlan(true); renderHud();
  });
  const pills = [...document.querySelectorAll('.pill')];

  // Hover: name what is under the cursor, with its real values.
  const tip = $('tip'), ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  let mouse = null;
  stage.renderer.domElement.addEventListener('pointermove', (e) => { const r = stage.renderer.domElement.getBoundingClientRect(); mouse = { x: e.clientX - r.left, y: e.clientY - r.top, w: r.width, h: r.height }; });
  stage.renderer.domElement.addEventListener('pointerleave', () => { mouse = null; tip.classList.remove('on'); });
  function hover() {
    if (!mouse) return;
    ndc.set((mouse.x / mouse.w) * 2 - 1, -(mouse.y / mouse.h) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    let html = '';
    const slotHit = ray.intersectObjects(slots.map((s) => s.g), true)[0];
    if (slotHit) {
      const i = slots.findIndex((s) => { let o = slotHit.object; while (o) { if (o === s.g) return true; o = o.parent; } return false; });
      const P = plan[i], c = isMeasured() ? res.config : cfg;
      if (P) html = `<b>Element ${Math.floor((i * c.n) / Math.max(1, K))} · ${prettyKet(P.label)}</b><span>${isMeasured() ? 'measured' : 'predicted'}</span>` +
        `<p>p(+1) = ${P.pp.toFixed(3)} · ${P.match ? 'verifies' : 'MISMATCH'}${P.affected && c.type !== 'NONE' ? ' · hit by ' + (TYPE_NAMES[c.type] || c.type) : ''}<br>|b| = ${P.rLen.toFixed(3)}</p>`;
    } else if (eve.group.visible && ray.intersectObject(eve.group, true).length) {
      html = `<b>Eve</b><span>${TYPE_NAMES[cfg.type] || ''}</span><p>${theory(isMeasured() ? res.config : cfg).lines[0]}</p>`;
    } else if (ray.intersectObject(bob.group, true).length) {
      html = res ? `<b>Bob · verifier</b><span>${res.classification}</span><p>anomaly ${fmt(res.anomaly)} vs τ ${fmt(res.threshold)}</p>` : '<b>Bob · verifier</b><p>measures each element in its own basis</p>';
    } else if (ray.intersectObject(alice.group, true).length) {
      html = '<b>Alice · signer</b><p>prepares one Pauli eigenstate per signature element</p>';
    }
    tip.innerHTML = html;
    tip.classList.toggle('on', !!html);
    tip.style.transform = `translate(${Math.min(mouse.x + 16, mouse.w - 240)}px, ${Math.min(mouse.y + 16, mouse.h - 110)}px)`;
  }

  // ------------------------------------------------------------ loop --------
  const tmp = V3(), tmp2 = V3();
  const mintC = new THREE.Color(PAL.mint), coralC = new THREE.Color(PAL.coral);
  let last = performance.now();
  function loop(now) {
    requestAnimationFrame(loop);
    const rdt = Math.min(0.05, (now - last) / 1000); last = now;
    const time = now / 1000;
    stage.resize(view.clientWidth, view.clientHeight);
    const d = bus.poll();
    if (d) onData(d);
    if (view.clientWidth < 10 || !frameVisible()) { last = performance.now(); return; }
    syncCard();

    const measured = isMeasured();
    const c = measured ? res.config : cfg;
    const V = measured ? verdictOf(res) : null;
    // Slow motion through the implosion and detonation.
    // Slow motion eases in and out of the implosion instead of snapping.
    slowS.target = measured && destroy && destroy.v > 1.5 && destroy.v < 2.6 ? 0.3 : 1;
    const slow = clamp(slowS.step(rdt), 0.2, 1);
    if (measured) filmT += rdt * slow;
    if (window.__qvForceT != null && res) filmT = window.__qvForceT; // test hook for frame capture
    const T = measured ? filmT : -1;
    const phase = !measured ? 0 : T < F.STREAM ? 0 : T < F.MEASURE ? 1 : T < F.DETECT ? 2 : T < F.VERDICT ? 3 : 4;
    pills.forEach((p, i) => { p.classList.toggle('on', measured ? i === phase : i === 0); p.classList.toggle('done', measured && i < phase); });

    // Eve's presence and temperament follow the configured intensity.
    const hostile = c.type !== 'NONE';
    S.aggro.target = hostile ? +c.intensity : 0;
    S.size.target = hostile ? 0.5 + 0.55 * c.intensity : 0.3;
    S.wob.target = c.type === 'CHANNEL_MANIPULATION' ? +c.intensity : 0;
    const ag = S.aggro.step(rdt), sz = S.size.step(rdt), wob = S.wob.step(rdt);
    const calm = V === 'THREAT' ? 1 - seg(T, F.VERDICT + 2.2, F.VERDICT + 3.4) : 1;
    const alertAmt = hostile ? clamp(0.25 + ag * 0.6) * calm : 0;
    stage.setAlert(alertAmt * 0.75);
    dust.update(time, 0.5, alertAmt);
    alice.update(time, 1);
    bob.update(time, 1 + (destroy ? destroy.pulse : 0));
    if (destroy) destroy.pulse *= Math.exp(-rdt * 4);

    // Fibre: tremor proportional to the depolarizing strength.
    if (wob > 0.01 || fiber._w) {
      fiber.deform((u) => { const env = Math.sin(Math.PI * u); return [0, Math.sin(u * 24 + time * 12) * wob * env * 0.35, Math.cos(u * 19 + time * 10) * wob * env * 0.3]; });
      fiber._w = wob > 0.01;
    }
    fog.points.visible = wob > 0.02;
    if (fog.points.visible) {
      fogBase.forEach((n, i) => {
        const p = curve.getPoint((n.u + time * 0.02 * n.s) % 1), ang = n.a + time * n.s * 2, rr = n.r * (0.4 + wob * 1.4);
        fog.pos.set([p.x, p.y + Math.cos(ang) * rr, p.z + Math.sin(ang) * rr], i * 3);
        fog.alpha[i] = 0.65 * clamp(wob * 1.6);
      });
      fog.commit();
    }

    // Adversaries.
    const imp = c.type === 'IMPERSONATION';
    const eveOn = hostile && !imp;
    const gone = destroy && destroy.exploded;
    const fleeing = V === 'SUSPICIOUS' ? ease.inCubic(seg(T, F.VERDICT + 0.9, F.VERDICT + 2.6)) : 0;
    const escaping = V === 'MISSED' ? seg(T, F.VERDICT + 0.5, F.VERDICT + 2.2) : 0;
    eve.group.visible = eveOn && !gone && fleeing < 0.99 && escaping < 0.99;
    const shiver = destroy ? destroy.shiver : 0;
    const ePos = V3(EVE_POS.x + hnoise(time * (0.8 + ag * 3), 3) * (0.1 + ag * 0.3) + (Math.random() - 0.5) * shiver,
      EVE_POS.y + Math.sin(time * 1.3) * 0.1 + fleeing * 6 + (Math.random() - 0.5) * shiver, EVE_POS.z - fleeing * 14 + escaping * 2);
    eve.group.position.copy(ePos);
    const squeeze = destroy ? destroy.squeeze : 1;
    eve.group.scale.setScalar(Math.max(0.001, sz * squeeze * (1 - escaping)));
    eve.update(time * (1 + ag * 1.5), 0.3 + ag * 0.7 * (0.5 + 0.5 * Math.sin(time * (4 + ag * 8))));
    eve.uCrack.value = destroy ? destroy.crack : 0;
    // Glitch-out when a missed attack escapes.
    if (escaping > 0 && escaping < 0.95) { eve.group.position.x += (Math.random() - 0.5) * escaping; if (Math.random() < 0.6) emit(ePos, PAL.coral, 4, 1.6, 0.9, -0.6); }
    const nT = ['FORGERY', 'UNAUTHORIZED_VERIFICATION', 'CHANNEL_MANIPULATION'].includes(c.type) ? 3 : 1;
    const reach = eveOn ? (0.35 + 0.65 * ag) * (destroy ? 1 - destroy.release : 1) : 0;
    eve.setTendrils([curve.getPoint(0.44), curve.getPoint(0.5), curve.getPoint(0.56)].slice(0, nT), reach * (1 - escaping) * (1 - fleeing), time);
    const mUp = imp ? springResp(measured ? T + 1 : 3, 6, 0.55) * (gone ? 0 : 1) : 0;
    mallory.group.visible = mUp > 0.01;
    mallory.group.position.y = lerp(-4.2, 0, mUp) + (imp ? fleeing * -4 : 0);
    mallory.group.scale.setScalar(destroy && imp ? Math.max(0.001, destroy.squeeze) : 1);
    mallory.update(time, 1 + ag);
    const mask = Math.sin(time * 26) > 0.55;
    mallory.bandMat.color.set(mask ? PAL.lav : PAL.coral); mallory.bandMat.emissive.copy(mallory.bandMat.color);
    mFiber.setGrow(imp ? mUp : 0);
    // Intercept-resend: Eve measures in a guessed basis (X, Y or Z).
    eveBloch.visible = c.type === 'UNAUTHORIZED_VERIFICATION' && eve.group.visible;
    eveBloch.position.copy(ePos).add(V3(0, 1.9 * sz + 0.4, 0));
    const guess = Math.floor(time * 2.2) % 3;
    eveBloch.userData.arrow.setDir([V3(1, 0, 0), V3(0, 1, 0), V3(0, 0, -1)][guess].multiplyScalar(Math.floor(time * 4.4) % 2 ? 1 : -1), 1);

    // ---- the qubit stream (preview loops; measured runs once on the film clock)
    const spacing = measured ? Math.min(0.14, 3.0 / Math.max(1, K)) : Math.min(0.22, 3.6 / Math.max(1, K));
    const L = 1.0 + spacing * K + 2.2 + 2.4;
    const st = measured ? T - F.STREAM : time % L;
    const travel = 1.6;
    RAIN.alpha.fill(0);
    let rainI = 0, matched = 0, seen = 0;
    for (let i = 0; i < K; i++) {
      const q = qubits[i], P = plan[i], slot = slots[i];
      if (!q || !P) continue;
      const t0 = 0.3 + i * spacing;
      const u = (st - t0) / travel;
      const hop = seg(st, t0 + travel, t0 + travel + 0.45);
      const fade = measured ? 1 : 1 - seg(st, L - 0.6, L - 0.1);
      q.visible = st > t0 && fade > 0.02;
      slot.tag.material.map = ketTexture(P.label);
      const fromM = imp && P.affected;
      let pos;
      if (u < 1) {
        if (fromM && u < 0.35) pos = mCurve.getPoint(clamp(u / 0.35));
        else pos = curve.getPoint(fromM ? 0.3 + clamp((u - 0.35) / 0.65) * 0.7 : clamp(u));
      } else {
        tmp.copy(OB); tmp2.copy(slot.p).setY(1.45);
        pos = tmp.clone().lerp(tmp2, ease.inOutCubic(hop));
        pos.y += Math.sin(Math.PI * hop) * 1.2;
      }
      const hit = P.affected && u > 0.5;
      let dir = P.dir, len = 0.98;
      if (c.type === 'CHANNEL_MANIPULATION') {
        len = lerp(1, P.rLen, clamp(u / 0.9));
        dir = P.dir.clone().add(V3(hnoise(time * 7, i), hnoise(time * 6, i + 2), 0).multiplyScalar(0.25 * c.intensity * (u < 1 ? 1 : 0.3)));
      }
      if (hit && (c.type === 'FORGERY' || c.type === 'UNAUTHORIZED_VERIFICATION')) dir = P.rDir;
      if (fromM) dir = P.rDir;
      if (u >= 1 && measured) { dir = P.rDir; len = P.rLen; }
      q.userData.arrow.setDir(dir, len);
      const bad = (hit && c.type !== 'CHANNEL_MANIPULATION') || fromM;
      q.setArrowColor(bad ? PAL.coral : PAL.lav);
      q.userData.shell.material.color.set(bad ? PAL.coralLight : PAL.sky);
      // The instant of substitution / collapse: the original state is lost.
      if (P.affected && !fromM && c.type !== 'CHANNEL_MANIPULATION' && u >= 0.5 && u - rdt / travel < 0.5) emit(pos, c.type === 'FORGERY' ? PAL.sky : PAL.lav, 16, 2, 0.9);
      q.position.copy(pos);
      q.scale.setScalar(Math.max(0.001, (u < 1 ? 1 : 1.25) * fade * springResp(st - t0, 12, 0.5)));
      // Replay: Eve re-sends the recorded stream as ghost duplicates.
      const gq = ghosts[i];
      if (c.type === 'REPLAY' && eveOn) {
        const g0 = t0 + 1.2, gu = (st - g0) / travel;
        gq.visible = gu > 0 && fade > 0.02 && !gone;
        const gp = gu < 1 ? ePos.clone().lerp(curve.getPoint(0.5 + 0.5 * clamp(gu)), clamp(gu * 6)) : slot.p.clone().setY(2.4 + 0.1 * Math.sin(time * 3 + i));
        gq.position.copy(gp);
        gq.userData.arrow.setDir(P.dir, 0.98);
        gq.scale.setScalar(Math.max(0.001, fade * (0.9 + 0.1 * Math.sin(time * 9 + i))));
      } else gq.visible = false;
      // Measurement: the slot's +1 / −1 tubes fill with the outcome split.
      const mOn = measured ? seg(T, F.MEASURE + i * 0.04, F.MEASURE + 1.6 + i * 0.04) : seg(st, t0 + travel + 0.4, t0 + travel + 1.3) * fade;
      slot.fills[0].scale.y = Math.max(0.001, P.pp * mOn); slot.fills[0].position.y = 0.2 + (P.pp * mOn) / 2;
      slot.fills[1].scale.y = Math.max(0.001, P.pm * mOn); slot.fills[1].position.y = 0.2 + (P.pm * mOn) / 2;
      const judged = mOn > 0.95;
      const rc = !judged ? PAL.skyLight : P.match ? PAL.mint : PAL.coral;
      slot.ring.material.color.set(rc); slot.ring.material.emissive.set(rc);
      slot.ring.scale.setScalar(1 + (judged && !P.match ? 0.15 * Math.sin(time * 8) : 0));
      if (judged) { seen++; if (P.match) matched++; }
      // Shot rain, denser with more shots per element.
      if (mOn > 0.01 && mOn < 0.98) {
        const nDrops = Math.min(22, Math.round((c.shots || 128) / 12));
        for (let j = 0; j < nDrops && rainI < RAINN; j++, rainI++) {
          const plus = hash(j, i) < P.pp;
          const ph = (time * 1.6 + hash(j, i + 50)) % 1;
          RAIN.pos.set([slot.p.x + (plus ? -0.12 : 0.12), 1.5 - ph * 1.2, slot.p.z], rainI * 3);
          const cc = plus ? mintC : coralC;
          RAIN.col.set([cc.r, cc.g, cc.b], rainI * 3);
          RAIN.alpha[rainI] = 0.85 * (1 - ph);
        }
      }
    }
    RAIN.commit();
    stepEmitter(rdt);

    // ---- detection gauge + evidence typing ---------------------------------
    const gOn = measured && T > F.DETECT - 0.3 ? springResp(T - F.DETECT + 0.3, 8, 0.5) : 0;
    const gOut = measured ? 1 - seg(T, F.VERDICT + 4.2, F.VERDICT + 4.8) : 0;
    gauge.group.visible = gOn * gOut > 0.01;
    gauge.group.scale.setScalar(Math.max(0.001, gOn * gOut));
    gauge.group.lookAt(camera.position.x, gauge.group.position.y, camera.position.z);
    if (measured) {
      const scale = Math.max(res.anomaly || 0, res.critical || 0, res.threshold || 0, 1e-6) * 1.25;
      const f = ease.outCubic(seg(T, F.DETECT, F.DETECT + 1.2));
      gauge.set(((res.anomaly || 0) / scale) * f, (res.threshold || 0) / scale, ((res.anomaly || 0) * f).toFixed(4));
      document.querySelectorAll('.meter').forEach((el) => { el.querySelector('.f').style.transform = `scaleX(${(+el.dataset.v || 0) * f})`; });
      const ev = [res.reason].concat(res.evidence || []).filter(Boolean).join('  ·  ').slice(0, 260);
      const nChars = Math.floor(seg(T, F.DETECT + 0.3, F.DETECT + 1.8) * ev.length);
      if (nChars !== evTyped) { evTyped = nChars; $('evidence').textContent = ev.slice(0, nChars) + (nChars < ev.length && nChars > 0 ? '▌' : ''); }
      $('verdict').classList.toggle('show', T > F.VERDICT);
      $('count').textContent = `${Math.round((matched / Math.max(1, K)) * c.n)} / ${c.n} verified`;
    } else {
      $('count').textContent = seen ? `${matched} / ${seen} slots predicted to verify` : '';
      if (res) document.querySelectorAll('.meter').forEach((el) => { el.querySelector('.f').style.transform = `scaleX(${+el.dataset.v || 0})`; });
    }

    // ---- verdict sequences -------------------------------------------------
    const target = imp ? MO.clone() : ePos.clone();
    const vt = measured ? T - F.VERDICT : -1;
    beams.forEach((b) => { b.visible = false; });
    cage.set(0, 0); pillar.material.opacity = 0; flash.material.opacity = 0; shockF.set(0); shockV.set(0);
    beacon.set(0); seal.visible = false;
    if (!(destroy && destroy.exploded)) { shardMesh.visible = false; embers.points.visible = false; embers2.points.visible = false; }
    let docOn = 0;
    if (measured && vt >= 0) {
      // Every mismatched slot testifies: its beam locks onto the adversary.
      const bEnd = V === 'THREAT' ? 2.0 : 1.4;
      const beamOn = V === 'THREAT' || V === 'SUSPICIOUS' ? ease.outExpo(seg(vt, 0, 0.5)) * (1 - seg(vt, bEnd, bEnd + 0.2)) : 0;
      let bi = 0;
      if (beamOn > 0.01) for (let i = 0; i < K && bi < beams.length; i++) {
        // Replay is caught by session metadata, not by mismatches: a third of the rack testifies.
        if (plan[i].match && !(c.type === 'REPLAY' && i % 3 === 0)) continue;
        const from = slots[i].p.clone().setY(1.45), dir = target.clone().sub(from);
        const len = dir.length() * clamp(beamOn * 1.2 - hash(i, 1) * 0.2);
        dir.normalize();
        const b = beams[bi++]; b.visible = len > 0.05;
        b.position.copy(from).addScaledVector(dir, len / 2); b.quaternion.setFromUnitVectors(UP, dir); b.scale.set(1 + Math.sin(time * 40 + i) * 0.3, len, 1);
      }
      if (V === 'THREAT') docOn = runCapture(vt, target, time, rdt);
      if (V === 'SUSPICIOUS') { beacon.position.copy(ePos); beacon.quaternion.copy(camera.quaternion); beacon.set((vt % 1.1) / 1.1, 2.5); docOn = seg(vt, 2.4, 3.2); }
      if (V === 'MISSED') docOn = seg(vt, 2.2, 3.0);
      if (V === 'CLEAR') {
        const sOn = springResp(vt - 0.3, 9, 0.35);
        seal.visible = sOn > 0.01;
        seal.position.copy(card.group.position).add(V3(0.7, 0.1, 0.4));
        seal.scale.setScalar(Math.max(0.001, 1.4 * (2.4 - 1.4 * clamp(sOn))));
        seal.material.opacity = clamp(sOn * 2);
        if (vt > 0.45 && vt - rdt < 0.45) emit(card.group.position, PAL.mint, 40, 3, 1.0, 1);
        shockV.position.copy(card.group.position); shockV.quaternion.copy(camera.quaternion); shockV.material.color.set(PAL.mint); shockV.set(seg(vt, 0.4, 1.4), 3);
        docOn = seg(vt, 1.4, 2.2);
      }
    }
    // Report / certificate card with the real numbers.
    doc.mesh.visible = docOn > 0.01;
    $('metrics').classList.toggle('doc', docOn > 0.4); // the card carries the numbers now
    if (doc.mesh.visible) {
      if (doc._drawn !== res.id) { drawDoc(V); doc._drawn = res.id; }
      doc.mesh.position.set(3.0, 5.7 + Math.sin(time * 1.1) * 0.06, 3.6);
      doc.mesh.lookAt(camera.position);
      doc.mat.opacity = ease.outCubic(docOn);
      doc.mesh.scale.set(1, Math.max(0.001, ease.outBack(docOn)), 1);
    }

    // ---- camera: a director for the film, a slow orbit otherwise -----------
    if (!userCam) {
      let P, Tg, fv = 38, k = 1.6;
      if (!measured) { const o = time * 0.06; P = V3(Math.sin(o) * 7, 7.5, 21 - (1 - Math.cos(o)) * 2); Tg = V3(0.5, 2.4, 1); fv = 36; k = 1.2; }
      else if (T < F.STREAM) { P = V3(-5, 6, 16); Tg = V3(-3, 2.8, 0.5); }
      else if (T < 3.4) { P = V3(-7.5, 4.5, 11); Tg = V3(-2, 2.6, 1.2); fv = 40; }
      else if (T < F.MEASURE) { P = V3(2.2, 3.4, 11); Tg = V3(0.5, 2.3, 2.2); fv = 40; }
      else if (T < F.DETECT) { P = V3(13, 5.5, 10.5); Tg = V3(7, 1.2, 1.8); fv = 40; }
      else if (T < F.VERDICT) { P = V3(11.5, 6, 9); Tg = V3(8, 4.4, 0.8); fv = 40; }
      else if (V === 'THREAT' && vt < 2.3) { P = V3(target.x + 4, 3.6, target.z + 9); Tg = target.clone(); fv = 38 - seg(vt, 1.2, 2.0) * 8; k = 2.6; }
      else if (V === 'THREAT' && vt < 5.0) { P = V3(target.x + 8, 5.5, 14); Tg = V3(4, 2.8, 1.5); fv = 44; }
      else if (docOn > 0) { P = V3(5.0, 6.0, 11.6); Tg = V3(3.0, 5.4, 3.6); k = 1.4; }
      else { P = V3(4, 5.5, 15); Tg = V3(2, 2.4, 1); }
      camTo(P, Tg, fv, rdt, k);
      applyCamera(camera, camBase.pos, camBase.tgt, camBase.fov, time, 0.03 + ag * 0.05, REDUCED ? 0 : destroy ? destroy.camShake : 0);
      controls.target.copy(camBase.tgt);
    } else controls.update();
    hover();
    stage.render(time);
  }

  // The capture: beams -> cage -> cracks -> implosion -> detonation ->
  // time-freeze -> shards pulled into Bob as evidence -> incident report.
  function runCapture(vt, target, time, dt) {
    if (!destroy) destroy = { v: 0, squeeze: 1, crack: 0, shiver: 0, release: 0, exploded: false, pulse: 0, camShake: 0 };
    const D = destroy; D.v = vt;
    const build = ease.outBack(seg(vt, 0.5, 1.1), 2.2);
    D.crack = ease.inCubic(seg(vt, 1.0, 2.0));
    D.shiver = 0.25 * seg(vt, 1.1, 2.0);
    D.squeeze = vt < 2.02 ? 1 - 0.3 * ease.inCubic(seg(vt, 1.1, 1.85)) - 0.65 * ease.inCubic(seg(vt, 1.85, 2.02)) : 0;
    D.release = seg(vt, 0.9, 1.4);
    const exT = vt - 2.02;
    cage.group.position.copy(target);
    cage.group.rotation.y = time * 0.8;
    cage.set(Math.max(0.001, build * (exT < 0 ? 1 - 0.25 * seg(vt, 1.1, 2.0) : 1 + seg(exT, 0, 0.5) * 1.5)), exT < 0 ? 1 : 1 - seg(exT, 0, 0.5));
    if (exT >= 0 && !D.exploded) {
      D.exploded = true; D.camShake = 0.9;
      shards.length = 0;
      for (let i = 0; i < NSH; i++) {
        const dir = V3(Math.random() * 2 - 1, Math.random() * 1.6 - 0.3, Math.random() * 2 - 1).normalize();
        shards.push({ p: target.clone().addScaledVector(dir, Math.random() * 0.5), v: dir.multiplyScalar(4 + Math.random() * 9),
          w: V3(Math.random() * 12, Math.random() * 12, Math.random() * 12), rot: new THREE.Euler(), s: 0.5 + Math.random() * 1.4, fp: null, delay: Math.random() * 1.2, done: false });
      }
    }
    D.camShake *= Math.exp(-dt * 3);
    flash.position.copy(target); flash.material.color.set(PAL.mint);
    flash.material.opacity = exT >= 0 ? win(exT, 0, 0.9, 0.02, 0.8) : 0;
    flash.scale.setScalar(1 + seg(exT, 0, 0.9) * 12);
    const pw = exT >= 0 ? 0.3 + seg(exT, 0, 0.3) * 2 - seg(exT, 0.3, 1.4) * 1.9 : 0.01;
    pillar.position.copy(target).setY(20);
    pillar.material.opacity = exT >= 0 ? 0.55 * win(exT, 0, 1.4, 0.03, 1.2) : 0;
    pillar.scale.set(Math.max(0.01, pw), 1, Math.max(0.01, pw));
    shockF.position.set(target.x, 0.03, target.z); shockF.set(exT >= 0 ? seg(exT, 0, 1.6) : 0, 12);
    shockV.position.copy(target); shockV.quaternion.copy(camera.quaternion); shockV.material.color.set(PAL.coral); shockV.set(exT >= 0 ? seg(exT, 0, 0.8) : 0, 6);
    embers.set(target, exT, 1.8, 0.6);
    embers2.set(target, exT - 0.05, 1.4, 1.2);
    if (D.exploded) {
      shardMesh.visible = true;
      const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = V3();
      const freeze = seg(exT, 0.7, 1.3); // velocity bleeds away: time stops
      const pull = exT - 1.7;            // evidence capture
      shards.forEach((s, i) => {
        if (pull < s.delay) {
          const h = dt * (1 - freeze);
          s.v.y -= 9.8 * h * 0.6; s.p.addScaledVector(s.v, h);
          if (s.p.y < 0.12) { s.p.y = 0.12; s.v.y *= -0.3; s.v.x *= 0.7; s.v.z *= 0.7; }
          s.rot.x += s.w.x * dt * (1 - freeze * 0.85); s.rot.y += s.w.y * dt * (1 - freeze * 0.85);
          s.fp = s.p.clone();
          q.setFromEuler(s.rot); sc.setScalar(s.s);
          m4.compose(s.p, q, sc);
        } else {
          if (!s.fp) s.fp = s.p.clone(); // first frame may land after the pull started
          const k = clamp((pull - s.delay) / 1.1), e = ease.inCubic(k);
          const p = s.fp.clone().lerp(OB, e);
          const sw = (1 - e) * 1.2, a = i * 2.4 + k * 9;
          p.x += Math.cos(a) * sw; p.z += Math.sin(a) * sw; p.y += Math.sin(Math.PI * k) * 1.4;
          if (k >= 1 && !s.done) { s.done = true; D.pulse = Math.min(3, D.pulse + 0.35); if (i % 6 === 0) emit(OB, PAL.mint, 4, 1.4, 0.5, 0); }
          q.setFromEuler(s.rot); sc.setScalar(k >= 1 ? 0 : s.s * (1 - e * 0.8));
          m4.compose(p, q, sc);
        }
        shardMesh.setMatrixAt(i, m4);
      });
      shardMesh.instanceMatrix.needsUpdate = true;
      shardMesh.material.emissiveIntensity = 0.3 + 1.6 * (1 - seg(exT, 0, 1.2)) + 0.8 * seg(pull, 0, 0.4);
      shardMesh.material.emissive.set(pull > 0 ? PAL.mint : PAL.coral);
    }
    return seg(vt, 4.9, 5.8);
  }

  function drawDoc(V) {
    const r = res, c = r.config, n = c.n;
    const mis = Math.round((r.mismatch_rate || 0) * n);
    const rows = [
      ['decision', r.classification],
      ['attack', TYPE_NAMES[c.type] + (c.type !== 'NONE' ? ` · I = ${(+c.intensity).toFixed(2)}` : '')],
      ['anomaly score', `${fmt(r.anomaly)}  vs τ ${fmt(r.threshold)}`],
      ['mismatches', `${mis} / ${n}   (${fmt(r.mismatch_rate, 3)})`],
      ['verification', fmt(r.verification)],
    ];
    if (r.authorization && r.authorization !== 'AUTHORIZED') rows.push(['access control', r.authorization.toLowerCase()]);
    const ev = [r.reason].concat(r.evidence || []).filter(Boolean).slice(0, 2);
    if (V === 'MISSED') ev.unshift(`The attack touched ${theory(c).k} of ${n} elements and the statistics stayed inside the calibrated baseline.`);
    const title = { THREAT: 'INCIDENT · CONTAINED', SUSPICIOUS: 'FLAGGED FOR REVIEW', MISSED: 'PASSED UNDETECTED', CLEAR: 'SIGNATURE VERIFIED' }[V];
    const accent = { THREAT: CSS.coral, SUSPICIOUS: CSS.peach, MISSED: CSS.coral, CLEAR: CSS.mint }[V];
    doc.draw(title, accent, rows, ev, `session ${String(r.id).slice(0, 12)} · ${V === 'THREAT' ? 'evidence captured' : 'recorded'}`);
  }

  buildRack(Math.min(cfg.n, KMAX));
  plan = buildPlan(false);
  renderHud();
  requestAnimationFrame(loop);
})();
