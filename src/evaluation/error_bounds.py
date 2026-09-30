"""
evaluation/error_bounds.py
==========================
Statistical confidence intervals for evaluation metrics.

Phase 6 -- SIH26141 | Blockchain & Cybersecurity.

No AI/ML libraries used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

__all__: list[str] = ["ConfidenceInterval", "wilson_interval", "Z_SCORES"]

# Standard normal percentiles for common confidence levels
Z_SCORES = {
    0.90: 1.645,
    0.95: 1.960,
    0.99: 2.576,
}


@dataclass
class ConfidenceInterval:
    """Represents a statistical confidence interval.
    
    Attributes
    ----------
    lower : float
        Lower bound of the interval [0.0, 1.0].
    upper : float
        Upper bound of the interval [0.0, 1.0].
    confidence : float
        Confidence level used (e.g., 0.95).
    """
    lower: float
    upper: float
    confidence: float


def wilson_interval(
    successes: int,
    trials: int,
    confidence: float = 0.95,
) -> ConfidenceInterval:
    """Calculate the Wilson score interval for a binomial proportion.
    
    Preferred over the normal approximation for small N or extreme probabilities.
    
    Parameters
    ----------
    successes : int
        Number of successful outcomes (e.g., correctly detected attacks).
    trials : int
        Total number of trials.
    confidence : float
        Confidence level to use (0.90, 0.95, or 0.99).
        
    Returns
    -------
    ConfidenceInterval
        The lower and upper bounds of the proportion, clipped to [0, 1].
    """
    if not (0 <= successes <= trials):
        raise ValueError("successes must be between 0 and trials")
    
    if trials == 0:
        return ConfidenceInterval(lower=0.0, upper=0.0, confidence=confidence)
    
    if confidence not in Z_SCORES:
        raise ValueError(
            f"Unsupported confidence level {confidence}. "
            f"Supported: {list(Z_SCORES.keys())}"
        )
        
    z = Z_SCORES[confidence]
    n = trials
    p = successes / n
    
    # Formula components
    z_sq = z * z
    denom = 1 + z_sq / n
    center = (p + z_sq / (2 * n)) / denom
    margin = (z / denom) * math.sqrt((p * (1 - p)) / n + z_sq / (4 * n * n))
    
    lower_bound = max(0.0, center - margin)
    upper_bound = min(1.0, center + margin)
    
    return ConfidenceInterval(
        lower=lower_bound,
        upper=upper_bound,
        confidence=confidence
    )
