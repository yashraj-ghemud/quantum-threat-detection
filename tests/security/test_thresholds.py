"""
tests/security/test_thresholds.py
====================================
Phase 4 -- Threshold Calibration test suite.
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

from security.thresholds import (
    CalibrationResult,
    DEFAULT_CRITICAL_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    ThresholdConfig,
    fixed_calibrate,
    percentile_calibrate,
    sigma_calibrate,
)

_ATOL = 1e-9
_BASELINE_SCORES = [0.0, 0.01, 0.02, 0.01, 0.0, 0.03, 0.01, 0.02, 0.0, 0.04]


class TestThresholdConfig:

    def test_valid_config(self) -> None:
        cfg = ThresholdConfig(warning=0.1, critical=0.3)
        assert cfg.warning == 0.1
        assert cfg.critical == 0.3

    def test_warning_greater_than_critical_raises(self) -> None:
        with pytest.raises(ValueError):
            ThresholdConfig(warning=0.5, critical=0.2)

    def test_warning_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            ThresholdConfig(warning=-0.1, critical=0.5)

    def test_critical_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            ThresholdConfig(warning=0.1, critical=1.5)

    def test_classify_normal(self) -> None:
        cfg = ThresholdConfig(warning=0.2, critical=0.5)
        assert cfg.classify(0.0)  == "NORMAL"
        assert cfg.classify(0.1)  == "NORMAL"
        assert cfg.classify(0.19) == "NORMAL"

    def test_classify_suspicious(self) -> None:
        cfg = ThresholdConfig(warning=0.2, critical=0.5)
        assert cfg.classify(0.2)  == "SUSPICIOUS"
        assert cfg.classify(0.35) == "SUSPICIOUS"
        assert cfg.classify(0.49) == "SUSPICIOUS"

    def test_classify_threat(self) -> None:
        cfg = ThresholdConfig(warning=0.2, critical=0.5)
        assert cfg.classify(0.5)  == "THREAT"
        assert cfg.classify(0.8)  == "THREAT"
        assert cfg.classify(1.0)  == "THREAT"

    def test_classify_boundary_warning_inclusive(self) -> None:
        """score == warning → SUSPICIOUS (lower bound inclusive)."""
        cfg = ThresholdConfig(warning=0.2, critical=0.5)
        assert cfg.classify(0.2) == "SUSPICIOUS"

    def test_classify_boundary_critical_inclusive(self) -> None:
        """score == critical → THREAT."""
        cfg = ThresholdConfig(warning=0.2, critical=0.5)
        assert cfg.classify(0.5) == "THREAT"

    def test_equal_warning_critical(self) -> None:
        cfg = ThresholdConfig(warning=0.3, critical=0.3)
        assert cfg.classify(0.29) == "NORMAL"
        assert cfg.classify(0.30) == "THREAT"

    def test_zero_thresholds_everything_threat(self) -> None:
        cfg = ThresholdConfig(warning=0.0, critical=0.0)
        assert cfg.classify(0.0) == "THREAT"

    def test_one_thresholds_everything_normal(self) -> None:
        cfg = ThresholdConfig(warning=1.0, critical=1.0)
        assert cfg.classify(0.99) == "NORMAL"

    def test_default_constants(self) -> None:
        assert 0.0 < DEFAULT_WARNING_THRESHOLD < DEFAULT_CRITICAL_THRESHOLD <= 1.0


class TestPercentileCalibrate:

    def test_returns_calibration_result(self) -> None:
        cr = percentile_calibrate(_BASELINE_SCORES)
        assert isinstance(cr, CalibrationResult)

    def test_warning_leq_critical(self) -> None:
        cr = percentile_calibrate(_BASELINE_SCORES)
        assert cr.config.warning <= cr.config.critical

    def test_thresholds_in_unit_interval(self) -> None:
        cr = percentile_calibrate(_BASELINE_SCORES)
        assert 0.0 <= cr.config.warning  <= 1.0
        assert 0.0 <= cr.config.critical <= 1.0

    def test_n_samples(self) -> None:
        cr = percentile_calibrate(_BASELINE_SCORES)
        assert cr.n_samples == len(_BASELINE_SCORES)

    def test_baseline_mean_correct(self) -> None:
        cr = percentile_calibrate(_BASELINE_SCORES)
        assert abs(cr.baseline_mean - float(np.mean(_BASELINE_SCORES))) <= _ATOL

    def test_method_label(self) -> None:
        cr = percentile_calibrate(_BASELINE_SCORES)
        assert cr.config.method == "percentile"

    def test_empty_scores_raises(self) -> None:
        with pytest.raises(ValueError):
            percentile_calibrate([])

    def test_all_zero_scores_uses_floor(self) -> None:
        """All-zero baseline still produces a positive warning threshold."""
        cr = percentile_calibrate([0.0] * 20)
        assert cr.config.warning > 0.0

    def test_custom_percentiles(self) -> None:
        cr = percentile_calibrate(_BASELINE_SCORES, warn_percentile=50, crit_percentile=90)
        cr2 = percentile_calibrate(_BASELINE_SCORES, warn_percentile=80, crit_percentile=99)
        assert cr2.config.warning >= cr.config.warning


class TestSigmaCalibrate:

    def test_returns_calibration_result(self) -> None:
        cr = sigma_calibrate(_BASELINE_SCORES)
        assert isinstance(cr, CalibrationResult)

    def test_method_label(self) -> None:
        assert sigma_calibrate(_BASELINE_SCORES).config.method == "sigma"

    def test_warning_leq_critical(self) -> None:
        cr = sigma_calibrate(_BASELINE_SCORES)
        assert cr.config.warning <= cr.config.critical

    def test_thresholds_in_unit_interval(self) -> None:
        cr = sigma_calibrate(_BASELINE_SCORES)
        assert 0.0 <= cr.config.warning  <= 1.0
        assert 0.0 <= cr.config.critical <= 1.0

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            sigma_calibrate([])

    def test_larger_k_gives_larger_threshold(self) -> None:
        cr2 = sigma_calibrate(_BASELINE_SCORES, k_warn=2.0, k_crit=3.0)
        cr3 = sigma_calibrate(_BASELINE_SCORES, k_warn=3.0, k_crit=5.0)
        assert cr3.config.warning  >= cr2.config.warning
        assert cr3.config.critical >= cr2.config.critical


class TestFixedCalibrate:

    def test_returns_calibration_result(self) -> None:
        cr = fixed_calibrate(0.1, 0.3)
        assert isinstance(cr, CalibrationResult)

    def test_method_label(self) -> None:
        assert fixed_calibrate().config.method == "fixed"

    def test_values_preserved(self) -> None:
        cr = fixed_calibrate(0.15, 0.40)
        assert abs(cr.config.warning  - 0.15) <= _ATOL
        assert abs(cr.config.critical - 0.40) <= _ATOL

    def test_default_values(self) -> None:
        cr = fixed_calibrate()
        assert abs(cr.config.warning  - DEFAULT_WARNING_THRESHOLD)  <= _ATOL
        assert abs(cr.config.critical - DEFAULT_CRITICAL_THRESHOLD) <= _ATOL
