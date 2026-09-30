import { useEffect, useMemo, useState } from 'react';
import { Link, useOutletContext, useNavigate } from 'react-router-dom';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { motion } from 'motion/react';
import { ArrowRight, Play, Radar, PenTool, Zap, ShieldCheck, Atom, Repeat, UserX, KeyRound, Waves, Scale, LineChart as LineIcon } from 'lucide-react';
import type { DistributionReport, SignatureReport } from '@/api/types';
import { ep, qk } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { toast } from '@/state/ui';
import { useLive } from '@/state/live';
import { usePrefs, reducedMotion } from '@/state/prefs';
import { Button, Chip, Panel, Stat } from '@/components/ui';
import { CountUp } from '@/components/motion';
import { LegacyScene } from '@/legacy/LegacyScene';
import { storyMetrics } from '@/legacy/adapters';
import { Sparkline, LineChart, Heatmap } from '@/charts/charts';
import { compact, fix, int, pct, sci, shortHash, catLabel } from '@/lib/format';
import { CAT_COLOR } from '@/lib/color';

const STORY_MESSAGE = 'transfer 100 to bob';
// Decided once per page load (StrictMode runs initializers twice): the film plays once per browser session.
let _film: boolean | null = null;
function filmDecision(introSeen: boolean) {
  if (_film != null) return _film;
  try { const seen = sessionStorage.getItem('qveris.film') === '1'; sessionStorage.setItem('qveris.film', '1'); _film = !seen && !introSeen && !reducedMotion(); } catch { _film = false; }
  return _film;
}
async function sha256hex(s: string) { const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)); return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join(''); }

const THREATS = [
  { cat: 'FORGERY', icon: PenTool, name: 'Forgery', line: 'A forger must guess six-state key qubits it never saw: ≥ 1/3 mismatches.', layers: ['S7 key tests', 'S8 SPRT', 'S9 forensics'] },
  { cat: 'IMPERSONATION', icon: UserX, name: 'Impersonation', line: 'A valid key is not the right key: bundles are bound to their signer.', layers: ['S2 key binding', 'S7'] },
  { cat: 'REPLAY', icon: Repeat, name: 'Replay', line: 'Physically invisible — perfect statistics — so the protocol layer catches it.', layers: ['S3 one-time', 'S4 nonce', 'S5 seq', 'S6 freshness'] },
  { cat: 'UNAUTHORIZED_VERIFICATION', icon: KeyRound, name: 'Unauthorized verification', line: 'Harvesting keys in transit breaks entanglement; outsiders hold no records.', layers: ['S1', 'D1 CHSH', 'D7'] },
  { cat: 'CHANNEL_MANIPULATION', icon: Waves, name: 'Channel manipulation', line: 'De-twirled tomography fingerprints dephasing, damping, rotation and frame flips.', layers: ['D1–D6', 'D10 CUSUM'] },
  { cat: 'REPUDIATION', icon: Scale, name: 'Repudiation', line: 'Symmetrization makes a signer unable to split the recipients’ decisions.', layers: ['D7', 'D8', 'S10'] },
] as const;

export default function Overview() {
  const { booted } = useOutletContext<{ booted: boolean }>();
  const nav = useNavigate();
  const introSeen = usePrefs((s) => s.introSeen);
  const metrics = useQuery({ queryKey: qk.metrics('all'), queryFn: () => ep.metrics('all'), refetchInterval: 20_000 });
  const ts = useQuery({ queryKey: qk.timeseries('sessions', { bucket_s: 60 }), queryFn: () => ep.timeseries('sessions', { bucket_s: 60 }) });
  const lastDistS = useQuery({ queryKey: qk.sessions({ kind: 'distribution', limit: 1, attack: false }), queryFn: () => ep.sessions({ kind: 'distribution', limit: 1, attack: false }) });
  const lastSigS = useQuery({ queryKey: qk.sessions({ kind: 'signature', limit: 1, attack: false }), queryFn: () => ep.sessions({ kind: 'signature', limit: 1, attack: false }) });
  const dist = useQuery({ queryKey: qk.session(lastDistS.data?.[0]?.id || ''), queryFn: () => ep.session(lastDistS.data![0].id), enabled: !!lastDistS.data?.[0], staleTime: Infinity, placeholderData: keepPreviousData });
  const sig = useQuery({ queryKey: qk.session(lastSigS.data?.[0]?.id || ''), queryFn: () => ep.session(lastSigS.data![0].id), enabled: !!lastSigS.data?.[0], staleTime: Infinity, placeholderData: keepPreviousData });
  const ledger = useQuery({ queryKey: qk.ledgerSummary, queryFn: ep.ledgerSummary });
  const matrix = useQuery({ queryKey: qk.latest('detection_matrix'), queryFn: () => ep.latest('detection_matrix'), retry: false });
  const forgeryJob = useQuery({ queryKey: qk.latest('forgery_analysis'), queryFn: () => ep.latest('forgery_analysis'), retry: false });
  const traffic = useLive((s) => s.traffic);
  const [digest, setDigest] = useState<string | null>(null);
  useEffect(() => { sha256hex(STORY_MESSAGE).then(setDigest).catch(() => setDigest('')); }, []);
  // The film plays once per browser session (as in the original dashboard), unless disabled in settings.
  const [playFilm] = useState(() => filmDecision(introSeen));
  const storyData = useMemo(() => (digest == null || !metrics.isFetched ? null : { message: STORY_MESSAGE, digest, metrics: storyMetrics(metrics.data), intro: playFilm, stickyTop: document.querySelector('.topbar')?.getBoundingClientRect().height ?? 0 }), [digest, metrics.isFetched]); // eslint-disable-line react-hooks/exhaustive-deps

  const m = metrics.data;
  const pts = ts.data?.points || [];
  const d = dist.data as DistributionReport | undefined;
  const s = sig.data as SignatureReport | undefined;
  const firstLink = d?.links?.[0];
  const v1 = s?.verifications?.[0];
  const idle = m && m.sessions.signature_total === 0;
  const startTraffic = async () => { try { await ep.trafficStart(12); toast({ tone: 'ok', title: 'Live traffic started', body: 'Honest signing traffic now flows through the engine.' }); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } };

  const chapters: [string, string, string | null][] = [
    ['01 · Entangle', 'Bell pairs certified by CHSH', firstLink ? `${firstLink.link_id}  S = ${fix(firstLink.bell.S, 3)}  (LCB ${fix(firstLink.bell.S_lcb, 3)} > 2)` : null],
    ['02 · Teleport', 'Key qubits teleported', d ? `${int(d.qubits_teleported)} qubits · ${d.links.reduce((a, l) => a + l.frame.mismatched, 0)} frame errors` : null],
    ['03 · Estimate', 'Parameter estimation', firstLink ? `QBER ${pct(firstLink.pe.qber, 2)} on ${int(firstLink.pe.matched)} matched positions` : null],
    ['04 · Symmetrize', 'Records swapped', d ? `${int(d.symmetrization?.forwarded_per_key as number)} records swapped per key` : null],
    ['05 · Sign', 'One-time keys revealed', s ? `digest ${shortHash(s.digest.hex)} · 256 keys revealed` : null],
    ['06 · Verify', 'Both recipients test', v1 ? `mismatch ${pct(v1.totals.rate, 2)} ≤ s_a ${pct(v1.threshold, 2)}` : null],
    ['07 · Detect', 'QSentinel', m?.detection.attack_runs ? `detected ${m.detection.detected}/${m.detection.attack_runs} · false alarms ${m.detection.false_rejections}/${m.detection.legit_runs}` : null],
    ['08 · Anchor', 'Audit ledger', ledger.data ? `block #${ledger.data.height} · ${shortHash(ledger.data.head_hash)}` : null],
  ];

  return (
    <div className="overview">
      <section className="story-host" aria-label="The journey of a signature (interactive 3D story)">
        {booted && storyData
          ? <LegacyScene scene="story" channel="story" data={storyData} label="The journey of a signature: an interactive 3D film scrubbed by scrolling" style={{ width: '100%', height: '100vh', borderRadius: 0, boxShadow: 'none' }} />
          : <div className="story-placeholder"><div className="empty"><div className="orb" /><h4>Preparing the story…</h4></div></div>}
      </section>

      <section className="ov-live">
        <div className="section-title"><span className="kicker">After the story</span><h2>The live system</h2></div>
        <p className="muted" style={{ maxWidth: 760 }}>Everything below runs the real engine: teleportation-based quantum digital signatures with physics-grounded threat detection. No machine learning, no fabricated numbers.</p>
        <div className="grid g4" style={{ marginTop: 18 }}>
          <Stat label="Signatures verified" value={<CountUp value={m?.sessions.accepted ?? null} format={(v) => int(v)} />} sub={m ? `${m.sessions.signature_total} total · ${m.sessions.rejected} rejected` : ''}
            spark={<Sparkline values={pts.map((p) => p.accepted)} color="var(--mint)" label="accepted per minute" />} />
          <Stat label="Attacks detected" explainTopic="threat_score" value={m?.detection.attack_runs ? `${m.detection.detected}/${m.detection.attack_runs}` : '—'} sub={m?.detection.attack_runs ? `${pct(m.detection.classification_accuracy, 1)} correctly classified` : 'launch one in the Attack Lab'}
            spark={<Sparkline values={pts.map((p) => p.attacks)} color="var(--coral)" label="attacks per minute" />} />
          <Stat label="Mean CHSH S" explainTopic="chsh" value={<CountUp value={m?.mean_chsh_recent ?? null} format={(v) => v.toFixed(3)} />} sub="last certified links · classical bound 2" />
          <Stat label="Ledger height" explainTopic="ledger" value={<CountUp value={ledger.data?.height ?? null} />} sub={ledger.data ? `${int(ledger.data.tx_total)} transactions` : ''} />
        </div>
        {idle && (
          <div className="banner info" style={{ marginTop: 14 }}><Play /><span className="grow">Engine idle — no signatures measured yet.</span><Button size="sm" variant="primary" onClick={startTraffic}>Start live traffic</Button></div>
        )}
        <div className="row wrap" style={{ marginTop: 18 }}>
          <Button variant="brand" size="lg" icon={<Radar />} onClick={() => nav('/command')}>Enter Command Center</Button>
          <Button size="lg" icon={<PenTool />} onClick={() => nav('/studio')}>Sign a message</Button>
          <Button size="lg" variant="ghost" icon={<Zap />} onClick={() => nav('/attack-lab')}>Launch an attack</Button>
          {!traffic?.running && <Button size="lg" variant="ghost" icon={<Play />} onClick={startTraffic}>Start live traffic</Button>}
        </div>
      </section>

      <section>
        <div className="section-title"><span className="kicker">Pipeline · bound to the latest real runs</span><h2>Eight steps, measured</h2></div>
        <div className="chapter-grid">
          {chapters.map(([k, t, proof], i) => (
            <motion.div key={k} className="chapter-card qv-tilt" initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-40px' }} transition={{ delay: (i % 4) * 0.06 }}>
              <span className="kicker">{k}</span><b>{t}</b>
              <code className={proof ? '' : 'faint'}>{proof ?? 'not measured yet'}</code>
            </motion.div>
          ))}
        </div>
      </section>

      <section>
        <div className="section-title"><span className="kicker">Threat model · 17 attacks in 6 classes</span><h2>What QSentinel catches</h2></div>
        <div className="threat-grid">
          {THREATS.map((t) => {
            const pc = m?.detection.per_category.find((x) => x.category === t.cat);
            return (
              <Link key={t.cat} to={`/attack-lab?category=${t.cat}`} className="threat-card qv-tilt" style={{ ['--c' as string]: CAT_COLOR[t.cat as keyof typeof CAT_COLOR] }} data-reveal="">
                <span className="tc-icon"><t.icon /></span>
                <b>{t.name}</b><p>{t.line}</p>
                <div className="row wrap" style={{ gap: 4 }}>{t.layers.map((l) => <Chip key={l} mono>{l}</Chip>)}</div>
                <span className="tc-count">{pc?.runs ? `${pc.detected}/${pc.runs} detected live` : 'not run yet'} <ArrowRight /></span>
              </Link>
            );
          })}
        </div>
      </section>

      <section>
        <div className="section-title"><span className="kicker">Evidence</span><h2>From the analysis jobs</h2></div>
        <div className="grid g2">
          <Panel title="Detection matrix" kicker={matrix.data ? `run ${new Date((matrix.data.finished_at || 0) * 1000).toLocaleString()}` : 'not run yet'} tight>
            {matrix.data?.result?.attacks ? <MatrixMini r={matrix.data.result} /> : <EmptyJob kind="detection_matrix" />}
          </Panel>
          <Panel title="Forgery bound vs L" kicker={forgeryJob.data ? 'exact + Monte Carlo' : 'not run yet'} tight>
            {forgeryJob.data?.result ? <ForgeryMini r={forgeryJob.data.result} /> : <EmptyJob kind="forgery_analysis" />}
          </Panel>
        </div>
      </section>

      <footer className="ov-foot">
        <div><b>QVeris</b> · SIH 26141 · Quantum-inspired cyber threat detection for digital signature security (Egreen Quanta · Blockchain &amp; Cybersecurity)</div>
        <div className="muted small">Teleportation-based QDS · six-state one-time keys · CHSH certification · de-twirled tomography · exact binomial security bounds · hash-chained audit ledger. No AI/ML. No fabricated data: every number on this site is computed by the engine or read from rows it wrote.</div>
        <div className="row wrap"><Link to="/method">Method</Link><a href="/docs" target="_blank" rel="noreferrer">API docs</a><Link to="/analytics">Analytics</Link></div>
      </footer>
    </div>
  );
}

function EmptyJob({ kind }: { kind: string }) {
  const nav = useNavigate();
  return <div className="empty"><div className="orb" /><p>No evaluation run yet.</p><Button size="sm" icon={<LineIcon />} onClick={async () => { try { await ep.submitJob(kind, 'quick'); toast({ tone: 'info', title: 'Quick analysis queued' }); nav(`/analytics#${kind}`); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } }}>Run quick analysis</Button></div>;
}

function MatrixMini({ r }: { r: any }) {
  const attacks: any[] = r.attacks || [];
  const ints: number[] = r.intensities || [];
  return (
    <div className="stack" style={{ ['--gap' as string]: '8px' }}>
      <Heatmap label="detection rate by attack and intensity" rows={attacks.map((a) => a.name)} cols={ints.map((i) => `I=${i}`)}
        values={attacks.map((a) => ints.map((i) => a.points.find((p: any) => p.intensity === i)?.rate ?? null))} />
      <div className="row wrap" style={{ gap: 6 }}>
        <Chip tone="ok">{r.far.attack_runs - r.far.missed}/{r.far.attack_runs} attacks detected</Chip>
        <Chip tone="ok">classification {pct(r.far.classification_accuracy, 1)}</Chip>
        <Chip tone="info">FRR {r.legit.false_rejections}/{r.legit.runs}</Chip>
      </div>
    </div>
  );
}

function ForgeryMini({ r }: { r: any }) {
  const c = r.curves; const L: number[] = c?.L || [];
  if (!L.length) return <p className="muted small">Result has no curve.</p>;
  return <LineChart label="forgery probability per key vs L" height={230} xLog yLog xLabel="L (positions per key)" fx={(v) => compact(v)} series={[
    { id: 'e', label: 'external forger (exact)', color: 'var(--sky)', points: L.map((x, i) => ({ x, y: c.external.exact[i] })) },
    { id: 'i', label: 'insider p = 1/3 (exact)', color: 'var(--coral)', points: L.map((x, i) => ({ x, y: c.insider.exact[i] })) },
    { id: 'mc', label: 'Monte Carlo (external)', color: 'var(--lav)', dots: true, points: (r.mc || []).filter((m: any) => m.strategy === 'external' && m.rate > 0).map((m: any) => ({ x: m.L, y: m.rate, lo: Math.max(m.ci[0], 1e-6), hi: m.ci[1] })) }]} />;
}

export { sci, catLabel, ShieldCheck, Atom };
