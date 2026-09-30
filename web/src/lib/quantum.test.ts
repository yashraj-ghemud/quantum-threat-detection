import { describe, it, expect } from 'vitest';
import { rotate, GATES, density, amplitudes, purity, polar, fromPolar, applyAffine, type V3 } from './quantum';

const g = (id: string) => GATES.find((x) => x.id === id)!;
const close = (a: V3, b: V3) => a.forEach((x, i) => expect(x).toBeCloseTo(b[i], 12));

describe('gate rotations', () => {
  it('preserve the norm', () => {
    const v: V3 = [0.3, -0.4, 0.5];
    for (const gt of GATES) { const w = rotate(v, gt.axis, gt.angle || 0.7); expect(Math.hypot(...w)).toBeCloseTo(Math.hypot(...v), 12); }
  });
  it('H maps z to x and x to z', () => { close(rotate([0, 0, 1], g('H').axis, g('H').angle), [1, 0, 0]); close(rotate([1, 0, 0], g('H').axis, g('H').angle), [0, 0, 1]); });
  it('S maps x to y', () => close(rotate([1, 0, 0], g('S').axis, g('S').angle), [0, 1, 0]));
  it('X flips z', () => close(rotate([0, 0, 1], g('X').axis, g('X').angle), [0, 0, -1]));
});

describe('states', () => {
  it('density matrix of |+i> has the right coherences', () => { const d = density([0, 1, 0]); expect(d.im[0][1]).toBeCloseTo(-0.5); expect(d.re[0][0]).toBeCloseTo(0.5); });
  it('amplitudes of |1> are (0, 1)', () => { const a = amplitudes([0, 0, -1]); expect(a.a).toBeCloseTo(0); expect(Math.hypot(a.bRe, a.bIm)).toBeCloseTo(1); });
  it('purity of the maximally mixed state is 1/2', () => expect(purity([0, 0, 0])).toBeCloseTo(0.5));
  it('polar round trip', () => { const v: V3 = [0.2, 0.5, -0.3]; const p = polar(v); close(fromPolar(p.theta, p.phi, p.r), v); });
  it('affine map', () => close(applyAffine([[0.5, 0, 0], [0, 0.5, 0], [0, 0, 1]], [0, 0, 0.1], [1, 0, 0]), [0.5, 0, 0.1]));
});
