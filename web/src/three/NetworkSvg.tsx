/* 2D network (fallback and low-power mode): same layout projected on x/z,
   with the same event-driven pulses. */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { Network } from '@/api/types';
import { useScene } from '@/state/live';
import { nodeColor } from '@/lib/color';

export function NetworkSvg({ net, selected, onSelect }: { net: Network; selected: { kind: string; id: string } | null; onSelect: (s: { kind: 'node' | 'link'; id: string } | null) => void }) {
  const nodes = net.nodes.filter((n) => !n.hidden);
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const links = net.links.filter((l) => !l.hidden && byId[l.a] && byId[l.b]);
  const xs = nodes.map((n) => n.pos[0]), zs = nodes.map((n) => n.pos[2]);
  const [minX, maxX, minZ, maxZ] = [Math.min(...xs), Math.max(...xs), Math.min(...zs), Math.max(...zs)];
  const W = 600, H = 360, pad = 60;
  const px = (x: number) => pad + ((x - minX) / (maxX - minX || 1)) * (W - 2 * pad);
  const pz = (z: number) => pad + ((z - minZ) / (maxZ - minZ || 1)) * (H - 2 * pad);
  const path = (a: string, b: string, lift = 40) => { const A = byId[a], B = byId[b]; const x1 = px(A.pos[0]), y1 = pz(A.pos[2]), x2 = px(B.pos[0]), y2 = pz(B.pos[2]); return `M${x1},${y1} Q${(x1 + x2) / 2},${(y1 + y2) / 2 - lift} ${x2},${y2}`; };
  const [pulses, setPulses] = useState<{ id: number; d: string; color: string; dur: number }[]>([]);
  const last = useRef(useScene.getState().events.at(-1)?.id ?? 0);
  const linkBetween = useMemo(() => (a: string, b: string) => links.find((l) => (l.a === a && l.b === b) || (l.a === b && l.b === a)), [links]);
  useEffect(() => useScene.subscribe((st) => {
    const fresh = st.events.filter((e) => e.id > last.current);
    if (!fresh.length) return;
    last.current = fresh[fresh.length - 1].id;
    const add: typeof pulses = [];
    for (const e of fresh) {
      const s = e.payload;
      if ((e.kind === 'pulses' || e.kind === 'packet') && s?.recipients) {
        const targets = e.kind === 'packet' ? [s.recipients[0]] : s.recipients;
        targets.forEach((r: string) => { const l = linkBetween(s.signer_id, r); if (l) add.push({ id: e.id * 10 + add.length, d: l.a === s.signer_id ? path(l.a, l.b, l.kind === 'quantum' ? 40 : 14) : path(l.b, l.a, -40), color: e.kind === 'packet' ? 'var(--gold)' : s.verdict === 'COMPROMISED' ? 'var(--coral)' : 'var(--sky)', dur: e.kind === 'packet' ? 0.9 : 1.1 }); });
      }
    }
    if (add.length) { setPulses((p) => [...p, ...add].slice(-40)); setTimeout(() => setPulses((p) => p.filter((x) => !add.includes(x))), 1400); }
  }), [links]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" role="img" aria-label="Network map" onClick={() => onSelect(null)}>
      {links.map((l) => {
        const color = l.kind === 'classical' ? 'var(--gold)' : l.status === 'QUARANTINED' ? 'var(--coral)' : l.status === 'DEGRADED' ? 'var(--peach)' : 'var(--sky)';
        const sel = selected?.kind === 'link' && selected.id === l.id;
        return <path key={l.id} d={path(l.a, l.b, l.kind === 'quantum' ? 40 : 14)} fill="none" stroke={color} strokeWidth={sel ? 5 : l.kind === 'quantum' ? 3 : 2} strokeDasharray={l.kind === 'classical' ? '6 6' : undefined}
          className={l.kind === 'quantum' ? 'flow' : 'flow-dash'} style={{ cursor: 'pointer' }} onClick={(e) => { e.stopPropagation(); onSelect({ kind: 'link', id: l.id }); }} />;
      })}
      {pulses.map((p) => <circle key={p.id} r={5} fill={p.color} style={{ filter: `drop-shadow(0 0 6px ${p.color})` }}><animateMotion dur={`${p.dur}s`} path={p.d} fill="freeze" /></circle>)}
      {nodes.map((n) => {
        const sel = selected?.kind === 'node' && selected.id === n.id;
        return (
          <g key={n.id} transform={`translate(${px(n.pos[0])},${pz(n.pos[2])})`} style={{ cursor: 'pointer' }} onClick={(e) => { e.stopPropagation(); onSelect({ kind: 'node', id: n.id }); }}>
            <circle r={sel ? 26 : 22} fill={nodeColor(n.id)} opacity={0.16} />
            <circle r={13} fill={nodeColor(n.id)} stroke="var(--bg-2)" strokeWidth={3} />
            <text y={34} textAnchor="middle" fontSize={13} fontWeight={700} fill="var(--text-0)" fontFamily="var(--font-display)">{n.name}</text>
            <text y={48} textAnchor="middle" fontSize={9.5} fill="var(--text-2)" fontFamily="var(--font-mono)">{n.role.toUpperCase()}</text>
          </g>
        );
      })}
    </svg>
  );
}
