"""
tests/security/test_detector.py
==================================
Phase 4 -- ThreatDetector test suite.
SIH26141 | Blockchain & Cybersecurity.

Categories
----------
1. Detector construction & baseline management
2. Calibration
3. detect() output structure
4. Classification boundaries NORMAL/SUSPICIOUS/THREAT
5. Reproducibility
6. Edge cases (no calibration, small baseline)
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

from security.detector import (
    NORMAL, SUSPICIOUS, THREAT,
    DetectionResult, ThreatDetector,
)
from security.fingerprint import SessionFingerprint
from security.statistics import MeasurementStats
from security.thresholds import ThresholdConfig
from qds.pauli_states import EIGENSTATE_LABELS, get_eigenstate
from qds.signature import generate_signature
from qds.verification import verify_signature

_SEED = 42
_ATOL = 1e-9
_N_BASELINE = 10
_SIG_LEN    = 32


def _build_detector(n=_N_BASELINE) -> ThreatDetector:
    d = ThreatDetector()
    for i in range(n):
        sig = generate_signature("m", length=_SIG_LEN, seed=i)
        d.add_baseline_session(verify_signature(sig))
    d.calibrate()
    return d


def _legit_vr(seed=99):
    sig = generate_signature("m", length=_SIG_LEN, seed=seed)
    return verify_signature(sig)


def _forged_vr(seed=99):
    sig = generate_signature("m", length=_SIG_LEN, seed=seed)
    received = [get_eigenstate(next(l for l in EIGENSTATE_LABELS if l != e.label)).statevector
                for e in sig.elements]
    return verify_signature(sig, received_statevectors=received)


# ===========================================================================
# 1. Construction & Baseline
# ===========================================================================

class TestDetectorConstruction:

    def test_baseline_size_zero_initially(self) -> None:
        d = ThreatDetector()
        assert d.baseline_size == 0

    def test_add_baseline_session(self) -> None:
        d = ThreatDetector()
        d.add_baseline_session(_legit_vr())
        assert d.baseline_size == 1

    def test_add_multiple_sessions(self) -> None:
        d = ThreatDetector()
        for i in range(5):
            d.add_baseline_session(_legit_vr(seed=i))
        assert d.baseline_size == 5

    def test_add_returns_self(self) -> None:
        d = ThreatDetector()
        result = d.add_baseline_session(_legit_vr())
        assert result is d

    def test_add_baseline_sessions_batch(self) -> None:
        d = ThreatDetector()
        vrs = [_legit_vr(seed=i) for i in range(4)]
        d.add_baseline_sessions(vrs)
        assert d.baseline_size == 4


# ===========================================================================
# 2. Calibration
# ===========================================================================

class TestCalibration:

    def test_calibrate_returns_self(self) -> None:
        d = ThreatDetector()
        d.add_baseline_session(_legit_vr())
        assert d.calibrate() is d

    def test_calibration_result_set(self) -> None:
        d = _build_detector()
        assert d.calibration is not None

    def test_thresholds_after_calibration(self) -> None:
        d = _build_detector()
        assert isinstance(d.thresholds, ThresholdConfig)

    def test_warning_leq_critical(self) -> None:
        d = _build_detector()
        assert d.thresholds.warning <= d.thresholds.critical

    def test_calibrate_no_baseline_raises(self) -> None:
        d = ThreatDetector()
        with pytest.raises(ValueError, match="No baseline"):
            d.calibrate()

    def test_override_thresholds_used(self) -> None:
        d = ThreatDetector(warning_threshold=0.10, critical_threshold=0.30)
        d.add_baseline_session(_legit_vr())
        d.calibrate()
        assert abs(d.thresholds.warning  - 0.10) <= _ATOL
        assert abs(d.thresholds.critical - 0.30) <= _ATOL

    def test_sigma_method(self) -> None:
        d = ThreatDetector(calibration_method="sigma")
        for i in range(5):
            d.add_baseline_session(_legit_vr(seed=i))
        d.calibrate()
        assert d.thresholds.method == "sigma"

    def test_calibration_n_samples(self) -> None:
        d = _build_detector(n=7)
        assert d.calibration.n_samples == 7


# ===========================================================================
# 3. detect() output structure
# ===========================================================================

class TestDetectOutput:

    @pytest.fixture(scope="class")
    @classmethod
    def detector(cls) -> ThreatDetector:
        return _build_detector()

    @pytest.fixture(scope="class")
    @classmethod
    def legit_result(cls, detector) -> DetectionResult:
        return detector.detect(_legit_vr())

    def test_returns_detection_result(self, detector) -> None:
        r = detector.detect(_legit_vr())
        assert isinstance(r, DetectionResult)

    def test_session_id_set(self, legit_result) -> None:
        assert len(legit_result.session_id) > 0

    def test_classification_is_string(self, legit_result) -> None:
        assert isinstance(legit_result.classification, str)
        assert legit_result.classification in (NORMAL, SUSPICIOUS, THREAT)

    def test_anomaly_score_in_unit_interval(self, legit_result) -> None:
        assert -_ATOL <= legit_result.anomaly_score <= 1.0 + _ATOL

    def test_mismatch_rate_in_unit_interval(self, legit_result) -> None:
        assert -_ATOL <= legit_result.mismatch_rate <= 1.0 + _ATOL

    def test_match_rate_in_unit_interval(self, legit_result) -> None:
        assert -_ATOL <= legit_result.match_rate <= 1.0 + _ATOL

    def test_match_mismatch_sum_one(self, legit_result) -> None:
        assert abs(legit_result.match_rate + legit_result.mismatch_rate - 1.0) <= _ATOL

    def test_stats_type(self, legit_result) -> None:
        assert isinstance(legit_result.stats, MeasurementStats)

    def test_fingerprint_type(self, legit_result) -> None:
        assert isinstance(legit_result.fingerprint, SessionFingerprint)

    def test_indicators_is_list(self, legit_result) -> None:
        assert isinstance(legit_result.indicators, list)

    def test_explanation_is_string(self, legit_result) -> None:
        assert isinstance(legit_result.explanation, str)
        assert len(legit_result.explanation) > 0

    def test_thresholds_stored(self, detector, legit_result) -> None:
        assert abs(legit_result.warning_threshold  - detector.thresholds.warning)  <= _ATOL
        assert abs(legit_result.critical_threshold - detector.thresholds.critical) <= _ATOL

    def test_no_nan_in_result(self, legit_result) -> None:
        for attr in ("anomaly_score","mismatch_rate","match_rate","mean","variance","z_score"):
            val = getattr(legit_result, attr)
            assert not np.isnan(val),  f"{attr} is NaN"
            assert not np.isinf(val),  f"{attr} is Inf"


# ===========================================================================
# 4. Classification Boundaries
# ===========================================================================

class TestClassificationBoundaries:

    def test_score_zero_is_normal(self) -> None:
        cfg = ThresholdConfig(warning=0.2, critical=0.5)
        assert cfg.classify(0.0) == NORMAL

    def test_score_at_warning_is_suspicious(self) -> None:
        cfg = ThresholdConfig(warning=0.2, critical=0.5)
        assert cfg.classify(0.2) == SUSPICIOUS

    def test_score_just_below_warning_is_normal(self) -> None:
        cfg = ThresholdConfig(warning=0.2, critical=0.5)
        assert cfg.classify(0.199999) == NORMAL

    def test_score_at_critical_is_threat(self) -> None:
        cfg = ThresholdConfig(warning=0.2, critical=0.5)
        assert cfg.classify(0.5) == THREAT

    def test_score_one_is_threat(self) -> None:
        cfg = ThresholdConfig(warning=0.2, critical=0.5)
        assert cfg.classify(1.0) == THREAT

    def test_legit_session_not_threat(self) -> None:
        d = _build_detector()
        r = d.detect(_legit_vr(seed=200))
        assert r.classification != THREAT

    def test_forged_session_higher_score_than_legit(self) -> None:
        d = _build_detector()
        r_legit  = d.detect(_legit_vr(seed=150))
        r_forged = d.detect(_forged_vr(seed=150))
        assert r_forged.anomaly_score > r_legit.anomaly_score

    def test_forged_classified_suspicious_or_threat(self) -> None:
        d = _build_detector()
        r = d.detect(_forged_vr(seed=150))
        assert r.classification in (SUSPICIOUS, THREAT)


# ===========================================================================
# 5. Reproducibility
# ===========================================================================

class TestReproducibility:

    def test_same_session_same_score(self) -> None:
        d = _build_detector()
        vr = _legit_vr(seed=77)
        r1 = d.detect(vr)
        r2 = d.detect(vr)
        assert abs(r1.anomaly_score - r2.anomaly_score) <= _ATOL

    def test_same_session_same_classification(self) -> None:
        d = _build_detector()
        vr = _legit_vr(seed=77)
        r1 = d.detect(vr)
        r2 = d.detect(vr)
        assert r1.classification == r2.classification


# ===========================================================================
# 6. Edge Cases
# ===========================================================================

class TestEdgeCases:

    def test_detect_before_calibrate_uses_defaults(self) -> None:
        """Detector without calibrate() uses default thresholds."""
        d = ThreatDetector()
        vr = _legit_vr()
        r  = d.detect(vr)
        assert isinstance(r, DetectionResult)

    def test_single_baseline_session(self) -> None:
        d = ThreatDetector()
        d.add_baseline_session(_legit_vr())
        d.calibrate()
        r = d.detect(_legit_vr(seed=55))
        assert isinstance(r, DetectionResult)

    def test_score_always_finite(self) -> None:
        d = _build_detector()
        for seed in range(5):
            r = d.detect(_legit_vr(seed=seed+100))
            assert np.isfinite(r.anomaly_score)
