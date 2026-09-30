/* Ledger as a chain of glass blocks along a gentle S-curve. New blocks drop in
   with a spring; a verification sweep turns each block mint (valid) or coral
   (tampered, with every downstream block dimmed); click selects. */
import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { OrbitControls, RoundedBox } from '@react-three/drei';
import * as THREE from 'three';
import type { Block } from '@/api/types';
import { LabelSprite, readVar } from './common';

const pos = (i: number, n: number) => { const t = n > 1 ? i / (n - 1) : 0.5; return new THREE.Vector3((t - 0.5) * Math.min(n, 14) * 1.35, Math.sin(t * Math.PI * 2) * 0.35, Math.sin(t * Math.PI) * -1.4); };

function BlockMesh({ b, i, n, state, selected, onSelect, sweep }: { b: Block; i: number; n: number; state: 'valid' | 'tampered' | 'downstream' | 'pending'; selected: boolean; onSelect: () => void; sweep: React.MutableRefObject<number> }) {
  const g = useRef<THREE.Group>(null);
  const born = useRef(performance.now());
  const target = pos(i, n);
  const edge = useRef<THREE.MeshStandardMaterial>(null);
  const colors = { valid: readVar('--mint'), tampered: readVar('--coral'), downstream: readVar('--text-3'), pending: readVar('--sky') };
  useFrame((st, dt) => {
    const grp = g.current; if (!grp) return;
    const age = (performance.now() - born.current) / 1000;
    const drop = age < 1.2 ? Math.exp(-age * 5) * Math.cos(age * 12) * 3 : 0;
    grp.position.lerp(new THREE.Vector3(target.x, target.y + Math.max(-0.2, drop) + (selected ? 0.25 : 0), target.z), 1 - Math.exp(-dt * 8));
    grp.rotation.y = Math.sin(st.clock.elapsedTime * 0.6 + i) * 0.08;
    const passed = sweep.current >= i / Math.max(1, n - 1);
    const c = new THREE.Color(passed ? colors[state] : colors.pending);
    edge.current?.emissive.lerp(c, 1 - Math.exp(-dt * 6));
    if (edge.current) edge.current.emissiveIntensity = (state === 'tampered' && passed ? 1.4 + Math.sin(st.clock.elapsedTime * 8) * 0.5 : 0.7) * (state === 'downstream' && passed ? 0.4 : 1);
  });
  useEffect(() => { born.current = performance.now(); }, [b.hash]);
  return (
    <group ref={g} position={[target.x, target.y + 3, target.z]} onClick={(e) => { e.stopPropagation(); onSelect(); }}>
      <RoundedBox args={[1, 0.72, 0.72]} radius={0.12} smoothness={4}>
        <meshPhysicalMaterial color={readVar('--bg-2', '#F3F4FB')} transparent opacity={0.82} roughness={0.2} clearcoat={1} />
      </RoundedBox>
      <RoundedBox args={[1.04, 0.76, 0.76]} radius={0.13} smoothness={2}>
        <meshStandardMaterial ref={edge} color="#000" emissive={colors.pending} emissiveIntensity={0.7} wireframe transparent opacity={0.55} />
      </RoundedBox>
      <LabelSprite position={[0, 0.72, 0]} title={`#${b.height}`} sub={`${b.tx_count} tx`} color={state === 'tampered' ? colors.tampered : readVar('--lav')} scale={0.6} />
    </group>
  );
}

export function ChainScene({ blocks, tamperedFrom, downstream = 0, selected, onSelect, sweepKey }: { blocks: Block[]; tamperedFrom: number | null; downstream?: number; selected: number | null; onSelect: (h: number) => void; sweepKey: number }) {
  const sorted = useMemo(() => [...blocks].sort((a, b) => a.height - b.height).slice(-14), [blocks]);
  const sweep = useRef(1);
  const plane = useRef<THREE.Mesh>(null);
  useEffect(() => { if (sweepKey) sweep.current = 0; }, [sweepKey]);
  useFrame((_, dt) => {
    if (sweep.current < 1) sweep.current = Math.min(1, sweep.current + dt / 1.6);
    if (plane.current) {
      const n = sorted.length;
      plane.current.visible = sweep.current < 1;
      const p = pos(sweep.current * (n - 1), n);
      plane.current.position.set(p.x, 0, 0);
    }
  });
  return (
    <>
      <ambientLight intensity={0.9} /><directionalLight position={[4, 6, 5]} intensity={1.5} />
      {sorted.map((b, i) => (
        <group key={b.height}>
          <BlockMesh b={b} i={i} n={sorted.length} selected={selected === b.height} onSelect={() => onSelect(b.height)} sweep={sweep}
            state={tamperedFrom == null ? 'valid' : b.height === tamperedFrom ? 'tampered' : b.height > tamperedFrom && b.height <= tamperedFrom + downstream ? 'downstream' : 'valid'} />
          {i > 0 && (() => { const a = pos(i - 1, sorted.length), c = pos(i, sorted.length); const m = a.clone().add(c).multiplyScalar(0.5);
            return <mesh position={m} rotation={[0, 0, Math.PI / 2]}><torusGeometry args={[0.13, 0.035, 8, 24]} /><meshStandardMaterial color={readVar('--gold')} metalness={0.6} roughness={0.3} /></mesh>; })()}
        </group>
      ))}
      <mesh ref={plane} visible={false}><planeGeometry args={[0.08, 3]} /><meshBasicMaterial color={readVar('--sky')} transparent opacity={0.6} side={THREE.DoubleSide} /></mesh>
      <OrbitControls enablePan enableDamping minDistance={4} maxDistance={20} target={[0, 0, 0]} />
    </>
  );
}
