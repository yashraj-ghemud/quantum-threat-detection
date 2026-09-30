import { create } from 'zustand';
import type { Campaign, MetricsTick, ReservoirEntry, SessionSummary, Severity, TrafficState, SelftestCheck } from '@/api/types';

export type ConnStatus = 'connecting' | 'live' | 'reconnecting' | 'offline';
interface ConnState { status: ConnStatus; attempts: number; rttMs: number | null; lastEventAt: number | null; serverVersion: string | null; preset: string | null }
export const useConn = create<ConnState & { set: (p: Partial<ConnState>) => void }>((set) => ({
  status: 'connecting', attempts: 0, rttMs: null, lastEventAt: null, serverVersion: null, preset: null, set: (p) => set(p),
}));

const FEED_MAX = 300;
interface LiveState {
  feed: SessionSummary[]; tick: MetricsTick | null; threat: Severity; openIncidents: number; traffic: TrafficState | null;
  campaigns: Campaign[]; reservoir: ReservoirEntry[] | null; selftest: SelftestCheck[]; selftestDone: boolean; ledgerHeight: number | null;
  pushFeed: (s: SessionSummary) => void; seedFeed: (s: SessionSummary[]) => void; set: (p: Partial<LiveState>) => void;
}
export const useLive = create<LiveState>((set, get) => ({
  feed: [], tick: null, threat: 'NONE', openIncidents: 0, traffic: null, campaigns: [], reservoir: null, selftest: [], selftestDone: false, ledgerHeight: null,
  pushFeed: (s) => {
    const f = get().feed;
    if (f.length && f[0].id === s.id) return;
    set({ feed: [s, ...f.filter((x) => x.id !== s.id)].slice(0, FEED_MAX) });
  },
  seedFeed: (s) => {
    const have = new Set(get().feed.map((x) => x.id));
    const merged = [...get().feed, ...s.filter((x) => !have.has(x.id))].sort((a, b) => b.created_at - a.created_at).slice(0, FEED_MAX);
    set({ feed: merged });
  },
  set: (p) => set(p),
}));

/* Scene events: 3D/2D scenes consume these (pulses, packets, lightning, blocks). */
export interface SceneEvent { id: number; kind: 'pulses' | 'packet' | 'lightning' | 'block' | 'shock' | 'verdict'; payload: any; t: number }
let seq = 1;
export const useScene = create<{ events: SceneEvent[]; push: (kind: SceneEvent['kind'], payload: any) => void; take: (since: number) => SceneEvent[] }>((set, get) => ({
  events: [],
  push: (kind, payload) => set({ events: [...get().events.slice(-80), { id: seq++, kind, payload, t: performance.now() }] }),
  take: (since) => get().events.filter((e) => e.id > since),
}));
