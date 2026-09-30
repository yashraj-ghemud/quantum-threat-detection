"""
security/statistics.py
=======================
Measurement statistics derived from QDS verification outcomes.

Phase 4 -- SIH26141 | Blockchain & Cybersecurity.

Computes deterministic, explainable statistics from the binary measurement
outcomes {-1, +1} produced by Phase 3 ``VerificationResult`` objects.

Mathematics
-----------
For n binary outcomes  x_i ∈ {-1, +1}:

    positive_count  = Σ 1[x_i = +1]
    negative_count  = Σ 1[x_i = -1]
    p_plus          = positive_count / n          (empirical prob of +1)
    p_minus         = 1 - p_plus
    mean            = Σ x_i / n                   = p_plus - p_minus
    variance        = Σ (x_i - mean)^2 / n
    match_rate      = matches / n
    mismatch_rate   = 1 - match_rate

No AI/ML is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "MeasurementStats",
    "BasisStats",
    "compute_measurement_stats",
    "compute_basis_stats",
    "stats_from_verification",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BasisStats:
    """Statistics for measurements in one Pauli basis.

    Attributes
    ----------
    basis : str
        Pauli basis label: ``'x'``, ``'y'``, or ``'z'``.
    count : int
        Number of measurements in this basis.
    positive_count : int
        Count of +1 outcomes.
    negative_count : int
        Count of -1 outcomes.
    p_plus : float
        Empirical P(+1) in [0, 1].
    p_minus : float
        Empirical P(-1) in [0, 1].
    mean : float
        Empirical mean of outcomes in [-1, +1].
    variance : float
        Empirical variance in [0, 1].
    match_rate : float
        Fraction of elements where measured == expected.
    mismatch_rate : float
        Fraction of elements where measured != expected.
    """

    basis: str
    count: int
    positive_count: int
    negative_count: int
    p_plus: float
    p_minus: float
    mean: float
    variance: float
    match_rate: float
    mismatch_rate: float


@dataclass
class MeasurementStats:
    """Complete measurement statistics for one QDS verification session.

    Attributes
    ----------
    total : int
        Total number of measured elements.
    positive_count : int
        Elements with measured eigenvalue +1.
    negative_count : int
        Elements with measured eigenvalue -1.
    p_plus : float
        Empirical probability of +1 outcome.
    p_minus : float
        Empirical probability of -1 outcome.
    mean : float
        Empirical mean of binary outcomes, mean = p_plus - p_minus.
    variance : float
        Empirical variance  = 1 - mean^2  for Bernoulli {-1,+1}.
    match_rate : float
        Fraction of elements that match the expected eigenvalue.
    mismatch_rate : float
        Fraction of elements that do NOT match.
    avg_p_plus_expected : float
        Average of the per-element P(+1) values from projection.
    avg_p_minus_expected : float
        Average of the per-element P(-1) values from projection.
    basis_stats : dict[str, BasisStats]
        Per-basis breakdown (keys: ``'x'``, ``'y'``, ``'z'``).
    """

    total: int
    positive_count: int
    negative_count: int
    p_plus: float
    p_minus: float
    mean: float
    variance: float
    match_rate: float
    mismatch_rate: float
    avg_p_plus_expected: float
    avg_p_minus_expected: float
    basis_stats: Dict[str, BasisStats] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Return True when all probabilities lie in [0,1] and sum checks pass."""
        try:
            assert 0.0 - 1e-9 <= self.p_plus  <= 1.0 + 1e-9
            assert 0.0 - 1e-9 <= self.p_minus <= 1.0 + 1e-9
            assert abs(self.p_plus + self.p_minus - 1.0) <= 1e-9
            assert 0.0 - 1e-9 <= self.match_rate    <= 1.0 + 1e-9
            assert 0.0 - 1e-9 <= self.mismatch_rate <= 1.0 + 1e-9
            assert abs(self.match_rate + self.mismatch_rate - 1.0) <= 1e-9
        except AssertionError:
            return False
        return True


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_measurement_stats(
    measured_eigenvalues: Sequence[int],
    expected_eigenvalues: Sequence[int],
    p_plus_values: Sequence[float],
    p_minus_values: Sequence[float],
    bases: Sequence[str],
) -> MeasurementStats:
    """Compute full measurement statistics from raw outcome sequences.

    Parameters
    ----------
    measured_eigenvalues : sequence of int (+1 / -1)
        Eigenvalue observed at each position.
    expected_eigenvalues : sequence of int (+1 / -1)
        Eigenvalue expected at each position.
    p_plus_values : sequence of float
        P(+1) from the projective measurement at each position.
    p_minus_values : sequence of float
        P(-1) from the projective measurement at each position.
    bases : sequence of str
        Pauli basis used at each position (``'x'``, ``'y'``, or ``'z'``).

    Returns
    -------
    MeasurementStats
    """
    n = len(measured_eigenvalues)
    if n == 0:
        return _empty_stats()

    meas  = np.array(measured_eigenvalues, dtype=float)
    exp   = np.array(expected_eigenvalues,  dtype=float)
    pplus = np.array(p_plus_values,         dtype=float)
    pminus = np.array(p_minus_values,       dtype=float)

    pos_count = int(np.sum(meas == +1))
    neg_count = int(np.sum(meas == -1))
    p_plus_emp  = float(np.clip(pos_count / n, 0.0, 1.0))
    p_minus_emp = float(np.clip(neg_count / n, 0.0, 1.0))
    mean_val    = float(np.mean(meas))                   # = p_plus - p_minus
    variance    = float(np.var(meas))                    # = 1 - mean^2 for balanced binary
    matches     = int(np.sum(meas == exp))
    match_rate  = float(matches / n)
    mismatch_rate = float(1.0 - match_rate)
    avg_pplus = float(np.mean(pplus))
    avg_pminus = float(np.mean(pminus))

    basis_stats = compute_basis_stats(
        measured_eigenvalues, expected_eigenvalues,
        p_plus_values, p_minus_values, bases
    )

    stats = MeasurementStats(
        total=n,
        positive_count=pos_count,
        negative_count=neg_count,
        p_plus=p_plus_emp,
        p_minus=p_minus_emp,
        mean=mean_val,
        variance=variance,
        match_rate=match_rate,
        mismatch_rate=mismatch_rate,
        avg_p_plus_expected=avg_pplus,
        avg_p_minus_expected=avg_pminus,
        basis_stats=basis_stats,
    )
    logger.debug("MeasurementStats: n=%d match=%.4f mismatch=%.4f mean=%.4f var=%.4f",
                 n, match_rate, mismatch_rate, mean_val, variance)
    return stats


def compute_basis_stats(
    measured_eigenvalues: Sequence[int],
    expected_eigenvalues: Sequence[int],
    p_plus_values: Sequence[float],
    p_minus_values: Sequence[float],
    bases: Sequence[str],
) -> Dict[str, BasisStats]:
    """Compute per-Pauli-basis statistics.

    Parameters
    ----------
    (same as ``compute_measurement_stats``)

    Returns
    -------
    dict[str, BasisStats]
        Keys: ``'x'``, ``'y'``, ``'z'``.  Missing bases get zero-count stubs.
    """
    result: Dict[str, BasisStats] = {}
    bases_list = list(bases)
    meas_list  = list(measured_eigenvalues)
    exp_list   = list(expected_eigenvalues)
    pplus_list = list(p_plus_values)
    pminus_list = list(p_minus_values)

    for basis in ("x", "y", "z"):
        indices = [i for i, b in enumerate(bases_list) if b == basis]
        if not indices:
            result[basis] = BasisStats(
                basis=basis, count=0,
                positive_count=0, negative_count=0,
                p_plus=0.5, p_minus=0.5,
                mean=0.0, variance=1.0,
                match_rate=1.0, mismatch_rate=0.0,
            )
            continue
        m = np.array([meas_list[i] for i in indices], dtype=float)
        e = np.array([exp_list[i]  for i in indices], dtype=float)
        pp = np.array([pplus_list[i] for i in indices], dtype=float)
        pm = np.array([pminus_list[i] for i in indices], dtype=float)
        n = len(m)
        pos = int(np.sum(m == +1))
        neg = int(np.sum(m == -1))
        matches_b = int(np.sum(m == e))
        result[basis] = BasisStats(
            basis=basis,
            count=n,
            positive_count=pos,
            negative_count=neg,
            p_plus=float(np.clip(pos / n, 0, 1)),
            p_minus=float(np.clip(neg / n, 0, 1)),
            mean=float(np.mean(m)),
            variance=float(np.var(m)),
            match_rate=float(matches_b / n),
            mismatch_rate=float(1 - matches_b / n),
        )
    return result


def stats_from_verification(vr) -> MeasurementStats:
    """Build ``MeasurementStats`` directly from a ``VerificationResult``.

    Parameters
    ----------
    vr : qds.verification.VerificationResult
        Output of ``qds.verification.verify_signature``.

    Returns
    -------
    MeasurementStats
    """
    ers = vr.element_results
    if not ers:
        return _empty_stats()
    return compute_measurement_stats(
        measured_eigenvalues=[e.measured_eigenvalue for e in ers],
        expected_eigenvalues=[e.expected_eigenvalue for e in ers],
        p_plus_values=[e.p_plus for e in ers],
        p_minus_values=[e.p_minus for e in ers],
        bases=[e.expected_basis for e in ers],
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _empty_stats() -> MeasurementStats:
    """Return a safe zero-count MeasurementStats for empty input."""
    bs = {b: BasisStats(basis=b, count=0, positive_count=0, negative_count=0,
                        p_plus=0.5, p_minus=0.5, mean=0.0, variance=1.0,
                        match_rate=1.0, mismatch_rate=0.0)
          for b in ("x", "y", "z")}
    return MeasurementStats(
        total=0, positive_count=0, negative_count=0,
        p_plus=0.5, p_minus=0.5,
        mean=0.0, variance=1.0,
        match_rate=1.0, mismatch_rate=0.0,
        avg_p_plus_expected=0.5, avg_p_minus_expected=0.5,
        basis_stats=bs,
    )
