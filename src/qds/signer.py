"""
qds/signer.py
=============
Quantum Digital Signature -- message signing.

Phase 3 -- SIH26141 | Blockchain & Cybersecurity.

Signs the *content* of a message, not an arbitrary identifier.  The
eigenstate sequence emitted for a message is::

    digest   = SHA-256(message)
    index_k  = SHA-256("QDS-SIGINDEX" || digest || k)  mod  table_size
    label_k  = key_table[index_k]

where ``key_table`` is derived from the signer's secret seed through
HMAC-SHA256 (:func:`qds.keygen.derive_key_table`).  The emitted sequence is
therefore a function of **both** the private key and the message hash:

- Change the message  -> the indices change -> a different sequence.
- Change the signer   -> the key table changes -> a different sequence.
- Without the seed    -> the table contents are unpredictable, so an
  adversary can do no better than guess 1-in-6 per element.

The index derivation is deliberately public so the verifier can reproduce
it with no secret; unforgeability rests on the secrecy of the table's
*contents*, in the same way Gottesman-Chuang QDS rests on the secrecy of
the signer's quantum key states.

No AI/ML libraries are used.
"""

from __future__ import annotations

import uuid
from typing import Optional

from qds.keygen import (
    PrivateKey,
    derive_signature_labels,
    message_digest,
)
from qds.pauli_states import get_eigenstate
from qds.signature import (
    DEFAULT_SIGNATURE_LENGTH,
    QDSSignature,
    SignatureElement,
)
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = ["sign_message", "usage_tracker_for"]

#: Per-configuration usage trackers, keyed by (table_size, length).
#: Signing is counted so key exhaustion is surfaced rather than silent.
_TRACKERS: dict = {}


def usage_tracker_for(table_size: int, signature_length: int):
    """Return (creating if needed) the usage tracker for this geometry."""
    from qds.key_policy import KeyUsagePolicy, KeyUsageTracker

    key = (table_size, signature_length)
    if key not in _TRACKERS:
        _TRACKERS[key] = KeyUsageTracker(
            KeyUsagePolicy(table_size=table_size, signature_length=signature_length)
        )
    return _TRACKERS[key]


def sign_message(
    message: bytes | str,
    private_key: PrivateKey,
    length: int = DEFAULT_SIGNATURE_LENGTH,
    message_id: Optional[str] = None,
) -> QDSSignature:
    """Sign a message with the signer's private key.

    Parameters
    ----------
    message : bytes or str
        The message **content** to sign.  ``str`` is encoded as UTF-8.
        The signature binds to these exact bytes: flipping a single bit
        changes the derived index sequence and invalidates the signature.
    private_key : PrivateKey
        Signer's secret key material, from
        :func:`qds.keygen.generate_key_pair`.
    length : int
        Number of Pauli eigenstate elements to emit.
    message_id : str or None
        Optional human-readable label carried in the signature header for
        logging and correlation.  It has **no** cryptographic role --
        unlike the legacy :func:`qds.signature.generate_signature`, the
        eigenstates do not depend on it.  Defaults to the digest prefix.

    Returns
    -------
    QDSSignature
        Signature whose elements, ``message_hash``, ``key_id`` and
        ``key_indices`` bind it to this message and this signer.

    Raises
    ------
    ValueError
        If *length* < 1.
    TypeError
        If *private_key* is not a :class:`~qds.keygen.PrivateKey`.
    """
    if length < 1:
        raise ValueError(f"Signature length must be >= 1, got {length}.")
    if not isinstance(private_key, PrivateKey):
        raise TypeError(
            "sign_message requires a PrivateKey; got "
            f"{type(private_key).__name__}. Generate one with "
            "qds.keygen.generate_key_pair()."
        )

    # Count this signature against the key's safe limit. Each signature
    # leaks the table entries at its indices, so a key that signs too many
    # messages becomes forgeable; the tracker warns (or raises, if the
    # policy enforces) rather than letting that happen silently.
    usage_tracker_for(private_key.table_size, length).record(private_key.key_id)

    digest = message_digest(message)
    indices, labels = derive_signature_labels(private_key, digest, length)

    elements = [
        SignatureElement(position=pos, eigenstate=get_eigenstate(lbl))
        for pos, lbl in enumerate(labels)
    ]

    digest_hex = digest.hex()
    sig = QDSSignature(
        signature_id=str(uuid.uuid4()),
        message_id=message_id if message_id is not None else f"msg_{digest_hex[:12]}",
        length=length,
        seed=-1,  # key-derived: no public seed is involved
        elements=elements,
        message_hash=digest_hex,
        key_id=private_key.key_id,
        signer_id=private_key.signer_id,
        key_indices=indices,
    )

    logger.info(
        "Signed message: sig=%s... key=%s... signer=%r len=%d digest=%s...",
        sig.signature_id[:8], private_key.key_id[:8],
        private_key.signer_id, length, digest_hex[:16],
    )
    return sig
