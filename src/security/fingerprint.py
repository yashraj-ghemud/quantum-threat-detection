"""
security/fingerprint.py
========================
Session fingerprint for QDS verification sessions.

Phase 4 -- SIH26141 | Blockchain & Cybersecurity.

A ``SessionFingerprint`` is a compact, deterministic statistical summary
of one QDS verification session, built from ``MeasurementStats``.  It
carries global statistics plus per-basis breakdowns and is the primary
input to the anomaly-scoring layer.

Fingerprint fields are chosen to be:
    - Interpretable: each field has a clear physical/statistical meaning.
    - Sufficient: together they fully characterise the session behaviour.
    - Stable: for legitimate sessions they cluster tightly around a known
      baseline regardless of which Pauli eigenstates were chosen.

No AI/ML is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from security.statistics import (
    MeasurementStats,
    stats_from_verification,
)
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "BasisFingerprint",
    "SessionFingerprint",
    "build_fingerprint",
    "build_baseline_fingerprint",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BasisFingerprint:
    """Statistical fingerprint for one Pauli basis within a session.

    Attributes
    ----------
    basis : str
        ``'x'``, ``'y'``, or ``'z'``.
    count : int
        Number of elements measured in this basis.
    p_plus : float
        Empirical P(+1) for this basis.
    mean : float
        Empirical mean for this basis.
    mismatch_rate : float
        Fraction of mismatches in this basis.
    """

    basis: str
    count: int
    p_plus: float
    mean: float
    mismatch_rate: float


@dataclass
class SessionFingerprint:
    """Statistical fingerprint for one complete QDS verification session.

    Built from a ``MeasurementStats`` object.  Used as the representation
    passed to the anomaly scorer and stored in the baseline.

    Attributes
    ----------
    session_id : str
        Identifier for the session (e.g. signature_id or a label).
    total : int
        Total elements in the session.
    p_plus : float
        Global empirical P(+1).
    p_minus : float
        Global empirical P(-1).
    mean : float
        Global empirical mean of binary outcomes.
    variance : float
        Global empirical variance.
    match_rate : float
        Global fraction of matching elements.
    mismatch_rate : float
        Global fraction of mismatching elements.
    avg_p_plus_expected : float
        Mean of per-element P(+1) projective values.
    basis_fingerprints : dict[str, BasisFingerprint]
        Per-basis statistics.
    """

    session_id: str
    total: int
    p_plus: float
    p_minus: float
    mean: float
    variance: float
    match_rate: float
    mismatch_rate: float
    avg_p_plus_expected: float
    basis_fingerprints: Dict[str, BasisFingerprint] = field(default_factory=dict)

    def as_vector(self) -> np.ndarray:
        """Return a flat feature vector for distance computation.

        Vector layout (8 elements):
            [p_plus, mean, variance, mismatch_rate,
             x_mismatch, y_mismatch, z_mismatch, avg_p_plus_expected]

        All values are already in [0, 1] or [-1, 1], so no scaling needed.
        """
        x_mm = self.basis_fingerprints.get("x", BasisFingerprint("x",0,0.5,0.0,0.0)).mismatch_rate
        y_mm = self.basis_fingerprints.get("y", BasisFingerprint("y",0,0.5,0.0,0.0)).mismatch_rate
        z_mm = self.basis_fingerprints.get("z", BasisFingerprint("z",0,0.5,0.0,0.0)).mismatch_rate
        return np.array([
            self.p_plus,
            (self.mean + 1.0) / 2.0,   # map [-1,1] -> [0,1]
            self.variance,
            self.mismatch_rate,
            x_mm,
            y_mm,
            z_mm,
            self.avg_p_plus_expected,
        ], dtype=float)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_fingerprint(
    vr,
    session_id: str = "",
) -> SessionFingerprint:
    """Build a ``SessionFingerprint`` from a ``VerificationResult``.

    Parameters
    ----------
    vr : qds.verification.VerificationResult
        Output of ``qds.verification.verify_signature``.
    session_id : str
        Optional label; defaults to the signature_id from *vr*.

    Returns
    -------
    SessionFingerprint
    """
    sid = session_id or getattr(vr, "signature_id", "unknown")
    stats: MeasurementStats = stats_from_verification(vr)

    basis_fps: Dict[str, BasisFingerprint] = {
        basis: BasisFingerprint(
            basis=basis,
            count=bs.count,
            p_plus=bs.p_plus,
            mean=bs.mean,
            mismatch_rate=bs.mismatch_rate,
        )
        for basis, bs in stats.basis_stats.items()
    }

    fp = SessionFingerprint(
        session_id=sid,
        total=stats.total,
        p_plus=stats.p_plus,
        p_minus=stats.p_minus,
        mean=stats.mean,
        variance=stats.variance,
        match_rate=stats.match_rate,
        mismatch_rate=stats.mismatch_rate,
        avg_p_plus_expected=stats.avg_p_plus_expected,
        basis_fingerprints=basis_fps,
    )
    logger.debug(
        "Built fingerprint %s: n=%d mismatch=%.4f mean=%.4f",
        sid[:8], fp.total, fp.mismatch_rate, fp.mean,
    )
    return fp


def build_baseline_fingerprint(
    fingerprints: List[SessionFingerprint],
) -> SessionFingerprint:
    """Aggregate multiple session fingerprints into a single baseline.

    Takes the element-wise mean across all fields.  The resulting baseline
    fingerprint represents the expected behaviour of a legitimate session.

    Parameters
    ----------
    fingerprints : list[SessionFingerprint]
        Collection of fingerprints from legitimate sessions.

    Returns
    -------
    SessionFingerprint
        Aggregated baseline.

    Raises
    ------
    ValueError
        If *fingerprints* is empty.
    """
    if not fingerprints:
        raise ValueError("Cannot build baseline from empty fingerprint list.")

    def _mean_field(attr: str) -> float:
        return float(np.mean([getattr(fp, attr) for fp in fingerprints]))

    # Aggregate per-basis fields
    basis_fps: Dict[str, BasisFingerprint] = {}
    for basis in ("x", "y", "z"):
        counts = [fp.basis_fingerprints.get(basis, BasisFingerprint(basis,0,0.5,0.0,0.0)).count
                  for fp in fingerprints]
        total_count = sum(counts)
        pplus_vals = [fp.basis_fingerprints.get(basis, BasisFingerprint(basis,0,0.5,0.0,0.0)).p_plus
                      for fp in fingerprints if fp.basis_fingerprints.get(basis, BasisFingerprint(basis,0,0.5,0.0,0.0)).count > 0]
        mean_vals  = [fp.basis_fingerprints.get(basis, BasisFingerprint(basis,0,0.5,0.0,0.0)).mean
                      for fp in fingerprints if fp.basis_fingerprints.get(basis, BasisFingerprint(basis,0,0.5,0.0,0.0)).count > 0]
        mm_vals    = [fp.basis_fingerprints.get(basis, BasisFingerprint(basis,0,0.5,0.0,0.0)).mismatch_rate
                      for fp in fingerprints if fp.basis_fingerprints.get(basis, BasisFingerprint(basis,0,0.5,0.0,0.0)).count > 0]
        basis_fps[basis] = BasisFingerprint(
            basis=basis,
            count=total_count,
            p_plus=float(np.mean(pplus_vals)) if pplus_vals else 0.5,
            mean=float(np.mean(mean_vals)) if mean_vals else 0.0,
            mismatch_rate=float(np.mean(mm_vals)) if mm_vals else 0.0,
        )

    return SessionFingerprint(
        session_id="__baseline__",
        total=int(np.mean([fp.total for fp in fingerprints])),
        p_plus=_mean_field("p_plus"),
        p_minus=_mean_field("p_minus"),
        mean=_mean_field("mean"),
        variance=_mean_field("variance"),
        match_rate=_mean_field("match_rate"),
        mismatch_rate=_mean_field("mismatch_rate"),
        avg_p_plus_expected=_mean_field("avg_p_plus_expected"),
        basis_fingerprints=basis_fps,
    )
