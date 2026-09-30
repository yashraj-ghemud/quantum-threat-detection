import { useEffect, useMemo, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import { PenTool, Sparkles, Atom, ShieldCheck, Blocks } from 'lucide-react';
import type { SignatureReport } from '@/api/types';
import { ep, qk } from '@/api/endpoints';
import { ApiError, friendly } from '@/api/client';
import { useLive, useScene } from '@/state/live';
import { toast, useUi } from '@/state/ui';
import { Button, Chip, HashChip, KeyValue, NodeAvatar, Panel, Segmented, VerdictBadge, InfoButton, ErrorState } from '@/components/ui';
import { ScrambleText, useDebounced } from '@/components/motion';
import { usePlayback, Stepper, PlaybackBar, VerdictStamp, PacketFlight } from '@/components/theater';
import { FindingCard, SignatureReportView, DesignTable } from '@/components/reports';
import { BitGrid, QubitGrid, SprtChart } from '@/charts/charts';
import { LegacyScene } from '@/legacy/LegacyScene';
import { BreakIt } from '@/components/breakit';
import { verifyPayload } from '@/legacy/adapters';
import { bytes, fix, int, pct, sci, utf8len, compact } from '@/lib/format';

const EXAMPLES = ['Pay 250 QVC to Bob', 'Rotate HSM key #7', 'Grid dispatch 42 MW to substation 9', 'Release escrow for invoice 2026-118'];
const STAGES = ['Envelope → digest', 'One-time key bundle', 'Reveal keys', 'Transmit', 'First verifier', 'Forward (transfer)', 'Sentinel assessment', 'Anchor in ledger'];
const DUR = [1.2, 1.6, 1.8, 1.0, 3.4, 1.8, 2.2, 1.4];

export default function Studio() {
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const net = useQuery({ queryKey: qk.network, queryFn: () => ep.network() });
  const cfg = useQuery({ queryKey: qk.config, queryFn: ep.config, staleTime: 60_000 });
  const reservoir = useLive((s) => s.reservoir);
  const groups = (net.data?.groups || []).filter((g) => !g.hidden);
  const [group, setGroup] = useState(params.get('group') || 'g-alice');
  const [message, setMessage] = useState(EXAMPLES[0]);
  const [encoding, setEncoding] = useState<'sha256' | 'raw'>('sha256');
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<SignatureReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const size = utf8len(message);
  const rawOk = size <= 31;
  useEffect(() => { if (!rawOk && encoding === 'raw') setEncoding('sha256'); }, [rawOk, encoding]);

  const g = groups.find((x) => x.id === group);
  const preset = cfg.data?.active_preset || 'standard';
  const pinfo = cfg.data?.presets?.[preset];
  const groupLinks = (net.data?.links || []).filter((l) => l.kind === 'quantum' && g && l.a === g.signer_id && g.recipients.includes(l.b));
  const eBase = Math.max(0.001, ...groupLinks.map((l) => l.baseline?.qber ?? 0.01));
  const dq = useDebounced({ L: pinfo?.L ?? 4096, e: +(eBase * 1.25).toFixed(4), eps_rob: pinfo?.eps_rob_target, eps_forge: pinfo?.eps_forge_target, eps_rep: pinfo?.eps_rep_target }, 120);
  const design = useQuery({ queryKey: ['theory', 'design', dq], queryFn: () => ep.design(dq as any), enabled: !!pinfo, staleTime: 60_000 });
  const res = reservoir?.find((r) => r.group_id === group);

  const bundle = useQuery({ queryKey: ['bundle', report?.bundle_id], queryFn: () => ep.bundle(report!.bundle_id!), enabled: !!report?.bundle_id, staleTime: Infinity });
  const pb = usePlayback(DUR, report?.session_id ?? null);
  const [block, setBlock] = useState<{ height: number; hash: string } | null>(null);
  useEffect(() => { setBlock(null); }, [report?.session_id]);
  useEffect(() => useScene.subscribe((st) => {
    const e = st.events.at(-1);
    if (e?.kind === 'block' && report?.ledger?.tx_id && e.payload?.tx_ids?.includes(report.ledger.tx_id)) setBlock({ height: e.payload.height, hash: e.payload.hash });
  }), [report?.ledger?.tx_id]);

  const sign = async () => {
    setBusy(true); setError(null);
    try {
      const r = await ep.signAndVerify({ group_id: group, message, encoding });
      setReport(r);
      useUi.getState().say(`Signature ${r.verdict.toLowerCase()} by ${r.verifications.map((v) => v.verifier_id).join(' and ')}`);
      qc.invalidateQueries({ queryKey: qk.reservoir });
    } catch (e) {
      setError(e);
      if (!(e instanceof ApiError && e.code === 'BUNDLE_UNAVAILABLE')) toast({ tone: 'warn', title: friendly(e) });
    } finally { setBusy(false); }
  };
  const distributeNow = async () => {
    setBusy(true);
    try { const d = await ep.distribute(group); toast({ tone: d.verdict === 'CERTIFIED' ? 'ok' : 'threat', title: `Distribution ${d.verdict.toLowerCase()}`, body: `${compact(d.qubits_teleported)} qubits teleported` }); setError(null); }
    catch (e) { toast({ tone: 'warn', title: friendly(e) }); } finally { setBusy(false); }
  };

  const [verifierTab, setVerifierTab] = useState(0);
  const constellation = useMemo(() => (report ? verifyPayload(report, verifierTab) : undefined), [report, verifierTab]);

  return (
    <div className="stack">
      <header className="page-head">
        <div><span className="kicker">Sign · teleport · verify · transfer</span><h1>Signature Studio</h1>
          <p>Sign any message with a one-time quantum key bundle and watch every stage the engine actually runs, from the digest bits to the ledger block.</p></div>
      </header>
      <div className="studio-grid">
        <Panel title="Composer" kicker="Your message" className="composer">
          <div className="stack">
            <div className="field">
              <div className="row between"><label className="label" htmlFor="msg">Message</label><span className={`xs mono ${encoding === 'raw' && !rawOk ? 'threat-text' : 'muted'}`}>{size} B UTF-8</span></div>
              <textarea id="msg" className="textarea" value={message} maxLength={4096} onChange={(e) => setMessage(e.target.value)} />
              <div className="row wrap" style={{ gap: 6 }}>{EXAMPLES.map((x) => <button key={x} type="button" className="chip no-magnet" onClick={() => setMessage(x)}>{x}</button>)}</div>
            </div>
            <div className="field"><span className="label row">Encoding <InfoButton topic="lamport" /></span>
              <Segmented label="Encoding" value={encoding} onChange={setEncoding} options={[{ value: 'sha256', label: 'SHA-256 (any length)' }, { value: 'raw', label: 'Raw ≤ 31 B', disabled: !rawOk, title: rawOk ? 'Signs the bytes directly: fully information-theoretic' : 'Message too long for raw mode' }]} /></div>
            <div className="field"><span className="label">Signer group</span>
              <div className="stack" style={{ ['--gap' as string]: '8px' }}>
                {groups.map((x) => { const r = reservoir?.find((y) => y.group_id === x.id); return (
                  <button key={x.id} type="button" className={`group-card ${group === x.id ? 'on' : ''}`} onClick={() => setGroup(x.id)}>
                    <NodeAvatar id={x.signer_id} /><span className="grow"><b>{x.signer_id}</b> → {x.recipients.join(', ')}</span>
                    <Chip tone={r?.active ? 'ok' : 'warn'} mono>{r ? `${r.active}/${r.target} bundles` : '…'}</Chip>
                  </button>); })}
              </div>
            </div>
            <div className="field"><span className="label row">Design preview · preset {preset} <InfoButton topic="thresholds" /></span>
              {design.data ? <KeyValue rows={[['L per key', int(design.data.L)], ['s_a / s_v', `${pct(design.data.s_a, 2)} / ${pct(design.data.s_v, 2)}`],
                ['ε_rob · ε_forge · ε_rep', `${sci(design.data.eps_rob_msg)} · ${sci(design.data.eps_forge_key)} · ${sci(design.data.eps_rep_msg)}`], ['qubits per bundle', compact(pinfo?.qubits as number)]]} /> : <div className="skeleton" style={{ height: 90 }} />}
              <span className="xs faint">from /theory/design at the links’ baseline QBER ({pct(eBase, 2)}) with a 25 % margin</span>
            </div>
            <Button variant="primary" size="lg" loading={busy} icon={<PenTool />} onClick={sign} disabled={!message.trim()}>Sign &amp; verify</Button>
            {res?.blocked_reason && <div className="banner warn">{res.blocked_reason}</div>}
          </div>
        </Panel>

        <div className="stack theater">
          {error instanceof ApiError && error.code === 'BUNDLE_UNAVAILABLE' ? (
            <Panel title="Reservoir empty" kicker="No certified bundle for this group">
              <p className="muted">Distributing a bundle teleports millions of key qubits and certifies both links. It takes about a second.</p>
              <Button variant="primary" icon={<Atom />} loading={busy} onClick={distributeNow}>Distribute now</Button>
            </Panel>
          ) : error ? <ErrorState error={error} retry={sign} /> : null}
          {!report && !error && (
            <Panel className="theater-empty">
              <div className="empty"><div className="orb" /><h4>Nothing signed yet</h4><p>Write a message and press <b>Sign &amp; verify</b>. The theater replays the real report: digest bits, the bundle’s certification, the keys revealed, both verifications, the SPRT and the detector cascade.</p></div>
            </Panel>
          )}
          {report && (
            <Panel className="theater-panel" reveal={false}>
              <div className="stack">
                <Stepper steps={STAGES} pb={pb} />
                <AnimatePresence mode="wait">
                  <motion.div key={pb.done ? 'done' : pb.stage} className="stage-box" initial={{ opacity: 0, y: 10, filter: 'blur(6px)' }} animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.3 }}>
                    <Stage i={pb.done ? 7 : pb.stage} k={pb.done ? 1 : pb.local} r={report} bundle={bundle.data} block={block} done={pb.done} />
                  </motion.div>
                </AnimatePresence>
                <PlaybackBar pb={pb} />
              </div>
            </Panel>
          )}
        </div>
      </div>

      {report && pb.done && (
        <>
          <div className="section-title"><span className="kicker">3D · real sampled qubits</span><h2>Signature constellation</h2></div>
          <Panel flush reveal={false} className="scene-panel">
            <div className="scene-overlay tr"><Segmented label="Verifier" value={verifierTab} onChange={setVerifierTab} options={report.verifications.map((v, i) => ({ value: i, label: v.verifier_id }))} /></div>
            <LegacyScene scene="verify" channel="studio-verify" title="SIGNATURE CONSTELLATION" payload={constellation} label="Signature constellation: sampled qubits of the verification" style={{ height: 480 }} />
          </Panel>
          <BreakIt report={report} />
          <div className="section-title"><span className="kicker">Full report</span><h2>What the engine recorded</h2><Link to={`/sessions/${report.session_id}`} className="small">permalink →</Link></div>
          <SignatureReportView r={report} />
        </>
      )}
    </div>
  );
}

function Stage({ i, k, r, bundle, block, done }: { i: number; k: number; r: SignatureReport; bundle: any; block: { height: number; hash: string } | null; done: boolean }) {
  const bits = r.digest?.bits || '';
  const v1 = r.verifications[0], v2 = r.verifications[1];
  const nBits = Math.round(k * bits.length);
  switch (i) {
    case 0: return (
      <>
        <h3>Envelope → SHA-256 digest</h3>
        <div className="env-chips">{[['signer', r.envelope.signer_id], ['recipients', r.envelope.recipients.join(', ')], ['seq', r.envelope.seq], ['timestamp', new Date(r.envelope.timestamp * 1000).toLocaleTimeString()], ['nonce', r.envelope.nonce.slice(0, 10) + '…'], ['message', r.envelope.message.slice(0, 40)]].map(([a, b], j) =>
          <motion.span key={a as string} className="chip mono" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: j * 0.08 }}>{a}: {String(b)}</motion.span>)}</div>
        <div className="digest-hex"><ScrambleText text={r.digest.hex} duration={900} /></div>
        <BitGrid cells={bits.split('').map((b, j) => ({ state: j < nBits ? (b === '1' ? 'one' : 'zero') : 'pending', title: `bit ${j} = ${b}` }))} cols={32} size={11} label="digest bits" reveal={false} />
        <p className="small muted">Each of the {bits.length} digest bits picks which of two one-time keys gets revealed.</p>
      </>);
    case 1: return (
      <>
        <h3>One-time key bundle</h3>
        <div className="bundle-card">
          <div className="row between wrap"><b className="row" style={{ gap: 8 }}><ShieldCheck style={{ color: 'var(--ok)' }} />Bundle <HashChip hash={r.bundle_id} /></b><VerdictBadge verdict="CERTIFIED" /></div>
          {bundle ? <KeyValue rows={[['preset', `${bundle.preset} · L = ${int(bundle.params?.L)}`], ['qubits teleported', compact(bundle.params?.qubits)], ['Bell pairs sacrificed', compact(bundle.params?.bell_pairs)],
            ...((bundle.summary?.links || []) as any[]).map((l) => [`${l.link_id}`, `S = ${fix(l.S, 3)} · QBER ${pct(l.qber, 2)} · frame errors ${l.frame_mismatch}`] as [string, string])]} /> : <div className="skeleton" style={{ height: 100 }} />}
        </div>
        <p className="small muted">This bundle was distributed and certified before signing: both links beat the CHSH bound and matched their baselines. It can sign exactly once.</p>
      </>);
    case 2: return (
      <>
        <h3>Reveal keys · 256 of 512</h3>
        <div className="keypair-grid" aria-label="Lamport key pairs">{bits.split('').map((b, j) => { const on = j < k * bits.length; return (
          <span key={j} title={`bit ${j} = ${b}: reveal key ${b}`}><i className={on ? (b === '0' ? 'chosen' : 'burnt') : ''} /><i className={on ? (b === '1' ? 'chosen' : 'burnt') : ''} /></span>); })}</div>
        <p className="small muted">For each bit the signer reveals the labels of the chosen key ({int(bundle?.params?.L)} six-state labels each) and destroys its twin. Signature size {bytes(r.signature.size_bytes)} · sha256 <HashChip hash={r.signature.sha256} /></p>
      </>);
    case 3: return (
      <>
        <h3>Transmit to {v1.verifier_id}</h3>
        <PacketFlight from={r.envelope.signer_id} to={v1.verifier_id} progress={k} label={bytes(r.signature.size_bytes)} />
        <p className="small muted">Classical transmission: the security comes from the quantum records the verifiers already hold, not from this channel.</p>
      </>);
    case 4: case 5: {
      const v = i === 4 ? v1 : v2;
      if (!v) return <p className="muted">No transfer verification in this run.</p>;
      const cut = Math.round(k * v.keys.pass.length);
      return (
        <>
          <div className="row between wrap"><h3>{i === 4 ? 'First verifier' : 'Transfer'} · {v.verifier_id} <span className="muted small">threshold s = {pct(v.threshold, 2)}</span></h3>{k > 0.95 && <VerdictBadge verdict={v.decision === 'ACCEPT' ? 'ACCEPTED' : 'REJECTED'} />}</div>
          {i === 5 && <PacketFlight from={v1.verifier_id} to={v.verifier_id} progress={Math.min(1, k * 3)} label="forward" />}
          <div className="grid g2">
            <div><div className="label" style={{ marginBottom: 6 }}>keys ({cut}/{v.keys.pass.length} checked)</div>
              <BitGrid cells={v.keys.pass.map((p, j) => ({ state: j < cut ? (p ? 'pass' : 'fail') : 'pending', title: `key ${j}: ${v.keys.m_own[j] + v.keys.m_recv[j]}/${v.keys.n_own[j] + v.keys.n_recv[j]} mismatches` }))} cols={32} size={9} label="key results" reveal={false} /></div>
            {i === 4 && v.grid_sample && <div><div className="label" style={{ marginBottom: 6 }}>sampled records (scan)</div><QubitGrid cells={v.grid_sample.cells} label="sampled records" /></div>}
          </div>
          {i === 4 && v.sprt?.traces?.length > 0 && <SprtChart traces={v.sprt.traces} A={v.sprt.A} B={v.sprt.B} height={170} progress={k} />}
          <p className="small muted">{int(v.totals.mismatches)} mismatches in {int(v.totals.tested)} tested positions = {pct(v.totals.rate, 3)} (the forger’s floor is 33 %).</p>
        </>);
    }
    case 6: {
      const f = r.assessment.findings;
      const shown = Math.ceil(k * Math.min(8, f.length));
      const list = [...f].sort((a, b) => Number(b.fired) - Number(a.fired)).slice(0, shown);
      return (
        <div className="grid g2" style={{ alignItems: 'start' }}>
          <div className="stack" style={{ ['--gap' as string]: '6px' }}>{list.map((x, j) => <FindingCard key={x.id + j} f={x} i={j} />)}</div>
          <div className="stack" style={{ alignItems: 'center', justifyContent: 'center', minHeight: 240 }}>
            <VerdictStamp verdict={r.verdict} sub={r.assessment.classification.category === 'NONE' ? 'both recipients agree' : r.assessment.classification.category.replace(/_/g, ' ')} show={k > 0.55} />
            {k > 0.6 && <p className="small muted" style={{ textAlign: 'center', maxWidth: 320 }}>{r.assessment.classification.explanation}</p>}
          </div>
        </div>);
    }
    default: return (
      <>
        <div className="row between wrap"><h3 className="row" style={{ gap: 8 }}><Blocks />Anchor in the audit ledger</h3><VerdictBadge verdict={r.verdict} /></div>
        <div className="bundle-card" style={{ background: 'linear-gradient(135deg, var(--gold-l), var(--bg-2))' }}>
          <KeyValue rows={[['ledger tx', <HashChip key="t" hash={r.ledger?.tx_id} />], ['block', block ? <span key="b">#{block.height} <HashChip hash={block.hash} /></span> : <span key="b" className="muted">pending · sealed within a few seconds</span>]]} />
        </div>
        {done && <div className="row wrap"><Link className="btn" to="/ledger"><Blocks />Open ledger</Link><Link className="btn ghost" to={`/sessions/${r.session_id}`}><Sparkles />Full report</Link></div>}
      </>);
  }
}

export { DesignTable };
