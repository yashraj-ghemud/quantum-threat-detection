import { Suspense, useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion, MotionConfig } from 'motion/react';
import { ep, qk } from '@/api/endpoints';
import { connect } from '@/stream/socket';
import { useLive } from '@/state/live';
import { usePrefs, resolvedTheme, reducedMotion } from '@/state/prefs';
import { useUi } from '@/state/ui';
import { installFx } from '@/fx/fx';
import { NavRail, TopBar, BottomNav, DegradedBanner } from './Shell';
import { Boot } from './Boot';
import { CommandPalette } from './CommandPalette';
import { Toasts } from './Toasts';
import { ExplainDrawer } from './ExplainDrawer';
import { SettingsSheet } from './SettingsSheet';
import { PageErrorBoundary } from './ErrorBoundary';
import { NAV } from './nav';

export function App() {
  const prefs = usePrefs();
  const loc = useLocation();
  const nav = useNavigate();
  const ui = useUi();
  const threat = useLive((s) => s.threat);
  const [booted, setBooted] = useState(() => { try { return sessionStorage.getItem('qveris.booted') === '1'; } catch { return false; } });
  const reduce = reducedMotion(prefs.motion);

  // Theme + motion on <html>.
  useEffect(() => {
    const apply = () => {
      const t = resolvedTheme(prefs.theme);
      document.documentElement.dataset.theme = t;
      document.documentElement.dataset.motion = reduce ? 'reduced' : 'full';
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', t === 'noir' ? '#060816' : '#EAEDF7');
    };
    apply();
    const mq = matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener?.('change', apply);
    return () => mq.removeEventListener?.('change', apply);
  }, [prefs.theme, reduce]);
  useEffect(() => { installFx({ cursor: prefs.cursor, reduced: reduce }); }, [prefs.cursor, reduce]);
  useEffect(() => { document.body.classList.toggle('threat-high', threat === 'HIGH' || threat === 'CRITICAL'); }, [threat]);

  // Live stream + initial state.
  useEffect(() => { connect(); }, []);
  const sessions = useQuery({ queryKey: qk.sessions({ limit: 80 }), queryFn: () => ep.sessions({ limit: 80 }) });
  const reservoir = useQuery({ queryKey: qk.reservoir, queryFn: ep.reservoir });
  const traffic = useQuery({ queryKey: qk.traffic, queryFn: ep.traffic });
  const incidents = useQuery({ queryKey: qk.incidents({ status: 'OPEN' }), queryFn: () => ep.incidents({ status: 'OPEN', limit: 200 }) });
  const campaigns = useQuery({ queryKey: qk.campaigns, queryFn: ep.campaigns });
  useEffect(() => { if (sessions.data) useLive.getState().seedFeed(sessions.data); }, [sessions.data]);
  useEffect(() => { if (reservoir.data) useLive.getState().set({ reservoir: reservoir.data }); }, [reservoir.data]);
  useEffect(() => { if (traffic.data) useLive.getState().set({ traffic: traffic.data }); }, [traffic.data]);
  useEffect(() => { if (campaigns.data) useLive.getState().set({ campaigns: campaigns.data.campaigns.filter((c) => c.state === 'running') }); }, [campaigns.data]);
  useEffect(() => {
    if (!incidents.data) return;
    const rank = { NONE: 0, LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 } as Record<string, number>;
    const worst = incidents.data.reduce((w, i) => (rank[i.severity] > rank[w] ? i.severity : w), 'NONE' as string);
    if (!useLive.getState().tick) useLive.getState().set({ openIncidents: incidents.data.length, threat: worst as any });
  }, [incidents.data]);

  // Keyboard: palette, g-navigation, settings.
  useEffect(() => {
    let g = false, gt: ReturnType<typeof setTimeout>;
    const h = (e: KeyboardEvent) => {
      const typing = /INPUT|TEXTAREA|SELECT/.test((e.target as HTMLElement)?.tagName) || (e.target as HTMLElement)?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); ui.set({ paletteOpen: !useUi.getState().paletteOpen }); return; }
      if (typing) return;
      if (e.key === '/') { e.preventDefault(); ui.set({ paletteOpen: true }); return; }
      if (e.key === ',') { ui.set({ settingsOpen: true }); return; }
      if (g) { const item = NAV.find((n) => n.key === e.key.toLowerCase()); g = false; if (item) nav(item.to); return; }
      if (e.key === 'g') { g = true; clearTimeout(gt); gt = setTimeout(() => { g = false; }, 900); }
    };
    addEventListener('keydown', h);
    return () => removeEventListener('keydown', h);
  }, [nav]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { window.scrollTo({ top: 0 }); }, [loc.pathname]);

  const origin = ui.transitionOrigin;
  return (
    <MotionConfig reducedMotion={reduce ? 'always' : 'never'}>
      <a href="#main" className="skip-link">Skip to content</a>
      {!booted && <Boot onDone={() => { setBooted(true); try { sessionStorage.setItem('qveris.booted', '1'); } catch { /* ignore */ } }} />}
      <div className="shell">
        <NavRail />
        <div className="shell-main">
          <TopBar />
          <DegradedBanner />
          <main id="main" className="content" tabIndex={-1}>
            <PageErrorBoundary key={loc.pathname}>
              <AnimatePresence mode="wait" initial={false}>
                <motion.div key={loc.pathname} className="page"
                  initial={reduce ? { opacity: 0 } : { opacity: 0, clipPath: `circle(0% at ${origin?.x ?? innerWidth / 2}px ${origin?.y ?? innerHeight / 2}px)` }}
                  animate={reduce ? { opacity: 1 } : { opacity: 1, clipPath: `circle(150% at ${origin?.x ?? innerWidth / 2}px ${origin?.y ?? innerHeight / 2}px)`, transitionEnd: { clipPath: 'none' } }}
                  exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.985, filter: 'blur(6px)' }}
                  transition={{ duration: reduce ? 0.12 : 0.6, ease: [0.22, 1, 0.36, 1] }}>
                  <Suspense fallback={<PageSkeleton />}>
                    <Outlet context={{ booted }} />
                  </Suspense>
                </motion.div>
              </AnimatePresence>
            </PageErrorBoundary>
          </main>
        </div>
        <BottomNav />
      </div>
      <CommandPalette />
      <ExplainDrawer />
      <SettingsSheet />
      <Toasts />
      <div className="sr-only" aria-live="polite">{ui.announce}</div>
    </MotionConfig>
  );
}

function PageSkeleton() {
  return <div className="stack" style={{ padding: 8 }}><div className="skeleton" style={{ height: 48, width: 280 }} /><div className="grid g3"><div className="skeleton" style={{ height: 140 }} /><div className="skeleton" style={{ height: 140 }} /><div className="skeleton" style={{ height: 140 }} /></div><div className="skeleton" style={{ height: 360 }} /></div>;
}
