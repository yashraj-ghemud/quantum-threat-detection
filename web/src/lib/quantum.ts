/* Exact single-qubit Bloch-vector math for the Playground (gates, states, ρ). */
export type V3 = [number, number, number];
const norm = (v: V3) => Math.hypot(v[0], v[1], v[2]);
export const unit = (v: V3): V3 => { const n = norm(v) || 1; return [v[0] / n, v[1] / n, v[2] / n]; };

/** Rodrigues rotation of v about unit axis k by angle θ (right-handed). */
export function rotate(v: V3, axis: V3, theta: number): V3 {
  const k = unit(axis), c = Math.cos(theta), s = Math.sin(theta);
  const dot = k[0] * v[0] + k[1] * v[1] + k[2] * v[2];
  const cross: V3 = [k[1] * v[2] - k[2] * v[1], k[2] * v[0] - k[0] * v[2], k[0] * v[1] - k[1] * v[0]];
  return [0, 1, 2].map((i) => v[i] * c + cross[i] * s + k[i] * dot * (1 - c)) as V3;
}

export interface Gate { id: string; label: string; axis: V3; angle: number; param?: boolean; desc: string }
const S2 = Math.SQRT1_2;
export const GATES: Gate[] = [
  { id: 'X', label: 'X', axis: [1, 0, 0], angle: Math.PI, desc: 'π about x̂ (bit flip)' },
  { id: 'Y', label: 'Y', axis: [0, 1, 0], angle: Math.PI, desc: 'π about ŷ' },
  { id: 'Z', label: 'Z', axis: [0, 0, 1], angle: Math.PI, desc: 'π about ẑ (phase flip)' },
  { id: 'H', label: 'H', axis: [S2, 0, S2], angle: Math.PI, desc: 'π about (x̂+ẑ)/√2: swaps X and Z' },
  { id: 'S', label: 'S', axis: [0, 0, 1], angle: Math.PI / 2, desc: 'π/2 about ẑ: x̂ → ŷ' },
  { id: 'Sdg', label: 'S†', axis: [0, 0, 1], angle: -Math.PI / 2, desc: '−π/2 about ẑ' },
  { id: 'T', label: 'T', axis: [0, 0, 1], angle: Math.PI / 4, desc: 'π/4 about ẑ' },
  { id: 'Rx', label: 'Rx(θ)', axis: [1, 0, 0], angle: 0, param: true, desc: 'θ about x̂' },
  { id: 'Ry', label: 'Ry(θ)', axis: [0, 1, 0], angle: 0, param: true, desc: 'θ about ŷ' },
  { id: 'Rz', label: 'Rz(θ)', axis: [0, 0, 1], angle: 0, param: true, desc: 'θ about ẑ' },
];

/** Polar angles of a Bloch vector. */
export function polar(v: V3) {
  const r = norm(v);
  if (r < 1e-12) return { r: 0, theta: 0, phi: 0 };
  return { r, theta: Math.acos(Math.max(-1, Math.min(1, v[2] / r))), phi: Math.atan2(v[1], v[0]) };
}
export const fromPolar = (theta: number, phi: number, r = 1): V3 => [r * Math.sin(theta) * Math.cos(phi), r * Math.sin(theta) * Math.sin(phi), r * Math.cos(theta)];

/** ρ = (I + r·σ)/2 as [[re, im]] entries. */
export function density(v: V3): { re: number[][]; im: number[][] } {
  const [x, y, z] = v;
  return { re: [[(1 + z) / 2, x / 2], [x / 2, (1 - z) / 2]], im: [[0, -y / 2], [y / 2, 0]] };
}
/** Amplitudes (α, β) of the pure state with the direction of v (global phase: α real ≥ 0). */
export function amplitudes(v: V3) {
  const { theta, phi } = polar(v);
  return { a: Math.cos(theta / 2), bRe: Math.sin(theta / 2) * Math.cos(phi), bIm: Math.sin(theta / 2) * Math.sin(phi) };
}
export const purity = (v: V3) => (1 + norm(v) ** 2) / 2;
export const applyAffine = (M: number[][], c: number[], v: V3): V3 => [0, 1, 2].map((i) => M[i][0] * v[0] + M[i][1] * v[1] + M[i][2] * v[2] + c[i]) as V3;
export function nearestLabel(v: V3): number {
  const dirs: V3[] = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
  let best = 4, bd = -Infinity;
  dirs.forEach((d, i) => { const dot = d[0] * v[0] + d[1] * v[1] + d[2] * v[2]; if (dot > bd) { bd = dot; best = i; } });
  return best;
}
export { norm };
