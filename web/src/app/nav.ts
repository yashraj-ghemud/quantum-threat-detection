import { Orbit, Radar, PenTool, Zap, Atom, LineChart, Blocks, ShieldAlert, BookOpen, type LucideIcon } from 'lucide-react';

export interface NavItem { to: string; label: string; title: string; icon: LucideIcon; key: string; mobile?: boolean }
export const NAV: NavItem[] = [
  { to: '/', label: 'Overview', title: 'Overview', icon: Orbit, key: 'o' },
  { to: '/command', label: 'Command', title: 'Command Center', icon: Radar, key: 'c', mobile: true },
  { to: '/studio', label: 'Studio', title: 'Signature Studio', icon: PenTool, key: 's', mobile: true },
  { to: '/attack-lab', label: 'Attack Lab', title: 'Attack Lab', icon: Zap, key: 'a', mobile: true },
  { to: '/playground', label: 'Playground', title: 'Quantum Playground', icon: Atom, key: 'p' },
  { to: '/analytics', label: 'Analytics', title: 'Analytics', icon: LineChart, key: 'n', mobile: true },
  { to: '/ledger', label: 'Ledger', title: 'Audit Ledger', icon: Blocks, key: 'l' },
  { to: '/incidents', label: 'Incidents', title: 'Incidents', icon: ShieldAlert, key: 'i' },
  { to: '/method', label: 'Method', title: 'Method', icon: BookOpen, key: 'm' },
];
export const titleFor = (path: string) => {
  if (path.startsWith('/sessions/')) return 'Session report';
  if (path.startsWith('/incidents/')) return 'Incident';
  const hit = NAV.filter((n) => (n.to === '/' ? path === '/' : path.startsWith(n.to))).pop();
  return hit ? hit.title : 'Not found';
};
