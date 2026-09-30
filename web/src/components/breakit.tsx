/* "Try to break it": real attacks against the signature the user just made. */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { Repeat, Clock, PenLine, ShieldCheck, ShieldAlert } from 'lucide-react';
import type { SignatureReport } from '@/api/types';
import { ep } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { Button, Chip, Panel } from './ui';
import { catLabel } from '@/lib/format';

interface Outcome { key: string; label: string; verdict: string; category: string; subtype: string | null; evidence: string; sessionId?: string; incidentId?: string | null; error?: string }

export function BreakIt({ report }: { report: SignatureReport }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [out, setOut] = useState<Outcome[]>([]);
  const add = (o: Outcome) => setOut((x) => [o, ...x.filter((y) => y.key !== o.key)]);
  const fromSig = (key: string, label: string, r: SignatureReport, prefer?: string): Outcome => {
    const fired = r.assessment.findings.filter((x) => x.fired);
    const f = fired.find((x) => prefer && x.id.startsWith(prefer)) ?? fired[0];
    return { key, label, verdict: r.verdict, category: r.assessment.classification.category, subtype: r.assessment.classification.subtype, evidence: f?.evidence || r.assessment.classification.explanation, sessionId: r.session_id, incidentId: r.incident_id };
  };
  const run = async (key: string, label: string, fn: () => Promise<Outcome>) => {
    setBusy(key);
    try { add(await fn()); } catch (e) { add({ key, label, verdict: 'ERROR', category: 'NONE', subtype: null, evidence: friendly(e), error: friendly(e) }); } finally { setBusy(null); }
  };
  const msg = report.envelope?.message || 'signed message';
  return (
    <Panel title="Try to break it" kicker="Real attacks against this signature" tight reveal={false}>
      <p className="small muted" style={{ marginTop: 0 }}>Each button runs the attack for real and shows the engine’s own verdict. A defence that fails would show ACCEPTED here.</p>
      <div className="row wrap" style={{ gap: 8 }}>
        <Button size="sm" icon={<Repeat />} loading={busy === 'replay'} onClick={() => run('replay', 'Replay the exact signature', async () => fromSig('replay', 'Replay the exact signature', await ep.reverify(report.session_id)))}>Replay it</Button>
        <Button size="sm" icon={<Clock />} loading={busy === 'late'} onClick={() => run('late', 'Deliver it 5 minutes late', async () => fromSig('late', 'Deliver it 5 minutes late', await ep.reverify(report.session_id, { delay_s: 300 }), 'S6'))}>Deliver it late</Button>
        <Button size="sm" variant="danger" icon={<PenLine />} loading={busy === 'forge'} onClick={() => run('forge', 'Forge an altered copy', async () => {
          const r = await ep.runAttack({ attack: { attack_id: 'forgery.blind', intensity: 0.5 }, group_id: report.group_id, message: msg, counterfactual: false });
          const s = r.signature as SignatureReport;
          return { ...fromSig('forge', 'Forge an altered copy', s), evidence: `${r.notes?.[0] ?? ''} ${s.assessment.findings.find((f) => f.fired)?.evidence ?? ''}`.trim(), incidentId: r.incident_id };
        })}>Forge an altered copy</Button>
      </div>
      <div className="stack" style={{ ['--gap' as string]: '8px', marginTop: 12 }}>
        {out.map((o) => {
          const held = o.verdict === 'REJECTED' || o.verdict === 'ERROR';
          return (
            <motion.div key={o.key + o.sessionId} className={`break-row ${held ? 'held' : 'breach'}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              {held ? <ShieldCheck /> : <ShieldAlert />}
              <div className="grow" style={{ minWidth: 0 }}>
                <div className="row wrap" style={{ gap: 6 }}><b className="small">{o.label}</b><Chip tone={held ? 'ok' : 'threat'}>{o.error ? 'refused' : o.verdict}</Chip>
                  {o.category !== 'NONE' && <Chip mono>{catLabel(o.category)}{o.subtype ? ` · ${o.subtype.replace(/_/g, ' ')}` : ''}</Chip>}</div>
                <p className="xs muted" style={{ margin: '4px 0 0' }}>{o.evidence}</p>
              </div>
              {o.sessionId && <Link className="btn ghost sm" to={`/sessions/${o.sessionId}`}>Report</Link>}
            </motion.div>
          );
        })}
      </div>
    </Panel>
  );
}
