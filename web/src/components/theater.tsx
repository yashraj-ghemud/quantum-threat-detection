/* Shared playback machinery for theaters (Studio, Attack Lab). */
import { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { Play, Pause, SkipForward, RotateCcw } from 'lucide-react';
import { reducedMotion } from '@/state/prefs';

export function usePlayback(durations: number[], runKey: string | null) {
  const total = durations.reduce((a, b) => a + b, 0);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const last = useRef(0);
  useEffect(() => {
    if (!runKey) return;
    if (reducedMotion()) { setT(total); setPlaying(false); return; }
    setT(0); setPlaying(true);
  }, [runKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!playing) return;
    let raf = 0; last.current = performance.now();
    const step = (now: number) => {
      const dt = (now - last.current) / 1000; last.current = now;
      setT((x) => { const n = Math.min(total, x + dt * speed); if (n >= total) setPlaying(false); return n; });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, total]);
  let acc = 0, stage = 0, local = 0;
  for (let i = 0; i < durations.length; i++) { if (t < acc + durations[i] || i === durations.length - 1) { stage = i; local = Math.min(1, (t - acc) / durations[i]); break; } acc += durations[i]; }
  const done = t >= total;
  return { t, total, stage, local, done, playing, speed, setSpeed, setPlaying, seek: (x: number) => setT(Math.max(0, Math.min(total, x))), seekStage: (i: number) => { setT(durations.slice(0, i).reduce((a, b) => a + b, 0) + 0.001); }, skip: () => { setT(total); setPlaying(false); }, replay: () => { setT(0); setPlaying(true); },
    progressOf: (i: number) => (i < stage || done ? 1 : i > stage ? 0 : local) };
}

export function Stepper({ steps, pb }: { steps: string[]; pb: ReturnType<typeof usePlayback> }) {
  return (
    <ol className="stepper" aria-label="Pipeline stages" style={{ ['--n' as string]: steps.length }}>
      {steps.map((s, i) => {
        const p = pb.progressOf(i);
        const state = p >= 1 ? 'done' : i === pb.stage ? 'on' : 'todo';
        return (
          <li key={s} className={state} aria-current={state === 'on' ? 'step' : undefined}>
            <span className="st-dot" role="button" tabIndex={0} aria-label={`Go to stage ${i + 1}: ${s}`} onClick={() => pb.seekStage(i)} onKeyDown={(e) => { if (e.key === 'Enter') pb.seekStage(i); }}>{i + 1}</span><span className="st-label" onClick={() => pb.seekStage(i)}>{s}</span>
            {i < steps.length - 1 && <span className="st-bar"><motion.i animate={{ scaleX: p }} initial={false} transition={{ duration: 0.1 }} /></span>}
          </li>
        );
      })}
    </ol>
  );
}

export function PlaybackBar({ pb }: { pb: ReturnType<typeof usePlayback> }) {
  return (
    <div className="pb-bar">
      <button className="btn icon sm" aria-label={pb.playing ? 'Pause' : 'Play'} onClick={() => (pb.done ? pb.replay() : pb.setPlaying(!pb.playing))}>{pb.done ? <RotateCcw /> : pb.playing ? <Pause /> : <Play />}</button>
      <input className="range grow" type="range" min={0} max={pb.total} step={0.01} value={pb.t} aria-label="Scrub" onChange={(e) => { pb.setPlaying(false); pb.seek(Number(e.target.value)); }}
        style={{ ['--fill' as string]: `${(pb.t / pb.total) * 100}%` }} />
      <div className="seg">{[0.5, 1, 2].map((s) => <button key={s} aria-pressed={pb.speed === s} onClick={() => pb.setSpeed(s)}>×{s}</button>)}</div>
      <button className="btn sm" onClick={pb.skip}><SkipForward />Skip to verdict</button>
    </div>
  );
}

export function VerdictStamp({ verdict, sub, show }: { verdict: string; sub?: string; show: boolean }) {
  const ok = verdict === 'ACCEPTED' || verdict === 'CERTIFIED';
  return show ? (
    <motion.div className={`stamp ${ok ? 'ok' : 'bad'}`} initial={{ scale: 1.8, opacity: 0, rotate: -14 }} animate={{ scale: 1, opacity: 1, rotate: -6 }} transition={{ type: 'spring', stiffness: 180, damping: 12 }}>
      <b>{verdict}</b>{sub && <span>{sub}</span>}
      <motion.i className="stamp-ring" initial={{ scale: 0.6, opacity: 0.8 }} animate={{ scale: 2.6, opacity: 0 }} transition={{ duration: 1.1 }} />
    </motion.div>
  ) : null;
}

/** A packet flying along a bezier between two labelled endpoints. */
export function PacketFlight({ from, to, progress, label, color = 'var(--gold)' }: { from: string; to: string; progress: number; label: string; color?: string }) {
  const d = 'M60,90 C200,10 380,10 520,90';
  return (
    <svg viewBox="0 0 580 130" width="100%" className="packet" role="img" aria-label={`${label} from ${from} to ${to}`}>
      <path d={d} fill="none" stroke="var(--line-strong)" strokeWidth={2} strokeDasharray="6 6" />
      <path d={d} fill="none" stroke={color} strokeWidth={3} pathLength={1} strokeDasharray={`${progress} 1`} />
      <g transform="translate(60,90)"><circle r={22} fill={`var(--${from})`} opacity={0.2} /><circle r={12} fill={`var(--${from})`} /><text y={40} textAnchor="middle" fontSize={13} fontWeight={700} fill="var(--text-0)">{from}</text></g>
      <g transform="translate(520,90)"><circle r={22} fill={`var(--${to})`} opacity={0.2} /><circle r={12} fill={`var(--${to})`} /><text y={40} textAnchor="middle" fontSize={13} fontWeight={700} fill="var(--text-0)">{to}</text></g>
      {progress > 0 && progress < 1 && (() => { const t = progress; const x = (1 - t) ** 3 * 60 + 3 * (1 - t) ** 2 * t * 200 + 3 * (1 - t) * t * t * 380 + t ** 3 * 520; const y = (1 - t) ** 3 * 90 + 3 * (1 - t) ** 2 * t * 10 + 3 * (1 - t) * t * t * 10 + t ** 3 * 90;
        return <g transform={`translate(${x},${y})`}><rect x={-26} y={-13} width={52} height={26} rx={8} fill={color} style={{ filter: `drop-shadow(0 0 10px ${color})` }} /><text y={4} textAnchor="middle" fontSize={10} fontWeight={700} fill="#fff">{label}</text></g>; })()}
    </svg>
  );
}

/** Press-and-hold to confirm (pointer or Space/Enter). */
export function HoldButton({ onConfirm, children, holdMs = 650, disabled, loading }: { onConfirm: () => void; children: React.ReactNode; holdMs?: number; disabled?: boolean; loading?: boolean }) {
  const [p, setP] = useState(0);
  const raf = useRef(0), t0 = useRef(0), fired = useRef(false);
  const stop = () => { cancelAnimationFrame(raf.current); if (!fired.current) setP(0); };
  const start = () => {
    if (disabled || loading) return;
    fired.current = false; t0.current = performance.now();
    const step = (now: number) => {
      const k = Math.min(1, (now - t0.current) / holdMs); setP(k);
      if (k >= 1) { fired.current = true; onConfirm(); setTimeout(() => setP(0), 400); return; }
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  };
  return (
    <button type="button" className="btn danger lg hold-btn no-magnet" disabled={disabled} aria-busy={loading || undefined}
      onPointerDown={(e) => { (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId); start(); }} onPointerUp={stop} onPointerCancel={stop}
      onKeyDown={(e) => { if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); start(); } }} onKeyUp={(e) => { if (e.key === ' ' || e.key === 'Enter') stop(); }}>
      <svg className="hold-ring" viewBox="0 0 36 36" aria-hidden><circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,.35)" strokeWidth="3" /><circle cx="18" cy="18" r="15" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" pathLength={1} strokeDasharray={`${p} 1`} transform="rotate(-90 18 18)" /></svg>
      {loading ? <span className="spin" /> : null}{children}
      <i className="hold-fill" style={{ transform: `scaleX(${p})` }} />
    </button>
  );
}
