"""
sentinel/protocol/signing.py
============================
Lamport-style one-time signing with quantum public keys.

For each signed bit ``i`` with value ``d_i`` the signer reveals the private
labels of key ``(i, d_i)``. The labels of key ``(i, 1 - d_i)`` stay secret
forever, which is what a forger would have to guess.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from sentinel.protocol.encoding import Envelope, digest_hex, encode_bits
from sentinel.protocol.keys import KeyBundle, KeyReuseError

__all__ = ["Signature", "sign", "signature_from_labels"]


@dataclass
class Signature:
    envelope: Envelope
    bits: np.ndarray       # uint8 (B,)
    revealed: np.ndarray   # uint8 (B, L) labels of key (i, bits[i])
    oracle: bool = False   # analysis only: bits supplied by a hypothetical near-collision oracle

    @property
    def size_bytes(self) -> int:
        return int(self.revealed.size)

    def sha256(self) -> str:
        h = hashlib.sha256()
        h.update(digest_hex(self.envelope).encode())
        h.update(self.revealed.tobytes())
        return h.hexdigest()

    def copy(self) -> "Signature":
        return Signature(self.envelope, self.bits.copy(), self.revealed.copy(), self.oracle)


def sign(bundle: KeyBundle, envelope: Envelope) -> Signature:
    """Sign ``envelope`` with a one-time bundle (marks the bundle as signed)."""
    if bundle.signed:
        raise KeyReuseError(f"bundle {bundle.bundle_id} has already signed a message")
    if envelope.bundle_id != bundle.bundle_id:
        raise ValueError("envelope.bundle_id does not match the bundle")
    labels = bundle.private_labels()
    bits = encode_bits(envelope, bundle.params.digest_bits)
    revealed = labels[np.arange(bits.size), bits, :].copy()
    bundle.signed = True
    return Signature(envelope=envelope, bits=bits, revealed=revealed)


def signature_from_labels(envelope: Envelope, revealed: np.ndarray, digest_bits: int) -> Signature:
    """Assemble a signature from arbitrary declared labels (used by adversaries)."""
    bits = encode_bits(envelope, digest_bits)
    return Signature(envelope=envelope, bits=bits, revealed=np.asarray(revealed, dtype=np.uint8))
