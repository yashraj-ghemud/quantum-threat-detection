"""
tests/security/test_anomaly.py
================================
Phase 4 -- Anomaly Scoring test suite.
SIH26141 | Blockchain & Cybersecurity.
"""

from __future__ import annotations

import sys, warnings
from pathlib import Path
import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

warnings.filterwarnings("ignore", category=DeprecationWarning)

from security.anomaly import (
    ANOMALY_WEIGHTS,
    AnomalyBreakdown,
    compute_anomaly_breakdown,
    compute_anomaly_score,
    z_score_mismatch,
)
from security.fingerprint import build_fingerprint, build_baseline_fingerprint
from qds.pauli_states import EIGENSTATE_LABELS, get_eigenstate
from qds.signature import generate_signature
from qds.verification import verify_signature

_SEED = 42
_ATOL = 1e-9


def _baseline_fp(n_sessions=8, length=32):
    fps = []
    for i in range(n_sessions):
        sig = generate_signature("m", length=length, seed=i)
        vr  = verify_signature(sig)
        fps.append(build_fingerprint(vr))
    return build_baseline_fingerprint(fps)


def _legit_fp(seed=_SEED, length=32):
    sig = generate_signature("m", length=length, seed=seed)
    return build_fingerprint(verify_signature(sig))


def _forged_fp(seed=_SEED, length=32):
    sig = generate_signature("m", length=length, seed=seed)
    received = [get_eigenstate(next(l for l in EIGENSTATE_LABELS if l != e.label)).statevector
                for e in sig.elements]
    vr = verify_signature(sig, received_statevectors=received)
    return build_fingerprint(vr)


class TestAnomalyWeights:

    def test_weights_sum_to_one(self) -> None:
        assert abs(sum(ANOMALY_WEIGHTS.values()) - 1.0) <= _ATOL

    def test_all_weights_positive(self) -> None:
        assert all(w > 0 for w in ANOMALY_WEIGHTS.values())

    def test_required_weight_keys(self) -> None:
        assert set(ANOMALY_WEIGHTS) == {"mismatch_rate","mean","p_plus","basis_mismatch"}


class TestComputeAnomalyBreakdown:

    def test_returns_anomaly_breakdown(self) -> None:
        bl = _baseline_fp()
        fp = _legit_fp()
        bd = compute_anomaly_breakdown(fp, bl)
        assert isinstance(bd, AnomalyBreakdown)

    def test_self_comparison_score_zero(self) -> None:
        """Same fingerprint as baseline -> score == 0."""
        fp = _legit_fp()
        bd = compute_anomaly_breakdown(fp, fp)
        assert abs(bd.anomaly_score) <= _ATOL

    def test_score_in_unit_interval(self) -> None:
        bl = _baseline_fp()
        for seed in range(5):
            fp = _legit_fp(seed=seed+10)
            bd = compute_anomaly_breakdown(fp, bl)
            assert -_ATOL <= bd.anomaly_score <= 1.0 + _ATOL

    def test_forged_score_higher_than_legit(self) -> None:
        bl  = _baseline_fp()
        fp_legit  = _legit_fp(seed=99)
        fp_forged = _forged_fp(seed=99)
        score_legit  = compute_anomaly_breakdown(fp_legit,  bl).anomaly_score
        score_forged = compute_anomaly_breakdown(fp_forged, bl).anomaly_score
        assert score_forged > score_legit

    def test_delta_mismatch_non_negative(self) -> None:
        bl = _baseline_fp()
        fp = _legit_fp()
        bd = compute_anomaly_breakdown(fp, bl)
        assert bd.delta_mismatch >= -_ATOL

    def test_delta_mean_non_negative(self) -> None:
        bl = _baseline_fp()
        fp = _legit_fp()
        bd = compute_anomaly_breakdown(fp, bl)
        assert bd.delta_mean >= -_ATOL

    def test_delta_p_plus_non_negative(self) -> None:
        bl = _baseline_fp()
        fp = _legit_fp()
        bd = compute_anomaly_breakdown(fp, bl)
        assert bd.delta_p_plus >= -_ATOL

    def test_delta_basis_non_negative(self) -> None:
        bl = _baseline_fp()
        fp = _legit_fp()
        bd = compute_anomaly_breakdown(fp, bl)
        assert bd.delta_basis >= -_ATOL

    def test_indicators_is_list(self) -> None:
        bl = _baseline_fp()
        fp = _forged_fp()
        bd = compute_anomaly_breakdown(fp, bl)
        assert isinstance(bd.indicators, list)

    def test_forged_has_indicators(self) -> None:
        bl = _baseline_fp()
        fp = _forged_fp()
        bd = compute_anomaly_breakdown(fp, bl)
        assert len(bd.indicators) > 0

    def test_deterministic_same_inputs(self) -> None:
        bl = _baseline_fp()
        fp = _legit_fp(seed=77)
        s1 = compute_anomaly_breakdown(fp, bl).anomaly_score
        s2 = compute_anomaly_breakdown(fp, bl).anomaly_score
        assert abs(s1 - s2) <= _ATOL

    def test_no_nan_or_inf(self) -> None:
        bl = _baseline_fp()
        for seed in range(5):
            fp = _legit_fp(seed=seed+20)
            bd = compute_anomaly_breakdown(fp, bl)
            assert not np.isnan(bd.anomaly_score)
            assert not np.isinf(bd.anomaly_score)


class TestComputeAnomalyScore:

    def test_returns_float(self) -> None:
        bl = _baseline_fp()
        fp = _legit_fp()
        assert isinstance(compute_anomaly_score(fp, bl), float)

    def test_legit_baseline_low_score(self) -> None:
        """Legitimate sessions scored against their own baseline are near 0."""
        bl = _baseline_fp()
        for seed in range(5):
            sig = generate_signature("m", length=32, seed=seed)
            vr  = verify_signature(sig)
            fp  = build_fingerprint(vr)
            score = compute_anomaly_score(fp, bl)
            assert score < 0.20, f"seed={seed}: score={score:.4f} unexpectedly high"

    def test_forged_score_above_legit(self) -> None:
        bl = _baseline_fp()
        legit_score  = compute_anomaly_score(_legit_fp(seed=50), bl)
        forged_score = compute_anomaly_score(_forged_fp(seed=50), bl)
        assert forged_score > legit_score


class TestZScoreMismatch:

    def test_zero_std_returns_zero(self) -> None:
        assert z_score_mismatch(0.5, 0.5, 0.0) == 0.0

    def test_positive_deviation(self) -> None:
        z = z_score_mismatch(0.3, 0.0, 0.1)
        assert z > 0.0

    def test_negative_deviation(self) -> None:
        z = z_score_mismatch(0.0, 0.3, 0.1)
        assert z < 0.0

    def test_zero_deviation(self) -> None:
        assert abs(z_score_mismatch(0.2, 0.2, 0.1)) <= _ATOL
