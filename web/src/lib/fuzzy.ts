/** Subsequence match with bonuses for word starts and consecutive runs. Returns -1 on no match. */
export function fuzzyScore(query: string, text: string): number {
  const q = query.toLowerCase().trim(), t = text.toLowerCase();
  if (!q) return 0;
  if (t.includes(q)) return 100 + (t.startsWith(q) ? 50 : 0) - t.indexOf(q) * 0.5;
  let score = 0, ti = 0, run = 0;
  for (const ch of q) {
    if (ch === ' ') continue;
    const idx = t.indexOf(ch, ti);
    if (idx < 0) return -1;
    const wordStart = idx === 0 || /[\s._\-/]/.test(t[idx - 1]);
    run = idx === ti ? run + 1 : 0;
    score += 1 + (wordStart ? 6 : 0) + run * 3 - Math.min(5, idx - ti) * 0.3;
    ti = idx + 1;
  }
  return score;
}
