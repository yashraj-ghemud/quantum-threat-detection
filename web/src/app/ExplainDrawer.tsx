import { Link } from 'react-router-dom';
import { Drawer } from '@/components/overlays';
import { Formula } from '@/components/Formula';
import { EXPLAIN } from '@/lib/explanations';
import { useUi } from '@/state/ui';

export function ExplainDrawer() {
  const topic = useUi((s) => s.explain);
  const set = useUi((s) => s.set);
  const e = topic ? EXPLAIN[topic] : null;
  return (
    <Drawer open={!!topic} onClose={() => set({ explain: null })} title={e?.title || 'Explain'}>
      {e ? (
        <div className="stack explain">
          <section><div className="kicker">What it is</div><p>{e.what}</p></section>
          <section><div className="kicker">How we compute it</div><p>{e.how}</p>{e.tex && <Formula tex={e.tex} display />}</section>
          <section><div className="kicker">Why it matters for security</div><p>{e.why}</p></section>
          {e.limits && <section><div className="kicker">Limits</div><p className="muted">{e.limits}</p></section>}
          {e.method && <Link to={`/method#${e.method}`} onClick={() => set({ explain: null })}>Go deeper in the Method →</Link>}
        </div>
      ) : <p className="muted">No explanation for “{topic}”.</p>}
    </Drawer>
  );
}
