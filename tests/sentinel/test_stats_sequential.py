"""Statistical toolkit and sequential tests."""

from __future__ import annotations

import math
from itertools import combinations

import numpy as np
import pytest
from scipy.stats import binom

from sentinel.sequential import Cusum, Ewma, Sprt
from sentinel.stats import (
    binom_cdf, binom_sf, chernoff_lower_tail, chernoff_upper_tail, chi2_homogeneity, clopper_pearson,
    cp_lower, cp_upper, holm, hypergeom_split_tail, kl_bernoulli, two_proportion_test,
)


def test_binomial_tails_brute_force():
    n, p = 12, 0.3
    pmf = [math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(n + 1)]
    for m in range(-1, n + 2):
        assert binom_sf(m, n, p) == pytest.approx(sum(pmf[max(m, 0):]), abs=1e-12)
        assert binom_cdf(m, n, p) == pytest.approx(sum(pmf[: max(0, min(m, n) + 1)]) if m >= 0 else 0.0, abs=1e-12)


def test_clopper_pearson_coverage_and_bounds():
    lo, hi = clopper_pearson(5, 50, 0.05)
    assert lo < 0.1 < hi
    assert clopper_pearson(0, 20, 0.05)[0] == 0.0
    assert clopper_pearson(20, 20, 0.05)[1] == 1.0
    # One-sided bound: P(X <= x | p = upper) = delta
    up = cp_upper(3, 100, 1e-3)
    assert binom.cdf(3, 100, up) == pytest.approx(1e-3, rel=1e-6)
    low = cp_lower(30, 100, 1e-3)
    assert binom.sf(29, 100, low) == pytest.approx(1e-3, rel=1e-6)


def test_chernoff_dominates_exact():
    n, p = 300, 1 / 3
    for q in (0.15, 0.2, 0.25):
        exact = binom_cdf(int(q * n), n, p)
        assert exact <= chernoff_lower_tail(n, p, q) + 1e-15
    for q in (0.05, 0.08):
        assert binom_sf(math.ceil(q * n), n, 0.01) <= chernoff_upper_tail(n, 0.01, q) + 1e-15
    assert kl_bernoulli(0.2, 0.2) == pytest.approx(0.0)


def test_two_proportion_and_fisher_fallback():
    big = two_proportion_test(300, 1000, 200, 1000, "greater")
    assert big["method"] == "z" and big["p_value"] < 1e-6
    small = two_proportion_test(3, 10, 1, 10)
    assert small["method"] == "fisher" and small["p_value"] > 0.05
    same = two_proportion_test(100, 1000, 100, 1000)
    assert same["p_value"] == pytest.approx(1.0)


def test_chi2_homogeneity():
    same = chi2_homogeneity(np.array([500, 300]), np.array([1000, 1000]), np.array([500, 300]), np.array([1000, 1000]))
    assert same["statistic"] == pytest.approx(0.0) and same["df"] == 2
    diff = chi2_homogeneity(np.array([500]), np.array([1000]), np.array([400]), np.array([1000]))
    assert diff["p_value"] < 1e-5
    degenerate = chi2_homogeneity(np.array([10]), np.array([10]), np.array([5]), np.array([5]))
    assert degenerate["df"] == 0 and degenerate["p_value"] == 1.0


def test_holm_hand_example():
    # alpha = 0.05, m = 4: thresholds 0.0125, 0.0167, 0.025, 0.05
    assert holm([0.01, 0.04, 0.03, 0.005], 0.05) == [True, False, False, True]
    assert holm([0.001, 0.002, 0.003, 0.02], 0.05) == [True, True, True, True]
    assert holm([], 0.05) == []


def test_hypergeom_split_tail_brute_force():
    N, K, n1, a, b = 10, 4, 5, 1, 2
    total = 0
    count = 0
    items = list(range(N))
    marked = set(range(K))
    for subset in combinations(items, n1):
        x = len(marked.intersection(subset))
        total += 1
        if x <= a and K - x > b:
            count += 1
    assert hypergeom_split_tail(N, K, n1, a, b) == pytest.approx(count / total)


class TestSprt:
    def test_rejects_forgery_quickly_and_keeps_honest(self):
        s = Sprt(0.02, 1 / 3, alpha=1e-9, beta=1e-6)
        rng = np.random.default_rng(0)
        forged = rng.random(400) < 1 / 3
        r = s.run(forged, early_accept=False)
        assert r.decision == "reject" and r.n_used < 150
        honest = rng.random(400) < 0.02
        assert s.run(honest, early_accept=False).decision == "continue"

    def test_asn_wald_close_to_monte_carlo(self):
        s = Sprt(0.02, 1 / 3, alpha=1e-6, beta=1e-6)
        rng = np.random.default_rng(1)
        for p in (0.02, 1 / 3):
            used = [s.run(rng.random(2000) < p).n_used for _ in range(300)]
            assert np.mean(used) == pytest.approx(s.asn(p), rel=0.25)
        assert s.oc(0.02) > 0.999 and s.oc(1 / 3) < 1e-3


def test_cusum_alarm_timing_and_state_roundtrip():
    c = Cusum(k=0.0025, h=0.015)
    alarms = [c.update(0.005)[1] for _ in range(10)]  # +0.0025 net per step
    assert alarms.index(True) == 6  # 7 * 0.0025 = 0.0175 > 0.015
    again = Cusum.from_state(c.state())
    assert again.value == c.value and again.alarms == c.alarms
    quiet = Cusum(k=0.0025, h=0.015)
    assert not any(quiet.update(-0.001)[1] for _ in range(100))


def test_ewma():
    e = Ewma(0.5)
    assert e.update(1.0) == 1.0
    assert e.update(0.0) == 0.5
