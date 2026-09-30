import { useEffect, useRef } from 'react';
import 'katex/dist/katex.min.css';

let katexP: Promise<typeof import('katex')> | null = null;
export function Formula({ tex, display }: { tex: string; display?: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    katexP = katexP || import('katex');
    let alive = true;
    katexP.then((k) => { if (alive && ref.current) (k.default || (k as any)).render(tex, ref.current, { displayMode: !!display, throwOnError: false }); });
    return () => { alive = false; };
  }, [tex, display]);
  return <span ref={ref} className={display ? 'formula-block' : 'formula'} style={display ? { display: 'block', overflowX: 'auto', padding: '6px 0' } : undefined}>{tex}</span>;
}
