"""
sentinel/stats.py
=================
Statistical toolkit for QSentinel. Closed-form and exact methods only.

Everything here is a standard, textbook procedure: exact binomial and
hypergeometric tails, Clopper-Pearson intervals, Hoeffding and Chernoff-KL
bounds, two-proportion tests with a Fisher exact fallback, Pearson
chi-square homogeneity, and the Holm-Bonferroni step-down procedure.

No AI/ML is used.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy import stats as _st

__all__ = [
    "P_FLOOR",
    "binom_sf",
    "binom_cdf",
    "clopper_pearson",
    "cp_upper",
    "cp_lower",
    "hoeffding_halfwidth",
    "kl_bernoulli",
    "chernoff_upper_tail",
    "chernoff_lower_tail",
    "two_proportion_test",
    "chi2_homogeneity",
    "holm",
    "hypergeom_split_tail",
    "log10p",
]

#: Smallest p-value reported (avoids log(0) in the UI).
P_FLOOR = 1e-300


def _clip_p(p: float) -> float:
    if not math.isfinite(p):
        return 1.0
    return float(min(1.0, max(P_FLOOR, p)))


def log10p(p: float) -> float:
    return float(math.log10(_clip_p(p)))


def binom_sf(m: int, n: int, p: float) -> float:
    """P(Bin(n, p) >= m)."""
    if m <= 0:
        return 1.0
    if m > n:
        return 0.0
    return float(_st.binom.sf(m - 1, n, p))


def binom_cdf(m: int, n: int, p: float) -> float:
    """P(Bin(n, p) <= m)."""
    if m < 0:
        return 0.0
    if m >= n:
        return 1.0
    return float(_st.binom.cdf(m, n, p))


def clopper_pearson(x: int, n: int, delta: float = 0.05) -> tuple[float, float]:
    """Exact two-sided (1 - delta) interval for a binomial proportion."""
    if n <= 0:
        return 0.0, 1.0
    lo = 0.0 if x <= 0 else float(_st.beta.ppf(delta / 2.0, x, n - x + 1))
    hi = 1.0 if x >= n else float(_st.beta.ppf(1.0 - delta / 2.0, x + 1, n - x))
    return lo, hi


def cp_upper(x: int, n: int, delta: float) -> float:
    """One-sided exact upper (1 - delta) bound."""
    if n <= 0 or x >= n:
        return 1.0
    return float(_st.beta.ppf(1.0 - delta, x + 1, n - x))


def cp_lower(x: int, n: int, delta: float) -> float:
    """One-sided exact lower (1 - delta) bound."""
    if n <= 0 or x <= 0:
        return 0.0
    return float(_st.beta.ppf(delta, x, n - x + 1))


def hoeffding_halfwidth(n: int, delta: float, value_range: float = 1.0) -> float:
    """Two-sided Hoeffding half-width for the mean of n bounded samples."""
    if n <= 0:
        return float("inf")
    return float(math.sqrt(value_range ** 2 * math.log(2.0 / delta) / (2.0 * n)))


def kl_bernoulli(q: float, p: float) -> float:
    """KL(Bern(q) || Bern(p))."""
    eps = 1e-300
    q = min(max(q, 0.0), 1.0)
    p = min(max(p, eps), 1 - 1e-16)
    a = 0.0 if q == 0 else q * math.log(q / p)
    b = 0.0 if q == 1 else (1 - q) * math.log((1 - q) / (1 - p))
    return a + b


def chernoff_upper_tail(n: int, p: float, q: float) -> float:
    """exp(-n KL(q||p)) bounds P(Bin(n,p) >= n q) for q > p."""
    if q <= p:
        return 1.0
    return float(math.exp(-n * kl_bernoulli(q, p)))


def chernoff_lower_tail(n: int, p: float, q: float) -> float:
    """exp(-n KL(q||p)) bounds P(Bin(n,p) <= n q) for q < p."""
    if q >= p:
        return 1.0
    return float(math.exp(-n * kl_bernoulli(q, p)))


def two_proportion_test(x1: int, n1: int, x2: int, n2: int,
                        alternative: str = "two-sided") -> dict:
    """Compare two binomial proportions p1 = x1/n1 and p2 = x2/n2.

    ``alternative``: ``'two-sided'``, ``'greater'`` (p1 > p2) or ``'less'``.
    Uses the pooled z-test; falls back to Fisher's exact test when any
    expected cell count is below 10.
    """
    if n1 <= 0 or n2 <= 0:
        return {"p_value": 1.0, "z": 0.0, "method": "none", "p1": 0.0, "p2": 0.0, "diff": 0.0}
    p1, p2 = x1 / n1, x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    expected = [n1 * pooled, n1 * (1 - pooled), n2 * pooled, n2 * (1 - pooled)]
    if min(expected) < 10:
        table = [[x1, n1 - x1], [x2, n2 - x2]]
        alt = {"two-sided": "two-sided", "greater": "greater", "less": "less"}[alternative]
        _, p = _st.fisher_exact(table, alternative=alt)
        return {"p_value": _clip_p(float(p)), "z": float("nan"), "method": "fisher",
                "p1": p1, "p2": p2, "diff": p1 - p2}
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return {"p_value": 1.0, "z": 0.0, "method": "z", "p1": p1, "p2": p2, "diff": p1 - p2}
    z = (p1 - p2) / se
    if alternative == "greater":
        p = _st.norm.sf(z)
    elif alternative == "less":
        p = _st.norm.cdf(z)
    else:
        p = 2 * _st.norm.sf(abs(z))
    return {"p_value": _clip_p(float(p)), "z": float(z), "method": "z", "p1": p1, "p2": p2, "diff": p1 - p2}


def chi2_homogeneity(plus_a: np.ndarray, n_a: np.ndarray,
                     plus_b: np.ndarray, n_b: np.ndarray) -> dict:
    """Pearson chi-square homogeneity over independent two-outcome cells.

    Each cell contributes the statistic of its 2x2 table
    ``[[plus_a, n_a - plus_a], [plus_b, n_b - plus_b]]`` with one degree of
    freedom. Degenerate cells (a zero margin) are skipped.
    """
    pa = np.asarray(plus_a, dtype=float).ravel()
    na = np.asarray(n_a, dtype=float).ravel()
    pb = np.asarray(plus_b, dtype=float).ravel()
    nb = np.asarray(n_b, dtype=float).ravel()
    stat = 0.0
    df = 0
    for a1, a, b1, b in zip(pa, na, pb, nb):
        if a <= 0 or b <= 0:
            continue
        pooled = (a1 + b1) / (a + b)
        if pooled <= 0 or pooled >= 1:
            continue
        for obs, tot in ((a1, a), (b1, b)):
            e1 = tot * pooled
            e0 = tot * (1 - pooled)
            stat += (obs - e1) ** 2 / e1 + ((tot - obs) - e0) ** 2 / e0
        df += 1
    p = float(_st.chi2.sf(stat, df)) if df > 0 else 1.0
    return {"statistic": float(stat), "df": int(df), "p_value": _clip_p(p)}


def holm(pvalues: Sequence[float], alpha: float) -> list[bool]:
    """Holm-Bonferroni step-down. Returns rejection flags in input order."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    reject = [False] * m
    for rank, idx in enumerate(order):
        if pvalues[idx] <= alpha / (m - rank):
            reject[idx] = True
        else:
            break
    return reject


def holm_thresholds(pvalues: Sequence[float], alpha: float) -> list[float]:
    """The Holm threshold each hypothesis was compared against (in input order)."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    out = [alpha] * m
    for rank, idx in enumerate(order):
        out[idx] = alpha / (m - rank)
    return out


def hypergeom_split_tail(N: int, K: int, n1: int, a: int, b: int) -> float:
    """P(X <= a and K - X > b) for X ~ Hypergeom(N, K, n1).

    X is the number of the K marked items falling into a random subset of
    size n1 out of N; ``K - X`` are the ones in the complement.
    """
    if N <= 0 or n1 < 0 or K < 0:
        return 0.0
    lo = max(0, K - (N - n1))
    hi = min(a, K - b - 1, n1, K)
    if hi < lo:
        return 0.0
    xs = np.arange(lo, hi + 1)
    return float(np.sum(_st.hypergeom.pmf(xs, N, K, n1)))
