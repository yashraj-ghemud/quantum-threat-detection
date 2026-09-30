import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import { PenLine, Atom, ShieldCheck, ShieldOff, ScanLine, Zap, ExternalLink, ChevronRight } from 'lucide-react';
import type { Incident, LinkInfo, ReservoirEntry, SessionSummary, Severity } from '@/api/types';
import { ep, qk } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { toast } from '@/state/ui';
import { ago, catLabel, compact, fix, ms, pct } from '@/lib/format';
import { sevColor, SEV_RANK } from '@/lib/color';
import { Button, Chip, VerdictBadge, NodeAvatar } from './ui';
import { Sparkline, ChshGauge } from '@/charts/charts';
import { Drawer } from './overlays';
import { useNow } from './motion';
import { ReportView } from './reports';

/* ------------------------------------------------------------ threat ring */
export function ThreatRing({ level, incidents, size = 170 }: { level: Severity; incidents: Incident[]; size?: number }) {
  const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 } as Record<string, number>;
  incidents.forEach((i) => { if (i.severity in counts) counts[i.severity]++; });
  const rings = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
  const c = size / 2;
  const total = Math.max(1, incidents.length);
  return (
    <div className="threat-ring" style={{ width: size, height: size }} role="img" aria-label={`Threat level ${level}, ${incidents.length} open incidents`}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}>
        {rings.map((s, i) => {
          const r = c - 10 - i * 14, circ = 2 * Math.PI * r, frac = counts[s] / total;
          return (
            <g key={s} style={{ transformOrigin: `${c}px ${c}px`, animation: `spin ${40 + i * 12}s linear infinite${i % 2 ? ' reverse' : ''}` }}>
              <circle cx={c} cy={c} r={r} fill="none" stroke="var(--line-strong)" strokeWidth={8} opacity={0.6} />
              <motion.circle cx={c} cy={c} r={r} fill="none" stroke={sevColor(s)} strokeWidth={8} strokeLinecap="round" opacity={counts[s] ? 1 : 0}
                initial={false} animate={{ strokeDasharray: `${Math.max(counts[s] ? 6 : 0, frac * circ)} ${circ}` }} transition={{ type: 'spring', stiffness: 80, damping: 16 }} />
            </g>
          );
        })}
      </svg>
      <div className="tr-center"><b style={{ color: sevColor(level) }}>{level === 'NONE' ? 'CLEAR' : level}</b><span>{incidents.length} open</span></div>
    </div>
  );
}

/* ------------------------------------------------------------ liquid gauge */
export function LiquidGauge({ value, max, label, sub, color = 'var(--sky)' }: { value: number; max: number; label: string; sub?: string; color?: string }) {
  const k = Math.max(0, Math.min(1, max ? value / max : 0));
  return (
    <div className="liquid" role="meter" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label}>
      <div className="lq-tank" style={{ ['--c' as string]: color }}>
        <motion.div className="lq-fill" initial={false} animate={{ height: `${k * 100}%` }} transition={{ type: 'spring', stiffness: 70, damping: 14 }}>
          <svg className="lq-wave" viewBox="0 0 120 12" preserveAspectRatio="none"><path d="M0 6 Q 15 0 30 6 T 60 6 T 90 6 T 120 6 V12 H0 Z" fill={color} /></svg>
        </motion.div>
        <b>{value}<small>/{max}</small></b>
      </div>
      <div className="lq-label"><span>{label}</span>{sub && <small>{sub}</small>}</div>
    </div>
  );
}

export function ReservoirPanel({ reservoir }: { reservoir: ReservoirEntry[] | null }) {
  if (!reservoir) return <div className="skeleton" style={{ height: 120 }} />;
  return (
    <div className="row wrap" style={{ gap: 18 }}>
      {reservoir.map((r) => (
        <LiquidGauge key={r.group_id} value={r.active} max={r.target} label={`${r.signer_id} → ${r.recipients.join(', ')}`}
          sub={r.blocked_reason ? `blocked: ${r.blocked_reason}` : `${r.signed} signed · ${r.compromised_total} refused`} color={r.blocked_reason ? 'var(--coral)' : r.signer_id === 'diana' ? 'var(--diana)' : 'var(--alice)'} />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------ feed */
export function FeedRow({ s, onOpen, now }: { s: SessionSummary; onOpen: (id: string) => void; now: number }) {
  const sig = s.kind === 'signature';
  const bad = s.verdict === 'REJECTED' || s.verdict === 'COMPROMISED';
  return (
    <motion.button layout="position" type="button" className={`feed-row ${bad ? 'bad' : ''}`} onClick={() => onOpen(s.id)}
      initial={{ opacity: 0, y: -14, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ type: 'spring', stiffness: 380, damping: 30 }}>
      <span className={`fr-icon ${sig ? 'sig' : 'dist'}`}>{sig ? <PenLine /> : <Atom />}</span>
      <span className="fr-main">
        <span className="fr-title">{sig ? (s.message_preview || 'signature') : `${compact(s.qubits)} qubits teleported`}</span>
        <span className="fr-meta">{s.group_id} · {s.origin.toLowerCase()} · {ms(s.latency_ms)}{s.injected_attack && <> · <span className="threat-text">injected {s.injected_attack.attack_id}</span></>}</span>
      </span>
      <span className="fr-right">
        <VerdictBadge verdict={s.verdict} />
        {s.category !== 'NONE' && <span className="xs" style={{ color: sevColor(s.threat_level) }}>{catLabel(s.category)}{s.subtype ? ` · ${s.subtype.replace(/_/g, ' ')}` : ''}</span>}
        <span className="xs faint">{ago(s.created_at, now)}</span>
      </span>
    </motion.button>
  );
}

export function LiveFeed({ feed, max = 40 }: { feed: SessionSummary[]; max?: number }) {
  const [filter, setFilter] = useState<'all' | 'signature' | 'distribution' | 'threats'>('all');
  const [open, setOpen] = useState<string | null>(null);
  const now = useNow(5000);
  const rows = useMemo(() => feed.filter((s) => filter === 'all' || (filter === 'threats' ? s.verdict === 'REJECTED' || s.verdict === 'COMPROMISED' || s.category !== 'NONE' : s.kind === filter)).slice(0, max), [feed, filter, max]);
  return (
    <div className="stack" style={{ ['--gap' as string]: '10px' }}>
      <div className="row wrap" style={{ gap: 6 }}>
        {(['all', 'signature', 'distribution', 'threats'] as const).map((f) => (
          <button key={f} type="button" className="chip no-magnet" aria-pressed={filter === f} onClick={() => setFilter(f)}>{f === 'all' ? 'All' : f === 'signature' ? 'Signatures' : f === 'distribution' ? 'Distributions' : 'Threats'}</button>
        ))}
      </div>
      <div className="feed">
        <AnimatePresence initial={false}>{rows.map((s) => <FeedRow key={s.id} s={s} onOpen={setOpen} now={now} />)}</AnimatePresence>
        {!rows.length && <div className="empty"><div className="orb" /><h4>No sessions yet</h4><p>Start live traffic or sign a message in the Studio: every row here is a real engine run.</p></div>}
      </div>
      <SessionDrawer id={open} onClose={() => setOpen(null)} />
    </div>
  );
}

export function SessionDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const q = useQuery({ queryKey: qk.session(id || ''), queryFn: () => ep.session(id!), enabled: !!id, staleTime: Infinity });
  return (
    <Drawer open={!!id} onClose={onClose} title={q.data ? (q.data.kind === 'signature' ? 'Signature session' : 'Key distribution') : 'Session'} width={720}>
      {q.isLoading && <div className="skeleton" style={{ height: 300 }} />}
      {q.error && <div className="error-box">{friendly(q.error)}</div>}
      {q.data && <>
        <div className="row" style={{ marginBottom: 12 }}><Link className="btn sm" to={`/sessions/${id}`} onClick={onClose}><ExternalLink />Open full report</Link></div>
        <ReportView report={q.data} compact />
      </>}
    </Drawer>
  );
}

/* ------------------------------------------------------------ link card */
export function LinkCard({ link, onDetails }: { link: LinkInfo; onDetails: (id: string) => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const mon = useQuery({ queryKey: qk.linkMonitor(link.id), queryFn: () => ep.linkMonitor(link.id, 40), staleTime: 10_000 });
  const pts = (mon.data || []).slice().sort((a, b) => a.t - b.t);
  const last = link.last;
  const act = async (name: string, fn: () => Promise<any>, ok: (r: any) => string) => {
    setBusy(name);
    try { const r = await fn(); toast({ tone: 'ok', title: ok(r) }); qc.invalidateQueries({ queryKey: qk.network }); qc.invalidateQueries({ queryKey: qk.reservoir }); }
    catch (e) { toast({ tone: 'warn', title: friendly(e) }); } finally { setBusy(null); }
  };
  const status = link.status;
  const cusumFrac = last?.h_qber ? Math.min(1, (last.cusum_qber || 0) / last.h_qber) : 0;
  return (
    <div className={`link-card panel tight ${status === 'QUARANTINED' ? 'accent-threat' : ''} ${busy === 'certify' ? 'scanning' : ''}`}>
      <div className="row between">
        <div className="row" style={{ gap: 8 }}><NodeAvatar id={link.a} size={22} /><ChevronRight style={{ width: 14, color: 'var(--text-3)' }} /><NodeAvatar id={link.b} size={22} /><b className="small">{link.a} → {link.b}</b></div>
        <Chip tone={status === 'ACTIVE' ? 'ok' : status === 'QUARANTINED' ? 'threat' : 'warn'}>{status.toLowerCase()}</Chip>
      </div>
      <div className="lc-body">
        <ChshGauge S={last?.chsh} S0={link.baseline?.chsh} size={128} label={`${link.id} CHSH`} />
        <div className="stack grow" style={{ ['--gap' as string]: '6px' }}>
          <div className="xs muted row between"><span>QBER</span><b className="num" style={{ color: 'var(--text-0)' }}>{pct(last?.qber)}</b></div>
          <Sparkline values={pts.map((p) => p.qber)} band={link.baseline ? [0, link.baseline.qber * 1.6] : undefined} color="var(--sky)" label={`${link.id} QBER trend`} />
          <div className="xs muted row between"><span>CUSUM vs h</span><span className="num">{fix(last?.cusum_qber, 4)} / {fix(last?.h_qber ?? null, 4)}</span></div>
          <div className="progress"><i style={{ width: `${cusumFrac * 100}%`, background: cusumFrac >= 1 ? 'var(--coral)' : undefined }} /></div>
          <div className="xs faint">{link.length_km} km · {last ? `updated ${ago(last.t)}` : 'no bundle measured yet'}</div>
        </div>
      </div>
      <div className="row wrap" style={{ gap: 6 }}>
        <Button size="sm" icon={<ScanLine />} loading={busy === 'certify'} onClick={() => act('certify', () => ep.certify(link.id), (r) => r.certified ? `${link.id} certified · S = ${fix(r.bell?.S, 3)}` : `${link.id} NOT certified`)}>Certify</Button>
        {status === 'QUARANTINED'
          ? <Button size="sm" icon={<ShieldCheck />} loading={busy === 'rel'} onClick={() => act('rel', () => ep.release(link.id), () => `${link.id} released`)}>Release</Button>
          : <Button size="sm" icon={<ShieldOff />} loading={busy === 'q'} onClick={() => act('q', () => ep.quarantine(link.id, 'operator'), () => `${link.id} quarantined`)}>Quarantine</Button>}
        <Button size="sm" variant="ghost" icon={<Zap />} onClick={() => nav(`/attack-lab?attack=channel.dephase&target=${link.b === 'bob' || link.b === 'charlie' && link.a === 'diana' ? 'first' : 'second'}`)}>Attack</Button>
        <Button size="sm" variant="ghost" onClick={() => onDetails(link.id)}>Details</Button>
      </div>
    </div>
  );
}

export function worstSeverity(incidents: Incident[] | undefined): Severity {
  return (incidents || []).reduce((w, i) => (SEV_RANK[i.severity] > SEV_RANK[w] ? i.severity : w), 'NONE' as Severity);
}
