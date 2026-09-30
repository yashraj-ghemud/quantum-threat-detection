import { useState } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { Command as CmdIcon, Settings, Pause, Play, MoreHorizontal, WifiOff, Wifi, AlertTriangle, X } from 'lucide-react';
import { NAV, titleFor } from './nav';
import { useConn, useLive } from '@/state/live';
import { useUi } from '@/state/ui';
import { ep } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { toast } from '@/state/ui';
import { sevColor } from '@/lib/color';
import { ScrambleText } from '@/components/motion';
import { Drawer } from '@/components/overlays';
import { reconnectNow } from '@/stream/socket';

export function QubitLogo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden className="qubit-logo">
      <defs><linearGradient id="qlg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#8C84F0" /><stop offset=".55" stopColor="#6FA8F0" /><stop offset="1" stopColor="#4FC3A1" /></linearGradient></defs>
      <rect x="4" y="4" width="56" height="56" rx="18" fill="url(#qlg)" />
      <circle cx="32" cy="32" r="13" fill="#EEF0F9" />
      <g className="orbit"><ellipse cx="32" cy="32" rx="22" ry="8" fill="none" stroke="#F7F7FD" strokeWidth="2.5" transform="rotate(-28 32 32)" /><circle cx="51" cy="22" r="3" fill="#F7F7FD" /></g>
      <circle cx="32" cy="32" r="4.5" fill="#8C84F0" />
    </svg>
  );
}

function useNavClick() {
  const set = useUi((s) => s.set);
  return (e: React.MouseEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    set({ transitionOrigin: { x: r.left + r.width / 2, y: r.top + r.height / 2 } });
  };
}

export function NavRail() {
  const onNav = useNavClick();
  const open = useLive((s) => s.openIncidents);
  const [pinned, setPinned] = useState(false);
  return (
    <nav className={`navrail ${pinned ? 'pinned' : ''}`} aria-label="Primary">
      <Link to="/" className="nav-logo" onClick={onNav} aria-label="QVeris home"><QubitLogo /><span className="nav-brand">QVERIS</span></Link>
      <ul>
        {NAV.map((n) => (
          <li key={n.to}>
            <NavLink to={n.to} end={n.to === '/'} onClick={onNav} className="nav-item" title={n.title}>
              {({ isActive }) => (<>
                {isActive && <motion.span layoutId="nav-active" className="nav-active" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
                <n.icon aria-hidden /><span className="nav-label">{n.label}</span>
                {n.to === '/incidents' && open > 0 && <span className="nav-badge" aria-label={`${open} open`}>{open > 99 ? '99+' : open}</span>}
              </>)}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="nav-foot">
        <button className="nav-item" onClick={() => useUi.getState().set({ settingsOpen: true })} title="Settings"><Settings aria-hidden /><span className="nav-label">Settings</span></button>
        <button className="nav-pin xs" onClick={() => setPinned(!pinned)} aria-pressed={pinned}>{pinned ? '‹ collapse' : '› pin'}</button>
      </div>
    </nav>
  );
}

export function ConnectionPill() {
  const c = useConn();
  const live = c.status === 'live';
  return (
    <button className={`conn-pill ${c.status}`} onClick={() => !live && reconnectNow()} title={live ? `event stream live${c.rttMs != null ? ` · RTT ${c.rttMs} ms` : ''}` : 'reconnect now'}>
      {live ? <span className="dot pulse" /> : c.status === 'offline' ? <WifiOff /> : <Wifi />}
      <span className="conn-label">{live ? `live${c.rttMs != null ? ` · ${c.rttMs} ms` : ''}` : c.status === 'offline' ? 'offline' : `reconnecting${c.attempts ? ` ${c.attempts}` : ''}`}</span>
    </button>
  );
}

export function ThreatPill() {
  const threat = useLive((s) => s.threat);
  const open = useLive((s) => s.openIncidents);
  const nav = useNavigate();
  const color = sevColor(threat);
  const hot = threat === 'HIGH' || threat === 'CRITICAL';
  return (
    <button className={`threat-pill ${hot ? 'hot' : ''}`} style={{ color, ['--c' as string]: color }} onClick={() => nav("/incidents")} title={`threat level = worst severity among ${open} open incidents · resolve or dismiss them to clear it`} aria-label={`Threat level ${threat}, ${open} open incidents`}>
      {hot ? <AlertTriangle /> : <span className="dot" />}<span className="tp-label">threat</span><b>{threat === 'NONE' ? 'CLEAR' : threat}</b>
    </button>
  );
}

export function TrafficControl({ compact }: { compact?: boolean }) {
  const t = useLive((s) => s.traffic);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => { setBusy(true); try { await fn(); } catch (e) { toast({ tone: 'warn', title: friendly(e) }); } finally { setBusy(false); } };
  const running = !!t?.running && !t?.paused_idle;
  return (
    <div className="traffic-ctl" title={t ? `${t.generated} live transactions signed since start` : 'live signing traffic'}>
      <button className={`btn sm ${running ? 'ok' : ''}`} aria-busy={busy} onClick={() => run(() => (running ? ep.trafficStop() : ep.trafficStart(t?.rate_per_min)))}>
        {running ? <Pause /> : <Play />}{!compact && (running ? 'Live traffic' : t?.paused_idle ? 'Paused (idle)' : 'Start traffic')}
      </button>
      {!compact && (
        <div className="seg" role="group" aria-label="Traffic rate">
          {[6, 12, 30].map((r) => (
            <button key={r} aria-pressed={t?.rate_per_min === r} onClick={() => run(() => ep.trafficStart(r))}>{r}/m</button>
          ))}
        </div>
      )}
    </div>
  );
}

export function TopBar() {
  const loc = useLocation();
  const set = useUi((s) => s.set);
  const title = titleFor(loc.pathname);
  return (
    <header className="topbar">
      <Link to="/" className="top-logo" aria-label="QVeris home"><QubitLogo size={28} /></Link>
      <h1 className="top-title"><ScrambleText key={title} text={title} duration={520} /></h1>
      <div className="top-right">
        <ConnectionPill />
        <ThreatPill />
        <div className="hide-sm"><TrafficControl /></div>
        <button className="btn sm cmdk" onClick={() => set({ paletteOpen: true })} aria-label="Open command palette"><CmdIcon /><span className="hide-sm">Search</span><kbd className="hide-sm">⌘K</kbd></button>
        <button className="btn icon sm hide-sm" onClick={() => set({ settingsOpen: true })} aria-label="Settings"><Settings /></button>
      </div>
    </header>
  );
}

export function BottomNav() {
  const onNav = useNavClick();
  const [more, setMore] = useState(false);
  const loc = useLocation();
  const items = NAV.filter((n) => n.mobile);
  const rest = NAV.filter((n) => !n.mobile);
  const inMore = rest.some((n) => (n.to === '/' ? loc.pathname === '/' : loc.pathname.startsWith(n.to)));
  return (
    <>
      <nav className="bottomnav" aria-label="Primary (mobile)">
        {items.map((n) => (
          <NavLink key={n.to} to={n.to} onClick={onNav} className="bn-item">
            {({ isActive }) => (<>{isActive && <motion.span layoutId="bn-active" className="bn-active" />}<motion.span animate={isActive ? { y: [0, -4, 0] } : {}} transition={{ duration: 0.35 }}><n.icon aria-hidden /></motion.span><span>{n.label}</span></>)}
          </NavLink>
        ))}
        <button className={`bn-item ${inMore ? 'active' : ''}`} onClick={() => setMore(true)} aria-haspopup="dialog">
          {inMore && <motion.span layoutId="bn-active" className="bn-active" />}<MoreHorizontal aria-hidden /><span>More</span>
        </button>
      </nav>
      <Drawer open={more} onClose={() => setMore(false)} title="More">
        <div className="grid g2">
          {rest.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'} className="more-item" onClick={(e) => { onNav(e); setMore(false); }}><n.icon aria-hidden /><span>{n.title}</span></NavLink>
          ))}
          <button className="more-item" onClick={() => { setMore(false); useUi.getState().set({ settingsOpen: true }); }}><Settings aria-hidden /><span>Settings</span></button>
        </div>
        <div style={{ marginTop: 18 }}><div className="label" style={{ marginBottom: 8 }}>Live traffic</div><TrafficControl /></div>
      </Drawer>
    </>
  );
}

export function DegradedBanner() {
  const status = useConn((s) => s.status);
  const attempts = useConn((s) => s.attempts);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const key = status === 'offline' ? 'offline' : status === 'reconnecting' && attempts >= 2 ? 'reconnecting' : null;
  return (
    <AnimatePresence>
      {key && dismissed !== key && (
        <motion.div className={`banner ${key === 'offline' ? 'threat' : 'warn'} degraded`} role="status" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
          <WifiOff />
          <span className="grow">{key === 'offline' ? 'Engine unreachable — showing the last known state. Start the backend (python -m server) and it reconnects automatically.' : `Event stream reconnecting (attempt ${attempts})…`}</span>
          <button className="btn ghost sm" onClick={() => reconnectNow()}>Retry now</button>
          <button className="btn ghost icon sm" aria-label="Dismiss" onClick={() => setDismissed(key)}><X /></button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
