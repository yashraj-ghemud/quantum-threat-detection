/* One WebSocket to /ws. Exponential backoff with jitter, a 10 s ping for RTT,
   reconnect after 30 s of silence, and rAF-batched delivery so campaigns
   never cause render storms. */
import { wsUrl } from '@/api/client';
import type { WsEvent } from '@/api/types';
import { useConn } from '@/state/live';
import { route } from './router';

let ws: WebSocket | null = null;
let attempts = 0;
let queue: WsEvent[] = [];
let raf = 0;
let pingTimer: ReturnType<typeof setInterval> | undefined;
let retryTimer: ReturnType<typeof setTimeout> | undefined;
let lastMsg = 0;
let stopped = false;
const pings = new Map<number, number>();

function flush() {
  raf = 0;
  const batch = queue; queue = [];
  for (const ev of batch) { try { route(ev); } catch (e) { console.error('ws route', e); } }
}

function schedule() {
  if (raf) return;
  raf = typeof requestAnimationFrame === 'function' && !document.hidden ? requestAnimationFrame(flush) : (setTimeout(flush, 50) as unknown as number);
}

export function connect() {
  stopped = false;
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  const conn = useConn.getState();
  conn.set({ status: attempts ? 'reconnecting' : 'connecting', attempts });
  let sock: WebSocket;
  try { sock = new WebSocket(wsUrl()); } catch { return retry(); }
  ws = sock;
  sock.onopen = () => {
    attempts = 0; lastMsg = Date.now();
    useConn.getState().set({ status: 'live', attempts: 0 });
    clearInterval(pingTimer);
    pingTimer = setInterval(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      if (Date.now() - lastMsg > 30_000) { ws.close(); return; }
      const t = Math.round(performance.now());
      pings.set(t, t);
      ws.send(JSON.stringify({ op: 'ping', t }));
    }, 10_000);
  };
  sock.onmessage = (m) => {
    lastMsg = Date.now();
    let ev: WsEvent;
    try { ev = JSON.parse(m.data); } catch { return; }
    if (ev.type === 'pong') {
      const t = Number(ev.data?.t);
      if (pings.has(t)) { useConn.getState().set({ rttMs: Math.round(performance.now() - t) }); pings.delete(t); }
      return;
    }
    if (ev.type === 'heartbeat') return;
    useConn.getState().set({ lastEventAt: Date.now() });
    if (ev.type === 'hello') {
      useConn.getState().set({ serverVersion: ev.data?.server_version ?? null, preset: ev.data?.preset ?? null });
      // Measure RTT right away.
      const t = Math.round(performance.now()); pings.set(t, t);
      sock.send(JSON.stringify({ op: 'ping', t }));
    }
    queue.push(ev);
    schedule();
  };
  sock.onclose = () => {
    clearInterval(pingTimer);
    if (ws === sock) ws = null;
    if (!stopped) retry();
  };
  sock.onerror = () => { try { sock.close(); } catch { /* ignore */ } };
}

function retry() {
  attempts++;
  const base = Math.min(8000, 500 * 2 ** Math.min(attempts - 1, 4));
  const delay = base * (0.8 + Math.random() * 0.4);
  useConn.getState().set({ status: attempts > 6 ? 'offline' : 'reconnecting', attempts });
  clearTimeout(retryTimer);
  retryTimer = setTimeout(connect, delay);
}

export function disconnect() {
  stopped = true;
  clearInterval(pingTimer); clearTimeout(retryTimer);
  ws?.close(); ws = null;
}

export function reconnectNow() { attempts = 0; clearTimeout(retryTimer); if (!ws) connect(); }

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !ws && !stopped) reconnectNow(); });
}
