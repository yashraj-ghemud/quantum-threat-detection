"""
tests/security/test_fingerprint.py
=====================================
Phase 4 -- Session Fingerprint test suite.
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

from security.fingerprint import (
    BasisFingerprint, SessionFingerprint,
    build_fingerprint, build_baseline_fingerprint,
)
from qds.signature import generate_signature
from qds.verification import verify_signature

_SEED = 42
_ATOL = 1e-9


def _legit_vr(length=32, seed=_SEED):
    sig = generate_signature("m", length=length, seed=seed)
    return verify_signature(sig)


def _legit_fp(length=32, seed=_SEED):
    return build_fingerprint(_legit_vr(length, seed))


class TestBuildFingerprint:

    def test_returns_session_fingerprint(self) -> None:
        assert isinstance(_legit_fp(), SessionFingerprint)

    def test_session_id_set(self) -> None:
        vr = _legit_vr()
        fp = build_fingerprint(vr)
        assert len(fp.session_id) > 0

    def test_custom_session_id(self) -> None:
        vr = _legit_vr()
        fp = build_fingerprint(vr, session_id="custom_42")
        assert fp.session_id == "custom_42"

    def test_total_equals_sig_length(self) -> None:
        for n in (8, 16, 32):
            fp = _legit_fp(length=n)
            assert fp.total == n

    def test_legit_mismatch_rate_is_zero(self) -> None:
        fp = _legit_fp()
        assert abs(fp.mismatch_rate) <= _ATOL

    def test_legit_match_rate_is_one(self) -> None:
        fp = _legit_fp()
        assert abs(fp.match_rate - 1.0) <= _ATOL

    def test_p_plus_in_unit_interval(self) -> None:
        fp = _legit_fp()
        assert -_ATOL <= fp.p_plus <= 1.0 + _ATOL

    def test_p_minus_in_unit_interval(self) -> None:
        fp = _legit_fp()
        assert -_ATOL <= fp.p_minus <= 1.0 + _ATOL

    def test_p_plus_p_minus_sum_to_one(self) -> None:
        fp = _legit_fp()
        assert abs(fp.p_plus + fp.p_minus - 1.0) <= _ATOL

    def test_basis_fingerprints_have_xyz_keys(self) -> None:
        fp = _legit_fp()
        assert set(fp.basis_fingerprints.keys()) == {"x", "y", "z"}

    def test_basis_fingerprint_type(self) -> None:
        fp = _legit_fp()
        for bfp in fp.basis_fingerprints.values():
            assert isinstance(bfp, BasisFingerprint)

    def test_as_vector_length(self) -> None:
        fp = _legit_fp()
        v = fp.as_vector()
        assert len(v) == 8

    def test_as_vector_all_finite(self) -> None:
        fp = _legit_fp()
        v = fp.as_vector()
        assert np.all(np.isfinite(v))

    def test_as_vector_in_zero_one(self) -> None:
        """All vector components should be in [0,1] since inputs are bounded."""
        fp = _legit_fp()
        v = fp.as_vector()
        assert np.all(v >= -_ATOL), f"Vector has negative values: {v}"
        assert np.all(v <= 1.0 + _ATOL), f"Vector exceeds 1: {v}"

    def test_deterministic_same_seed(self) -> None:
        fp1 = _legit_fp(seed=_SEED)
        fp2 = _legit_fp(seed=_SEED)
        assert np.allclose(fp1.as_vector(), fp2.as_vector(), atol=_ATOL)


class TestBuildBaselineFingerprint:

    def test_returns_session_fingerprint(self) -> None:
        fps = [_legit_fp(seed=i) for i in range(5)]
        bf  = build_baseline_fingerprint(fps)
        assert isinstance(bf, SessionFingerprint)

    def test_session_id_is_baseline(self) -> None:
        fps = [_legit_fp(seed=i) for i in range(3)]
        bf  = build_baseline_fingerprint(fps)
        assert bf.session_id == "__baseline__"

    def test_baseline_mismatch_near_zero(self) -> None:
        fps = [_legit_fp(seed=i) for i in range(8)]
        bf  = build_baseline_fingerprint(fps)
        assert abs(bf.mismatch_rate) <= _ATOL

    def test_baseline_match_rate_near_one(self) -> None:
        fps = [_legit_fp(seed=i) for i in range(8)]
        bf  = build_baseline_fingerprint(fps)
        assert abs(bf.match_rate - 1.0) <= _ATOL

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            build_baseline_fingerprint([])

    def test_single_session_baseline(self) -> None:
        fp  = _legit_fp()
        bf  = build_baseline_fingerprint([fp])
        assert isinstance(bf, SessionFingerprint)
        assert abs(bf.mismatch_rate - fp.mismatch_rate) <= _ATOL
