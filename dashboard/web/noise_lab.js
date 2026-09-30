/* ==========================================================================
   QVeris "Channel Anatomy": the Quantum Noise panel
   --------------------------------------------------------------------------
   Bus payload (from dashboard/components/quantum_view.py), all real:
     noise_type, p, state, fidelity, purity,
     ideal     Bloch vector of the input eigenstate
     received  Bloch vector of Bob's measured density matrix, b = Tr(ρσ)
   Each noise model gets its own physics on the fibre, and a wireframe
   ellipsoid on Bob's sphere shows where one application of the channel maps
   EVERY state (theory). It deforms live with p.
   ========================================================================== */

const NOISE = {
  bit_flip: { name: 'Bit flip', glyph: 'X', formula: (p) => `X applied with probability p = ${p.toFixed(2)} · (x, y, z) → (x, (1−2p)y, (1−2p)z)` },
  phase_flip: { name: 'Phase flip', glyph: 'Z', formula: (p) => `Z applied with probability p = ${p.toFixed(2)} · (x, y, z) → ((1−2p)x, (1−2p)y, z)` },
  depolarizing: { name: 'Depolarizing', glyph: '', formula: (p) => `ρ → (1−p)ρ + p·I/2 · every vector shrinks by 1−p = ${(1 - p).toFixed(2)}` },
  amplitude_damping: { name: 'Amplitude damping', glyph: '', formula: (p) => `energy leaks to |0⟩ with γ = ${p.toFixed(2)} · (x, y) → √(1−γ)(x, y), z → (1−γ)z + γ` },
};
// One application of the channel, per axis: [scale x, scale y, scale z] and z offset (Bloch frame).
function channelMap(type, p) {
  switch (type) {
    case 'bit_flip': return { s: [1, Math.abs(1 - 2 * p), Math.abs(1 - 2 * p)], dz: 0 };
    case 'phase_flip': return { s: [Math.abs(1 - 2 * p), Math.abs(1 - 2 * p), 1], dz: 0 };
    case 'amplitude_damping': return { s: [Math.sqrt(1 - p), Math.sqrt(1 - p), 1 - p], dz: p };
    default: return { s: [1 - p, 1 - p, 1 - p], dz: 0 };
  }
}

(async function main() {
  await fontsReady();
  const $ = (id) => document.getElementById(id);
  const view = $('view');
  const stage = createStage($('stage'), { fogNear: 26, fogFar: 90, maxDpr: 1.5 });
  const { scene, camera } = stage;
  bridgeCursor();
  const bus = makeBus(QV.channel || 'noise');
  $('title').textContent = QV.title || 'CHANNEL ANATOMY';

  const dust = makeDust(stage, 500, [44, 12, 30], 12);
  scene.add(dust.points);
  const R = 1.35, Y = 3.3;
  function pedestal(x, color, title, sub) {
    const g = new THREE.Group();
    const light = new THREE.Color(color).lerp(new THREE.Color(0xF7F7FC), 0.62);
    const prof = [[0, 0], [1.2, 0], [1.28, 0.08], [1.24, 0.24], [0.62, 0.36], [0.4, 0.9], [0.4, 1.5], [0.62, 1.66], [0.66, 1.76], [0, 1.78]].map((p) => new THREE.Vector2(p[0], p[1]));
    const body = new THREE.Mesh(new THREE.LatheGeometry(prof, 96), MAT.ceramic(light));
    body.castShadow = true; body.receiveShadow = true;
    const band = new THREE.Mesh(new THREE.TorusGeometry(1.25, 0.022, 10, 120), MAT.glow(color, 1.8));
    band.rotation.x = Math.PI / 2; band.position.y = 0.16;
    const label = makeLabel(title, sub, { accent: '#' + new THREE.Color(color).getHexString(), height: 0.7 });
    label.position.y = Y + R + 0.75;
    g.add(body, band, label);
    g.position.x = x;
    scene.add(g);
    return g;
  }
  pedestal(-5.5, PAL.lav, 'ALICE', 'input state');
  pedestal(5.5, PAL.mint, 'BOB', 'measured ρ');
  // Soft glowing cores under each sphere keep the arrows readable on a light floor.
  const A = makeBloch(R, { color: PAL.lav, arrowColor: PAL.lav });
  A.position.set(-5.5, Y, 0);
  const B = makeBloch(R, { color: PAL.mint, arrowColor: PAL.coral });
  B.position.set(5.5, Y, 0);
  scene.add(A, B);
  const ghost = makeArrow(R, PAL.mint, { opacity: 0.35, glow: 0.4 });
  B.add(ghost);
  // Where the channel sends every state: a deforming wireframe ellipsoid.
  const ell = new THREE.Mesh(new THREE.SphereGeometry(R, 28, 18), new THREE.MeshBasicMaterial({ color: PAL.coral, wireframe: true, transparent: true, opacity: 0.35 }));
  const ellFill = new THREE.Mesh(new THREE.SphereGeometry(R * 0.995, 40, 24), new THREE.MeshBasicMaterial({ color: PAL.coral, transparent: true, opacity: 0.07, depthWrite: false }));
  B.add(ell, ellFill);
  const curve = new THREE.CatmullRomCurve3([V3(-5.5 + R, Y, 0), V3(-2, Y + 0.9, 0.4), V3(2, Y + 0.9, -0.4), V3(5.5 - R, Y, 0)]);
  const fiber = makeFiber(curve, { radius: 0.09 });
  scene.add(fiber.group);
  const carrier = makeQubit(0.34, PAL.sky, PAL.lav);
  scene.add(carrier);
  const trail = makePulse(stage, PAL.sky, { size: 0.08, trail: 28 });
  scene.add(trail.group, trail.trail.points);
  const gates = [0.25, 0.42, 0.58, 0.75].map((u) => { const s = makeGlyph('X', { size: 0.62, color: CSS.ink, ring: CSS.coral }); s.position.copy(curve.getPoint(u)).add(V3(0, 0.75, 0)); s.userData.u = u; scene.add(s); return s; });
  const fog = makePoints(stage, 420, { size: 0.12 });
  const FR = rng(9), fb = [];
  for (let i = 0; i < 420; i++) { fb.push({ u: FR(), r: FR(), a: FR() * 6.28, s: 0.3 + FR() }); const c = new THREE.Color(i % 3 ? PAL.coralLight : PAL.peach); fog.col.set([c.r, c.g, c.b], i * 3); fog.sz[i] = 0.5 + FR() * 1.4; }
  scene.add(fog.points);
  const drops = makePoints(stage, 160, { size: 0.09 });
  for (let i = 0; i < 160; i++) { const c = new THREE.Color(PAL.gold); drops.col.set([c.r, c.g, c.b], i * 3); }
  scene.add(drops.points);

  const controls = new OrbitControls(camera, stage.renderer.domElement);
  Object.assign(controls, { enableDamping: true, dampingFactor: 0.06, enableZoom: false, enablePan: false, minPolarAngle: 0.3, maxPolarAngle: 1.45 });
  let userCam = false;
  controls.addEventListener('start', () => { userCam = true; $('hint').style.opacity = 0; });
  controls.target.set(0, Y, 0);

  // Everything morphs through springs when the widgets change.
  let D = { noise_type: 'depolarizing', p: 0.1, state: '|+>', fidelity: 1, purity: 1, ideal: [1, 0, 0], received: [1, 0, 0] };
  const sp = { p: new Spring(0.1, 70, 0.7), s: [0, 1, 2].map(() => new Spring(1, 70, 0.55)), dz: new Spring(0, 70, 0.6), rec: [0, 1, 2].map(() => new Spring(0, 55, 0.5)), ide: [0, 1, 2].map(() => new Spring(0, 55, 0.45)) };
  let changedAt = -9;
  function onData(d) {
    D = Object.assign({}, D, d);
    changedAt = performance.now() / 1000;
    const nz = NOISE[D.noise_type] || NOISE.depolarizing;
    $('sub').textContent = `${nz.name} · p = ${(+D.p).toFixed(2)} · ${prettyKet(D.state || '')}`;
    const len = Math.hypot(...D.received);
    const F = +D.fidelity;
    $('rows').innerHTML = [
      ['fidelity', F.toFixed(4), F >= 0.8 ? 'good' : 'bad'], ['purity Tr ρ²', (+D.purity).toFixed(4), ''],
      ['|b| received', len.toFixed(4), len > 0.95 ? 'good' : 'warn'],
      ['b ideal', D.ideal.map((x) => (+x).toFixed(2)).join(', '), ''], ['b measured', D.received.map((x) => (+x).toFixed(2)).join(', '), ''],
    ].map(([k, v, c]) => `<div class="row"><span>${k}</span><b class="${c}">${v}</b></div>`).join('');
    $('note').innerHTML = `<span class="h">CHANNEL · ${nz.name.toUpperCase()}</span>${nz.formula(+D.p)}<br>ellipsoid: one application (theory) · coral arrow: measured ρ<sub>Bob</sub> after the full teleportation circuit`;
    const b = $('badge');
    b.className = 'on ' + (F >= 0.8 ? 'ok' : 'bad');
    b.textContent = F >= 0.8 ? 'Transmission within threshold (F ≥ 0.80)' : 'Fidelity below threshold: the channel destroyed the state';
  }
  const glyphTex = {};
  function gateTex(ch) {
    if (!glyphTex[ch]) glyphTex[ch] = makeGlyph(ch, { size: 0.62, color: CSS.ink, ring: CSS.coral }).material.map;
    return glyphTex[ch];
  }

  let last = performance.now(), prevPass = -1;
  function loop(now) {
    requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    const time = now / 1000;
    stage.resize(view.clientWidth, view.clientHeight);
    const d = bus.poll();
    if (d) onData(d);
    if (view.clientWidth < 10 || !frameVisible()) return;
    const type = D.noise_type, nz = NOISE[type] || NOISE.depolarizing;
    sp.p.target = +D.p;
    const cm = channelMap(type, +D.p);
    cm.s.forEach((v, i) => { sp.s[i].target = v; });
    sp.dz.target = cm.dz;
    const rs = blochToScene(D.received), is = blochToScene(D.ideal);
    [rs.x, rs.y, rs.z].forEach((v, i) => { sp.rec[i].target = v; });
    [is.x, is.y, is.z].forEach((v, i) => { sp.ide[i].target = v; });
    const p = sp.p.step(dt);
    const s = sp.s.map((q) => q.step(dt)), dz = sp.dz.step(dt);
    const rec = V3(...sp.rec.map((q) => q.step(dt))), ide = V3(...sp.ide.map((q) => q.step(dt)));
    stage.setAlert(clamp(p * 0.9));
    dust.update(time, 0.5, p);

    // Alice: the input eigenstate. Bob: the ideal ghost and the measured vector.
    A.userData.arrow.setDir(ide, 1);
    ghost.setDir(ide, 1);
    B.userData.arrow.setDir(rec.lengthSq() > 1e-6 ? rec : V3(0, 1, 0), Math.max(0.02, rec.length()));
    ell.scale.set(s[0], s[2], s[1]); ellFill.scale.copy(ell.scale); // Bloch (x, y, z) -> scene (x, z, y)
    ell.position.set(0, dz * R, 0); ellFill.position.copy(ell.position);
    ell.rotation.y = time * 0.15;

    // One carrier crosses the channel every 2.4 s, and the noise acts on it.
    const period = 2.4, pass = Math.floor(time / period), u = (time % period) / period;
    carrier.position.copy(curve.getPoint(u));
    trail.setColor(p > 0.3 ? PAL.coral : PAL.sky);
    trail.placeOnCurve(curve, u, 1, 0.12); trail.head.visible = false;
    let cDir = ide.clone(), cLen = 1;
    // Each gate fires on this pass with probability p (seeded per pass, so it is a fair sample).
    const flipAxis = type === 'bit_flip' ? V3(1, 0, 0) : V3(0, 1, 0);
    gates.forEach((g, k) => {
      const fire = (type === 'bit_flip' || type === 'phase_flip') && hashP(pass, k) < p;
      g.visible = type === 'bit_flip' || type === 'phase_flip';
      if (g.visible) g.material.map = gateTex(nz.glyph);
      g.material.opacity = fire ? 1 : 0.18;
      const near = Math.abs(u - g.userData.u) < 0.03;
      g.scale.setScalar(0.62 * (fire && near ? 1.35 : 1));
      if (fire && u > g.userData.u) cDir.applyAxisAngle(flipAxis, Math.PI * clamp((u - g.userData.u) / 0.05));
    });
    if (type === 'depolarizing') cLen = lerp(1, 1 - p, clamp(u / 0.95));
    if (type === 'amplitude_damping') { const k = clamp(u / 0.95); cDir = ide.clone().multiplyScalar(Math.sqrt(1 - p * k)); cDir.y = ide.y * (1 - p * k) + p * k; cLen = cDir.length(); }
    carrier.userData.arrow.setDir(cDir, Math.max(0.05, cLen));
    carrier.setArrowColor(cLen < 0.8 ? PAL.coral : PAL.lav);
    prevPass = pass;
    // Depolarizing fog, denser with p.
    fog.points.visible = type === 'depolarizing' || type === 'amplitude_damping';
    if (fog.points.visible) {
      fb.forEach((f, i) => {
        const q = curve.getPoint((f.u + time * 0.015 * f.s) % 1), a = f.a + time * f.s;
        const rr = 0.3 + f.r * (0.3 + p * 1.8);
        fog.pos.set([q.x, q.y + Math.cos(a) * rr, q.z + Math.sin(a) * rr], i * 3);
        fog.alpha[i] = (type === 'depolarizing' ? 0.7 : 0.25) * clamp(p * 2.2) * (f.r < p * 1.2 + 0.1 ? 1 : 0.15);
      });
      fog.commit();
    }
    // Amplitude damping: energy drips out of the carrier as it relaxes to |0⟩.
    drops.points.visible = type === 'amplitude_damping';
    if (drops.points.visible) {
      for (let i = 0; i < 160; i++) {
        const born = (i / 160) * period, age = ((time - born) % period + period) % period;
        const bu = (born / period);
        const on = hashP(i, 3) < p * 1.6;
        const q = curve.getPoint(bu);
        drops.pos.set([q.x, q.y - 4.9 * age * age, q.z], i * 3);
        drops.alpha[i] = on && q.y - 4.9 * age * age > 0.05 ? 0.8 * (1 - age / period) : 0;
      }
      drops.commit();
    }
    // Re-measurement pulse on Bob when new data arrives.
    const since = time - changedAt;
    B.userData.core.scale.setScalar(1 + 2 * Math.exp(-since * 3));

    if (!userCam) {
      const o = time * 0.05;
      applyCamera(camera, V3(Math.sin(o) * 5, 6.2, 15.5 - (1 - Math.cos(o)) * 1.5), V3(0, Y - 0.2, 0), 36, time, 0.03, 0);
    } else controls.update();
    stage.render(time);
  }
  function hashP(a, b) { const x = Math.sin(a * 91.7 + b * 17.3) * 43758.5453; return x - Math.floor(x); }
  requestAnimationFrame(loop);
})();
