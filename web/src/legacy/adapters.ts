/* Adapters: real QVeris engine reports → the data contracts of the original
   scenes (dashboard/web/*.js). Every number shown by a scene comes from here,
   and everything here comes from an API response. */
import type { AttackRunReport, CatalogEntry, DistributionReport, LinkEvidence, MetricsSummary, SignatureReport, Verification, PlaygroundTeleport } from '@/api/types';
import { LABEL_BASIS, LABEL_BIT, LABEL_KET, BASIS_NAME } from '@/lib/color';
import { catLabel, pct, fix, sci } from '@/lib/format';

const LEGACY_KET = ['|+>', '|->', '|+i>', '|-i>', '|0>', '|1>'];
const LEGACY_TYPE: Record<string, string> = {
  FORGERY: 'FORGERY', IMPERSONATION: 'IMPERSONATION', REPLAY: 'REPLAY', UNAUTHORIZED_VERIFICATION: 'UNAUTHORIZED_VERIFICATION',
  CHANNEL_MANIPULATION: 'CHANNEL_MANIPULATION', REPUDIATION: 'FORGERY', NONE: 'NONE',
};

async function sha256hex(s: string): Promise<string> {
  try {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
    return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
  } catch { return ''; }
}

/** The configured (not yet measured) attack, with the rules from the catalog entry. */
export function labConfig(entry: CatalogEntry | null, intensity: number, message: string, digest = '', n = 24) {
  if (!entry) return { type: 'NONE', name: 'legitimate session', intensity: 0, n, message, digest, lines: ['honest signing over the calibrated links', 'expected: every key verifies at both recipients'] };
  const I = +intensity;
  const lines: string[] = [];
  if (entry.intensity?.formula) lines.push(`${entry.intensity.formula.replace(/I\b/g, `I = ${I.toFixed(2)}`)}`);
  lines.push(entry.physics.length > 150 ? entry.physics.slice(0, 147) + '…' : entry.physics);
  if (entry.detection?.length) lines.push(`caught by ${entry.detection.join(' · ')}`);
  const hit = entry.category === 'CHANNEL_MANIPULATION' || entry.category === 'UNAUTHORIZED_VERIFICATION' ? Math.min(1, 0.25 + I) :
    entry.category === 'REPLAY' || entry.category === 'IMPERSONATION' && entry.subtype === 'identity_swap' ? 0 : 0.5;
  return { type: LEGACY_TYPE[entry.category] || 'FORGERY', name: entry.name.toLowerCase(), intensity: I, n, message, digest, lines, hit_fraction: hit };
}

function keyRate(v: Verification, i: number) {
  const n = (v.keys.n_own[i] || 0) + (v.keys.n_recv[i] || 0);
  const m = (v.keys.m_own[i] || 0) + (v.keys.m_recv[i] || 0);
  return n ? m / n : 0;
}

/** Tested cells of a verifier's grid sample → scene elements. */
export function verificationElements(v: Verification, max = 48) {
  const g = v.grid_sample; if (!g) return [];
  const out: { label: string; basis: string; match: boolean; purity: number; p0: number; expected: number; measured: number; p_plus: number; key: number }[] = [];
  const rows = g.cells.length, cols = rows ? g.cells[0].length : 0;
  // Interleave keys so the ring shows many keys, not one key's positions.
  for (let j = 0; j < cols && out.length < max; j++) {
    for (let i = 0; i < rows && out.length < max; i++) {
      const c = g.cells[i][j]; // [basis, outcome, set, tested, mismatch, label]
      if (!c || c[3] !== 1) continue;
      const lab = c[5];
      const rate = keyRate(v, i);
      const r = Math.max(0, 1 - 2 * rate);
      const expected = LABEL_BIT[lab] ? -1 : 1;
      const measured = c[1] === 1 ? -1 : 1;
      out.push({ label: LEGACY_KET[lab], basis: BASIS_NAME[LABEL_BASIS[lab]], match: c[4] === 0, purity: (1 + r * r) / 2, p0: 1 - rate,
        expected, measured, p_plus: expected === 1 ? 1 - rate : rate, key: i });
    }
  }
  return out;
}

function linkElements(ev: LinkEvidence, max = 32) {
  const r6 = ev.tomography?.detwirled?.r || [];
  const out: ReturnType<typeof verificationElements> = [];
  for (const s of ev.sample || []) {
    if (out.length >= max) break;
    if (s.basis !== LABEL_BASIS[s.label]) continue;
    const r = Math.max(0, Math.min(1, r6[s.label] ?? 1));
    const expected = LABEL_BIT[s.label] ? -1 : 1, measured = s.outcome ? -1 : 1;
    out.push({ label: LEGACY_KET[s.label], basis: BASIS_NAME[s.basis], match: s.outcome === LABEL_BIT[s.label], purity: (1 + r * r) / 2, p0: (1 + r) / 2,
      expected, measured, p_plus: (1 + expected * r) / 2, key: -1 });
  }
  return out;
}

function worstLink(d: DistributionReport | null): LinkEvidence | null {
  if (!d?.links?.length) return null;
  return [...d.links].sort((a, b) => (b.pe?.qber ?? 0) - (a.pe?.qber ?? 0))[0];
}

/** A measured attack run → the Attack Lab film input. */
export async function labResult(run: AttackRunReport, entry: CatalogEntry | null, message: string) {
  const sig = run.signature as SignatureReport | null;
  const dist = run.distribution as DistributionReport | null;
  const design = sig?.design || dist?.design || null;
  const first = sig?.verifications?.[0] || null;
  const link = worstLink(dist);
  const distPhase = run.phase === 'distribution';
  const elements = distPhase && link ? linkElements(link) : first ? verificationElements(first) : [];
  const n = Math.max(elements.length, 8);
  const digest = sig?.digest?.hex || (await sha256hex(message));
  const config = { ...labConfig(entry, run.attack.intensity, message, digest, n), n };
  const assessment = distPhase ? dist?.assessment : sig?.assessment;
  const cls = assessment?.classification;
  const detected = run.detected;
  const fired = (assessment?.findings || []).filter((f) => f.fired);
  let anomaly: number, mismatch: number, verification: number;
  const labels: Record<string, string> = { threshold: 's_a' };
  if (distPhase && link) {
    anomaly = link.pe.qber; mismatch = link.pe.qber; verification = Math.max(0, link.bell.F_lcb);
    labels.anomaly = 'Link QBER'; labels.mismatch = 'PE error rate'; labels.verification = 'Bell fidelity (LCB)';
  } else if (first) {
    let worst = 0; for (let i = 0; i < first.keys.pass.length; i++) worst = Math.max(worst, keyRate(first, i));
    anomaly = worst; mismatch = first.totals.rate;
    verification = first.keys.pass.length ? first.keys.pass.reduce((a, b) => a + b, 0) / first.keys.pass.length : 0;
    labels.anomaly = 'Worst key mismatch'; labels.mismatch = 'Mismatch rate'; labels.verification = 'Keys passed';
  } else { anomaly = 0; mismatch = 0; verification = 0; }
  const verdict = distPhase ? dist?.verdict : sig?.verdict;
  const result = {
    id: run.id || `${run.attack.attack_id}-${run.created_at || Date.now()}`,
    config,
    classification: detected ? (assessment?.threat_level === 'MEDIUM' || assessment?.threat_level === 'LOW' ? 'SUSPICIOUS' : 'THREAT') : entry ? 'MISSED' : 'LEGITIMATE',
    verdict_label: `${verdict || '—'}${cls && cls.category !== 'NONE' ? ` · ${catLabel(cls.category)}` : ''}`,
    verdict_sub: detected ? `${cls?.subtype ? cls.subtype.replace(/_/g, ' ') + ' · ' : ''}${run.correctly_classified ? 'correctly classified' : 'classified as ' + catLabel(run.detected_category)}`
      : entry ? 'attack passed undetected' : 'session verified',
    authorization: run.expected_category === 'UNAUTHORIZED_VERIFICATION' && detected ? 'UNAUTHORIZED' : 'AUTHORIZED',
    anomaly, threshold: design?.s_a ?? null, critical: design?.p_forge ?? 1 / 3, mismatch_rate: mismatch, verification, labels,
    elements, reason: cls?.explanation || '', evidence: fired.slice(0, 3).map((f) => f.evidence),
    missed_note: 'The statistics stayed inside the calibrated baseline and every protocol check passed.',
    doc_rows: [
      ['decision', `${verdict} · ${catLabel(cls?.category)}`],
      ['attack', `${entry?.name || 'none'} · I = ${run.attack.intensity.toFixed(2)}`],
      [labels.anomaly || 'statistic', `${fix(anomaly, 4)}  vs s_a ${fix(design?.s_a ?? null, 4)}`],
      [labels.verification || 'verification', fix(verification, 4)],
      ['detectors fired', String(fired.length)],
    ],
  };
  return { config, result };
}

/** A signature report → Signature Constellation input. */
export function verifyPayload(rep: SignatureReport, verifierIndex = 0) {
  const v = rep.verifications[verifierIndex] || rep.verifications[0];
  const els = verificationElements(v, 48);
  const matches = els.filter((e) => e.match).length;
  const s = v.threshold;
  const accepted = v.decision === 'ACCEPT';
  return {
    n: els.length, threshold: 1 - s, score: 1 - v.totals.rate, matches, accepted, seed: rep.envelope?.seq ?? 0,
    message: `${rep.session_id}|${v.verifier_id}`, elements: els.map((e) => ({ label: e.label, basis: e.basis, expected: e.expected, measured: e.measured, match: e.match, p_plus: e.p_plus })),
    sub: `${v.verifier_id} · ${els.length} sampled qubits · 1 − s = ${(1 - s).toFixed(3)}`,
    rows: [
      ['match rate (all tested)', (1 - v.totals.rate).toFixed(4), accepted ? 'good' : 'bad'],
      ['accept bound 1 − s', (1 - s).toFixed(3), ''],
      ['keys passed', `${v.keys.pass.reduce((a, b) => a + b, 0)} / ${v.keys.pass.length}`, accepted ? 'good' : 'bad'],
      ['tested positions', `${v.totals.tested}`, ''],
      ['decision', accepted ? 'ACCEPT' : 'REJECT', accepted ? 'good' : 'bad'],
    ],
    note: `<span class="h">HOW ${v.verifier_id.toUpperCase()} DECIDES</span>` +
      `the ring shows ${els.length} of ${v.totals.tested} tested qubits (real outcomes). A key passes when its mismatches m ≤ s·n on the positions measured in the revealed basis; ` +
      `the signature is accepted when all ${v.keys.pass.length} keys pass${v.sprt?.enabled ? ' and the SPRT never crossed its reject bound' : ''}.`,
  };
}

/** Playground teleport response → Channel Anatomy input. */
export function noisePayload(t: PlaygroundTeleport, type: string, p: number, label: number) {
  const r = t.average_bloch;
  const len = Math.hypot(r[0], r[1], r[2]);
  const fid = t.fidelity ?? (1 + (t.input_bloch[0] * r[0] + t.input_bloch[1] * r[1] + t.input_bloch[2] * r[2])) / 2;
  return { noise_type: type, p, state: LEGACY_KET[label], fidelity: fid, purity: (1 + len * len) / 2, ideal: t.input_bloch, received: r };
}

/** Real headline metrics for the story's finale chips. */
export function storyMetrics(m: MetricsSummary | undefined | null) {
  if (!m) return null;
  const d = m.detection;
  const chips: [string, string][] = [
    ['attacks detected', d.attack_runs ? `${d.detected}/${d.attack_runs}` : 'none run yet'],
    ['classification', d.classification_accuracy != null ? pct(d.classification_accuracy, 1) : 'n/a'],
    ['false alarms', d.legit_runs ? `${d.false_rejections}/${d.legit_runs}` : 'n/a'],
    ['mean CHSH S', m.mean_chsh_recent != null ? fix(m.mean_chsh_recent, 3) : 'n/a'],
  ];
  return { chips, source: `measured · live engine · ${m.sessions.signature_total} signatures, ${m.distributions.total} distributions` };
}

export { LABEL_KET, sci };
