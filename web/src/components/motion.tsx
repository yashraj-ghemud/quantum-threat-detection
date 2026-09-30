import { useEffect, useRef, useState } from 'react';
import { animate, useReducedMotion } from 'motion/react';

/** Springs from the previous value (never from 0 after the first render). */
export function CountUp({ value, format = (v: number) => String(Math.round(v)), duration = 0.9 }: { value: number | null | undefined; format?: (v: number) => string; duration?: number }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState<number | null>(value ?? null);
  const prev = useRef<number | null>(value ?? null);
  useEffect(() => {
    if (value == null || !Number.isFinite(value)) { setShown(null); return; }
    const from = prev.current ?? 0;
    prev.current = value;
    if (reduce || from === value) { setShown(value); return; }
    const ctl = animate(from, value, { duration, ease: [0.22, 1, 0.36, 1], onUpdate: (v) => setShown(v) });
    return () => ctl.stop();
  }, [value, reduce, duration]);
  return <span className="tnum">{shown == null ? '—' : format(shown)}</span>;
}

const GLYPHS = '0123456789abcdef';
/** Characters resolve left→right from random glyphs. */
export function ScrambleText({ text, duration = 700, className }: { text: string; duration?: number; className?: string }) {
  const reduce = useReducedMotion();
  const [out, setOut] = useState(text);
  useEffect(() => {
    if (reduce) { setOut(text); return; }
    let raf = 0; const t0 = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / duration);
      const n = Math.floor(k * text.length);
      setOut(text.slice(0, n) + text.slice(n).split('').map((c) => (c === ' ' ? ' ' : GLYPHS[(Math.random() * 16) | 0])).join(''));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [text, duration, reduce]);
  return <span className={className}>{out}</span>;
}

/** Headline whose letters assemble from scattered positions. */
export function AssembleText({ text, className, delay = 0 }: { text: string; className?: string; delay?: number }) {
  const reduce = useReducedMotion();
  return (
    <span className={className} aria-label={text}>
      {text.split('').map((c, i) => (
        <span key={i} aria-hidden style={{ display: 'inline-block', whiteSpace: 'pre', opacity: reduce ? 1 : 0,
          animation: reduce ? undefined : `qv-assemble .9s cubic-bezier(.2,.8,.2,1) forwards`, animationDelay: `${delay + i * 22}ms`,
          ['--dx' as string]: `${((i * 37) % 80) - 40}px`, ['--dy' as string]: `${((i * 53) % 60) - 30}px` }}>{c}</span>
      ))}
    </span>
  );
}

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => { const t = setInterval(() => setNow(Date.now() / 1000), intervalMs); return () => clearInterval(t); }, [intervalMs]);
  return now;
}

export function useDebounced<T>(value: T, ms = 150): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

export function useMeasure<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ width: e.contentRect.width, height: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

export function useInView<T extends HTMLElement>(margin = '120px') {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { rootMargin: margin });
    io.observe(el);
    return () => io.disconnect();
  }, [margin]);
  return [ref, inView] as const;
}
