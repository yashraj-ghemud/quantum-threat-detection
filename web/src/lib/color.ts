import type { Category, Severity, Verdict } from '@/api/types';

export const cssVar = (name: string, el: Element = document.documentElement) => getComputedStyle(el).getPropertyValue(name).trim();
export const NODE_VAR: Record<string, string> = { alice: '--alice', diana: '--diana', bob: '--bob', charlie: '--charlie', erin: '--erin', eve: '--threat', mallory: '--mallory' };
export const nodeColor = (id: string) => `var(${NODE_VAR[id] || '--quantum'})`;
export const SEV_VAR: Record<Severity, string> = { NONE: '--sev-none', LOW: '--sev-low', MEDIUM: '--sev-medium', HIGH: '--sev-high', CRITICAL: '--sev-critical' };
export const sevColor = (s: Severity | string | null | undefined) => `var(${SEV_VAR[(s || 'NONE') as Severity] || '--sev-none'})`;
export const SEV_RANK: Record<string, number> = { NONE: 0, LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 };
export const verdictTone = (v: Verdict | string | null | undefined): 'ok' | 'threat' | 'warn' | 'neutral' =>
  v === 'ACCEPTED' || v === 'CERTIFIED' ? 'ok' : v === 'REJECTED' || v === 'COMPROMISED' ? 'threat' : 'neutral';
export const CAT_COLOR: Record<Category, string> = {
  NONE: 'var(--text-3)', FORGERY: 'var(--coral)', IMPERSONATION: 'var(--mallory)', REPLAY: 'var(--gold)',
  UNAUTHORIZED_VERIFICATION: 'var(--lav)', CHANNEL_MANIPULATION: 'var(--sky)', REPUDIATION: 'var(--diana)', DEGRADED: 'var(--peach)',
};
export const BASIS_VAR = ['--basis-x', '--basis-y', '--basis-z'];
export const LABEL_KET = ['|+⟩', '|−⟩', '|+i⟩', '|−i⟩', '|0⟩', '|1⟩'];
export const LABEL_BASIS = [0, 0, 1, 1, 2, 2];
export const LABEL_BIT = [0, 1, 0, 1, 0, 1];
export const LABEL_BLOCH: [number, number, number][] = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
export const BASIS_NAME = ['X', 'Y', 'Z'];
