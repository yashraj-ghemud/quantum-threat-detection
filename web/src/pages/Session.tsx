import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Copy } from 'lucide-react';
import { ep, qk } from '@/api/endpoints';
import { Button, Chip, ErrorState, Skeleton } from '@/components/ui';
import { ReportView } from '@/components/reports';
import { BreakIt } from '@/components/breakit';
import { toast } from '@/state/ui';
import { clock } from '@/lib/format';

export default function Session() {
  const { id = '' } = useParams();
  const q = useQuery({ queryKey: qk.session(id), queryFn: () => ep.session(id), staleTime: Infinity });
  if (q.isLoading) return <Skeleton h={500} />;
  if (q.error || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const r = q.data;
  return (
    <div className="stack">
      <header className="page-head"><div><span className="kicker">{r.kind === 'signature' ? 'Signature session' : 'Key distribution'} · {r.origin.toLowerCase()} · {clock(r.created_at)}</span>
        <h1>{r.kind === 'signature' ? (r as any).envelope?.message?.slice(0, 60) || 'Signature' : `${(r as any).signer_id} → ${(r as any).recipients?.join(', ')}`}</h1>
        {r.injected_attack && <div className="row" style={{ marginTop: 8 }}><Chip tone="threat">ground truth: injected {r.injected_attack.attack_id}</Chip><Link to={`/attack-lab?attack=${r.injected_attack.attack_id}`}>replay in the Attack Lab →</Link></div>}</div>
        <Button icon={<Copy />} onClick={() => { navigator.clipboard?.writeText(location.href); toast({ tone: 'info', title: 'Link copied' }); }}>Copy link</Button>
      </header>
      {r.kind === 'signature' && r.verdict === 'ACCEPTED' && !r.injected_attack && <BreakIt report={r as any} />}
      <ReportView report={r} />
    </div>
  );
}
