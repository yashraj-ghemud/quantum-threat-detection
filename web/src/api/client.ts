/* Fetch wrapper: JSON in/out, timeouts, GET retries, and the backend's
   uniform error envelope parsed into ApiError. */
import { getPrefs } from '@/state/prefs';

export class ApiError extends Error {
  code: string; status: number; detail: Record<string, unknown>; requestId?: string;
  constructor(status: number, code: string, message: string, detail: Record<string, unknown> = {}, requestId?: string) {
    super(message); this.status = status; this.code = code; this.detail = detail; this.requestId = requestId;
  }
}

export function apiBase(): string {
  const b = getPrefs().apiBase || (import.meta.env.VITE_API_BASE as string | undefined) || '';
  return b.replace(/\/$/, '');
}

export function wsUrl(): string {
  const base = apiBase();
  if (base) return base.replace(/^http/, 'ws') + '/ws';
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/ws`;
}

type Query = Record<string, string | number | boolean | null | undefined>;
export interface RequestOpts { body?: unknown; query?: Query; timeoutMs?: number; signal?: AbortSignal; retries?: number }

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function request<T>(method: string, path: string, opts: RequestOpts = {}): Promise<T> {
  const qs = opts.query
    ? '?' + Object.entries(opts.query).filter(([, v]) => v !== undefined && v !== null && v !== '')
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&')
    : '';
  const url = `${apiBase()}/api/v1${path}${qs === '?' ? '' : qs}`;
  const retries = opts.retries ?? (method === 'GET' ? 2 : 0);
  let attempt = 0;
  for (;;) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), opts.timeoutMs ?? (method === 'GET' ? 20000 : 120000));
    const onAbort = () => ctl.abort();
    opts.signal?.addEventListener('abort', onAbort);
    try {
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
      const key = getPrefs().apiKey;
      if (key) headers['X-API-Key'] = key;
      const res = await fetch(url, { method, headers, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined, signal: ctl.signal });
      const text = await res.text();
      const data = text ? safeJson(text) : null;
      if (!res.ok) {
        const e = (data && typeof data === 'object' && 'error' in data ? (data as any).error : null) || {};
        throw new ApiError(res.status, e.code || `HTTP_${res.status}`, e.message || res.statusText || 'request failed', e.detail || {}, e.request_id);
      }
      return data as T;
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if (opts.signal?.aborted) throw err;
      if (attempt >= retries) {
        const aborted = (err as Error)?.name === 'AbortError';
        throw new ApiError(0, aborted ? 'TIMEOUT' : 'NETWORK', aborted ? 'The engine did not answer in time.' : 'The engine is unreachable.');
      }
      attempt++;
      await sleep(attempt === 1 ? 300 : 900);
    } finally {
      clearTimeout(timer);
      opts.signal?.removeEventListener('abort', onAbort);
    }
  }
}

function safeJson(t: string): unknown { try { return JSON.parse(t); } catch { return t; } }

export const api = {
  get: <T>(p: string, query?: Query, o: RequestOpts = {}) => request<T>('GET', p, { ...o, query }),
  post: <T>(p: string, body: unknown = {}, o: RequestOpts = {}) => request<T>('POST', p, { ...o, body }),
  put: <T>(p: string, body: unknown = {}, o: RequestOpts = {}) => request<T>('PUT', p, { ...o, body }),
  patch: <T>(p: string, body: unknown = {}, o: RequestOpts = {}) => request<T>('PATCH', p, { ...o, body }),
  del: <T>(p: string, o: RequestOpts = {}) => request<T>('DELETE', p, o),
};

const FRIENDLY: Record<string, string> = {
  BUNDLE_UNAVAILABLE: 'No certified key bundle is ready for this group.',
  BUNDLE_COMPROMISED: 'That key bundle was flagged as compromised and cannot sign.',
  LINK_QUARANTINED: 'A quantum link of this group is quarantined.',
  MESSAGE_TOO_LONG: 'The message is too long for the chosen encoding.',
  RATE_LIMITED: 'Too many heavy requests; the engine asks you to slow down.',
  NETWORK: 'The engine is unreachable.',
  TIMEOUT: 'The engine did not answer in time.',
  JOB_CONFLICT: 'A job of this kind is already running.',
  FEATURE_DISABLED: 'This feature is disabled on this server.',
  UNAUTHORIZED: 'An API key is required for this action (Settings → API key).',
};
export function friendly(err: unknown): string {
  if (err instanceof ApiError) return FRIENDLY[err.code] ? `${FRIENDLY[err.code]} ${err.code === 'VALIDATION_ERROR' ? err.message : ''}`.trim() : err.message;
  return (err as Error)?.message || String(err);
}
