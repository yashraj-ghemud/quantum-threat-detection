"""
tests/security/test_statistics.py
====================================
Phase 4 -- Measurement Statistics test suite.
SIH26141 | Blockchain & Cybersecurity.

Categories
----------
1. compute_measurement_stats  -- correct mean, variance, counts, probabilities
2. Probability invariants      -- sum to 1, in [0,1], match+mismatch=1
3. Basis stats                 -- per-basis breakdown correctness
4. stats_from_verification     -- integration with VerificationResult
5. Edge cases                  -- empty input, single element, all-same
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

warnings.filterwarnings("ignore", category=DeprecationWarning)

from security.statistics import (
    BasisStats,
    MeasurementStats,
    compute_basis_stats,
    compute_measurement_stats,
    stats_from_verification,
)
from qds.signature import generate_signature
from qds.verification import verify_signature

_SEED = 42
_ATOL = 1e-9


# ===========================================================================
# Helpers
# ===========================================================================

def _make_stats(meas, exp, pplus, pminus, bases):
    return compute_measurement_stats(meas, exp, pplus, pminus, bases)


def _legit_stats(length=32):
    sig = generate_signature("msg", length=length, seed=_SEED)
    vr  = verify_signature(sig)
    return stats_from_verification(vr)


# ===========================================================================
# 1. compute_measurement_stats
# ===========================================================================

class TestComputeMeasurementStats:

    def test_returns_measurement_stats(self) -> None:
        s = _make_stats([+1,-1,+1,+1],[+1,-1,+1,+1],[1,0,1,1],[0,1,0,0],["z","z","x","y"])
        assert isinstance(s, MeasurementStats)

    def test_total(self) -> None:
        s = _make_stats([+1,-1,+1],[+1,-1,+1],[1,0,1],[0,1,0],["x","y","z"])
        assert s.total == 3

    def test_positive_count(self) -> None:
        s = _make_stats([+1,+1,-1,+1],  [+1]*4, [1,1,0,1],[0,0,1,0],["z"]*4)
        assert s.positive_count == 3

    def test_negative_count(self) -> None:
        s = _make_stats([+1,+1,-1,+1],  [+1]*4, [1,1,0,1],[0,0,1,0],["z"]*4)
        assert s.negative_count == 1

    def test_p_plus_correct(self) -> None:
        s = _make_stats([+1,+1,-1,-1],[+1]*4,[1,1,0,0],[0,0,1,1],["z"]*4)
        assert abs(s.p_plus - 0.5) <= _ATOL

    def test_p_minus_correct(self) -> None:
        s = _make_stats([+1,+1,-1,-1],[+1]*4,[1,1,0,0],[0,0,1,1],["z"]*4)
        assert abs(s.p_minus - 0.5) <= _ATOL

    def test_mean_all_plus_one(self) -> None:
        s = _make_stats([+1]*4,[+1]*4,[1]*4,[0]*4,["z"]*4)
        assert abs(s.mean - 1.0) <= _ATOL

    def test_mean_all_minus_one(self) -> None:
        s = _make_stats([-1]*4,[+1]*4,[0]*4,[1]*4,["z"]*4)
        assert abs(s.mean + 1.0) <= _ATOL

    def test_mean_balanced(self) -> None:
        s = _make_stats([+1,+1,-1,-1],[+1]*4,[1,1,0,0],[0,0,1,1],["z"]*4)
        assert abs(s.mean) <= _ATOL

    def test_variance_all_same(self) -> None:
        """All +1 => variance = 0."""
        s = _make_stats([+1]*8,[+1]*8,[1]*8,[0]*8,["z"]*8)
        assert abs(s.variance) <= _ATOL

    def test_variance_balanced(self) -> None:
        """Equal +1/-1 => variance = 1."""
        s = _make_stats([+1,-1]*4,[+1]*8,[1,0]*4,[0,1]*4,["z"]*8)
        assert abs(s.variance - 1.0) <= _ATOL

    def test_match_rate_perfect(self) -> None:
        s = _make_stats([+1,-1,+1],[+1,-1,+1],[1,0,1],[0,1,0],["z"]*3)
        assert abs(s.match_rate - 1.0) <= _ATOL

    def test_mismatch_rate_perfect(self) -> None:
        s = _make_stats([+1,-1,+1],[+1,-1,+1],[1,0,1],[0,1,0],["z"]*3)
        assert abs(s.mismatch_rate) <= _ATOL

    def test_match_rate_zero(self) -> None:
        """All measured opposite to expected."""
        s = _make_stats([-1]*4,[+1]*4,[0]*4,[1]*4,["z"]*4)
        assert abs(s.match_rate) <= _ATOL

    def test_avg_p_plus_expected(self) -> None:
        pplus = [0.8, 0.6, 0.4, 0.2]
        s = _make_stats([+1]*4,[+1]*4, pplus,[1-p for p in pplus],["z"]*4)
        assert abs(s.avg_p_plus_expected - 0.5) <= _ATOL


# ===========================================================================
# 2. Probability Invariants
# ===========================================================================

class TestProbabilityInvariants:

    def test_p_plus_p_minus_sum_to_one(self) -> None:
        s = _legit_stats()
        assert abs(s.p_plus + s.p_minus - 1.0) <= _ATOL

    def test_match_mismatch_sum_to_one(self) -> None:
        s = _legit_stats()
        assert abs(s.match_rate + s.mismatch_rate - 1.0) <= _ATOL

    def test_p_plus_in_unit_interval(self) -> None:
        s = _legit_stats()
        assert -_ATOL <= s.p_plus <= 1.0 + _ATOL

    def test_p_minus_in_unit_interval(self) -> None:
        s = _legit_stats()
        assert -_ATOL <= s.p_minus <= 1.0 + _ATOL

    def test_match_rate_in_unit_interval(self) -> None:
        s = _legit_stats()
        assert -_ATOL <= s.match_rate <= 1.0 + _ATOL

    def test_variance_non_negative(self) -> None:
        s = _legit_stats()
        assert s.variance >= -_ATOL

    def test_is_valid_returns_true_for_legit(self) -> None:
        s = _legit_stats()
        assert s.is_valid()

    def test_positive_plus_negative_equals_total(self) -> None:
        s = _legit_stats()
        assert s.positive_count + s.negative_count == s.total


# ===========================================================================
# 3. Basis Stats
# ===========================================================================

class TestBasisStats:

    def test_basis_stats_keys(self) -> None:
        s = _legit_stats()
        assert set(s.basis_stats.keys()) == {"x", "y", "z"}

    def test_basis_counts_sum_to_total(self) -> None:
        s = _legit_stats(length=48)
        total_from_bases = sum(bs.count for bs in s.basis_stats.values())
        assert total_from_bases == s.total

    def test_basis_match_mismatch_sum_to_one(self) -> None:
        s = _legit_stats()
        for basis, bs in s.basis_stats.items():
            if bs.count > 0:
                assert abs(bs.match_rate + bs.mismatch_rate - 1.0) <= _ATOL, basis

    def test_basis_p_plus_p_minus_sum_to_one(self) -> None:
        s = _legit_stats()
        for basis, bs in s.basis_stats.items():
            if bs.count > 0:
                assert abs(bs.p_plus + bs.p_minus - 1.0) <= _ATOL, basis

    def test_basis_stats_type(self) -> None:
        s = _legit_stats()
        for bs in s.basis_stats.values():
            assert isinstance(bs, BasisStats)


# ===========================================================================
# 4. stats_from_verification
# ===========================================================================

class TestStatsFromVerification:

    def test_returns_measurement_stats(self) -> None:
        sig = generate_signature("m", length=16, seed=_SEED)
        vr  = verify_signature(sig)
        s   = stats_from_verification(vr)
        assert isinstance(s, MeasurementStats)

    def test_total_equals_sig_length(self) -> None:
        for length in (8, 16, 32):
            sig = generate_signature("m", length=length, seed=_SEED)
            vr  = verify_signature(sig)
            s   = stats_from_verification(vr)
            assert s.total == length

    def test_legit_match_rate_is_one(self) -> None:
        sig = generate_signature("m", length=32, seed=_SEED)
        vr  = verify_signature(sig)
        s   = stats_from_verification(vr)
        assert abs(s.match_rate - 1.0) <= _ATOL

    def test_legit_mismatch_rate_is_zero(self) -> None:
        sig = generate_signature("m", length=32, seed=_SEED)
        vr  = verify_signature(sig)
        s   = stats_from_verification(vr)
        assert abs(s.mismatch_rate) <= _ATOL

    def test_forged_mismatch_rate_high(self) -> None:
        from qds.pauli_states import EIGENSTATE_LABELS, get_eigenstate
        sig = generate_signature("m", length=32, seed=_SEED)
        received = [get_eigenstate(next(l for l in EIGENSTATE_LABELS if l != e.label)).statevector
                    for e in sig.elements]
        vr = verify_signature(sig, received_statevectors=received)
        s  = stats_from_verification(vr)
        assert s.mismatch_rate > 0.3


# ===========================================================================
# 5. Edge Cases
# ===========================================================================

class TestEdgeCases:

    def test_single_element_plus_one(self) -> None:
        s = _make_stats([+1],[+1],[1.0],[0.0],["z"])
        assert s.total == 1
        assert abs(s.match_rate - 1.0) <= _ATOL
        assert s.is_valid()

    def test_single_element_minus_one(self) -> None:
        s = _make_stats([-1],[+1],[0.0],[1.0],["z"])
        assert s.total == 1
        assert abs(s.mismatch_rate - 1.0) <= _ATOL

    def test_no_nan_in_legit_stats(self) -> None:
        s = _legit_stats()
        for attr in ("mean","variance","p_plus","p_minus","match_rate","mismatch_rate"):
            val = getattr(s, attr)
            assert not np.isnan(val), f"{attr} is NaN"
            assert not np.isinf(val), f"{attr} is Inf"

    def test_reproducibility_same_seed(self) -> None:
        sig1 = generate_signature("m", length=32, seed=_SEED)
        sig2 = generate_signature("m", length=32, seed=_SEED)
        s1 = stats_from_verification(verify_signature(sig1))
        s2 = stats_from_verification(verify_signature(sig2))
        assert abs(s1.mean       - s2.mean)        <= _ATOL
        assert abs(s1.match_rate - s2.match_rate)   <= _ATOL
