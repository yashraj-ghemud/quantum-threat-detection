/* Command Center network: backend topology in 3D. Every effect is caused by a
   live event: distribution → qubit pulses per link; signature → a gold packet
   signer → first verifier → transferee; COMPROMISED → coral lightning, a
   shockwave and Eve beside the link; link status tints the fibre. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import type { Network, LinkInfo, NodeInfo } from '@/api/types';
import { useScene, type SceneEvent } from '@/state/live';
import { readVar, NODE_HEX, LabelSprite } from './common';
import { usePrefs } from '@/state/prefs';

const SCALE = 1.0;
const P = (n: NodeInfo) => new THREE.Vector3(n.pos[0] * SCALE, (n.pos[1] ?? 0) * SCALE, n.pos[2] * SCALE);

function arc(a: THREE.Vector3, b: THREE.Vector3, lift = 1.6) {
  const mid = a.clone().add(b).multiplyScalar(0.5); mid.y += lift + a.distanceTo(b) * 0.12;
  return new THREE.QuadraticBezierCurve3(a.clone().setY(a.y + 1.1), mid, b.clone().setY(b.y + 1.1));
}

const fiberVS = `varying vec2 vUv; varying vec3 vN; varying vec3 vV; void main(){ vUv = uv; vec4 mv = modelViewMatrix * vec4(position,1.0); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`;
const fiberFS = `uniform vec3 uColor; uniform float uTime, uSpeed, uBoost, uDash; varying vec2 vUv; varying vec3 vN; varying vec3 vV;
void main(){ float stripe = smoothstep(0.35, 0.5, fract(vUv.x * 14.0 - uTime * uSpeed)) * (1.0 - smoothstep(0.5, 0.65, fract(vUv.x * 14.0 - uTime * uSpeed)));
  float fres = pow(1.0 - abs(dot(vN, vV)), 1.6);
  float dash = uDash > 0.5 ? step(0.5, fract(vUv.x * 40.0 - uTime * 0.8)) : 1.0;
  float a = (0.22 + 0.55 * stripe + 0.45 * fres + uBoost * 0.6) * dash;
  gl_FragColor = vec4(uColor * (0.8 + stripe * 0.9 + uBoost), a); }`;

function Fiber({ link, a, b, selected, onSelect, boost }: { link: LinkInfo; a: THREE.Vector3; b: THREE.Vector3; selected: boolean; onSelect: () => void; boost: React.MutableRefObject<Record<string, number>> }) {
  const curve = useMemo(() => arc(a, b, link.kind === 'quantum' ? 1.6 : 0.6), [a, b, link.kind]);
  const geo = useMemo(() => new THREE.TubeGeometry(curve, 96, link.kind === 'quantum' ? 0.07 : 0.035, 10, false), [curve, link.kind]);
  const color = link.kind === 'classical' ? readVar('--gold', '#E8B860') : link.status === 'QUARANTINED' ? readVar('--coral', '#E8697A') : link.status === 'DEGRADED' ? readVar('--peach', '#F4A77A') : readVar('--sky', '#6FA8F0');
  const mat = useMemo(() => new THREE.ShaderMaterial({ vertexShader: fiberVS, fragmentShader: fiberFS, transparent: true, depthWrite: false, blending: THREE.NormalBlending,
    uniforms: { uColor: { value: new THREE.Color(color) }, uTime: { value: 0 }, uSpeed: { value: 0.35 }, uBoost: { value: 0 }, uDash: { value: link.kind === 'classical' ? 1 : 0 } } }), []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { mat.uniforms.uColor.value.set(color); }, [color, mat]);
  useFrame((st, dt) => {
    const b0 = boost.current[link.id] || 0;
    boost.current[link.id] = Math.max(0, b0 - dt * 0.8);
    mat.uniforms.uTime.value = st.clock.elapsedTime;
    mat.uniforms.uSpeed.value = 0.35 + b0 * 2.2 + (link.status === 'QUARANTINED' ? -0.3 : 0);
    mat.uniforms.uBoost.value = b0 * 0.6 + (selected ? 0.35 : 0);
  });
  return <mesh geometry={geo} material={mat} onClick={(e) => { e.stopPropagation(); onSelect(); }} onPointerOver={() => (document.body.style.cursor = 'pointer')} onPointerOut={() => (document.body.style.cursor = '')} />;
}

function NodeMesh({ node, selected, onSelect, flash }: { node: NodeInfo; selected: boolean; onSelect: () => void; flash: React.MutableRefObject<Record<string, { t: number; color: string }>> }) {
  const g = useRef<THREE.Group>(null);
  const core = useRef<THREE.Mesh>(null);
  const color = readVar(NODE_HEX[node.id] || '--quantum');
  const signer = node.role === 'signer';
  const adversary = node.role === 'adversary';
  useFrame((st) => {
    const t = st.clock.elapsedTime;
    if (g.current) { g.current.rotation.y = t * (signer ? 0.5 : 0.3); g.current.position.y = P(node).y + 1.1 + Math.sin(t * 1.2 + node.pos[0]) * 0.08; }
    const f = flash.current[node.id];
    const m = core.current?.material as THREE.MeshStandardMaterial | undefined;
    if (m) {
      const k = f ? Math.max(0, 1 - (performance.now() - f.t) / 900) : 0;
      m.emissive.set(k > 0 ? f!.color : color);
      m.emissiveIntensity = 0.9 + k * 2.4 + (selected ? 0.6 : 0) + (node.suspended ? Math.sin(t * 6) * 0.5 : 0);
    }
  });
  const p = P(node);
  return (
    <group position={[p.x, 0, p.z]} onClick={(e) => { e.stopPropagation(); onSelect(); }} onPointerOver={() => (document.body.style.cursor = 'pointer')} onPointerOut={() => (document.body.style.cursor = '')}>
      <mesh position={[0, 0.05, 0]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.55, 0.62, 48]} /><meshBasicMaterial color={color} transparent opacity={selected ? 0.9 : 0.4} /></mesh>
      <mesh position={[0, 0.5, 0]}><cylinderGeometry args={[0.04, 0.04, 1.0, 8]} /><meshStandardMaterial color={color} transparent opacity={0.35} /></mesh>
      <group ref={g} position={[0, 1.1, 0]}>
        <mesh ref={core}>{signer ? <octahedronGeometry args={[0.42, 0]} /> : adversary ? <tetrahedronGeometry args={[0.46, 0]} /> : <icosahedronGeometry args={[0.36, 0]} />}
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1} roughness={0.25} metalness={0.2} flatShading /></mesh>
        <mesh rotation={[Math.PI / 2.4, 0, 0]}><torusGeometry args={[0.66, 0.012, 8, 96]} /><meshBasicMaterial color={color} transparent opacity={0.6} /></mesh>
        {signer && <mesh rotation={[Math.PI / 2, 0.6, 0]}><torusGeometry args={[0.8, 0.01, 8, 96]} /><meshBasicMaterial color={color} transparent opacity={0.4} /></mesh>}
      </group>
      <LabelSprite position={[0, 2.15, 0]} title={node.name} sub={`${node.role}${node.suspended ? ' · suspended' : ''}`} color={color} />
    </group>
  );
}

interface Pulse { curve: THREE.Curve<THREE.Vector3>; t0: number; dur: number; color: THREE.Color; size: number; onArrive?: () => void; arrived?: boolean }
const MAX_PULSES = 400;
function Pulses({ pulses }: { pulses: React.MutableRefObject<Pulse[]> }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const m4 = useMemo(() => new THREE.Matrix4(), []);
  const v = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    const im = mesh.current; if (!im) return;
    const now = performance.now();
    let n = 0;
    pulses.current = pulses.current.filter((p) => now - p.t0 < p.dur + 50);
    for (const p of pulses.current) {
      const k = (now - p.t0) / p.dur;
      if (k < 0) continue;
      if (k >= 1) { if (!p.arrived) { p.arrived = true; p.onArrive?.(); } continue; }
      if (n >= MAX_PULSES) break;
      p.curve.getPoint(k, v);
      const s = p.size * (0.7 + Math.sin(k * Math.PI) * 0.6);
      m4.makeScale(s, s, s).setPosition(v);
      im.setMatrixAt(n, m4); im.setColorAt(n, p.color); n++;
    }
    im.count = n;
    im.instanceMatrix.needsUpdate = true;
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
  });
  return <instancedMesh ref={mesh} args={[undefined as any, undefined as any, MAX_PULSES]} frustumCulled={false}>
    <sphereGeometry args={[1, 12, 10]} /><meshBasicMaterial toneMapped={false} />
  </instancedMesh>;
}

function Lightning({ bolts }: { bolts: React.MutableRefObject<{ curve: THREE.Curve<THREE.Vector3>; t0: number }[]> }) {
  const line = useRef<THREE.LineSegments>(null);
  const geo = useMemo(() => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6 * 40 * 3), 3)); return g; }, []);
  useFrame(() => {
    const now = performance.now();
    bolts.current = bolts.current.filter((b) => now - b.t0 < 700);
    const pos = geo.attributes.position.array as Float32Array; let i = 0;
    for (const b of bolts.current.slice(0, 6)) {
      let prev = b.curve.getPoint(0);
      for (let s = 1; s <= 20; s++) {
        const p = b.curve.getPoint(s / 20).add(new THREE.Vector3((Math.random() - 0.5) * 0.5, (Math.random() - 0.5) * 0.5, (Math.random() - 0.5) * 0.5));
        pos.set([prev.x, prev.y, prev.z, p.x, p.y, p.z], i); i += 6; prev = p;
      }
    }
    geo.setDrawRange(0, i / 3); geo.attributes.position.needsUpdate = true;
    if (line.current) (line.current.material as THREE.LineBasicMaterial).opacity = bolts.current.length ? 0.6 + Math.random() * 0.4 : 0;
  });
  return <lineSegments ref={line} geometry={geo}><lineBasicMaterial color={readVar('--coral', '#E8697A')} transparent toneMapped={false} /></lineSegments>;
}

function Shocks({ shocks }: { shocks: React.MutableRefObject<{ p: THREE.Vector3; t0: number; color: string }[]> }) {
  const group = useRef<THREE.Group>(null);
  const [, force] = useState(0);
  useFrame(() => {
    const now = performance.now();
    const before = shocks.current.length;
    shocks.current = shocks.current.filter((s) => now - s.t0 < 1200);
    if (before !== shocks.current.length) force((x) => x + 1);
    group.current?.children.forEach((c, i) => {
      const s = shocks.current[i]; if (!s) return;
      const k = (now - s.t0) / 1200;
      c.scale.setScalar(0.3 + k * 4.5);
      ((c as THREE.Mesh).material as THREE.MeshBasicMaterial).opacity = (1 - k) * 0.7;
    });
  });
  return <group ref={group}>{shocks.current.map((s, i) => (
    <mesh key={`${s.t0}-${i}`} position={[s.p.x, 0.08, s.p.z]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.9, 1, 64]} /><meshBasicMaterial color={s.color} transparent side={THREE.DoubleSide} /></mesh>
  ))}</group>;
}

function Eve({ at }: { at: React.MutableRefObject<{ p: THREE.Vector3; t0: number } | null> }) {
  const g = useRef<THREE.Group>(null);
  useFrame((st) => {
    const e = at.current; const grp = g.current; if (!grp) return;
    const k = e ? (performance.now() - e.t0) / 3000 : 1;
    grp.visible = !!e && k < 1;
    if (!e || k >= 1) return;
    const s = Math.sin(Math.min(1, k * 4) * Math.PI / 2) * (1 - Math.max(0, (k - 0.8) / 0.2));
    grp.position.set(e.p.x + 1.2, 1.2 + Math.sin(st.clock.elapsedTime * 4) * 0.1, e.p.z + 1.2);
    grp.scale.setScalar(Math.max(0.001, s));
    grp.rotation.y = st.clock.elapsedTime * 2;
  });
  return (
    <group ref={g} visible={false}>
      <mesh><octahedronGeometry args={[0.45, 0]} /><meshStandardMaterial color="#2B2742" emissive={readVar('--coral', '#E8697A')} emissiveIntensity={0.8} metalness={0.8} roughness={0.25} flatShading /></mesh>
      <LabelSprite position={[0, 0.95, 0]} title="Eve" sub="adversary" color={readVar('--coral', '#E8697A')} dark scale={0.8} />
    </group>
  );
}

function Floor() {
  const mat = useMemo(() => new THREE.ShaderMaterial({ transparent: true, depthWrite: false,
    uniforms: { uColor: { value: new THREE.Color(readVar('--lav')) }, uTime: { value: 0 } },
    vertexShader: 'varying vec3 vW; void main(){ vec4 w = modelMatrix*vec4(position,1.0); vW = w.xyz; gl_Position = projectionMatrix*viewMatrix*w; }',
    fragmentShader: `uniform vec3 uColor; uniform float uTime; varying vec3 vW;
      void main(){ vec2 g = abs(fract(vW.xz/1.2 - 0.5) - 0.5)*1.2; float dotv = smoothstep(0.06,0.0,length(g));
        float d = length(vW.xz); float ring = smoothstep(0.3,0.0,abs(fract(d/7.0 - uTime*0.06)-0.5)*7.0-3.2)*0.35;
        float fade = smoothstep(22.0, 4.0, d); gl_FragColor = vec4(uColor, (dotv*0.5 + ring)*fade*0.55); }` }), []);
  useFrame((st) => { mat.uniforms.uTime.value = st.clock.elapsedTime; });
  return <mesh rotation={[-Math.PI / 2, 0, 0]} material={mat}><planeGeometry args={[60, 60]} /></mesh>;
}

function CameraRig({ focus }: { focus: THREE.Vector3 | null }) {
  const { camera } = useThree();
  const target = useRef(new THREE.Vector3(0, 0.8, 0));
  useFrame((_, dt) => { if (focus) { target.current.lerp(focus, 1 - Math.exp(-dt * 3)); camera.lookAt(target.current); } });
  return null;
}

export function NetworkScene({ net, selected, onSelect, showHidden }: { net: Network; selected: { kind: 'node' | 'link'; id: string } | null; onSelect: (s: { kind: 'node' | 'link'; id: string } | null) => void; showHidden?: boolean }) {
  const nodes = net.nodes.filter((n) => showHidden || !n.hidden);
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const links = net.links.filter((l) => (showHidden || !l.hidden) && byId[l.a] && byId[l.b]);
  const pulses = useRef<Pulse[]>([]);
  const bolts = useRef<{ curve: THREE.Curve<THREE.Vector3>; t0: number }[]>([]);
  const shocks = useRef<{ p: THREE.Vector3; t0: number; color: string }[]>([]);
  const eve = useRef<{ p: THREE.Vector3; t0: number } | null>(null);
  const boost = useRef<Record<string, number>>({});
  const flash = useRef<Record<string, { t: number; color: string }>>({});
  const lastEv = useRef(useScene.getState().events.at(-1)?.id ?? 0);
  const curveOf = useMemo(() => {
    const m: Record<string, THREE.Curve<THREE.Vector3>> = {};
    links.forEach((l) => { m[l.id] = arc(P(byId[l.a]), P(byId[l.b]), l.kind === 'quantum' ? 1.6 : 0.6); });
    return m;
  }, [links, byId]);
  const linkBetween = (a: string, b: string) => links.find((l) => (l.a === a && l.b === b) || (l.a === b && l.b === a));
  const reverse = (c: THREE.Curve<THREE.Vector3>) => ({ getPoint: (t: number, v?: THREE.Vector3) => c.getPoint(1 - t, v) }) as THREE.Curve<THREE.Vector3>;
  const quality = usePrefs((s) => s.quality);

  useEffect(() => useScene.subscribe((st) => {
    const fresh: SceneEvent[] = st.events.filter((e) => e.id > lastEv.current);
    if (!fresh.length) return;
    lastEv.current = fresh[fresh.length - 1].id;
    const now = performance.now();
    const cap = quality === 'low' ? 8 : 20;
    for (const e of fresh) {
      const s = e.payload;
      if (e.kind === 'pulses' && s?.recipients) {
        const n = Math.max(6, Math.min(cap, Math.round(Math.log10(s.qubits || 1e6) * 3)));
        const bad = s.verdict === 'COMPROMISED';
        s.recipients.forEach((r: string) => {
          const l = linkBetween(s.signer_id, r); if (!l) return;
          const c = l.a === s.signer_id ? curveOf[l.id] : reverse(curveOf[l.id]);
          boost.current[l.id] = 1;
          for (let i = 0; i < n; i++) pulses.current.push({ curve: c, t0: now + i * 40, dur: 1100, color: new THREE.Color(readVar(bad && i % 3 === 0 ? '--coral' : '--sky')), size: 0.09 });
        });
      } else if (e.kind === 'packet' && s?.recipients?.length === 2) {
        const [v1, v2] = s.recipients;
        const l1 = linkBetween(s.signer_id, v1); if (!l1) continue;
        const ok = s.verdict === 'ACCEPTED';
        const verdictColor = readVar(ok ? '--mint' : '--coral');
        const c1 = l1.a === s.signer_id ? curveOf[l1.id] : reverse(curveOf[l1.id]);
        const l2 = linkBetween(v1, v2);
        pulses.current.push({ curve: c1, t0: now, dur: 900, color: new THREE.Color(readVar('--gold')), size: 0.16, onArrive: () => {
          flash.current[v1] = { t: performance.now(), color: verdictColor };
          if (l2) {
            const c2 = l2.a === v1 ? curveOf[l2.id] : reverse(curveOf[l2.id]);
            pulses.current.push({ curve: c2, t0: performance.now(), dur: 700, color: new THREE.Color(readVar('--gold')), size: 0.14, onArrive: () => { flash.current[v2] = { t: performance.now(), color: verdictColor }; } });
          }
        } });
      } else if (e.kind === 'lightning' && s?.links) {
        for (const lk of s.links as { link_id: string; S: number }[]) {
          if (lk.S > 2.2 && s.links.length > 1) continue;
          const c = curveOf[lk.link_id]; if (!c) continue;
          bolts.current.push({ curve: c, t0: now });
          const mid = c.getPoint(0.5);
          eve.current = { p: mid, t0: now };
          const l = links.find((x) => x.id === lk.link_id);
          if (l) shocks.current.push({ p: P(byId[l.b]), t0: now, color: readVar('--coral') });
        }
      } else if (e.kind === 'shock' && s?.link_id) {
        const l = links.find((x) => x.id === s.link_id);
        if (l) shocks.current.push({ p: P(byId[l.b]), t0: now, color: readVar('--coral') });
      }
    }
  }), [curveOf, links, byId, quality]); // eslint-disable-line react-hooks/exhaustive-deps

  const focus = selected?.kind === 'node' && byId[selected.id] ? P(byId[selected.id]).setY(1) : null;
  return (
    <>
      <color attach="background" args={[readVar('--bg-0', '#EAEDF7')]} />
      <fog attach="fog" args={[readVar('--bg-0', '#EAEDF7'), 18, 42]} />
      <ambientLight intensity={0.7} />
      <directionalLight position={[6, 12, 8]} intensity={1.4} />
      <pointLight position={[0, 6, 0]} intensity={30} color={readVar('--lav')} />
      <Floor />
      {links.map((l) => <Fiber key={l.id} link={l} a={P(byId[l.a])} b={P(byId[l.b])} selected={selected?.kind === 'link' && selected.id === l.id} onSelect={() => onSelect({ kind: 'link', id: l.id })} boost={boost} />)}
      {nodes.map((n) => <NodeMesh key={n.id} node={n} selected={selected?.kind === 'node' && selected.id === n.id} onSelect={() => onSelect({ kind: 'node', id: n.id })} flash={flash} />)}
      <Pulses pulses={pulses} />
      <Lightning bolts={bolts} />
      <Shocks shocks={shocks} />
      <Eve at={eve} />
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} minDistance={6} maxDistance={32} maxPolarAngle={Math.PI / 2.15} autoRotate autoRotateSpeed={0.3} target={[0, 0.8, 0]} />
      <CameraRig focus={focus} />
    </>
  );
}
