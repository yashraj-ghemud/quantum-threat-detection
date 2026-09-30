import { Component, type ReactNode } from 'react';
import { useRouteError, Link } from 'react-router-dom';

export class PageErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error) { console.error(error); }
  render() {
    if (!this.state.error) return this.props.children;
    return <Decoherence error={this.state.error} retry={() => this.setState({ error: null })} />;
  }
}
function Decoherence({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div className="panel" style={{ maxWidth: 640, margin: '40px auto' }}>
      <div className="kicker" style={{ color: 'var(--coral)' }}>Decoherence</div>
      <h2 style={{ margin: '8px 0 10px' }}>This view collapsed unexpectedly</h2>
      <p className="muted">{error.message}</p>
      <div className="row">
        {retry && <button className="btn primary" onClick={retry}>Retry</button>}
        <button className="btn" onClick={() => navigator.clipboard?.writeText(`${error.name}: ${error.message}\n${error.stack || ''}`)}>Copy details</button>
        <Link className="btn ghost" to="/">Overview</Link>
      </div>
    </div>
  );
}
export function RouteError() {
  const e = useRouteError() as Error;
  return <div style={{ padding: 24 }}><Decoherence error={e instanceof Error ? e : new Error(String(e))} retry={() => location.reload()} /></div>;
}
