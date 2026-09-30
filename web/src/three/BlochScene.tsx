/* Bloch sphere with channel ellipsoids. A map r → M r + c is drawn by
   transforming the unit sphere; each of the 12 numbers springs toward its
   target so a change of channel visibly deforms the ellipsoid. Bloch axes
   map to the scene as (x, y, z)_bloch → (x, z, −y)_scene (z is up). */
import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { LabelSprite, readVar } from './common';

export type Vec3 = [number, number, number];
export interface MapSpec { M: number[][]; c: number[]; color: string; wire?: boolean; opacity?: number; label?: string }
export interface ArrowSpec { v: Vec3; color: string; width?: number; trail?: boolean }

const toScene = (v: Vec3 | number[]) => new THREE.Vector3(v[0], v[2], -v[1]);
const P = new THREE.Matrix3().set(1, 0, 0, 0, 0, 1, 0, -1, 0);
const Pinv = P.clone().invert();

function Ellipsoid({ spec }: { spec: MapSpec }) {
  const mesh = useRef<THREE.Mesh>(null);
  const cur = useRef<number[]>([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]);
  const target = [...spec.M.flat(), ...spec.c];
  useFrame((_, dt) => {
    const k = 1 - Math.exp(-dt * 6);
    const c = cur.current;
    for (let i = 0; i < 12; i++) c[i] += ((target[i] ?? 0) - c[i]) * k;
    const M = new THREE.Matrix3().set(c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8]);
    const S = P.clone().multiply(M).multiply(Pinv);
    const e = S.elements; // column-major
    const t = toScene([c[9], c[10], c[11]]);
    const m4 = new THREE.Matrix4().set(e[0], e[3], e[6], t.x, e[1], e[4], e[7], t.y, e[2], e[5], e[8], t.z, 0, 0, 0, 1);
    if (mesh.current) { mesh.current.matrixAutoUpdate = false; mesh.current.matrix.copy(m4); }
  });
  return (
    <mesh ref={mesh}>
      <sphereGeometry args={[1, spec.wire ? 18 : 48, spec.wire ? 12 : 32]} />
      {spec.wire
        ? <meshBasicMaterial color={spec.color} wireframe transparent opacity={spec.opacity ?? 0.5} depthWrite={false} />
        : <meshPhysicalMaterial color={spec.color} transparent opacity={spec.opacity ?? 0.42} roughness={0.15} metalness={0.05} clearcoat={1} iridescence={0.6} depthWrite={false} side={THREE.DoubleSide} />}
    </mesh>
  );
}

function Arrow({ spec }: { spec: ArrowSpec }) {
  const g = useRef<THREE.Group>(null);
  const cur = useRef(new THREE.Vector3(0, 1, 0));
  const trail = useRef<THREE.Vector3[]>([]);
  const line = useRef<THREE.Line>(null);
  const lineGeo = useMemo(() => new THREE.BufferGeometry().setFromPoints(Array.from({ length: 64 }, () => new THREE.Vector3())), []);
  const lineObj = useMemo(() => new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: spec.color, transparent: true, opacity: 0.45 })), [lineGeo]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { lineGeo.dispose(); (lineObj.material as THREE.Material).dispose(); }, [lineGeo, lineObj]);
  useFrame((_, dt) => {
    const tgt = toScene(spec.v);
    cur.current.lerp(tgt, 1 - Math.exp(-dt * 7));
    const len = cur.current.length();
    if (g.current) {
      g.current.visible = len > 0.02;
      if (len > 1e-4) g.current.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), cur.current.clone().normalize());
      g.current.scale.set(1, Math.max(0.02, len), 1);
    }
    if (spec.trail && line.current) {
      const t = trail.current;
      if (!t.length || t[t.length - 1].distanceTo(cur.current) > 0.01) { t.push(cur.current.clone()); if (t.length > 64) t.shift(); }
      const pos = lineGeo.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < 64; i++) { const p = t[Math.max(0, t.length - 64 + i)] || cur.current; pos.setXYZ(i, p.x, p.y, p.z); }
      pos.needsUpdate = true;
    }
  });
  const w = spec.width ?? 0.028;
  return (
    <>
      <group ref={g}>
        <mesh position={[0, 0.43, 0]}><cylinderGeometry args={[w, w, 0.86, 12]} /><meshStandardMaterial color={spec.color} emissive={spec.color} emissiveIntensity={0.8} /></mesh>
        <mesh position={[0, 0.93, 0]}><coneGeometry args={[w * 3, 0.16, 20]} /><meshStandardMaterial color={spec.color} emissive={spec.color} emissiveIntensity={1.1} /></mesh>
      </group>
      {spec.trail && <primitive object={lineObj} ref={line} />}
    </>
  );
}

function Frame({ labels = true }: { labels?: boolean }) {
  const bx = readVar('--basis-x', '#2E9FD0'), by = readVar('--basis-y', '#D24C9B'), bz = readVar('--basis-z', '#C9A200');
  const ink = readVar('--text-2', '#5A6384');
  const kets: [string, Vec3, string][] = [['|+⟩', [1.28, 0, 0], bx], ['|−⟩', [-1.28, 0, 0], bx], ['|+i⟩', [0, 1.28, 0], by], ['|−i⟩', [0, -1.28, 0], by], ['|0⟩', [0, 0, 1.28], bz], ['|1⟩', [0, 0, -1.28], bz]];
  return (
    <group>
      <mesh><sphereGeometry args={[1, 64, 48]} /><meshPhysicalMaterial color="#ffffff" transparent opacity={0.1} roughness={0.05} clearcoat={1} depthWrite={false} /></mesh>
      {[[Math.PI / 2, 0, 0], [0, 0, 0], [0, Math.PI / 2, 0]].map((r, i) => (
        <mesh key={i} rotation={r as any}><torusGeometry args={[1, 0.004, 6, 128]} /><meshBasicMaterial color={ink} transparent opacity={0.35} /></mesh>
      ))}
      {([[1, 0, 0, bx], [0, 1, 0, by], [0, 0, 1, bz]] as [number, number, number, string][]).map(([x, y, z, col]) => {
        const d = toScene([x, y, z]);
        const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d);
        return <mesh key={col + x} quaternion={q}><cylinderGeometry args={[0.006, 0.006, 2.3, 6]} /><meshBasicMaterial color={col} transparent opacity={0.8} /></mesh>;
      })}
      {kets.map(([t, v, col]) => {
        const s = toScene(v);
        return <group key={t}>
          <mesh position={toScene(v.map((x) => x / 1.28) as Vec3)}><sphereGeometry args={[0.035, 12, 10]} /><meshBasicMaterial color={col} /></mesh>
          {labels && <LabelSprite position={[s.x, s.y, s.z]} title={t} color={col} scale={0.42} />}
        </group>;
      })}
    </group>
  );
}

function DragSurface({ onDrag }: { onDrag: (v: Vec3) => void }) {
  const dragging = useRef(false);
  const { controls } = useThree() as any;
  const set = (e: ThreeEvent<PointerEvent>) => {
    const p = e.point.clone().normalize();
    onDrag([p.x, -p.z, p.y]);
  };
  return (
    <mesh onPointerDown={(e) => { if (e.button !== 0) return; e.stopPropagation(); dragging.current = true; if (controls) controls.enabled = false; (e.target as any)?.setPointerCapture?.(e.pointerId); set(e); }}
      onPointerMove={(e) => { if (dragging.current) set(e); }}
      onPointerUp={() => { dragging.current = false; if (controls) controls.enabled = true; }}>
      <sphereGeometry args={[1.02, 32, 24]} /><meshBasicMaterial transparent opacity={0} depthWrite={false} />
    </mesh>
  );
}

export function BlochScene({ maps = [], arrows = [], onDrag, autoRotate = false, labels = true }: { maps?: MapSpec[]; arrows?: ArrowSpec[]; onDrag?: (v: Vec3) => void; autoRotate?: boolean; labels?: boolean }) {
  const inv = useThree((s) => s.invalidate);
  useEffect(() => { inv(); }, [maps, arrows, inv]);
  return (
    <>
      <ambientLight intensity={0.9} />
      <directionalLight position={[3, 5, 4]} intensity={1.6} />
      <pointLight position={[-3, -2, -3]} intensity={8} color={readVar('--lav')} />
      <Frame labels={labels} />
      {maps.map((m, i) => <Ellipsoid key={i + (m.wire ? 'w' : 's')} spec={m} />)}
      {arrows.map((a, i) => <Arrow key={i} spec={a} />)}
      {onDrag && <DragSurface onDrag={onDrag} />}
      <OrbitControls makeDefault enablePan={false} enableDamping minDistance={2.2} maxDistance={6} autoRotate={autoRotate} autoRotateSpeed={0.6} />
    </>
  );
}

/** Tiny static 2D fallback: the ellipsoid's xz-cross-section. */
export function BlochSvg({ maps = [], arrows = [] }: { maps?: MapSpec[]; arrows?: ArrowSpec[] }) {
  const R = 90, c = 110;
  return (
    <svg viewBox="0 0 220 220" width="100%" style={{ maxHeight: 320 }} role="img" aria-label="Bloch sphere (2D)">
      <circle cx={c} cy={c} r={R} fill="none" stroke="var(--line-strong)" />
      <line x1={c - R} x2={c + R} y1={c} y2={c} stroke="var(--basis-x)" opacity={0.5} /><line y1={c - R} y2={c + R} x1={c} x2={c} stroke="var(--basis-z)" opacity={0.5} />
      {maps.map((m, i) => <ellipse key={i} cx={c + m.c[0] * R} cy={c - m.c[2] * R} rx={Math.abs(m.M[0][0]) * R} ry={Math.abs(m.M[2][2]) * R} fill={m.wire ? 'none' : m.color} fillOpacity={0.25} stroke={m.color} strokeDasharray={m.wire ? '4 3' : undefined} />)}
      {arrows.map((a, i) => <line key={i} x1={c} y1={c} x2={c + a.v[0] * R} y2={c - a.v[2] * R} stroke={a.color} strokeWidth={3} strokeLinecap="round" />)}
    </svg>
  );
}
