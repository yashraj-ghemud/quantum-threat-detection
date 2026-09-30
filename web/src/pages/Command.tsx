import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'motion/react';
import { Box, Map as MapIcon, Swords, X, Square, Pause, UserX, UserCheck, ShieldOff, ShieldCheck, Lock, Unlock } from 'lucide-react';
import { ep, qk } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { useConn, useLive } from '@/state/live';
import { usePrefs, qualityTier } from '@/state/prefs';
import { toast } from '@/state/ui';
import { Button, Chip, ErrorState, Panel, Segmented, Slider, Stat, KeyValue, Skeleton } from '@/components/ui';
import { CountUp } from '@/components/motion';
import { LinkCard, LiveFeed, ReservoirPanel, ThreatRing } from '@/components/live';
import { Drawer } from '@/components/overlays';
import { LineChart, Sparkline } from '@/charts/charts';
import { SceneCanvas } from '@/three/common';
import { NetworkScene } from '@/three/NetworkScene';
import { NetworkSvg } from '@/three/NetworkSvg';
import { TrafficControl } from '@/app/Shell';
import { pct, pctCI, fix, ago, int } from '@/lib/format';
import { sevColor } from '@/lib/color';

export default function Command() {
  const qc = useQueryClient();
  const net = useQuery({ queryKey: qk.network, queryFn: () => ep.network(), refetchInterval: 30_000 });
  const metrics = useQuery({ queryKey: qk.metrics('15m'), queryFn: () => ep.metrics('15m'), refetchInterval: 15_000 });
  const metricsAll = useQuery({ queryKey: qk.metrics('all'), queryFn: () => ep.metrics('all'), refetchInterval: 30_000 });
  const ts = useQuery({ queryKey: qk.timeseries('sessions', { bucket_s: 60 }), queryFn: () => ep.timeseries('sessions', { bucket_s: 60 }), refetchInterval: 20_000 });
  const incidents = useQuery({ queryKey: qk.incidents({ status: 'OPEN' }), queryFn: () => ep.incidents({ status: 'OPEN', limit: 200 }) });
  const live = useLive();
  const conn = useConn((s) => s.status);
  const quality = usePrefs((s) => s.quality);
  const [mode, setMode] = useState<'3d' | '2d'>(() => (qualityTier(quality) === 'low' ? '2d' : '3d'));
  const [selected, setSelected] = useState<{ kind: 'node' | 'link'; id: string } | null>(null);
  const [details, setDetails] = useState<string | null>(null);
  const [campaignOpen, setCampaignOpen] = useState(false);

  const m = metrics.data, all = metricsAll.data;
  const tick = live.tick;
  const pts = ts.data?.points || [];
  const quantum = (net.data?.links || []).filter((l) => l.kind === 'quantum' && !l.hidden);
  const selLink = selected?.kind === 'link' ? net.data?.links.find((l) => l.id === selected.id) : null;
  const selNode = selected?.kind === 'node' ? net.data?.nodes.find((n) => n.id === selected.id) : null;
  const campaign = live.campaigns[0];
  const sentence = useMemo(() => {
    const rate = tick?.sessions_per_min ?? m?.throughput_per_min ?? 0;
    return { rate, level: live.threat, open: live.openIncidents, height: live.ledgerHeight };
  }, [tick, m, live.threat, live.openIncidents, live.ledgerHeight]);

  if (net.error) return <ErrorState error={net.error} retry={() => net.refetch()} />;
  return (
    <div className="stack command">
      <header className="page-head">
        <div>
          <span className="kicker">Live security operations</span>
          <h1>Command Center</h1>
          <p className="status-sentence">
            <span className={`dot ${conn === 'live' ? 'pulse' : ''}`} style={{ color: conn === 'live' ? 'var(--ok)' : 'var(--warn)', display: 'inline-block', marginRight: 8 }} />
            {conn === 'live' ? 'Live' : 'Stream ' + conn} · <b className="num">{fix(sentence.rate, 1)}</b> signatures/min · threat level <b style={{ color: sevColor(sentence.level) }}>{sentence.level === 'NONE' ? 'CLEAR' : sentence.level}</b> · {sentence.open} open incidents{sentence.height != null && <> · ledger #{sentence.height}</>}
          </p>
        </div>
        <div className="row wrap">
          <div className="show-sm"><TrafficControl /></div>
          <Button variant={campaign ? 'danger' : 'default'} icon={<Swords />} onClick={() => setCampaignOpen(true)}>{campaign ? 'Campaign running' : 'Attack campaign'}</Button>
        </div>
      </header>

      <AnimatePresence>
        {live.traffic?.blocked && Object.keys(live.traffic.blocked).length > 0 && (
          <motion.div key="blocked" className="banner warn" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
            <Pause /><span className="grow">Live traffic skips {Object.entries(live.traffic.blocked).map(([g, why]) => `${g} (${why})`).join(' · ')}. Release the link or reinstate the signer to resume.</span>
          </motion.div>
        )}
        {campaign && (
          <motion.div className="banner threat" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
            <Swords /><span className="grow"><b>{campaign.name}</b> · {campaign.runs ?? 0} attacks launched · {campaign.detected ?? 0} detected{campaign.ends_at ? ` · ends ${ago(campaign.ends_at)}` : ''}</span>
            <Button size="sm" icon={<Square />} onClick={async () => { try { await ep.stopCampaign(campaign.id); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } }}>Stop</Button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="cmd-grid">
        <Panel className="cmd-scene" flush reveal={false}>
          <div className="scene-wrap">
            {net.data ? (mode === '3d'
              ? <SceneCanvas label="3D quantum network" camera={{ position: [0, 12, 17.5], fov: 44 }} fallback={<NetworkSvg net={net.data} selected={selected} onSelect={setSelected} />} style={{ height: '100%' }}>
                  <NetworkScene net={net.data} selected={selected} onSelect={setSelected} />
                </SceneCanvas>
              : <NetworkSvg net={net.data} selected={selected} onSelect={setSelected} />) : <Skeleton h="100%" />}
            <div className="scene-overlay tl">
              <Segmented label="Network view" value={mode} onChange={setMode} options={[{ value: '3d', label: <span className="row" style={{ gap: 6 }}><Box size={14} />3D</span> }, { value: '2d', label: <span className="row" style={{ gap: 6 }}><MapIcon size={14} />2D</span> }]} />
            </div>
            <div className="scene-overlay bl legend">
              <span><i style={{ background: 'var(--sky)' }} />quantum link</span><span><i style={{ background: 'var(--gold)' }} />classical / signature</span><span><i style={{ background: 'var(--coral)' }} />threat</span>
            </div>
            {conn !== 'live' && <div className="scene-offline">stream {conn} — showing last known state</div>}
            <AnimatePresence>
              {(selLink || selNode) && (
                <motion.div className="scene-detail" initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 30, opacity: 0 }}>
                  <div className="row between"><b>{selLink ? `${selLink.a} → ${selLink.b}` : selNode?.name}</b><button className="btn ghost icon sm" aria-label="Close" onClick={() => setSelected(null)}><X /></button></div>
                  {selLink && <KeyValue rows={[['kind', selLink.kind], ['status', selLink.status], ['length', `${selLink.length_km} km`], ['transmittance', selLink.transmittance != null ? pct(selLink.transmittance, 1) : '—'],
                    ['baseline channel', (selLink.baseline_channel || []).map((c) => `${c.type}${Object.entries(c).filter(([k]) => k !== 'type').map(([k, v]) => ` ${k}=${v}`).join('')}`).join(' ∘ ') || '—'],
                    ['last QBER / S', selLink.last ? `${pct(selLink.last.qber, 2)} / ${fix(selLink.last.chsh, 3)}` : 'not measured'], ['MAC on classical bits', selLink.authenticated_classical ? 'yes' : 'no']]} />}
                  {selNode && <KeyValue rows={[['role', selNode.role], ['label', selNode.label], ['status', selNode.suspended ? 'suspended' : 'active']]} />}
                  {selNode?.role === 'signer' && <NodeActions id={selNode.id} suspended={selNode.suspended} />}
                  {selLink?.kind === 'quantum' && <LinkActions id={selLink.id} status={selLink.status} mac={selLink.authenticated_classical} />}
                  {selLink?.kind === 'quantum' && <Button size="sm" onClick={() => setDetails(selLink.id)}>Link monitor</Button>}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </Panel>

        <div className="cmd-side stack">
          <Panel title="Threat level" kicker="Open incidents" explainTopic="threat_score" tilt>
            <div className="row" style={{ gap: 18 }}>
              <ThreatRing level={live.threat} incidents={incidents.data || []} />
              <div className="stack xs" style={{ ['--gap' as string]: '6px' }}>
                {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((s) => <span key={s} className="row" style={{ gap: 8 }}><span className="dot" style={{ color: sevColor(s), background: sevColor(s) }} />{s.toLowerCase()} <b className="num">{(incidents.data || []).filter((i) => i.severity === s).length}</b></span>)}
              </div>
            </div>
          </Panel>
          <div className="grid g2" style={{ ['--gap' as string]: '12px' }}>
            <Stat label="Throughput" value={<CountUp value={tick?.sessions_per_min ?? m?.throughput_per_min ?? 0} format={(v) => v.toFixed(1)} />} sub="signatures / min"
              spark={<Sparkline values={pts.map((p) => p.signatures)} label="signatures per minute" />} />
            <Stat label="Acceptance (15 min)" value={m && m.sessions.signature_total ? pct(m.sessions.accepted / m.sessions.signature_total, 1) : '—'} sub={m ? `${m.sessions.accepted}/${m.sessions.signature_total} accepted` : ''}
              spark={<Sparkline values={pts.map((p) => (p.signatures ? p.accepted / p.signatures : null))} color="var(--mint)" label="acceptance" />} />
            <Stat label="Attacks detected" explainTopic="threat_score" value={all?.detection.attack_runs ? `${all.detection.detected}/${all.detection.attack_runs}` : '—'}
              sub={all?.detection.detection_rate != null ? pctCI(all.detection.detection_rate, all.detection.far_ci ? [1 - all.detection.far_ci[1], 1 - all.detection.far_ci[0]] : null, 1) : 'run an attack to measure'} tone="var(--threat)" />
            <Stat label="False alarms" explainTopic="eps_rob" value={all?.detection.legit_runs ? `${all.detection.false_rejections}/${int(all.detection.legit_runs)}` : '—'}
              sub={all?.detection.frr != null ? `honest runs flagged · ${pctCI(all.detection.frr, all.detection.frr_ci, 2)}` : ''} tone="var(--ok)" />
          </div>
          <Panel title="Key reservoir" kicker="Certified one-time bundles" explainTopic="lamport">
            <ReservoirPanel reservoir={live.reservoir} />
          </Panel>
        </div>
      </div>

      <div className="cmd-grid bottom">
        <div className="stack">
          <div className="section-title" style={{ margin: '8px 0 0' }}><span className="kicker">Quantum links</span><h2>Link health</h2></div>
          <div className="link-row">{quantum.map((l) => <LinkCard key={l.id} link={l} onDetails={setDetails} />)}{!quantum.length && <Skeleton h={220} />}</div>
          <Panel title="Sessions per minute" kicker="Last hour">
            <LineChart label="sessions per minute" height={200} xLabel="time" fx={(v) => new Date(v * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              series={[{ id: 'sig', label: 'signatures', color: 'var(--lav)', points: pts.map((p) => ({ x: p.t, y: p.signatures })) },
                { id: 'dist', label: 'distributions', color: 'var(--sky)', points: pts.map((p) => ({ x: p.t, y: p.distributions })) },
                { id: 'att', label: 'attacks', color: 'var(--coral)', points: pts.map((p) => ({ x: p.t, y: p.attacks })) }]} />
          </Panel>
        </div>
        <Panel title="Live feed" kicker="Real engine runs · traffic payloads are synthetic payments" actions={<Chip mono>{live.feed.length}</Chip>}>
          <LiveFeed feed={live.feed} />
        </Panel>
      </div>

      <LinkDrawer id={details} onClose={() => setDetails(null)} />
      <CampaignSheet open={campaignOpen} onClose={() => setCampaignOpen(false)} onStarted={() => qc.invalidateQueries({ queryKey: qk.campaigns })} />
    </div>
  );
}

function LinkDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const mon = useQuery({ queryKey: qk.linkMonitor(id || ''), queryFn: () => ep.linkMonitor(id!, 300), enabled: !!id });
  const pts = (mon.data || []).slice().sort((a, b) => a.t - b.t);
  const fx = (v: number) => new Date(v * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const alarms = pts.filter((p) => p.alarm);
  return (
    <Drawer open={!!id} onClose={onClose} title={`Link monitor · ${id}`} width={760}>
      {mon.isLoading ? <Skeleton h={300} /> : pts.length === 0 ? <p className="muted">No bundles measured on this link yet.</p> : (
        <div className="stack">
          <p className="small muted">Each point is one key distribution on this link. CUSUM accumulates small QBER rises and CHSH drops; runs already flagged by single-run detectors are excluded from the accumulator.</p>
          <LineChart label="QBER over time" height={200} xLabel="time" fx={fx} fy={(v) => `${(v * 100).toFixed(2)}%`}
            series={[{ id: 'q', label: 'QBER', color: 'var(--sky)', points: pts.map((p) => ({ x: p.t, y: p.qber })), dots: true }, { id: 'e', label: 'EWMA', color: 'var(--lav)', dashed: true, points: pts.map((p) => ({ x: p.t, y: p.ewma_qber })) }]}
            markers={alarms.map((p) => ({ x: p.t, y: p.qber, color: 'var(--coral)' }))} />
          <LineChart label="CHSH over time" height={180} xLabel="time" fx={fx} series={[{ id: 's', label: 'CHSH S', color: 'var(--mint)', points: pts.map((p) => ({ x: p.t, y: p.chsh })), dots: true }]} refs={[{ y: 2, label: 'classical bound 2' }]} />
          <LineChart label="CUSUM" height={180} xLabel="time" fx={fx} series={[{ id: 'c', label: 'CUSUM (QBER)', color: 'var(--coral)', step: true, points: pts.map((p) => ({ x: p.t, y: p.cusum_qber })) }, { id: 'h', label: 'limit h', color: 'var(--text-3)', dashed: true, points: pts.map((p) => ({ x: p.t, y: p.h_qber ?? null })) }]} />
        </div>
      )}
    </Drawer>
  );
}

function CampaignSheet({ open, onClose, onStarted }: { open: boolean; onClose: () => void; onStarted: () => void }) {
  const q = useQuery({ queryKey: qk.campaigns, queryFn: ep.campaigns, enabled: open });
  const [preset, setPreset] = useState('blitz');
  const [rate, setRate] = useState(6);
  const [dur, setDur] = useState(120);
  const [busy, setBusy] = useState(false);
  const presets = q.data?.presets || {};
  const start = async () => {
    setBusy(true);
    try { const c = await ep.startCampaign({ preset, rate_per_min: rate, duration_s: dur }); toast({ tone: 'warn', title: `Campaign “${c.name}” started`, body: 'Attacks now mix into live traffic. Watch the network and the feed.' }); onStarted(); onClose(); }
    catch (e) { toast({ tone: 'warn', title: friendly(e) }); } finally { setBusy(false); }
  };
  return (
    <Drawer open={open} onClose={onClose} title="Attack campaign">
      <div className="stack">
        <p className="small muted">A campaign draws attacks from a weighted mix with the CSPRNG and runs them against the live network, mixed with honest traffic. Every detection you see is the engine’s real decision.</p>
        <div className="stack" style={{ ['--gap' as string]: '8px' }}>
          {Object.entries(presets).map(([k, p]) => (
            <button key={k} type="button" className={`preset-card ${preset === k ? 'on' : ''}`} onClick={() => setPreset(k)}>
              <b>{p.name}</b><span className="xs muted">{p.description}</span>
            </button>
          ))}
        </div>
        <Slider label="Rate" value={rate} min={1} max={30} step={1} onChange={setRate} format={(v) => `${v} attacks/min`} />
        <Slider label="Duration" value={dur} min={10} max={900} step={10} onChange={setDur} format={(v) => `${Math.floor(v / 60)} min ${v % 60} s`} />
        <Button variant="danger" size="lg" loading={busy} onClick={start} icon={<Swords />}>Launch campaign</Button>
      </div>
    </Drawer>
  );
}

function NodeActions({ id, suspended }: { id: string; suspended: boolean }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { await (suspended ? ep.reinstateNode(id) : ep.suspendNode(id)); toast({ tone: suspended ? 'ok' : 'warn', title: `${id} ${suspended ? 'reinstated' : 'suspended'}`, body: suspended ? 'The signer may sign again.' : 'Its signatures are refused until reinstated; the action is in the ledger.' }); qc.invalidateQueries({ queryKey: qk.network }); qc.invalidateQueries({ queryKey: qk.reservoir }); }
    catch (e) { toast({ tone: 'warn', title: friendly(e) }); } finally { setBusy(false); }
  };
  return <Button size="sm" variant={suspended ? 'ok' : 'danger'} loading={busy} icon={suspended ? <UserCheck /> : <UserX />} onClick={run}>{suspended ? 'Reinstate signer' : 'Suspend signer'}</Button>;
}

function LinkActions({ id, status, mac }: { id: string; status: string; mac: boolean }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const act = async (k: string, fn: () => Promise<unknown>, ok: string) => { setBusy(k); try { await fn(); toast({ tone: 'ok', title: ok }); qc.invalidateQueries({ queryKey: qk.network }); qc.invalidateQueries({ queryKey: qk.reservoir }); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } finally { setBusy(null); } };
  return (
    <div className="row wrap" style={{ gap: 6 }}>
      {status === 'QUARANTINED'
        ? <Button size="sm" icon={<ShieldCheck />} loading={busy === 'r'} onClick={() => act('r', () => ep.release(id), `${id} released`)}>Release</Button>
        : <Button size="sm" icon={<ShieldOff />} loading={busy === 'q'} onClick={() => act('q', () => ep.quarantine(id, 'operator'), `${id} quarantined — its bundles can no longer sign`)}>Quarantine</Button>}
      <Button size="sm" variant="ghost" icon={mac ? <Unlock /> : <Lock />} loading={busy === 'm'} onClick={() => act('m', () => ep.patchLink(id, { authenticated_classical: !mac }), mac ? 'MAC on frame bits disabled' : 'Frame bits now authenticated (Wegman–Carter MAC)')}>{mac ? 'Disable MAC' : 'Enable MAC'}</Button>
    </div>
  );
}
