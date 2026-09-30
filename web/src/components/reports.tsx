import { useState } from 'react';
import { motion } from 'motion/react';
import { CheckCircle2, AlertTriangle, XCircle, MinusCircle } from 'lucide-react';
import type { DistributionReport, Finding, Report, SignatureReport, Verification, LinkEvidence, Design } from '@/api/types';
import { catLabel, fix, int, ms, pct, sci, bytes, clock } from '@/lib/format';
import { sevColor } from '@/lib/color';
import { Chip, HashChip, InfoButton, KeyValue, SeverityPill, Tabs, VerdictBadge } from './ui';
import { BarChart, BitGrid, ChshGauge, MatrixView, QubitGrid, SprtChart } from '@/charts/charts';
import { JsonViewer } from './JsonViewer';

const TOPIC: Record<string, string> = { D1: 'chsh', D2: 'chsh', D3a: 'witness', D3b: 'witness', D4: 'qber', D5: 'detwirl', D6: 'frame', D7: 'source_consistency', D8: 'copy_consistency', D9: 'margin', D10: 'cusum',
  S1: 'protocol_guard', S2: 'protocol_guard', S3: 'protocol_guard', S4: 'protocol_guard', S5: 'protocol_guard', S6: 'protocol_guard', S7: 'key_tests', S8: 'sprt', S9: 'forensics', S10: 'symmetrization' };
const topicOf = (id: string) => TOPIC[id.split('.')[0]] || 'threat_score';

export function FindingCard({ f, i = 0 }: { f: Finding; i?: number }) {
  const Icon = !f.fired ? CheckCircle2 : f.severity === 'CRITICAL' || f.severity === 'HIGH' ? XCircle : f.severity === 'NONE' ? MinusCircle : AlertTriangle;
  const color = !f.fired ? 'var(--ok)' : sevColor(f.severity);
  const lp = f.log10_p ?? (f.p_value != null && f.p_value > 0 ? Math.log10(f.p_value) : null);
  const la = f.alpha != null && f.alpha > 0 ? Math.log10(f.alpha) : null;
  return (
    <motion.div className={`finding ${f.fired ? 'fired' : ''}`} style={{ ['--c' as string]: color }} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i, 12) * 0.04 }}>
      <Icon className="f-icon" aria-hidden />
      <div className="grow" style={{ minWidth: 0 }}>
        <div className="row between wrap" style={{ gap: 8 }}>
          <b className="small">{f.name} <span className="mono xs faint">{f.id.split('.')[0]}{f.link_id ? ` · ${f.link_id}` : ''}</span></b>
          <span className="row" style={{ gap: 4 }}>{f.fired && <SeverityPill level={f.severity} compact />}{f.conclusive && <Chip mono>conclusive</Chip>}<InfoButton topic={topicOf(f.id)} /></span>
        </div>
        <p className="xs" style={{ margin: '4px 0 0', color: 'var(--text-1)' }}>{f.evidence}</p>
        {lp != null && la != null && (
          <div className="pbar" title={`p = ${sci(f.p_value)} vs α = ${sci(f.alpha)}`}>
            <i style={{ width: `${Math.min(100, (Math.min(-lp, 30) / 30) * 100)}%`, background: f.fired ? color : 'var(--text-3)' }} />
            <em style={{ left: `${Math.min(100, (-la / 30) * 100)}%` }} />
            <span className="mono xs faint">p = {sci(f.p_value)} · α = {sci(f.alpha)}{f.effect != null ? ` · effect ${fix(f.effect, 4)}` : ''}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

export function FindingsList({ findings, showAll = false }: { findings: Finding[]; showAll?: boolean }) {
  const [all, setAll] = useState(showAll);
  const sorted = [...findings].sort((a, b) => Number(b.fired) - Number(a.fired));
  const fired = sorted.filter((f) => f.fired).length;
  const list = all ? sorted : sorted.filter((f) => f.fired).concat(sorted.filter((f) => !f.fired).slice(0, Math.max(0, 4 - fired)));
  return (
    <div className="stack" style={{ ['--gap' as string]: '8px' }}>
      <div className="row between"><span className="small muted">{fired} of {findings.length} detectors fired</span><button className="btn ghost sm" onClick={() => setAll(!all)}>{all ? 'Fired first' : `Show all ${findings.length}`}</button></div>
      {list.map((f, i) => <FindingCard key={`${f.id}-${f.link_id}-${i}`} f={f} i={i} />)}
    </div>
  );
}

export function ClassificationCard({ report }: { report: Report }) {
  const a = report.assessment, c = a.classification;
  return (
    <div className="class-card" style={{ ['--c' as string]: sevColor(a.threat_level) }}>
      <div className="row between wrap"><VerdictBadge verdict={report.verdict} size="lg" /><SeverityPill level={a.threat_level} /></div>
      <h3 style={{ marginTop: 12 }}>{c.category === 'NONE' ? 'No threat detected' : `${catLabel(c.category)}${c.subtype ? ` · ${c.subtype.replace(/_/g, ' ')}` : ''}`}</h3>
      <p className="small" style={{ margin: '6px 0 0', color: 'var(--text-1)' }}>{c.explanation}</p>
      <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
        {c.rule && <Chip mono>rule {c.rule}</Chip>}{c.confidence && c.confidence !== 'none' && <Chip>{c.confidence}</Chip>}
        {c.attributed_to && <Chip tone="threat">attributed to {c.attributed_to}</Chip>}
        <Chip mono title="UI-only aggregate; decisions never use it">score {fix(a.threat_score, 2)}</Chip>
      </div>
      {c.alternatives?.length > 0 && <p className="xs muted" style={{ marginTop: 8 }}>Physically equivalent explanations: {c.alternatives.join(' · ')}</p>}
    </div>
  );
}

export function DesignTable({ d }: { d: Design | null }) {
  if (!d) return <p className="muted small">No design recorded.</p>;
  const row = (k: string, v: number, target: number, ok: boolean, topic: string) => (
    <tr key={k}><td>{k} <InfoButton topic={topic} /></td><td className="num">{sci(v)}</td><td className="num faint">≤ {sci(target)}</td><td>{ok ? <Chip tone="ok">met</Chip> : <Chip tone="warn">not met</Chip>}</td></tr>
  );
  return (
    <div className="stack" style={{ ['--gap' as string]: '10px' }}>
      <KeyValue rows={[['L (positions per key)', int(d.L)], ['tested positions n_min', int(d.n_min)], ['honest error bound e_ucb', pct(d.e_ucb, 3)],
        ['accept threshold s_a', `${pct(d.s_a, 2)} (m ≤ ${d.c_a})`], ['transfer threshold s_v', `${pct(d.s_v, 2)} (m ≤ ${d.c_v})`], ['forger rate p_forge', fix(d.p_forge, 4)]]} />
      <div className="table-wrap"><table className="table"><thead><tr><th>bound</th><th className="num">value</th><th className="num">target</th><th /></tr></thead><tbody>
        {row('ε_rob (message)', d.eps_rob_msg, d.targets.eps_rob, d.meets_targets.robustness, 'eps_rob')}
        {row('ε_forge (per key)', d.eps_forge_key, d.targets.eps_forge, d.meets_targets.forgery, 'eps_forge')}
        {row('ε_rep (message)', d.eps_rep_msg, d.targets.eps_rep, d.meets_targets.repudiation, 'eps_rep')}
      </tbody></table></div>
      {!d.meets_targets.repudiation && <p className="xs warn-text">This preset trades repudiation strength for speed; the standard and high presets meet all three targets.</p>}
    </div>
  );
}

function keyCells(v: Verification) {
  return v.keys.pass.map((p, i) => ({ state: (v.keys.inconclusive[i] ? 'inconclusive' : p ? 'pass' : 'fail') as 'pass' | 'fail' | 'inconclusive',
    title: `key ${i}: own ${v.keys.m_own[i]}/${v.keys.n_own[i]} · recv ${v.keys.m_recv[i]}/${v.keys.n_recv[i]}` }));
}

export function VerificationView({ v, compact }: { v: Verification; compact?: boolean }) {
  const passed = v.keys.pass.reduce((a, b) => a + b, 0);
  return (
    <div className="stack" style={{ ['--gap' as string]: '12px' }}>
      <div className="row between wrap">
        <div className="row" style={{ gap: 8 }}><b>{v.verifier_id}</b><Chip mono>{v.role}</Chip><Chip mono>{v.mode}</Chip></div>
        <VerdictBadge verdict={v.decision === 'ACCEPT' ? 'ACCEPTED' : v.decision === 'REJECT' ? 'REJECTED' : 'SKIPPED'} />
      </div>
      <KeyValue rows={[['keys passed', `${passed} / ${v.keys.pass.length}`], ['mismatches (all tested)', `${int(v.totals.mismatches)} / ${int(v.totals.tested)} = ${pct(v.totals.rate, 3)}`],
        ['threshold s', pct(v.threshold, 2)], ['SPRT', v.sprt?.enabled ? (v.sprt.early_reject ? `early reject at key ${v.sprt.reject_key} after ${pct(v.sprt.fraction_read, 1)} read` : `no early reject (${pct(v.sprt.fraction_read, 0)} read)`) : 'off'],
        ['verify time', ms(v.latency_ms)]]} />
      <div><div className="label" style={{ marginBottom: 6 }}>256 keys (hover for counts)</div><BitGrid cells={keyCells(v)} cols={32} size={compact ? 9 : 12} label={`${v.verifier_id} per-key results`} /></div>
      {!compact && v.grid_sample && <div><div className="label" style={{ marginBottom: 6 }}>Sampled records · {v.grid_sample.keys} keys × {v.grid_sample.positions} positions (colour = basis X/Y/Z, faded = not tested, ring = mismatch, dot = received via symmetrization)</div><QubitGrid cells={v.grid_sample.cells} label="sampled qubit records" /></div>}
      {!compact && v.sprt?.traces?.length > 0 && <SprtChart traces={v.sprt.traces} A={v.sprt.A} B={v.sprt.B} height={200} />}
      {v.guard?.length > 0 && <div className="row wrap" style={{ gap: 6 }}>{v.guard.map((g) => <Chip key={g.id} tone={g.fired ? 'threat' : 'ok'} title={g.evidence}>{g.fired ? '✕' : '✓'} {g.name}</Chip>)}</div>}
    </div>
  );
}

export function LinkEvidenceView({ ev, compact }: { ev: LinkEvidence; compact?: boolean }) {
  const [view, setView] = useState<'detwirled' | 'effective'>('detwirled');
  const tomo = ev.tomography?.[view];
  const base = ev.baseline;
  const qb = ['x', 'y', 'z'].map((b) => ({ label: b.toUpperCase(), values: [
    { key: 'baseline', value: base?.qber_per_basis?.[b] ?? 0, color: 'var(--mint)' },
    { key: 'measured', value: ev.pe.per_basis[b]?.rate ?? 0, color: 'var(--sky)' },
    { key: 'Bell-predicted', value: ev.bell.predicted_error?.[b]?.rate ?? 0, color: 'var(--lav)' }] }));
  return (
    <div className="stack" style={{ ['--gap' as string]: '12px' }}>
      <div className="row between wrap"><b>{ev.link_id} <span className="muted xs">→ {ev.verifier_id}</span></b>{ev.findings?.some((f) => f.fired) ? <Chip tone="threat">{ev.findings.filter((f) => f.fired).length} findings</Chip> : <Chip tone="ok">clean</Chip>}</div>
      <div className="row wrap top" style={{ gap: 16 }}>
        <ChshGauge S={ev.bell.S} S_lcb={ev.bell.S_lcb} S0={base?.S} size={compact ? 150 : 190} label={`${ev.link_id} CHSH`} />
        <div className="grow" style={{ minWidth: 240 }}>
          <KeyValue rows={[['CHSH S (LCB)', `${fix(ev.bell.S, 3)} (${fix(ev.bell.S_lcb, 3)})`], ['fidelity F (LCB)', `${fix(ev.bell.F, 4)} (${fix(ev.bell.F_lcb, 4)})`],
            ['PE QBER', `${pct(ev.pe.qber, 3)} · ${int(ev.pe.errors)}/${int(ev.pe.matched)}`], ['baseline QBER', pct(base?.qber, 3)],
            ['frame mismatches', `${ev.frame.mismatched}/${int(ev.frame.compared)}${ev.frame.mac !== 'absent' ? ` · MAC ${ev.frame.mac}` : ''}`], ['modelled hardware time', ms(ev.hardware_time_ms_modelled)]]} />
        </div>
      </div>
      <div><div className="label row" style={{ marginBottom: 4 }}>QBER per basis <InfoButton topic="qber" /></div>
        <BarChart data={qb} height={compact ? 150 : 190} label="QBER per basis" fy={(v) => `${(v * 100).toFixed(1)}%`} /></div>
      {!compact && tomo && (
        <div className="stack" style={{ ['--gap' as string]: '8px' }}>
          <div className="row between wrap"><div className="label row">Channel map (M, c) <InfoButton topic="detwirl" /></div>
            <div className="seg"><button aria-pressed={view === 'detwirled'} onClick={() => setView('detwirled')}>de-twirled</button><button aria-pressed={view === 'effective'} onClick={() => setView('effective')}>effective (twirled)</button></div></div>
          <div className="row wrap top" style={{ gap: 16 }}>
            <MatrixView m={tomo.M} labels={['x', 'y', 'z']} colLabels={['x', 'y', 'z']} label="Bloch map M" max={1} />
            <MatrixView m={tomo.c.map((v) => [v])} labels={['x', 'y', 'z']} colLabels={['c']} label="translation c" max={0.5} />
          </div>
          {view === 'effective' && <p className="xs muted">The effective view is what verification experiences: teleportation’s Pauli twirl hides non-unital and coherent components. The de-twirled view recovers them.</p>}
        </div>
      )}
    </div>
  );
}

export function LatencyBars({ lat }: { lat: Record<string, number> }) {
  const entries = Object.entries(lat).filter(([k, v]) => k !== 'total' && k !== 'total_ms' && typeof v === 'number');
  const total = lat.total ?? lat.total_ms ?? entries.reduce((a, [, v]) => a + v, 0);
  let acc = 0;
  return (
    <div className="stack" style={{ ['--gap' as string]: '6px' }}>
      {entries.map(([k, v]) => { const left = (acc / total) * 100; acc += v; return (
        <div key={k} className="lat-row"><span className="xs mono">{k.replace(/_ms$/, '').replace(/_/g, ' ')}</span>
          <div className="lat-track"><motion.i initial={{ width: 0 }} animate={{ width: `${(v / total) * 100}%` }} style={{ left: `${left}%` }} /></div><span className="xs mono num">{ms(v)}</span></div>); })}
      <div className="xs muted">total {ms(total)}</div>
    </div>
  );
}

export function SignatureReportView({ r, compact }: { r: SignatureReport; compact?: boolean }) {
  const [tab, setTab] = useState<'summary' | 'findings' | 'bounds' | 'raw'>('summary');
  return (
    <div className="stack">
      <ClassificationCard report={r} />
      <Tabs label="Report sections" value={tab} onChange={setTab} items={[{ value: 'summary', label: 'Verifiers' }, { value: 'findings', label: 'Findings' }, { value: 'bounds', label: 'ε bounds' }, { value: 'raw', label: 'Raw' }]} />
      {tab === 'summary' && <>
        <KeyValue rows={[['message', r.envelope?.message ?? '—'], ['signer → recipients', `${r.envelope?.signer_id} → ${r.envelope?.recipients?.join(', ')}`], ['seq · nonce', `${r.envelope?.seq} · ${r.envelope?.nonce?.slice(0, 12)}…`],
          ['digest (SHA-256)', <HashChip key="d" hash={r.digest?.hex} head={12} tail={10} />], ['signature size', bytes(r.signature?.size_bytes ?? 0)], ['bundle', <HashChip key="b" hash={r.bundle_id} />], ['time', clock(r.created_at)]]} />
        <div className={compact ? 'stack' : 'grid g2'}>{r.verifications.map((v) => <div key={v.verifier_id + v.role} className="panel tight" data-reveal=""><VerificationView v={v} compact={compact} /></div>)}</div>
        {r.latency_ms && <LatencyBars lat={r.latency_ms} />}
        {r.notes?.length > 0 && <div className="banner info">{r.notes.join(' · ')}</div>}
      </>}
      {tab === 'findings' && <FindingsList findings={r.assessment.findings} />}
      {tab === 'bounds' && <DesignTable d={r.design} />}
      {tab === 'raw' && <JsonViewer data={r} filename={`signature-${r.session_id}.json`} />}
    </div>
  );
}

export function DistributionReportView({ r, compact }: { r: DistributionReport; compact?: boolean }) {
  const [tab, setTab] = useState<'links' | 'findings' | 'bounds' | 'raw'>('links');
  return (
    <div className="stack">
      <ClassificationCard report={r} />
      <Tabs label="Report sections" value={tab} onChange={setTab} items={[{ value: 'links', label: 'Links' }, { value: 'findings', label: 'Findings' }, { value: 'bounds', label: 'ε bounds' }, { value: 'raw', label: 'Raw' }]} />
      {tab === 'links' && <>
        <KeyValue rows={[['group', `${r.signer_id} → ${r.recipients.join(', ')}`], ['preset', `${r.preset} · L = ${int(r.params?.L as number)}`], ['qubits teleported', int(r.qubits_teleported)], ['Bell pairs sacrificed', int(r.bell_pairs)],
          ['records swapped per key (symmetrization)', int(r.symmetrization?.forwarded_per_key as number)], ['bundle', <HashChip key="b" hash={r.bundle_id} />], ['status', r.status]]} />
        <div className={compact ? 'stack' : 'grid g2'}>{r.links.map((ev) => <div key={ev.link_id} className="panel tight" data-reveal=""><LinkEvidenceView ev={ev} compact={compact} /></div>)}</div>
        {r.latency_ms && <LatencyBars lat={r.latency_ms} />}
      </>}
      {tab === 'findings' && <FindingsList findings={r.assessment.findings} />}
      {tab === 'bounds' && <DesignTable d={r.design} />}
      {tab === 'raw' && <JsonViewer data={r} filename={`distribution-${r.session_id}.json`} />}
    </div>
  );
}

export function ReportView({ report, compact }: { report: Report; compact?: boolean }) {
  return report.kind === 'signature' ? <SignatureReportView r={report} compact={compact} /> : <DistributionReportView r={report as DistributionReport} compact={compact} />;
}
