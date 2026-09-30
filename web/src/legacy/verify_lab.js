/* ==========================================================================
   QVeris "Signature Constellation": the Live Verification panel
   --------------------------------------------------------------------------
   Bus payload (from dashboard/components/security_panel.py), all real:
     n, threshold, score, matches, accepted, seed,
     elements  [{label, basis, expected, measured, match, p_plus}]
   The signature's elements orbit as a ring of qubits. A scanner sweeps the
   ring and collapses each one in its own basis, showing the real p(+1) and
   whether it matched. The central gauge fills to the real verification score;
   the threshold τ is a notch that springs to the slider's value, and the gate
   opens (accepted) or locks (rejected) as the engine decides.
   ========================================================================== */

const VMAX = 48;

(async function main() {
  await fontsReady();
  const $ = (id) => document.getElementById(id);
  const view = $('view');
  const stage = createStage($('stage'), { fogNear: 26, fogFar: 90, maxDpr: 1.5 });
  const { scene, camera } = stage;
  bridgeCursor();
  const bus = makeBus(QV.channel || 'verify');
  $('title').textContent = QV.title || 'SIGNATURE CONSTELLATION';

  const dust = makeDust(stage, 500, [40, 12, 40], 21);
  scene.add(dust.points);
  // Central monument: pedestal, glass core, score ring and threshold notch.
  const mono = new THREE.Group();
  scene.add(mono);
  const prof = [[0, 0], [1.9, 0], [2.0, 0.1], [1.9, 0.26], [1.0, 0.4], [0.7, 1.2], [0.8, 1.4], [0, 1.42]].map((p) => new THREE.Vector2(p[0], p[1]));
  const base = new THREE.Mesh(new THREE.LatheGeometry(prof, 120), MAT.ceramic(0xE8E6F7));
  base.castShadow = true; base.receiveShadow = true;
  mono.add(base);
  const core = new THREE.Mesh(new THREE.SphereGeometry(0.75, 64, 48), MAT.glass(PAL.lav, true));
  core.position.y = 2.4; core.castShadow = true;
  const heart = new THREE.Mesh(new THREE.SphereGeometry(0.26, 32, 24), MAT.glow(PAL.lav, 3));
  heart.position.y = 2.4;
  mono.add(core, heart);
  const SEG = 72, RR = 1.35;
  const segs = new THREE.InstancedMesh(new RoundedBoxGeometry(0.1, 0.06, 0.24, 2, 0.02), new THREE.MeshStandardMaterial({ roughness: 0.4 }), SEG);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), one = V3(1, 1, 1);
  for (let i = 0; i < SEG; i++) {
    const a = (i / SEG) * Math.PI * 2;
    q.setFromAxisAngle(UP, -a);
    m4.compose(V3(Math.cos(a) * RR, 1.5, Math.sin(a) * RR), q, one);
    segs.setMatrixAt(i, m4); segs.setColorAt(i, new THREE.Color(0xD5DAEA));
  }
  mono.add(segs);
  const notch = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.34, 0.34), new THREE.MeshStandardMaterial({ color: PAL.ink }));
  mono.add(notch);
  const tauTag = makeGlyph('τ', { size: 0.45, color: CSS.ink });
  mono.add(tauTag);
  const gate = makeCage(PAL.mint, 1.25);
  gate.group.position.y = 2.4;
  mono.add(gate.group);
  const lockRing = makeShockwave(PAL.coral); lockRing.rotation.x = -Math.PI / 2; lockRing.position.y = 0.05; scene.add(lockRing);
  const sealRing = makeShockwave(PAL.mint); sealRing.rotation.x = -Math.PI / 2; sealRing.position.y = 0.05; scene.add(sealRing);
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 1, 8), MAT.glow(PAL.sky, 3));
  scene.add(beam);
  const scanFan = new THREE.Mesh(new THREE.CircleGeometry(6.2, 48, 0, 0.35), new THREE.MeshBasicMaterial({ color: PAL.sky, transparent: true, opacity: 0.12, side: THREE.DoubleSide, depthWrite: false }));
  scanFan.rotation.x = -Math.PI / 2; scanFan.position.y = 0.04;
  scene.add(scanFan);

  // The ring of signature elements (rebuilt when n changes).
  const ring = [];
  const ringGroup = new THREE.Group();
  scene.add(ringGroup);
  let N = 0;
  function build(n) {
    while (ringGroup.children.length) ringGroup.remove(ringGroup.children[0]);
    ring.length = 0; N = n;
    const Rr = 4.2 + Math.min(1.6, n / 30);
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2;
      const g = new THREE.Group();
      g.position.set(Math.cos(a) * Rr, 1.9 + Math.sin(a * 3) * 0.25, Math.sin(a) * Rr);
      const qb = makeQubit(n > 32 ? 0.2 : 0.28, PAL.sky, PAL.lav);
      const bar = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 1, 8), MAT.glow(PAL.mint, 0.8));
      bar.position.y = -0.6;
      const tag = new THREE.Sprite(MAT.sprite(ketTexture('|0>'), 0.85));
      tag.scale.set(0.46, 0.28, 1); tag.position.y = 0.62;
      const pad = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.02, 6, 40), MAT.glow(PAL.skyLight, 1));
      pad.rotation.x = Math.PI / 2; pad.position.y = -0.4;
      g.add(qb, bar, tag, pad);
      ringGroup.add(g);
      ring.push({ g, qb, bar, tag, pad, a, born: performance.now() / 1000 + Math.random() * 0.4 });
    }
  }

  const controls = new OrbitControls(camera, stage.renderer.domElement);
  Object.assign(controls, { enableDamping: true, dampingFactor: 0.06, enableZoom: false, enablePan: false, minPolarAngle: 0.3, maxPolarAngle: 1.4 });
  let userCam = false;
  controls.addEventListener('start', () => { userCam = true; $('hint').style.opacity = 0; });
  controls.target.set(0, 1.8, 0);

  let D = null;
  const sp = { tau: new Spring(0.7, 80, 0.45), score: new Spring(0, 40, 0.8), open: new Spring(0, 60, 0.5) };
  let scanStart = 0, dataAt = 0, sigKey = '';
  function onData(d) {
    const prevAcc = D ? D.accepted : null;
    D = d;
    const n = Math.min(d.n || (d.elements || []).length || 8, VMAX);
    if (n !== N) build(n);
    ring.forEach((r, i) => { const e = d.elements[Math.floor((i * d.elements.length) / n)] || {}; r.e = e; r.tag.material.map = ketTexture(e.label || '|0>'); });
    const now = performance.now() / 1000;
    // Re-scan only when the signature itself changed; a τ change just moves the notch.
    const key = [d.n, d.seed, d.message, d.score, d.matches].join('|');
    if (key !== sigKey) { sigKey = key; scanStart = now; }
    dataAt = now;
    $('sub').textContent = d.sub || `${d.n} elements · τ = ${(+d.threshold).toFixed(2)} · seed ${d.seed}`;
    $('rows').innerHTML = (d.rows || [
      ['verification score', (+d.score).toFixed(4), d.accepted ? 'good' : 'bad'], ['threshold τ', (+d.threshold).toFixed(2), ''],
      ['matches', `${d.matches} / ${d.n}`, d.matches === d.n ? 'good' : 'warn'], ['outcome', d.accepted ? 'ACCEPTED' : 'REJECTED', d.accepted ? 'good' : 'bad'],
    ]).map(([k, v, c]) => `<div class="row"><span>${k}</span><b class="${c}">${v}</b></div>`).join('');
    $('note').innerHTML = (d.note || '<span class="h">HOW IT IS DECIDED</span>each element is measured in its own Pauli basis; it matches when the measured eigenvalue equals the key’s. score = matches / n, accepted when score ≥ τ.') +
      (prevAcc !== null && prevAcc !== d.accepted ? `<br><b style="color:${d.accepted ? CSS.mint : CSS.coral}">τ moved: the outcome flipped to ${d.accepted ? 'ACCEPTED' : 'REJECTED'}</b>` : '');
    const b = $('badge');
    b.className = 'on ' + (d.accepted ? 'ok' : 'bad');
    b.textContent = d.accepted ? 'Signature accepted' : 'Signature rejected';
  }

  const tip = document.createElement('div');
  tip.style.cssText = 'position:absolute;left:0;top:0;max-width:230px;padding:10px 12px;border-radius:12px;pointer-events:none;opacity:0;background:rgba(246,247,253,.94);border:1px solid rgba(255,255,255,.7);box-shadow:0 16px 36px -16px rgba(30,36,64,.4);transition:opacity .2s;z-index:6;font:500 11.5px/1.45 "JetBrains Mono",monospace;color:#5A6384';
  view.appendChild(tip);
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  let mouse = null;
  stage.renderer.domElement.addEventListener('pointermove', (e) => { const r = stage.renderer.domElement.getBoundingClientRect(); mouse = { x: e.clientX - r.left, y: e.clientY - r.top, w: r.width, h: r.height }; });
  stage.renderer.domElement.addEventListener('pointerleave', () => { mouse = null; tip.style.opacity = 0; });
  function hover() {
    if (!mouse || !D) return;
    ndc.set((mouse.x / mouse.w) * 2 - 1, -(mouse.y / mouse.h) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(ring.map((r) => r.g), true)[0];
    if (!hit) { tip.style.opacity = 0; return; }
    const i = ring.findIndex((r) => { let o = hit.object; while (o) { if (o === r.g) return true; o = o.parent; } return false; });
    const e = (ring[i] || {}).e || {};
    tip.innerHTML = `<b style="font:700 13px 'Space Grotesk',sans-serif;color:#1E2440">${prettyKet(e.label || '')} · ${String(e.basis || '').toUpperCase()} basis</b><br>` +
      `expected ${e.expected > 0 ? '+1' : '−1'} · measured ${e.measured > 0 ? '+1' : '−1'}<br>p(+1) = ${(+e.p_plus || 0).toFixed(4)}<br>` +
      `<b style="color:${e.match ? CSS.mint : CSS.coral}">${e.match ? 'MATCH' : 'MISMATCH'}</b>`;
    tip.style.opacity = 1;
    tip.style.transform = `translate(${Math.min(mouse.x + 16, mouse.w - 240)}px, ${Math.min(mouse.y + 16, mouse.h - 110)}px)`;
  }
  const tmp = V3();
  let last = performance.now();
  function loop(now) {
    requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    const time = now / 1000;
    stage.resize(view.clientWidth, view.clientHeight);
    const d = bus.poll();
    if (d) onData(d);
    if (view.clientWidth < 10 || !frameVisible() || !D) return;

    // The scanner sweeps once per measurement, then keeps idling around.
    const sweepDur = 3.2, ts = time - scanStart;
    const sweep = clamp(ts / sweepDur);
    const ang = sweep < 1 ? sweep * Math.PI * 2 : (ts - sweepDur) * 0.6 + Math.PI * 2;
    scanFan.rotation.z = -ang;
    let scanned = 0, matchedSoFar = 0;
    ring.forEach((r, i) => {
      const e = r.e || {};
      const hitT = (i / N) * sweepDur;
      const got = ts > hitT;
      if (got) { scanned++; if (e.match) matchedSoFar++; }
      const s = springResp(time - r.born, 10, 0.45);
      const collapse = got ? springResp(ts - hitT, 14, 0.35) : 0;
      // Before measurement the arrow drifts; afterwards it snaps to the measured eigenvalue.
      const expDir = blochToScene(EIGEN[e.label] || EIGEN['|+>']).normalize();
      const measDir = expDir.clone().multiplyScalar(e.measured === e.expected ? 1 : -1);
      const drift = V3(Math.sin(time * 1.3 + i), Math.cos(time * 1.1 + i * 2), Math.sin(time * 0.9 + i * 3)).normalize();
      tmp.copy(drift).lerp(measDir, clamp(collapse)).normalize();
      r.qb.userData.arrow.setDir(tmp, 1);
      r.qb.setArrowColor(!got ? PAL.lav : e.match ? PAL.mint : PAL.coral);
      r.qb.userData.shell.material.color.set(!got ? PAL.sky : e.match ? PAL.mintLight : PAL.coralLight);
      const pp = e.p_plus == null ? 0.5 : +e.p_plus;
      const h = Math.max(0.02, (e.expected === 1 ? pp : 1 - pp) * 0.9 * clamp(collapse));
      r.bar.scale.y = h; r.bar.position.y = -0.95 + h / 2;
      r.bar.material.color.set(e.match ? PAL.mint : PAL.coral); r.bar.material.emissive.copy(r.bar.material.color);
      r.pad.material.color.set(!got ? PAL.skyLight : e.match ? PAL.mint : PAL.coral); r.pad.material.emissive.copy(r.pad.material.color);
      r.g.scale.setScalar(Math.max(0.001, s * (1 + (got && ts - hitT < 0.3 ? 0.25 * (1 - (ts - hitT) / 0.3) : 0))));
      r.g.position.y = 1.9 + Math.sin(r.a * 3 + time * 0.8) * 0.2;
    });
    // Beam from the core to the element being measured.
    beam.visible = sweep < 1;
    if (beam.visible) {
      const i = Math.min(N - 1, Math.floor(sweep * N));
      const from = V3(0, 2.4, 0), to = ring[i] ? ring[i].g.position.clone() : from.clone();
      const dir = to.clone().sub(from), len = dir.length(); dir.normalize();
      beam.position.copy(from).addScaledVector(dir, len / 2); beam.quaternion.setFromUnitVectors(UP, dir); beam.scale.set(1, len, 1);
    }
    // Score ring fills with the running score; τ notch springs to the slider.
    sp.tau.target = +D.threshold;
    sp.score.target = sweep < 1 ? matchedSoFar / Math.max(1, N) : +D.score;
    const tau = sp.tau.step(dt), score = sp.score.step(dt);
    const k = Math.round(clamp(score) * SEG);
    const c0 = new THREE.Color(0xD5DAEA), cOk = new THREE.Color(PAL.mint), cBad = new THREE.Color(PAL.coral);
    // Colour follows the engine's decision once the sweep is done; during it, the running score.
    const passing = sweep >= 1 ? D.accepted : score >= tau;
    for (let i = 0; i < SEG; i++) segs.setColorAt(i, i < k ? (passing ? cOk : cBad) : c0);
    segs.instanceColor.needsUpdate = true;
    const ta = clamp(tau) * Math.PI * 2;
    notch.position.set(Math.cos(ta) * RR, 1.5, Math.sin(ta) * RR); notch.rotation.y = -ta;
    tauTag.position.set(Math.cos(ta) * (RR + 0.55), 1.75, Math.sin(ta) * (RR + 0.55));
    // Gate: opens into a mint lattice when accepted, a pulsing coral lock when rejected.
    sp.open.target = sweep >= 1 ? (D.accepted ? 1 : -1) : 0;
    const open = sp.open.step(dt);
    gate.set(Math.max(0.001, Math.abs(open)), clamp(Math.abs(open)));
    gate.group.rotation.y = time * (open > 0 ? 0.6 : 2);
    heart.material.color.set(open > 0.3 ? PAL.mint : open < -0.3 ? PAL.coral : PAL.lav); heart.material.emissive.copy(heart.material.color);
    const since = time - scanStart - sweepDur;
    sealRing.set(D.accepted && since > 0 ? seg(since, 0, 1.4) : 0, 7);
    lockRing.set(!D.accepted && since > 0 ? (since % 1.2) / 1.2 : 0, 4);
    stage.setAlert(!D.accepted && sweep >= 1 ? 0.35 : 0);
    dust.update(time, 0.5, !D.accepted && sweep >= 1 ? 0.5 : 0);

    if (!userCam) {
      const o = time * 0.07;
      applyCamera(camera, V3(Math.sin(o) * 11, 7.2 + Math.sin(time * 0.2) * 0.4, Math.cos(o) * 11), V3(0, 1.8, 0), 40, time, 0.03, 0);
    } else controls.update();
    hover();
    stage.render(time);
  }
  requestAnimationFrame(loop);
})();
