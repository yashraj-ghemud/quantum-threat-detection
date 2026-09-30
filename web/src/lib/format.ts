const SUP: Record<string, string> = { '-': '⁻', '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹' };
export const sup = (n: number | string) => String(n).split('').map((c) => SUP[c] ?? c).join('');

/** 3.1 × 10⁻¹⁰ for tiny/huge values; plain decimals otherwise. */
export function sci(x: number | null | undefined, digits = 2): string {
  if (x == null || !Number.isFinite(x)) return '—';
  if (x === 0) return '0';
  const a = Math.abs(x);
  if (a >= 1e-3 && a < 1e5) return x.toPrecision(digits + 1).replace(/\.?0+$/, (m) => (m.includes('.') ? '' : m));
  const e = Math.floor(Math.log10(a));
  const m = x / 10 ** e;
  return `${m.toFixed(digits - 1)} × 10${sup(e)}`;
}
export const pct = (x: number | null | undefined, d = 2) => (x == null || !Number.isFinite(x) ? '—' : `${(x * 100).toFixed(d)} %`);
export const pctCI = (x: number | null | undefined, ci?: [number, number] | null, d = 2) =>
  x == null ? '—' : `${pct(x, d)}${ci ? ` [${(ci[0] * 100).toFixed(d)}, ${(ci[1] * 100).toFixed(d)}]` : ''}`;
export const fix = (x: number | null | undefined, d = 3) => (x == null || !Number.isFinite(x) ? '—' : x.toFixed(d));
/** 2 330 624 with thin spaces. */
export const int = (x: number | null | undefined) => (x == null || !Number.isFinite(x) ? '—' : Math.round(x).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' '));
export function compact(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return '—';
  const a = Math.abs(x);
  if (a >= 1e9) return (x / 1e9).toFixed(2) + ' G';
  if (a >= 1e6) return (x / 1e6).toFixed(2) + ' M';
  if (a >= 1e4) return (x / 1e3).toFixed(1) + ' k';
  return int(x);
}
export function ms(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return '—';
  if (x < 1) return `${(x * 1000).toFixed(0)} µs`;
  if (x < 1000) return `${x < 10 ? x.toFixed(1) : Math.round(x)} ms`;
  if (x < 60_000) return `${(x / 1000).toFixed(x < 10_000 ? 2 : 1)} s`;
  return `${Math.floor(x / 60_000)} min ${Math.round((x % 60_000) / 1000)} s`;
}
export function ago(ts: number | null | undefined, now = Date.now() / 1000): string {
  if (!ts) return '—';
  const d = Math.max(0, now - ts);
  if (d < 5) return 'just now';
  if (d < 60) return `${Math.floor(d)} s ago`;
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return `${Math.floor(d / 86400)} d ago`;
}
export const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
export const shortHash = (h: string | null | undefined, head = 6, tail = 4) => (!h ? '—' : h.length <= head + tail + 1 ? h : `${h.slice(0, head)}…${h.slice(-tail)}`);
export const titleCase = (s: string | null | undefined) => (s ? s.replace(/[_.]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '');
export const catLabel = (c: string | null | undefined) => ({
  NONE: 'None', FORGERY: 'Forgery', IMPERSONATION: 'Impersonation', REPLAY: 'Replay', UNAUTHORIZED_VERIFICATION: 'Unauthorized verification',
  CHANNEL_MANIPULATION: 'Channel manipulation', REPUDIATION: 'Repudiation', DEGRADED: 'Degraded link',
} as Record<string, string>)[c || 'NONE'] || titleCase(c);
export const bytes = (n: number) => (n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(2)} MiB` : n >= 1024 ? `${(n / 1024).toFixed(1)} KiB` : `${n} B`);
export const utf8len = (s: string) => new TextEncoder().encode(s).length;
