import { useEffect, useMemo, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'motion/react';
import { Search, Zap, ShieldAlert, ShieldCheck, Eye, History, CircleCheck, CircleX, ArrowRight } from 'lucide-react';
import type { AttackRunReport, CatalogEntry, ChannelSpec, DistributionReport, SignatureReport } from '@/api/types';
import { ep, qk } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { toast, useUi } from '@/state/ui';
import { Button, Chip, Panel, Segmented, Slider, Toggle, InfoButton, ErrorState, Tabs } from '@/components/ui';
import { HoldButton } from '@/components/theater';
import { ClassificationCard, FindingsList, LinkEvidenceView, VerificationView, DesignTable } from '@/components/reports';
import { LegacyScene } from '@/legacy/LegacyScene';
import { labConfig, labResult } from '@/legacy/adapters';
import { SceneCanvas } from '@/three/common';
import { BlochScene, BlochSvg, type MapSpec } from '@/three/BlochScene';
import { ChshGauge, BarChart } from '@/charts/charts';
import { useDebounced } from '@/components/motion';
import { catLabel, fix, pct } from '@/lib/format';
import { CAT_COLOR } from '@/lib/color';

const CATS = ['ALL', 'FORGERY', 'IMPERSONATION', 'REPLAY', 'UNAUTHORIZED_VERIFICATION', 'CHANNEL_MANIPULATION', 'REPUDIATION'] as const;
const CAT_SHORT: Record<string, string> = { ALL: 'All', FORGERY: 'Forgery', IMPERSONATION: 'Impersonation', REPLAY: 'Replay', UNAUTHORIZED_VERIFICATION: 'Unauthorized', CHANNEL_MANIPULATION: 'Channel', REPUDIATION: 'Repudiation' };
const ACTION_LABEL: Record<string, string> = { quarantine_link: 'Quarantine link', release_link: 'Release link', recertify_link: 'Re-certify link', revoke_link_bundles: 'Revoke link bundles', enable_mac: 'Enable MAC on classical bits',
  suspend_signer: 'Suspend signer', reinstate_signer: 'Reinstate signer', flag_principal: 'Flag principal', notify_recipients: 'Notify recipients', escalate_dispute: 'Escalate dispute', review_capture_source: 'Review capture source', deny_principal: 'Deny principal', use_larger_L: 'Use a larger L' };

/** The attack as a channel (for the exact-algebra preview), when it is one. */
function attackChannel(a: CatalogEntry, I: number, params: Record<string, any>): ChannelSpec | null {
  const v = (a.intensity?.scale ?? 1) * I;
  switch (a.id) {
    case 'channel.depolarize': return { type: 'depolarizing', p: v };
    case 'channel.dephase': return { type: 'dephasing', p: v, axis: params.axis || 'z' };
    case 'channel.amplitude_damp': return { type: 'amplitude_damping', gamma: v };
    case 'channel.coherent_rotation': { const ax = params.axis || 'z'; return { type: 'rotation', axis: ax === 'x' ? [1, 0, 0] : ax === 'y' ? [0, 1, 0] : [0, 0, 1], theta: v }; }
    default: return null;
  }
}

export default function AttackLab() {
  const [sp, setSp] = useSearchParams();
  const qc = useQueryClient();
  const cat = useQuery({ queryKey: qk.catalog, queryFn: ep.catalog, staleTime: Infinity });
  const net = useQuery({ queryKey: qk.network, queryFn: () => ep.network() });
  const [filter, setFilter] = useState<(typeof CATS)[number]>((sp.get('category') as any) || 'ALL');
  const [q, setQ] = useState('');
  const [attackId, setAttackId] = useState(sp.get('attack') || 'channel.dephase');
  const [intensity, setIntensity] = useState(Number(sp.get('intensity') || 0.5));
  const [params, setParams] = useState<Record<string, any>>({});
  const [target, setTarget] = useState<string>(sp.get('target') || 'first');
  const [group, setGroup] = useState('g-alice');
  const [message, setMessage] = useState('Transfer 1,000 QVC to Bob');
  const [counterfactual, setCounterfactual] = useState(true);
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState<AttackRunReport | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [history, setHistory] = useState<AttackRunReport[]>([]);
  const [lab, setLab] = useState<{ config: any; result: any } | null>(null);
  const entry = cat.data?.find((a) => a.id === attackId) || null;

  useEffect(() => { if (entry) { const d: Record<string, any> = {}; entry.params.forEach((p) => { if (p.name !== 'target' && p.default !== undefined) d[p.name] = p.default; }); setParams(d); } }, [entry?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setSp((s) => { s.set('attack', attackId); s.set('intensity', intensity.toFixed(2)); return s; }, { replace: true }); }, [attackId, intensity]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = useMemo(() => (cat.data || []).filter((a) => (filter === 'ALL' || a.category === filter) && (!q || `${a.name} ${a.summary} ${a.id}`.toLowerCase().includes(q.toLowerCase()))), [cat.data, filter, q]);
  const hasTarget = !!entry?.params.find((p) => p.name === 'target');
  const groupObj = net.data?.groups.find((g) => g.id === group);
  const targetRecipient = groupObj ? (target === 'second' ? groupObj.recipients[1] : groupObj.recipients[0]) : 'bob';
  const targetLink = net.data?.links.find((l) => l.kind === 'quantum' && groupObj && l.a === groupObj.signer_id && l.b === targetRecipient);

  // Exact-algebra preview of channel attacks.
  const ch = entry ? attackChannel(entry, intensity, params) : null;
  const previewKey = useDebounced(JSON.stringify({ base: targetLink?.baseline_channel, ch }), 150);
  const preview = useQuery({ queryKey: ['theory', 'link', previewKey], enabled: !!ch && !!targetLink, staleTime: 60_000,
    queryFn: async () => { const base = targetLink?.baseline_channel || []; const [b, a] = await Promise.all([ep.theoryLink(base), ep.theoryLink([...base, ch!])]); return { base: b, attacked: a }; } });

  // The configured attack in the original film (theory) and, after a run, the measured film.
  const cfgPayload = useMemo(() => {
    const theoryCfg = { ...labConfig(entry, intensity, message), n: 24 };
    // While the controls still match the measured run, show that run's config (the film plays it).
    const same = lab && entry && lab.result.config.name === theoryCfg.name && Math.abs(lab.result.config.intensity - intensity) < 1e-9 && lab.result.config.message === message;
    return { config: same ? lab!.result.config : theoryCfg, result: lab?.result ?? null };
  }, [entry, intensity, message, lab]);
  const launch = async () => {
    if (!entry) return;
    setRunning(true); setErr(null);
    try {
      const p: Record<string, any> = { ...params };
      const r = await ep.runAttack({ attack: { attack_id: entry.id, intensity, params: p, target: hasTarget ? target : 'first' }, group_id: group, message, counterfactual });
      setRun(r); setHistory((h) => [r, ...h].slice(0, 12));
      setLab(await labResult(r, entry, message));
      useUi.getState().say(`${entry.name}: ${r.detected ? 'detected' : 'not detected'}, verdict ${r.verdict}`);
      qc.invalidateQueries({ queryKey: qk.attackRuns });
    } catch (e) { setErr(e); toast({ tone: 'warn', title: friendly(e) }); } finally { setRunning(false); }
  };
  const selectRun = async (r: AttackRunReport) => { setRun(r); setAttackId(r.attack.attack_id); setIntensity(r.attack.intensity); setLab(await labResult(r, cat.data?.find((a) => a.id === r.attack.attack_id) || null, message)); };

  return (
    <div className="stack">
      <header className="page-head">
        <div><span className="kicker">17 attacks · real physics · real detectors</span><h1 className={running ? 'glitch' : ''} data-text="Attack Lab">Attack Lab</h1>
          <p>Choose an adversary, set its strength, and launch it against the live engine. The film replays the measured run; the panels show the evidence each detector saw and what would have happened without the defence.</p></div>
      </header>

      <div className="lab-grid">
        <div className="lab-left stack">
        <Panel className="lab-catalog" title="Catalog" kicker="Choose an attack" tight>
          <div className="stack" style={{ ['--gap' as string]: '10px' }}>
            <div className="row wrap" style={{ gap: 4 }}>{CATS.map((c) => <button key={c} className="chip no-magnet" aria-pressed={filter === c} onClick={() => setFilter(c)}>{CAT_SHORT[c]}</button>)}</div>
            <label className="search-box"><Search aria-hidden /><input className="input" placeholder="Search attacks" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search attacks" /></label>
            <div className="atk-list" role="listbox" aria-label="Attacks">
              {cat.isLoading && <div className="skeleton" style={{ height: 300 }} />}
              {list.map((a) => (
                <button key={a.id} role="option" aria-selected={a.id === attackId} className={`atk-item ${a.id === attackId ? 'on' : ''}`} onClick={() => setAttackId(a.id)} style={{ ['--c' as string]: CAT_COLOR[a.category] }}>
                  <span className="atk-dot" /><span className="grow"><b>{a.name}</b><span className="xs muted">{a.summary}</span></span>
                  <Chip tone={a.phase === 'distribution' ? 'info' : 'gold'} mono>{a.phase === 'distribution' ? 'dist' : 'sign'}</Chip>
                </button>
              ))}
            </div>
          </div>
        </Panel>

        <Panel className="lab-config" title={entry?.name || 'Configure'} kicker={entry ? `${catLabel(entry.category)} · ${entry.subtype.replace(/_/g, ' ')}` : 'Configure'} tight>
          {entry ? (
            <div className="stack" style={{ ['--gap' as string]: '14px' }}>
              <p className="small" style={{ margin: 0 }}>{entry.summary}</p>
              <details className="physics"><summary className="label">Physics</summary><p className="small muted">{entry.physics}</p></details>
              <div><span className="label">Adversary knowledge</span><ul className="small muted" style={{ margin: '6px 0 0', paddingLeft: 18 }}>{entry.knowledge.map((k) => <li key={k}>{k}</li>)}</ul></div>
              {entry.intensity && <Slider label="Intensity I" tone="threat" value={intensity} min={0.05} max={1} step={0.05} onChange={setIntensity}
                format={(v) => `I = ${v.toFixed(2)}${entry.intensity?.scale ? ` → ${entry.intensity.param} = ${(v * entry.intensity.scale).toFixed(3)}` : ''}`} hint={entry.intensity.formula} />}
              {hasTarget && <div className="field"><span className="label">Target link</span><Segmented label="Target" value={target} onChange={setTarget} options={[{ value: 'first', label: 'first recipient' }, { value: 'second', label: 'second' }, { value: 'both', label: 'both' }]} /></div>}
              {entry.params.filter((p) => p.name !== 'target').map((p) => (
                <div key={p.name} className="field">
                  {p.type === 'enum' && p.options ? (<><span className="label">{p.name.replace(/_/g, ' ')}</span>
                    <Segmented label={p.name} value={params[p.name] ?? p.default} onChange={(v) => setParams({ ...params, [p.name]: v })} options={p.options.map((o) => ({ value: o as any, label: String(o).replace(/_/g, ' ') }))} /></>)
                    : <Slider label={p.name.replace(/_/g, ' ')} value={Number(params[p.name] ?? p.default ?? 1)} min={p.name === 'delay_s' ? 0 : 1} max={p.name === 'delay_s' ? 900 : 32} step={1}
                      onChange={(v) => setParams({ ...params, [p.name]: v })} format={(v) => (p.name === 'delay_s' ? `${v} s` : String(v))} />}
                  {p.description && <span className="xs faint">{p.description}</span>}
                </div>
              ))}
              <div className="field"><span className="label">Group</span><Segmented label="Group" value={group} onChange={setGroup} options={(net.data?.groups || []).filter((g) => !g.hidden).map((g) => ({ value: g.id, label: `${g.signer_id} → ${g.recipients.join(', ')}` }))} /></div>
              {entry.phase === 'signing' && <div className="field"><label className="label" htmlFor="amsg">Message</label><input id="amsg" className="input" value={message} onChange={(e) => setMessage(e.target.value)} /></div>}
              <Toggle checked={counterfactual} onChange={setCounterfactual} label="Also run the counterfactual (defence off)" />
              {ch && preview.data && (
                <div className="predict">
                  <div className="label row">Predicted effect on {targetLink?.id} <InfoButton topic="chsh" /></div>
                  <div className="grid g3" style={{ ['--gap' as string]: '8px' }}>
                    <div><span className="xs muted">CHSH S</span><b className="num">{fix(preview.data.base.S, 3)} → <span className={preview.data.attacked.S <= 2 ? 'threat-text' : ''}>{fix(preview.data.attacked.S, 3)}</span></b></div>
                    <div><span className="xs muted">Fidelity F</span><b className="num">{fix(preview.data.base.F, 3)} → {fix(preview.data.attacked.F, 3)}</b></div>
                    <div><span className="xs muted">QBER</span><b className="num">{pct(preview.data.base.qber, 2)} → {pct(preview.data.attacked.qber, 2)}</b></div>
                  </div>
                  <span className="xs faint">Prediction from exact channel algebra; the run will sample it.</span>
                </div>
              )}
              {entry.id === 'channel.intercept_resend' && <div className="predict xs"><b>Prediction:</b> intercept-resend on a fraction f = {intensity.toFixed(2)} raises QBER by ≈ f/3 = {pct(intensity / 3, 1)} and destroys entanglement in proportion; the run samples it.</div>}
              {entry.honesty && <div className="banner info xs">{entry.honesty}</div>}
              <HoldButton onConfirm={launch} loading={running} disabled={running}><Zap />Hold to launch</HoldButton>
            </div>
          ) : <div className="skeleton" style={{ height: 400 }} />}
        </Panel>
        </div>

        <div className="lab-theater stack">
          <Panel flush reveal={false} className={`scene-panel ${running ? 'attacking' : ''}`}>
            <LegacyScene scene="attack_lab" channel="lab-v2" title="ATTACK LAB" payload={cfgPayload} label="Attack film: the configured attack, then the measured run" style={{ height: 600 }} />
          </Panel>
          {err ? <ErrorState error={err} retry={launch} /> : null}
          {run && <RunVerdict run={run} />}
        </div>
      </div>

      {run && <RunDetail run={run} />}

      {history.length > 0 && (
        <Panel title="This session’s runs" kicker="Click to replay" tight>
          <div className="run-strip">{history.map((r, i) => (
            <button key={(r.id as string) || i} className={`run-chip ${run === r ? 'on' : ''}`} onClick={() => selectRun(r)}>
              {r.detected ? <ShieldCheck style={{ color: 'var(--ok)' }} /> : <ShieldAlert style={{ color: 'var(--threat)' }} />}
              <span><b>{r.catalog_entry?.name || r.attack.attack_id}</b><span className="xs muted">I = {r.attack.intensity.toFixed(2)} · {r.verdict}</span></span>
            </button>))}</div>
        </Panel>
      )}
    </div>
  );
}

function RunVerdict({ run }: { run: AttackRunReport }) {
  return (
    <motion.div className={`panel tight run-verdict ${run.detected ? 'accent-ok' : 'accent-threat'}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <div className="row wrap" style={{ gap: 10 }}>
        <Chip tone={run.detected ? 'ok' : 'threat'}>{run.detected ? <CircleCheck /> : <CircleX />}{run.detected ? 'Detected' : 'Not detected'}</Chip>
        <Chip tone={run.correctly_classified ? 'ok' : 'warn'}>{run.correctly_classified ? <CircleCheck /> : <CircleX />}{run.correctly_classified ? 'Correctly classified' : `Classified as ${catLabel(run.detected_category)}`}</Chip>
        <Chip mono>ground truth: {catLabel(run.expected_category)}</Chip>
        <Chip mono>engine: {catLabel(run.detected_category)}{run.detected_subtype ? ` · ${run.detected_subtype.replace(/_/g, ' ')}` : ''}</Chip>
        {run.incident_id && <Link className="btn sm" to={`/incidents/${run.incident_id}`}>Incident <ArrowRight /></Link>}
      </div>
      {run.notes?.length > 0 && <p className="xs muted" style={{ margin: '8px 0 0' }}>{run.notes.join(' · ')}</p>}
    </motion.div>
  );
}

function RunDetail({ run }: { run: AttackRunReport }) {
  const dist = run.distribution as DistributionReport | null;
  const sig = run.signature as SignatureReport | null;
  const main = run.phase === 'distribution' ? dist : sig;
  const [linkIdx, setLinkIdx] = useState(0);
  const [tab, setTab] = useState<'instruments' | 'evidence' | 'bounds'>('instruments');
  const qc = useQueryClient();
  const actions = main?.assessment?.recommended_actions || [];
  const respond = async (a: string) => {
    if (!run.incident_id) return;
    try { const r = await ep.respond(run.incident_id, a); toast({ tone: 'ok', title: `${ACTION_LABEL[a] || a} executed`, body: typeof r.result?.note === 'string' ? r.result.note : undefined }); qc.invalidateQueries({ queryKey: qk.network }); }
    catch (e) { toast({ tone: 'warn', title: friendly(e) }); }
  };
  const ev = dist?.links?.[linkIdx];
  const maps: MapSpec[] = ev ? [
    { M: ev.baseline.M, c: ev.baseline.c, color: '#4FC3A1', wire: true, opacity: 0.55 },
    { M: ev.tomography.detwirled.M, c: ev.tomography.detwirled.c, color: '#E8697A', opacity: 0.4 },
  ] : [];
  return (
    <div className="lab-detail">
      <div className="stack">
        {main && <ClassificationCard report={main} />}
        <Tabs label="Run details" value={tab} onChange={setTab} items={[{ value: 'instruments', label: 'Instruments' }, { value: 'evidence', label: 'Evidence cascade' }, { value: 'bounds', label: 'ε bounds' }]} />
        {tab === 'instruments' && run.phase === 'distribution' && dist && (
          <div className="stack">
            <div className="row wrap"><Segmented label="Link" value={linkIdx} onChange={setLinkIdx} options={dist.links.map((l, i) => ({ value: i, label: l.link_id }))} /></div>
            <div className="grid g2" style={{ alignItems: 'start' }}>
              <Panel title="De-twirled channel" kicker="Baseline (mint wire) vs measured (coral)" explainTopic="detwirl" tight reveal={false}>
                <SceneCanvas label="Bloch sphere: baseline vs measured channel" camera={{ position: [2.4, 1.6, 2.6], fov: 45 }} fallback={<BlochSvg maps={maps} />} style={{ height: 320 }}>
                  <BlochScene maps={maps} autoRotate />
                </SceneCanvas>
              </Panel>
              {ev && <Panel tight reveal={false}><LinkEvidenceView ev={ev} /></Panel>}
            </div>
          </div>
        )}
        {tab === 'instruments' && run.phase !== 'distribution' && sig && (
          <div className="grid g2" style={{ alignItems: 'start' }}>
            {sig.verifications.map((v) => <Panel key={v.verifier_id + v.role} tight reveal={false}><VerificationView v={v} /></Panel>)}
            {!sig.verifications.length && <p className="muted">The signature never reached a verifier.</p>}
          </div>
        )}
        {tab === 'evidence' && main && <FindingsList findings={main.assessment.findings} />}
        {tab === 'bounds' && <DesignTable d={(main as any)?.design ?? null} />}
      </div>
      <div className="stack">
        {run.counterfactual && <Counterfactual run={run} />}
        {actions.length > 0 && (
          <Panel title="Recommended response" kicker={run.incident_id ? 'Executes against the live network' : 'No incident opened'} tight reveal={false}>
            <div className="stack" style={{ ['--gap' as string]: '6px' }}>{actions.map((a) => <Button key={a} size="sm" disabled={!run.incident_id} onClick={() => respond(a)}>{ACTION_LABEL[a] || a}</Button>)}</div>
          </Panel>
        )}
        {dist && run.phase === 'distribution' && (
          <Panel title="Bell certificates" tight reveal={false}>
            <div className="row wrap" style={{ justifyContent: 'space-around' }}>{dist.links.map((l) => <div key={l.link_id} style={{ textAlign: 'center' }}><ChshGauge S={l.bell.S} S_lcb={l.bell.S_lcb} S0={l.baseline?.S} size={150} /><div className="xs mono">{l.link_id}</div></div>)}</div>
            <BarChart height={160} label="QBER per link" fy={(v) => `${(v * 100).toFixed(1)}%`} data={dist.links.map((l) => ({ label: l.link_id, values: [{ key: 'baseline', value: l.baseline.qber, color: 'var(--mint)' }, { key: 'measured', value: l.pe.qber, color: 'var(--coral)' }] }))} />
          </Panel>
        )}
      </div>
    </div>
  );
}

function Counterfactual({ run }: { run: AttackRunReport }) {
  const cf = run.counterfactual as any;
  const breach = !!cf?.breach;
  return (
    <Panel title="Counterfactual" kicker="Same attack, one defence switched off" tight reveal={false} className={breach ? 'accent-threat' : ''}>
      <div className="cf-split">
        <div className="cf-side ok"><ShieldCheck /><b>With QSentinel</b><span className="xs">{run.detected ? `attack ${run.phase === 'distribution' ? 'refused at distribution' : 'rejected'}` : 'not detected'} · {run.verdict}</span></div>
        <div className="cf-line"><motion.i initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8 }} className={breach ? 'breach' : ''} /></div>
        <div className={`cf-side ${breach ? 'bad' : 'ok'}`}><Eye /><b>Without the defence</b><span className="xs">{breach ? 'the attack would succeed' : 'still stopped'}</span></div>
      </div>
      <p className="small" style={{ margin: '10px 0 0' }}>{cf.outcome_sentence || cf.outcome || ''}</p>
      {cf.description && <p className="xs muted" style={{ margin: '6px 0 0' }}>{cf.description}</p>}
    </Panel>
  );
}

export { History };
