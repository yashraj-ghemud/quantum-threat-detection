import { create } from 'zustand';

export interface Toast { id: number; tone: 'ok' | 'threat' | 'warn' | 'info'; title: string; body?: string; action?: { label: string; href?: string; run?: () => void }; sticky?: boolean; at: number }
interface UiState {
  paletteOpen: boolean; settingsOpen: boolean; explain: string | null; transitionOrigin: { x: number; y: number } | null;
  toasts: Toast[]; announce: string;
  set: (p: Partial<UiState>) => void; toast: (t: Omit<Toast, 'id' | 'at'>) => void; dismiss: (id: number) => void; say: (m: string) => void;
}
let tid = 1;
export const useUi = create<UiState>((set, get) => ({
  paletteOpen: false, settingsOpen: false, explain: null, transitionOrigin: null, toasts: [], announce: '',
  set: (p) => set(p),
  toast: (t) => {
    const all = [...get().toasts, { ...t, id: tid++, at: Date.now() }];
    set({ toasts: all.slice(-6) });
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
  say: (m) => set({ announce: m }),
}));
export const toast = (t: Omit<Toast, 'id' | 'at'>) => useUi.getState().toast(t);
export const explain = (topic: string) => useUi.getState().set({ explain: topic });
