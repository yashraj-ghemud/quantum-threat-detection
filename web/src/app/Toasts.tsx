import { useEffect } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Info, X, ShieldAlert } from 'lucide-react';
import { useUi, type Toast } from '@/state/ui';

const ICON = { ok: CheckCircle2, threat: ShieldAlert, warn: AlertTriangle, info: Info };
const COLOR = { ok: 'var(--ok)', threat: 'var(--threat)', warn: 'var(--warn)', info: 'var(--sky)' };

function ToastView({ t }: { t: Toast }) {
  const dismiss = useUi((s) => s.dismiss);
  const nav = useNavigate();
  useEffect(() => { if (t.sticky) return; const id = setTimeout(() => dismiss(t.id), 6000); return () => clearTimeout(id); }, [t, dismiss]);
  const Icon = ICON[t.tone];
  return (
    <motion.div layout className="toast" role={t.tone === 'threat' ? 'alert' : 'status'} style={{ color: COLOR[t.tone] }}
      initial={{ opacity: 0, x: 40, scale: 0.96 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, x: 60 }}
      drag="x" dragConstraints={{ left: 0, right: 0 }} onDragEnd={(_, i) => { if (Math.abs(i.offset.x) > 80) dismiss(t.id); }}>
      <span className="t-icon" style={{ background: `color-mix(in srgb, ${COLOR[t.tone]} 16%, transparent)` }}><Icon /></span>
      <b style={{ color: 'var(--text-0)' }}>{t.title}</b>
      <button className="btn ghost icon sm" aria-label="Dismiss" onClick={() => dismiss(t.id)} style={{ width: 24, minHeight: 24 }}><X style={{ width: 14 }} /></button>
      {t.body && <p>{t.body.length > 180 ? t.body.slice(0, 177) + '…' : t.body}</p>}
      {t.action && <div className="t-actions"><button className="btn sm" onClick={() => { if (t.action?.href) nav(t.action.href); t.action?.run?.(); dismiss(t.id); }}>{t.action.label}</button></div>}
      {!t.sticky && <motion.i className="t-bar" initial={{ scaleX: 1 }} animate={{ scaleX: 0 }} transition={{ duration: 6, ease: 'linear' }} />}
    </motion.div>
  );
}
export function Toasts() {
  const toasts = useUi((s) => s.toasts);
  return <div className="toasts" aria-live="polite"><AnimatePresence initial={false}>{toasts.slice(-4).map((t) => <ToastView key={t.id} t={t} />)}</AnimatePresence></div>;
}
