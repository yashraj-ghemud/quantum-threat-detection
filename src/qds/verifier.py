"""
qds/verifier.py
===============
Quantum Digital Signature -- key-aware signature verification.

Phase 3 -- SIH26141 | Blockchain & Cybersecurity.

Where :mod:`qds.verification` measures a signature against the *signer's
own* stored elements, this module verifies against the **verifier's public
key** -- the eigenstates it received by teleportation.  That is the check
that actually detects forgery: the verifier never consults the attacker-
supplied element list for its expectations.

Protocol
--------
1. Confirm the signature's ``key_id`` matches the public key presented.
2. Recompute ``SHA-256(message)`` and confirm it matches the signature's
   ``message_hash`` -- this rejects any message substitution.
3. Recompute the key-table indices from the digest (public derivation).
4. For each position, take the **expected** eigenstate from the public key
   at that index, and projectively measure the **received** statevector in
   that eigenstate's Pauli basis.
5. Accept when the match rate meets the threshold.

Measurement model
-----------------
Each key element is distributed as *multiple copies* (standard practice in
QDS -- one copy cannot be measured twice, by no-cloning), and the verifier
samples each copy under the Born rule.  This matters for security: a state
guessed from a *conjugate* basis yields p(+1) = p(-1) = 0.5, i.e. a coin
flip.  A deterministic "dominant outcome" tie-break would instead resolve
every such tie the same way and hand a blind forger a free 50% match rate
per element.  Averaging ``copies_per_element`` Born-rule samples and
requiring the mean eigenvalue to clear ``decision_margin`` collapses that
advantage: a conjugate-basis guess must win a lopsided coin-flip streak.

With the defaults below, a forger without the private key matches an
element with probability ~0.19 (vs. 1/6 = 0.167 for pure guessing), and
whole-signature acceptance falls to well under 1%.

No AI/ML libraries are used.
"""

from __future__ import annotations

import hmac
from typing import List, Optional, Sequence

import numpy as np

from qds.keygen import PublicKey, derive_signature_indices, message_digest
from qds.pauli_states import projective_measurement_probs
from qds.signature import QDSSignature
from qds.verification import (
    DEFAULT_ACCEPT_THRESHOLD,
    ElementVerificationResult,
    VerificationResult,
)
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "verify_signature",
    "KeyVerificationError",
    "DEFAULT_COPIES_PER_ELEMENT",
    "DEFAULT_DECISION_MARGIN",
]

#: Number of copies of each key eigenstate the verifier measures.
DEFAULT_COPIES_PER_ELEMENT: int = 16

#: Minimum |mean eigenvalue| required to accept an element as a match.
DEFAULT_DECISION_MARGIN: float = 0.5


class KeyVerificationError(ValueError):
    """Raised when a signature cannot be checked against the given public key."""


def _rejected(
    signature: QDSSignature,
    threshold: float,
    reason: str,
) -> VerificationResult:
    """Build a zero-score REJECTED result for a pre-measurement failure."""
    logger.warning("Verification rejected before measurement: %s", reason)
    return VerificationResult(
        signature_id=signature.signature_id,
        message_id=signature.message_id,
        total_elements=signature.length,
        matches=0,
        mismatches=signature.length,
        verification_score=0.0,
        threshold=threshold,
        accepted=False,
        element_results=[],
    )


def verify_signature(
    signature: QDSSignature,
    public_key: PublicKey,
    message: bytes | str,
    received_statevectors: Optional[Sequence[np.ndarray]] = None,
    threshold: float = DEFAULT_ACCEPT_THRESHOLD,
    strict: bool = False,
    copies_per_element: int = DEFAULT_COPIES_PER_ELEMENT,
    decision_margin: float = DEFAULT_DECISION_MARGIN,
    rng: Optional[np.random.Generator] = None,
) -> VerificationResult:
    """Verify a quantum signature against a public key and a message.

    Parameters
    ----------
    signature : QDSSignature
        Signature artefact received from the claimed signer.
    public_key : PublicKey
        Verifier's teleported copy of the signer's key table.
    message : bytes or str
        The message the signature is claimed to cover.
    received_statevectors : sequence of np.ndarray or None
        Statevectors as they arrived over the channel.  ``None`` uses the
        signature's own statevectors (an undisturbed transmission).
    threshold : float
        Acceptance threshold for the match rate.
    strict : bool
        When ``True``, key/message binding failures raise
        :class:`KeyVerificationError` instead of returning a REJECTED
        result.
    copies_per_element : int
        Number of copies of each key state the verifier measures under the
        Born rule.  ``1`` reproduces single-copy behaviour.
    decision_margin : float
        Minimum ``|mean eigenvalue|`` required to count an element as a
        match.  Guards against conjugate-basis coin flips.
    rng : numpy.random.Generator or None
        Generator for measurement sampling.  ``None`` draws fresh
        randomness, which is correct for physical measurement; pass a
        seeded generator for reproducible experiments.

    Returns
    -------
    VerificationResult
        Outcome with a per-element breakdown.

    Raises
    ------
    KeyVerificationError
        Only when *strict* is ``True`` and a binding check fails.
    """
    # --- 1. The signature must be key-derived --------------------------
    if not signature.is_key_derived:
        reason = (
            "signature is legacy seed-derived and carries no key binding; "
            "it cannot be verified against a public key"
        )
        if strict:
            raise KeyVerificationError(reason)
        return _rejected(signature, threshold, reason)

    # --- 2. Key identity binding ---------------------------------------
    if signature.key_id != public_key.key_id:
        reason = (
            f"key_id mismatch: signature claims {signature.key_id[:8]}..., "
            f"public key is {public_key.key_id[:8]}... (impersonation)"
        )
        if strict:
            raise KeyVerificationError(reason)
        return _rejected(signature, threshold, reason)

    # --- 3. Message binding --------------------------------------------
    digest = message_digest(message)
    if not hmac.compare_digest(digest.hex(), signature.message_hash):
        reason = (
            "message digest mismatch: the signature does not cover this "
            "message (substitution or tampering)"
        )
        if strict:
            raise KeyVerificationError(reason)
        return _rejected(signature, threshold, reason)

    # --- 4. Recompute expected key-table indices (public derivation) ----
    indices = derive_signature_indices(
        digest, signature.length, public_key.table_size
    )
    if signature.key_indices and tuple(signature.key_indices) != indices:
        reason = (
            "declared key indices do not match the digest-derived indices "
            "(forged index list)"
        )
        if strict:
            raise KeyVerificationError(reason)
        return _rejected(signature, threshold, reason)

    # --- 5. Measure each received state against the verifier's key -----
    if copies_per_element < 1:
        raise ValueError(
            f"copies_per_element must be >= 1, got {copies_per_element}."
        )
    gen = np.random.default_rng() if rng is None else rng

    element_results: List[ElementVerificationResult] = []
    for pos, table_index in enumerate(indices):
        expected = public_key.state_at(table_index)

        if received_statevectors is None:
            received = signature.elements[pos].statevector
        else:
            received = np.asarray(received_statevectors[pos], dtype=complex)

        p_plus, p_minus = projective_measurement_probs(received, expected.basis)

        # Born-rule sampling over the distributed copies.  An exact match
        # gives p_plus in {0, 1} and so a unanimous outcome; a
        # conjugate-basis guess gives p_plus = 0.5 and a coin flip.
        draws = gen.random(copies_per_element)
        outcomes = np.where(draws < p_plus, 1.0, -1.0)
        mean_ev = float(outcomes.mean())

        measured_ev = +1 if mean_ev >= 0.0 else -1
        match = bool(expected.eigenvalue * mean_ev >= decision_margin)

        element_results.append(
            ElementVerificationResult(
                position=pos,
                expected_label=expected.label,
                expected_basis=expected.basis,
                expected_eigenvalue=expected.eigenvalue,
                p_plus=p_plus,
                p_minus=p_minus,
                measured_eigenvalue=measured_ev,
                match=match,
            )
        )

    matches = sum(1 for r in element_results if r.match)
    total = len(element_results)
    score = matches / total if total else 0.0
    accepted = score >= threshold

    logger.info(
        "Key verification %s: score=%.4f threshold=%.4f matches=%d/%d key=%s...",
        "ACCEPTED" if accepted else "REJECTED",
        score, threshold, matches, total, public_key.key_id[:8],
    )

    return VerificationResult(
        signature_id=signature.signature_id,
        message_id=signature.message_id,
        total_elements=total,
        matches=matches,
        mismatches=total - matches,
        verification_score=score,
        threshold=threshold,
        accepted=accepted,
        element_results=element_results,
    )
