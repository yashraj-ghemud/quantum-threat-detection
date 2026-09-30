import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { scaleLinear, scaleLog, scaleBand } from 'd3-scale';
import { line, area, curveMonotoneX, curveStepAfter } from 'd3-shape';
import { motion, useReducedMotion } from 'motion/react';
import { useMeasure } from '@/components/motion';
import { sci } from '@/lib/format';

/* ------------------------------------------------------------ sparkline */
export function Sparkline({ values, color = 'var(--lav)', height = 34, band, label }: { values: (number | null)[]; color?: string; height?: number; band?: [number, number]; label?: string }) {
  const [ref, { width }] = useMeasure<HTMLDivElement>();
  const v = values.filter((x): x is number => x != null && Number.isFinite(x));
  const d = useMemo(() => {
    if (v.length < 2 || !width) return null;
    const lo = Math.min(...v, band?.[0] ?? Infinity), hi = Math.max(...v, band?.[1] ?? -Infinity);
    const x = scaleLinear().domain([0, v.length - 1]).range([2, width - 4]);
    const y = scaleLinear().domain(lo === hi ? [lo - 1, hi + 1] : [lo, hi]).range([height - 3, 3]);
    return { path: line<number>().x((_, i) => x(i)).y((p) => y(p)).curve(curveMonotoneX)(v) || '', last: [x(v.length - 1), y(v[v.length - 1])], band: band ? [y(band[1]), y(band[0])] : null };
  }, [v.join(','), width, height, band?.[0], band?.[1]]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div ref={ref} style={{ height }} role="img" aria-label={label || 'trend'}>
      {d && <svg width={width} height={height}>
        {d.band && <rect x={0} width={width} y={d.band[0]} height={Math.max(1, d.band[1] - d.band[0])} fill={color} opacity={0.08} />}
        <path d={d.path} fill="none" stroke={color} strokeWidth={1.8} strokeLinecap="round" />
        <circle cx={d.last[0]} cy={d.last[1]} r={3.2} fill={color} style={{ filter: `drop-shadow(0 0 5px ${color})` }} />
      </svg>}
    </div>
  );
}

/* ------------------------------------------------------------ line chart */
export interface Series { id: string; label: string; color: string; points: { x: number; y: number | null; lo?: number | null; hi?: number | null }[]; dashed?: boolean; step?: boolean; dots?: boolean; width?: number }
export interface RefLine { x?: number; y?: number; label: string; color?: string }
export function LineChart({ series, height = 260, xLog, yLog, xLabel, yLabel, refs = [], fx = (v: number) => String(+v.toPrecision(3)), fy = (v: number) => String(+v.toPrecision(3)), yDomain, xDomain, label, markers = [] }: {
  series: Series[]; height?: number; xLog?: boolean; yLog?: boolean; xLabel?: string; yLabel?: string; refs?: RefLine[]; fx?: (v: number) => string; fy?: (v: number) => string;
  yDomain?: [number, number]; xDomain?: [number, number]; label: string; markers?: { x: number; y: number; color: string; label?: string }[];
}) {
  const [ref, { width }] = useMeasure<HTMLDivElement>();
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hover, setHover] = useState<number | null>(null);
  const reduce = useReducedMotion();
  const m = { l: 52, r: 14, t: 12, b: 38 };
  const vis = series.filter((s) => !hidden.has(s.id));
  const all = vis.flatMap((s) => s.points.filter((p) => p.y != null && Number.isFinite(p.y as number)));
  const xs = all.map((p) => p.x), ys = all.flatMap((p) => [p.y as number, p.lo ?? (p.y as number), p.hi ?? (p.y as number)]).filter((v) => Number.isFinite(v) && (!yLog || v > 0));
  refs.forEach((r) => { if (r.y != null && (!yLog || r.y > 0)) ys.push(r.y); });
  const W = Math.max(0, width - m.l - m.r), H = height - m.t - m.b;
  const xd: [number, number] = xDomain || [Math.min(...xs), Math.max(...xs)];
  let yd: [number, number] = yDomain || [Math.min(...ys), Math.max(...ys)];
  if (!yDomain && !yLog) { const pad = (yd[1] - yd[0]) * 0.08 || Math.abs(yd[1]) * 0.1 || 1; yd = [yd[0] - pad, yd[1] + pad]; }
  const ok = xs.length > 0 && W > 20 && Number.isFinite(xd[0]) && Number.isFinite(yd[0]);
  const x = (xLog ? scaleLog() : scaleLinear()).domain(xd[0] === xd[1] ? [xd[0] * 0.9 || -1, xd[1] * 1.1 || 1] : xd).range([0, W]);
  const y = (yLog ? scaleLog() : scaleLinear()).domain(yd[0] === yd[1] ? [yd[0] * 0.9 || -1, yd[1] * 1.1 || 1] : yd).range([H, 0]).clamp(true);
  const niceLog = (ts: number[], max: number) => { const m = ts.filter((t) => { const e = Math.floor(Math.log10(t) + 1e-9); const k = Math.round(t / 10 ** e); return k === 1 || k === 2 || k === 5; }); const p = ts.filter((t) => Math.abs(Math.log10(t) - Math.round(Math.log10(t))) < 1e-9); return m.length <= max ? m : p.length <= max ? p : p.filter((_, i) => i % Math.ceil(p.length / max) === 0); };
  const xt = ok ? (xLog ? niceLog((x as any).ticks(), width < 500 ? 4 : 8) : (x as any).ticks(width < 500 ? 4 : 7)) : [];
  const yt = ok ? (yLog ? niceLog((y as any).ticks(), 6) : (y as any).ticks(5)) : [];
  const allX = [...new Set(all.map((p) => p.x))].sort((a, b) => a - b);
  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const r = (e.currentTarget as SVGRectElement).getBoundingClientRect();
    const px = e.clientX - r.left;
    let best = null as number | null, bd = Infinity;
    for (const v of allX) { const d = Math.abs(x(v) - px); if (d < bd) { bd = d; best = v; } }
    setHover(best);
  };
  return (
    <div className="chart" role="img" aria-label={label}>
      <div ref={ref} style={{ height, position: 'relative' }}>
        {ok && <svg width={width} height={height} style={{ overflow: 'visible' }}>
          <g transform={`translate(${m.l},${m.t})`}>
            {yt.map((t: number) => <g key={`y${t}`}><line x1={0} x2={W} y1={y(t)} y2={y(t)} stroke="var(--line)" /><text x={-8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--text-3)" className="num">{yLog ? sci(t, 1) : fy(t)}</text></g>)}
            {xt.map((t: number) => <text key={`x${t}`} x={x(t)} y={H + 18} textAnchor="middle" fontSize={11} fill="var(--text-3)" className="num">{fx(t)}</text>)}
            {xLabel && <text x={W / 2} y={H + 34} textAnchor="middle" fontSize={11.5} fill="var(--text-2)">{xLabel}</text>}
            {yLabel && <text transform={`translate(${-40},${H / 2}) rotate(-90)`} textAnchor="middle" fontSize={11.5} fill="var(--text-2)">{yLabel}</text>}
            {refs.map((r, i) => r.y != null ? (
              <g key={`r${i}`}><line x1={0} x2={W} y1={y(r.y)} y2={y(r.y)} stroke={r.color || 'var(--coral)'} strokeDasharray="5 4" strokeWidth={1.3} />
                <text x={W - 4} y={y(r.y) - 5} textAnchor="end" fontSize={11} fill={r.color || 'var(--coral)'} fontWeight={600}>{r.label}</text></g>
            ) : r.x != null ? (
              <g key={`r${i}`}><line y1={0} y2={H} x1={x(r.x)} x2={x(r.x)} stroke={r.color || 'var(--coral)'} strokeDasharray="5 4" strokeWidth={1.3} />
                <text x={x(r.x) + 4} y={10} fontSize={11} fill={r.color || 'var(--coral)'} fontWeight={600}>{r.label}</text></g>
            ) : null)}
            {vis.map((s) => {
              const pts = s.points.filter((p) => p.y != null && Number.isFinite(p.y as number) && (!yLog || (p.y as number) > 0));
              const band = pts.filter((p) => p.lo != null && p.hi != null);
              const bandPath = band.length > 1 ? area<typeof pts[0]>().x((p) => x(p.x)).y0((p) => y(Math.max(p.lo as number, yLog ? 1e-300 : -Infinity))).y1((p) => y(p.hi as number)).curve(curveMonotoneX)(band) : null;
              const path = line<typeof pts[0]>().x((p) => x(p.x)).y((p) => y(p.y as number)).curve(s.step ? curveStepAfter : curveMonotoneX)(pts) || '';
              return (
                <g key={s.id}>
                  {bandPath && <path d={bandPath} fill={s.color} opacity={0.14} />}
                  <motion.path d={path} fill="none" stroke={s.color} strokeWidth={s.width ?? 2} strokeDasharray={s.dashed ? '6 5' : undefined} strokeLinecap="round"
                    initial={reduce ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} />
                  {(s.dots || pts.length < 3) && pts.map((p, i) => <circle key={i} cx={x(p.x)} cy={y(p.y as number)} r={3} fill={s.color} />)}
                  {band.filter(() => s.dots).map((p, i) => <line key={`w${i}`} x1={x(p.x)} x2={x(p.x)} y1={y(p.lo as number)} y2={y(p.hi as number)} stroke={s.color} strokeWidth={1.4} />)}
                </g>
              );
            })}
            {markers.map((mk, i) => <g key={`m${i}`}><circle cx={x(mk.x)} cy={y(mk.y)} r={5} fill={mk.color} stroke="var(--bg-2)" strokeWidth={2} />{mk.label && <text x={x(mk.x) + 8} y={y(mk.y) - 6} fontSize={11} fill={mk.color}>{mk.label}</text>}</g>)}
            {hover != null && <line x1={x(hover)} x2={x(hover)} y1={0} y2={H} stroke="var(--text-3)" strokeDasharray="2 3" />}
            <rect width={W} height={H} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
          </g>
        </svg>}
        {ok && hover != null && (
          <div className="chart-tip" style={{ left: Math.min(m.l + x(hover) + 12, width - 190), top: 8 }}>
            <div className="mono xs muted">{xLabel || 'x'} = {fx(hover)}</div>
            {vis.map((s) => { const p = s.points.find((q) => q.x === hover); return p && p.y != null ? <div key={s.id} className="row xs" style={{ gap: 6 }}><span className="dot" style={{ background: s.color }} />{s.label}<b className="num" style={{ marginLeft: 'auto' }}>{yLog ? sci(p.y) : fy(p.y)}</b></div> : null; })}
          </div>
        )}
        {!ok && <div className="empty" style={{ height }}><p className="small">No points to plot yet.</p></div>}
      </div>
      {series.length > 1 && (
        <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>
          {series.map((s) => (
            <button key={s.id} type="button" className="chip legend-chip no-magnet" aria-pressed={!hidden.has(s.id)} style={{ opacity: hidden.has(s.id) ? 0.4 : 1, textDecoration: hidden.has(s.id) ? 'line-through' : undefined }}
              onClick={() => { const n = new Set(hidden); n.has(s.id) ? n.delete(s.id) : n.add(s.id); setHidden(n); }}>
              <span className="dot" style={{ background: s.color }} />{s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- bar chart */
export function BarChart({ data, height = 220, label, fy = (v: number) => String(+v.toPrecision(3)), yLog, refs = [], stacked }: {
  data: { label: string; values: { key: string; value: number; color: string; lo?: number; hi?: number }[] }[]; height?: number; label: string; fy?: (v: number) => string; yLog?: boolean; refs?: RefLine[]; stacked?: boolean;
}) {
  const [ref, { width }] = useMeasure<HTMLDivElement>();
  const reduce = useReducedMotion();
  const rot = data.some((d) => d.label.length * 6.2 > (width - 56) / Math.max(1, data.length) * 0.78);
  const m = { l: 48, r: 8, t: 14, b: rot ? 58 : 30 };
  const W = Math.max(0, width - m.l - m.r), H = height - m.t - m.b;
  const keys = [...new Set(data.flatMap((d) => d.values.map((v) => v.key)))];
  const maxV = Math.max(1e-12, ...data.map((d) => (stacked ? d.values.reduce((a, v) => a + v.value, 0) : Math.max(...d.values.map((v) => v.hi ?? v.value)))), ...refs.map((r) => r.y ?? 0));
  const minV = yLog ? Math.max(1e-12, Math.min(...data.flatMap((d) => d.values.map((v) => v.value)).filter((v) => v > 0)) / 2) : 0;
  const x0 = scaleBand().domain(data.map((d) => d.label)).range([0, W]).padding(0.22);
  const x1 = scaleBand().domain(stacked ? ['s'] : keys).range([0, x0.bandwidth()]).padding(0.08);
  const y = (yLog ? scaleLog().domain([minV, maxV * 1.5]) : scaleLinear().domain([0, maxV * 1.12])).range([H, 0]).clamp(true);
  return (
    <div ref={ref} style={{ height }} role="img" aria-label={label}>
      {W > 20 && <svg width={width} height={height}>
        <g transform={`translate(${m.l},${m.t})`}>
          {(yLog ? (y as any).ticks().filter((t: number) => Math.abs(Math.log10(t) - Math.round(Math.log10(t))) < 1e-9) : (y as any).ticks(4)).map((t: number) => <g key={t}><line x1={0} x2={W} y1={y(t)} y2={y(t)} stroke="var(--line)" /><text x={-8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--text-3)" className="num">{yLog ? sci(t, 1) : fy(t)}</text></g>)}
          {data.map((d, di) => {
            let acc = 0;
            return (
              <g key={`${d.label}-${di}`} transform={`translate(${x0(d.label)},0)`}>
                {d.values.map((v, i) => {
                  const bx = stacked ? 0 : x1(v.key) || 0, bw = stacked ? x0.bandwidth() : x1.bandwidth();
                  const top = stacked ? y(acc + v.value) : y(Math.max(v.value, minV)), bottom = stacked ? y(acc) : H;
                  acc += v.value;
                  return (
                    <g key={v.key + i}>
                      <motion.rect x={bx} width={bw} rx={Math.min(6, bw / 3)} fill={v.color} initial={reduce ? false : { y: H, height: 0 }}
                        animate={{ y: top, height: Math.max(0, bottom - top) }} transition={{ type: 'spring', stiffness: 160, damping: 22, delay: i * 0.03 }}>
                        <title>{`${d.label} · ${v.key}: ${fy(v.value)}`}</title>
                      </motion.rect>
                      {v.lo != null && v.hi != null && <line x1={bx + bw / 2} x2={bx + bw / 2} y1={y(Math.max(v.lo, minV))} y2={y(v.hi)} stroke="var(--text-1)" strokeWidth={1.2} />}
                    </g>
                  );
                })}
                {x0.bandwidth() < d.label.length * 6.2
                  ? <text transform={`translate(${x0.bandwidth() / 2},${H + 12}) rotate(-24)`} textAnchor="end" fontSize={10} fill="var(--text-2)">{d.label}</text>
                  : <text x={x0.bandwidth() / 2} y={H + 18} textAnchor="middle" fontSize={11} fill="var(--text-2)">{d.label}</text>}
              </g>
            );
          })}
          {refs.map((r, i) => r.y != null && <g key={i}><line x1={0} x2={W} y1={y(r.y)} y2={y(r.y)} stroke={r.color || 'var(--coral)'} strokeDasharray="5 4" /><text x={W} y={y(r.y) - 4} textAnchor="end" fontSize={11} fill={r.color || 'var(--coral)'}>{r.label}</text></g>)}
        </g>
      </svg>}
    </div>
  );
}

/* ------------------------------------------------------------ CHSH gauge */
export function ChshGauge({ S, S_lcb, S0, size = 190, label }: { S: number | null | undefined; S_lcb?: number | null; S0?: number | null; size?: number; label?: string }) {
  const reduce = useReducedMotion();
  const R = size / 2 - 14, cx = size / 2, cy = size / 2 + 4;
  const ang = (v: number) => Math.PI + (Math.max(0, Math.min(3, v)) / 3) * Math.PI;
  const pt = (v: number, r = R) => [cx + r * Math.cos(ang(v)), cy + r * Math.sin(ang(v))];
  const arc = (a: number, b: number, r = R) => { const [x0, y0] = pt(a, r), [x1, y1] = pt(b, r); return `M${x0},${y0} A${r},${r} 0 0 1 ${x1},${y1}`; };
  const T = 2 * Math.SQRT2;
  const s = S ?? 0;
  const needle = ang(s) * (180 / Math.PI) - 180;
  const ok = (S_lcb ?? s) > 2;
  return (
    <div role="img" aria-label={label || `CHSH S = ${S?.toFixed(3)}`} style={{ width: size, maxWidth: '100%' }}>
      <svg viewBox={`0 0 ${size} ${size / 2 + 34}`} width="100%">
        <defs>
          <pattern id="hatch" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="var(--coral-l)" /><line x1="0" y1="0" x2="0" y2="6" stroke="var(--coral)" strokeWidth="1.4" opacity=".5" /></pattern>
          <linearGradient id="qz" x1="0" x2="1"><stop offset="0" stopColor="var(--sky)" /><stop offset="1" stopColor="var(--mint)" /></linearGradient>
        </defs>
        <path d={arc(0, 2)} stroke="url(#hatch)" strokeWidth={14} fill="none" />
        <path d={arc(2, T)} stroke="url(#qz)" strokeWidth={14} fill="none" />
        <path d={arc(T, 3)} stroke="var(--bg-3)" strokeWidth={14} fill="none" />
        {S_lcb != null && S != null && <path d={arc(Math.min(S_lcb, s), s, R - 14)} stroke={ok ? 'var(--mint)' : 'var(--coral)'} strokeWidth={5} fill="none" opacity={0.55} strokeLinecap="round" />}
        {[2, T].map((v) => { const [x0, y0] = pt(v, R - 10), [x1, y1] = pt(v, R + 10); return <line key={v} x1={x0} y1={y0} x2={x1} y2={y1} stroke="var(--text-1)" strokeWidth={2} />; })}
        {S0 != null && (() => { const [x, y] = pt(S0, R + 12); return <rect x={x - 4} y={y - 4} width={8} height={8} transform={`rotate(45 ${x} ${y})`} fill="var(--lav)"><title>baseline S₀ = {S0.toFixed(3)}</title></rect>; })()}
        <motion.g initial={reduce ? false : { rotate: 0 }} animate={{ rotate: needle }} transition={{ type: 'spring', stiffness: 140, damping: 16 }} style={{ originX: `${cx}px`, originY: `${cy}px` }}>
          <line x1={cx} y1={cy} x2={cx - R + 18} y2={cy} stroke="var(--text-0)" strokeWidth={3} strokeLinecap="round" />
        </motion.g>
        <circle cx={cx} cy={cy} r={6} fill="var(--text-0)" />
        <text x={pt(2, R + 22)[0]} y={pt(2, R + 22)[1]} textAnchor="middle" fontSize={10} fill="var(--text-2)">2</text>
        <text x={pt(T, R + 22)[0] + 8} y={pt(T, R + 22)[1]} textAnchor="middle" fontSize={10} fill="var(--text-2)">2√2</text>
        <text x={cx} y={cy + 24} textAnchor="middle" fontSize={20} fontWeight={700} fill={ok ? 'var(--ok)' : 'var(--threat)'} fontFamily="var(--font-display)">{S != null ? `S = ${S.toFixed(3)}` : 'S = —'}</text>
      </svg>
      {S_lcb != null && <div className="xs mono muted" style={{ textAlign: 'center', marginTop: -4 }}>LCB {S_lcb.toFixed(3)} {ok ? '> 2 · certified' : '≤ 2 · not certified'}</div>}
    </div>
  );
}

/* --------------------------------------------------------------- PMF */
export function PmfChart({ n, honest, forger, sA, sV, height = 230 }: { n: number; honest: number[]; forger: number[]; sA: number; sV: number; height?: number }) {
  const [ref, { width }] = useMeasure<HTMLDivElement>();
  const m = { l: 44, r: 10, t: 12, b: 32 };
  const W = Math.max(0, width - m.l - m.r), H = height - m.t - m.b;
  const kmax = Math.min(n, Math.max(10, Math.ceil(n * 0.5)));
  const x = scaleLinear().domain([0, kmax]).range([0, W]);
  const ymax = Math.max(1e-9, ...honest.slice(0, kmax + 1), ...forger.slice(0, kmax + 1));
  const y = scaleLinear().domain([0, ymax * 1.08]).range([H, 0]);
  const bw = Math.max(1, W / (kmax + 1) * 0.9);
  const ca = Math.floor(sA * n), cv = Math.floor(sV * n);
  return (
    <div ref={ref} style={{ height }} role="img" aria-label="Honest and forger mismatch distributions with thresholds">
      {W > 20 && <svg width={width} height={height}><g transform={`translate(${m.l},${m.t})`}>
        {y.ticks(4).map((t) => <g key={t}><line x1={0} x2={W} y1={y(t)} y2={y(t)} stroke="var(--line)" /><text x={-6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={10} fill="var(--text-3)">{t.toPrecision(2)}</text></g>)}
        {honest.slice(0, kmax + 1).map((p, k) => <rect key={`h${k}`} x={x(k) - bw / 2} width={bw} y={y(p)} height={H - y(p)} fill="var(--mint)" opacity={k > ca ? 1 : 0.55}><title>{`honest P(m=${k}) = ${sci(p)}`}</title></rect>)}
        {forger.slice(0, kmax + 1).map((p, k) => <rect key={`f${k}`} x={x(k) - bw / 2} width={bw} y={y(p)} height={H - y(p)} fill="var(--coral)" opacity={k <= cv ? 1 : 0.45}><title>{`forger P(m=${k}) = ${sci(p)}`}</title></rect>)}
        {[[ca, 's_a', 'var(--ok)'], [cv, 's_v', 'var(--threat)']].map(([c, l, col]) => (
          <g key={l as string}><line x1={x(c as number)} x2={x(c as number)} y1={-4} y2={H} stroke={col as string} strokeWidth={2} strokeDasharray="4 3" />
            <text x={x(c as number) + 4} y={8} fontSize={11} fontWeight={700} fill={col as string}>{l as string} · m ≤ {c as number}</text></g>
        ))}
        {x.ticks(6).map((t) => <text key={t} x={x(t)} y={H + 16} textAnchor="middle" fontSize={10} fill="var(--text-3)">{t}</text>)}
        <text x={W / 2} y={H + 30} textAnchor="middle" fontSize={11} fill="var(--text-2)">mismatches m out of n = {n} tested positions</text>
      </g></svg>}
    </div>
  );
}

/* ------------------------------------------------------------- SPRT */
export function SprtChart({ traces, A, B, height = 220, progress = 1 }: { traces: { key: number; set: string; trace: number[][]; decision: string }[]; A: number; B: number; height?: number; progress?: number }) {
  const all = traces.flatMap((t) => t.trace);
  const maxN = Math.max(1, ...all.map((p) => p[0]));
  const series: Series[] = traces.slice(0, 8).map((t, i) => ({
    id: `${t.key}-${t.set}-${i}`, label: `key ${t.key} (${t.set})`, color: t.decision === 'reject' ? 'var(--coral)' : i % 2 ? 'var(--sky)' : 'var(--lav)', step: true, width: 1.6,
    points: t.trace.filter((p) => p[0] <= maxN * progress).map((p) => ({ x: p[0], y: p[1] })),
  }));
  return <LineChart label="SPRT log-likelihood ratio paths" series={series} height={height} xLabel="observations read" yLabel="log Λ"
    refs={[{ y: A, label: `reject A = ${A.toFixed(1)}`, color: 'var(--coral)' }, { y: B, label: `accept B = ${B.toFixed(1)}`, color: 'var(--ok)' }]} yDomain={[Math.min(B * 1.1, ...all.map((p) => p[1])), Math.max(A * 1.1, ...all.map((p) => p[1]))]} xDomain={[0, maxN]} />;
}

/* ------------------------------------------------------------- grids */
export function BitGrid({ cells, cols = 16, size = 14, label, reveal = true }: { cells: { state: 'pass' | 'fail' | 'inconclusive' | 'pending' | 'one' | 'zero'; title?: string }[]; cols?: number; size?: number; label: string; reveal?: boolean }) {
  const reduce = useReducedMotion();
  const color = { pass: 'var(--mint)', fail: 'var(--coral)', inconclusive: 'var(--peach)', pending: 'var(--bg-3)', one: 'var(--lav)', zero: 'color-mix(in srgb, var(--lav) 18%, var(--bg-3))' };
  return (
    <div role="img" aria-label={label} style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, ${size}px)`, gap: 3, maxWidth: '100%', overflow: 'hidden' }}>
      {cells.map((c, i) => (
        <motion.span key={i} title={c.title} initial={reduce || !reveal ? false : { opacity: 0, scale: 0.4 }} animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: reduce ? 0 : ((i % cols) + Math.floor(i / cols)) * 0.012, type: 'spring', stiffness: 300, damping: 20 }}
          style={{ width: size, height: size, borderRadius: 4, background: color[c.state], boxShadow: c.state === 'fail' ? '0 0 8px var(--coral)' : undefined }} />
      ))}
    </div>
  );
}

/** Canvas grid of sampled qubits: basis colour fill, mismatches ringed coral. */
export function QubitGrid({ cells, label, scan = true }: { cells: number[][][]; label: string; scan?: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [wrap, { width }] = useMeasure<HTMLDivElement>();
  const reduce = useReducedMotion();
  useEffect(() => {
    const cv = ref.current; if (!cv || !width || !cells.length) return;
    const rows = cells.length, cols = cells[0].length;
    const cs = Math.max(4, Math.floor((width - 2) / cols)), h = rows * cs + 2;
    const dpr = Math.min(2, devicePixelRatio || 1);
    cv.width = width * dpr; cv.height = h * dpr; cv.style.width = `${width}px`; cv.style.height = `${h}px`;
    const ctx = cv.getContext('2d')!; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const st = getComputedStyle(document.documentElement);
    const bc = ['--basis-x', '--basis-y', '--basis-z'].map((v) => st.getPropertyValue(v).trim());
    const coral = st.getPropertyValue('--coral').trim(), faint = st.getPropertyValue('--bg-3').trim();
    let raf = 0; const t0 = performance.now();
    const draw = (now: number) => {
      const k = reduce || !scan ? 1 : Math.min(1, (now - t0) / 1400);
      ctx.clearRect(0, 0, width, h);
      for (let i = 0; i < rows; i++) for (let j = 0; j < cols; j++) {
        const c = cells[i][j]; const x = 1 + j * cs, y = 1 + i * cs;
        const shown = j / cols <= k;
        if (!c || c[0] < 0) { ctx.fillStyle = faint; ctx.globalAlpha = 0.5; ctx.fillRect(x, y, cs - 1, cs - 1); continue; }
        ctx.globalAlpha = shown ? (c[3] ? 1 : 0.28) : 0.08;
        ctx.fillStyle = bc[c[0]] || faint;
        ctx.fillRect(x, y, cs - 1, cs - 1);
        if (shown && c[4]) { ctx.globalAlpha = 1; ctx.strokeStyle = coral; ctx.lineWidth = 2; ctx.strokeRect(x + 1, y + 1, cs - 3, cs - 3); }
        if (shown && c[2] === 1) { ctx.globalAlpha = 0.9; ctx.fillStyle = '#fff'; ctx.fillRect(x + cs / 2 - 1, y + cs / 2 - 1, 2, 2); }
      }
      ctx.globalAlpha = 1;
      if (k < 1) { const bx = k * width; const g = ctx.createLinearGradient(bx - 40, 0, bx + 4, 0); g.addColorStop(0, 'rgba(111,168,240,0)'); g.addColorStop(1, 'rgba(111,168,240,.55)'); ctx.fillStyle = g; ctx.fillRect(bx - 40, 0, 44, h); raf = requestAnimationFrame(draw); }
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [cells, width, reduce, scan]);
  return <div ref={wrap} role="img" aria-label={label}><canvas ref={ref} /></div>;
}

/* ------------------------------------------------------------- matrix */
export function MatrixView({ m, labels, colLabels, diverging = true, digits = 3, label, max: maxIn }: { m: number[][]; labels?: string[]; colLabels?: string[]; diverging?: boolean; digits?: number; label: string; max?: number }) {
  const max = maxIn ?? Math.max(1e-9, ...m.flat().map(Math.abs));
  const bg = (v: number) => {
    const a = Math.min(1, Math.abs(v) / max);
    const c = !diverging || v >= 0 ? 'var(--sky)' : 'var(--coral)';
    return `color-mix(in srgb, ${c} ${Math.round(a * 42)}%, var(--bg-3))`;
  };
  return (
    <div role="img" aria-label={label} style={{ overflowX: 'auto' }}>
      <table className="matrix"><tbody>
        {colLabels && <tr><th />{colLabels.map((c) => <th key={c}>{c}</th>)}</tr>}
        {m.map((row, i) => <tr key={i}>{labels && <th>{labels[i]}</th>}{row.map((v, j) => <td key={j} style={{ background: bg(v) }} className="num">{Number.isFinite(v) ? v.toFixed(digits) : '—'}</td>)}</tr>)}
      </tbody></table>
    </div>
  );
}

/* ------------------------------------------------------------- heatmap */
export function Heatmap({ rows, cols, values, fmt = (v: number) => (v * 100).toFixed(0) + '%', label, color = 'var(--mint)', low = 'var(--bg-3)', titleOf }: {
  rows: string[]; cols: string[]; values: (number | null)[][]; fmt?: (v: number) => string; label: string; color?: string; low?: string; titleOf?: (i: number, j: number) => string;
}) {
  const reduce = useReducedMotion();
  return (
    <div role="img" aria-label={label} style={{ overflowX: 'auto' }}>
      <table className="matrix heat"><tbody>
        <tr><th />{cols.map((c, j) => <th key={`${c}-${j}`}>{c}</th>)}</tr>
        {rows.map((r, i) => (
          <tr key={`${r}-${i}`}><th style={{ textAlign: 'left', whiteSpace: 'nowrap' }}>{r}</th>
            {cols.map((c, j) => { const v = values[i]?.[j]; return (
              <motion.td key={`${c}-${j}`} className="num" title={titleOf?.(i, j)} initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: (i + j) * 0.02 }}
                style={{ background: v == null ? 'transparent' : `color-mix(in srgb, ${color} ${Math.round(v * 70)}%, ${low})`, color: v != null && v > 0.6 ? '#fff' : undefined }}>
                {v == null ? '·' : fmt(v)}
              </motion.td>); })}
          </tr>
        ))}
      </tbody></table>
    </div>
  );
}

/* ------------------------------------------------------------- radar */
export function Radar({ axes, current, baseline, size = 200, label }: { axes: string[]; current: number[]; baseline?: number[]; size?: number; label: string }) {
  const c = size / 2, R = size / 2 - 26;
  const mx = Math.max(1e-9, ...current, ...(baseline || []));
  const pts = (v: number[]) => v.map((x, i) => { const a = -Math.PI / 2 + (i / axes.length) * Math.PI * 2; const r = (x / mx) * R; return `${c + r * Math.cos(a)},${c + r * Math.sin(a)}`; }).join(' ');
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width="100%" style={{ maxWidth: size }} role="img" aria-label={label}>
      {[0.25, 0.5, 0.75, 1].map((k) => <polygon key={k} points={pts(axes.map(() => k * mx))} fill="none" stroke="var(--line)" />)}
      {axes.map((a, i) => { const ang = -Math.PI / 2 + (i / axes.length) * Math.PI * 2; return <g key={a}><line x1={c} y1={c} x2={c + R * Math.cos(ang)} y2={c + R * Math.sin(ang)} stroke="var(--line)" /><text x={c + (R + 14) * Math.cos(ang)} y={c + (R + 14) * Math.sin(ang)} textAnchor="middle" dy="0.32em" fontSize={11} fill="var(--text-2)">{a}</text></g>; })}
      {baseline && <polygon points={pts(baseline)} fill="none" stroke="var(--mint)" strokeDasharray="4 3" strokeWidth={1.5} />}
      <motion.polygon points={pts(current)} fill="color-mix(in srgb, var(--lav) 25%, transparent)" stroke="var(--lav)" strokeWidth={2} initial={false} animate={{ points: pts(current) }} />
    </svg>
  );
}

export function Legend({ items }: { items: { color: string; label: ReactNode; dashed?: boolean }[] }) {
  return <div className="row wrap xs muted" style={{ gap: 12 }}>{items.map((it, i) => <span key={i} className="row" style={{ gap: 6 }}><span style={{ width: 14, height: 3, borderRadius: 2, background: it.color, opacity: it.dashed ? 0.6 : 1 }} />{it.label}</span>)}</div>;
}
