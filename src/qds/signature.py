"""
qds/signature.py
================
Quantum Digital Signature -- generation module.

Phase 3 -- SIH26141 | Blockchain & Cybersecurity.

A QDS signature is a fixed-length sequence of Pauli eigenstates chosen
by the signer using a seeded RNG.  Each element stores the full
``PauliEigenstate`` descriptor so the verifier can apply the correct
projective measurement without any classical side-channel.

Design
------
- ``SignatureElement``  : one (eigenstate, position) pair.
- ``QDSSignature``      : the complete signed artefact (header + elements).
- ``generate_signature``: produces a deterministic signature from a seed.

Two generation paths exist:

- :func:`generate_signature` -- legacy, seed-derived.  The seed is a
  *public* config value, so this path is reproducible by anyone and
  provides **no unforgeability**.  It is retained only to generate
  neutral baseline traffic for detector calibration.
- :func:`qds.signer.sign_message` -- key-derived.  The eigenstate sequence
  is a function of both the signer's secret key and a SHA-256 digest of
  the message content, and is the path used for all security claims.

No AI/ML is used.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from qds.pauli_states import (
    EIGENSTATE_LABELS,
    PauliEigenstate,
    get_eigenstate,
    validate_statevector_norm,
)
from utils.config import ConfigLoader
from utils.logger import get_logger
from utils.reproducibility import get_rng

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "SignatureElement",
    "QDSSignature",
    "DEFAULT_SIGNATURE_LENGTH",
    "generate_signature",
    "signature_summary",
]

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SIGNATURE_LENGTH: int = 16

# One label per position, drawn uniformly from the six eigenstates.
_LABEL_POOL: Tuple[str, ...] = EIGENSTATE_LABELS


# ---------------------------------------------------------------------------
# SignatureElement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignatureElement:
    """A single element of a QDS signature sequence.

    Attributes
    ----------
    position : int
        Zero-based index in the signature sequence.
    eigenstate : PauliEigenstate
        The Pauli eigenstate encoding the key material at this position.
    """

    position: int
    eigenstate: PauliEigenstate

    @property
    def label(self) -> str:
        """Eigenstate label string (e.g. ``'|+>'``)."""
        return self.eigenstate.label

    @property
    def basis(self) -> str:
        """Measurement basis (``'x'``, ``'y'``, or ``'z'``)."""
        return self.eigenstate.basis

    @property
    def eigenvalue(self) -> int:
        """Pauli eigenvalue (+1 or -1)."""
        return self.eigenstate.eigenvalue

    @property
    def statevector(self) -> np.ndarray:
        """Statevector of the eigenstate."""
        return self.eigenstate.statevector

    def __repr__(self) -> str:
        return (
            f"SignatureElement(pos={self.position}, "
            f"label={self.label!r}, basis={self.basis!r})"
        )


# ---------------------------------------------------------------------------
# QDSSignature
# ---------------------------------------------------------------------------

@dataclass
class QDSSignature:
    """A complete Quantum Digital Signature artefact.

    Attributes
    ----------
    signature_id : str
        Unique identifier (UUID4 string) assigned at generation time.
    message_id : str
        Caller-supplied identifier for the message being signed.
    length : int
        Number of signature elements.
    seed : int
        RNG seed used during generation (for auditability).  ``-1`` for
        key-derived signatures, which use no public seed.
    elements : list[SignatureElement]
        Ordered sequence of Pauli eigenstate elements.
    message_hash : str
        Hex SHA-256 digest of the signed message content.  Empty for
        legacy seed-derived signatures.
    key_id : str
        Identifier of the signing key pair.  Empty for legacy signatures.
    signer_id : str
        Identity of the signer.
    key_indices : tuple[int, ...]
        Key-table position used at each signature index.  Public: the
        verifier recomputes these from the message digest.
    """

    signature_id: str
    message_id: str
    length: int
    seed: int
    elements: List[SignatureElement] = field(default_factory=list)
    message_hash: str = ""
    key_id: str = ""
    signer_id: str = ""
    key_indices: Tuple[int, ...] = ()

    @property
    def is_key_derived(self) -> bool:
        """``True`` when this signature was produced from a real private key.

        Legacy seed-derived signatures (``generate_signature``) carry no
        key material and offer no unforgeability; key-derived signatures
        (``qds.signer.sign_message``) do.
        """
        return bool(self.key_id)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def get_element(self, position: int) -> SignatureElement:
        """Return the element at the given position.

        Parameters
        ----------
        position : int
            Index in [0, length).

        Raises
        ------
        IndexError
            If *position* is out of range.
        """
        if not (0 <= position < self.length):
            raise IndexError(
                f"Position {position} out of range [0, {self.length})."
            )
        return self.elements[position]

    def basis_sequence(self) -> List[str]:
        """Return the basis label at each position."""
        return [e.basis for e in self.elements]

    def eigenvalue_sequence(self) -> List[int]:
        """Return the eigenvalue at each position."""
        return [e.eigenvalue for e in self.elements]

    def label_sequence(self) -> List[str]:
        """Return the eigenstate label at each position."""
        return [e.label for e in self.elements]

    def statevectors(self) -> List[np.ndarray]:
        """Return all statevectors in order."""
        return [e.statevector for e in self.elements]

    def validate(self, atol: float = 1e-9) -> bool:
        """Validate all elements have normalised statevectors.

        Returns
        -------
        bool
            ``True`` when all elements pass the norm check.
        """
        return all(
            validate_statevector_norm(e.statevector, atol=atol)
            for e in self.elements
        )

    def __repr__(self) -> str:
        return (
            f"QDSSignature(id={self.signature_id[:8]}..., "
            f"msg={self.message_id!r}, len={self.length}, seed={self.seed})"
        )


# ---------------------------------------------------------------------------
# Signature generation
# ---------------------------------------------------------------------------

def generate_signature(
    message_id: str,
    length: int = DEFAULT_SIGNATURE_LENGTH,
    seed: Optional[int] = None,
    label_pool: Sequence[str] = _LABEL_POOL,
) -> QDSSignature:
    """Generate a deterministic QDS signature for a message.

    Uses a seeded NumPy ``Generator`` to draw uniformly from *label_pool*
    at each position, producing a reproducible sequence when the same
    *seed* is used.

    Parameters
    ----------
    message_id : str
        Identifier for the message being signed (e.g. ``'tx_001'``).
    length : int
        Number of Pauli eigenstate elements in the signature.
        Defaults to ``DEFAULT_SIGNATURE_LENGTH`` (16).
    seed : int or None
        RNG seed.  Defaults to ``ConfigLoader().random_seed`` (42).
    label_pool : sequence of str
        Set of eigenstate labels to draw from.  Defaults to all six
        Pauli eigenstates.

    Returns
    -------
    QDSSignature
        Fully populated signature with a unique ``signature_id``.

    Raises
    ------
    ValueError
        If *length* < 1 or *label_pool* is empty.
    """
    if length < 1:
        raise ValueError(f"Signature length must be >= 1, got {length}.")
    if not label_pool:
        raise ValueError("label_pool must not be empty.")

    if seed is None:
        cfg = ConfigLoader()
        seed = cfg.random_seed

    logger.debug(
        "generate_signature() is the legacy seed-derived path and provides "
        "NO unforgeability (the seed is public). Use qds.signer.sign_message "
        "with a PrivateKey for security-relevant signatures."
    )

    rng = get_rng(seed)
    pool = list(label_pool)

    # Draw *length* labels uniformly
    indices = rng.integers(0, len(pool), size=length)
    chosen_labels = [pool[int(i)] for i in indices]

    elements = [
        SignatureElement(
            position=pos,
            eigenstate=get_eigenstate(lbl),
        )
        for pos, lbl in enumerate(chosen_labels)
    ]

    sig = QDSSignature(
        signature_id=str(uuid.uuid4()),
        message_id=message_id,
        length=length,
        seed=seed,
        elements=elements,
    )
    logger.info(
        "Generated QDS signature: id=%s... msg=%r len=%d seed=%d",
        sig.signature_id[:8], message_id, length, seed,
    )
    return sig


# ---------------------------------------------------------------------------
# Summary helper (for experiment scripts)
# ---------------------------------------------------------------------------

def signature_summary(sig: QDSSignature) -> str:
    """Return a compact multi-line summary of a ``QDSSignature``.

    Parameters
    ----------
    sig : QDSSignature

    Returns
    -------
    str
        Human-readable summary text.
    """
    from collections import Counter
    basis_counts  = Counter(sig.basis_sequence())
    label_counts  = Counter(sig.label_sequence())
    lines = [
        f"  Signature ID  : {sig.signature_id}",
        f"  Message ID    : {sig.message_id!r}",
        f"  Length        : {sig.length}",
        f"  Seed          : {sig.seed}",
        f"  Basis counts  : {dict(basis_counts)}",
        f"  State counts  : {dict(label_counts)}",
        f"  Label sequence: {' '.join(sig.label_sequence())}",
    ]
    return "\n".join(lines)
