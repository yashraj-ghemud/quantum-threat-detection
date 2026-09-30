"""
qds/verification.py
====================
Quantum Digital Signature -- verification module.

Phase 3 -- SIH26141 | Blockchain & Cybersecurity.

The verifier receives a ``QDSSignature`` (or a potentially modified copy)
and measures each element in its expected Pauli basis.  A match occurs
when the dominant measurement outcome agrees with the expected eigenvalue.

Verification pipeline
---------------------
For each element at position *i*:
    1. Retrieve the expected eigenstate (label, basis, eigenvalue).
    2. Compute projective measurement probabilities P(+1), P(-1) in the
       expected basis from the received statevector.
    3. The measured eigenvalue is the one with the higher probability.
    4. Record match (expected == measured) or mismatch.

After all elements:
    verification_score = matches / total_elements
    accept             = verification_score >= threshold

No AI/ML is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from qds.pauli_states import (
    PauliEigenstate,
    measure_eigenstate,
    projective_measurement_probs,
)
from qds.signature import QDSSignature, SignatureElement
from utils.config import ConfigLoader
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "ElementVerificationResult",
    "VerificationResult",
    "DEFAULT_ACCEPT_THRESHOLD",
    "verify_element",
    "verify_signature",
]

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_ACCEPT_THRESHOLD: float = 0.7
"""Minimum verification score to accept a signature as legitimate."""


# ---------------------------------------------------------------------------
# Per-element result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ElementVerificationResult:
    """Verification outcome for a single signature element.

    Attributes
    ----------
    position : int
        Position in the signature sequence.
    expected_label : str
        Expected eigenstate label.
    expected_basis : str
        Expected measurement basis.
    expected_eigenvalue : int
        Expected Pauli eigenvalue (+1 or -1).
    p_plus : float
        Measured P(+1) in the expected basis.
    p_minus : float
        Measured P(-1) in the expected basis.
    measured_eigenvalue : int
        Eigenvalue with higher probability: +1 or -1.
    match : bool
        True when measured_eigenvalue == expected_eigenvalue.
    """

    position: int
    expected_label: str
    expected_basis: str
    expected_eigenvalue: int
    p_plus: float
    p_minus: float
    measured_eigenvalue: int
    match: bool

    def __repr__(self) -> str:
        status = "MATCH" if self.match else "MISMATCH"
        return (
            f"ElementVerificationResult(pos={self.position}, "
            f"{self.expected_label!r} basis={self.expected_basis!r} "
            f"exp={self.expected_eigenvalue:+d} "
            f"meas={self.measured_eigenvalue:+d} [{status}])"
        )


# ---------------------------------------------------------------------------
# Full verification result
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    """Complete QDS verification outcome.

    Attributes
    ----------
    signature_id : str
        ID of the signature being verified.
    message_id : str
        Message identifier.
    total_elements : int
        Total number of elements in the signature.
    matches : int
        Number of elements where measured == expected.
    mismatches : int
        Number of elements where measured != expected.
    verification_score : float
        ``matches / total_elements``.  In [0, 1].
    threshold : float
        Accept/reject threshold used.
    accepted : bool
        ``True`` when ``verification_score >= threshold``.
    element_results : list[ElementVerificationResult]
        Per-element breakdown.
    """

    signature_id: str
    message_id: str
    total_elements: int
    matches: int
    mismatches: int
    verification_score: float
    threshold: float
    accepted: bool
    element_results: List[ElementVerificationResult] = field(default_factory=list)

    def __repr__(self) -> str:
        verdict = "ACCEPTED" if self.accepted else "REJECTED"
        return (
            f"VerificationResult(id={self.signature_id[:8]}..., "
            f"score={self.verification_score:.4f}/{self.threshold:.4f} "
            f"[{verdict}] matches={self.matches}/{self.total_elements})"
        )


# ---------------------------------------------------------------------------
# Element-level verification
# ---------------------------------------------------------------------------

def verify_element(
    element: SignatureElement,
    received_statevector=None,
) -> ElementVerificationResult:
    """Verify a single signature element.

    Measures the received (or expected, if not provided) statevector in
    the expected basis and compares the dominant eigenvalue.

    Parameters
    ----------
    element : SignatureElement
        The expected element from the original signature.
    received_statevector : array-like or None
        The statevector actually received.  When ``None``, the expected
        statevector from *element* is used (legitimate verification).

    Returns
    -------
    ElementVerificationResult
    """
    sv = (
        element.statevector
        if received_statevector is None
        else received_statevector
    )
    p_plus, p_minus = projective_measurement_probs(sv, element.basis)
    # Dominant outcome
    measured_ev = +1 if p_plus >= p_minus else -1
    match = measured_ev == element.eigenvalue

    logger.debug(
        "verify_element pos=%d %s exp=%+d meas=%+d p+=%+.4f p-=%+.4f %s",
        element.position, element.label, element.eigenvalue,
        measured_ev, p_plus, p_minus, "MATCH" if match else "MISMATCH",
    )
    return ElementVerificationResult(
        position=element.position,
        expected_label=element.label,
        expected_basis=element.basis,
        expected_eigenvalue=element.eigenvalue,
        p_plus=p_plus,
        p_minus=p_minus,
        measured_eigenvalue=measured_ev,
        match=match,
    )


# ---------------------------------------------------------------------------
# Full-signature verification
# ---------------------------------------------------------------------------

def verify_signature(
    signature: QDSSignature,
    received_statevectors=None,
    threshold: float = DEFAULT_ACCEPT_THRESHOLD,
) -> VerificationResult:
    """Verify a full QDS signature.

    For each element the verifier measures the received statevector (or
    the ideal stored statevector when *received_statevectors* is ``None``)
    in the expected Pauli basis.

    Parameters
    ----------
    signature : QDSSignature
        The reference signature produced by the signer.
    received_statevectors : list[array-like] or None
        One statevector per position.  When ``None``, uses the signer's
        own states (simulates a legitimate, unmodified transmission).
    threshold : float
        Accept/reject threshold for the verification score.
        Defaults to ``DEFAULT_ACCEPT_THRESHOLD`` (0.7).

    Returns
    -------
    VerificationResult
        Full outcome including per-element breakdown.
    """
    element_results: List[ElementVerificationResult] = []

    for i, element in enumerate(signature.elements):
        rv = None if received_statevectors is None else received_statevectors[i]
        element_results.append(verify_element(element, received_statevector=rv))

    matches    = sum(1 for r in element_results if r.match)
    mismatches = len(element_results) - matches
    total      = len(element_results)
    score      = matches / total if total > 0 else 0.0
    accepted   = score >= threshold

    result = VerificationResult(
        signature_id=signature.signature_id,
        message_id=signature.message_id,
        total_elements=total,
        matches=matches,
        mismatches=mismatches,
        verification_score=score,
        threshold=threshold,
        accepted=accepted,
        element_results=element_results,
    )
    verdict = "ACCEPTED" if accepted else "REJECTED"
    logger.info(
        "Verification %s: score=%.4f threshold=%.4f matches=%d/%d",
        verdict, score, threshold, matches, total,
    )
    return result
