/* Types for the QVeris API (hand-written from the backend reports; see
   docs/plan/01_BACKEND_PLAN.md §12). Loose where the engine adds detail. */
export type Verdict = 'ACCEPTED' | 'REJECTED' | 'CERTIFIED' | 'COMPROMISED';
export type Severity = 'NONE' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type Category = 'NONE' | 'FORGERY' | 'IMPERSONATION' | 'REPLAY' | 'UNAUTHORIZED_VERIFICATION' | 'CHANNEL_MANIPULATION' | 'REPUDIATION' | 'DEGRADED';
export type Basis = 'x' | 'y' | 'z';
export type Dict<T = unknown> = Record<string, T>;

export interface Health { status: string; version: string; engine_version: string; uptime_s: number; ws_clients: number; preset: string; time: number; env: string }

export interface NodeInfo { id: string; name: string; role: 'signer' | 'verifier' | 'adversary'; label: string; color: string; hidden: boolean; suspended: boolean; meta: Dict; pos: [number, number, number] }
export interface ChannelSpec { type: string; [k: string]: unknown }
export interface MonitorPoint { t: number; qber: number; chsh: number; fidelity: number; cusum_qber: number; cusum_chsh: number; ewma_qber: number; h_qber?: number | null; h_chsh?: number | null; alarm: boolean | number; bundle_id?: string; link_id?: string; excluded?: boolean }
export interface LinkInfo {
  id: string; kind: 'quantum' | 'classical'; a: string; b: string; length_km: number; status: 'ACTIVE' | 'DEGRADED' | 'QUARANTINED' | string;
  status_reason: string | null; authenticated_classical: boolean; baseline_channel: ChannelSpec[] | null; hidden: boolean;
  transmittance?: number; last?: MonitorPoint | null; baseline?: { calibrated_at: number; qber: number; chsh: number; fidelity: number; samples: number } | null;
}
export interface GroupInfo { id: string; signer_id: string; recipients: string[]; hidden: boolean; reservoir_target: number }
export interface Network { nodes: NodeInfo[]; links: LinkInfo[]; groups: GroupInfo[] }

export interface ReservoirEntry { group_id: string; signer_id: string; recipients: string[]; active: number; target: number; signed: number; consumed_total: number; compromised_total: number; revoked_total: number; burned_total: number; last_distribution_at: number | null; blocked_reason: string | null }

export interface Finding {
  id: string; name: string; layer: string; fired: boolean; severity: Severity; conclusive: boolean;
  statistic: { name: string; value: number } | null; p_value: number | null; alpha: number | null; effect: number | null;
  evidence: string; link_id: string | null; data: Dict; candidate?: boolean; log10_p?: number | null;
}
export interface Classification { category: Category; subtype: string | null; confidence: string; rule: string; explanation: string; alternatives: string[]; attributed_to: string | null }
export interface Assessment { verdict: Verdict; threat_level: Severity; threat_score: number; classification: Classification; findings: Finding[]; recommended_actions: string[] }

export interface Design {
  L: number; digest_bits: number; e_ucb: number; p_forge: number; n_nom: number; n_min: number; c_a: number; c_v: number; s_a: number; s_v: number;
  feasible: boolean; eps_rob_msg: number; eps_rob_set: number; eps_inconclusive: number; eps_forge_key: number; eps_forge_chernoff: number;
  eps_rep_key: number; eps_rep_msg: number; targets: { eps_rob: number; eps_forge: number; eps_rep: number };
  meets_targets: { robustness: boolean; forgery: boolean; repudiation: boolean }; L_min: number | null;
  sprt: { p0: number; p1: number; alpha: number; beta: number; A: number; B: number };
  pmf_honest?: { n: number; p: number; k0: number; pmf: number[] }; pmf_forger?: { n: number; p: number; k0: number; pmf: number[] };
}
export interface Rate { errors: number; n: number; rate: number }
export interface BellResult { n_per_setting: number[]; E: Dict<number>; S: number; S_lcb: number; S_se: number; F: number; F_lcb: number; F_se: number; predicted_error: Dict<Rate>; counts: number[][] }
export interface Tomo { M: number[][]; c: number[]; M_se: number[][]; c_se: number[]; r: number[]; n: number[]; plus: number[] }
export interface LinkEvidence {
  link_id: string; verifier_id: string; bell: BellResult;
  pe: { n: number; qber: number; errors: number; matched: number; per_basis: Dict<Rate> };
  tomography: { detwirled: Tomo; effective: Tomo; frames?: Tomo[] };
  frame: { compared: number; mismatched: number; rate: number; flip_rates: { m0: number; m1: number }; matrix: number[][]; mac: string };
  hardware_time_ms_modelled: number; sample: { label: number; sent: number; k: number; c: number; basis: number; outcome: number; pe: boolean }[];
  baseline: { link_id: string; calibrated_at: number; samples: number; qber: number; qber_per_basis: Dict<number>; S: number; S_se: number; F: number; M: number[][]; c: number[] };
  monitor: MonitorPoint | null; findings: Finding[]; fingerprint?: Dict;
}
export interface DistributionReport {
  session_id: string; kind: 'distribution'; created_at: number; origin: string; bundle_id: string; group_id: string; signer_id: string; recipients: string[];
  preset: string; params: Dict; qubits_teleported: number; bell_pairs: number; links: LinkEvidence[]; symmetrization: Dict; design: Design; e_ucb: number;
  assessment: Assessment; verdict: Verdict; status: string; latency_ms: Dict<number>; hardware_time_ms_modelled: number; injected_attack: InjectedAttack | null;
  incident_id?: string | null; ledger?: { tx_id: string | null; status: string };
}
export interface SprtTrace { key: number; set: string; trace: number[][]; decision: string }
export interface Verification {
  verifier_id: string; role: string; mode: string; threshold: number; n_min: number; decision: 'ACCEPT' | 'REJECT' | 'SKIPPED';
  keys: { n_own: number[]; m_own: number[]; n_recv: number[]; m_recv: number[]; pass: number[]; inconclusive: number[] };
  failed_keys: number[]; totals: { tested: number; mismatches: number; rate: number };
  sprt: { enabled: boolean; early_reject: boolean; reject_key: number | null; observations_used: number; observations_available: number; fraction_read: number; A: number; B: number; p0: number; p1: number; traces: SprtTrace[] };
  grid_sample: { keys: number; positions: number; fields: string[]; cells: number[][][]; bits: number[] };
  latency_ms: number; guard: Finding[];
}
export interface SignatureReport {
  session_id: string; kind: 'signature'; created_at: number; origin: string; group_id: string; bundle_id: string | null; encoding: string;
  envelope: { group_id: string; signer_id: string; recipients: string[]; bundle_id: string; seq: number; timestamp: number; nonce: string; message: string; encoding: string; protocol: string };
  digest: { hex: string; bits: string; oracle: boolean };
  signature: { sha256: string; size_bytes: number; revealed_sample: number[] };
  verifications: Verification[]; assessment: Assessment; verdict: Verdict; design: Design | null; eps: Dict<number>; latency_ms: Dict<number>;
  stage: string; injected_attack: InjectedAttack | null; counterfactual: boolean; notes: string[]; incident_id?: string | null; ledger?: { tx_id: string | null; status: string };
}
export type Report = DistributionReport | SignatureReport;
export interface InjectedAttack { attack_id: string; category: Category; intensity?: number }

export interface SessionSummary {
  id: string; kind: 'signature' | 'distribution'; created_at: number; origin: string; group_id: string; signer_id: string; recipients: string[];
  bundle_id: string | null; verdict: Verdict; threat_level: Severity; category: Category; subtype: string | null; threat_score: number;
  injected_attack: InjectedAttack | null; latency_ms: number; message_preview?: string; qubits?: number;
  decisions?: { first: string; transfer: string }; links?: { link_id: string; verifier_id: string; S: number; qber: number; frame_mismatch: number }[];
}

export interface CatalogParam { name: string; type: 'enum' | 'float' | 'int' | 'bool' | string; options?: (string | number)[]; default?: unknown; min?: number; max?: number; step?: number; description?: string }
export interface CatalogEntry {
  id: string; category: Category; subtype: string; phase: 'distribution' | 'signing'; name: string; icon: string; summary: string; physics: string;
  knowledge: string[]; intensity: { param: string | null; scale?: number; formula: string } | null; params: CatalogParam[]; detection: string[]; honesty?: string;
}
export interface AttackRunReport {
  id?: string; attack: { attack_id: string; intensity: number; params: Dict; target: string }; catalog_entry: CatalogEntry; phase: string;
  distribution: DistributionReport | null; signature: SignatureReport | null; setup: SignatureReport[];
  counterfactual: { defence: string; description?: string; verdict?: string; breach: boolean; outcome: string; [k: string]: unknown } | null;
  detected: boolean; correctly_classified: boolean; expected_category: Category; detected_category: Category; detected_subtype: string | null;
  verdict: Verdict; threat_level: Severity; notes: string[]; incident_id?: string | null; created_at?: number; [k: string]: unknown;
}
export interface AttackRunSummary { id: string; attack_id: string; category: Category; group_id: string; origin: string; detected: boolean; correctly_classified: boolean; created_at: number; verdict?: Verdict; intensity?: number }

export interface Incident {
  id: string; created_at: number; updated_at: number; severity: Severity; category: Category; subtype: string | null; title: string; summary: string;
  link_id: string | null; group_id: string | null; session_id: string | null; bundle_id: string | null; occurrences: number;
  status: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'; attributed_to: string | null; ledger_tx_id: string | null; recommended: string[];
  actions?: { at: number; action: string; result?: unknown; note?: string }[]; notes?: unknown[]; evidence?: Finding[]; [k: string]: unknown;
}

export interface MetricsSummary {
  window: string; generated_at: number;
  sessions: { signature_total: number; accepted: number; rejected: number; by_origin: Dict<number> };
  distributions: { total: number; certified: number; compromised: number };
  detection: { legit_runs: number; false_rejections: number; frr: number | null; frr_ci: [number, number] | null; attack_runs: number; detected: number; far: number | null; far_ci: [number, number] | null;
    detection_rate: number | null; correctly_classified: number; classification_accuracy: number | null;
    per_category: { category: Category; runs: number; detected: number; correct: number; rate: number | null; ci: [number, number] | null }[] };
  throughput_per_min: number; latency_ms: { p50: number | null; p95: number | null }; mean_chsh_recent: number | null; links?: LinkInfo[];
  incidents?: Dict; ledger?: Dict; reservoir?: Dict; threat_level?: Severity; [k: string]: unknown;
}
export interface MetricsTick { sessions_per_min: number; accepted_last_min: number; rejected_last_min: number; threat_level: Severity; open_incidents: number; ledger_height: number; reservoir_total: number; [k: string]: unknown }
export interface TimeseriesPoint { t: number; signatures: number; accepted: number; rejected: number; distributions: number; compromised: number; attacks: number; latency_ms?: number | null; [k: string]: unknown }

export interface TrafficState { running: boolean; paused_idle: boolean; rate_per_min: number; generated: number; started_at: number | null; last_session_at: number | null; groups: string[] | null; errors: number; autostart: boolean; blocked?: Record<string, string> }
export interface Campaign { id: string; name: string; preset: string | null; mix: { attack: { attack_id: string; intensity?: number }; weight: number }[]; rate_per_min: number; duration_s: number; started_at: number; ends_at?: number; runs: number; detected: number; state: string; [k: string]: unknown }

export interface LedgerSummary { height: number; head_hash: string; tx_total: number; pending: number; last_verification: { at: number; valid: boolean; first_invalid_height: number | null } | null; tamper_demo_enabled: boolean; tampered: string[] }
export interface Block { height: number; hash: string; prev_hash: string; merkle_root: string; timestamp: number; tx_count: number; [k: string]: unknown }
export interface LedgerTx { id: string; kind: string; ref_id?: string | null; created_at: number; payload: Dict; payload_hash?: string; block_height?: number | null; idx?: number; proof?: { hash: string; side: string }[] | Dict[]; merkle_root?: string; [k: string]: unknown }
export interface BlockDetail { block: Block; txs: (LedgerTx & { idx: number; payload_hash: string; valid: boolean })[]; merkle_levels: string[][] }
export interface VerifyResult { valid: boolean; checked_blocks: number; checked_txs: number; first_invalid_height: number | null; issues: { height: number; tx_id?: string; kind: string; detail?: string }[]; downstream_blocks: number; duration_ms: number; at: number }

export interface JobKind { kind: string; title: string; description: string; presets: Dict; eta?: Dict; [k: string]: unknown }
export interface Job { id: string; kind: string; preset: string; params: Dict; status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED'; progress: number; message: string | null; result: any; error?: string | null; created_at?: number; started_at?: number | null; finished_at?: number | null }

export interface SelftestCheck { id: string; name: string; status: 'pending' | 'running' | 'pass' | 'fail' | 'skip'; detail: string; duration_ms: number | null; metrics: Dict }
export interface Selftest { state: 'idle' | 'running' | 'done'; started_at: number | null; finished_at: number | null; checks: SelftestCheck[] }

export interface PresetInfo { preset: string; digest_bits: number; L: number; f_pe: number; bell_pairs_per_setting: number; eps_rob_target: number; eps_forge_target: number; eps_rep_target: number; qubits?: number; [k: string]: unknown }
export interface SystemConfig {
  presets: Dict<PresetInfo>; active_preset: string; detection: Dict; features: { tamper_demo: boolean; mac: boolean; api_key_required: boolean };
  channel_types: Dict<{ label: string; params: { name: string; type: string; min?: number; max?: number; step?: number; default?: unknown; options?: string[] }[]; description: string }>;
  categories: Dict; limits: Dict; hardware_model: Dict<number>;
}
export interface TheoryLink { S: number; F: number; qber_per_basis: Dict<number>; qber: number; E: Dict<number>; M: number[][]; c: number[]; twirled_M: number[][]; twirled_c: number[] }
export interface PlaygroundChannel { kraus: { re: number[][]; im: number[][] }[]; ptm: number[][]; M: number[][]; c: number[]; choi_eigenvalues: number[]; cptp: boolean; twirled: { M: number[][]; c: number[] }; predicted: { S: number; F: number; qber_per_basis: Dict<number>; qber: number } }
export interface TeleportOutcome { k: number; bits: [number, number]; prob: number; bloch_pre: number[]; bloch_post: number[]; received: Dict; [k: string]: unknown }
export interface PlaygroundTeleport { input_bloch: number[]; outcomes: TeleportOutcome[]; average_bloch: number[]; fidelity: number | null; samples?: { basis: Basis; shots: number; counts: { '0': number; '1': number }; born_p0: number; frames: Dict<number> } }

export interface WsEvent<T = any> { v: number; topic: string; type: string; ts: number; id: number; data: T }
