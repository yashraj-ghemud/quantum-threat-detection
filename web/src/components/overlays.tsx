import { useEffect, useRef, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { X } from 'lucide-react';

function useEsc(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    addEventListener('keydown', h);
    return () => removeEventListener('keydown', h);
  }, [open, onClose]);
}
function useFocusTrap(open: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const el = ref.current;
    const first = el?.querySelector<HTMLElement>('input, button, textarea, select, [tabindex]:not([tabindex="-1"])');
    setTimeout(() => (first || el)?.focus(), 30);
    const h = (e: KeyboardEvent) => {
      if (e.key !== 'Tab' || !el) return;
      const f = [...el.querySelectorAll<HTMLElement>('a, button, input, textarea, select, [tabindex]:not([tabindex="-1"])')].filter((x) => !x.hasAttribute('disabled'));
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    };
    addEventListener('keydown', h);
    return () => { removeEventListener('keydown', h); prev?.focus?.(); };
  }, [open]);
  return ref;
}

export function Drawer({ open, onClose, title, children, width }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: number }) {
  useEsc(open, onClose);
  const ref = useFocusTrap(open);
  const mobile = typeof window !== 'undefined' && innerWidth < 768;
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="scrim" style={{ zIndex: 'var(--z-drawer)' as any }} onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.aside ref={ref} tabIndex={-1} className="drawer" role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : 'Details'}
            style={width && !mobile ? { width: `min(${width}px, 100vw)` } : undefined}
            initial={mobile ? { y: '100%' } : { x: '100%' }} animate={mobile ? { y: 0 } : { x: 0 }} exit={mobile ? { y: '100%' } : { x: '100%' }}
            transition={{ type: 'spring', stiffness: 260, damping: 30 }}
            drag={mobile ? 'y' : false} dragConstraints={{ top: 0, bottom: 0 }} dragElastic={{ top: 0, bottom: 0.6 }}
            onDragEnd={(_, i) => { if (i.offset.y > 120 || i.velocity.y > 600) onClose(); }}>
            <div className="drawer-head"><h3 style={{ fontSize: 18 }}>{title}</h3><button className="btn ghost icon sm" aria-label="Close" onClick={onClose}><X /></button></div>
            <div className="drawer-body">{children}</div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

export function Modal({ open, onClose, children, label }: { open: boolean; onClose: () => void; children: ReactNode; label: string }) {
  useEsc(open, onClose);
  const ref = useFocusTrap(open);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.div ref={ref} tabIndex={-1} className="modal" role="dialog" aria-modal="true" aria-label={label}
            initial={{ opacity: 0, scale: 0.96, filter: 'blur(6px)' }} animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }} exit={{ opacity: 0, scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}>
            {children}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

export function Confirm({ open, onClose, onConfirm, title, body, confirmLabel = 'Confirm', danger }: { open: boolean; onClose: () => void; onConfirm: () => void; title: string; body: ReactNode; confirmLabel?: string; danger?: boolean }) {
  return (
    <Modal open={open} onClose={onClose} label={title}>
      <div style={{ padding: 24 }} className="stack">
        <h3>{title}</h3>
        <div className="muted">{body}</div>
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className={`btn ${danger ? 'danger' : 'primary'}`} onClick={() => { onConfirm(); onClose(); }}>{confirmLabel}</button>
        </div>
      </div>
    </Modal>
  );
}
