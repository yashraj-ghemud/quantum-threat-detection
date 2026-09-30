"""
security/detector.py
=====================
Statistical threat detection engine.

Phase 4 -- SIH26141 | Blockchain & Cybersecurity.

Orchestrates the full detection pipeline:

    1. Build a ``SessionFingerprint`` from a ``VerificationResult``.
    2. Compute the anomaly score against a calibrated baseline fingerprint.
    3. Classify using calibrated thresholds (NORMAL / SUSPICIOUS / THREAT).
    4. Return a structured ``DetectionResult`` with full explanation.

The detector also supports:
    - Baseline collection from multiple legitimate sessions.
    - Percentile or sigma threshold calibration.
    - Z-score reporting for statistical interpretability.

All logic is deterministic; no AI/ML is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np

from security.anomaly import (
    AnomalyBreakdown,
    compute_anomaly_breakdown,
    z_score_mismatch,
)
from security.fingerprint import (
    SessionFingerprint,
    build_baseline_fingerprint,
    build_fingerprint,
)
from security.statistics import MeasurementStats, stats_from_verification
from security.thresholds import (
    CalibrationResult,
    ThresholdConfig,
    DEFAULT_CRITICAL_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    percentile_calibrate,
)
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "DetectionResult",
    "ThreatDetector",
    "Classification",
]

# ---------------------------------------------------------------------------
# Classification literals
# ---------------------------------------------------------------------------

Classification = str  # Literal["NORMAL", "SUSPICIOUS", "THREAT"]
NORMAL     = "NORMAL"
SUSPICIOUS = "SUSPICIOUS"
THREAT     = "THREAT"


# ---------------------------------------------------------------------------
# DetectionResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    """Structured output of a single threat-detection run.

    Attributes
    ----------
    session_id : str
        Identifier of the session that was evaluated.
    classification : str
        One of ``'NORMAL'``, ``'SUSPICIOUS'``, ``'THREAT'``.
    anomaly_score : float
        Composite anomaly score in [0, 1].
    warning_threshold : float
        Warning threshold used for classification.
    critical_threshold : float
        Critical threshold used for classification.
    mismatch_rate : float
        Observed mismatch rate for the session.
    match_rate : float
        Observed match rate for the session.
    mean : float
        Empirical mean of binary outcomes.
    variance : float
        Empirical variance.
    z_score : float
        Z-score of the observed mismatch rate vs. baseline distribution.
    breakdown : AnomalyBreakdown
        Per-component score breakdown.
    stats : MeasurementStats
        Full measurement statistics for this session.
    fingerprint : SessionFingerprint
        Fingerprint of this session.
    indicators : list[str]
        Human-readable explanation of triggered anomaly indicators.
    explanation : str
        One-line human-readable summary.
    """

    session_id:         str
    classification:     Classification
    anomaly_score:      float
    warning_threshold:  float
    critical_threshold: float
    mismatch_rate:      float
    match_rate:         float
    mean:               float
    variance:           float
    z_score:            float
    breakdown:          AnomalyBreakdown
    stats:              MeasurementStats
    fingerprint:        SessionFingerprint
    indicators:         List[str] = field(default_factory=list)
    explanation:        str = ""

    def __repr__(self) -> str:
        return (
            f"DetectionResult(id={self.session_id[:8]}..., "
            f"classification={self.classification!r}, "
            f"score={self.anomaly_score:.4f}, "
            f"mismatch={self.mismatch_rate:.4f})"
        )


# ---------------------------------------------------------------------------
# ThreatDetector
# ---------------------------------------------------------------------------

class ThreatDetector:
    """Quantum-statistical threat detection engine.

    Usage
    -----
    1. Build a detector with ``ThreatDetector()``.
    2. Feed legitimate sessions via ``add_baseline_session()``.
    3. Call ``calibrate()`` to derive thresholds from baseline.
    4. Call ``detect(verification_result)`` for each new session.

    No AI/ML — all decisions use statistical metrics and thresholds.

    Parameters
    ----------
    warning_threshold : float or None
        Override warning threshold.  ``None`` → derived from calibration.
    critical_threshold : float or None
        Override critical threshold.  ``None`` → derived from calibration.
    calibration_method : str
        ``'percentile'`` (default) or ``'sigma'``.
    warn_percentile : float
        Percentile for warning threshold (percentile method).
    crit_percentile : float
        Percentile for critical threshold (percentile method).
    """

    def __init__(
        self,
        warning_threshold:  Optional[float] = None,
        critical_threshold: Optional[float] = None,
        calibration_method: str = "percentile",
        warn_percentile:    float = 75.0,
        crit_percentile:    float = 95.0,
    ) -> None:
        self._override_warning  = warning_threshold
        self._override_critical = critical_threshold
        self._calibration_method = calibration_method
        self._warn_pct  = warn_percentile
        self._crit_pct  = crit_percentile

        self._baseline_fingerprints: List[SessionFingerprint] = []
        self._baseline_scores: List[float] = []

        self._baseline_fp:   Optional[SessionFingerprint] = None
        self._calibration:   Optional[CalibrationResult]  = None
        self._threshold_cfg: Optional[ThresholdConfig]    = None

        # Set defaults before calibration
        self._threshold_cfg = ThresholdConfig(
            warning=self._override_warning  or DEFAULT_WARNING_THRESHOLD,
            critical=self._override_critical or DEFAULT_CRITICAL_THRESHOLD,
            method="fixed",
        )

    # ------------------------------------------------------------------
    # Baseline management
    # ------------------------------------------------------------------

    def add_baseline_session(self, vr) -> "ThreatDetector":
        """Add one legitimate ``VerificationResult`` to the baseline pool.

        Parameters
        ----------
        vr : qds.verification.VerificationResult

        Returns
        -------
        ThreatDetector (self, for chaining)
        """
        fp = build_fingerprint(vr, session_id=getattr(vr, "signature_id", ""))
        self._baseline_fingerprints.append(fp)
        logger.debug("Added baseline session %s (total=%d)",
                     fp.session_id[:8], len(self._baseline_fingerprints))
        return self

    def add_baseline_sessions(self, vrs: Sequence) -> "ThreatDetector":
        """Add multiple ``VerificationResult`` objects to the baseline pool."""
        for vr in vrs:
            self.add_baseline_session(vr)
        return self

    @property
    def baseline_size(self) -> int:
        """Number of sessions in the baseline pool."""
        return len(self._baseline_fingerprints)

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def calibrate(self) -> "ThreatDetector":
        """Derive thresholds from the collected baseline sessions.

        Must be called after ``add_baseline_session`` calls and before
        ``detect``.

        Returns
        -------
        ThreatDetector (self, for chaining)

        Raises
        ------
        ValueError
            If no baseline sessions have been added.
        """
        if not self._baseline_fingerprints:
            raise ValueError(
                "No baseline sessions available.  "
                "Call add_baseline_session() first."
            )

        # Build aggregate baseline fingerprint
        self._baseline_fp = build_baseline_fingerprint(self._baseline_fingerprints)

        # Compute anomaly score for every baseline session against the baseline
        self._baseline_scores = [
            compute_anomaly_breakdown(fp, self._baseline_fp).anomaly_score
            for fp in self._baseline_fingerprints
        ]

        # Calibrate thresholds
        if self._override_warning is not None and self._override_critical is not None:
            from security.thresholds import fixed_calibrate
            self._calibration = fixed_calibrate(
                self._override_warning, self._override_critical,
                baseline_scores=self._baseline_scores,
            )
        elif self._calibration_method == "sigma":
            from security.thresholds import sigma_calibrate
            self._calibration = sigma_calibrate(self._baseline_scores)
        else:
            self._calibration = percentile_calibrate(
                self._baseline_scores,
                warn_percentile=self._warn_pct,
                crit_percentile=self._crit_pct,
            )
        self._threshold_cfg = self._calibration.config
        logger.info(
            "Calibrated: n=%d warn=%.4f crit=%.4f method=%s",
            self.baseline_size,
            self._threshold_cfg.warning,
            self._threshold_cfg.critical,
            self._threshold_cfg.method,
        )
        return self

    @property
    def thresholds(self) -> ThresholdConfig:
        """Current threshold configuration."""
        return self._threshold_cfg

    @property
    def calibration(self) -> Optional[CalibrationResult]:
        """Calibration result (None before ``calibrate()`` is called)."""
        return self._calibration

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, vr, session_id: str = "") -> DetectionResult:
        """Detect threats in one verification session.

        Parameters
        ----------
        vr : qds.verification.VerificationResult
            Session to evaluate.
        session_id : str
            Optional label; defaults to the signature_id from *vr*.

        Returns
        -------
        DetectionResult
        """
        sid = session_id or getattr(vr, "signature_id", "session")
        stats: MeasurementStats = stats_from_verification(vr)
        fp: SessionFingerprint = build_fingerprint(vr, session_id=sid)

        # Ensure we have a baseline fingerprint
        baseline_fp = self._baseline_fp
        if baseline_fp is None:
            # No calibration done yet — use fingerprint of this session as a
            # trivial same-session baseline (score will be 0)
            baseline_fp = fp

        breakdown = compute_anomaly_breakdown(fp, baseline_fp)
        score     = breakdown.anomaly_score
        cls       = self._threshold_cfg.classify(score)

        # Z-score for the mismatch rate
        if self._calibration is not None:
            bl_scores = np.array(self._calibration.baseline_scores, dtype=float)
            mm_scores = [
                bfp.mismatch_rate for bfp in self._baseline_fingerprints
            ]
            bl_mm_mean = float(np.mean(mm_scores)) if mm_scores else 0.0
            bl_mm_std  = float(np.std(mm_scores))  if mm_scores else 0.0
        else:
            bl_mm_mean, bl_mm_std = 0.0, 0.0

        z = z_score_mismatch(fp.mismatch_rate, bl_mm_mean, bl_mm_std)

        # Build explanation
        explanation = (
            f"{cls}: anomaly_score={score:.4f} "
            f"(warn={self._threshold_cfg.warning:.4f}, "
            f"crit={self._threshold_cfg.critical:.4f}) | "
            f"mismatch={fp.mismatch_rate:.4f} z={z:.2f}"
        )

        result = DetectionResult(
            session_id=sid,
            classification=cls,
            anomaly_score=score,
            warning_threshold=self._threshold_cfg.warning,
            critical_threshold=self._threshold_cfg.critical,
            mismatch_rate=fp.mismatch_rate,
            match_rate=fp.match_rate,
            mean=fp.mean,
            variance=fp.variance,
            z_score=z,
            breakdown=breakdown,
            stats=stats,
            fingerprint=fp,
            indicators=breakdown.indicators,
            explanation=explanation,
        )
        logger.info("detect %s: %s  score=%.4f", sid[:12], cls, score)
        return result
