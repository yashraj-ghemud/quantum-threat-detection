"""
security/thresholds.py
=======================
Threshold calibration for the statistical threat detector.

Phase 4 -- SIH26141 | Blockchain & Cybersecurity.

Thresholds are derived from a collection of anomaly scores computed on
legitimate baseline sessions.  Three tiers are defined:

    warning   Score at which a session is flagged as SUSPICIOUS.
    critical  Score at which a session is classified as THREAT.

Derivation methods
------------------
percentile_calibrate  : warning = p75 of baseline scores,
                        critical = p95 of baseline scores.
sigma_calibrate       : warning = mu + k_warn*sigma,
                        critical = mu + k_crit*sigma.
fixed_calibrate       : Caller supplies explicit float values.

All methods enforce  0 <= warning <= critical <= 1.

No AI/ML is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "ThresholdConfig",
    "CalibrationResult",
    "percentile_calibrate",
    "sigma_calibrate",
    "fixed_calibrate",
    "DEFAULT_WARNING_THRESHOLD",
    "DEFAULT_CRITICAL_THRESHOLD",
]

DEFAULT_WARNING_THRESHOLD:  float = 0.15
DEFAULT_CRITICAL_THRESHOLD: float = 0.35


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ThresholdConfig:
    """Calibrated detection thresholds.

    Attributes
    ----------
    warning : float
        Anomaly score >= warning  → SUSPICIOUS.
    critical : float
        Anomaly score >= critical → THREAT.
    method : str
        Derivation method: ``'percentile'``, ``'sigma'``, or ``'fixed'``.
    """

    warning:  float
    critical: float
    method:   str = "fixed"

    def __post_init__(self) -> None:
        if not (0.0 <= self.warning <= 1.0):
            raise ValueError(f"warning must be in [0,1], got {self.warning}.")
        if not (0.0 <= self.critical <= 1.0):
            raise ValueError(f"critical must be in [0,1], got {self.critical}.")
        if self.warning > self.critical:
            raise ValueError(
                f"warning ({self.warning}) must be <= critical ({self.critical})."
            )

    def classify(self, score: float) -> str:
        """Classify an anomaly score into NORMAL / SUSPICIOUS / THREAT.

        Boundary rule (inclusive lower bound, exclusive upper bound):
            score <  warning          → NORMAL
            warning <= score < critical → SUSPICIOUS
            score >= critical          → THREAT

        Parameters
        ----------
        score : float
            Anomaly score in [0, 1].

        Returns
        -------
        str
            One of ``'NORMAL'``, ``'SUSPICIOUS'``, ``'THREAT'``.
        """
        if score >= self.critical:
            return "THREAT"
        if score >= self.warning:
            return "SUSPICIOUS"
        return "NORMAL"

    def __repr__(self) -> str:
        return (
            f"ThresholdConfig(warning={self.warning:.4f}, "
            f"critical={self.critical:.4f}, method={self.method!r})"
        )


@dataclass
class CalibrationResult:
    """Full output of a threshold calibration run.

    Attributes
    ----------
    config : ThresholdConfig
        The calibrated thresholds.
    baseline_scores : list[float]
        Anomaly scores from the baseline sessions used for calibration.
    baseline_mean : float
        Mean anomaly score of baseline sessions.
    baseline_std : float
        Standard deviation of baseline anomaly scores.
    baseline_min : float
    baseline_max : float
    n_samples : int
        Number of baseline sessions used.
    """

    config:           ThresholdConfig
    baseline_scores:  List[float]
    baseline_mean:    float
    baseline_std:     float
    baseline_min:     float
    baseline_max:     float
    n_samples:        int


# ---------------------------------------------------------------------------
# Calibration functions
# ---------------------------------------------------------------------------

def percentile_calibrate(
    baseline_scores: Sequence[float],
    warn_percentile:  float = 75.0,
    crit_percentile:  float = 95.0,
    min_warning:      float = 0.05,
    min_critical:     float = 0.10,
) -> CalibrationResult:
    """Calibrate thresholds from percentiles of baseline anomaly scores.

    Parameters
    ----------
    baseline_scores : sequence of float
        Anomaly scores computed on legitimate sessions.
    warn_percentile : float
        Percentile for the warning threshold (default 75).
    crit_percentile : float
        Percentile for the critical threshold (default 95).
    min_warning : float
        Floor for the warning threshold (prevents degenerate 0 thresholds).
    min_critical : float
        Floor for the critical threshold.

    Returns
    -------
    CalibrationResult
    """
    if not baseline_scores:
        raise ValueError("baseline_scores must not be empty.")
    scores = np.array(list(baseline_scores), dtype=float)
    warn  = float(max(np.percentile(scores, warn_percentile), min_warning))
    crit  = float(max(np.percentile(scores, crit_percentile), min_critical))
    # Enforce ordering
    crit = max(crit, warn)

    cfg = ThresholdConfig(warning=warn, critical=crit, method="percentile")
    result = CalibrationResult(
        config=cfg,
        baseline_scores=list(scores),
        baseline_mean=float(np.mean(scores)),
        baseline_std=float(np.std(scores)),
        baseline_min=float(np.min(scores)),
        baseline_max=float(np.max(scores)),
        n_samples=len(scores),
    )
    logger.info(
        "percentile_calibrate: n=%d warn=%.4f crit=%.4f (p%g/p%g)",
        len(scores), warn, crit, warn_percentile, crit_percentile,
    )
    return result


def sigma_calibrate(
    baseline_scores: Sequence[float],
    k_warn:  float = 2.0,
    k_crit:  float = 3.0,
    min_warning:  float = 0.05,
    min_critical: float = 0.10,
) -> CalibrationResult:
    """Calibrate thresholds using the k-sigma rule.

    warning  = mu + k_warn * sigma
    critical = mu + k_crit * sigma

    Parameters
    ----------
    baseline_scores : sequence of float
    k_warn : float
        Sigma multiplier for warning (default 2.0).
    k_crit : float
        Sigma multiplier for critical (default 3.0).
    min_warning, min_critical : float
        Floors applied after sigma computation.

    Returns
    -------
    CalibrationResult
    """
    if not baseline_scores:
        raise ValueError("baseline_scores must not be empty.")
    scores = np.array(list(baseline_scores), dtype=float)
    mu, sigma = float(np.mean(scores)), float(np.std(scores))
    warn  = float(np.clip(max(mu + k_warn * sigma, min_warning),  0.0, 1.0))
    crit  = float(np.clip(max(mu + k_crit * sigma, min_critical), 0.0, 1.0))
    crit  = max(crit, warn)

    cfg = ThresholdConfig(warning=warn, critical=crit, method="sigma")
    result = CalibrationResult(
        config=cfg,
        baseline_scores=list(scores),
        baseline_mean=mu,
        baseline_std=sigma,
        baseline_min=float(np.min(scores)),
        baseline_max=float(np.max(scores)),
        n_samples=len(scores),
    )
    logger.info(
        "sigma_calibrate: n=%d mu=%.4f sigma=%.4f warn=%.4f crit=%.4f",
        len(scores), mu, sigma, warn, crit,
    )
    return result


def fixed_calibrate(
    warning:  float = DEFAULT_WARNING_THRESHOLD,
    critical: float = DEFAULT_CRITICAL_THRESHOLD,
    baseline_scores: Optional[Sequence[float]] = None,
) -> CalibrationResult:
    """Use explicit fixed threshold values.

    Parameters
    ----------
    warning : float
        Warning threshold.
    critical : float
        Critical threshold.
    baseline_scores : sequence of float or None
        Optional baseline scores for metadata only (not used for calibration).

    Returns
    -------
    CalibrationResult
    """
    cfg = ThresholdConfig(warning=warning, critical=critical, method="fixed")
    scores = list(baseline_scores) if baseline_scores else [0.0]
    arr = np.array(scores, dtype=float)
    return CalibrationResult(
        config=cfg,
        baseline_scores=scores,
        baseline_mean=float(np.mean(arr)),
        baseline_std=float(np.std(arr)),
        baseline_min=float(np.min(arr)),
        baseline_max=float(np.max(arr)),
        n_samples=len(scores),
    )
