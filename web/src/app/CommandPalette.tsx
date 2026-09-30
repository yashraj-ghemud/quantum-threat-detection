import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Search, ArrowRight, Zap, Play, Pause, ShieldCheck, LineChart, Moon, Sun, Settings, History, Link2 } from 'lucide-react';
import { Modal } from '@/components/overlays';
import { useUi, toast } from '@/state/ui';
import { usePrefs } from '@/state/prefs';
import { useLive } from '@/state/live';
import { ep, qk } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { fuzzyScore } from '@/lib/fuzzy';
import { NAV } from './nav';
import { catLabel } from '@/lib/format';

interface Cmd { id: string; group: 'Navigate' | 'Actions' | 'Attacks' | 'Analyses' | 'Recent'; label: string; hint?: string; icon: React.ComponentType<any>; run: () => void | Promise<void> }

export function CommandPalette() {
  const open = useUi((s) => s.paletteOpen);
  const set = useUi((s) => s.set);
  const nav = useNavigate();
  const prefs = usePrefs();
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const catalog = useQuery({ queryKey: qk.catalog, queryFn: ep.catalog, staleTime: Infinity, enabled: open });
  const kinds = useQuery({ queryKey: qk.kinds, queryFn: ep.analyticsKinds, staleTime: Infinity, enabled: open });
  const net = useQuery({ queryKey: qk.network, queryFn: () => ep.network(), enabled: open });
  const feed = useLive((s) => s.feed);
  const traffic = useLive((s) => s.traffic);
  const close = () => { set({ paletteOpen: false }); setQ(''); setSel(0); };
  const act = (fn: () => Promise<unknown>, ok: string) => async () => { try { await fn(); toast({ tone: 'ok', title: ok }); qc.invalidateQueries(); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } };

  const cmds: Cmd[] = useMemo(() => {
    const out: Cmd[] = NAV.map((n) => ({ id: `nav${n.to}`, group: 'Navigate', label: n.title, hint: `g ${n.key}`, icon: n.icon, run: () => nav(n.to) }));
    const running = traffic?.running && !traffic.paused_idle;
    out.push({ id: 'traffic', group: 'Actions', label: running ? 'Stop live traffic' : 'Start live traffic', icon: running ? Pause : Play, run: act(() => (running ? ep.trafficStop() : ep.trafficStart()), running ? 'Traffic stopped' : 'Traffic started') });
    [6, 12, 30, 60].forEach((r) => out.push({ id: `rate${r}`, group: 'Actions', label: `Set traffic rate to ${r}/min`, icon: Play, run: act(() => ep.trafficStart(r), `Traffic at ${r}/min`) }));
    out.push({ id: 'verify', group: 'Actions', label: 'Verify ledger integrity', icon: ShieldCheck, run: async () => { try { const r = await ep.verifyLedger(); toast({ tone: r.valid ? 'ok' : 'threat', title: r.valid ? `Ledger valid · ${r.checked_blocks} blocks` : `Ledger INVALID from height ${r.first_invalid_height}` }); nav('/ledger'); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } } });
    (net.data?.links || []).filter((l) => l.kind === 'quantum' && !l.hidden).forEach((l) => out.push({ id: `cert${l.id}`, group: 'Actions', label: `Certify link ${l.a} → ${l.b}`, icon: Link2, run: act(() => ep.certify(l.id), `Certification run on ${l.id}`) }));
    out.push({ id: 'theme', group: 'Actions', label: prefs.theme === 'noir' ? 'Switch to Mist theme' : 'Switch to Noir theme', icon: prefs.theme === 'noir' ? Sun : Moon, run: () => prefs.set({ theme: prefs.theme === 'noir' ? 'mist' : 'noir' }) });
    out.push({ id: 'motion', group: 'Actions', label: prefs.motion === 'reduced' ? 'Enable full motion' : 'Reduce motion', icon: Settings, run: () => prefs.set({ motion: prefs.motion === 'reduced' ? 'full' : 'reduced' }) });
    out.push({ id: 'sound', group: 'Actions', label: prefs.sound ? 'Turn sound off' : 'Turn sound on', icon: Settings, run: () => prefs.set({ sound: !prefs.sound }) });
    out.push({ id: 'settings', group: 'Actions', label: 'Open settings', icon: Settings, run: () => set({ settingsOpen: true }) });
    (catalog.data || []).forEach((a) => out.push({ id: `atk${a.id}`, group: 'Attacks', label: `Launch ${a.name}`, hint: catLabel(a.category), icon: Zap, run: () => nav(`/attack-lab?attack=${a.id}`) }));
    (kinds.data || []).forEach((k) => out.push({ id: `job${k.kind}`, group: 'Analyses', label: `Run ${k.title} (quick)`, icon: LineChart, run: act(async () => { await ep.submitJob(k.kind, 'quick'); nav(`/analytics#${k.kind}`); }, `${k.title} queued`) }));
    feed.slice(0, 6).forEach((s) => out.push({ id: `recent${s.id}`, group: 'Recent', label: `${s.kind === 'signature' ? (s.message_preview || 'signature') : 'distribution'} · ${s.verdict}`, hint: s.group_id, icon: History, run: () => nav(`/sessions/${s.id}`) }));
    return out;
  }, [catalog.data, kinds.data, net.data, feed, traffic, prefs.theme, prefs.motion, prefs.sound]); // eslint-disable-line react-hooks/exhaustive-deps

  const results = useMemo(() => {
    if (!q.trim()) return cmds.filter((c) => c.group !== 'Attacks' && c.group !== 'Analyses').slice(0, 30);
    return cmds.map((c) => ({ c, s: fuzzyScore(q, `${c.label} ${c.hint || ''} ${c.group}`) })).filter((x) => x.s >= 0).sort((a, b) => b.s - a.s).slice(0, 40).map((x) => x.c);
  }, [q, cmds]);
  useEffect(() => { setSel(0); }, [q]);
  useEffect(() => { listRef.current?.querySelector(`[data-i="${sel}"]`)?.scrollIntoView({ block: 'nearest' }); }, [sel]);

  const run = (c: Cmd) => { close(); setTimeout(() => c.run(), 10); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(results.length - 1, s + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
    else if (e.key === 'Enter' && results[sel]) { e.preventDefault(); run(results[sel]); }
  };
  let lastGroup = '';
  return (
    <Modal open={open} onClose={close} label="Command palette">
      <div className="palette" onKeyDown={onKey}>
        <div className="pal-input"><Search aria-hidden /><input autoFocus placeholder="Search pages, attacks, analyses, actions…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Command search" /><kbd>esc</kbd></div>
        <div className="pal-list" ref={listRef} role="listbox">
          {results.length === 0 && <div className="empty" style={{ padding: 24 }}><p>No command matches “{q}”.</p></div>}
          {results.map((c, i) => {
            const head = c.group !== lastGroup ? (lastGroup = c.group) : null;
            return (
              <div key={c.id}>
                {head && <div className="pal-group">{head}</div>}
                <button data-i={i} role="option" aria-selected={i === sel} className={`pal-item ${i === sel ? 'sel' : ''}`} onMouseEnter={() => setSel(i)} onClick={() => run(c)}>
                  <c.icon aria-hidden /><span className="grow">{c.label}</span>{c.hint && <span className="xs muted mono">{c.hint}</span>}<ArrowRight className="pal-go" aria-hidden />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </Modal>
  );
}
