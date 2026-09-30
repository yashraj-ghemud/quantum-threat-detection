import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'motion/react';
import { Plus, Trash2, ArrowUp, ArrowDown, Undo2, Play } from 'lucide-react';
import type { ChannelSpec, PlaygroundTeleport } from '@/api/types';
import { ep, qk } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { toast } from '@/state/ui';
import { Button, Chip, KeyValue, Panel, Segmented, Slider, Tabs, InfoButton } from '@/components/ui';
import { useDebounced } from '@/components/motion';
import { SceneCanvas } from '@/three/common';
import { BlochScene, BlochSvg, type MapSpec, type ArrowSpec } from '@/three/BlochScene';
import { BarChart, MatrixView } from '@/charts/charts';
import { LegacyScene } from '@/legacy/LegacyScene';
import { noisePayload } from '@/legacy/adapters';
import { GATES, rotate, polar, fromPolar, density, amplitudes, purity, applyAffine, nearestLabel, type V3 } from '@/lib/quantum';
import { LABEL_KET, LABEL_BLOCH } from '@/lib/color';
import { fix, pct } from '@/lib/format';

const ANATOMY_TYPES: Record<string, string> = { depolarizing: 'p', dephasing: 'p', bit_flip: 'p', phase_flip: 'p', bit_phase_flip: 'p', amplitude_damping: 'gamma', phase_damping: 'lam' };

export default function Playground() {
  const cfg = useQuery({ queryKey: qk.config, queryFn: ep.config, staleTime: Infinity });
  const types = cfg.data?.channel_types || {};
  const [r, setR] = useState<V3>([0, 0, 1]);
  const [history, setHistory] = useState<{ g: string; before: V3 }[]>([]);
  const [theta, setTheta] = useState(Math.PI / 3);
  const [channels, setChannels] = useState<ChannelSpec[]>([{ type: 'amplitude_damping', gamma: 0.3 }]);
  const [twirled, setTwirled] = useState(false);
  const [tab, setTab] = useState<'state' | 'gates' | 'channel' | 'teleport' | 'measure'>('state');
  const anim = useRef(0);

  const dq = useDebounced(JSON.stringify(channels), 150);
  const ch = useQuery({ queryKey: ['pg', 'channel', dq], queryFn: () => ep.pgChannel(JSON.parse(dq)), placeholderData: (p) => p, staleTime: 60_000 });
  const map = ch.data ? (twirled ? ch.data.twirled : { M: ch.data.M, c: ch.data.c }) : null;
  const out = map ? applyAffine(map.M, map.c, r) : r;

  const applyGate = (id: string) => {
    const g = GATES.find((x) => x.id === id)!;
    const angle = g.param ? theta : g.angle;
    const start = r; const t0 = performance.now();
    setHistory((h) => [...h, { g: g.param ? `${g.label.replace('θ', fix(theta, 2))}` : g.label, before: start }].slice(-20));
    cancelAnimationFrame(anim.current);
    const step = (now: number) => { const k = Math.min(1, (now - t0) / 500); setR(rotate(start, g.axis, angle * (1 - (1 - k) ** 3))); if (k < 1) anim.current = requestAnimationFrame(step); };
    anim.current = requestAnimationFrame(step);
  };
  const undo = () => { const h = history.at(-1); if (!h) return; setR(h.before); setHistory(history.slice(0, -1)); };
  const p = polar(r);
  const maps: MapSpec[] = map ? [{ M: map.M, c: map.c, color: '#8C84F0', opacity: 0.32 }, { M: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], c: [0, 0, 0], color: '#6FA8F0', wire: true, opacity: 0.18 }] : [];
  const arrows: ArrowSpec[] = [{ v: r, color: '#8C84F0', trail: true }, ...(map && tab !== 'state' && tab !== 'gates' ? [{ v: out, color: '#E8697A' }] : [])];

  // Original "Channel Anatomy" scene, fed by a real teleport through the first supported channel.
  const first = channels.find((c) => c.type in ANATOMY_TYPES);
  const anatomyKey = useDebounced(JSON.stringify({ first, lab: nearestLabel(r) }), 250);
  const anatomy = useQuery({ queryKey: ['pg', 'anatomy', anatomyKey], enabled: !!first, placeholderData: (x) => x, staleTime: 60_000,
    queryFn: async () => { const { first: f, lab } = JSON.parse(anatomyKey); const t = await ep.pgTeleport({ label: lab, channels: [f] }); return noisePayload(t, f.type, Number(f[ANATOMY_TYPES[f.type]]), lab); } });

  return (
    <div className="stack">
      <header className="page-head"><div><span className="kicker">Bloch sphere · gates · channels · teleportation</span><h1>Quantum Playground</h1>
        <p>The same exact engine that runs the protocol. Drag the state on the sphere, apply gates, stack channels and watch the Bloch ellipsoid deform, then teleport through them.</p></div></header>
      <div className="pg-grid">
        <Panel flush reveal={false} className="pg-scene">
          <SceneCanvas label="Interactive Bloch sphere" camera={{ position: [2.6, 1.7, 2.8], fov: 45 }} style={{ height: '100%' }} fallback={<BlochSvg maps={maps} arrows={arrows} />}>
            <BlochScene maps={tab === 'state' || tab === 'gates' ? [] : maps} arrows={arrows} onDrag={(v) => setR(v.map((x) => x * Math.max(0.02, p.r || 1)) as V3)} />
          </SceneCanvas>
          <div className="scene-overlay tl legend"><span><i style={{ background: 'var(--lav)' }} />input state (drag)</span>{tab !== 'state' && tab !== 'gates' && <><span><i style={{ background: 'var(--coral)' }} />after channel</span><span><i style={{ background: 'var(--lav)', opacity: 0.4 }} />image of every state</span></>}</div>
        </Panel>
        <div className="stack">
          <Tabs label="Tools" value={tab} onChange={setTab} items={[{ value: 'state', label: 'State' }, { value: 'gates', label: 'Gates' }, { value: 'channel', label: 'Channel' }, { value: 'teleport', label: 'Teleport' }, { value: 'measure', label: 'Measure' }]} />
          {tab === 'state' && <Panel tight reveal={false}>
            <div className="stack">
              <div className="row wrap" style={{ gap: 6 }}>{LABEL_KET.map((k, i) => <button key={k} className="chip mono no-magnet" onClick={() => setR(LABEL_BLOCH[i])}>{k}</button>)}</div>
              <Slider label="θ (polar)" value={p.theta} min={0} max={Math.PI} step={0.01} onChange={(v) => setR(fromPolar(v, p.phi, p.r || 1))} format={(v) => `${fix(v / Math.PI, 3)} π`} />
              <Slider label="φ (azimuth)" value={p.phi} min={-Math.PI} max={Math.PI} step={0.01} onChange={(v) => setR(fromPolar(p.theta, v, p.r || 1))} format={(v) => `${fix(v / Math.PI, 3)} π`} />
              <Slider label="purity radius |r|" value={p.r} min={0} max={1} step={0.01} onChange={(v) => setR(fromPolar(p.theta, p.phi, v))} format={(v) => `${fix(v, 2)} · Tr ρ² = ${fix(purity(r), 3)}`} />
              <StateReadout r={r} />
            </div></Panel>}
          {tab === 'gates' && <Panel tight reveal={false}>
            <div className="stack">
              <div className="gate-grid">{GATES.map((g) => <button key={g.id} className="gate no-magnet" title={g.desc} onClick={() => applyGate(g.id)}><b>{g.label}</b><span>{g.desc}</span></button>)}</div>
              <Slider label="θ for Rx/Ry/Rz" value={theta} min={-Math.PI} max={Math.PI} step={0.01} onChange={setTheta} format={(v) => `${fix(v / Math.PI, 3)} π`} />
              <div className="row wrap" style={{ gap: 4 }}>{history.map((h, i) => <Chip key={i} mono>{h.g}</Chip>)}{history.length > 0 && <Button size="sm" variant="ghost" icon={<Undo2 />} onClick={undo}>Undo</Button>}</div>
              <StateReadout r={r} />
            </div></Panel>}
          {tab === 'channel' && <Panel tight reveal={false}>
            <div className="stack">
              {channels.map((c, i) => <ChannelBlock key={i} c={c} spec={types[c.type]} onChange={(n) => setChannels(channels.map((x, j) => (j === i ? n : x)))}
                onRemove={() => setChannels(channels.filter((_, j) => j !== i))} onMove={(d) => { const a = [...channels]; const j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; setChannels(a); }} />)}
              <div className="row wrap" style={{ gap: 6 }}>{Object.keys(types).filter((t) => t !== 'identity').map((t) => <button key={t} className="chip no-magnet" onClick={() => {
                const d: ChannelSpec = { type: t }; types[t].params.forEach((pp) => { d[pp.name] = pp.default; }); setChannels([...channels, d]); }}><Plus size={12} />{types[t].label}</button>)}</div>
              <Segmented label="View" value={twirled ? 'tw' : 'raw'} onChange={(v) => setTwirled(v === 'tw')} options={[{ value: 'raw', label: 'channel N' }, { value: 'tw', label: 'as teleportation sees it (twirled)' }]} />
              {ch.data && <>
                <div className="row wrap top" style={{ gap: 12 }}><MatrixView m={ch.data.ptm} labels={['I', 'X', 'Y', 'Z']} colLabels={['I', 'X', 'Y', 'Z']} label="Pauli transfer matrix" max={1} /></div>
                <KeyValue rows={[['CPTP', ch.data.cptp ? 'yes (Choi ≥ 0)' : 'NO'], ['Choi eigenvalues', ch.data.choi_eigenvalues.map((x) => fix(x, 3)).join(', ')],
                  ['predicted CHSH S', fix(ch.data.predicted.S, 3)], ['predicted F', fix(ch.data.predicted.F, 4)], ['predicted QBER x / y / z', ['x', 'y', 'z'].map((b) => pct(ch.data!.predicted.qber_per_basis[b], 2)).join(' / ')],
                  ['output state', `(${out.map((x) => fix(x, 3)).join(', ')})`]]} />
              </>}
              {ch.error && <div className="error-box">{friendly(ch.error)}</div>}
            </div></Panel>}
          {tab === 'teleport' && <TeleportTool r={r} channels={channels} />}
          {tab === 'measure' && <MeasureTool r={r} channels={channels} />}
        </div>
      </div>
      {first && <>
        <div className="section-title"><span className="kicker">original QVeris scene · real teleport</span><h2>Channel anatomy</h2><InfoButton topic="teleportation" /></div>
        <Panel flush reveal={false}><LegacyScene scene="noise" channel="pg-noise" title="CHANNEL ANATOMY" payload={anatomy.data} label="Channel anatomy: input vs measured Bloch vector after teleportation" style={{ height: 460 }} /></Panel>
      </>}
    </div>
  );
}

function StateReadout({ r }: { r: V3 }) {
  const d = density(r), a = amplitudes(r);
  return <KeyValue rows={[['Bloch vector', `(${r.map((x) => fix(x, 3)).join(', ')})`], ['α, β (if pure)', `${fix(a.a, 3)}, ${fix(a.bRe, 3)}${a.bIm >= 0 ? '+' : '−'}${fix(Math.abs(a.bIm), 3)}i`],
    ['ρ', `[[${fix(d.re[0][0], 3)}, ${fix(d.re[0][1], 3)}${d.im[0][1] >= 0 ? '+' : '−'}${fix(Math.abs(d.im[0][1]), 3)}i], [·, ${fix(d.re[1][1], 3)}]]`], ['purity Tr ρ²', fix(purity(r), 4)]]} />;
}

function ChannelBlock({ c, spec, onChange, onRemove, onMove }: { c: ChannelSpec; spec: any; onChange: (c: ChannelSpec) => void; onRemove: () => void; onMove: (d: number) => void }) {
  return (
    <motion.div layout className="ch-block">
      <div className="row between"><b>{spec?.label || c.type}</b><span className="row" style={{ gap: 2 }}>
        <button className="btn ghost icon sm" aria-label="Move up" onClick={() => onMove(-1)}><ArrowUp /></button><button className="btn ghost icon sm" aria-label="Move down" onClick={() => onMove(1)}><ArrowDown /></button>
        <button className="btn ghost icon sm" aria-label="Remove" onClick={onRemove}><Trash2 /></button></span></div>
      {(spec?.params || []).map((pp: any) => pp.options ? <Segmented key={pp.name} label={pp.name} value={c[pp.name] as string} onChange={(v) => onChange({ ...c, [pp.name]: v })} options={pp.options.map((o: string) => ({ value: o, label: o }))} />
        : Array.isArray(pp.default) ? <Segmented key={pp.name} label="axis" value={JSON.stringify(c[pp.name])} onChange={(v) => onChange({ ...c, [pp.name]: JSON.parse(v) })} options={[['x', [1, 0, 0]], ['y', [0, 1, 0]], ['z', [0, 0, 1]]].map(([l, v]) => ({ value: JSON.stringify(v), label: l as string }))} />
        : <Slider key={pp.name} label={pp.name} value={Number(c[pp.name] ?? pp.default)} min={pp.min ?? 0} max={pp.max ?? 1} step={0.005} onChange={(v) => onChange({ ...c, [pp.name]: v })} format={(v) => fix(v, 3)} />)}
      <span className="xs faint">{spec?.description}</span>
    </motion.div>
  );
}

function TeleportTool({ r, channels }: { r: V3; channels: ChannelSpec[] }) {
  const [m0, setM0] = useState(0), [m1, setM1] = useState(0);
  const [res, setRes] = useState<PlaygroundTeleport | null>(null);
  const [stage, setStage] = useState(-1);
  const run = async () => {
    try { const t = await ep.pgTeleport({ bloch: r, channels, frame_flip: { m0, m1 }, shots: 1 }); setRes(t); setStage(0); for (let i = 1; i <= 5; i++) setTimeout(() => setStage(i), i * 450); }
    catch (e) { toast({ tone: 'warn', title: friendly(e) }); }
  };
  const k = res?.samples ? Object.entries(res.samples.frames).find(([, n]) => n > 0)?.[0] : null;
  return (
    <Panel tight reveal={false}>
      <div className="stack">
        <svg viewBox="0 0 520 170" width="100%" role="img" aria-label="Teleportation circuit">
          {[30, 85, 140].map((y, i) => <g key={y}><text x={4} y={y + 4} fontSize={11} fill="var(--text-2)" fontFamily="var(--font-mono)">q{i}</text><line x1={30} x2={500} y1={y} y2={y} stroke={stage >= 0 ? 'var(--sky)' : 'var(--line-strong)'} strokeWidth={stage >= 0 ? 2 : 1.2} /></g>)}
          <rect x={60} y={72} width={26} height={26} rx={5} fill={stage >= 1 ? 'var(--lav)' : 'var(--bg-3)'} /><text x={73} y={89} textAnchor="middle" fontSize={12} fill="#fff" fontWeight={700}>H</text>
          <line x1={120} x2={120} y1={85} y2={140} stroke="var(--text-1)" strokeWidth={2} /><circle cx={120} cy={85} r={4} fill="var(--text-1)" /><circle cx={120} cy={140} r={9} fill="none" stroke="var(--text-1)" strokeWidth={2} />
          <line x1={180} x2={180} y1={30} y2={85} stroke={stage >= 2 ? 'var(--lav)' : 'var(--text-1)'} strokeWidth={2} /><circle cx={180} cy={30} r={4} fill="var(--text-1)" /><circle cx={180} cy={85} r={9} fill="none" stroke="var(--text-1)" strokeWidth={2} />
          <rect x={215} y={17} width={26} height={26} rx={5} fill={stage >= 2 ? 'var(--lav)' : 'var(--bg-3)'} /><text x={228} y={34} textAnchor="middle" fontSize={12} fill="#fff" fontWeight={700}>H</text>
          {[30, 85].map((y, i) => <g key={y}><rect x={270} y={y - 13} width={30} height={26} rx={5} fill={stage >= 3 ? 'var(--gold)' : 'var(--bg-3)'} /><text x={285} y={y + 4} textAnchor="middle" fontSize={11} fontWeight={700} fill="#fff">{stage >= 3 && k ? k[i] : 'M'}</text>
            <path d={`M300,${y} C380,${y} 380,140 ${i ? 400 : 440},125`} fill="none" stroke="var(--gold)" strokeDasharray="4 4" opacity={stage >= 4 ? 1 : 0.2} /></g>)}
          <rect x={395} y={127} width={26} height={26} rx={5} fill={stage >= 5 ? 'var(--mint)' : 'var(--bg-3)'} /><text x={408} y={144} textAnchor="middle" fontSize={12} fill="#fff" fontWeight={700}>X</text>
          <rect x={435} y={127} width={26} height={26} rx={5} fill={stage >= 5 ? 'var(--mint)' : 'var(--bg-3)'} /><text x={448} y={144} textAnchor="middle" fontSize={12} fill="#fff" fontWeight={700}>Z</text>
        </svg>
        <Slider label="flip probability m₀ (classical tamper)" value={m0} min={0} max={1} step={0.01} onChange={setM0} tone="threat" format={(v) => pct(v, 0)} />
        <Slider label="flip probability m₁" value={m1} min={0} max={1} step={0.01} onChange={setM1} tone="threat" format={(v) => pct(v, 0)} />
        <Button variant="primary" icon={<Play />} onClick={run}>Teleport the current state</Button>
        {res && <>
          <div className="grid g2" style={{ ['--gap' as string]: '8px' }}>{res.outcomes.map((o) => (
            <div key={o.k} className={`outcome ${k === `${o.bits[0]}${o.bits[1]}` ? 'on' : ''}`}><b className="mono">k = {o.bits.join('')}</b>
              <div className="progress"><i style={{ width: `${o.prob * 100}%` }} /></div><span className="xs mono muted">p = {fix(o.prob, 4)}</span>
              <span className="xs mono">after correction ({o.bloch_post.map((x) => fix(x, 2)).join(', ')})</span></div>))}</div>
          <KeyValue rows={[['average received state', `(${res.average_bloch.map((x) => fix(x, 3)).join(', ')})`], ['fidelity with input', res.fidelity != null ? fix(res.fidelity, 4) : 'input not pure']]} />
        </>}
      </div>
    </Panel>
  );
}

function MeasureTool({ r, channels }: { r: V3; channels: ChannelSpec[] }) {
  const [basis, setBasis] = useState<'x' | 'y' | 'z'>('z');
  const [shots, setShots] = useState(2000);
  const [res, setRes] = useState<PlaygroundTeleport | null>(null);
  const run = async () => { try { setRes(await ep.pgTeleport({ bloch: r, channels, shots, basis })); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } };
  const s = res?.samples;
  const lo = useMemo(() => { if (!s) return null; const ph = s.counts['0'] / s.shots, se = Math.sqrt(ph * (1 - ph) / s.shots); return [ph - 1.96 * se, ph + 1.96 * se]; }, [s]);
  useEffect(() => { setRes(null); }, [basis]);
  return (
    <Panel tight reveal={false}>
      <div className="stack">
        <Segmented label="Basis" value={basis} onChange={setBasis} options={[{ value: 'x', label: 'X' }, { value: 'y', label: 'Y' }, { value: 'z', label: 'Z' }]} />
        <Slider label="shots" value={shots} min={10} max={20000} step={10} onChange={setShots} />
        <Button variant="primary" icon={<Play />} onClick={run}>Teleport and measure</Button>
        {s && <>
          <BarChart label="measurement counts vs Born rule" height={200} data={[{ label: `+1 (${basis})`, values: [{ key: 'measured', value: s.counts['0'], color: 'var(--lav)' }, { key: 'Born', value: s.born_p0 * s.shots, color: 'var(--mint)' }] },
            { label: `−1 (${basis})`, values: [{ key: 'measured', value: s.counts['1'], color: 'var(--lav)' }, { key: 'Born', value: (1 - s.born_p0) * s.shots, color: 'var(--mint)' }] }]} />
          <KeyValue rows={[['p(+1) measured', `${fix(s.counts['0'] / s.shots, 4)} [${fix(lo![0], 4)}, ${fix(lo![1], 4)}]`], ['p(+1) Born', fix(s.born_p0, 4)], ['⟨σ⟩ measured', fix((s.counts['0'] - s.counts['1']) / s.shots, 4)]]} />
        </>}
      </div>
    </Panel>
  );
}
