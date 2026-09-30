import { create } from 'zustand';

export type Theme = 'mist' | 'noir' | 'system';
export type Motion = 'system' | 'full' | 'reduced';
export type Quality = 'auto' | 'high' | 'medium' | 'low';
export interface Prefs {
  theme: Theme; motion: Motion; quality: Quality; sound: boolean; haptics: boolean; cursor: boolean; hints: boolean;
  apiBase: string; apiKey: string; introSeen: boolean;
}
const KEY = 'qveris.prefs.v1';
const DEFAULTS: Prefs = { theme: 'mist', motion: 'system', quality: 'auto', sound: false, haptics: true, cursor: true, hints: true, apiBase: '', apiKey: '', introSeen: false };

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
  } catch { return { ...DEFAULTS }; }
}
interface PrefsStore extends Prefs { set: (p: Partial<Prefs>) => void }
export const usePrefs = create<PrefsStore>((set, get) => ({
  ...load(),
  set: (p) => {
    set(p);
    try { const { set: _s, ...rest } = get(); localStorage.setItem(KEY, JSON.stringify(rest)); } catch { /* storage unavailable */ }
  },
}));
export const getPrefs = () => usePrefs.getState();

export function resolvedTheme(t: Theme): 'mist' | 'noir' {
  if (t !== 'system') return t;
  try { return matchMedia('(prefers-color-scheme: dark)').matches ? 'noir' : 'mist'; } catch { return 'mist'; }
}
export function reducedMotion(m: Motion = getPrefs().motion): boolean {
  if (m === 'reduced') return true;
  if (m === 'full') return false;
  try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return false; }
}
export function qualityTier(q: Quality = getPrefs().quality): 'high' | 'medium' | 'low' {
  if (q !== 'auto') return q;
  try {
    const coarse = matchMedia('(pointer: coarse)').matches;
    const cores = navigator.hardwareConcurrency || 4;
    const mem = (navigator as any).deviceMemory || 8;
    if (coarse && (devicePixelRatio > 2 || cores <= 4)) return 'low';
    if (cores <= 4 || mem <= 4) return 'medium';
    return 'high';
  } catch { return 'medium'; }
}
