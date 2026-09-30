"""
qds/scheme.py
=============
Quantum Digital Signature -- high-level scheme orchestration.

Phase 3 -- SIH26141 | Blockchain & Cybersecurity.

``QDSScheme`` ties the full lifecycle together::

    keygen  ->  quantum key distribution  ->  sign  ->  verify
    (secret     (Bell pair + teleportation    (HMAC-     (measure against
     seed)       + Pauli correction)           derived)   the public key)

Typical use::

    scheme = QDSScheme(signature_length=16, distribute=True)
    scheme.generate_keys(signer_id="alice")
    sig = scheme.sign(b"transfer 100 to bob")
    res = scheme.verify(sig, b"transfer 100 to bob")
    assert res.accepted

No AI/ML libraries are used.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from qds.keygen import (
    DEFAULT_KEY_TABLE_SIZE,
    PrivateKey,
    PublicKey,
    generate_key_pair,
)
from qds.signature import DEFAULT_SIGNATURE_LENGTH, QDSSignature
from qds.signer import sign_message
from qds.verification import DEFAULT_ACCEPT_THRESHOLD, VerificationResult
from qds.verifier import verify_signature as verify_against_key
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = ["QDSScheme"]


class QDSScheme:
    """End-to-end orchestrator for the Quantum Digital Signature scheme.

    Parameters
    ----------
    signature_length : int
        Number of Pauli eigenstate elements per signature.
    table_size : int
        Size of the signer's secret key table.
    distribute : bool
        When ``True``, the public key is delivered to the verifier by
        quantum teleportation over a simulated channel.  When ``False``
        the verifier's copy is taken directly (equivalent to a perfect
        channel) -- much faster for bulk experiments.
    noise_type : str or None
        Channel noise model used during key distribution.
    noise_level : float
        Channel noise probability in [0, 1].
    shots : int
        Aer shots per teleported eigenstate.
    threshold : float
        Verification acceptance threshold.
    max_distributed_states : int or None
        Cap on how many key-table entries are physically teleported.
    """

    def __init__(
        self,
        signature_length: int = DEFAULT_SIGNATURE_LENGTH,
        table_size: int = DEFAULT_KEY_TABLE_SIZE,
        distribute: bool = False,
        noise_type: Optional[str] = None,
        noise_level: float = 0.0,
        shots: int = 1024,
        threshold: float = DEFAULT_ACCEPT_THRESHOLD,
        max_distributed_states: Optional[int] = None,
    ) -> None:
        if signature_length < 1:
            raise ValueError(
                f"signature_length must be >= 1, got {signature_length}."
            )
        self.signature_length = signature_length
        self.table_size = table_size
        self.distribute = distribute
        self.noise_type = noise_type
        self.noise_level = noise_level
        self.shots = shots
        self.threshold = threshold
        self.max_distributed_states = max_distributed_states

        self._private_key: Optional[PrivateKey] = None
        self._public_key: Optional[PublicKey] = None

    # ------------------------------------------------------------------
    # Key material
    # ------------------------------------------------------------------

    @property
    def private_key(self) -> PrivateKey:
        """The signer's private key.

        Raises
        ------
        RuntimeError
            If :meth:`generate_keys` has not been called.
        """
        if self._private_key is None:
            raise RuntimeError("No keys yet — call generate_keys() first.")
        return self._private_key

    @property
    def public_key(self) -> PublicKey:
        """The verifier's public key.

        Raises
        ------
        RuntimeError
            If :meth:`generate_keys` has not been called.
        """
        if self._public_key is None:
            raise RuntimeError("No keys yet — call generate_keys() first.")
        return self._public_key

    @property
    def has_keys(self) -> bool:
        """``True`` once a key pair has been generated."""
        return self._private_key is not None and self._public_key is not None

    def generate_keys(
        self,
        signer_id: str = "signer_alice",
        private_seed: Optional[bytes] = None,
    ) -> tuple[PrivateKey, PublicKey]:
        """Generate a key pair and distribute the public key.

        Parameters
        ----------
        signer_id : str
            Identity to bind the keys to.
        private_seed : bytes or None
            Pin the private seed for reproducible experiments.  ``None``
            (default) draws fresh cryptographic randomness.

        Returns
        -------
        tuple[PrivateKey, PublicKey]
        """
        priv, pub = generate_key_pair(
            signer_id=signer_id,
            table_size=self.table_size,
            private_seed=private_seed,
            distribute=self.distribute,
            noise_type=self.noise_type,
            noise_level=self.noise_level,
            shots=self.shots,
        )
        self._private_key, self._public_key = priv, pub
        logger.info(
            "QDSScheme keys ready: signer=%r distributed=%s fidelity=%.4f",
            signer_id, self.distribute, pub.distribution_fidelity,
        )
        return priv, pub

    # ------------------------------------------------------------------
    # Sign / verify
    # ------------------------------------------------------------------

    def sign(
        self,
        message: bytes | str,
        message_id: Optional[str] = None,
    ) -> QDSSignature:
        """Sign *message* with the scheme's private key.

        Generates a key pair automatically if none exists yet.
        """
        if self._private_key is None:
            self.generate_keys()
        return sign_message(
            message,
            self.private_key,
            length=self.signature_length,
            message_id=message_id,
        )

    def verify(
        self,
        signature: QDSSignature,
        message: bytes | str,
        received_statevectors: Optional[Sequence[np.ndarray]] = None,
        public_key: Optional[PublicKey] = None,
        **kwargs,
    ) -> VerificationResult:
        """Verify *signature* over *message* against the public key.

        Parameters
        ----------
        signature : QDSSignature
            Signature to check.
        message : bytes or str
            Message the signature is claimed to cover.
        received_statevectors : sequence of np.ndarray or None
            States as they arrived over the channel.  ``None`` means an
            undisturbed transmission.
        public_key : PublicKey or None
            Override the verifier's key -- used to model a verifier that
            holds a *different* signer's key (impersonation).
        **kwargs
            Forwarded to :func:`qds.verifier.verify_signature` (e.g.
            ``copies_per_element``, ``decision_margin``, ``rng``).

        Returns
        -------
        VerificationResult
        """
        return verify_against_key(
            signature,
            public_key if public_key is not None else self.public_key,
            message,
            received_statevectors=received_statevectors,
            threshold=self.threshold,
            **kwargs,
        )

    def sign_and_verify(
        self,
        message: bytes | str,
    ) -> tuple[QDSSignature, VerificationResult]:
        """Convenience round-trip: sign *message*, then verify it."""
        sig = self.sign(message)
        return sig, self.verify(sig, message)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        state = "keyed" if self.has_keys else "unkeyed"
        return (
            f"QDSScheme(length={self.signature_length}, "
            f"table_size={self.table_size}, distribute={self.distribute}, "
            f"noise={self.noise_type}@{self.noise_level:.3f}, {state})"
        )
