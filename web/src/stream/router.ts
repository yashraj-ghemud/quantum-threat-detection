/* Routes WebSocket events into stores, the query cache, toasts and scenes. */
import type { Campaign, LinkInfo, Network, SessionSummary, WsEvent } from '@/api/types';
import { queryClient } from '@/api/query';
import { qk } from '@/api/endpoints';
import { useLive, useScene } from '@/state/live';
import { toast } from '@/state/ui';
import { sfx } from '@/lib/audio';
import { getPrefs } from '@/state/prefs';

const timers = new Map<string, ReturnType<typeof setTimeout>>();
function debounce(key: string, ms: number, fn: () => void) {
  clearTimeout(timers.get(key));
  timers.set(key, setTimeout(fn, ms));
}
const inval = (key: readonly unknown[], ms = 600) => debounce(JSON.stringify(key), ms, () => queryClient.invalidateQueries({ queryKey: key }));

export function route(ev: WsEvent) {
  const live = useLive.getState();
  const scene = useScene.getState();
  switch (ev.type) {
    case 'hello':
      if (ev.data?.traffic) live.set({ traffic: ev.data.traffic });
      return;
    case 'session.completed': {
      const s = ev.data as SessionSummary;
      live.pushFeed(s);
      scene.push('packet', s);
      if (s.verdict === 'ACCEPTED') sfx.accept(); else sfx.reject();
      inval(['sessions']); inval(['metrics'], 1000); inval(['timeseries'], 1500);
      return;
    }
    case 'distribution.completed': {
      const s = ev.data as SessionSummary;
      live.pushFeed(s);
      scene.push('pulses', s);
      if (s.verdict === 'COMPROMISED') scene.push('lightning', s);
      inval(['sessions']); inval(['metrics'], 1000); inval(['timeseries'], 1500);
      return;
    }
    case 'incident.opened': {
      const inc = ev.data;
      const crit = inc.severity === 'CRITICAL' || inc.severity === 'HIGH';
      toast({ tone: crit ? 'threat' : 'warn', title: inc.title || 'New incident', body: inc.summary,
        action: { label: 'Investigate', href: `/incidents/${inc.id}` }, sticky: inc.severity === 'CRITICAL' && inc.origin !== 'CAMPAIGN' });
      scene.push('shock', inc);
      if (crit) { sfx.alarm(); if (getPrefs().haptics) { try { navigator.vibrate?.([30, 40, 30]); } catch { /* unsupported */ } } }
      inval(['incidents'], 300); inval(['metrics'], 800);
      return;
    }
    case 'incident.updated':
      inval(['incidents'], 300);
      if (ev.data?.id) queryClient.invalidateQueries({ queryKey: qk.incident(ev.data.id) });
      return;
    case 'link.updated': {
      const l = ev.data as LinkInfo;
      queryClient.setQueryData<Network>(qk.network, (n) => n ? { ...n, links: n.links.map((x) => (x.id === l.id ? { ...x, ...l } : x)) } : n);
      inval(qk.linkMonitor(l.id), 800);
      return;
    }
    case 'node.updated':
      queryClient.setQueryData<Network>(qk.network, (n) => n ? { ...n, nodes: n.nodes.map((x) => (x.id === ev.data.id ? { ...x, suspended: ev.data.suspended } : x)) } : n);
      inval(qk.reservoir, 200);
      return;
    case 'reservoir.updated':
      live.set({ reservoir: ev.data });
      queryClient.setQueryData(qk.reservoir, ev.data);
      return;
    case 'traffic.state':
      live.set({ traffic: ev.data });
      queryClient.setQueryData(qk.traffic, ev.data);
      return;
    case 'campaign.state': {
      const c = ev.data as Campaign;
      const others = live.campaigns.filter((x) => x.id !== c.id);
      live.set({ campaigns: c.state === 'running' ? [...others, c] : others });
      if (c.state !== 'running') toast({ tone: 'info', title: `Campaign “${c.name}” ${c.state}`, body: `${c.runs ?? 0} attacks · ${c.detected ?? 0} detected` });
      inval(qk.campaigns, 300);
      return;
    }
    case 'metrics.tick':
      live.set({ tick: ev.data, threat: ev.data.threat_level ?? 'NONE', openIncidents: ev.data.open_incidents ?? 0, ledgerHeight: ev.data.ledger_height ?? null });
      return;
    case 'job.progress':
    case 'job.completed': {
      const j = ev.data;
      queryClient.setQueryData(['job', j.id], (old: any) => ({ ...(old || {}), ...j }));
      if (ev.type === 'job.completed') {
        queryClient.invalidateQueries({ queryKey: qk.latest(j.kind) });
        queryClient.invalidateQueries({ queryKey: qk.jobs });
        toast({ tone: j.status === 'SUCCEEDED' ? 'ok' : 'warn', title: `Analysis “${j.kind.replace(/_/g, ' ')}” ${j.status.toLowerCase()}`,
          body: j.message || undefined, action: { label: 'Open', href: `/analytics#${j.kind}` } });
      } else inval(qk.jobs, 1500);
      return;
    }
    case 'ledger.block':
      scene.push('block', ev.data);
      live.set({ ledgerHeight: ev.data.height });
      sfx.block();
      inval(['ledger'], 200);
      return;
    case 'ledger.verified':
    case 'ledger.tampered':
      inval(['ledger'], 100);
      return;
    case 'selftest.start':
      live.set({ selftest: ev.data.checks || [], selftestDone: false });
      return;
    case 'selftest.check': {
      const c = ev.data;
      const list = live.selftest.some((x) => x.id === c.id) ? live.selftest.map((x) => (x.id === c.id ? c : x)) : [...live.selftest, c];
      live.set({ selftest: list });
      return;
    }
    case 'selftest.done':
      live.set({ selftest: ev.data.checks, selftestDone: true });
      queryClient.setQueryData(qk.selftest, ev.data);
      return;
    case 'system.notice':
      toast({ tone: ev.data.level === 'warning' ? 'warn' : 'info', title: ev.data.message });
      return;
    default:
  }
}
