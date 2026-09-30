import { api } from './client';
import type * as T from './types';

export const ep = {
  health: () => api.get<T.Health>('/health', undefined, { retries: 0, timeoutMs: 6000 }),
  selftest: () => api.get<T.Selftest>('/system/selftest'),
  runSelftest: () => api.post<T.Selftest>('/system/selftest/run'),
  config: () => api.get<T.SystemConfig>('/system/config'),
  setPreset: (preset: string) => api.put<{ active_preset: string; params: T.PresetInfo }>('/system/preset', { preset }),

  network: (includeHidden = false) => api.get<T.Network>('/network', { include_hidden: includeHidden }),
  link: (id: string) => api.get<T.LinkInfo & Record<string, unknown>>(`/network/links/${id}`),
  linkMonitor: (id: string, limit = 200) => api.get<T.MonitorPoint[]>(`/network/links/${id}/monitor`, { limit }),
  certify: (id: string) => api.post<Record<string, any>>(`/network/links/${id}/certify`),
  quarantine: (id: string, reason = '') => api.post<T.LinkInfo>(`/network/links/${id}/quarantine`, { reason }),
  release: (id: string) => api.post<T.LinkInfo>(`/network/links/${id}/release`),
  suspendNode: (id: string) => api.post<{ signer_id: string; suspended: boolean }>(`/network/nodes/${id}/suspend`),
  reinstateNode: (id: string) => api.post<{ signer_id: string; suspended: boolean }>(`/network/nodes/${id}/reinstate`),
  patchLink: (id: string, body: Record<string, unknown>) => api.patch<T.LinkInfo>(`/network/links/${id}`, body),

  reservoir: () => api.get<T.ReservoirEntry[]>('/keys/reservoir'),
  bundles: (q: Record<string, string | number | undefined> = {}) => api.get<any[]>('/keys/bundles', q),
  bundle: (id: string) => api.get<Record<string, any>>(`/keys/bundles/${id}`),
  distribute: (group_id: string, preset?: string, origin = 'STUDIO') => api.post<T.DistributionReport>('/keys/distribute', { group_id, preset, origin }),
  revokeBundle: (id: string, reason = '') => api.post(`/keys/bundles/${id}/revoke`, { reason }),

  signAndVerify: (b: { group_id: string; message: string; encoding: 'sha256' | 'raw'; bundle_id?: string; origin?: string }) =>
    api.post<T.SignatureReport>('/signatures/sign-and-verify', { origin: 'STUDIO', ...b }),
  captured: () => api.get<{ session_id: string; group_id: string; at: number; message: string }[]>('/signatures/captured'),
  reverify: (sid: string, body: { verifier_id?: string; delay_s?: number } = {}) => api.post<T.SignatureReport>(`/signatures/${sid}/reverify`, body),

  sessions: (q: { kind?: string; origin?: string; verdict?: string; group_id?: string; attack?: boolean; limit?: number; before?: number } = {}) => api.get<T.SessionSummary[]>('/sessions', q),
  session: (id: string) => api.get<T.Report>(`/sessions/${id}`),

  catalog: () => api.get<T.CatalogEntry[]>('/attacks/catalog'),
  runAttack: (b: { attack: { attack_id: string; intensity: number; params?: Record<string, unknown>; target?: string }; group_id?: string; message?: string; counterfactual?: boolean }) =>
    api.post<T.AttackRunReport>('/attacks/run', b),
  attackRuns: (limit = 30) => api.get<T.AttackRunSummary[]>('/attacks/runs', { limit }),
  attackRun: (id: string) => api.get<T.AttackRunReport>(`/attacks/runs/${id}`),
  campaigns: () => api.get<{ campaigns: T.Campaign[]; presets: Record<string, { name: string; description: string; mix: unknown[] }> }>('/attacks/campaigns'),
  startCampaign: (b: Record<string, unknown>) => api.post<T.Campaign>('/attacks/campaigns', b),
  stopCampaign: (id: string) => api.del<T.Campaign>(`/attacks/campaigns/${id}`),

  traffic: () => api.get<T.TrafficState>('/traffic'),
  trafficStart: (rate_per_min?: number, groups?: string[]) => api.post<T.TrafficState>('/traffic/start', { rate_per_min, groups }),
  trafficStop: () => api.post<T.TrafficState>('/traffic/stop'),

  detectionConfig: () => api.get<Record<string, any>>('/detection/config'),
  setDetection: (patch: Record<string, unknown>) => api.put<Record<string, any>>('/detection/config', patch),
  detectors: () => api.get<Record<string, any>[]>('/detection/detectors'),
  baselines: () => api.get<Record<string, any>[]>('/detection/baselines'),
  calibrate: (link_ids?: string[]) => api.post<Record<string, any>[]>('/detection/baselines/calibrate', { link_ids }),

  incidents: (q: { status?: string; severity?: string; category?: string; limit?: number } = {}) => api.get<T.Incident[]>('/incidents', q),
  incident: (id: string) => api.get<T.Incident>(`/incidents/${id}`),
  ackIncident: (id: string, note = '') => api.post<T.Incident>(`/incidents/${id}/acknowledge`, { note }),
  resolveIncident: (id: string, note = '') => api.post<T.Incident>(`/incidents/${id}/resolve`, { note }),
  respond: (id: string, action: string) => api.post<{ incident: T.Incident; result: any }>(`/incidents/${id}/respond`, { action }),

  analyticsKinds: () => api.get<T.JobKind[]>('/analytics/kinds'),
  submitJob: (kind: string, preset: 'quick' | 'full' = 'quick', params: Record<string, unknown> = {}) => api.post<T.Job>('/analytics/jobs', { kind, preset, params }),
  jobs: (limit = 20) => api.get<T.Job[]>('/analytics/jobs', { limit }),
  job: (id: string) => api.get<T.Job>(`/analytics/jobs/${id}`),
  cancelJob: (id: string) => api.del<T.Job>(`/analytics/jobs/${id}`),
  latest: (kind: string) => api.get<T.Job | null>(`/analytics/latest/${kind}`, undefined, { retries: 0 }),

  design: (q: { L: number; e: number; digest_bits?: number; eps_rob?: number; eps_forge?: number; eps_rep?: number }) => api.get<T.Design>('/theory/design', q),
  forgery: (q: { L_min?: number; L_max?: number; points?: number; s_v?: number; e?: number }) => api.get<Record<string, any>>('/theory/forgery', q),
  theoryLink: (channels: T.ChannelSpec[]) => api.post<T.TheoryLink>('/theory/link', { channels }),
  pgChannel: (channels: T.ChannelSpec[]) => api.post<T.PlaygroundChannel>('/playground/channel', { channels }),
  pgTeleport: (b: { bloch?: number[]; label?: number; channels?: T.ChannelSpec[]; frame_flip?: { m0?: number; m1?: number }; shots?: number; basis?: T.Basis }) =>
    api.post<T.PlaygroundTeleport>('/playground/teleport', b),

  ledgerSummary: () => api.get<T.LedgerSummary>('/ledger/summary'),
  blocks: (before?: number, limit = 30) => api.get<T.Block[]>('/ledger/blocks', { before, limit }),
  block: (h: number) => api.get<T.BlockDetail>(`/ledger/blocks/${h}`),
  tx: (id: string) => api.get<T.LedgerTx>(`/ledger/tx/${id}`),
  verifyLedger: () => api.post<T.VerifyResult>('/ledger/verify'),
  tamper: (height?: number) => api.post<Record<string, any>>('/ledger/tamper', { height }),
  revertTamper: () => api.post<{ reverted: string[] }>('/ledger/tamper/revert'),
  seal: () => api.post<T.Block | null>('/ledger/seal'),

  metrics: (window = 'all') => api.get<T.MetricsSummary>('/metrics/summary', { window }),
  timeseries: (series: 'sessions' | 'qber' = 'sessions', extra: Record<string, string | number> = {}) =>
    api.get<{ series: string; bucket_s?: number; points: any[] }>('/metrics/timeseries', { series, ...extra }),
};

export const qk = {
  health: ['health'] as const,
  config: ['config'] as const,
  selftest: ['selftest'] as const,
  network: ['network'] as const,
  reservoir: ['reservoir'] as const,
  sessions: (f: object = {}) => ['sessions', f] as const,
  session: (id: string) => ['session', id] as const,
  catalog: ['catalog'] as const,
  attackRuns: ['attackRuns'] as const,
  campaigns: ['campaigns'] as const,
  traffic: ['traffic'] as const,
  incidents: (f: object = {}) => ['incidents', f] as const,
  incident: (id: string) => ['incident', id] as const,
  metrics: (w = 'all') => ['metrics', w] as const,
  timeseries: (s: string, extra: object = {}) => ['timeseries', s, extra] as const,
  ledgerSummary: ['ledger', 'summary'] as const,
  blocks: ['ledger', 'blocks'] as const,
  block: (h: number) => ['ledger', 'block', h] as const,
  kinds: ['analyticsKinds'] as const,
  jobs: ['jobs'] as const,
  latest: (k: string) => ['latest', k] as const,
  detectors: ['detectors'] as const,
  baselines: ['baselines'] as const,
  detection: ['detection'] as const,
  linkMonitor: (id: string) => ['linkMonitor', id] as const,
};
