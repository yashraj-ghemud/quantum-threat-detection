import { forwardRef, useId, useState, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { motion } from 'motion/react';
import { AlertTriangle, Check, Info, ShieldAlert, ShieldCheck, X, Copy } from 'lucide-react';
import type { Severity, Verdict } from '@/api/types';
import { verdictTone, sevColor } from '@/lib/color';
import { explain } from '@/state/ui';
import { shortHash } from '@/lib/format';
import { toast } from '@/state/ui';
import { friendly } from '@/api/client';

type BtnVariant = 'default' | 'primary' | 'brand' | 'danger' | 'ok' | 'ghost';
interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> { variant?: BtnVariant; size?: 'sm' | 'md' | 'lg'; icon?: ReactNode; loading?: boolean; iconOnly?: boolean }
export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button({ variant = 'default', size = 'md', icon, loading, iconOnly, className = '', children, disabled, ...rest }, ref) {
  const cls = ['btn', variant !== 'default' ? variant : '', size !== 'md' ? size : '', iconOnly ? 'icon' : '', className].filter(Boolean).join(' ');
  return (
    <button ref={ref} className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <span className="spin" aria-hidden /> : icon}
      {!iconOnly && children}
    </button>
  );
});

export function Chip({ tone, children, mono, title, className = '' }: { tone?: 'ok' | 'threat' | 'warn' | 'info' | 'lav' | 'gold'; children: ReactNode; mono?: boolean; title?: string; className?: string }) {
  return <span className={`chip ${tone || ''} ${mono ? 'mono' : ''} ${className}`} title={title}>{children}</span>;
}

export function VerdictBadge({ verdict, size }: { verdict: Verdict | string | null | undefined; size?: 'lg' }) {
  const tone = verdictTone(verdict);
  const Icon = verdict === 'ACCEPTED' ? Check : verdict === 'CERTIFIED' ? ShieldCheck : verdict === 'COMPROMISED' ? ShieldAlert : verdict === 'REJECTED' ? X : Info;
  return <span className={`verdict ${tone} ${size || ''}`}><Icon aria-hidden />{verdict || '—'}</span>;
}

export function SeverityPill({ level, compact }: { level: Severity | string | null | undefined; compact?: boolean }) {
  const l = (level || 'NONE') as Severity;
  const color = sevColor(l);
  return (
    <span className="chip" style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)`, borderColor: 'transparent' }}>
      {l === 'CRITICAL' || l === 'HIGH' ? <AlertTriangle aria-hidden /> : <span className="dot" style={{ background: color }} />}
      {compact ? l[0] + l.slice(1).toLowerCase() : l}
    </span>
  );
}

export function Segmented<T extends string | number>({ options, value, onChange, label, block, size }: {
  options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[]; value: T; onChange: (v: T) => void; label: string; block?: boolean; size?: 'sm';
}) {
  const id = useId();
  return (
    <div className={`seg ${block ? 'block' : ''}`} role="group" aria-label={label} style={size === 'sm' ? { fontSize: 12 } : undefined}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" aria-pressed={o.value === value} disabled={o.disabled} title={o.title} onClick={() => onChange(o.value)}>
          {o.value === value && <motion.span layoutId={`seg-${id}`} className="seg-pill" transition={{ type: 'spring', stiffness: 520, damping: 34 }} />}
          <span style={{ position: 'relative', zIndex: 1 }}>{o.label}</span>
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({ items, value, onChange, label }: { items: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void; label: string }) {
  const id = useId();
  return (
    <div className="tabs" role="tablist" aria-label={label} style={{ position: 'relative', isolation: 'isolate' }}>
      {items.map((it) => (
        <button key={it.value} role="tab" type="button" aria-selected={it.value === value} onClick={() => onChange(it.value)}>
          {it.value === value && <motion.span layoutId={`tab-${id}`} className="tab-pill" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
          <span>{it.label}</span>
        </button>
      ))}
    </div>
  );
}

export function Slider({ label, value, min, max, step = 0.01, onChange, format, hint, tone, disabled }: {
  label: ReactNode; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; format?: (v: number) => string; hint?: ReactNode; tone?: 'threat'; disabled?: boolean;
}) {
  const id = useId();
  const fill = ((value - min) / (max - min || 1)) * 100;
  return (
    <div className="slider">
      <div className="slider-head"><label className="label" htmlFor={id}>{label}</label><span className="val">{format ? format(value) : value}</span></div>
      <input id={id} className={`range ${tone || ''}`} type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))} style={{ ['--fill' as string]: `${fill}%` }} />
      {hint && <div className="xs muted">{hint}</div>}
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <button type="button" role="switch" aria-checked={checked} className="toggle" onClick={() => onChange(!checked)} style={{ background: 'none', border: 0, padding: 0 }}>
      <span className="track"><motion.span className="knob" animate={{ x: checked ? 18 : 0 }} transition={{ type: 'spring', stiffness: 520, damping: 34 }} /></span>
      <span>{label}</span>
    </button>
  );
}

export function InfoButton({ topic, label = 'Explain' }: { topic: string; label?: string }) {
  return (
    <button type="button" className="btn ghost icon sm no-magnet" aria-label={`${label}: ${topic}`} title="Explain" onClick={() => explain(topic)} style={{ width: 26, minHeight: 26, color: 'var(--text-3)' }}>
      <Info style={{ width: 15, height: 15 }} />
    </button>
  );
}

export function Panel({ title, kicker, actions, explainTopic, children, className = '', tilt, flush, tight, id, style, reveal = true }: {
  title?: ReactNode; kicker?: ReactNode; actions?: ReactNode; explainTopic?: string; children?: ReactNode; className?: string; tilt?: boolean; flush?: boolean; tight?: boolean; id?: string; style?: React.CSSProperties; reveal?: boolean;
}) {
  return (
    <section id={id} className={`panel ${tilt ? 'qv-tilt' : ''} ${flush ? 'flush' : ''} ${tight ? 'tight' : ''} ${className}`} style={style} data-reveal={reveal ? '' : undefined}>
      {(title || kicker || actions) && (
        <header className="panel-head" style={flush ? { padding: '18px 20px 0' } : undefined}>
          <div className="grow">
            {kicker && <span className="kicker">{kicker}</span>}
            {title && <h3 className="row" style={{ gap: 4 }}>{title}{explainTopic && <InfoButton topic={explainTopic} />}</h3>}
          </div>
          {actions && <div className="row wrap" style={{ justifyContent: 'flex-end' }}>{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function KeyValue({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return <dl className="kv">{rows.map(([k, v], i) => <div key={i} style={{ display: 'contents' }}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>;
}

export function HashChip({ hash, head = 8, tail = 6, label }: { hash: string | null | undefined; head?: number; tail?: number; label?: string }) {
  if (!hash) return <span className="faint">—</span>;
  return (
    <button type="button" className="hash no-magnet" title={hash} aria-label={`${label || 'hash'} ${hash}, copy`}
      onClick={() => { navigator.clipboard?.writeText(hash).then(() => toast({ tone: 'info', title: 'Copied to clipboard', body: shortHash(hash, 12, 8) })).catch(() => {}); }}>
      {shortHash(hash, head, tail)} <Copy style={{ width: 11, height: 11, opacity: 0.6 }} aria-hidden />
    </button>
  );
}

export function Empty({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return <div className="empty"><div className="orb" aria-hidden /><h4>{title}</h4>{body && <p>{body}</p>}{action}</div>;
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const [open, setOpen] = useState(false);
  const e = error as any;
  return (
    <div className="error-box" role="alert">
      <div className="row between wrap"><b>{friendly(error)}</b>{retry && <Button size="sm" onClick={retry}>Retry</Button>}</div>
      {e?.code && <div className="xs mono" style={{ marginTop: 6, opacity: 0.8 }}>{e.code}{e.requestId ? ` · request ${e.requestId}` : ''} <button className="btn ghost sm no-magnet" style={{ minHeight: 20, padding: '0 6px' }} onClick={() => setOpen(!open)}>{open ? 'hide' : 'details'}</button></div>}
      {open && <pre className="json" style={{ marginTop: 8 }}>{JSON.stringify(e?.detail ?? {}, null, 2)}</pre>}
    </div>
  );
}

export const Skeleton = ({ h = 120, w = '100%', r }: { h?: number | string; w?: number | string; r?: number }) =>
  <div className="skeleton" style={{ height: h, width: w, borderRadius: r }} aria-hidden />;

export function Progress({ value, label }: { value: number; label?: string }) {
  return <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)} aria-label={label}><i style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} /></div>;
}

export function Stat({ label, value, sub, spark, explainTopic, tone, className = '' }: { label: ReactNode; value: ReactNode; sub?: ReactNode; spark?: ReactNode; explainTopic?: string; tone?: string; className?: string }) {
  return (
    <div className={`stat qv-tilt ${className}`} data-reveal="">
      <div className="s-label">{label}{explainTopic && <InfoButton topic={explainTopic} />}</div>
      <div className="s-value" style={tone ? { color: tone } : undefined}>{value}</div>
      {sub && <div className="s-sub">{sub}</div>}
      {spark && <div className="s-spark">{spark}</div>}
    </div>
  );
}

export function NodeAvatar({ id, size = 26 }: { id: string; size?: number }) {
  const color = `var(--${['alice', 'diana', 'bob', 'charlie', 'erin'].includes(id) ? id : id === 'eve' ? 'threat' : id === 'mallory' ? 'mallory' : 'quantum'})`;
  return (
    <span aria-hidden style={{ width: size, height: size, borderRadius: '50%', display: 'inline-grid', placeItems: 'center', flex: 'none',
      background: `radial-gradient(circle at 35% 30%, #fff8, ${color} 70%)`, color: '#fff', font: `700 ${Math.round(size * 0.46)}px var(--font-display)`,
      boxShadow: `0 6px 14px -6px ${color}` }}>{id[0]?.toUpperCase()}</span>
  );
}
