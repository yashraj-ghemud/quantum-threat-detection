/* ==========================================================================
   QVeris story scene: "The Journey of a Signature"
   --------------------------------------------------------------------------
   The whole film is a pure function of story time T (0..T_END seconds), so
   one world drives both modes:

     film  - full-screen cinematic intro, T runs on a clock with time-warp
     dock  - sticky landing-page hero, T is scrubbed by page scroll

   The chapter script lives in docs/animation_storyboard.md.
   ========================================================================== */

const T_END = 34.5;   // the film
const T_SCROLL = 38;  // scroll adds the dive into the dashboard
const REVEAL_C = [0, 7.8, 0]; // where the QVERIS singularity ignites
const CHAPTERS = [
  { id: 'prologue', t: [0, 3.5], num: 'Prologue', title: 'A message is born',
    film: 'Alice writes “' + (QV.message || 'transfer 100 to bob') + '”.', code: 'MESSAGE' },
  { id: 'bind', t: [3.5, 7], num: 'Chapter I', title: 'Bind',
    film: 'SHA-256 binds every byte of the message.',
    body: 'The message bytes are hashed with SHA-256. Change a single character and every state further down the pipeline changes with it.',
    code: 'src/qds/signer.py' },
  { id: 'sign', t: [7, 11], num: 'Chapter II', title: 'Sign',
    film: 'The digest selects Pauli eigenstates from Alice’s secret key table.',
    body: 'Each signature element is one of six Pauli eigenstates (|0⟩ |1⟩ |+⟩ |−⟩ |+i⟩ |−i⟩), chosen from an HMAC key table indexed by the digest.',
    code: 'src/qds/keygen.py · pauli_states.py' },
  { id: 'entangle', t: [11, 15], num: 'Chapter III', title: 'Entangle',
    film: 'A Bell pair |Φ+⟩ links Alice and Bob across the quantum channel.',
    body: 'Signer and verifier share a Bell pair. The verifier’s public key is the set of states it actually received over the channel, not a list it was handed.',
    code: 'src/quantum/bell_states.py · qds/key_distribution.py' },
  { id: 'teleport', t: [15, 19.5], num: 'Chapter IV', title: 'Teleport',
    film: 'Bell measurement, 2 classical bits, Pauli correction. The state reappears at Bob.',
    body: 'Alice performs a Bell measurement and sends two classical bits. Bob applies the X and Z corrections and the state reappears on his side. The qubit that gets verified is the qubit that came out of the channel.',
    code: 'src/quantum/teleportation.py' },
  { id: 'intrude', t: [19.5, 23], num: 'Chapter V', title: 'Intrusion',
    film: 'Eve strikes: forgery, impersonation, replay, interception.',
    body: 'Eve can substitute states (forgery), sign with the wrong key (impersonation), resend an old session (replay), measure in transit (intercept-resend) or inject channel noise.',
    code: 'src/attacks/' },
  { id: 'detect', t: [23, 27], num: 'Chapter VI', title: 'Detect',
    film: 'The measurement statistics betray her. No ML, just physics.',
    body: 'Bob measures each element in its basis. Shannon entropy, Hellinger distance and KL divergence against a calibrated baseline push the anomaly score past τ, and the session is quarantined.',
    code: 'src/security/detector.py · threat_engine.py' },
  { id: 'epilogue', t: [27, T_END], num: 'Epilogue', title: 'QVERIS',
    film: 'QVERIS · Quantum Verification & Risk Evaluation System', code: '' },
];
const chapterAt = (T) => { for (let i = CHAPTERS.length - 1; i >= 0; i--) if (T >= CHAPTERS[i].t[0]) return i; return 0; };

// Camera script: [time, position, look-at, fov]. Interpolated with a
// centripetal Catmull-Rom spline so the move never stops dead at a key.
const CAM = [
  [0.0, [0, 3.6, 17], [0, 2.4, 0], 30],
  [3.4, [0.6, 2.7, 7.2], [0, 2.4, 0], 35],
  [5.2, [5.6, 3.4, 5.0], [0, 2.4, 0.3], 38],
  [7.0, [6.6, 4.4, 1.4], [0, 2.5, 0.6], 40],
  [9.0, [1.6, 9.6, 4.2], [0, 2.4, 1.0], 42],
  [11.0, [0, 7.4, 10.5], [0, 2.4, 0.5], 46],
  [12.6, [0, 5.4, 15], [0, 2.3, 0], 52],
  [15.0, [0, 6.6, 27], [0, 2.4, 0], 32],
  [16.2, [-12.6, 5.4, 6.4], [-8.0, 3.2, 0], 44],
  [18.0, [1.0, 7.2, 8.4], [5.0, 4.9, 0], 48],
  [19.5, [12.6, 4.6, 7.6], [8.6, 3.2, 0.6], 42],
  [21.0, [3.8, 0.9, 10.2], [0, 2.1, 2.4], 40],
  [23.0, [-3.0, 1.6, 9.6], [0.6, 2.0, 2.4], 38],
  [24.6, [5.4, 4.2, 12.6], [3.4, 2.4, 1.2], 40],
  [25.9, [1.4, 2.4, 7.6], [0, 1.6, 2.8], 36],
  [27.4, [0, 3.6, 14], [0, 2.4, 0.5], 40],
  [28.4, [10, 7.5, 15], [0, 7.2, 0], 48],      // the world is pulled into a vortex
  [29.1, [0, 7.8, 8.4], [0, 7.8, 0], 74],      // singularity: rush in, wide lens
  [29.9, [-7, 8.8, 15], [0, 7.6, 0], 42],      // letters fly past the camera
  [31.0, [5, 7.0, 13], [0, 7.6, 0], 34],
  [32.4, [0, 7.6, 20.5], [0, 7.25, 0], 32],    // hero pose
  [34.5, [0, 8.2, 23.5], [0, 7.1, 0], 31],
  [36.4, [10.5, 5.2, 9.5], [8.6, 3.0, 0.2], 40],
  [38.0, [9.0, 2.9, 1.25], [9.0, 2.66, 0], 72],
];
const camPos = new THREE.CatmullRomCurve3(CAM.map((k) => V3(...k[1])), false, 'centripetal');
const camTgt = new THREE.CatmullRomCurve3(CAM.map((k) => V3(...k[2])), false, 'centripetal');
function camAt(T) {
  let i = 0;
  while (i < CAM.length - 2 && T >= CAM[i + 1][0]) i++;
  const l = clamp((T - CAM[i][0]) / (CAM[i + 1][0] - CAM[i][0]));
  const u = (i + l) / (CAM.length - 1);
  return { pos: camPos.getPoint(u), tgt: camTgt.getPoint(u), fov: lerp(CAM[i][3], CAM[i + 1][3], smooth(l)) };
}
// Hand-held intensity and impact shakes, as functions of T.
const SLAMS = [0, 1, 2, 3, 4, 5].map((i) => 29.45 + i * 0.22); // each letter hits its mark
const SHAKES = [[19.9, 0.28], [21.3, 0.22], [25.62, 0.55], [29.2, 0.7], ...SLAMS.map((t, i) => [t, i === 5 ? 0.4 : 0.14])];
function shakeAt(T) { let s = 0; for (const [t, a] of SHAKES) if (T > t) s += a * Math.exp(-(T - t) * 4.5); return s; }
function handheldAt(T) { return 0.035 + 0.1 * win(T, 19.6, 23.4, 0.6, 0.6) + 0.04 * win(T, 23.4, 26.2, 0.3, 0.6); }

// Film time-warp: slow motion on the two big beats, a little faster on the chase.
function filmSpeed(T) {
  if (T > 28.85 && T < 29.35) return 0.3; // the singularity, in slow motion
  if (T > 25.35 && T < 26.2) return 0.32;
  if (T > 15.45 && T < 15.95) return 0.5;
  if (T > 16.2 && T < 18.0) return 1.12;
  return 1;
}

function buildWorld(stage) {
  const { scene } = stage;
  const MESSAGE = QV.message || 'transfer 100 to bob';
  const DIGEST = QV.digest || 'e4f1c0a8b3d29e7f60a1c5b8d4e3f2a19c8b7d6e5f4a3b2c1d0e9f8a7b6c5d4e';

  const dust = makeDust(stage, 1100, [72, 18, 52]);
  scene.add(dust.points);

  // ---- PROLOGUE: the message card condenses out of dust
  const card = makeCard(MESSAGE, DIGEST);
  scene.add(card.group);
  const CARD_POS = V3(0, 2.4, 0);
  const condense = makePoints(stage, 800, { size: 0.075 });
  const R = rng(21), cSrc = [], cDst = [];
  for (let i = 0; i < 800; i++) {
    const a = R() * Math.PI * 2, r = 3 + R() * 9;
    cSrc.push(V3(Math.cos(a) * r, 2.4 + (R() - 0.5) * 7, Math.sin(a) * r - 2));
    cDst.push(V3((R() - 0.5) * 3.3, 2.4 + (R() - 0.5) * 2.0, 0.06));
    const c = new THREE.Color([PAL.lav, PAL.sky, PAL.mint][i % 3]);
    condense.col[i * 3] = c.r; condense.col[i * 3 + 1] = c.g; condense.col[i * 3 + 2] = c.b;
    condense.sz[i] = 0.5 + R();
  }
  scene.add(condense.points);

  // ---- BIND: 64 hex glyphs of the real SHA-256 digest
  const hexTex = makeHexTextures();
  const glyphMats = {};
  for (const ch in hexTex) glyphMats[ch] = MAT.sprite(hexTex[ch], 0);
  const glyphs = [];
  for (let i = 0; i < 64; i++) {
    const s = new THREE.Sprite(glyphMats[DIGEST[i]] || glyphMats['0']);
    s.scale.setScalar(0.24);
    s.userData.start = V3(-1.45 + (i % 32) * 0.092, 2.4 - 0.05 - Math.floor(i / 32) * 0.16, 0.08);
    scene.add(s);
    glyphs.push(s);
  }
  const CORE_POS = V3(0, 2.5, 1.3);
  const core = new THREE.Mesh(new THREE.SphereGeometry(0.28, 32, 24), MAT.glow(PAL.lav, 4));
  const coreShell = new THREE.Mesh(new THREE.SphereGeometry(0.5, 48, 32), MAT.glass(PAL.lav, false));
  const coreFlash = makeFlash(PAL.lav);
  core.position.copy(CORE_POS); coreShell.position.copy(CORE_POS); coreFlash.position.copy(CORE_POS);
  scene.add(core, coreShell, coreFlash);

  // ---- SIGN: six Pauli-eigenstate qubits chosen by the digest
  const labels = [];
  for (let i = 0; i < 6; i++) labels.push(EIGEN_LABELS[parseInt(DIGEST[i * 2] + DIGEST[i * 2 + 1], 16) % 6]);
  const qubits = labels.map((l, i) => {
    const b = makeBloch(0.42, { color: PAL.sky, arrowColor: PAL.lav });
    const tag = makeGlyph(prettyKet(l), { size: 0.42, color: CSS.ink, font: `700 64px ${FONT_MONO}` });
    tag.position.y = 0.72;
    b.add(tag);
    scene.add(b);
    const R2 = rng(100 + i);
    const initDir = V3(R2() - 0.5, R2() - 0.5, R2() - 0.5).normalize();
    return { g: b, tag, label: l, dir: blochToScene(EIGEN[l]).normalize(), initDir, qa: new THREE.Quaternion().setFromUnitVectors(UP, initDir), qb: new THREE.Quaternion().setFromUnitVectors(UP, blochToScene(EIGEN[l]).normalize()) };
  });

  // ---- ENTANGLE: stations, fibre, pylons, Bell pair
  const alice = makeStation(PAL.lav, 'ALICE', 'signer');
  const bob = makeStation(PAL.mint, 'BOB', 'verifier');
  alice.group.position.set(-9, -4, 0);
  bob.group.position.set(9, -4, 0);
  scene.add(alice.group, bob.group);
  const OA = V3(-9, alice.orbY, 0), OB = V3(9, bob.orbY, 0);
  const curve = new THREE.CatmullRomCurve3([OA, V3(-6, 3.3, 0.4), V3(-2.5, 3.6, 0.2), V3(0, 3.65, 0), V3(2.5, 3.6, -0.2), V3(6, 3.3, -0.4), OB], false, 'catmullrom', 0.5);
  const fiber = makeFiber(curve);
  scene.add(fiber.group);
  const pylons = [-4.5, 0, 4.5].map((x) => {
    const p = curve.getPoint((x + 9) / 18);
    const g = new THREE.Group();
    const col = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.09, p.y, 16), MAT.ceramic(0xE9E8F6));
    col.position.y = p.y / 2; col.castShadow = true;
    const clampRing = new THREE.Mesh(new THREE.TorusGeometry(0.13, 0.03, 10, 32), MAT.metal(0xD9D6FB));
    clampRing.position.y = p.y; clampRing.rotation.y = Math.PI / 2;
    const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.36, 0.08, 32), MAT.ceramic(0xE9E8F6));
    foot.position.y = 0.04; foot.receiveShadow = true;
    g.add(col, clampRing, foot);
    g.position.set(p.x, 0, p.z);
    scene.add(g);
    return g;
  });
  const bellA = new THREE.Mesh(new THREE.SphereGeometry(0.2, 32, 24), MAT.glow(PAL.sky, 4));
  const bellB = bellA.clone(); bellB.material = MAT.glow(PAL.sky, 4);
  const bellFlash = makeFlash(PAL.sky);
  scene.add(bellA, bellB, bellFlash);
  const helix = makeHelix(stage);
  scene.add(helix.points);
  const carriers = [0, 1, 2, 3, 4].map(() => { const p = makePulse(stage, PAL.sky, { size: 0.11 }); scene.add(p.group, p.trail.points); return p; });

  // ---- TELEPORT: classical arc, two gold bits, X/Z gates, Bob's qubit
  const arc = new THREE.QuadraticBezierCurve3(V3(-9, 3.4, 0), V3(0, 7.4, -1.6), V3(9, 3.4, 0));
  const arcDots = makePoints(stage, 90, { size: 0.06 });
  const gold = new THREE.Color(PAL.gold);
  for (let i = 0; i < 90; i++) { const p = arc.getPoint(i / 89); arcDots.pos.set([p.x, p.y, p.z], i * 3); arcDots.col.set([gold.r, gold.g, gold.b], i * 3); }
  arcDots.commit();
  scene.add(arcDots.points);
  const bits = [1, 0].map((b) => {
    const cube = new THREE.Mesh(new RoundedBoxGeometry(0.36, 0.36, 0.36, 4, 0.07), new THREE.MeshStandardMaterial({ color: PAL.gold, metalness: 0.85, roughness: 0.22, emissive: PAL.gold, emissiveIntensity: 0.25 }));
    cube.castShadow = true;
    const tag = makeGlyph(String(b), { size: 0.42, color: CSS.ink, ring: CSS.gold });
    tag.position.y = 0.52; cube.add(tag);
    const trail = makePulse(stage, PAL.gold, { size: 0.08, trail: 30 });
    scene.add(cube, trail.group, trail.trail.points);
    return { cube, trail };
  });
  const gateX = makeGlyph('X', { size: 0.62, color: CSS.ink, ring: CSS.sky });
  const gateZ = makeGlyph('Z', { size: 0.62, color: CSS.ink, ring: CSS.sky });
  gateX.position.set(8.2, 3.9, 1.0); gateZ.position.set(9.8, 3.9, 1.0);
  scene.add(gateX, gateZ);
  const aliceBurst = makeBurst(stage, 70, PAL.lav, 9, 5);
  scene.add(aliceBurst.points);
  const bobQ = makeBloch(0.55, { color: PAL.mint, arrowColor: PAL.mint });
  scene.add(bobQ);
  const BOBQ_POS = V3(7.7, 3.9, 1.5);

  // ---- INTRUSION: Eve and her forged pulses
  const eve = makeEve(stage);
  scene.add(eve.group);
  const EVE_POS = V3(0, 1.55, 3.0);
  const forged = [0, 1, 2].map(() => { const p = makePulse(stage, PAL.coral, { size: 0.13 }); scene.add(p.group, p.trail.points); return p; });
  const grip = [0.38, 0.5, 0.62].map((u) => curve.getPoint(u));

  // ---- DETECT: histogram, gauge, beam, cage, shatter
  const pattern = [1, 1, 0, 1, 1, 0, 1, 0];
  const bars = pattern.map((m, i) => {
    const th = Math.PI * (0.28 + (i / (pattern.length - 1)) * 0.5);
    const bar = new THREE.Mesh(new RoundedBoxGeometry(0.3, 1, 0.3, 3, 0.06), MAT.ceramic(m ? PAL.mint : PAL.coral, 0.35));
    bar.castShadow = true;
    bar.position.set(9 + Math.cos(th) * 2.7, 0, Math.sin(th) * 2.7);
    scene.add(bar);
    return { bar, m };
  });
  const gauge = makeGauge(1.15);
  gauge.group.position.set(9.2, 5.6, 0.8);
  gauge.group.rotation.y = -0.35;
  scene.add(gauge.group);
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 1, 12), MAT.glow(PAL.mint, 3.5));
  scene.add(beam);
  const cage = makeCage(PAL.mint, 1.95);
  cage.group.position.copy(EVE_POS);
  scene.add(cage.group);
  const shards = makeShards(stage, 80);
  scene.add(shards.mesh);
  const shock = makeShockwave(PAL.mint);
  shock.rotation.x = -Math.PI / 2;
  shock.position.set(EVE_POS.x, 0.02, EVE_POS.z);
  scene.add(shock);
  const impactFlash = makeFlash(PAL.mint);
  impactFlash.position.copy(EVE_POS);
  scene.add(impactFlash);

  // ---- EPILOGUE: the protected network blooms around the world
  const NR = rng(77), netNodes = [];
  for (let i = 0; i < 14; i++) {
    const a = (i / 14) * Math.PI * 2 + NR() * 0.3, r = 20 + NR() * 9;
    const pos = V3(Math.cos(a) * r, 0, Math.sin(a) * r * 0.75 - 4);
    const g = new THREE.Group();
    const col = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.3, 1.8, 16), MAT.ceramic(0xE6E4F6));
    col.position.y = 0.9; col.castShadow = true;
    const orb = new THREE.Mesh(new THREE.SphereGeometry(0.32, 24, 16), MAT.glow([PAL.lav, PAL.sky, PAL.mint][i % 3], 3));
    orb.position.y = 2.1;
    g.add(col, orb); g.position.copy(pos); scene.add(g);
    const from = i % 2 ? OA : OB;
    const arcC = new THREE.QuadraticBezierCurve3(from.clone(), from.clone().lerp(pos, 0.5).add(V3(0, 6 + NR() * 4, 0)), pos.clone().add(V3(0, 2.1, 0)));
    const arcF = makeFiber(arcC, { radius: 0.035, color: PAL.mint });
    scene.add(arcF.group);
    const pulse = makePulse(stage, PAL.mint, { size: 0.09, trail: 16 });
    scene.add(pulse.group, pulse.trail.points);
    netNodes.push({ g, arcF, arcC, pulse, d: 31.9 + i * 0.12 + NR() * 0.25 });
  }

  // ---- EPILOGUE: the QVERIS reveal ----------------------------------------
  // vortex -> singularity -> explosion -> six pearlescent 3D letters are
  // forged from the blast and slam into place one by one -> light sweep.
  const C = V3(...REVEAL_C);
  const wordmark = makeWordmark(stage, 'QVERIS', 13.4, 2200, 17); // glitter aura behind the letters
  wordmark.group.position.set(0, 7.6, -0.9);
  scene.add(wordmark.group);
  const letters = [];
  const LCOL = [PAL.lav, 0xA79CF5, PAL.sky, 0x7FC0E8, 0x62CDB5, PAL.mint];
  new FontLoader().load(`https://cdn.jsdelivr.net/npm/three@${QV.three_version || '0.165.0'}/examples/fonts/helvetiker_bold.typeface.json`, (font) => {
    const geos = 'QVERIS'.split('').map((ch) => {
      const g = new TextGeometry(ch, { font, size: 2.3, depth: 0.6, curveSegments: 12, bevelEnabled: true, bevelThickness: 0.09, bevelSize: 0.055, bevelSegments: 6 });
      g.computeBoundingBox();
      const bb = g.boundingBox;
      g.translate(-(bb.min.x + bb.max.x) / 2, -(bb.min.y + bb.max.y) / 2, -(bb.min.z + bb.max.z) / 2);
      return { g, w: bb.max.x - bb.min.x };
    });
    const gap = 0.42, total = geos.reduce((a, x) => a + x.w, 0) + gap * (geos.length - 1);
    let x = -total / 2;
    const R = rng(404);
    geos.forEach(({ g, w }, i) => {
      const colr = new THREE.Color(LCOL[i]);
      const mat = new THREE.MeshPhysicalMaterial({
        color: colr.clone().lerp(new THREE.Color(0xF4F3FC), 0.35), metalness: 0.28, roughness: 0.16,
        clearcoat: 1, clearcoatRoughness: 0.06, iridescence: 1, iridescenceIOR: 1.38, iridescenceThicknessRange: [180, 720],
        sheen: 0.5, sheenColor: new THREE.Color(0xffffff), emissive: colr, emissiveIntensity: 0,
      });
      const mesh = new THREE.Mesh(g, mat);
      mesh.castShadow = true;
      const edge = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: colr, transparent: true, opacity: 0, side: THREE.BackSide, blending: THREE.AdditiveBlending, depthWrite: false }));
      edge.scale.setScalar(1.06);
      mesh.add(edge);
      mesh.visible = false;
      scene.add(mesh);
      const dir = V3(R() * 2 - 1, R() * 1.4 - 0.4, R() * 1.2 + 0.3).normalize();
      const spin = V3(R() * 2 - 1, R() * 2 - 1, R() * 2 - 1).normalize().multiplyScalar(5 + R() * 5);
      const ring = makeShockwave(LCOL[i]);
      const sparks = makeBurst(stage, 60, LCOL[i], 900 + i, 6);
      scene.add(ring, sparks.points);
      letters.push({ mesh, edge, mat, target: V3(x + w / 2, C.y - 0.2, 0), dir, spin, ring, sparks, i });
      x += w + gap;
    });
  });
  const implode = [0, 1, 2].map((k) => { const r = makeShockwave([PAL.lav, PAL.sky, PAL.mint][k]); scene.add(r); return r; });
  const blast = makeShockwave(0xFFFFFF); scene.add(blast);
  const blastFloor = makeShockwave(PAL.lav); blastFloor.rotation.x = -Math.PI / 2; blastFloor.position.set(0, 0.03, 0); scene.add(blastFloor);
  const sing = makeFlash(PAL.lav); sing.position.copy(C); scene.add(sing);
  const halo = makeFlash(PAL.sky); halo.position.set(0, C.y - 0.2, -2.5); scene.add(halo);
  const sweep = new THREE.PointLight(0xFFF6EE, 0, 0, 2); scene.add(sweep);
  const underline = new THREE.Mesh(new RoundedBoxGeometry(1, 0.07, 0.07, 2, 0.03), MAT.glow(PAL.lav, 3));
  underline.position.set(0, C.y - 1.75, 0.2); scene.add(underline);

  const tmp = V3(), tmp2 = V3(), q = new THREE.Quaternion();
  const coralC = new THREE.Color(PAL.coral), skyC = new THREE.Color(PAL.sky), mintC = new THREE.Color(PAL.mint);

  function update(T, time) {
    const alert = seg(T, 19.6, 20.8) * (1 - seg(T, 25.7, 27.0));
    stage.setAlert(alert);
    dust.update(time, 0.55 + 0.25 * seg(T, 0, 2), alert);

    // PROLOGUE -------------------------------------------------------------
    const cp = ease.inOutCubic(seg(T, 0.2, 2.5)), cFade = 1 - seg(T, 2.3, 3.1);
    condense.points.visible = cFade > 0;
    if (condense.points.visible) {
      for (let i = 0; i < 800; i++) {
        const k = clamp((cp - (i % 7) * 0.03) / 0.8);
        const e = ease.outCubic(k);
        tmp.lerpVectors(cSrc[i], cDst[i], e);
        const sw = Math.sin(Math.PI * e) * 1.2;
        condense.pos[i * 3] = tmp.x + Math.cos(i + time) * sw;
        condense.pos[i * 3 + 1] = tmp.y + Math.sin(i * 1.3 + time) * sw * 0.5;
        condense.pos[i * 3 + 2] = tmp.z + Math.sin(i * 0.7) * sw;
        condense.alpha[i] = cFade * (0.2 + 0.8 * e) * 0.8;
      }
      condense.commit();
    }
    const cardIn = ease.outCubic(seg(T, 1.3, 2.7));
    const toAlice = ease.inOutCubic(seg(T, 12.0, 13.1));
    card.group.visible = cardIn > 0.01 && toAlice < 0.999;
    if (card.group.visible) {
      tmp.copy(CARD_POS).lerp(OA, toAlice);
      tmp.y += Math.sin(time * 0.8) * 0.05 * (1 - toAlice) + Math.sin(Math.PI * toAlice) * 2.2;
      // During binding and signing the card steps back and tilts to make room.
      const back = ease.inOutCubic(seg(T, 3.6, 4.6)) * (1 - toAlice);
      tmp.z -= back * 1.4;
      card.group.position.copy(tmp);
      card.group.rotation.set(-back * 0.18, Math.sin(time * 0.4) * 0.1 + toAlice * 2.4, 0);
      card.group.scale.setScalar((0.88 + 0.12 * springResp(T - 1.3, 7, 0.5)) * (1 - toAlice * 0.9));
      const op = cardIn * (1 - seg(T, 12.6, 13.1));
      card.bodyMat.opacity = op; card.faceMat.opacity = op;
      card.draw(Math.floor(seg(T, 2.0, 3.3) * MESSAGE.length), seg(T, 6.2, 7.0), seg(T, 8.4, 10.2));
    }

    // BIND ------------------------------------------------------------------
    const lift = ease.outCubic(seg(T, 3.7, 4.8)), col = ease.inCubic(seg(T, 6.05, 7.0));
    const gOp = Math.min(seg(T, 3.6, 3.95), 1 - seg(T, 6.85, 7.0));
    for (const ch in glyphMats) glyphMats[ch].opacity = gOp;
    for (let i = 0; i < 64; i++) {
      const s = glyphs[i];
      s.visible = gOp > 0.001;
      if (!s.visible) continue;
      const th = (i / 64) * Math.PI * 2 + T * 0.9 + col * 7;
      const r = 2.35 * (1 - col);
      tmp.set(Math.cos(th) * r, Math.sin(th * 3 + time) * 0.12, Math.sin(th) * r);
      tmp.applyAxisAngle(V3(1, 0, 0), 0.38).add(CORE_POS);
      tmp2.copy(s.userData.start).add(V3(0, 0, card.group.position.z));
      s.position.lerpVectors(tmp2, tmp, lift);
      s.position.lerp(CORE_POS, col);
      s.scale.setScalar(0.24 * (1 - col * 0.7));
    }
    const coreK = springResp(T - 6.3, 9, 0.45) * (1 - seg(T, 7.0, 7.25));
    core.visible = coreShell.visible = coreK > 0.01;
    core.scale.setScalar(coreK); coreShell.scale.setScalar(coreK * (1 + Math.sin(time * 6) * 0.03));
    coreFlash.material.opacity = win(T, 6.95, 7.6, 0.05, 0.5) * 0.9;
    coreFlash.scale.setScalar(1 + seg(T, 6.95, 7.6) * 5);

    // SIGN + queue at Alice + teleport of qubit 0 --------------------------
    qubits.forEach((Q, i) => {
      const appear = springResp(T - 7.0 - i * 0.06, 9, 0.5);
      const a = (i / 6) * Math.PI * 2 + Math.PI / 6 + T * 0.12;
      const hex = V3(Math.cos(a) * 2.3, Math.sin(a * 2 + T) * 0.12, Math.sin(a) * 2.3).add(CORE_POS);
      tmp.copy(CORE_POS).lerp(hex, appear);
      // Fly to Alice's queue.
      const fly = ease.inOutCubic(seg(T, 12.0 + i * 0.08, 13.3 + i * 0.08));
      const qa = (i / 6) * Math.PI * 2 + time * 0.7;
      const queue = V3(Math.cos(qa) * 1.1, 0.55 + Math.sin(qa * 2) * 0.12, Math.sin(qa) * 1.1).add(OA);
      queue.y += alice.group.position.y;
      tmp.lerp(queue, fly);
      tmp.y += Math.sin(Math.PI * fly) * 1.8;
      let scale = appear * lerp(1, 0.55, fly);
      // Qubit 0 is the one that gets teleported.
      if (i === 0) {
        const inA = ease.inOutCubic(seg(T, 15.0, 15.6));
        tmp.lerp(OA, inA);
        scale *= 1 - inA * 0.75;
        if (T > 15.62) scale = 0;
      }
      Q.g.visible = scale > 0.01 && T > 7.0;
      Q.g.position.copy(tmp);
      Q.g.scale.setScalar(Math.max(0.001, scale));
      const turn = springResp(T - 8.0 - i * 0.18, 13, 0.3);
      q.slerpQuaternions(Q.qa, Q.qb, Math.min(turn, 1.25));
      Q.g.userData.arrow.quaternion.copy(q);
      Q.tag.material.opacity = seg(T, 8.3 + i * 0.18, 8.7 + i * 0.18) * (1 - fly);
      Q.tag.scale.setScalar(0.42 * springResp(T - 8.3 - i * 0.18, 12, 0.4) + 0.001);
    });

    // ENTANGLE ------------------------------------------------------------
    alice.group.position.y = lerp(-4.2, 0, springResp(T - 11.0, 6.5, 0.6));
    bob.group.position.y = lerp(-4.2, 0, springResp(T - 11.35, 6.5, 0.6));
    alice.group.visible = T > 10.8; bob.group.visible = T > 11.1;
    alice.group.scale.setScalar(1); bob.group.scale.setScalar(1);
    const flashA = win(T, 15.55, 16.3, 0.05, 0.6);
    alice.update(time, 1 + flashA * 2.5 + seg(T, 27, 28));
    bob.update(time, 1 + win(T, 18.8, 19.6, 0.1, 0.6) * 2 + seg(T, 27, 28));
    alice.flash.material.opacity = flashA * 0.9;
    alice.flash.scale.setScalar(1 + seg(T, 15.55, 16.3) * 6);
    aliceBurst.set(OA, T - 15.58);
    fiber.setGrow(ease.inOutCubic(seg(T, 11.8, 13.2)));
    pylons.forEach((p, i) => { const k = ease.outCubic(seg(T, 11.6 + i * 0.15, 12.5 + i * 0.15)); p.visible = k > 0.01; p.scale.set(1, Math.max(0.001, k), 1); });
    const bellIn = springResp(T - 13.0, 10, 0.45);
    const split = ease.inOutCubic(seg(T, 13.45, 14.8));
    const uA = 0.5 - 0.5 * split, uB = 0.5 + 0.5 * split;
    bellA.visible = T > 13.0 && T < 15.7;
    bellB.visible = T > 13.0 && T < 18.9;
    bellA.position.copy(curve.getPoint(uA)); bellB.position.copy(curve.getPoint(uB));
    bellA.scale.setScalar(bellIn); bellB.scale.setScalar(bellIn);
    bellFlash.position.copy(curve.getPoint(0.5));
    bellFlash.material.opacity = win(T, 12.95, 13.7, 0.05, 0.6);
    bellFlash.scale.setScalar(1 + seg(T, 12.95, 13.7) * 4);
    const hA = seg(T, 13.1, 13.6) * (1 - seg(T, 15.7, 16.5));
    helix.points.visible = hA > 0.01;
    if (helix.points.visible) helix.set(curve, uA + seg(T, 15.7, 16.5) * (uB - uA), uB, hA, time);
    const carrierA = seg(T, 13.2, 14.0);
    const carrierC = skyC.clone().lerp(coralC, seg(T, 21.3, 21.8) * (1 - seg(T, 25.7, 26.4))).lerp(mintC, seg(T, 26.4, 27.4));
    carriers.forEach((p, k) => {
      p.setColor(carrierC);
      p.placeOnCurve(curve, ((time * 0.16 + k / 5) % 1), carrierA);
    });
    fiber.coreMat.emissive.copy(carrierC); fiber.coreMat.color.copy(carrierC);

    // TELEPORT ------------------------------------------------------------
    arcDots.points.visible = T > 15.6 && T < 19.6;
    for (let i = 0; i < 90; i++) arcDots.alpha[i] = 0.55 * win(T, 15.6, 19.6, 0.4, 0.5) * (i / 89 <= seg(T, 15.8, 16.6) ? 1 : 0);
    arcDots.commit();
    bits.forEach((b, k) => {
      const u = ease.inOutSine(seg(T, 15.9 + k * 0.25, 18.1 + k * 0.1));
      const vis = T > 15.9 + k * 0.25 && T < 18.25 + k * 0.1 ? 1 : 0;
      b.cube.visible = vis > 0;
      b.cube.position.copy(arc.getPoint(u)).add(V3(0, 0, k ? -0.35 : 0.35));
      b.cube.rotation.set(T * 3 + k, T * 4, T * 2);
      b.cube.scale.setScalar(springResp(T - 15.9 - k * 0.25, 10, 0.45) * (1 - seg(T, 18.0 + k * 0.1, 18.25 + k * 0.1)) + 0.001);
      b.trail.placeOnCurve(arc, u, vis, 0.12);
      b.trail.head.visible = false;
    });
    const gx = win(T, 18.15, 18.9, 0.1, 0.35), gz = win(T, 18.45, 19.2, 0.1, 0.35);
    gateX.material.opacity = gx; gateX.scale.setScalar(0.62 * (0.4 + springResp(T - 18.15, 14, 0.35) * 0.6));
    gateZ.material.opacity = gz; gateZ.scale.setScalar(0.62 * (0.4 + springResp(T - 18.45, 14, 0.35) * 0.6));
    gateX.visible = gx > 0.01; gateZ.visible = gz > 0.01;
    // Bob's received qubit: same state as qubit 0, then disturbed by Eve, then verified.
    const bq = springResp(T - 18.9, 8, 0.5) * (1 - seg(T, 28.0, 28.8));
    bobQ.visible = bq > 0.01;
    tmp.copy(OB).lerp(BOBQ_POS, ease.outCubic(seg(T, 18.9, 19.8)));
    bobQ.position.copy(tmp);
    bobQ.position.y += Math.sin(time * 1.1) * 0.04;
    bobQ.scale.setScalar(Math.max(0.001, bq));
    const hit = seg(T, 22.1, 22.7) * (1 - seg(T, 25.8, 26.6));
    const d0 = qubits[0].dir.clone();
    const jitter = V3(hnoise(time * 5, 1), hnoise(time * 5, 2), hnoise(time * 5, 3)).multiplyScalar(1.4 * hit);
    const flip = d0.clone().multiplyScalar(1 - 2 * hit).add(jitter);
    bobQ.userData.arrow.setDir(flip, 1 - 0.3 * hit);
    const am = bobQ.userData.arrow.userData.mat;
    am.color.copy(mintC).lerp(coralC, hit); am.emissive.copy(am.color);

    // INTRUSION -----------------------------------------------------------
    const rise = springResp(T - 19.7, 5.2, 0.5);
    eve.group.visible = T > 19.5 && T < 25.62;
    eve.group.position.set(EVE_POS.x + hnoise(time * 0.8, 4) * 0.15, lerp(-2.8, EVE_POS.y, rise), EVE_POS.z);
    const squeeze = 1 - 0.22 * ease.inCubic(seg(T, 25.1, 25.6));
    eve.group.scale.setScalar(squeeze);
    eve.update(time, win(T, 20.8, 25.6, 0.3, 0.1) * (0.5 + 0.5 * Math.sin(time * 9)) + seg(T, 24.6, 25.6) * 1.5);
    const reach = ease.outCubic(seg(T, 20.7, 21.6)) * (1 - ease.inCubic(seg(T, 24.4, 24.95)));
    eve.setTendrils(grip, reach, time);
    forged.forEach((p, k) => {
      const t0 = 21.6 + k * 0.45;
      p.placeOnCurve(curve, 0.5 + 0.5 * ease.inOutSine(seg(T, t0, t0 + 1.2)), T > t0 && T < t0 + 1.2 ? 1 : 0);
    });

    // DETECT --------------------------------------------------------------
    const barsOut = 1 - seg(T, 27.6, 28.4);
    bars.forEach((b, i) => {
      const h = springResp(T - 23.1 - i * 0.09, 8.5, 0.45) * (b.m ? 1.7 : 0.6) * barsOut;
      b.bar.visible = h > 0.01;
      b.bar.scale.set(1, Math.max(0.001, h), 1);
      b.bar.position.y = h / 2;
    });
    const gIn = springResp(T - 23.0, 9, 0.5) * barsOut;
    gauge.group.visible = gIn > 0.01;
    gauge.group.scale.setScalar(Math.max(0.001, gIn));
    const fill = 0.8 * ease.outCubic(seg(T, 23.5, 24.7));
    gauge.set(fill, 0.36, (fill * 0.52).toFixed(3));
    const bOn = ease.outExpo(seg(T, 24.3, 24.65)) * (1 - seg(T, 25.6, 25.9));
    beam.visible = bOn > 0.01;
    if (beam.visible) {
      const from = OB.clone(), to = eve.group.position.clone();
      const len = from.distanceTo(to) * bOn;
      const dir = to.clone().sub(from).normalize();
      beam.position.copy(from).addScaledVector(dir, len / 2);
      beam.quaternion.setFromUnitVectors(UP, dir);
      beam.scale.set(1 + Math.sin(time * 40) * 0.2, len, 1 + Math.sin(time * 40) * 0.2);
    }
    const build = ease.outBack(seg(T, 24.5, 25.1), 2.2);
    const burst = seg(T, 25.62, 26.3);
    cage.group.position.copy(eve.group.position.y > 0 ? eve.group.position : EVE_POS);
    cage.set(build * squeeze * (1 + burst * 0.8), 1 - burst);
    cage.group.rotation.y = time * 0.5;
    shards.set(EVE_POS, T - 25.62, 1 - seg(T, 28.6, 30.0));
    shock.set(seg(T, 25.65, 27.2), 10);
    impactFlash.material.opacity = win(T, 25.6, 26.4, 0.02, 0.7);
    impactFlash.scale.setScalar(1 + seg(T, 25.6, 26.4) * 9);

    // EPILOGUE ------------------------------------------------------------
    // ---- QVERIS reveal ----
    wordmark.set(seg(T, 29.7, 31.8), time, 0.32);
    // Vortex: the world's dust spirals into the singularity, then is blasted out.
    if (T > 27.8 && T < 31.8) {
      const P = dust.P, n = P.alpha.length;
      const pull = ease.inCubic(seg(T, 27.8, 29.15)), boom = ease.outExpo(seg(T, 29.2, 30.4)), back = ease.inOutCubic(seg(T, 30.4, 31.7));
      for (let i = 0; i < n; i++) {
        const bx = P.pos[i * 3], by = P.pos[i * 3 + 1], bz = P.pos[i * 3 + 2];
        const rx = bx - C.x, ry = by - C.y, rz = bz - C.z, r = Math.hypot(rx, rz) + 1e-3, d = Math.hypot(rx, ry, rz) + 1e-3;
        let x, y, z;
        if (T < 29.2) {
          const a = Math.atan2(rz, rx) + pull * (8 + (i % 7)) + time * 2 * pull, rr = lerp(r, 0.25, pull);
          x = lerp(bx, C.x + Math.cos(a) * rr, pull); y = lerp(by, C.y + ry * (1 - pull) * 0.3, pull); z = lerp(bz, C.z + Math.sin(a) * rr, pull);
        } else {
          const out = 0.3 + boom * (d + 8);
          x = lerp(C.x + (rx / d) * out, bx, back); y = lerp(C.y + (ry / d) * out, by, back); z = lerp(C.z + (rz / d) * out, bz, back);
        }
        P.pos[i * 3] = x; P.pos[i * 3 + 1] = y; P.pos[i * 3 + 2] = z;
        P.alpha[i] = Math.min(1, P.alpha[i] * (1 + 1.5 * pull * (1 - back)));
      }
      P.commit();
    }
    implode.forEach((r, k) => {
      r.position.copy(C); r.quaternion.copy(stage.camera.quaternion);
      const p = seg(T, 28.0 + k * 0.28, 29.15);
      r.visible = p > 0 && p < 1;
      r.scale.setScalar(Math.max(0.01, (1 - ease.inCubic(p)) * 14));
      r.material.opacity = 0.55 * win(T, 28.0 + k * 0.28, 29.15, 0.3, 0.1);
    });
    sing.material.opacity = win(T, 28.3, 29.6, 0.4, 0.25);
    sing.scale.setScalar(T < 29.2 ? 0.3 + ease.inCubic(seg(T, 28.3, 29.2)) * 2.2 : 2.5 + seg(T, 29.2, 29.6) * 26);
    blast.position.copy(C); blast.quaternion.copy(stage.camera.quaternion); blast.set(seg(T, 29.2, 30.3), 22);
    blastFloor.set(seg(T, 29.25, 30.8), 30);
    stage.bloom.strength = 0.38 + 1.1 * win(T, 28.7, 30.0, 0.4, 0.6);
    sweep.position.set(lerp(-11, 11, ease.inOutSine(seg(T, 31.0, 32.6))), C.y + 1.5, 4.5);
    sweep.intensity = 420 * win(T, 31.0, 32.6, 0.25, 0.4);
    letters.forEach((L) => {
      const s = SLAMS[L.i], u = ease.inOutCubic(seg(T, 29.25, s)), tau = T - s;
      L.mesh.visible = T > 29.25;
      if (!L.mesh.visible) return;
      if (tau < 0) { // ejected by the blast, then pulled back to its mark along a curve
        const ctrl = C.clone().addScaledVector(L.dir, 15);
        const a = C.clone().lerp(ctrl, u), b = ctrl.clone().lerp(L.target, u);
        L.mesh.position.copy(a.lerp(b, u));
        L.mesh.rotation.set(L.spin.x * (1 - u), L.spin.y * (1 - u), L.spin.z * (1 - u));
        L.mesh.scale.setScalar(lerp(0.15, 1, ease.outCubic(u)));
        L.edge.material.opacity = 0.35 * u;
      } else {       // slam: overshoot into the plane, squash, ring out
        const damp = Math.exp(-6.5 * tau), wob = damp * Math.cos(17 * tau);
        const hero = seg(T, 32.2, 33.2);
        L.mesh.position.set(L.target.x, L.target.y + Math.sin(time * 1.1 + L.i) * 0.07 * hero, L.target.z - 0.7 * wob);
        L.mesh.rotation.set(0.08 * wob, Math.sin(time * 0.55 + L.i) * 0.07 * hero, 0);
        L.mesh.scale.set(1 + 0.12 * wob, 1 - 0.16 * wob, 1);
        L.edge.material.opacity = 0.9 * Math.exp(-3.5 * tau) + 0.12 * hero;
      }
      const shine = Math.exp(-Math.pow((sweep.position.x - L.target.x) / 1.4, 2)) * win(T, 31.1, 32.6, 0.2, 0.4);
      L.mat.emissiveIntensity = (tau > 0 ? 1.4 * Math.exp(-2.5 * tau) : 0.3) + shine * 1.2 + 0.08;
      L.ring.position.copy(L.target); L.ring.quaternion.copy(stage.camera.quaternion); L.ring.set(seg(T, s, s + 0.7), 3.2);
      L.sparks.set(L.target, tau, 0.9, 1.4);
    });
    halo.material.opacity = 0.55 * seg(T, 30.6, 31.6); halo.scale.setScalar(16 + Math.sin(time * 0.8) * 0.8);
    underline.visible = T > 31.3;
    underline.scale.set(Math.max(0.01, ease.outExpo(seg(T, 31.3, 32.2)) * 13.6), 1, 1);
    netNodes.forEach((n, i) => {
      const pop = springResp(T - n.d, 8, 0.45);
      n.g.visible = pop > 0.01;
      n.g.scale.setScalar(Math.max(0.001, pop));
      n.arcF.setGrow(ease.inOutCubic(seg(T, n.d + 0.2, n.d + 1.3)));
      n.pulse.placeOnCurve(n.arcC, (time * 0.35 + i * 0.13) % 1, seg(T, n.d + 1.2, n.d + 1.6));
    });

    const glitch = win(T, 20.9, 23.0, 0.2, 0.4) * Math.max(0, Math.sin(T * 37) * Math.sin(T * 13 + 1)) + win(T, 25.6, 25.9, 0.02, 0.28) * 0.6;
    return { alert, glitch, chapter: chapterAt(T), handheld: handheldAt(T), shake: shakeAt(T) };
  }

  // Objects the viewer can hover and click on the landing page.
  const pickables = [
    { obj: alice.group, name: 'Alice', sub: 'signer', desc: 'Holds the secret key table. Signs SHA-256(message) as a string of Pauli eigenstates.' },
    { obj: bob.group, name: 'Bob', sub: 'verifier', desc: 'Measures each received state in its basis and checks it against the public key he received.' },
    { obj: eve.group, name: 'Eve', sub: 'adversary', desc: 'Forgery, impersonation, replay, intercept-resend, channel noise: all simulated in src/attacks/.' },
    { obj: card.group, name: 'Message', sub: 'SHA-256 bound', desc: 'The bytes being signed. Their digest indexes the key table.' },
    { obj: bobQ, name: 'Received qubit', sub: 'Bloch vector', desc: 'Length = √(2·purity − 1). A full-length arrow is pure; a shrunken one was decohered by the channel.' },
    { obj: gauge.group, name: 'Anomaly score', sub: 'vs threshold τ', desc: 'τ is calibrated from percentiles of legitimate baseline sessions. No training, no ML.' },
    { obj: fiber.outer, noBump: true, name: 'Quantum channel', sub: 'depolarizing p = 0.02', desc: 'Every session, legitimate ones too, crosses a noisy channel, so the detector must beat real imperfection.' },
    ...qubits.map((Q) => ({ obj: Q.g, name: 'Qubit ' + prettyKet(Q.label), sub: 'Pauli eigenstate', desc: 'One signature element. Measured in its own basis, it returns a definite ±1 eigenvalue.' })),
  ];
  return { update, pickables, T_END };
}

// Wrap each headline character in a span so it can assemble letter by letter.
function splitHeadline() {
  const h = document.querySelector('#landing h1');
  if (!h || h.dataset.split) return;
  h.dataset.split = '1';
  let i = 0;
  const walk = (node) => {
    [...node.childNodes].forEach((c) => {
      if (c.nodeType === 3) {
        // Words stay unbreakable; letters inside them animate individually.
        const frag = document.createDocumentFragment();
        c.textContent.split(/(\s+)/).forEach((word) => {
          if (!word) return;
          if (/^\s+$/.test(word)) { frag.appendChild(document.createTextNode(' ')); return; }
          const w = document.createElement('span');
          w.style.whiteSpace = 'nowrap'; w.style.display = 'inline-block';
          for (const ch of word) {
            const sp = document.createElement('span');
            sp.className = 'ch'; sp.textContent = ch; sp.style.setProperty('--i', i++);
            w.appendChild(sp);
          }
          frag.appendChild(w);
        });
        c.replaceWith(frag);
      } else if (c.nodeType === 1) walk(c);
    });
  };
  walk(h);
}

// ==========================================================================
//   Driver: film <-> docked scroll hero
// ==========================================================================
(async function main() {
  await fontsReady();
  const view = document.getElementById('view');
  const stage = createStage(document.getElementById('stage'), { fogNear: 40, fogFar: 150 });
  const world = buildWorld(stage);
  const cam = stage.camera;

  let P = null, pdoc = null, frame = null;
  try { frame = window.frameElement; P = window.parent; pdoc = P.document; void pdoc.body; } catch (e) { frame = null; }
  const embedded = !!(frame && pdoc);

  // Inject the page-wide interaction layer (cursor, tilt, reveal) once.
  if (embedded && QV.fx && !P.__qvFx) {
    const s = pdoc.createElement('script');
    s.id = 'qv-fx'; s.textContent = QV.fx;
    pdoc.head.appendChild(s);
  }
  const cursor = bridgeCursor();

  // ---- DOM
  const $ = (id) => document.getElementById(id);
  const capKicker = $('cap-kicker'), capTitle = $('cap-title'), capLine = $('cap-line');
  const filmProg = $('film-prog-fill'), sprog = $('sprog-fill'), tip = $('tip'), glitchEl = $('glitch');
  const rail = $('rail'), panels = $('panels'), flashEl = $('flash'), diveEl = $('dive'), revealEl = $('reveal');
  splitHeadline();
  CHAPTERS.forEach((c, i) => {
    const b = document.createElement('button');
    b.className = 'dot'; b.dataset.i = i;
    b.innerHTML = `<i></i><span>${c.title}</span>`;
    b.addEventListener('click', () => scrollToT((c.t[0] + c.t[1]) / 2));
    rail.appendChild(b);
    if (!c.body) return;
    const p = document.createElement('article');
    p.className = 'panel' + (i % 2 ? ' right' : '');
    p.dataset.i = i;
    p.innerHTML = `<div class="kicker">${c.num}</div><h2>${c.title}</h2><p>${c.body}</p><code>${c.code}</code>`;
    panels.appendChild(p);
  });
  const panelEls = [...panels.children];
  const dotEls = [...rail.children];

  // Real headline metrics from the canonical run, when present.
  const m = QV.metrics;
  if (m) {
    const chip = (k, v) => `<div class="chip"><b>${v}</b><span>${k}</span></div>`;
    const pc = (x) => (x == null ? 'n/a' : (x * 100).toFixed(2) + '%');
    $('finale-metrics').innerHTML = chip('detection rate', pc(m.detection_rate)) + chip('false acceptance', pc(m.far)) +
      chip('false rejection', pc(m.frr)) + chip('threshold τ', m.threshold != null ? Number(m.threshold).toFixed(4) : 'n/a');
    $('finale-src').textContent = 'measured · experiments/results/final';
  }

  // ---- layout helpers
  const HERO_SCREENS = 7;
  // The landing frame opens on the finished message card (the prologue
  // plays in the film), so scroll maps onto T in [T_DOCK0, T_END].
  const T_DOCK0 = 3.4;
  const tFromP = (p) => T_DOCK0 + p * (T_SCROLL - T_DOCK0);
  let mode = 'dock', layoutMode = 'sticky';
  let wrap = null;
  const vh = () => (embedded ? P.innerHeight : window.innerHeight);
  function scroller() {
    let el = frame ? frame.parentElement : null;
    while (el && el !== pdoc.body) {
      const cs = P.getComputedStyle(el);
      if (/(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 1) return el;
      el = el.parentElement;
    }
    return pdoc.scrollingElement || pdoc.documentElement;
  }
  // Height and full-bleed geometry go through CSS variables on the host
  // page (see theme.css): Streamlit re-renders reset the wrapper's inline
  // styles, but never touch <html> or our data attribute on the iframe.
  function hostGeometry() {
    const root = pdoc.documentElement.style, h = vh();
    frame.setAttribute('data-qv', 'story');
    root.setProperty('--qv-hero-h', h * HERO_SCREENS + 'px');
    const main = scroller();
    if (!main || main === pdoc.scrollingElement) return;
    // Measure with the offsets cleared (same task, so nothing paints), then
    // pull the hero flush to the scroller's top-left edge.
    root.setProperty('--qv-bleed-l', '0px'); root.setProperty('--qv-bleed-t', '0px');
    const mr = main.getBoundingClientRect(), r = wrap.getBoundingClientRect();
    root.setProperty('--qv-bleed-l', mr.left - r.left + 'px');
    root.setProperty('--qv-bleed-w', main.clientWidth + 'px');
    root.setProperty('--qv-bleed-t', -Math.max(0, r.top - mr.top + main.scrollTop) + 'px');
  }
  function layoutDock() {
    if (!embedded) return;
    const h = vh();
    hostGeometry();
    if (layoutMode === 'sticky') {
      frame.style.cssText = `position:sticky;top:0;left:0;width:100%;height:${h}px;border:0;display:block;z-index:2;border-radius:0;`;
      view.style.cssText = '';
    } else {
      frame.style.cssText = `position:relative;width:100%;height:${h * HERO_SCREENS}px;border:0;display:block;`;
    }
  }
  function enterFilm() {
    mode = 'film';
    document.body.classList.add('film');
    document.body.classList.remove('docking');
    if (embedded) {
      frame.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;border:0;display:block;z-index:999999;border-radius:0;transition:none;';
      view.style.cssText = '';
    }
    film.T = 0; lastChapter = -1;
    document.body.classList.remove('landing-in');
  }
  // Film -> page: the world collapses into a point of light, flashes, and
  // bursts back out as the landing composition (docs/animation_storyboard.md 6.4).
  function dock() {
    if (mode !== 'film') return;
    mode = 'transition';
    trans = { start: performance.now(), from: Math.min(film.T, T_END), swapped: false };
    document.body.classList.remove('film', 'landing-in');
    document.body.classList.add('docking');
    if (embedded) { const sc = scroller(), r0 = wrap.getBoundingClientRect(); if (r0.top < 0) sc.scrollTop += r0.top; }
  }
  function finishTransition() {
    mode = 'dock'; trans = null;
    if (pendingDash) { pendingDash = false; setTimeout(goToDashboard, 350); }
    document.body.classList.remove('docking');
    flashEl.style.opacity = 0;
  }
  // "Go to dashboard": the camera dives into Bob's orb (the end of the scroll
  // story), then the page lands on the dashboard under the mint light.
  function goToDashboard() {
    if (!embedded) return;
    if (mode === 'film') { pendingDash = true; dock(); return; }
    if (mode === 'transition') { pendingDash = true; return; } // runs as soon as the page settles
    if (mode !== 'dock' || goDash) return;
    wheel.target = null;
    goDash = { start: performance.now(), from: Tshow };
  }
  function scrollToT(T) {
    if (!embedded) return;
    const sc = scroller(), r = wrap.getBoundingClientRect();
    const range = r.height - vh();
    sc.scrollTo({ top: sc.scrollTop + r.top + clamp((T - T_DOCK0) / (T_SCROLL - T_DOCK0)) * range, behavior: 'smooth' });
  }
  function progress() {
    if (!embedded) return 0;
    const r = wrap.getBoundingClientRect(), range = r.height - vh();
    return range > 0 ? clamp(-r.top / range) : 0;
  }

  if (embedded) {
    wrap = frame.parentElement;
    wrap.classList.add('qv-hero-wrap');
    layoutDock();
    P.addEventListener('resize', () => { if (mode === 'dock') layoutDock(); });
    // A floating "back to the story" pill on the dashboard itself.
    let back = pdoc.getElementById('qv-back');
    if (!back) {
      back = pdoc.createElement('button');
      back.id = 'qv-back';
      back.textContent = '↑ Back to the story';
      back.style.cssText = 'position:fixed;right:24px;bottom:24px;z-index:2147483000;border:1px solid rgba(255,255,255,.7);border-radius:999px;padding:11px 18px;font:600 13px Inter,sans-serif;color:#1E2440;background:rgba(243,244,251,.88);backdrop-filter:blur(10px);box-shadow:0 14px 30px -14px rgba(76,70,160,.55);opacity:0;transform:translateY(16px);pointer-events:none;transition:all .5s cubic-bezier(.2,.8,.2,1);';
      pdoc.body.appendChild(back);
    }
    back.onclick = () => { const sc = scroller(); sc.scrollTo({ top: sc.scrollTop + wrap.getBoundingClientRect().top, behavior: 'smooth' }); };
    const syncBack = () => { const out = wrap.getBoundingClientRect().bottom < 40; back.style.opacity = out ? 1 : 0; back.style.transform = out ? 'none' : 'translateY(16px)'; back.style.pointerEvents = out ? 'auto' : 'none'; };
    P.addEventListener('scroll', syncBack, true);
    setInterval(syncBack, 800);
    // Verify sticky positioning survived the host's layout; otherwise emulate it.
    P.addEventListener('scroll', () => {
      if (mode !== 'dock' || layoutMode !== 'sticky') return;
      const r = wrap.getBoundingClientRect(), f = frame.getBoundingClientRect();
      if (r.top < -40 && r.bottom > vh() + 40 && Math.abs(f.top) > 3) { layoutMode = 'translate'; layoutDock(); }
    }, true);
    // Forward wheel to the page so the hero scrolls like normal content.
    // Wheel over the hero scrolls the page with easing (native feel, no jumps).
    window.addEventListener('wheel', (e) => {
      e.preventDefault();
      if (mode !== 'dock' || goDash) return;
      const sc = scroller(), max = sc.scrollHeight - sc.clientHeight;
      const base = wheel.target == null ? sc.scrollTop : wheel.target;
      wheel.target = clamp(base + e.deltaY * (e.deltaMode === 1 ? 40 : 1), 0, max);
    }, { passive: false });
  }

  // ---- film state
  const film = { T: 0 };
  let rewind = null, trans = null, lastChapter = -1, goDash = null, pendingDash = false;
  const wheel = { target: null };
  const playIntro = embedded ? !P.__qvIntroDone && QV.intro !== false && !REDUCED : QV.intro !== false;
  if (embedded) P.__qvIntroDone = true;
  if (playIntro) enterFilm(); else document.body.classList.add('landing-in');
  $('skip').addEventListener('click', dock);
  $('godash').addEventListener('click', goToDashboard);
  $('fg-dash').addEventListener('click', goToDashboard);
  $('fg-story').addEventListener('click', dock);
  $('play').addEventListener('click', () => { if (embedded) { const sc = scroller(); sc.scrollTop += wrap.getBoundingClientRect().top; } enterFilm(); });
  window.addEventListener('keydown', (e) => { if (mode === 'film' && (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ')) dock(); });
  try { P && P.addEventListener('keydown', (e) => { if (mode === 'film' && e.key === 'Escape') dock(); }); } catch (e) {}

  function setCaption(i) {
    const c = CHAPTERS[i];
    const cap = $('cap');
    cap.classList.remove('in'); void cap.offsetWidth;
    capKicker.textContent = c.num; capTitle.textContent = c.title; capLine.textContent = c.film;
    cap.classList.add('in');
    cap.classList.toggle('alert', c.id === 'intrude');
    cap.classList.toggle('hide', c.id === 'epilogue');
  }

  // ---- interaction: parallax, hover, click
  const mouse = { x: 0, y: 0, sx: 0, sy: 0, inside: false, px: 0, py: 0 };
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  const bumps = world.pickables.map(() => new Spring(1, 220, 0.28));
  let hovered = -1;
  const rings = [0, 1, 2].map(() => { const r = makeShockwave(PAL.lav); stage.scene.add(r); return { r, t: 9, p: V3() }; });
  const clickBurst = makeBurst(stage, 40, PAL.sky, 77, 3);
  stage.scene.add(clickBurst.points);
  let clickT = 9, clickP = V3();
  let ringIdx = 0;
  window.addEventListener('pointermove', (e) => {
    mouse.px = e.clientX; mouse.py = e.clientY;
    mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(e.clientY / Math.min(window.innerHeight, vh())) * 2 + 1;
    mouse.inside = true;
  });
  window.addEventListener('pointerleave', () => { mouse.inside = false; hovered = -1; tip.classList.remove('on'); });
  const visibleDeep = (o) => { while (o) { if (!o.visible) return false; o = o.parent; } return true; };
  function pick() {
    ndc.set(mouse.x, mouse.y);
    ray.setFromCamera(ndc, cam);
    let best = -1, bestD = Infinity, bestP = null;
    world.pickables.forEach((pk, i) => {
      if (!visibleDeep(pk.obj)) return;
      const hit = ray.intersectObject(pk.obj, true).find((h) => visibleDeep(h.object) && !h.object.isSprite && !h.object.isPoints);
      if (hit && hit.distance < bestD) { best = i; bestD = hit.distance; bestP = hit.point; }
    });
    return { i: best, p: bestP };
  }
  window.addEventListener('pointerdown', () => {
    if (mode !== 'dock') return;
    const { i, p } = pick();
    if (i < 0) return;
    bumps[i].kick(5.5);
    const rr = rings[ringIdx++ % rings.length];
    rr.t = 0; rr.p.copy(p);
    clickT = 0; clickP.copy(p);
  });

  // ---- main loop
  let last = performance.now(), Tshow = playIntro ? 0 : T_DOCK0;
  const base = { pos: V3(), tgt: V3() };
  let baseInit = false;
  function frameLoop(now) {
    requestAnimationFrame(frameLoop);
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    const time = now / 1000;
    const h = Math.min(window.innerHeight, vh());
    if (layoutMode === 'translate' && mode === 'dock' && embedded) {
      const r = wrap.getBoundingClientRect();
      const off = clamp(-r.top, 0, r.height - h);
      view.style.cssText = `position:absolute;left:0;top:0;width:100%;height:${h}px;transform:translate3d(0,${off}px,0);`;
    }
    stage.resize(view.clientWidth || window.innerWidth, h);
    if (wheel.target != null && embedded) {
      const sc = scroller(), d = wheel.target - sc.scrollTop;
      if (Math.abs(d) < 0.8) wheel.target = null; else sc.scrollTop += d * (1 - Math.exp(-dt * 14));
    }

    // Skip rendering while the docked hero is scrolled out of view.
    if (mode === 'dock' && embedded) {
      const r = wrap.getBoundingClientRect();
      if (r.bottom < 0 || r.top > vh()) return;
    }

    let T;
    if (mode === 'film') {
      film.T += dt * filmSpeed(film.T);
      T = film.T;
      if (T >= T_END + 1.0) dock();
      $('film-go').classList.toggle('on', T > 32.6);
      filmProg.style.transform = `scaleX(${clamp(T / T_END)})`;
      const ci = chapterAt(T);
      if (ci !== lastChapter) { lastChapter = ci; setCaption(ci); }
      Tshow = T;
    } else if (mode === 'transition') {
      const k = clamp((now - trans.start) / 2600);
      if (k < 0.34) T = trans.from;
      else {
        T = T_DOCK0;
        if (!trans.swapped) { trans.swapped = true; if (embedded) layoutDock(); Tshow = T_DOCK0; baseInit = false; }
        if (k > 0.42 && !document.body.classList.contains('landing-in')) { document.body.classList.remove('docking'); document.body.classList.add('landing-in'); }
      }
      flashEl.style.opacity = k < 0.34 ? ease.inCubic(k / 0.34) : 1 - ease.outCubic(clamp((k - 0.34) / 0.4));
      flashEl.style.transform = `scale(${k < 0.34 ? 0.2 + 1.6 * ease.inCubic(k / 0.34) : 1.8})`;
      if (k >= 1) finishTransition();
    } else if (rewind) {
      const k = clamp((now - rewind.start) / rewind.dur);
      const target = tFromP(progress());
      T = lerp(Math.min(rewind.from, T_END), target, ease.inOutCubic(k));
      Tshow = T;
      if (k >= 1) rewind = null;
    } else if (goDash) {
      const k = clamp((now - goDash.start) / 2000);
      T = Tshow = lerp(goDash.from, T_SCROLL, ease.inOutCubic(k));
      if (k >= 1) { // land on the dashboard: the hero is scrolled away under full mint light
        const sc = scroller();
        sc.scrollTop += wrap.getBoundingClientRect().bottom;
        goDash = null;
      }
    } else {
      const target = tFromP(progress());
      Tshow += (target - Tshow) * (1 - Math.exp(-dt * 5.5));
      T = Tshow;
    }
    if (window.__qvForceT != null) T = window.__qvForceT; // test hook for frame capture
    T = clamp(T, 0, mode === 'dock' ? T_SCROLL : T_END);

    const info = world.update(T, time);
    const c = camAt(T);
    if (!baseInit) { base.pos.copy(c.pos); base.tgt.copy(c.tgt); baseInit = true; }
    // Critically damped follow smooths speed changes between camera keys.
    const k = mode === 'film' ? 1 - Math.exp(-dt * 7) : 1;
    base.pos.lerp(c.pos, k); base.tgt.lerp(c.tgt, k);
    mouse.sx += ((mode === 'dock' && mouse.inside ? mouse.x : 0) - mouse.sx) * (1 - Math.exp(-dt * 3));
    mouse.sy += ((mode === 'dock' && mouse.inside ? mouse.y : 0) - mouse.sy) * (1 - Math.exp(-dt * 3));
    // On the landing frame, slide the card right of the headline.
    const land = mode === 'film' ? 0 : 1 - ease.inOutCubic(seg(T, T_DOCK0, T_DOCK0 + 1.4));
    const narrow = stage.width < 760 ? 0.2 : 1;
    const par = V3(mouse.sx * 1.4, mouse.sy * 0.8, 0).applyQuaternion(cam.quaternion);
    const pan = V3(-2.6 * land * narrow, 0.2 * land, 4.2 * land).applyQuaternion(cam.quaternion);
    const panT = V3(-2.6 * land * narrow, 0.2 * land, 0).applyQuaternion(cam.quaternion);
    let camPosF = base.pos.clone().add(par).add(pan), camTgtF = base.tgt.clone().add(par.multiplyScalar(0.25)).add(panT), fovF = c.fov;
    if (mode === 'transition') {
      const k = clamp((now - trans.start) / 2600);
      if (k < 0.34) { // implosion: rush into the wordmark's heart
        const e = ease.inCubic(k / 0.34);
        camPosF.lerp(camTgtF, e * 0.85); fovF = lerp(c.fov, 9, e);
      } else {        // big bang: spiral back out into the landing frame
        const e = ease.outCubic(clamp((k - 0.34) / 0.66));
        const off = camPosF.clone().sub(camTgtF).applyAxisAngle(UP, (1 - e) * 2.4).multiplyScalar(1 + (1 - e) * 2.2);
        camPosF = camTgtF.clone().add(off); camPosF.y += (1 - e) * 6; fovF = lerp(115, c.fov, e);
      }
    }
    applyCamera(cam, camPosF, camTgtF, fovF, time, info.handheld, REDUCED ? 0 : info.shake + (mode === 'transition' ? 0.15 : 0));

    // Hover + click feedback.
    if (mode === 'dock' && mouse.inside) {
      const { i } = pick();
      if (i !== hovered) {
        hovered = i;
        if (cursor) cursor.hover(i >= 0 ? 1 : 0);
        if (i >= 0) { const pk = world.pickables[i]; tip.innerHTML = `<b>${pk.name}</b><span>${pk.sub}</span><p>${pk.desc}</p>`; }
        tip.classList.toggle('on', i >= 0);
      }
      tip.style.transform = `translate(${mouse.px + 18}px, ${mouse.py + 18}px)`;
    } else if (hovered >= 0) { hovered = -1; tip.classList.remove('on'); }
    world.pickables.forEach((pk, i) => {
      bumps[i].target = i === hovered ? 1.06 : 1;
      const s = bumps[i].step(dt);
      if (!pk.noBump) pk.obj.scale.multiplyScalar(s);
    });
    rings.forEach((rr) => {
      rr.t += dt;
      rr.r.position.copy(rr.p); rr.r.quaternion.copy(cam.quaternion);
      rr.r.set(clamp(rr.t / 0.8), 2.2);
    });
    clickT += dt; clickBurst.set(clickP, clickT, 0.9);

    // Overlays.
    glitchEl.style.opacity = REDUCED ? 0 : info.glitch;
    if (info.glitch > 0.05 && !REDUCED) {
      glitchEl.style.transform = `translate(${(Math.random() - 0.5) * 18 * info.glitch}px, 0)`;
      stage.renderer.domElement.style.filter = `hue-rotate(${info.glitch * -25}deg) saturate(${1 + info.glitch * 0.6})`;
    } else stage.renderer.domElement.style.filter = '';
    document.body.style.setProperty('--alert', info.alert.toFixed(3));
    if (mode !== 'film') {
      const p = clamp((T - T_DOCK0) / (T_SCROLL - T_DOCK0));
      sprog.style.transform = `scaleX(${p})`;
      const lo = seg(T, T_DOCK0 + 0.1, T_DOCK0 + 1.0);
      $('landing').style.opacity = 1 - lo;
      $('landing').style.transform = `translateY(calc(-50% - ${lo * 40}px))`;
      $('landing').style.pointerEvents = lo < 0.5 ? 'auto' : 'none';
      panelEls.forEach((el) => {
        const ch = CHAPTERS[+el.dataset.i];
        const a = win(T, ch.t[0] + 0.1, ch.t[1] - 0.05, 0.7, 0.7);
        el.style.opacity = a;
        el.style.transform = `translateY(${(1 - a) * 36}px) rotateX(${(1 - a) * 10}deg)`;
      });
      dotEls.forEach((d, i) => d.classList.toggle('on', i === info.chapter));
    }
    const fin = seg(T, 32.4, 33.4) * (1 - seg(T, 34.9, 35.7));
    const rv = seg(T, 31.5, 32.4) * (1 - seg(T, 35.0, 35.8));
    revealEl.style.opacity = rv; revealEl.classList.toggle('on', rv > 0.05);
    const dive = mode === 'dock' ? seg(T, 36.3, 37.8) : 0;
    diveEl.style.opacity = dive;
    diveEl.style.transform = `scale(${1 + dive * 0.08})`;
    $('finale').style.opacity = fin;
    $('finale').style.transform = `translateY(${(1 - fin) * 30}px)`;
    stage.render(time);
  }
  requestAnimationFrame(frameLoop);
})();
