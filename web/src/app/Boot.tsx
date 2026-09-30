/* Boot sequence: a terminal log fed by REAL calls — /health and the engine's
   self-test checks (selftest.check events or polling). Min 1.6 s on screen;
   reveals after 6 s at most; offline shows a retry countdown. */
import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ep } from '@/api/endpoints';
import { useConn, useLive } from '@/state/live';
import { reducedMotion } from '@/state/prefs';
import type { SelftestCheck } from '@/api/types';
import { QubitLogo } from './Shell';

interface Line { text: string; tag?: 'OK' | 'FAIL' | 'SKIP' | '..' | 'ERR'; }
export function Boot({ onDone }: { onDone: () => void }) {
  const [lines, setLines] = useState<Line[]>([{ text: 'QVERIS SENTINEL · cold start' }]);
  const [progress, setProgress] = useState(0.05);
  const [offline, setOffline] = useState<number | null>(null);
  const [leaving, setLeaving] = useState(false);
  const t0 = useRef(performance.now());
  const reduce = reducedMotion();
  const seen = useRef(new Set<string>());
  const checks = useLive((s) => s.selftest);
  const conn = useConn((s) => s.status);
  const rtt = useConn((s) => s.rttMs);

  const push = (l: Line) => setLines((x) => [...x, l]);
  const finish = () => {
    const wait = Math.max(0, 1600 - (performance.now() - t0.current));
    setTimeout(() => { setLeaving(true); setTimeout(onDone, reduce ? 0 : 650); }, reduce ? 0 : wait);
  };

  useEffect(() => {
    if (reduce) { onDone(); return; }
    let alive = true;
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { setLeaving(true); setTimeout(onDone, 300); } };
    addEventListener('keydown', esc);
    const go = async () => {
      const s = performance.now();
      try {
        const h = await ep.health();
        if (!alive) return;
        push({ text: `GET /api/v1/health … 200 (${Math.round(performance.now() - s)} ms) · engine ${h.engine_version} · preset ${h.preset}`, tag: 'OK' });
        setProgress(0.25);
        const st = await ep.selftest();
        if (!alive) return;
        (st.checks || []).forEach(addCheck);
        if (st.state === 'idle' && !st.checks.length) push({ text: 'self-test queued by the server (runs after baseline calibration)', tag: '..' });
        setTimeout(() => alive && finish(), st.state === 'done' ? 400 : 6000);
      } catch {
        if (!alive) return;
        push({ text: 'engine unreachable', tag: 'ERR' });
        let n = 3; setOffline(n);
        const iv = setInterval(() => { n -= 1; setOffline(n); if (n <= 0) { clearInterval(iv); setOffline(null); if (alive) go(); } }, 1000);
      }
    };
    go();
    return () => { alive = false; removeEventListener('keydown', esc); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function addCheck(c: SelftestCheck) {
    if (seen.current.has(c.id) || c.status === 'pending' || c.status === 'running') return;
    seen.current.add(c.id);
    push({ text: `${c.id.padEnd(20, ' ')} ${c.detail || c.name}${c.duration_ms != null ? `  (${Math.round(c.duration_ms)} ms)` : ''}`, tag: c.status === 'pass' ? 'OK' : c.status === 'skip' ? 'SKIP' : 'FAIL' });
  }
  useEffect(() => { checks.forEach(addCheck); setProgress((p) => Math.max(p, 0.25 + 0.7 * (seen.current.size / Math.max(9, checks.length)))); }, [checks]); // eslint-disable-line react-hooks/exhaustive-deps
  const doneAll = useLive((s) => s.selftestDone);
  useEffect(() => { if (doneAll) { setProgress(1); finish(); } }, [doneAll]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (conn === 'live') push({ text: `event stream … ws open${rtt != null ? ` (rtt ${rtt} ms)` : ''}`, tag: 'OK' }); }, [conn === 'live']); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <AnimatePresence>
      {!leaving && (
        <motion.div className="boot" role="dialog" aria-label="Starting QVeris" exit={{ opacity: 0, scale: 1.04, filter: 'blur(10px)' }} transition={{ duration: 0.6 }}>
          <div className="boot-card">
            <div className="row" style={{ gap: 14 }}><QubitLogo size={42} /><div><div className="kicker">SIH 26141 · Egreen Quanta</div><b className="boot-brand">QVERIS</b></div></div>
            <div className="boot-log mono" aria-live="polite">
              {lines.map((l, i) => (
                <motion.div key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.25 }}>
                  {l.tag && <span className={`bt ${l.tag}`}>[{l.tag === 'OK' ? ' OK ' : l.tag}]</span>} {l.text}
                </motion.div>
              ))}
              {offline != null && <div className="bt-retry">retrying in {offline} s … <button className="btn sm" onClick={() => { setLeaving(true); setTimeout(onDone, 300); }}>Continue offline</button></div>}
              <span className="caret" />
            </div>
            <div className="progress"><i style={{ width: `${progress * 100}%` }} /></div>
            <button className="btn ghost sm boot-skip" onClick={() => { setLeaving(true); setTimeout(onDone, 300); }}>Skip <kbd>Esc</kbd></button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
