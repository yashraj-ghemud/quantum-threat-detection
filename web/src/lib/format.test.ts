import { describe, it, expect } from 'vitest';
import { sci, pct, int, ms, shortHash } from './format';
import { fuzzyScore } from './fuzzy';

describe('format', () => {
  it('scientific notation with true superscripts', () => { expect(sci(3.1e-10)).toBe('3.1 × 10⁻¹⁰'); expect(sci(0.0123)).toBe('0.0123'); expect(sci(null)).toBe('—'); });
  it('percent', () => expect(pct(0.01234, 2)).toBe('1.23 %'));
  it('thin-space grouping', () => expect(int(2330624)).toBe('2 330 624'));
  it('durations', () => { expect(ms(41)).toBe('41 ms'); expect(ms(2300)).toBe('2.30 s'); expect(ms(0.5)).toBe('500 µs'); });
  it('short hash', () => expect(shortHash('0123456789abcdef', 4, 2)).toBe('0123…ef'));
});
describe('fuzzy', () => {
  it('prefers word starts and substrings', () => {
    expect(fuzzyScore('att lab', 'Attack Lab')).toBeGreaterThan(fuzzyScore('att lab', 'Start traffic label'));
    expect(fuzzyScore('zzz', 'Attack Lab')).toBe(-1);
  });
});
