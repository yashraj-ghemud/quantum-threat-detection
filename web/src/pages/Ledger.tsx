import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'motion/react';
import { ShieldCheck, ShieldAlert, Hammer, Undo2, ScanLine, FileJson, CheckCircle2, XCircle } from 'lucide-react';
import type { LedgerTx, VerifyResult } from '@/api/types';
import { ep, qk } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { toast } from '@/state/ui';
import { useScene } from '@/state/live';
import { Button, Chip, HashChip, KeyValue, Panel, Stat, InfoButton, ErrorState, Skeleton } from '@/components/ui';
import { CountUp, ScrambleText } from '@/components/motion';
import { Confirm, Drawer } from '@/components/overlays';
import { JsonViewer } from '@/components/JsonViewer';
import { SceneCanvas } from '@/three/common';
import { ChainScene } from '@/three/ChainScene';
import { ago, clock, int, ms, shortHash } from '@/lib/format';

const hexToBytes = (h: string) => new Uint8Array(h.match(/../g)!.map((x) => parseInt(x, 16)));
async function sha(bytes: Uint8Array) { const d = await crypto.subtle.digest('SHA-256', bytes as unknown as ArrayBuffer); return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join(''); }
/** Re-hashes an inclusion proof in the browser (independent of the server). */
async function checkProof(leaf: string, proof: { hash: string; side: string }[], root: string) {
  let h = leaf; const steps: string[] = [];
  for (const p of proof) { const a = p.side === 'left' ? p.hash + h : h + p.hash; h = await sha(hexToBytes(a)); steps.push(h); }
  return { ok: h === root, steps };
}

export default function Ledger() {
  const qc = useQueryClient();
  const summary = useQuery({ queryKey: qk.ledgerSummary, queryFn: ep.ledgerSummary, refetchInterval: 10_000 });
  const blocks = useQuery({ queryKey: qk.blocks, queryFn: () => ep.blocks(undefined, 40), refetchInterval: 10_000 });
  const [sel, setSel] = useState<number | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [sweepKey, setSweepKey] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [tx, setTx] = useState<string | null>(null);
  const S = summary.data;
  const selected = sel ?? blocks.data?.[0]?.height ?? null;
  const block = useQuery({ queryKey: qk.block(selected ?? -1), queryFn: () => ep.block(selected!), enabled: selected != null });
  const tamperedFrom = verify && !verify.valid ? verify.first_invalid_height : null;
  useEffect(() => useScene.subscribe((st) => { const e = st.events.at(-1); if (e?.kind === 'block') { qc.invalidateQueries({ queryKey: ['ledger'] }); } }), [qc]);

  const runVerify = async () => {
    setBusy('verify'); setSweepKey((k) => k + 1);
    try { const r = await ep.verifyLedger(); await new Promise((res) => setTimeout(res, 1400)); setVerify(r); toast({ tone: r.valid ? 'ok' : 'threat', title: r.valid ? `Chain valid · ${r.checked_blocks} blocks, ${int(r.checked_txs)} transactions` : `Chain INVALID from block #${r.first_invalid_height}`, body: r.valid ? undefined : `${r.downstream_blocks} downstream blocks no longer anchor to a valid history.` }); qc.invalidateQueries({ queryKey: ['ledger'] }); }
    catch (e) { toast({ tone: 'warn', title: friendly(e) }); } finally { setBusy(null); }
  };
  const tamper = async () => {
    setBusy('tamper');
    try { const r = await ep.tamper(); toast({ tone: 'warn', title: `Rewrote tx ${shortHash(r.tx_id)} in block #${r.height}`, body: `${r.field}: ${JSON.stringify(r.before)} → ${JSON.stringify(r.after)}` }); setSel(r.height); await runVerify(); }
    catch (e) { toast({ tone: 'warn', title: friendly(e) }); setBusy(null); }
  };
  const revert = async () => {
    setBusy('revert');
    try { const r = await ep.revertTamper(); toast({ tone: 'ok', title: `Reverted ${r.reverted.length} tampered transaction(s)` }); await runVerify(); }
    catch (e) { toast({ tone: 'warn', title: friendly(e) }); setBusy(null); }
  };

  if (summary.error) return <ErrorState error={summary.error} retry={() => summary.refetch()} />;
  return (
    <div className="stack">
      <header className="page-head">
        <div><span className="kicker">Hash chain · Merkle trees · tamper evidence</span><h1>Audit ledger</h1>
          <p>Every distribution, signature, incident and response is appended as a transaction; blocks commit to the previous hash and a Merkle root. Rewrite one stored row and verification pinpoints it.</p></div>
        <div className="row wrap">
          <Button variant="primary" icon={<ScanLine />} loading={busy === 'verify'} onClick={runVerify}>Verify integrity</Button>
          {S?.tamper_demo_enabled && <Button variant="danger" icon={<Hammer />} loading={busy === 'tamper'} onClick={() => setConfirm(true)}>Tamper demo</Button>}
          {S?.tampered?.length ? <Button icon={<Undo2 />} loading={busy === 'revert'} onClick={revert}>Revert tamper</Button> : null}
        </div>
      </header>

      <div className="grid g4">
        <Stat label="Height" explainTopic="ledger" value={<CountUp value={S?.height ?? null} />} sub={S ? `${int(S.pending)} pending tx` : ''} />
        <Stat label="Transactions" value={<CountUp value={S?.tx_total ?? null} format={(v) => int(v)} />} sub="sealed + pending" />
        <Stat label="Head hash" value={<span className="mono" style={{ fontSize: 18 }}>{S ? <ScrambleText text={shortHash(S.head_hash, 8, 6)} /> : '—'}</span>} sub={S ? <HashChip hash={S.head_hash} head={4} tail={4} /> : ''} />
        <Stat label="Integrity" value={verify ? (verify.valid ? <span className="ok-text row" style={{ gap: 8 }}><ShieldCheck />valid</span> : <span className="threat-text row" style={{ gap: 8 }}><ShieldAlert />broken</span>) : S?.last_verification ? (S.last_verification.valid ? 'valid' : 'broken') : 'not checked'}
          sub={verify ? `checked in ${ms(verify.duration_ms)}` : S?.last_verification ? `last check ${ago(S.last_verification.at)}` : 'run Verify'} />
      </div>

      <AnimatePresence>{verify && !verify.valid && (
        <motion.div className="banner threat" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
          <ShieldAlert /><span className="grow"><b>Tamper detected in block #{verify.first_invalid_height}.</b> {verify.issues.map((i) => `${i.kind}${i.tx_id ? ` (tx ${shortHash(i.tx_id)})` : ''}`).join(' · ')} — {verify.downstream_blocks} downstream block(s) affected.</span>
        </motion.div>)}</AnimatePresence>

      <Panel flush reveal={false} className="chain-panel">
        {blocks.data ? (
          <SceneCanvas label="Ledger chain" camera={{ position: [0, 1.8, 6.4], fov: 50 }} style={{ height: 360 }} fallback={<ChainCards blocks={blocks.data} sel={selected} onSelect={setSel} tamperedFrom={tamperedFrom} />}>
            <ChainScene blocks={blocks.data} tamperedFrom={tamperedFrom} downstream={verify?.downstream_blocks ?? 0} selected={selected} onSelect={setSel} sweepKey={sweepKey} />
          </SceneCanvas>
        ) : <Skeleton h={360} />}
        <div className="chain-cards-mobile"><ChainCards blocks={blocks.data || []} sel={selected} onSelect={setSel} tamperedFrom={tamperedFrom} /></div>
      </Panel>

      <div className="ledger-grid">
        <Panel title={selected != null ? `Block #${selected}` : 'Block'} kicker="Header" tight>
          {block.data ? (
            <div className="stack">
              <KeyValue rows={[['hash', <HashChip key="h" hash={block.data.block.hash} />], ['previous', <HashChip key="p" hash={block.data.block.prev_hash} />], ['Merkle root', <HashChip key="m" hash={block.data.block.merkle_root} />],
                ['sealed', clock(block.data.block.timestamp)], ['transactions', block.data.block.tx_count]]} />
              <div className="stack" style={{ ['--gap' as string]: '6px' }}>
                {block.data.txs.map((t) => (
                  <button key={t.id} className={`tx-row ${t.valid ? '' : 'bad'}`} onClick={() => setTx(t.id)}>
                    {t.valid ? <CheckCircle2 style={{ color: 'var(--ok)' }} /> : <XCircle style={{ color: 'var(--threat)' }} />}
                    <span className="grow"><b>{t.kind.replace(/_/g, ' ').toLowerCase()}</b><span className="xs muted mono">{shortHash(t.payload_hash, 8, 6)} · {clock(t.created_at)}</span></span><FileJson />
                  </button>))}
              </div>
            </div>) : <Skeleton h={240} />}
        </Panel>
        <Panel title="Merkle tree" kicker="Leaves = SHA-256 of canonical transaction JSON" explainTopic="merkle" tight>
          {block.data ? <MerkleTree levels={block.data.merkle_levels} txs={block.data.txs} highlight={tx} /> : <Skeleton h={240} />}
        </Panel>
      </div>

      <Confirm open={confirm} onClose={() => setConfirm(false)} onConfirm={tamper} danger confirmLabel="Rewrite a stored transaction" title="Tamper demo"
        body={<>This rewrites one stored transaction <b>directly in the database</b>, bypassing the ledger, the way an attacker with disk access would. Verification then runs automatically. You can revert afterwards.</>} />
      <TxDrawer id={tx} onClose={() => setTx(null)} />
    </div>
  );
}

function ChainCards({ blocks, sel, onSelect, tamperedFrom }: { blocks: { height: number; hash: string; tx_count: number }[]; sel: number | null; onSelect: (h: number) => void; tamperedFrom: number | null }) {
  return (
    <div className="chain-cards">
      {[...blocks].sort((a, b) => a.height - b.height).map((b) => (
        <button key={b.height} className={`chain-card ${sel === b.height ? 'on' : ''} ${tamperedFrom != null && b.height === tamperedFrom ? 'bad' : ''}`} onClick={() => onSelect(b.height)}>
          <b>#{b.height}</b><span className="mono xs">{shortHash(b.hash, 5, 3)}</span><span className="xs muted">{b.tx_count} tx</span>
        </button>))}
    </div>
  );
}

function MerkleTree({ levels, txs, highlight }: { levels: string[][]; txs: { id: string; payload_hash: string }[]; highlight: string | null }) {
  const W = 640, rows = levels.length, H = Math.max(160, rows * 70);
  const hiIdx = highlight ? txs.findIndex((t) => t.id === highlight) : -1;
  const path = useMemo(() => { const s = new Set<string>(); if (hiIdx < 0) return s; let i = hiIdx; levels.forEach((_, l) => { s.add(`${l}-${i}`); i = Math.floor(i / 2); }); return s; }, [hiIdx, levels]);
  const xy = (l: number, i: number) => { const n = levels[l].length; return [((i + 0.5) / n) * W, H - 30 - l * ((H - 60) / Math.max(1, rows - 1))]; };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Merkle tree of the block">
      {levels.map((lv, l) => l > 0 && lv.map((_, i) => [2 * i, 2 * i + 1].filter((c) => c < levels[l - 1].length || c === 2 * i).map((c) => {
        const cc = Math.min(c, levels[l - 1].length - 1);
        const [x1, y1] = xy(l, i), [x2, y2] = xy(l - 1, cc); const on = path.has(`${l}-${i}`) && path.has(`${l - 1}-${cc}`);
        return <motion.line key={`${l}-${i}-${c}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke={on ? 'var(--lav)' : 'var(--line-strong)'} strokeWidth={on ? 3 : 1.4} initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: l * 0.15 }} />;
      })))}
      {levels.map((lv, l) => lv.map((h, i) => { const [x, y] = xy(l, i); const on = path.has(`${l}-${i}`); const root = l === rows - 1;
        return <g key={`${l}-${i}`}><rect x={x - 38} y={y - 12} width={76} height={24} rx={8} fill={root ? 'var(--lav)' : on ? 'var(--lav-l)' : 'var(--bg-2)'} stroke={on || root ? 'var(--lav)' : 'var(--line-strong)'} />
          <text x={x} y={y + 4} textAnchor="middle" fontSize={10.5} fontFamily="var(--font-mono)" fill={root ? '#fff' : 'var(--text-1)'}>{h.slice(0, 8)}</text><title>{h}</title></g>; }))}
      <text x={6} y={H - 6} fontSize={10} fill="var(--text-3)">leaves (transactions)</text><text x={6} y={16} fontSize={10} fill="var(--text-3)">root</text>
    </svg>
  );
}

function TxDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const q = useQuery({ queryKey: ['ledger', 'tx', id], queryFn: () => ep.tx(id!), enabled: !!id });
  const [check, setCheck] = useState<{ ok: boolean; steps: string[] } | null>(null);
  useEffect(() => { setCheck(null); }, [id]);
  const t = q.data as (LedgerTx & { proof?: { hash: string; side: string }[] }) | undefined;
  return (
    <Drawer open={!!id} onClose={onClose} title="Ledger transaction" width={680}>
      {!t ? <Skeleton h={300} /> : (
        <div className="stack">
          <KeyValue rows={[['kind', t.kind], ['block', t.block_height ?? 'pending'], ['index', t.idx ?? '—'], ['leaf (payload hash)', <HashChip key="l" hash={t.payload_hash} />], ['Merkle root', <HashChip key="r" hash={t.merkle_root} />], ['time', clock(t.created_at)]]} />
          {t.proof && t.payload_hash && t.merkle_root && (
            <div className="panel tight">
              <div className="row between wrap"><b className="row" style={{ gap: 6 }}>Inclusion proof · {t.proof.length} hashes <InfoButton topic="merkle" /></b>
                <Button size="sm" onClick={async () => setCheck(await checkProof((t.computed_hash as string) || t.payload_hash!, t.proof as any, t.merkle_root!))}>Check in this browser</Button></div>
              <div className={`banner ${t.valid === false ? 'threat' : 'info'}`} style={{ margin: '10px 0' }}>{t.valid === false
                ? <>The payload as stored now hashes to <b className="mono">{shortHash(t.computed_hash as string, 8, 6)}</b>, not the committed leaf <b className="mono">{shortHash(t.payload_hash, 8, 6)}</b>: this row was rewritten after sealing.</>
                : <>The payload re-hashes to the committed leaf.</>}</div>
              <ol className="proof">{(t.proof as any[]).map((p, i) => <li key={i}><Chip mono>{p.side}</Chip><span className="mono xs">{shortHash(p.hash, 12, 8)}</span>{check && <span className="mono xs muted">→ {shortHash(check.steps[i], 8, 6)}</span>}</li>)}</ol>
              {check && <div className={`banner ${check.ok ? 'info' : 'threat'}`}>{check.ok ? 'WebCrypto re-hashed the recomputed leaf along the proof to the block’s Merkle root: the transaction is intact and in the block.' : 'Starting from the payload as stored now, the path does not reach the block’s Merkle root: the record was altered.'}</div>}
            </div>)}
          <JsonViewer data={t.payload} filename={`tx-${t.id}.json`} />
        </div>)}
    </Drawer>
  );
}
