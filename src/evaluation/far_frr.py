"""
evaluation/far_frr.py
=====================
False Acceptance Rate (FAR) and False Rejection Rate (FRR) with interval
estimates.

Phase 6/7 -- SIH26141 | Blockchain & Cybersecurity.

    FAR = FP / (FP + TN)   -- rate of accepting forged/attack signatures
    FRR = FN / (FN + TP)   -- rate of rejecting legitimate signatures
    EER -- threshold where FAR == FRR

Why intervals are mandatory here
--------------------------------
A rate is a point estimate from a finite sample, and a *small* sample makes
an extreme rate look far more certain than it is.  Observing zero false
accepts in 25 attack sessions does not mean FAR = 0: the 95% Clopper-Pearson
upper bound is still ~13.7%.  Reporting "FAR = 0.00%" from such a sample
overstates the result by an order of magnitude.

Every rate this module returns therefore carries a confidence interval, and
:class:`RateEstimate` renders as ``"0.00% (95% CI [0.00%, 13.72%], n=25)"``
so the sample size travels with the number.

Two interval methods are provided:

``wilson`` (default)
    Good general-purpose coverage, including for small samples and rates
    near 0 or 1.  Slightly liberal (intervals a touch narrow).

``clopper_pearson``
    Exact, based on the Beta distribution.  Never under-covers, so it is
    the honest choice when reporting a 0% or 100% rate -- which is exactly
    the case this project needs to report carefully.

No AI/ML -- all figures come from threshold sweeps over simulation results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from evaluation.error_bounds import ConfidenceInterval, wilson_interval
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "RateEstimate",
    "clopper_pearson_interval",
    "rate_with_interval",
    "compute_far",
    "compute_frr",
    "compute_eer",
    "sweep_far_frr",
    "INTERVAL_METHODS",
]

#: Supported interval estimators.
INTERVAL_METHODS: Tuple[str, ...] = ("wilson", "clopper_pearson")


# ---------------------------------------------------------------------------
# Rate + interval container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RateEstimate:
    """A rate reported together with its uncertainty.

    Attributes
    ----------
    rate : float
        Point estimate in [0, 1].
    successes : int
        Numerator (e.g. false accepts).
    trials : int
        Denominator (e.g. attack sessions evaluated).
    lower, upper : float
        Confidence-interval bounds in [0, 1].
    confidence : float
        Nominal confidence level (e.g. 0.95).
    method : str
        Interval estimator used.
    """

    rate: float
    successes: int
    trials: int
    lower: float
    upper: float
    confidence: float = 0.95
    method: str = "wilson"

    @property
    def margin(self) -> float:
        """Half-width of the interval -- a one-number summary of precision."""
        return (self.upper - self.lower) / 2.0

    def as_percent(self) -> str:
        """Render as ``'0.00% (95% CI [0.00%, 13.72%], n=25)'``."""
        return (
            f"{self.rate * 100:.2f}% "
            f"({int(self.confidence * 100)}% CI "
            f"[{self.lower * 100:.2f}%, {self.upper * 100:.2f}%], "
            f"n={self.trials})"
        )

    def to_row(self, metric: str) -> dict:
        """Return a flat dict suitable for a results CSV row."""
        return {
            "Metric": metric,
            "Value": self.rate,
            "CI_Lower": self.lower,
            "CI_Upper": self.upper,
            "Successes": self.successes,
            "Trials": self.trials,
            "Confidence": self.confidence,
            "Method": self.method,
        }

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"RateEstimate({self.as_percent()}, method={self.method!r})"


# ---------------------------------------------------------------------------
# Interval estimators
# ---------------------------------------------------------------------------

def clopper_pearson_interval(
    successes: int,
    trials: int,
    confidence: float = 0.95,
) -> ConfidenceInterval:
    """Exact binomial (Clopper-Pearson) confidence interval.

    Inverts the binomial test using the Beta distribution::

        lower = Beta(alpha/2;      k,     n-k+1)
        upper = Beta(1-alpha/2;  k+1,     n-k)

    with ``lower = 0`` when ``k = 0`` and ``upper = 1`` when ``k = n``.
    The interval never under-covers, which is what makes it the right
    choice for reporting a 0% or 100% observed rate.

    Parameters
    ----------
    successes : int
        Number of successes observed.
    trials : int
        Number of trials.
    confidence : float
        Confidence level in (0, 1).

    Returns
    -------
    ConfidenceInterval

    Raises
    ------
    ValueError
        If *trials* < 0, *successes* is outside [0, trials], or
        *confidence* is not in (0, 1).
    """
    if trials < 0:
        raise ValueError(f"trials must be >= 0, got {trials}.")
    if not (0 <= successes <= trials):
        raise ValueError(
            f"successes must be in [0, {trials}], got {successes}."
        )
    if not (0.0 < confidence < 1.0):
        raise ValueError(f"confidence must be in (0,1), got {confidence}.")

    if trials == 0:
        return ConfidenceInterval(lower=0.0, upper=1.0, confidence=confidence)

    from scipy import stats

    alpha = 1.0 - confidence

    lower = (
        0.0 if successes == 0
        else float(stats.beta.ppf(alpha / 2.0, successes, trials - successes + 1))
    )
    upper = (
        1.0 if successes == trials
        else float(stats.beta.ppf(1.0 - alpha / 2.0, successes + 1, trials - successes))
    )
    return ConfidenceInterval(lower=lower, upper=upper, confidence=confidence)


def rate_with_interval(
    successes: int,
    trials: int,
    confidence: float = 0.95,
    method: str = "wilson",
) -> RateEstimate:
    """Compute a rate and its confidence interval.

    Parameters
    ----------
    successes : int
        Numerator.
    trials : int
        Denominator.  ``0`` yields a fully uninformative [0, 1] interval
        rather than a divide-by-zero.
    confidence : float
        Confidence level.
    method : str
        One of :data:`INTERVAL_METHODS`.

    Returns
    -------
    RateEstimate

    Raises
    ------
    ValueError
        If *method* is unknown.
    """
    if method not in INTERVAL_METHODS:
        raise ValueError(
            f"Unknown interval method {method!r}. Supported: {list(INTERVAL_METHODS)}"
        )

    if trials == 0:
        return RateEstimate(
            rate=0.0, successes=0, trials=0,
            lower=0.0, upper=1.0,
            confidence=confidence, method=method,
        )

    ci = (
        wilson_interval(successes, trials, confidence=confidence)
        if method == "wilson"
        else clopper_pearson_interval(successes, trials, confidence=confidence)
    )
    return RateEstimate(
        rate=successes / trials,
        successes=successes,
        trials=trials,
        lower=float(ci.lower),
        upper=float(ci.upper),
        confidence=confidence,
        method=method,
    )


# ---------------------------------------------------------------------------
# FAR / FRR
# ---------------------------------------------------------------------------

def compute_far(
    false_accepts: int,
    attack_trials: int,
    confidence: float = 0.95,
    method: str = "clopper_pearson",
) -> RateEstimate:
    """Compute the False Acceptance Rate with a confidence interval.

    ``FAR = FP / (FP + TN)`` -- the fraction of *attack* sessions that the
    detector let through.

    Parameters
    ----------
    false_accepts : int
        Attack sessions classified as benign (FP).
    attack_trials : int
        Total attack sessions evaluated (FP + TN).
    confidence : float
        Confidence level.
    method : str
        Interval estimator.  Defaults to ``'clopper_pearson'`` because FAR
        is routinely near 0, where exact coverage matters most.

    Returns
    -------
    RateEstimate
    """
    est = rate_with_interval(false_accepts, attack_trials, confidence, method)
    logger.info("FAR = %s", est.as_percent())
    return est


def compute_frr(
    false_rejects: int,
    legitimate_trials: int,
    confidence: float = 0.95,
    method: str = "clopper_pearson",
) -> RateEstimate:
    """Compute the False Rejection Rate with a confidence interval.

    ``FRR = FN / (FN + TP)`` -- the fraction of *legitimate* sessions the
    detector wrongly flagged.

    Parameters
    ----------
    false_rejects : int
        Legitimate sessions flagged as attacks (FN).
    legitimate_trials : int
        Total legitimate sessions evaluated.
    confidence : float
        Confidence level.
    method : str
        Interval estimator.

    Returns
    -------
    RateEstimate
    """
    est = rate_with_interval(false_rejects, legitimate_trials, confidence, method)
    logger.info("FRR = %s", est.as_percent())
    return est


def sweep_far_frr(
    legitimate_scores: Sequence[float],
    attack_scores: Sequence[float],
    thresholds: Optional[Sequence[float]] = None,
    confidence: float = 0.95,
    method: str = "clopper_pearson",
) -> List[dict]:
    """Sweep anomaly thresholds and report FAR/FRR with intervals at each.

    A session is flagged when its anomaly score is **>=** the threshold.

    Parameters
    ----------
    legitimate_scores : sequence of float
        Anomaly scores from legitimate sessions.
    attack_scores : sequence of float
        Anomaly scores from attack sessions.
    thresholds : sequence of float or None
        Thresholds to evaluate.  ``None`` uses 101 points spanning the
        observed score range.
    confidence : float
        Confidence level for the intervals.
    method : str
        Interval estimator.

    Returns
    -------
    list[dict]
        One row per threshold with FAR/FRR point estimates and bounds.
    """
    legit = np.asarray(legitimate_scores, dtype=float)
    attack = np.asarray(attack_scores, dtype=float)

    if thresholds is None:
        combined = np.concatenate([legit, attack]) if legit.size or attack.size else np.array([0.0])
        lo, hi = float(combined.min()), float(combined.max())
        if np.isclose(lo, hi):
            hi = lo + 1e-6
        thresholds = np.linspace(lo, hi, 101)

    rows: List[dict] = []
    for thr in thresholds:
        # Attack sessions scoring BELOW threshold slip through -> false accept
        false_accepts = int((attack < thr).sum())
        # Legitimate sessions scoring AT/ABOVE threshold are wrongly flagged
        false_rejects = int((legit >= thr).sum())

        far = compute_far(false_accepts, attack.size, confidence, method)
        frr = compute_frr(false_rejects, legit.size, confidence, method)

        rows.append({
            "threshold": float(thr),
            "far": far.rate,
            "far_ci_lower": far.lower,
            "far_ci_upper": far.upper,
            "frr": frr.rate,
            "frr_ci_lower": frr.lower,
            "frr_ci_upper": frr.upper,
            "n_attack": int(attack.size),
            "n_legitimate": int(legit.size),
        })
    return rows


def compute_eer(
    legitimate_scores: Sequence[float],
    attack_scores: Sequence[float],
    thresholds: Optional[Sequence[float]] = None,
) -> Tuple[float, float]:
    """Locate the Equal Error Rate operating point.

    Finds the threshold minimising ``|FAR - FRR|`` and returns it together
    with the averaged error rate there.

    Parameters
    ----------
    legitimate_scores : sequence of float
        Anomaly scores from legitimate sessions.
    attack_scores : sequence of float
        Anomaly scores from attack sessions.
    thresholds : sequence of float or None
        Thresholds to search.  ``None`` sweeps the observed range.

    Returns
    -------
    tuple[float, float]
        ``(eer_threshold, eer_rate)``.
    """
    rows = sweep_far_frr(legitimate_scores, attack_scores, thresholds)
    if not rows:
        return 0.0, 0.0

    best = min(rows, key=lambda r: abs(r["far"] - r["frr"]))
    eer = (best["far"] + best["frr"]) / 2.0
    logger.info(
        "EER = %.4f at threshold %.6f (FAR=%.4f, FRR=%.4f)",
        eer, best["threshold"], best["far"], best["frr"],
    )
    return float(best["threshold"]), float(eer)
