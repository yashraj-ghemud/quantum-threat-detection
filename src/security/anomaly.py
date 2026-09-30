"""
security/anomaly.py
====================
Deterministic statistical anomaly scoring.

Phase 4 -- SIH26141 | Blockchain & Cybersecurity.

The anomaly score quantifies how much an observed verification session
deviates from a legitimate baseline.  It is composed of four additive
components, each normalised to [0, 1]:

    Component 1 — Mismatch-rate deviation  (weight 0.40)
        delta_mismatch = |mismatch_obs - mismatch_baseline|
        This is the most direct indicator of a tampered signature.

    Component 2 — Mean deviation  (weight 0.25)
        delta_mean = |mean_obs - mean_baseline| / 2
        Dividing by 2 normalises the range of mean ∈ [-1,+1].

    Component 3 — P(+1) deviation  (weight 0.20)
        delta_pplus = |p_plus_obs - p_plus_baseline|

    Component 4 — Basis-wise mismatch deviation  (weight 0.15)
        delta_basis = mean over {x,y,z} of |mismatch_obs_b - mismatch_baseline_b|
        Captures basis-localised tampering patterns.

    anomaly_score = clip(
        w1*delta_mismatch + w2*delta_mean + w3*delta_pplus + w4*delta_basis,
        0, 1
    )

Interpretation
--------------
score = 0.0   → perfectly matches the baseline (legitimate session)
score = 1.0   → maximum deviation from baseline (extreme attack)

The score is:
    - Deterministic: no randomness, same inputs -> same output.
    - Bounded: always in [0, 1].
    - Explainable: every component has a documented statistical meaning.
    - No AI/ML: purely mathematical metric.

Additionally provides:
    - Z-score for the mismatch rate deviation.
    - Per-component deviation breakdown for reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

from security.fingerprint import SessionFingerprint
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "AnomalyBreakdown",
    "ANOMALY_WEIGHTS",
    "compute_anomaly_score",
    "compute_anomaly_breakdown",
    "z_score_mismatch",
]

# ---------------------------------------------------------------------------
# Weights (must sum to 1.0)
# ---------------------------------------------------------------------------

ANOMALY_WEIGHTS: Dict[str, float] = {
    "mismatch_rate":  0.40,
    "mean":           0.25,
    "p_plus":         0.20,
    "basis_mismatch": 0.15,
}
assert abs(sum(ANOMALY_WEIGHTS.values()) - 1.0) < 1e-12, "Weights must sum to 1."


# ---------------------------------------------------------------------------
# Breakdown dataclass
# ---------------------------------------------------------------------------

@dataclass
class AnomalyBreakdown:
    """Per-component breakdown of the anomaly score.

    Attributes
    ----------
    delta_mismatch : float
        |mismatch_obs - mismatch_baseline|
    delta_mean : float
        |mean_obs - mean_baseline| / 2  (normalised to [0, 1])
    delta_p_plus : float
        |p_plus_obs - p_plus_baseline|
    delta_basis : float
        Mean per-basis mismatch deviation.
    anomaly_score : float
        Weighted sum, clipped to [0, 1].
    indicators : list[str]
        Human-readable descriptions of the largest contributors.
    """

    delta_mismatch:  float
    delta_mean:      float
    delta_p_plus:    float
    delta_basis:     float
    anomaly_score:   float
    indicators:      list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core scoring functions
# ---------------------------------------------------------------------------

def compute_anomaly_breakdown(
    observed: SessionFingerprint,
    baseline: SessionFingerprint,
) -> AnomalyBreakdown:
    """Compute the full anomaly breakdown for one session vs. baseline.

    Parameters
    ----------
    observed : SessionFingerprint
        Fingerprint of the session being evaluated.
    baseline : SessionFingerprint
        Fingerprint representing legitimate behaviour (from calibration).

    Returns
    -------
    AnomalyBreakdown
        Full breakdown with per-component deviations and composite score.
    """
    # Component 1: mismatch-rate deviation
    delta_mismatch = abs(observed.mismatch_rate - baseline.mismatch_rate)

    # Component 2: mean deviation (normalised to [0,1])
    delta_mean = abs(observed.mean - baseline.mean) / 2.0

    # Component 3: p_plus deviation
    delta_p_plus = abs(observed.avg_p_plus_expected - baseline.avg_p_plus_expected)

    # Component 4: basis-wise mismatch deviation
    basis_devs = []
    for basis in ("x", "y", "z"):
        obs_b  = observed.basis_fingerprints.get(basis)
        base_b = baseline.basis_fingerprints.get(basis)
        if obs_b is not None and base_b is not None and obs_b.count > 0:
            basis_devs.append(abs(obs_b.mismatch_rate - base_b.mismatch_rate))
    delta_basis = float(np.mean(basis_devs)) if basis_devs else 0.0

    # Weighted composite score
    w = ANOMALY_WEIGHTS
    raw_score = (
        w["mismatch_rate"]  * delta_mismatch +
        w["mean"]           * delta_mean +
        w["p_plus"]         * delta_p_plus +
        w["basis_mismatch"] * delta_basis
    )
    score = float(np.clip(raw_score, 0.0, 1.0))

    # Build human-readable indicators for the largest deviations
    indicators = []
    threshold = 0.05
    if delta_mismatch > threshold:
        indicators.append(
            f"mismatch_rate_deviation={delta_mismatch:.4f} "
            f"(obs={observed.mismatch_rate:.4f} baseline={baseline.mismatch_rate:.4f})"
        )
    if delta_mean > threshold:
        indicators.append(
            f"mean_deviation={delta_mean:.4f} "
            f"(obs={observed.mean:.4f} baseline={baseline.mean:.4f})"
        )
    if delta_p_plus > threshold:
        indicators.append(
            f"p_plus_deviation={delta_p_plus:.4f} "
            f"(obs={observed.avg_p_plus_expected:.4f} baseline={baseline.avg_p_plus_expected:.4f})"
        )
    if delta_basis > threshold:
        indicators.append(f"basis_mismatch_deviation={delta_basis:.4f}")

    breakdown = AnomalyBreakdown(
        delta_mismatch=delta_mismatch,
        delta_mean=delta_mean,
        delta_p_plus=delta_p_plus,
        delta_basis=delta_basis,
        anomaly_score=score,
        indicators=indicators,
    )
    logger.debug(
        "Anomaly breakdown: score=%.4f d_mm=%.4f d_mean=%.4f d_pp=%.4f d_basis=%.4f",
        score, delta_mismatch, delta_mean, delta_p_plus, delta_basis,
    )
    return breakdown


def compute_anomaly_score(
    observed: SessionFingerprint,
    baseline: SessionFingerprint,
) -> float:
    """Return the scalar anomaly score for *observed* vs *baseline*.

    Parameters
    ----------
    observed : SessionFingerprint
    baseline : SessionFingerprint

    Returns
    -------
    float
        Score in [0, 1].
    """
    return compute_anomaly_breakdown(observed, baseline).anomaly_score


def z_score_mismatch(
    observed_mismatch: float,
    baseline_mean: float,
    baseline_std: float,
) -> float:
    """Compute a z-score for the observed mismatch rate.

    z = (observed - mu) / sigma

    Returns 0.0 when *baseline_std* <= 0 (degenerate case).

    Parameters
    ----------
    observed_mismatch : float
        Mismatch rate of the session under test.
    baseline_mean : float
        Mean mismatch rate across baseline sessions.
    baseline_std : float
        Standard deviation of mismatch rates across baseline sessions.

    Returns
    -------
    float
        Z-score (can be negative; not clipped).
    """
    if baseline_std <= 1e-12:
        return 0.0
    return float((observed_mismatch - baseline_mean) / baseline_std)
