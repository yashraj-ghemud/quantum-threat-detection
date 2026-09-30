/* ==========================================================================
   QVeris 3D core
   --------------------------------------------------------------------------
   Shared stage, materials, models and motion helpers for every WebGL scene
   in the dashboard. dashboard/components/_web.py concatenates this file in
   front of a scene entry file (story.js / attack_lab.js) inside one ES
   module, so everything here is visible to the entry file without exports.

   The host template provides:  THREE, RoomEnvironment, EffectComposer,
   RenderPass, UnrealBloomPass, OutputPass, OrbitControls,
   RoundedBoxGeometry, and window.QV_DATA.

   See docs/animation_storyboard.md for the story every scene tells.
   ========================================================================== */

const QV = window.QV_DATA || {};
const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches || QV.reducedMotion === true;
// QVeris 2: the host app can ask for the dark "Noir" world.
const DARK = QV.theme === 'noir';
const WORLD = DARK
  ? { top: 0x0B0F24, mid: 0x0A0E20, bottom: 0x060816, tint: 0x3A1024, fog: 0x0A0E20, fogAlert: 0x2A0C1A, hemiSky: 0x4A4F8C, hemiGround: 0x0A0C1C, key: 0xC8CCFF, rim: 0x7C66F5, floor: 0x0E1330, exposure: 1.15 }
  : { top: 0xE4DEF7, mid: 0xE6EAF6, bottom: 0xD6DDEF, tint: 0xF6D9DE, fog: 0xE6EAF6, fogAlert: 0xF2DDE2, hemiSky: 0xF6F3FF, hemiGround: 0xC9D0EA, key: 0xFFFBF6, rim: 0xCFC8FF, floor: 0xDDE2F2, exposure: 1.0 };

// ---------------------------------------------------------------- palette --
// Light pastel world: nothing is pure white. Each hue carries a meaning.
const PAL = {
  mist: 0xEAEDF7, mist2: 0xDFE4F2, surface: 0xF3F4FB,
  ink: 0x1E2440, inkSoft: 0x5A6384,
  lav: 0x8C84F0, lavLight: 0xD9D6FB,     // Alice / signer / secret key
  mint: 0x4FC3A1, mintLight: 0xCDEFE4,   // Bob / verified / secure
  sky: 0x6FA8F0, skyLight: 0xD3E4FA,     // quantum channel, qubits
  gold: 0xE8B860,                         // classical correction bits
  peach: 0xF4A77A,                        // suspicious
  coral: 0xE8697A, coralLight: 0xF7D3D9, // Eve / threat
  obsidian: 0x2B2742,
};
const CSS = {};
for (const k in PAL) CSS[k] = '#' + PAL[k].toString(16).padStart(6, '0');

const FONT_HEAD = '"Space Grotesk", "Inter", system-ui, sans-serif';
const FONT_MONO = '"JetBrains Mono", ui-monospace, Consolas, monospace';

// --------------------------------------------------------------- math/motion
const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const UP = V3(0, 1, 0);
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, t) => a + (b - a) * t;
const seg = (t, a, b) => clamp((t - a) / (b - a));
const smooth = (t) => t * t * (3 - 2 * t);
const ease = {
  inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  outCubic: (t) => 1 - Math.pow(1 - t, 3),
  inCubic: (t) => t * t * t,
  outQuart: (t) => 1 - Math.pow(1 - t, 4),
  outExpo: (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
  inOutSine: (t) => -(Math.cos(Math.PI * t) - 1) / 2,
  inOutQuint: (t) => (t < 0.5 ? 16 * t ** 5 : 1 - Math.pow(-2 * t + 2, 5) / 2),
  outBack: (t, s = 1.70158) => 1 + (s + 1) * Math.pow(t - 1, 3) + s * Math.pow(t - 1, 2),
};
// Fades in over [a, a+fi] and out over [b-fo, b].
const win = (t, a, b, fi = 0.4, fo = 0.4) => Math.min(seg(t, a, a + fi), 1 - seg(t, b - fo, b));

// Closed-form step response of an under-damped spring. Being analytic, it
// can be evaluated at any story time, so springy motion stays scrubbable.
function springResp(tau, omega = 12, zeta = 0.42) {
  if (tau <= 0) return 0;
  const wd = omega * Math.sqrt(1 - zeta * zeta);
  return 1 - Math.exp(-zeta * omega * tau) * (Math.cos(wd * tau) + (zeta * omega / wd) * Math.sin(wd * tau));
}

// Layered low-frequency noise: the "hand" behind a hand-held camera.
function hnoise(t, s = 0) {
  return Math.sin(t * 0.91 + s) * 0.5 + Math.sin(t * 2.13 + s * 1.7) * 0.3 + Math.sin(t * 4.37 + s * 2.9) * 0.2;
}

function rng(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Numerically integrated spring, for interaction (hover / click / cursor).
class Spring {
  constructor(x = 0, k = 170, damping = 0.5) {
    this.x = x; this.v = 0; this.target = x; this.k = k;
    this.c = 2 * Math.sqrt(k) * damping;
  }
  step(dt) {
    const n = Math.max(1, Math.ceil(dt / 0.008)), h = dt / n;
    for (let i = 0; i < n; i++) {
      this.v += (this.k * (this.target - this.x) - this.c * this.v) * h;
      this.x += this.v * h;
    }
    return this.x;
  }
  kick(v) { this.v += v; }
}

// Bloch axes -> scene axes (Bloch Z is "up").
const blochToScene = (b) => V3(b[0], b[2], -b[1]);
const EIGEN = {
  '|0>': [0, 0, 1], '|1>': [0, 0, -1], '|+>': [1, 0, 0],
  '|->': [-1, 0, 0], '|+i>': [0, 1, 0], '|-i>': [0, -1, 0],
};
const EIGEN_LABELS = Object.keys(EIGEN);
// U+2212 minus avoids the '|-' -> '⊢' ligature in JetBrains Mono.
const prettyKet = (l) => l.replace('-', '−').replace('>', '⟩');

// ------------------------------------------------------------------- stage --
function createStage(container, opt = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  let dpr = Math.min(window.devicePixelRatio || 1, opt.maxDpr || 1.75);
  renderer.setPixelRatio(dpr);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  // Neutral tone mapping keeps pastel base colours faithful.
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = WORLD.exposure;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.style.display = 'block';
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 900);

  // Sky dome: soft vertical pastel gradient that can blush coral when Eve arrives.
  const skyU = {
    top: { value: new THREE.Color(WORLD.top) },
    mid: { value: new THREE.Color(WORLD.mid) },
    bottom: { value: new THREE.Color(WORLD.bottom) },
    tint: { value: new THREE.Color(WORLD.tint) },
    tintAmt: { value: 0 },
  };
  const sky = new THREE.Mesh(
    new THREE.SphereGeometry(600, 48, 24),
    new THREE.ShaderMaterial({
      uniforms: skyU, side: THREE.BackSide, depthWrite: false, fog: false,
      vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: `uniform vec3 top, mid, bottom, tint; uniform float tintAmt; varying vec3 vP;
        void main(){
          float h = vP.y;
          vec3 c = h > 0.0 ? mix(mid, top, smoothstep(0.0, 0.55, h)) : mix(mid, bottom, smoothstep(0.0, -0.35, h));
          c = mix(c, tint, tintAmt * (0.45 + 0.55 * (1.0 - abs(h))));
          gl_FragColor = vec4(c, 1.0);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    }),
  );
  sky.renderOrder = -10;
  scene.add(sky);
  const fogColor = new THREE.Color(WORLD.fog);
  scene.fog = new THREE.Fog(fogColor.clone(), opt.fogNear || 34, opt.fogFar || 120);

  // Image-based lighting for believable reflections on glass and ceramic.
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.42;

  const hemi = new THREE.HemisphereLight(WORLD.hemiSky, WORLD.hemiGround, DARK ? 0.9 : 0.7);
  scene.add(hemi);
  const key = new THREE.DirectionalLight(WORLD.key, DARK ? 1.5 : 1.9);
  key.position.set(10, 18, 12);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, { left: -22, right: 22, top: 22, bottom: -22, near: 1, far: 70 });
  key.shadow.bias = -0.0004;
  key.shadow.normalBias = 0.02;
  key.shadow.radius = 4;
  scene.add(key);
  const rim = new THREE.DirectionalLight(WORLD.rim, DARK ? 1.2 : 0.6);
  rim.position.set(-14, 7, -12);
  scene.add(rim);

  // Floor: soft matte ground that catches shadows, plus a fading dot grid.
  const floor = new THREE.Mesh(
    new THREE.CircleGeometry(160, 96),
    new THREE.MeshStandardMaterial({ color: WORLD.floor, roughness: DARK ? 0.6 : 0.92, metalness: DARK ? 0.2 : 0 }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);
  const gridU = { uColor: { value: new THREE.Color(PAL.lav) }, uTint: { value: new THREE.Color(PAL.coral) }, uTintAmt: { value: 0 }, uTime: { value: 0 } };
  const grid = new THREE.Mesh(
    new THREE.PlaneGeometry(160, 160),
    new THREE.ShaderMaterial({
      uniforms: gridU, transparent: true, depthWrite: false,
      vertexShader: 'varying vec3 vW; void main(){ vec4 w = modelMatrix * vec4(position,1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }',
      fragmentShader: `uniform vec3 uColor, uTint; uniform float uTintAmt, uTime; varying vec3 vW;
        void main(){
          vec2 g = abs(fract(vW.xz / 1.5 - 0.5) - 0.5) * 1.5;
          float dotv = smoothstep(0.07, 0.0, length(g));
          vec2 l = abs(fract(vW.xz / 6.0 - 0.5) - 0.5) * 6.0;
          float line = smoothstep(0.03, 0.0, min(l.x, l.y)) * 0.35;
          float d = length(vW.xz);
          float fade = smoothstep(46.0, 6.0, d);
          float ring = smoothstep(0.35, 0.0, abs(fract(d / 9.0 - uTime * 0.05) - 0.5) * 9.0 - 4.2) * 0.25;
          float a = (dotv * 0.55 + line + ring) * fade * 0.42;
          gl_FragColor = vec4(mix(uColor, uTint, uTintAmt), a);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    }),
  );
  grid.rotation.x = -Math.PI / 2;
  grid.position.y = 0.003;
  scene.add(grid);

  // Post: HDR render -> bloom on emissive highlights only -> tone map/output.
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.38, 0.5, 1.15);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  const pointMats = [];
  const stage = {
    renderer, scene, camera, composer, bloom, sky, skyU, fogColor, grid, gridU, key, hemi, floor,
    pointMats, width: 1, height: 1, quality: 2,
    resize(w, h) {
      w = Math.max(1, Math.floor(w)); h = Math.max(1, Math.floor(h));
      if (w === stage.width && h === stage.height) return;
      stage.width = w; stage.height = h;
      stage.settle = 2; // skip a couple of frames so render targets are rebuilt before showing
      renderer.setSize(w, h);
      composer.setSize(w, h);
      bloom.resolution.set(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    },
    // Blush the world coral when Eve is present (0 = calm, 1 = full alert).
    setAlert(a) {
      skyU.tintAmt.value = a * 0.8;
      gridU.uTintAmt.value = a;
      scene.fog.color.copy(fogColor).lerp(new THREE.Color(WORLD.fogAlert), a * 0.7);
    },
    render(time) {
      gridU.uTime.value = time;
      const s = (renderer.getSize(new THREE.Vector2()).y * renderer.getPixelRatio()) / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
      for (const m of pointMats) m.uniforms.uScale.value = s;
      if (stage.settle > 0) { stage.settle--; if (stage.settle > 0) return; }
      if (stage.quality >= 1) composer.render(); else renderer.render(scene, camera);
      adapt();
    },
  };

  // Adaptive quality: step down on slow GPUs instead of stuttering.
  let frames = 0, acc = 0, last = performance.now();
  function adapt() {
    const now = performance.now(), dt = now - last; last = now;
    if (dt > 250) return; // tab was hidden
    frames++; acc += dt;
    if (frames >= 90) {
      const avg = acc / frames; frames = 0; acc = 0;
      if (avg > 30 && stage.quality > 0) {
        stage.quality--;
        if (stage.quality === 1) { dpr = Math.min(dpr, 1.25); renderer.setPixelRatio(dpr); key.shadow.radius = 2; }
        if (stage.quality === 0) { dpr = 1; renderer.setPixelRatio(1); renderer.shadowMap.enabled = false; }
        const w = stage.width, h = stage.height; stage.width = 0; stage.resize(w, h);
      }
    }
  }
  return stage;
}

// Hand-held camera + decaying shake, applied on top of any base path.
function applyCamera(camera, pos, target, fov, time, handheld = 0.04, shake = 0) {
  const h = handheld, s = shake;
  camera.position.set(
    pos.x + hnoise(time * 0.7, 1) * h + hnoise(time * 23, 4) * s,
    pos.y + hnoise(time * 0.6, 2) * h * 0.7 + hnoise(time * 29, 5) * s,
    pos.z + hnoise(time * 0.5, 3) * h,
  );
  camera.lookAt(
    target.x + hnoise(time * 0.8, 7) * h * 0.5 + hnoise(time * 31, 8) * s * 0.6,
    target.y + hnoise(time * 0.9, 9) * h * 0.4 + hnoise(time * 27, 6) * s * 0.6,
    target.z,
  );
  camera.rotateZ(hnoise(time * 0.4, 11) * h * 0.05 + hnoise(time * 19, 12) * s * 0.05);
  if (Math.abs(camera.fov - fov) > 1e-3) { camera.fov = fov; camera.updateProjectionMatrix(); }
}

// --------------------------------------------------------------- materials --
const MAT = {
  ceramic: (c, rough = 0.42) => new THREE.MeshPhysicalMaterial({
    color: c, roughness: rough, metalness: 0, clearcoat: 0.55, clearcoatRoughness: 0.32,
    sheen: 0.35, sheenColor: new THREE.Color(0xffffff), sheenRoughness: 0.6,
  }),
  // "real" glass uses the transmission pass; cheap glass is a clear-coated
  // transparent shell, which reads the same at small sizes and costs nothing.
  glass: (c, real = false) => real
    ? new THREE.MeshPhysicalMaterial({
        color: 0xffffff, transmission: 1, thickness: 0.7, roughness: 0.05, ior: 1.46,
        attenuationColor: new THREE.Color(c), attenuationDistance: 1.1,
        clearcoat: 1, clearcoatRoughness: 0.04, envMapIntensity: 1.3, specularIntensity: 1,
      })
    : new THREE.MeshPhysicalMaterial({
        color: c, transparent: true, opacity: 0.2, roughness: 0.05, metalness: 0,
        clearcoat: 1, clearcoatRoughness: 0.04, envMapIntensity: 1.8, depthWrite: false,
      }),
  glow: (c, i = 3) => new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: i, roughness: 0.35, toneMapped: true }),
  metal: (c, rough = 0.22) => new THREE.MeshStandardMaterial({ color: c, metalness: 0.9, roughness: rough }),
  line: (c = PAL.ink, op = 0.25) => new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: op, depthWrite: false }),
  sprite: (tex, op = 1) => new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: op, depthWrite: false, fog: false }),
};

// Soft round particles with per-point colour, alpha and size.
function makePoints(stage, n, { size = 0.12, blending = THREE.NormalBlending, depthTest = true } = {}) {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(n * 3), col = new Float32Array(n * 3), alpha = new Float32Array(n), sz = new Float32Array(n).fill(1);
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3).setUsage(THREE.DynamicDrawUsage));
  geo.setAttribute('aColor', new THREE.BufferAttribute(col, 3).setUsage(THREE.DynamicDrawUsage));
  geo.setAttribute('aAlpha', new THREE.BufferAttribute(alpha, 1).setUsage(THREE.DynamicDrawUsage));
  geo.setAttribute('aSize', new THREE.BufferAttribute(sz, 1).setUsage(THREE.DynamicDrawUsage));
  const mat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, depthTest, blending,
    uniforms: { uSize: { value: size }, uScale: { value: 500 } },
    vertexShader: `attribute vec3 aColor; attribute float aAlpha; attribute float aSize;
      uniform float uSize, uScale; varying vec3 vC; varying float vA;
      void main(){ vC = aColor; vA = aAlpha;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = max(1.0, uSize * aSize * uScale / -mv.z);
        gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `varying vec3 vC; varying float vA;
      void main(){ float d = length(gl_PointCoord - 0.5);
        float a = pow(smoothstep(0.5, 0.0, d), 1.5) * vA;
        if (a < 0.004) discard;
        gl_FragColor = vec4(vC, a);
        #include <tonemapping_fragment>
        #include <colorspace_fragment> }`,
  });
  stage.pointMats.push(mat);
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  return {
    points, geo, pos, col, alpha, sz, n, mat,
    commit() {
      for (const k of ['position', 'aColor', 'aAlpha', 'aSize']) geo.attributes[k].needsUpdate = true;
    },
  };
}

// ------------------------------------------------------------- text/labels --
function canvasTexture(w, h, draw) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const ctx = c.getContext('2d');
  draw(ctx, w, h);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return { tex, canvas: c, ctx, redraw(fn) { ctx.clearRect(0, 0, w, h); fn(ctx, w, h); tex.needsUpdate = true; } };
}

function roundRectPath(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

// A floating pill label: title plus an optional mono subtitle.
function makeLabel(title, sub = '', { color = CSS.ink, accent = CSS.lav, height = 0.55, pill = true } = {}) {
  const W = 640, H = sub ? 200 : 140;
  const t = canvasTexture(W, H, (ctx) => {
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `700 64px ${FONT_HEAD}`;
    const tw = Math.min(W - 24, Math.max(ctx.measureText(title).width + 90, sub ? 380 : 0));
    if (pill) {
      roundRectPath(ctx, (W - tw) / 2, 8, tw, H - 16, (H - 16) / 2);
      ctx.fillStyle = 'rgba(246,247,253,0.86)'; ctx.fill();
      ctx.lineWidth = 3; ctx.strokeStyle = accent + '66'; ctx.stroke();
    }
    ctx.fillStyle = color;
    ctx.fillText(title, W / 2, sub ? 76 : H / 2 + 2);
    if (sub) { ctx.font = `500 34px ${FONT_MONO}`; ctx.fillStyle = accent; ctx.fillText(sub, W / 2, 142); }
  });
  const s = new THREE.Sprite(MAT.sprite(t.tex));
  s.scale.set(height * (W / H), height, 1);
  s.renderOrder = 20;
  return s;
}

function makeGlyph(text, { color = CSS.ink, font = `700 96px ${FONT_HEAD}`, size = 0.5, ring = null } = {}) {
  const t = canvasTexture(160, 160, (ctx, w, h) => {
    if (ring) {
      ctx.beginPath(); ctx.arc(w / 2, h / 2, 70, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(246,247,253,0.92)'; ctx.fill();
      ctx.lineWidth = 8; ctx.strokeStyle = ring; ctx.stroke();
    }
    ctx.fillStyle = color; ctx.font = font; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(text, w / 2, h / 2 + 6);
  });
  const s = new THREE.Sprite(MAT.sprite(t.tex));
  s.scale.setScalar(size);
  s.renderOrder = 21;
  return s;
}

// A soft radial flash sprite (Bell measurements, bursts, impacts).
let _flashTex = null;
function flashTexture() {
  if (_flashTex) return _flashTex;
  _flashTex = canvasTexture(256, 256, (ctx, w, h) => {
    const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.25, 'rgba(255,255,255,0.55)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  }).tex;
  return _flashTex;
}
function makeFlash(color) {
  const m = new THREE.SpriteMaterial({ map: flashTexture(), color, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, fog: false });
  const s = new THREE.Sprite(m);
  s.renderOrder = 30;
  return s;
}

// Expanding floor/space shockwave ring.
function makeShockwave(color) {
  const m = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide });
  const r = new THREE.Mesh(new THREE.RingGeometry(0.92, 1, 96), m);
  r.renderOrder = 5;
  r.set = (p, maxR = 6) => { // p in [0,1]
    r.visible = p > 0 && p < 1;
    r.scale.setScalar(0.01 + ease.outCubic(p) * maxR);
    m.opacity = (1 - p) * 0.7;
  };
  r.visible = false;
  return r;
}

// ------------------------------------------------------------------ models --

// Arrow for a Bloch vector: shaft + cone + glowing tip.
function makeArrow(r, color, { opacity = 1, glow = 1.4 } = {}) {
  const g = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: glow, roughness: 0.3, transparent: opacity < 1, opacity });
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.035, r * 0.035, r * 0.8, 14), mat);
  shaft.position.y = r * 0.4;
  const tip = new THREE.Mesh(new THREE.ConeGeometry(r * 0.095, r * 0.22, 24), mat);
  tip.position.y = r * 0.89;
  g.add(shaft, tip);
  g.userData.mat = mat;
  g.setDir = (v, len = 1) => {
    const d = v.clone();
    if (d.lengthSq() < 1e-8) d.set(0, 1, 0);
    g.quaternion.setFromUnitVectors(UP, d.normalize());
    g.scale.set(1, Math.max(0.02, len), 1);
  };
  return g;
}

// Bloch sphere: glass shell, great circles, axes and a state arrow.
function makeBloch(r = 1, { color = PAL.sky, arrowColor = PAL.lav, real = false, axes = true } = {}) {
  const g = new THREE.Group();
  const shell = new THREE.Mesh(new THREE.SphereGeometry(r, 64, 40), MAT.glass(color, real));
  shell.castShadow = real;
  g.add(shell);
  const ringMat = MAT.line(PAL.inkSoft, 0.3);
  for (const [rx, ry] of [[Math.PI / 2, 0], [0, 0], [0, Math.PI / 2]]) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(r, r * 0.008, 6, 128), ringMat);
    ring.rotation.set(rx, ry, 0);
    g.add(ring);
  }
  if (axes) {
    const axMat = MAT.line(PAL.inkSoft, 0.28);
    for (const rot of [[0, 0, 0], [0, 0, Math.PI / 2], [Math.PI / 2, 0, 0]]) {
      const ax = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.007, r * 0.007, r * 2.3, 6), axMat);
      ax.rotation.set(...rot);
      g.add(ax);
    }
  }
  const arrow = makeArrow(r, arrowColor);
  g.add(arrow);
  const core = new THREE.Mesh(new THREE.SphereGeometry(r * 0.07, 16, 12), MAT.glow(arrowColor, 1.2));
  g.add(core);
  g.userData = { shell, arrow, core, r };
  return g;
}

// Alice's and Bob's stations: lathe-turned ceramic pedestal, a crown of
// prongs, gyroscope rings and a transmissive glass orb with a glowing core.
function makeStation(color, title, sub) {
  const g = new THREE.Group();
  const c = new THREE.Color(color);
  const light = c.clone().lerp(new THREE.Color(0xF7F7FC), 0.62);
  const prof = [[0, 0], [1.55, 0], [1.66, 0.05], [1.71, 0.18], [1.67, 0.33], [1.5, 0.4], [1.06, 0.46], [0.74, 0.58],
    [0.57, 0.9], [0.52, 1.5], [0.6, 1.66], [0.88, 1.76], [0.95, 1.86], [0.9, 1.95], [0, 1.97]].map((p) => new THREE.Vector2(p[0], p[1]));
  const body = new THREE.Mesh(new THREE.LatheGeometry(prof, 128), MAT.ceramic(light));
  body.castShadow = true; body.receiveShadow = true;
  g.add(body);
  const bandMat = MAT.glow(color, 2.0);
  const band = new THREE.Mesh(new THREE.TorusGeometry(1.712, 0.026, 12, 160), bandMat);
  band.rotation.x = Math.PI / 2; band.position.y = 0.2;
  const band2 = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.02, 10, 120), bandMat);
  band2.rotation.x = Math.PI / 2; band2.position.y = 1.93;
  g.add(band, band2);
  for (let i = 0; i < 3; i++) {
    const a = (i / 3) * Math.PI * 2 + Math.PI / 6;
    const p = new THREE.Mesh(new THREE.CapsuleGeometry(0.052, 0.6, 6, 16), MAT.ceramic(light, 0.35));
    p.position.set(Math.cos(a) * 0.6, 2.28, Math.sin(a) * 0.6);
    p.quaternion.setFromAxisAngle(V3(Math.sin(a), 0, -Math.cos(a)), 0.36);
    p.castShadow = true;
    g.add(p);
  }
  const orbY = 2.66;
  // Layered glass instead of the transmission pass: a clear-coated shell over a
  // softly glowing inner orb. It reads the same and costs no extra scene render.
  const orbMat = MAT.glass(color, false);
  orbMat.opacity = 0.34; orbMat.envMapIntensity = 2.2;
  const orb = new THREE.Mesh(new THREE.SphereGeometry(0.46, 64, 48), orbMat);
  orb.position.y = orbY;
  const inner = new THREE.Mesh(new THREE.SphereGeometry(0.36, 48, 32), new THREE.MeshStandardMaterial({
    color: light, emissive: color, emissiveIntensity: 0.55, roughness: 0.25, transparent: true, opacity: 0.6, depthWrite: false }));
  inner.position.y = orbY;
  const core = new THREE.Mesh(new THREE.SphereGeometry(0.16, 32, 24), MAT.glow(color, 3.5));
  core.position.y = orbY;
  g.add(inner, core, orb);
  const gyro = new THREE.Group();
  gyro.position.y = orbY;
  const gyroMat = MAT.metal(light, 0.18);
  const r1 = new THREE.Mesh(new THREE.TorusGeometry(0.68, 0.013, 8, 160), gyroMat);
  const r2 = new THREE.Mesh(new THREE.TorusGeometry(0.76, 0.011, 8, 160), gyroMat);
  gyro.add(r1, r2);
  g.add(gyro);
  const label = makeLabel(title, sub, { accent: '#' + c.getHexString(), height: 0.95 });
  label.position.y = 4.15;
  g.add(label);
  const flash = makeFlash(color);
  flash.position.y = orbY;
  g.add(flash);
  return {
    group: g, orb, core, gyro, label, flash, bandMat, orbY,
    orbWorld: () => g.localToWorld(V3(0, orbY, 0)),
    update(time, energy = 1) {
      r1.rotation.set(time * 0.9, time * 0.35, 0);
      r2.rotation.set(Math.PI / 2 + time * 0.25, 0, time * 1.2);
      core.material.emissiveIntensity = (2.4 + Math.sin(time * 2.4) * 0.6) * energy;
      bandMat.emissiveIntensity = 1.2 + energy * 0.9;
      label.position.y = 4.15 + Math.sin(time * 1.3) * 0.05;
    },
  };
}

// The message: a frosted card with live, typeable canvas content.
function makeCard(message, digest) {
  const g = new THREE.Group();
  const w = 3.4, h = 2.1, r = 0.2;
  const shape = new THREE.Shape();
  shape.moveTo(-w / 2 + r, -h / 2); shape.lineTo(w / 2 - r, -h / 2); shape.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  shape.lineTo(w / 2, h / 2 - r); shape.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  shape.lineTo(-w / 2 + r, h / 2); shape.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  shape.lineTo(-w / 2, -h / 2 + r); shape.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  const geo = new THREE.ExtrudeGeometry(shape, { depth: 0.04, bevelEnabled: true, bevelThickness: 0.025, bevelSize: 0.025, bevelSegments: 5, curveSegments: 16 });
  geo.center();
  const bodyMat = new THREE.MeshPhysicalMaterial({
    color: 0xF6F5FD, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.12,
    sheen: 0.5, sheenColor: new THREE.Color(PAL.lavLight), transparent: true, opacity: 1,
  });
  const body = new THREE.Mesh(geo, bodyMat);
  body.castShadow = true;
  g.add(body);
  const face = canvasTexture(1024, 632, () => {});
  const faceMat = new THREE.MeshBasicMaterial({ map: face.tex, transparent: true, depthWrite: false, toneMapped: false });
  const facePlane = new THREE.Mesh(new THREE.PlaneGeometry(w - 0.06, h - 0.06), faceMat);
  facePlane.position.z = 0.05;
  g.add(facePlane);
  let lastKey = '';
  function draw(chars, digestReveal = 0, sigReveal = 0, stamp = '') {
    const key = `${chars}|${Math.round(digestReveal * 64)}|${Math.round(sigReveal * 40)}|${stamp}`;
    if (key === lastKey) return;
    lastKey = key;
    face.redraw((ctx, W, H) => {
      ctx.fillStyle = CSS.lav; ctx.font = `600 30px ${FONT_MONO}`; ctx.textBaseline = 'alphabetic';
      ctx.fillText('MESSAGE  ·  alice → bob', 56, 84);
      ctx.fillStyle = 'rgba(30,36,64,0.12)'; ctx.fillRect(56, 106, W - 112, 3);
      ctx.fillStyle = CSS.ink; ctx.font = `600 64px ${FONT_MONO}`;
      const txt = message.slice(0, chars);
      ctx.fillText(txt, 56, 236);
      if (chars < message.length || Math.floor(performance.now() / 420) % 2 === 0) {
        const tw = ctx.measureText(txt).width;
        ctx.fillStyle = CSS.lav; ctx.fillRect(60 + tw, 186, 6, 62);
      }
      if (digestReveal > 0) {
        ctx.fillStyle = CSS.inkSoft; ctx.font = `600 26px ${FONT_MONO}`;
        ctx.fillText('SHA-256', 56, 330);
        ctx.fillStyle = CSS.sky; ctx.font = `500 30px ${FONT_MONO}`;
        const n = Math.round(digestReveal * 64);
        ctx.fillText(digest.slice(0, Math.min(n, 32)), 56, 378);
        if (n > 32) ctx.fillText(digest.slice(32, n), 56, 420);
      }
      if (sigReveal > 0) {
        ctx.strokeStyle = CSS.lav; ctx.lineWidth = 6; ctx.lineCap = 'round';
        ctx.beginPath();
        const steps = Math.round(sigReveal * 40);
        for (let i = 0; i <= steps; i++) {
          const x = 560 + i * 9, y = 540 + Math.sin(i * 0.9) * 26 * Math.sin(i * 0.13 + 0.4) - i * 0.6;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.fillStyle = CSS.inkSoft; ctx.font = `600 24px ${FONT_MONO}`;
        ctx.fillText('QDS · signed by alice', 56, 560);
      }
      if (stamp) {
        ctx.save(); ctx.translate(W - 230, 180); ctx.rotate(-0.22);
        ctx.strokeStyle = CSS.coral; ctx.lineWidth = 8; roundRectPath(ctx, -150, -56, 300, 112, 20); ctx.stroke();
        ctx.fillStyle = CSS.coral; ctx.font = `700 60px ${FONT_HEAD}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(stamp, 0, 4); ctx.restore();
      }
    });
  }
  draw(0);
  return { group: g, body, bodyMat, faceMat, draw, w, h };
}

// One texture per hex digit, reused by every glyph sprite.
function makeHexTextures() {
  const out = {};
  for (const ch of '0123456789abcdef') {
    out[ch] = canvasTexture(96, 96, (ctx, w, h) => {
      ctx.fillStyle = CSS.sky; ctx.font = `700 70px ${FONT_MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(ch, w / 2, h / 2 + 4);
    }).tex;
  }
  return out;
}

// The quantum fibre: glass tube with a glowing core that can grow along its length.
function makeFiber(curve, { radius = 0.075, color = PAL.sky } = {}) {
  const g = new THREE.Group();
  const outer = new THREE.Mesh(new THREE.TubeGeometry(curve, 220, radius, 20, false), new THREE.MeshPhysicalMaterial({
    color: PAL.skyLight, transparent: true, opacity: 0.55, roughness: 0.08, clearcoat: 1, clearcoatRoughness: 0.05, envMapIntensity: 1.6, depthWrite: false,
  }));
  const coreMat = MAT.glow(color, 1.1);
  const inner = new THREE.Mesh(new THREE.TubeGeometry(curve, 220, radius * 0.28, 8, false), coreMat);
  outer.castShadow = true;
  g.add(inner, outer);
  const nOuter = outer.geometry.index.count, nInner = inner.geometry.index.count;
  return {
    group: g, curve, outer, inner, coreMat,
    setGrow(p) {
      p = clamp(p);
      g.visible = p > 0.001;
      outer.geometry.setDrawRange(0, Math.floor((nOuter * p) / 6) * 6);
      inner.geometry.setDrawRange(0, Math.floor((nInner * p) / 6) * 6);
    },
    rebuild(newCurve) { // legacy: full rebuild (allocates; prefer deform)
      outer.geometry.dispose(); inner.geometry.dispose();
      outer.geometry = new THREE.TubeGeometry(newCurve, 90, radius, 14, false);
      inner.geometry = new THREE.TubeGeometry(newCurve, 90, radius * 0.28, 6, false);
    },
    // Physically disturb the channel without allocating: offset each ring of
    // the tube by fn(u) -> [dx, dy, dz]. Tube vertices are laid out ring by
    // ring, (radialSegments + 1) per ring, so the ring index gives u.
    deform(fn) {
      for (const [mesh, radial] of [[outer, 20], [inner, 8]]) {
        const pos = mesh.geometry.attributes.position;
        if (!mesh.userData.base) mesh.userData.base = pos.array.slice();
        const base = mesh.userData.base, per = radial + 1, rings = pos.count / per;
        for (let r = 0; r < rings; r++) {
          const d = fn(r / (rings - 1));
          for (let j = 0; j < per; j++) {
            const k = (r * per + j) * 3;
            pos.array[k] = base[k] + d[0]; pos.array[k + 1] = base[k + 1] + d[1]; pos.array[k + 2] = base[k + 2] + d[2];
          }
        }
        pos.needsUpdate = true;
      }
    },
  };
}

// A travelling light pulse with a comet trail.
function makePulse(stage, color, { size = 0.16, trail = 26 } = {}) {
  const g = new THREE.Group();
  const mat = MAT.glow(color, 4);
  const head = new THREE.Mesh(new THREE.SphereGeometry(size, 24, 16), mat);
  g.add(head);
  const tr = makePoints(stage, trail, { size: size * 2.4 });
  const c = new THREE.Color(color);
  for (let i = 0; i < trail; i++) {
    tr.col[i * 3] = c.r; tr.col[i * 3 + 1] = c.g; tr.col[i * 3 + 2] = c.b;
    tr.sz[i] = 1 - i / trail;
  }
  const hist = [];
  return {
    group: g, head, trail: tr, mat,
    setColor(col) { c.set(col); mat.color.copy(c); mat.emissive.copy(c); for (let i = 0; i < trail; i++) { tr.col[i * 3] = c.r; tr.col[i * 3 + 1] = c.g; tr.col[i * 3 + 2] = c.b; } },
    // Trail is sampled backwards along a curve, so it is a pure function of u.
    placeOnCurve(curve, u, visible = 1, span = 0.06) {
      g.visible = visible > 0.01 && u >= 0 && u <= 1;
      if (!g.visible) { tr.alpha.fill(0); tr.commit(); return; }
      head.position.copy(curve.getPoint(clamp(u)));
      head.scale.setScalar(0.4 + visible * 0.6);
      for (let i = 0; i < trail; i++) {
        const uu = u - (i / trail) * span;
        const p = curve.getPoint(clamp(uu));
        tr.pos[i * 3] = p.x; tr.pos[i * 3 + 1] = p.y; tr.pos[i * 3 + 2] = p.z;
        tr.alpha[i] = uu < 0 ? 0 : visible * 0.55 * (1 - i / trail);
      }
      tr.commit();
    },
    // Free-flight trail from a position history.
    placeAt(p, visible = 1) {
      g.visible = visible > 0.01;
      head.position.copy(p);
      hist.unshift(p.clone()); if (hist.length > trail) hist.pop();
      for (let i = 0; i < trail; i++) {
        const q = hist[Math.min(i, hist.length - 1)];
        tr.pos[i * 3] = q.x; tr.pos[i * 3 + 1] = q.y; tr.pos[i * 3 + 2] = q.z;
        tr.alpha[i] = visible * 0.5 * (1 - i / trail);
      }
      tr.commit();
    },
    resetTrail() { hist.length = 0; },
  };
}

// Double helix of light between two points along a curve: entanglement.
function makeHelix(stage, n = 220) {
  const P = makePoints(stage, n, { size: 0.11 });
  const cA = new THREE.Color(PAL.sky), cB = new THREE.Color(PAL.lav);
  for (let i = 0; i < n; i++) {
    const c = i % 2 ? cA : cB;
    P.col[i * 3] = c.r; P.col[i * 3 + 1] = c.g; P.col[i * 3 + 2] = c.b;
  }
  const tmpT = V3(), tmpN = V3(), tmpB = V3();
  return {
    points: P.points,
    // Draw between curve params u0..u1 with visibility a.
    set(curve, u0, u1, a, time) {
      const half = n / 2;
      for (let i = 0; i < n; i++) {
        const strand = i % 2, k = Math.floor(i / 2) / (half - 1);
        const u = lerp(u0, u1, k);
        const p = curve.getPoint(clamp(u));
        curve.getTangent(clamp(u), tmpT);
        tmpN.crossVectors(tmpT, UP).normalize();
        tmpB.crossVectors(tmpN, tmpT).normalize();
        const ang = k * Math.PI * 10 - time * 3 + strand * Math.PI;
        const rad = 0.32 * Math.sin(Math.PI * k) + 0.04;
        P.pos[i * 3] = p.x + (tmpN.x * Math.cos(ang) + tmpB.x * Math.sin(ang)) * rad;
        P.pos[i * 3 + 1] = p.y + (tmpN.y * Math.cos(ang) + tmpB.y * Math.sin(ang)) * rad;
        P.pos[i * 3 + 2] = p.z + (tmpN.z * Math.cos(ang) + tmpB.z * Math.sin(ang)) * rad;
        P.alpha[i] = a * (0.35 + 0.65 * Math.sin(Math.PI * k));
      }
      P.commit();
    },
  };
}

// Eve: a spiked obsidian geode with coral fissures and grasping tendrils.
function makeEve(stage) {
  const g = new THREE.Group();
  const body = new THREE.Group();
  g.add(body);
  const geo = new THREE.IcosahedronGeometry(1, 5);
  const R = rng(1337), spikes = [];
  for (let i = 0; i < 26; i++) spikes.push(V3(R() * 2 - 1, R() * 2 - 1, R() * 2 - 1).normalize());
  const pos = geo.attributes.position, v = V3(), base = new Float32Array(pos.array);
  const crack = new Float32Array(pos.count);
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i).normalize();
    let d = 0;
    for (const s of spikes) d += Math.pow(Math.max(0, v.dot(s)), 48) * 0.95;
    const n = Math.sin(v.x * 9.1) * Math.sin(v.y * 7.3) * Math.sin(v.z * 8.7);
    crack[i] = Math.pow(1 - Math.abs(n), 18);
    v.multiplyScalar(0.8 + d + n * 0.04);
    pos.setXYZ(i, v.x, v.y, v.z);
  }
  geo.computeVertexNormals();
  geo.setAttribute('aCrack', new THREE.BufferAttribute(crack, 1));
  const mat = new THREE.MeshPhysicalMaterial({ color: PAL.obsidian, metalness: 0.55, roughness: 0.22, clearcoat: 1, clearcoatRoughness: 0.1, emissive: PAL.coral, emissiveIntensity: 0 });
  const uPulse = { value: 0 }, uCrack = { value: 0 };
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uPulse = uPulse; sh.uniforms.uCrack = uCrack;
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nattribute float aCrack; varying float vCrack;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvCrack = aCrack;');
    // uCrack (0..1) spreads glowing fractures outward from the fissure lines.
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying float vCrack; uniform float uPulse; uniform float uCrack;')
      .replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\nfloat spread = smoothstep(1.0 - uCrack, 1.0 - uCrack + 0.04, pow(vCrack, 0.12));\ntotalEmissiveRadiance = emissive * (vCrack * (1.6 + 2.6 * uPulse) + spread * (2.0 + 7.0 * uCrack));');
  };
  const shell = new THREE.Mesh(geo, mat);
  shell.castShadow = true;
  body.add(shell);
  const eye = new THREE.Mesh(new THREE.TorusGeometry(1.32, 0.03, 10, 160), MAT.glow(PAL.coral, 3));
  eye.rotation.x = Math.PI / 2.3;
  body.add(eye);
  const label = makeLabel('EVE', 'adversary', { accent: CSS.coral, height: 0.55 });
  label.position.y = 2.3;
  g.add(label);
  // Tendrils: chains of instanced beads, moved in place every frame (no allocation).
  const tendrilMat = new THREE.MeshPhysicalMaterial({ color: PAL.obsidian, metalness: 0.4, roughness: 0.3, emissive: PAL.coral, emissiveIntensity: 0.7, clearcoat: 0.8 });
  const BEADS = 34;
  const beads = new THREE.InstancedMesh(new THREE.SphereGeometry(0.085, 12, 8), tendrilMat, 3 * BEADS);
  beads.castShadow = true; beads.frustumCulled = false;
  beads.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  stage.scene.add(beads);
  const tendrils = [beads];
  const _m4 = new THREE.Matrix4(), _q = new THREE.Quaternion(), _s = V3(), _p = V3(), _from = V3();
  return {
    group: g, body, shell, mat, eye, label, tendrils, uPulse, uCrack, basePos: base,
    update(time, pulse = 0) {
      body.rotation.y = time * 0.35;
      body.rotation.x = Math.sin(time * 0.6) * 0.25;
      eye.rotation.z = time * 1.4;
      const br = 1 + Math.sin(time * 3.1) * 0.035;
      shell.scale.set(br, 1 / br, br);
      uPulse.value = pulse;
    },
    // Grip points in world space; reach in [0,1].
    setTendrils(targets, reach, time) {
      g.getWorldPosition(_from);
      beads.visible = reach > 0.01 && g.visible;
      if (!beads.visible) return;
      for (let i = 0; i < 3; i++) {
        const to = targets[i % targets.length], on = i < targets.length;
        for (let k = 0; k < BEADS; k++) {
          const u = k / (BEADS - 1), uu = u * reach, env = Math.sin(Math.PI * u);
          _p.copy(_from).lerp(to, uu);
          _p.x += Math.sin(time * 2.2 + i * 2 + u * 5) * 0.55 * env;
          _p.z += Math.cos(time * 1.7 + i + u * 4) * 0.35 * env;
          _p.y += Math.sin(Math.PI * uu) * 0.6;
          _s.setScalar(on ? (1.15 - 0.75 * u) * (0.9 + 0.1 * Math.sin(time * 9 - k)) : 0.0001); // tapered, pulsing
          _m4.compose(_p, _q, _s);
          beads.setMatrixAt(i * BEADS + k, _m4);
        }
      }
      beads.instanceMatrix.needsUpdate = true;
    },
  };
}

// Obsidian shards with ballistic physics: gravity, drag, spin, floor bounce.
function makeShards(stage, n = 70, seed = 7) {
  const geo = new THREE.TetrahedronGeometry(0.14, 0);
  const mat = new THREE.MeshPhysicalMaterial({ color: PAL.obsidian, metalness: 0.55, roughness: 0.22, clearcoat: 1, emissive: PAL.coral, emissiveIntensity: 0.5 });
  const mesh = new THREE.InstancedMesh(geo, mat, n);
  mesh.castShadow = true;
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.frustumCulled = false;
  const R = rng(seed);
  const init = [];
  for (let i = 0; i < n; i++) {
    const dir = V3(R() * 2 - 1, R() * 1.4 - 0.2, R() * 2 - 1).normalize();
    init.push({
      off: dir.clone().multiplyScalar(0.3 + R() * 0.7),
      vel: dir.clone().multiplyScalar(3 + R() * 6).add(V3(0, 2 + R() * 3, 0)),
      spin: V3(R() * 14 - 7, R() * 14 - 7, R() * 14 - 7),
      scale: 0.5 + R() * 1.3,
    });
  }
  const state = init.map(() => ({ p: V3(), v: V3(), rot: new THREE.Euler(), w: V3(), rest: false }));
  let simT = -1, origin = V3();
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = V3();
  function reset(o) {
    origin.copy(o); simT = 0;
    state.forEach((s, i) => { s.p.copy(o).add(init[i].off); s.v.copy(init[i].vel); s.w.copy(init[i].spin); s.rot.set(0, 0, 0); s.rest = false; });
  }
  function step(h) {
    for (const s of state) {
      if (s.rest) continue;
      s.v.y -= 9.8 * h;
      s.v.multiplyScalar(1 - 0.35 * h);
      s.p.addScaledVector(s.v, h);
      s.rot.x += s.w.x * h; s.rot.y += s.w.y * h; s.rot.z += s.w.z * h;
      if (s.p.y < 0.12) {
        s.p.y = 0.12;
        if (Math.abs(s.v.y) < 0.6) { s.v.set(0, 0, 0); s.rest = true; }
        else { s.v.y = -s.v.y * 0.36; s.v.x *= 0.62; s.v.z *= 0.62; s.w.multiplyScalar(0.55); }
      }
    }
  }
  return {
    mesh,
    // Deterministic: re-simulates from the break when time runs backwards.
    set(o, t, fade = 1) {
      mesh.visible = t > 0 && fade > 0.01;
      if (!mesh.visible) { simT = -1; return; }
      if (simT < 0 || t < simT - 1e-6 || !o.equals(origin)) reset(o);
      const h = 1 / 120;
      while (simT + h <= t) { step(h); simT += h; }
      state.forEach((s, i) => {
        q.setFromEuler(s.rot);
        sc.setScalar(init[i].scale * fade);
        m4.compose(s.p, q, sc);
        mesh.setMatrixAt(i, m4);
      });
      mesh.instanceMatrix.needsUpdate = true;
      mat.emissiveIntensity = 0.04 + Math.max(0, 1 - t) * 0.9; // embers cool as they fall
    },
  };
}

// Hexagonal containment cage (edges + fresnel shell).
function makeCage(color = PAL.mint, r = 1.9) {
  const g = new THREE.Group();
  const ico = new THREE.IcosahedronGeometry(r, 1);
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(ico), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9 }));
  const nodes = new THREE.InstancedMesh(new THREE.SphereGeometry(0.05, 10, 8), MAT.glow(color, 2.5), ico.attributes.position.count);
  const m4 = new THREE.Matrix4(), p = V3();
  for (let i = 0; i < ico.attributes.position.count; i++) { p.fromBufferAttribute(ico.attributes.position, i); m4.makeTranslation(p.x, p.y, p.z); nodes.setMatrixAt(i, m4); }
  const shellU = { uColor: { value: new THREE.Color(color) }, uA: { value: 0 } };
  const shell = new THREE.Mesh(new THREE.SphereGeometry(r * 0.98, 48, 32), new THREE.ShaderMaterial({
    uniforms: shellU, transparent: true, depthWrite: false, side: THREE.DoubleSide,
    vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix*vec4(position,1.); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }',
    fragmentShader: `uniform vec3 uColor; uniform float uA; varying vec3 vN; varying vec3 vV;
      void main(){ float f = pow(1.0 - abs(dot(vN, vV)), 2.5); gl_FragColor = vec4(uColor, f * uA);
      #include <tonemapping_fragment>
      #include <colorspace_fragment> }`,
  }));
  g.add(shell, edges, nodes);
  return {
    group: g,
    set(p, a = 1) { // p: build progress, a: opacity
      g.visible = p > 0.001 && a > 0.001;
      g.scale.setScalar(Math.max(0.001, p));
      edges.material.opacity = 0.85 * a;
      shellU.uA.value = 0.55 * a;
      nodes.visible = a > 0.05;
    },
  };
}

// Instanced 3D arc gauge with a threshold notch (anomaly score vs τ).
function makeGauge(r = 1.4, segs = 48) {
  const g = new THREE.Group();
  const geo = new RoundedBoxGeometry(0.1, 0.26, 0.08, 2, 0.02);
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.4, metalness: 0, emissiveIntensity: 0 });
  const mesh = new THREE.InstancedMesh(geo, mat, segs);
  const colors = [];
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s = V3(1, 1, 1);
  const baseC = new THREE.Color(0xD5DAEA);
  for (let i = 0; i < segs; i++) {
    const a = Math.PI * (1 - i / (segs - 1));
    q.setFromAxisAngle(V3(0, 0, 1), a - Math.PI / 2);
    m4.compose(V3(Math.cos(a) * r, Math.sin(a) * r, 0), q, s);
    mesh.setMatrixAt(i, m4);
    mesh.setColorAt(i, baseC);
    colors.push(new THREE.Color().lerpColors(new THREE.Color(PAL.mint), new THREE.Color(PAL.coral), i / (segs - 1)));
  }
  g.add(mesh);
  const notch = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.55, 0.12), new THREE.MeshStandardMaterial({ color: PAL.ink, roughness: 0.5 }));
  g.add(notch);
  const tau = makeGlyph('τ', { color: CSS.ink, size: 0.42 });
  g.add(tau);
  const readout = canvasTexture(512, 160, () => {});
  const val = new THREE.Sprite(MAT.sprite(readout.tex));
  val.scale.set(1.9, 0.6, 1);
  val.position.y = 0.35;
  g.add(val);
  let lastTxt = '';
  return {
    group: g,
    set(fill, thr, text = '', alertColor = CSS.coral) {
      const k = Math.round(clamp(fill) * segs);
      for (let i = 0; i < segs; i++) mesh.setColorAt(i, i < k ? colors[i] : baseC);
      mesh.instanceColor.needsUpdate = true;
      const a = Math.PI * (1 - clamp(thr));
      notch.position.set(Math.cos(a) * r, Math.sin(a) * r, 0.02);
      notch.rotation.z = a - Math.PI / 2;
      tau.position.set(Math.cos(a) * (r + 0.5), Math.sin(a) * (r + 0.5), 0);
      if (text !== lastTxt) {
        lastTxt = text;
        readout.redraw((ctx, w, h) => {
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.font = `700 84px ${FONT_MONO}`; ctx.fillStyle = fill > thr ? alertColor : CSS.ink;
          ctx.fillText(text, w / 2, h / 2);
        });
      }
    },
  };
}

// Pastel dust drifting through the whole world.
function makeDust(stage, n = 900, spread = [60, 16, 44], seed = 3) {
  const P = makePoints(stage, n, { size: 0.09 });
  const R = rng(seed), base = new Float32Array(n * 3), ph = new Float32Array(n);
  const cols = [PAL.lav, PAL.sky, PAL.mint, PAL.peach, PAL.lavLight].map((c) => new THREE.Color(c));
  for (let i = 0; i < n; i++) {
    base[i * 3] = (R() - 0.5) * spread[0]; base[i * 3 + 1] = R() * spread[1]; base[i * 3 + 2] = (R() - 0.5) * spread[2];
    ph[i] = R() * 100;
    const c = cols[i % cols.length];
    P.col[i * 3] = c.r; P.col[i * 3 + 1] = c.g; P.col[i * 3 + 2] = c.b;
    P.sz[i] = 0.4 + R() * 1.2;
  }
  return {
    points: P.points, P, base,
    update(time, alpha = 0.6, alert = 0) {
      const cc = new THREE.Color(PAL.coral);
      for (let i = 0; i < n; i++) {
        const t = time * 0.12 + ph[i];
        P.pos[i * 3] = base[i * 3] + Math.sin(t * 0.7) * 0.8 + Math.sin(t * 1.9) * 0.2;
        P.pos[i * 3 + 1] = base[i * 3 + 1] + Math.sin(t * 0.9 + 1) * 0.6;
        P.pos[i * 3 + 2] = base[i * 3 + 2] + Math.cos(t * 0.6) * 0.8;
        P.alpha[i] = alpha * (0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * 2.3)));
        if (alert > 0 && i % 3 === 0) {
          const c = cols[i % cols.length];
          P.col[i * 3] = lerp(c.r, cc.r, alert); P.col[i * 3 + 1] = lerp(c.g, cc.g, alert); P.col[i * 3 + 2] = lerp(c.b, cc.b, alert);
        }
      }
      P.commit();
    },
  };
}

// Particle wordmark: samples glyph pixels from a canvas and flies particles in.
function makeWordmark(stage, text = 'QVERIS', width = 12, n = 2600, seed = 11) {
  const W = 1400, H = 340;
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#000'; ctx.font = `700 260px ${FONT_HEAD}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(text, W / 2, H / 2 + 10);
  const data = ctx.getImageData(0, 0, W, H).data;
  const cand = [];
  for (let y = 0; y < H; y += 3) for (let x = 0; x < W; x += 3) if (data[(y * W + x) * 4 + 3] > 140) cand.push([x, y]);
  const R = rng(seed);
  const P = makePoints(stage, n, { size: 0.085 });
  const tgt = new Float32Array(n * 3), src = new Float32Array(n * 3), delay = new Float32Array(n);
  const s = width / W;
  const cL = new THREE.Color(PAL.lav), cS = new THREE.Color(PAL.sky), cM = new THREE.Color(PAL.mint), tmp = new THREE.Color();
  for (let i = 0; i < n; i++) {
    const p = cand[Math.floor(R() * cand.length)] || [W / 2, H / 2];
    tgt[i * 3] = (p[0] - W / 2) * s + (R() - 0.5) * s * 2;
    tgt[i * 3 + 1] = -(p[1] - H / 2) * s + (R() - 0.5) * s * 2;
    tgt[i * 3 + 2] = (R() - 0.5) * 0.18;
    const a = R() * Math.PI * 2, b = Math.acos(R() * 2 - 1), rr = 8 + R() * 22;
    src[i * 3] = Math.sin(b) * Math.cos(a) * rr; src[i * 3 + 1] = Math.cos(b) * rr * 0.5 - 5; src[i * 3 + 2] = Math.sin(b) * Math.sin(a) * rr;
    delay[i] = R() * 0.4 + (p[0] / W) * 0.15;
    const k = p[0] / W;
    tmp.lerpColors(cL, cS, clamp(k * 2)).lerp(cM, clamp(k * 2 - 1));
    P.col[i * 3] = tmp.r; P.col[i * 3 + 1] = tmp.g; P.col[i * 3 + 2] = tmp.b;
    P.sz[i] = 0.6 + R() * 0.8;
  }
  const g = new THREE.Group();
  g.add(P.points);
  return {
    group: g,
    set(p, time, alpha = 1) {
      g.visible = p > 0.001 && alpha > 0.001;
      if (!g.visible) return;
      for (let i = 0; i < n; i++) {
        const e = ease.inOutCubic(clamp((p - delay[i]) / 0.55));
        const sw = Math.sin(Math.PI * e) * 2.2;
        const ang = i * 0.37 + time * 0.2;
        P.pos[i * 3] = lerp(src[i * 3], tgt[i * 3], e) + Math.cos(ang) * sw;
        P.pos[i * 3 + 1] = lerp(src[i * 3 + 1], tgt[i * 3 + 1], e) + Math.sin(ang) * sw * 0.6 + (e >= 1 ? Math.sin(time * 2 + i) * 0.012 : 0);
        P.pos[i * 3 + 2] = lerp(src[i * 3 + 2], tgt[i * 3 + 2], e) + Math.sin(ang * 1.3) * sw;
        P.alpha[i] = alpha * (0.2 + 0.8 * e) * (0.85 + 0.15 * Math.sin(time * 3 + i));
      }
      P.commit();
    },
  };
}

// ------------------------------------------------------------- page bridge --
// Our iframe swallows pointer events, so forward them to the parent page's
// cursor layer (dashboard/web/fx.js) to keep one continuous custom cursor.
function bridgeCursor() {
  let fx = null, frame = null;
  try { fx = window.parent.__qvFx; frame = window.frameElement; } catch (e) { return; }
  const get = () => { try { fx = fx || window.parent.__qvFx; } catch (e) {} return fx; };
  const at = (e) => { const r = frame.getBoundingClientRect(); return [e.clientX + r.left, e.clientY + r.top]; };
  document.addEventListener('pointermove', (e) => { const f = get(); if (f && frame) f.bridgeMove(...at(e)); }, { passive: true });
  document.addEventListener('pointerdown', (e) => { const f = get(); if (f && frame) f.bridgeDown(...at(e)); }, { passive: true });
  document.addEventListener('pointerup', () => { const f = get(); if (f) f.bridgeUp(); }, { passive: true });
  document.addEventListener('pointerleave', () => { const f = get(); if (f) f.bridgeHover(0); }, { passive: true });
  return { hover(v) { const f = get(); if (f) f.bridgeHover(v); }, active: () => !!get() };
}

// True while this scene's iframe overlaps the visible page (with a margin).
// Scenes keep polling their data but skip rendering when off-screen, so four
// WebGL panels never compete for the GPU at once.
function frameVisible(margin = 120) {
  try {
    const f = window.frameElement;
    if (!f) return !document.hidden;
    const r = f.getBoundingClientRect(), vh = window.parent.innerHeight;
    return !document.hidden && r.width > 10 && r.bottom > -margin && r.top < vh + margin;
  } catch (e) { return !document.hidden; }
}

async function fontsReady(timeout = 1600) {
  try { await Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, timeout))]); } catch (e) {}
}

// ------------------------------------------------------------- data bus --
// Streamlit reruns publish fresh values through a zero-height component
// (dashboard/components/_web.py: publish). Long-lived scenes poll the bus,
// so a widget change morphs the world instead of reloading the iframe.
function makeBus(channel) {
  let lastV = null;
  return {
    poll() {
      let b = null;
      try { b = window.parent.__qvBus && window.parent.__qvBus[channel]; } catch (e) { b = null; }
      if (!b && QV.initial) b = { v: 'init', d: QV.initial };
      if (!b || b.v === lastV) return null;
      lastV = b.v;
      return b.d;
    },
  };
}

// Ballistic spark burst.
function makeBurst(stage, n, color, seed = 5, speed = 4) {
  const P = makePoints(stage, n, { size: 0.1 });
  const R = rng(seed), vel = [];
  const c = new THREE.Color(color);
  for (let i = 0; i < n; i++) {
    vel.push(V3(R() * 2 - 1, R() * 2 - 1, R() * 2 - 1).normalize().multiplyScalar(speed * (0.4 + R())));
    P.col[i * 3] = c.r; P.col[i * 3 + 1] = c.g; P.col[i * 3 + 2] = c.b; P.sz[i] = 0.5 + R();
  }
  return {
    points: P.points, P,
    set(o, t, life = 1.1, gravity = 0.8) {
      const k = t / life;
      P.points.visible = k > 0 && k < 1;
      if (!P.points.visible) return;
      const d = (1 - Math.exp(-t * 3)) / 3; // velocity with drag
      for (let i = 0; i < n; i++) {
        P.pos[i * 3] = o.x + vel[i].x * d; P.pos[i * 3 + 1] = o.y + vel[i].y * d - gravity * t * t; P.pos[i * 3 + 2] = o.z + vel[i].z * d;
        P.alpha[i] = (1 - k) * 0.9;
      }
      P.commit();
    },
  };
}

// Shared ket label textures (|0⟩ ... |−i⟩).
const _ketTex = {};
function ketTexture(label, color = DARK ? '#DCE0FF' : CSS.ink) {
  const key = label + color;
  if (_ketTex[key]) return _ketTex[key];
  _ketTex[key] = canvasTexture(160, 96, (ctx, w, h) => {
    ctx.fillStyle = color; ctx.font = `700 58px ${FONT_MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(prettyKet(label), w / 2, h / 2 + 4);
  }).tex;
  return _ketTex[key];
}

// Lightweight qubit: glass bead, equator ring and a Bloch arrow.
function makeQubit(r = 0.26, color = PAL.sky, arrowColor = PAL.lav) {
  const g = new THREE.Group();
  const shell = new THREE.Mesh(new THREE.SphereGeometry(r, 24, 16), MAT.glass(color, false));
  const ring = new THREE.Mesh(new THREE.TorusGeometry(r, r * 0.03, 4, 48), MAT.line(PAL.inkSoft, 0.35));
  ring.rotation.x = Math.PI / 2;
  const arrow = makeArrow(r, arrowColor, { glow: 1.2 });
  g.add(shell, ring, arrow);
  g.userData = { shell, arrow, r };
  g.setArrowColor = (c) => { const m = arrow.userData.mat; m.color.set(c); m.emissive.set(c); };
  return g;
}

// A floating document card rendered from a canvas (reports, certificates).
function makeDocCard(w = 3.6, h = 2.3) {
  const t = canvasTexture(1024, Math.round((1024 * h) / w), () => {});
  const mat = new THREE.MeshBasicMaterial({ map: t.tex, transparent: true, depthWrite: false, toneMapped: false, side: THREE.DoubleSide, opacity: 0 });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat);
  mesh.renderOrder = 40;
  return {
    mesh, mat,
    // draw(title, accent colour, rows [[key, value]], wrapped lines, footer)
    draw(title, accent, rows, lines = [], footer = '') {
      t.redraw((ctx, W, H) => {
        roundRectPath(ctx, 6, 6, W - 12, H - 12, 40);
        ctx.fillStyle = 'rgba(246,247,253,0.96)'; ctx.fill();
        ctx.lineWidth = 6; ctx.strokeStyle = accent; ctx.stroke();
        ctx.fillStyle = accent; ctx.fillRect(6, 40, 16, H - 80);
        ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
        ctx.fillStyle = accent; ctx.font = `700 26px ${FONT_MONO}`;
        ctx.fillText('QVERIS · FORENSIC RECORD', 70, 70);
        ctx.fillStyle = CSS.ink; ctx.font = `700 60px ${FONT_HEAD}`; ctx.fillText(title, 70, 142);
        let y = 208;
        ctx.font = `500 29px ${FONT_MONO}`;
        for (const [k, v] of rows) {
          ctx.fillStyle = CSS.inkSoft; ctx.textAlign = 'left'; ctx.fillText(k, 70, y);
          ctx.fillStyle = CSS.ink; ctx.textAlign = 'right'; ctx.fillText(String(v), W - 70, y);
          ctx.textAlign = 'left'; ctx.fillStyle = 'rgba(30,36,64,0.08)'; ctx.fillRect(70, y + 14, W - 140, 2);
          y += 50;
        }
        y += 10;
        ctx.font = `400 25px ${FONT_HEAD}`; ctx.fillStyle = CSS.inkSoft;
        for (const ln of lines) {
          let cur = '';
          for (const wd of String(ln).split(' ')) {
            if (cur && ctx.measureText(cur + wd).width > W - 150) { if (y < H - 80) ctx.fillText(cur, 70, y); y += 33; cur = ''; }
            cur += wd + ' ';
          }
          if (cur && y < H - 80) ctx.fillText(cur, 70, y);
          y += 38;
        }
        if (footer) { ctx.fillStyle = accent; ctx.font = `600 22px ${FONT_MONO}`; ctx.fillText(footer, 70, H - 40); }
      });
    },
  };
}
