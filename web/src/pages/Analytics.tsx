import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'motion/react';
import { Play, Square, Download, CheckCircle2, XCircle, Loader2, Layers } from 'lucide-react';
import type { Job, JobKind } from '@/api/types';
import { ep, qk } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { toast } from '@/state/ui';
import { Button, Chip, Panel, Slider, Progress, KeyValue, InfoButton, Empty, Segmented } from '@/components/ui';
import { LineChart, BarChart, Heatmap, PmfChart, MatrixView } from '@/charts/charts';
import { useDebounced, useNow } from '@/components/motion';
import { ago, compact, fix, int, ms, pct, sci } from '@/lib/format';

const ORDER = ['detection_matrix', 'roc', 'forgery_analysis', 'threshold_design', 'sprt_efficiency', 'channel_fingerprint', 'cusum_arl', 'performance', 'repudiation_analysis', 'engine_validation'];
const COLORS = ['var(--lav)', 'var(--sky)', 'var(--mint)', 'var(--coral)', 'var(--gold)', 'var(--diana)', 'var(--peach)', 'var(--erin)'];

function download(name: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${name}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function useLatest(kind: string) {
  return useQuery({ queryKey: qk.latest(kind), queryFn: () => ep.latest(kind), retry: false, staleTime: 30_000 });
}

export default function Analytics() {
  const loc = useLocation();
  const kinds = useQuery({ queryKey: qk.kinds, queryFn: ep.analyticsKinds, staleTime: Infinity });
  const jobs = useQuery({ queryKey: qk.jobs, queryFn: () => ep.jobs(40), refetchInterval: 4000 });
  const list = useMemo(() => ORDER.map((k) => kinds.data?.find((x) => x.kind === k)).filter(Boolean) as JobKind[], [kinds.data]);
  useEffect(() => { if (loc.hash) setTimeout(() => document.getElementById(loc.hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 400); }, [loc.hash]);
  const runSuite = async () => {
    let n = 0;
    for (const k of ORDER) { try { await ep.submitJob(k, 'quick'); n++; } catch { /* already running */ } }
    toast({ tone: 'info', title: `Queued ${n} quick analyses`, body: 'The server runs them one at a time; results appear here as they finish.' });
    jobs.refetch();
  };
  return (
    <div className="stack">
      <header className="page-head">
        <div><span className="kicker">Evaluation · theory · validation</span><h1>Analytics</h1>
          <p>Every chart on this page is produced by an analysis job the engine runs on demand: Monte Carlo over the real protocol, exact binomial theory, and cross-validation against Qiskit Aer.</p></div>
        <Button variant="brand" icon={<Layers />} onClick={runSuite}>Run quick suite</Button>
      </header>
      <nav className="chip-nav" aria-label="Sections">{list.map((k) => <a key={k.kind} className="chip" href={`#${k.kind}`}>{k.title}</a>)}</nav>
      <div className="job-grid">{list.map((k) => <JobCard key={k.kind} kind={k} jobs={jobs.data || []} />)}</div>
      <Section id="detection_matrix" title="Detection matrix" what="Every catalog attack at several intensities, plus honest traffic, run through the full protocol. Detection, classification and false rejections with exact (Clopper–Pearson) intervals."><DetectionSection /></Section>
      <Section id="roc" title="ROC curves" what="Weak attacks swept against each detector’s significance level α: the false-positive rate on honest runs vs the true-positive rate on attacked runs."><RocSection /></Section>
      <Section id="forgery_analysis" title="Forgery probability" what="Exact per-key forgery probability for external and insider forgers vs key length, Chernoff bounds, Monte Carlo with confidence intervals, and the insider’s optimum over all measurement directions."><ForgerySection /></Section>
      <Section id="threshold_design" title="Threshold designer" what="Pick L, the honest error bound and the targets: the designer returns s_a < s_v and the three security bounds from exact binomial tails."><ThresholdSection /></Section>
      <Section id="sprt_efficiency" title="Sequential test (SPRT)" what="Average number of observations before a decision, vs the true mismatch rate, compared with Wald’s approximation and with the fixed-sample test."><SprtSection /></Section>
      <Section id="channel_fingerprint" title="Channel fingerprint" what="Does the de-twirled tomography name the right physical family? Confusion of true channel vs the fingerprint’s shape."><FingerprintSection /></Section>
      <Section id="cusum_arl" title="CUSUM run length" what="How many bundles until the drift monitor alarms, vs the size of a persistent QBER shift. At zero shift this is the false-alarm run length."><CusumSection /></Section>
      <Section id="performance" title="Performance" what="Wall-clock cost of distribution and detection vs L, qubits per second, and the table-driven engine vs a Qiskit Aer density-matrix simulation of the same teleportation."><PerformanceSection /></Section>
      <Section id="repudiation_analysis" title="Repudiation" what="A dishonest signer corrupts a fraction r of one recipient’s copy. How often do the recipients disagree, with and without symmetrization?"><RepudiationSection /></Section>
      <Section id="engine_validation" title="Engine validation" what="The exact superoperator engine vs Qiskit Aer on the teleportation circuit for several channels: maximum deviation of every outcome-conditioned state."><ValidationSection /></Section>
    </div>
  );
}

function JobCard({ kind, jobs }: { kind: JobKind; jobs: Job[] }) {
  const qc = useQueryClient();
  const now = useNow(5000);
  const latest = useLatest(kind.kind);
  const active = jobs.find((j) => j.kind === kind.kind && (j.status === 'RUNNING' || j.status === 'QUEUED'));
  const live = useQuery({ queryKey: ['job', active?.id], queryFn: () => ep.job(active!.id), enabled: !!active, refetchInterval: 1500 });
  const a = live.data || active;
  const submit = async (preset: 'quick' | 'full') => { try { await ep.submitJob(kind.kind, preset); qc.invalidateQueries({ queryKey: qk.jobs }); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } };
  const L = latest.data;
  const dur = L?.finished_at && L?.started_at ? (L.finished_at - L.started_at) * 1000 : null;
  return (
    <div className={`job-card ${a ? 'running' : ''}`} data-reveal="">
      <div className="row between"><b>{kind.title}</b>{a ? <Chip tone="info"><Loader2 className="spinning" />{a.status.toLowerCase()}</Chip> : L ? (L.status === 'SUCCEEDED' ? <Chip tone="ok"><CheckCircle2 />done</Chip> : <Chip tone="threat"><XCircle />{L.status.toLowerCase()}</Chip>) : <Chip>never run</Chip>}</div>
      <p className="xs muted">{kind.description}</p>
      {a ? (
        <div className="stack" style={{ ['--gap' as string]: '6px' }}>
          <Progress value={a.progress || 0} label={`${kind.title} progress`} />
          <div className="row between xs muted"><span>{a.message || '…'}</span><button className="btn ghost sm" onClick={async () => { try { await ep.cancelJob(a.id); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } }}><Square />Cancel</button></div>
        </div>
      ) : (
        <div className="row between wrap">
          <span className="xs faint">{L ? `${L.preset} · ${ago(L.finished_at, now)}${dur ? ` · ${ms(dur)}` : ''}` : ''}</span>
          <div className="row" style={{ gap: 6 }}><Button size="sm" icon={<Play />} onClick={() => submit('quick')}>Quick</Button><Button size="sm" variant="ghost" onClick={() => submit('full')}>Full</Button></div>
        </div>
      )}
    </div>
  );
}

function Section({ id, title, what, children }: { id: string; title: string; what: string; children: React.ReactNode }) {
  const latest = useLatest(id);
  return (
    <section id={id} className="an-section">
      <div className="section-title"><span className="kicker">{id.replace(/_/g, ' ')}</span><h2>{title}</h2>
        {latest.data?.result && <button className="btn ghost sm" onClick={() => download(`${id}-${latest.data!.id}`, latest.data)}><Download />JSON</button>}</div>
      <p className="muted small" style={{ maxWidth: 820, marginTop: -8 }}>{what}</p>
      {children}
      {latest.data?.result?.params && <p className="xs faint mono" style={{ overflowWrap: 'anywhere' }}>params {JSON.stringify(latest.data.result.params).slice(0, 220)} · preset {latest.data.preset} · finished {latest.data.finished_at ? new Date(latest.data.finished_at * 1000).toLocaleString() : ''}</p>}
    </section>
  );
}

function NeedsRun({ kind }: { kind: string }) {
  const qc = useQueryClient();
  return <Panel><Empty title="Not run yet" body="Run the quick preset (seconds) or the full preset (minutes). The engine computes everything; nothing is pre-baked." action={<Button icon={<Play />} onClick={async () => { try { await ep.submitJob(kind, 'quick'); qc.invalidateQueries({ queryKey: qk.jobs }); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } }}>Run quick</Button>} /></Panel>;
}

function DetectionSection() {
  const q = useLatest('detection_matrix'); const r = q.data?.result;
  if (!r) return <NeedsRun kind="detection_matrix" />;
  const ints: number[] = r.intensities;
  const cats = [...new Set(r.attacks.map((a: any) => a.category))] as string[];
  return (
    <div className="grid g2" style={{ alignItems: 'start' }}>
      <Panel title="Detection rate · attack × intensity" tight>
        <Heatmap label="detection rate" rows={r.attacks.map((a: any) => a.name)} cols={ints.map((i) => `I = ${i}`)} values={r.attacks.map((a: any) => ints.map((i) => a.points.find((p: any) => p.intensity === i)?.rate ?? null))}
          titleOf={(i, j) => { const p = r.attacks[i].points.find((x: any) => x.intensity === ints[j]); return p ? `${p.detected}/${p.runs} detected · CI [${pct(p.ci[0], 1)}, ${pct(p.ci[1], 1)}]` : ''; }} />
      </Panel>
      <div className="stack">
        <div className="grid g3">
          <div className="kpi"><span>attacks detected</span><b>{r.far.attack_runs - r.far.missed}/{r.far.attack_runs}</b><em>miss rate {pct(r.far.far, 2)} [{pct(r.far.far_ci[0], 2)}, {pct(r.far.far_ci[1], 2)}]</em></div>
          <div className="kpi"><span>classified correctly</span><b>{pct(r.far.classification_accuracy, 1)}</b><em>of detected attacks</em></div>
          <div className="kpi"><span>false rejections</span><b>{r.legit.false_rejections}/{r.legit.runs}</b><em>FRR {pct(r.legit.frr, 2)} [{pct(r.legit.frr_ci[0], 2)}, {pct(r.legit.frr_ci[1], 2)}]</em></div>
        </div>
        <Panel title="Confusion matrix" kicker="rows = ground truth · columns = engine" tight>
          <Heatmap label="confusion matrix" rows={r.confusion.labels.map((l: string) => l.replace(/_/g, ' ').toLowerCase())} cols={r.confusion.labels.map((l: string) => l.slice(0, 5).toLowerCase())}
            values={r.confusion.matrix.map((row: number[]) => { const s = row.reduce((a, b) => a + b, 0) || 1; return row.map((v) => v / s); })} fmt={(v) => (v ? `${Math.round(v * 100)}%` : '·')} color="var(--lav)" />
        </Panel>
        <Panel title="Detection vs intensity by category" tight>
          <LineChart label="detection vs intensity" height={200} xLabel="intensity I" yDomain={[0, 1.05]} fy={(v) => `${Math.round(v * 100)}%`}
            series={cats.map((c, i) => { const as = r.attacks.filter((a: any) => a.category === c); return { id: c, label: c.replace(/_/g, ' ').toLowerCase(), color: COLORS[i % COLORS.length], dots: true,
              points: ints.map((I) => { const ps = as.map((a: any) => a.points.find((p: any) => p.intensity === I)).filter(Boolean); const runs = ps.reduce((s: number, p: any) => s + p.runs, 0); return { x: I, y: runs ? ps.reduce((s: number, p: any) => s + p.detected, 0) / runs : null }; }) }; })} />
        </Panel>
      </div>
    </div>
  );
}

function RocSection() {
  const q = useLatest('roc'); const r = q.data?.result;
  const attacks = r ? [...new Set(r.curves.map((c: any) => `${c.attack_id}@${c.intensity}`))] as string[] : [];
  const [sel, setSel] = useState<string | null>(null);
  if (!r) return <NeedsRun kind="roc" />;
  const cur = sel || attacks[0];
  const curves = r.curves.filter((c: any) => `${c.attack_id}@${c.intensity}` === cur);
  return (
    <Panel tight actions={<Segmented label="Attack" value={cur} onChange={setSel} options={attacks.map((a) => ({ value: a, label: `${a.split('@')[0].split('.')[1]} · I=${a.split('@')[1]}` }))} />} title="ROC" kicker="false-positive rate (log) vs true-positive rate">
      <div className="grid g2" style={{ alignItems: 'start' }}>
        <LineChart label="ROC curves" height={300} xLog xLabel="FPR" yLabel="TPR" yDomain={[0, 1.02]} xDomain={[1e-3, 1]}
          series={curves.map((c: any, i: number) => ({ id: c.detector, label: c.detector, color: c.detector === 'fused' ? 'var(--text-0)' : COLORS[i % COLORS.length], width: c.detector === 'fused' ? 3 : 1.8, step: true,
            points: c.points.map((p: any) => ({ x: Math.max(p.fpr, 1e-3), y: p.tpr })).sort((a: any, b: any) => a.x - b.x) }))} />
        <div className="stack" style={{ ['--gap' as string]: '6px' }}>{curves.map((c: any, i: number) => (
          <div key={c.detector} className="row between auc-row"><span className="row" style={{ gap: 8 }}><span className="dot" style={{ background: c.detector === 'fused' ? 'var(--text-0)' : COLORS[i % COLORS.length] }} />{c.detector}</span><b className="num">AUC {fix(c.auc, 3)}</b></div>))}
          <p className="xs muted">Weak attacks on purpose: single detectors disagree; the fused decision list combines them. {r.runs} runs per class.</p></div>
      </div>
    </Panel>
  );
}

function ForgerySection() {
  const q = useLatest('forgery_analysis'); const r = q.data?.result;
  if (!r) return <NeedsRun kind="forgery_analysis" />;
  const c = r.curves; const L: number[] = c.L;
  const sph = r.insider_optimum?.sphere;
  return (
    <div className="grid g2" style={{ alignItems: 'start' }}>
      <Panel title="ε_forge per key vs L" kicker={`s_v = ${c.s_v} · honest e = ${pct(c.e, 2)}`} explainTopic="eps_forge" tight>
        <LineChart label="forgery probability vs L" height={300} xLog yLog xLabel="L" fx={(v) => compact(v)} series={[
          { id: 'ee', label: 'external · exact', color: 'var(--sky)', points: L.map((x, i) => ({ x, y: c.external.exact[i] })) },
          { id: 'ec', label: 'external · Chernoff', color: 'var(--sky)', dashed: true, points: L.map((x, i) => ({ x, y: c.external.chernoff[i] })) },
          { id: 'ie', label: `insider · exact (p = ${fix(c.p_insider, 3)})`, color: 'var(--coral)', points: L.map((x, i) => ({ x, y: c.insider.exact[i] })) },
          { id: 'ic', label: 'insider · Chernoff', color: 'var(--coral)', dashed: true, points: L.map((x, i) => ({ x, y: c.insider.chernoff[i] })) },
          ...['external', 'insider'].map((s) => ({ id: `mc${s}`, label: `Monte Carlo · ${s}`, color: s === 'external' ? 'var(--lav)' : 'var(--peach)', dots: true, width: 0.01,
            points: r.mc.filter((m: any) => m.strategy === s && m.rate > 0).map((m: any) => ({ x: m.L, y: m.rate, lo: Math.max(m.ci[0], 1e-9), hi: m.ci[1] })) }))]} />
      </Panel>
      <div className="stack">
        {sph && <Panel title="Insider optimum over measurement directions" kicker={`min = ${fix(r.insider_optimum.min, 4)} · external reference ${r.insider_optimum.external_reference}`} tight>
          <SphereMap lat={sph.lat} lon={sph.lon} values={sph.values} />
          <p className="xs muted">The best an insider can do, whatever direction it measures in, is a mismatch of 1/3 at the six axis points: the six-state encoding leaves no better strategy.</p>
        </Panel>}
        {r.message_level && <Panel title="Message level" kicker={`L = ${int(r.message_level.reference_L)}`} tight>
          <KeyValue rows={[['per-key ε_forge', sci(r.message_level.eps_key)], ...r.message_level.k.slice(0, 5).map((k: number, i: number) => [`forging ${k} digest bit${k > 1 ? 's' : ''}`, `10${sup(Math.round(r.message_level.log10_eps[i]))}`] as [string, string]),
            ['random message (≈ 128 bits differ)', `10${sup(Math.round(r.message_level.random_message_log10_eps))}`]]} />
        </Panel>}
      </div>
    </div>
  );
}
const sup = (n: number) => String(n).split('').map((c) => ({ '-': '⁻', 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹' } as Record<string, string>)[c] ?? c).join('');

function SphereMap({ lat, lon, values }: { lat: number[]; lon: number[]; values: number[][] }) {
  const flat = values.flat(); const lo = Math.min(...flat), hi = Math.max(...flat);
  const W = 720, H = 360;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Insider mismatch over measurement directions (equirectangular)">
      {values.map((row, i) => row.map((v, j) => { const k = (v - lo) / (hi - lo || 1); return <rect key={`${i}-${j}`} x={(j / lon.length) * W} y={H - ((i + 1) / lat.length) * H} width={W / lon.length + 0.5} height={H / lat.length + 0.5} fill={`color-mix(in srgb, var(--coral) ${Math.round(k * 80)}%, var(--mint))`} />; }))}
      {[[0, 0, '+x'], [180, 0, '−x'], [90, 0, '+y'], [-90, 0, '−y'], [0, 90, '+z'], [0, -90, '−z']].map(([lo2, la, l]) => { const x = (((lo2 as number) + 180) / 360) * W, y = H - (((la as number) + 90) / 180) * H;
        return <g key={l as string}><circle cx={x} cy={Math.min(H - 6, Math.max(6, y))} r={6} fill="none" stroke="var(--text-0)" strokeWidth={2} /><text x={x + 9} y={Math.min(H - 8, Math.max(14, y))} fontSize={13} fontWeight={700} fill="var(--text-0)">{l as string}</text></g>; })}
    </svg>
  );
}

function ThresholdSection() {
  const [L, setL] = useState(12);    // log2
  const [e, setE] = useState(0.013);
  const [rob, setRob] = useState(-9), [forge, setForge] = useState(-6), [rep, setRep] = useState(-6);
  const qd = useDebounced({ L: 2 ** L, e, eps_rob: 10 ** rob, eps_forge: 10 ** forge, eps_rep: 10 ** rep }, 120);
  const d = useQuery({ queryKey: ['theory', 'design', qd], queryFn: () => ep.design(qd), staleTime: 60_000, placeholderData: (p) => p });
  const table = useLatest('threshold_design');
  const toArr = (x?: { k0: number; pmf: number[] }) => { if (!x) return []; const a: number[] = []; x.pmf.forEach((p, i) => { a[x.k0 + i] = p; }); for (let i = 0; i < a.length; i++) a[i] = a[i] ?? 0; return a; };
  const D = d.data;
  return (
    <div className="grid g2" style={{ alignItems: 'start' }}>
      <Panel title="Design" kicker="drag the sliders" explainTopic="thresholds" tight>
        <div className="stack">
          <Slider label="L (positions per key)" value={L} min={6} max={14} step={0.5} onChange={setL} format={(v) => int(Math.round(2 ** v))} />
          <Slider label="honest error bound e" value={e} min={0.001} max={0.1} step={0.001} onChange={setE} format={(v) => pct(v, 1)} />
          <Slider label="ε_rob target" value={rob} min={-15} max={-2} step={1} onChange={setRob} format={(v) => `10${sup(v)}`} />
          <Slider label="ε_forge target" value={forge} min={-15} max={-2} step={1} onChange={setForge} format={(v) => `10${sup(v)}`} />
          <Slider label="ε_rep target" value={rep} min={-15} max={-2} step={1} onChange={setRep} format={(v) => `10${sup(v)}`} />
          {D && <div className={`banner ${D.feasible && D.meets_targets.robustness && D.meets_targets.forgery && D.meets_targets.repudiation ? 'info' : 'warn'}`}>
            {D.feasible ? (D.meets_targets.robustness && D.meets_targets.forgery && D.meets_targets.repudiation ? 'All three targets met.' : `Feasible, but not every target is met${D.L_min ? ` — L ≥ ${int(D.L_min)} needed` : ''}.`) : `Infeasible: no s_a < s_v meets the targets${D.L_min ? ` — need L ≥ ${int(D.L_min)}` : ''}.`}</div>}
        </div>
      </Panel>
      <Panel title="Mismatch distributions" kicker={D ? `n = ${D.n_min} tested positions · s_a = ${pct(D.s_a, 2)} · s_v = ${pct(D.s_v, 2)}` : ''} tight>
        {D?.pmf_honest ? <PmfChart n={D.n_min} honest={toArr(D.pmf_honest)} forger={toArr(D.pmf_forger)} sA={D.s_a} sV={D.s_v} height={260} /> : <div className="skeleton" style={{ height: 260 }} />}
        {D && <KeyValue rows={[['ε_rob (message)', sci(D.eps_rob_msg)], ['ε_forge (key)', sci(D.eps_forge_key)], ['ε_rep (message)', sci(D.eps_rep_msg)], ['SPRT A / B', `${fix(D.sprt.A, 1)} / ${fix(D.sprt.B, 1)}`]]} />}
      </Panel>
      {table.data?.result?.rows && <Panel className="span2" title="Design table" kicker="threshold_design job" tight>
        <div className="table-wrap"><table className="table"><thead><tr><th className="num">e</th><th className="num">L</th><th className="num">s_a</th><th className="num">s_v</th><th className="num">ε_rob</th><th className="num">ε_forge</th><th className="num">ε_rep (msg)</th><th /></tr></thead>
          <tbody>{table.data.result.rows.map((r: any, i: number) => <tr key={i}><td className="num">{pct(r.e, 2)}</td><td className="num">{int(r.L)}</td><td className="num">{pct(r.s_a, 2)}</td><td className="num">{pct(r.s_v, 2)}</td><td className="num">{sci(r.eps_rob)}</td><td className="num">{sci(r.eps_forge)}</td><td className="num">{sci(r.eps_rep_msg)}</td>
            <td>{r.feasible && r.meets?.robustness && r.meets?.forgery && r.meets?.repudiation ? <Chip tone="ok">meets</Chip> : r.feasible ? <Chip tone="warn">partial</Chip> : <Chip tone="threat">infeasible</Chip>}</td></tr>)}</tbody></table></div>
      </Panel>}
    </div>
  );
}

function SprtSection() {
  const q = useLatest('sprt_efficiency'); const r = q.data?.result;
  if (!r) return <NeedsRun kind="sprt_efficiency" />;
  const pts = r.points;
  return (
    <div className="grid g2">
      <Panel title="Average sample number" kicker={`fixed-sample test reads n = ${r.fixed_n}`} explainTopic="sprt" tight>
        <LineChart label="ASN vs p" height={260} yLog xLabel="true mismatch rate p" yLabel="observations" refs={[{ y: r.fixed_n, label: `fixed n = ${r.fixed_n}`, color: 'var(--text-2)' }, { x: r.params.p0, label: 'p₀', color: 'var(--ok)' }, { x: r.params.p1, label: 'p₁ = 1/3', color: 'var(--coral)' }]}
          series={[{ id: 'mc', label: 'Monte Carlo', color: 'var(--lav)', dots: true, points: pts.map((p: any) => ({ x: p.p, y: p.asn_mc })) }, { id: 'w', label: 'Wald approximation', color: 'var(--sky)', dashed: true, points: pts.map((p: any) => ({ x: p.p, y: p.asn_wald })) }]} />
      </Panel>
      <Panel title="Reject rate (operating characteristic)" tight>
        <LineChart label="reject rate vs p" height={260} xLabel="true mismatch rate p" yDomain={[0, 1.02]} fy={(v) => `${Math.round(v * 100)}%`}
          series={[{ id: 'r', label: 'reject rate (MC)', color: 'var(--coral)', dots: true, points: pts.map((p: any) => ({ x: p.p, y: p.reject_rate })) }, { id: 'o', label: 'Wald OC', color: 'var(--text-2)', dashed: true, points: pts.map((p: any) => ({ x: p.p, y: p.oc_wald == null ? null : 1 - p.oc_wald })) }]} />
      </Panel>
    </div>
  );
}

function FingerprintSection() {
  const q = useLatest('channel_fingerprint'); const r = q.data?.result;
  if (!r) return <NeedsRun kind="channel_fingerprint" />;
  return (
    <div className="grid g2" style={{ alignItems: 'start' }}>
      <Panel title="True family × fingerprint shape" explainTopic="detwirl" tight>
        <Heatmap label="fingerprint confusion" rows={r.labels.map((l: string, i: number) => `${l} → ${r.expected[i]}`)} cols={r.shapes.map((s: string) => s.replace(/_/g, ' '))}
          values={r.matrix.map((row: number[]) => { const s = row.reduce((a, b) => a + b, 0) || 1; return row.map((v) => v / s); })} color="var(--sky)" fmt={(v) => (v ? `${Math.round(v * 100)}%` : '·')} />
      </Panel>
      <Panel title="Accuracy per family and strength" tight>
        <BarChart label="fingerprint accuracy" height={280} fy={(v) => `${Math.round(v * 100)}%`} data={[...new Set(r.per_family.map((p: any) => p.family))].map((f: any) => ({ label: String(f).replace('intercept–resend', 'I-R').replace('amplitude damping', 'amp. damp').replace('coherent rotation', 'rotation').replace('frame tampering', 'frame'),
          values: r.per_family.filter((p: any) => p.family === f).map((p: any, i: number) => ({ key: `s=${p.strength}`, value: p.accuracy, color: COLORS[i] })) }))} />
      </Panel>
    </div>
  );
}

function CusumSection() {
  const q = useLatest('cusum_arl'); const r = q.data?.result;
  if (!r) return <NeedsRun kind="cusum_arl" />;
  return (
    <Panel title="Average run length vs shift" kicker={`k = ${r.params.k} · h = ${r.params.h} · e₀ = ${pct(r.e0, 2)} · ${int(r.n_per_bundle)} PE positions per bundle`} explainTopic="cusum" tight>
      <div className="grid g2" style={{ alignItems: 'start' }}>
        <LineChart label="ARL vs shift" height={260} yLog xLabel="QBER shift" fx={(v) => `${(v * 100).toFixed(2)}%`}
          series={[{ id: 'm', label: 'mean run length (bundles)', color: 'var(--coral)', dots: true, points: r.points.map((p: any) => ({ x: p.shift, y: Math.max(1, p.arl_mean) })) }, { id: 'md', label: 'median', color: 'var(--lav)', dashed: true, points: r.points.map((p: any) => ({ x: p.shift, y: Math.max(1, p.arl_median) })) }]} />
        <div className="table-wrap"><table className="table"><thead><tr><th className="num">shift</th><th className="num">ARL</th><th className="num">censored</th><th className="num">false alarms</th></tr></thead>
          <tbody>{r.points.map((p: any) => <tr key={p.shift}><td className="num">{pct(p.shift, 2)}</td><td className="num">{p.censored === p.runs ? `> ${p.horizon}` : fix(p.arl_mean, 1)}</td><td className="num">{p.censored}/{p.runs}</td><td className="num">{p.shift === 0 ? pct(p.false_alarm_rate, 1) : '—'}</td></tr>)}</tbody></table></div>
      </div>
    </Panel>
  );
}

function PerformanceSection() {
  const q = useLatest('performance'); const r = q.data?.result;
  if (!r) return <NeedsRun kind="performance" />;
  return (
    <div className="grid g2" style={{ alignItems: 'start' }}>
      <Panel title="Latency per bundle vs L" tight>
        <BarChart label="latency per stage" height={260} stacked fy={(v) => `${Math.round(v)} ms`} data={r.rows.map((x: any) => ({ label: `L=${x.L}`, values: [
          { key: 'distribution', value: x.distribution_ms, color: 'var(--sky)' }, { key: 'detection', value: x.detect_ms || 0, color: 'var(--coral)' },
          ...(x.sign_ms != null ? [{ key: 'sign', value: x.sign_ms, color: 'var(--gold)' }] : []), ...(x.verify_ms != null ? [{ key: 'verify', value: x.verify_ms, color: 'var(--mint)' }] : [])] }))} />
        <div className="table-wrap"><table className="table"><thead><tr><th className="num">L</th><th className="num">qubits</th><th className="num">distribution</th><th className="num">sign</th><th className="num">verify</th><th className="num">qubits/s</th></tr></thead>
          <tbody>{r.rows.map((x: any) => <tr key={x.L}><td className="num">{int(x.L)}</td><td className="num">{compact(x.qubits)}</td><td className="num">{ms(x.distribution_ms)}</td><td className="num" title={x.sign_ms == null ? 'no feasible design at this L under the active targets: the engine refuses to sign' : undefined}>{x.sign_ms == null ? 'infeasible' : ms(x.sign_ms)}</td><td className="num">{x.verify_ms == null ? '—' : ms(x.verify_ms)}</td><td className="num">{compact(x.qubits_per_s)}</td></tr>)}</tbody></table></div>
      </Panel>
      <Panel title="Exact engine vs Qiskit Aer" tight>
        {r.aer?.available ? <>
          <BarChart label="qubits per second" height={220} yLog fy={(v) => compact(v)} data={[{ label: 'Qiskit Aer (density matrix)', values: [{ key: 'aer', value: r.aer.qubits_per_s, color: 'var(--text-3)' }] },
            { label: 'QVeris table engine', values: [{ key: 'engine', value: Math.max(...r.rows.map((x: any) => x.qubits_per_s)), color: 'var(--mint)' }] }]} />
          <p className="small"><b className="grad-text" style={{ fontSize: 28, fontFamily: 'var(--font-display)' }}>{Math.round(r.speedup)}×</b> faster, and exact: the same outcome-conditioned states to machine precision (see validation).</p>
          <p className="xs muted">{r.aer.note}</p></> : <p className="muted">Qiskit Aer is not installed on this server.</p>}
      </Panel>
    </div>
  );
}

function RepudiationSection() {
  const q = useLatest('repudiation_analysis'); const r = q.data?.result;
  if (!r) return <NeedsRun kind="repudiation_analysis" />;
  return (
    <Panel title="Dispute rate vs corruption fraction r" explainTopic="symmetrization" tight>
      <LineChart label="dispute rate" height={260} xLabel="fraction r of one copy corrupted" yDomain={[0, 1.02]} fy={(v) => `${Math.round(v * 100)}%`} fx={(v) => `${Math.round(v * 100)}%`} series={[
        { id: 'w', label: 'without symmetrization', color: 'var(--coral)', dots: true, points: r.points.map((p: any) => ({ x: p.r, y: p.dispute_without_sym, lo: p.ci_without[0], hi: p.ci_without[1] })) },
        { id: 's', label: 'with symmetrization', color: 'var(--mint)', dots: true, points: r.points.map((p: any) => ({ x: p.r, y: p.dispute_with_sym, lo: p.ci_with[0], hi: p.ci_with[1] })) },
        { id: 'd', label: 'caught already at distribution (D7/D8)', color: 'var(--lav)', dashed: true, points: r.points.map((p: any) => ({ x: p.r, y: p.detected_at_distribution })) }]} />
    </Panel>
  );
}

function ValidationSection() {
  const q = useLatest('engine_validation'); const r = q.data?.result;
  if (!r) return <NeedsRun kind="engine_validation" />;
  return (
    <Panel title={r.pass ? 'Engine agrees with Qiskit Aer' : 'Deviation found'} kicker={`qiskit ${r.qiskit_version} · aer ${r.aer_version} · max |Δ| = ${sci(r.max_dev)}`} tight>
      <div className="table-wrap"><table className="table"><thead><tr><th>channel</th><th>spec</th><th className="num">max |Δρ| over all outcomes</th><th /></tr></thead>
        <tbody>{r.checks.map((c: any) => <tr key={c.name}><td><b>{c.name}</b></td><td className="mono xs">{c.channel.map((x: any) => Object.entries(x).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(' ')).join(' ∘ ') || '—'}</td><td className="num">{sci(c.max_dev)}</td><td>{c.max_dev < 1e-9 ? <Chip tone="ok">pass</Chip> : <Chip tone="threat">fail</Chip>}</td></tr>)}</tbody></table></div>
    </Panel>
  );
}

export { MatrixView, InfoButton, motion };
