import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import { Search, CheckCheck, Eye, ArrowLeft, Blocks } from 'lucide-react';
import type { Incident } from '@/api/types';
import { ep, qk } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { toast } from '@/state/ui';
import { Button, Chip, Empty, HashChip, KeyValue, Panel, SeverityPill, VerdictBadge, Skeleton, ErrorState } from '@/components/ui';
import { FindingsList } from '@/components/reports';
import { Confirm } from '@/components/overlays';
import { LineChart } from '@/charts/charts';
import { useNow } from '@/components/motion';
import { ago, catLabel, clock, fix, pct } from '@/lib/format';
import { sevColor } from '@/lib/color';

const ACTION_LABEL: Record<string, string> = { quarantine_link: 'Quarantine link', release_link: 'Release link', recertify_link: 'Re-certify link', revoke_link_bundles: 'Revoke link bundles', enable_mac: 'Enable MAC on classical bits',
  suspend_signer: 'Suspend signer', reinstate_signer: 'Reinstate signer', flag_principal: 'Flag principal', notify_recipients: 'Notify recipients', escalate_dispute: 'Escalate dispute', review_capture_source: 'Review capture source', deny_principal: 'Deny principal', use_larger_L: 'Use a larger L' };

export default function Incidents() {
  const { id } = useParams();
  const nav = useNavigate();
  const [status, setStatus] = useState<'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED' | 'ALL'>('OPEN');
  const [sev, setSev] = useState<string>('ALL');
  const [q, setQ] = useState('');
  const list = useQuery({ queryKey: qk.incidents({ status, all: true }), queryFn: () => ep.incidents({ status: status === 'ALL' ? undefined : status, limit: 300 }), refetchInterval: 15_000 });
  const now = useNow(5000);
  const rows = useMemo(() => (list.data || []).filter((i) => (sev === 'ALL' || i.severity === sev) && (!q || `${i.title} ${i.link_id} ${i.group_id} ${i.category}`.toLowerCase().includes(q.toLowerCase()))), [list.data, sev, q]);
  const active = id || rows[0]?.id;
  return (
    <div className="stack">
      <header className="page-head"><div><span className="kicker">Detections that need a decision</span><h1>Incidents</h1>
        <p>Each incident is opened by the detector cascade with its evidence, classification and recommended response. Responses act on the live network and are anchored in the ledger.</p></div></header>
      <div className={`inc-grid ${id ? 'has-detail' : ''}`}>
        <Panel tight reveal={false} className="inc-list">
          <div className="stack" style={{ ['--gap' as string]: '10px' }}>
            <div className="row wrap" style={{ gap: 4 }}>{(['OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'ALL'] as const).map((s) => <button key={s} className="chip no-magnet" aria-pressed={status === s} onClick={() => setStatus(s)}>{s.toLowerCase()}</button>)}</div>
            <div className="row wrap" style={{ gap: 4 }}>{['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((s) => <button key={s} className="chip no-magnet" aria-pressed={sev === s} onClick={() => setSev(s)} style={s !== 'ALL' ? { color: sevColor(s) } : undefined}>{s.toLowerCase()}</button>)}</div>
            <label className="search-box"><Search aria-hidden /><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, link, group" aria-label="Search incidents" /></label>
            {list.isLoading && <Skeleton h={300} />}
            {list.error && <ErrorState error={list.error} retry={() => list.refetch()} />}
            {!list.isLoading && !rows.length && <Empty title={status === 'OPEN' ? 'No open incidents' : 'No incidents'} body="Launch an attack in the Attack Lab or start a campaign: detections open incidents here." />}
            <div className="inc-items"><AnimatePresence initial={false}>
              {rows.map((i) => (
                <motion.button layout key={i.id} className={`inc-card ${active === i.id ? 'on' : ''}`} style={{ ['--c' as string]: sevColor(i.severity) }} onClick={() => nav(`/incidents/${i.id}`)}
                  initial={{ opacity: 0, x: -12, backgroundColor: 'var(--coral-l)' }} animate={{ opacity: 1, x: 0, backgroundColor: 'var(--bg-2)' }} transition={{ duration: 0.6 }}>
                  <span className="inc-stripe" />
                  <span className="grow" style={{ minWidth: 0 }}><b>{i.title}</b><span className="xs muted">{catLabel(i.category)}{i.subtype ? ` · ${i.subtype.replace(/_/g, ' ')}` : ''}{i.occurrences > 1 ? ` · ×${i.occurrences}` : ''}</span></span>
                  <span className="stack" style={{ ['--gap' as string]: '4px', alignItems: 'flex-end' }}><SeverityPill level={i.severity} compact /><span className="xs faint">{ago(i.updated_at, now)}</span></span>
                </motion.button>))}
            </AnimatePresence></div>
          </div>
        </Panel>
        <div className="inc-detail">{active ? <IncidentDetail id={active} /> : <Panel><Empty title="Select an incident" /></Panel>}</div>
      </div>
    </div>
  );
}

function IncidentDetail({ id }: { id: string }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const q = useQuery({ queryKey: qk.incident(id), queryFn: () => ep.incident(id) });
  const sess = useQuery({ queryKey: qk.session((q.data?.session_id as string) || ''), queryFn: () => ep.session(q.data!.session_id!), enabled: !!q.data?.session_id, staleTime: Infinity });
  const [confirm, setConfirm] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const i = q.data as (Incident & { link_monitor?: any[]; ledger_tx?: { id: string; block_height: number | null } | null; assessment?: any }) | undefined;
  const act = async (name: string, fn: () => Promise<unknown>, ok: string) => { setBusy(name); try { await fn(); toast({ tone: 'ok', title: ok }); qc.invalidateQueries({ queryKey: ['incidents'] }); qc.invalidateQueries({ queryKey: qk.incident(id) }); qc.invalidateQueries({ queryKey: qk.network }); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } finally { setBusy(null); } };
  if (q.isLoading) return <Skeleton h={500} />;
  if (q.error || !i) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const mon = (i.link_monitor || []).slice().sort((a: any, b: any) => a.t - b.t);
  const fx = (v: number) => new Date(v * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const findings = (sess.data as any)?.assessment?.findings || i.assessment?.findings || [];
  return (
    <motion.div key={id} className="stack" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <Panel tight reveal={false} className={i.severity === 'CRITICAL' ? 'accent-threat' : ''}>
        <div className="stack" style={{ ['--gap' as string]: '10px' }}>
          <button className="btn ghost sm show-md" onClick={() => nav('/incidents')} style={{ width: 'fit-content' }}><ArrowLeft />All incidents</button>
          <div className="row between wrap"><div className="row wrap" style={{ gap: 8 }}><SeverityPill level={i.severity} /><Chip>{i.status.toLowerCase()}</Chip>{i.attributed_to && <Chip tone="threat">attributed to {i.attributed_to}</Chip>}</div>
            <span className="xs muted">first {clock(i.created_at)} · last {clock(i.updated_at)} · ×{i.occurrences}</span></div>
          <h2>{i.title}</h2>
          <p style={{ margin: 0, color: 'var(--text-1)' }}>{i.summary}</p>
          <div className="row wrap">
            {i.status === 'OPEN' && <Button icon={<Eye />} loading={busy === 'ack'} onClick={() => act('ack', () => ep.ackIncident(id, 'acknowledged in console'), 'Incident acknowledged')}>Acknowledge</Button>}
            {i.status !== 'RESOLVED' && <Button variant="ok" icon={<CheckCheck />} loading={busy === 'res'} onClick={() => act('res', () => ep.resolveIncident(id, 'resolved in console'), 'Incident resolved')}>Resolve</Button>}
          </div>
        </div>
      </Panel>
      <div className="grid g2" style={{ alignItems: 'start' }}>
        <Panel title="Recommended response" kicker="Executes against the live network" tight reveal={false}>
          <div className="stack" style={{ ['--gap' as string]: '6px' }}>
            {i.recommended.map((a) => <Button key={a} size="sm" loading={busy === a} onClick={() => setConfirm(a)}>{ACTION_LABEL[a] || a}</Button>)}
            {!i.recommended.length && <p className="muted small">No automated response for this class.</p>}
          </div>
          {(i.actions || []).length > 0 && <div className="timeline">{(i.actions || []).map((a, k) => <div key={k} className="tl-item"><span className="tl-dot" /><div><b className="small">{ACTION_LABEL[a.action] || a.action}</b><div className="xs muted">{clock(a.at)}{a.note ? ` · ${a.note}` : ''}</div></div></div>)}</div>}
        </Panel>
        <Panel title="Anchors" tight reveal={false}>
          <KeyValue rows={[['link', i.link_id || '—'], ['group', i.group_id || '—'], ['session', i.session_id ? <Link key="s" to={`/sessions/${i.session_id}`}>open report →</Link> : '—'], ['bundle', <HashChip key="b" hash={i.bundle_id} />],
            ['ledger tx', i.ledger_tx ? <span key="l"><HashChip hash={i.ledger_tx.id} /> {i.ledger_tx.block_height != null ? `block #${i.ledger_tx.block_height}` : 'pending'}</span> : '—']]} />
          {i.ledger_tx && <Link className="btn sm ghost" to="/ledger" style={{ marginTop: 8 }}><Blocks />Ledger</Link>}
        </Panel>
      </div>
      {mon.length > 1 && <Panel title="Link monitor around the incident" kicker={i.link_id || ''} tight reveal={false}>
        <LineChart label="QBER around incident" height={200} xLabel="time" fx={fx} fy={(v) => pct(v, 1)} refs={[{ x: i.created_at, label: 'incident', color: 'var(--coral)' }]}
          series={[{ id: 'q', label: 'QBER', color: 'var(--sky)', dots: true, points: mon.map((p: any) => ({ x: p.t, y: p.qber })) }]} />
        <LineChart label="CHSH around incident" height={170} xLabel="time" fx={fx} fy={(v) => fix(v, 2)} refs={[{ y: 2, label: 'classical bound' }, { x: i.created_at, label: '', color: 'var(--coral)' }]}
          series={[{ id: 's', label: 'CHSH S', color: 'var(--mint)', dots: true, points: mon.map((p: any) => ({ x: p.t, y: p.chsh })) }]} />
      </Panel>}
      {sess.data && <Panel title="Related session" tight reveal={false} actions={<VerdictBadge verdict={sess.data.verdict} />}><FindingsList findings={findings} /></Panel>}
      <Confirm open={!!confirm} onClose={() => setConfirm(null)} title={ACTION_LABEL[confirm || ''] || ''} confirmLabel="Execute"
        body="This changes the live network (link status, bundles or principals) and is recorded on the incident and in the audit ledger."
        onConfirm={() => { const a = confirm!; act(a, () => ep.respond(id, a), `${ACTION_LABEL[a] || a} executed`); }} />
    </motion.div>
  );
}
