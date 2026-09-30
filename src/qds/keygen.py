"""
qds/keygen.py
=============
Quantum Digital Signature -- key generation.

Phase 3 -- SIH26141 | Blockchain & Cybersecurity.

Generates a real ``PrivateKey`` / ``PublicKey`` pair for the QDS scheme.

Security model
--------------
The private key is a cryptographically random 32-byte seed produced by
``secrets.token_bytes`` -- it is **never** derived from the public
``random_seed`` in ``config/quantum_config.yaml``.  From that seed the
signer deterministically derives a *key table* of Pauli eigenstates::

    key_table[i] = LABELS[ HMAC-SHA256(priv_seed, "QDS-KEYTABLE" || i) mod 6 ]

Because HMAC-SHA256 is a pseudo-random function, an adversary who does not
hold ``priv_seed`` cannot predict any entry of the table better than
guessing uniformly (1/6 per position).

The **public key** is the verifier's copy of that same table, delivered as
*quantum states* by teleportation (see :mod:`qds.key_distribution`).  This
mirrors Gottesman-Chuang QDS: the public key is quantum, so no-cloning
prevents a third party from reading it off the wire and reconstructing the
table.  Only the ``fingerprint`` -- a SHA-256 commitment -- is broadcast in
the clear; it binds the key to a signer identity without revealing any
eigenstate.

Accordingly, :class:`PublicKey` stores its eigenstate labels in a private
attribute reachable only through :meth:`PublicKey.state_at`, and attack
models are never handed that object (see ``attacks/forgery.py``).

No AI/ML libraries are used.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from functools import lru_cache
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from qds.pauli_states import EIGENSTATE_LABELS, PauliEigenstate, get_eigenstate
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "PrivateKey",
    "PublicKey",
    "DEFAULT_KEY_TABLE_SIZE",
    "PRIVATE_SEED_BYTES",
    "generate_key_pair",
    "derive_key_table",
    "derive_signature_indices",
    "message_digest",
]

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

#: Number of eigenstates in a signer's key table.
#:
#: 1024, not 64. Signature positions recur across messages, so each
#: recurrence leaks a table entry; at T=64 with 16-element signatures the
#: table is 72% exposed after just 5 signatures and forgery succeeds
#: (measured: 60/60). See :mod:`qds.key_policy` for the derivation --
#: T=64 permits exactly one safe signature, T=1024 permits 27.
DEFAULT_KEY_TABLE_SIZE: int = 1024

#: Entropy of the private seed, in bytes (256 bits).
PRIVATE_SEED_BYTES: int = 32

#: Domain-separation tags, so the same seed cannot collide across purposes.
_TAG_KEY_TABLE = b"QDS-KEYTABLE"
_TAG_FINGERPRINT = b"QDS-FINGERPRINT"
_TAG_INDEX = b"QDS-SIGINDEX"
_TAG_SIGN = b"QDS-SIGN"


# ---------------------------------------------------------------------------
# Key material
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PrivateKey:
    """Signer-held secret key material.

    Attributes
    ----------
    seed : bytes
        The secret 32-byte seed.  Never logged, never serialised, and
        redacted from ``repr`` so it cannot leak into experiment output.
    key_id : str
        Public, non-secret identifier for this key pair.
    signer_id : str
        Identity of the signer that owns this key.
    table_size : int
        Number of eigenstates in the derived key table.
    """

    seed: bytes
    key_id: str
    signer_id: str
    table_size: int = DEFAULT_KEY_TABLE_SIZE

    def key_table(self) -> Tuple[str, ...]:
        """Derive and return the full eigenstate-label key table."""
        return derive_key_table(self.seed, self.table_size)

    def fingerprint(self) -> str:
        """Return the public SHA-256 commitment to this key."""
        return hashlib.sha256(_TAG_FINGERPRINT + self.seed).hexdigest()

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"PrivateKey(key_id={self.key_id!r}, signer_id={self.signer_id!r}, "
            f"table_size={self.table_size}, seed=<redacted {len(self.seed)}B>)"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class PublicKey:
    """Verifier-held public key.

    The eigenstate labels are the verifier's copy of the signer's key
    table, obtained by quantum teleportation.  Physically these are
    *quantum states* held in the verifier's lab: no-cloning means a third
    party cannot obtain them, so they are deliberately not exposed as a
    plain public attribute.  Only :attr:`fingerprint` is broadcast.

    Attributes
    ----------
    key_id : str
        Public identifier, matching the signer's :class:`PrivateKey`.
    signer_id : str
        Identity this key is bound to.
    fingerprint : str
        SHA-256 commitment -- the only classically-public component.
    table_size : int
        Number of eigenstates in the key table.
    distribution_fidelity : float
        Mean teleportation fidelity achieved while distributing the key.
        ``1.0`` when the key was distributed over a noiseless channel.
    """

    key_id: str
    signer_id: str
    fingerprint: str
    table_size: int = DEFAULT_KEY_TABLE_SIZE
    distribution_fidelity: float = 1.0
    _labels: Tuple[str, ...] = field(default=(), repr=False)

    def state_at(self, index: int) -> PauliEigenstate:
        """Return the verifier's eigenstate for key-table *index*.

        Raises
        ------
        IndexError
            If *index* falls outside the key table.
        """
        if not (0 <= index < len(self._labels)):
            raise IndexError(
                f"Key-table index {index} out of range [0, {len(self._labels)})."
            )
        return get_eigenstate(self._labels[index])

    def label_at(self, index: int) -> str:
        """Return the eigenstate label at key-table *index*."""
        if not (0 <= index < len(self._labels)):
            raise IndexError(
                f"Key-table index {index} out of range [0, {len(self._labels)})."
            )
        return self._labels[index]

    def matches(self, private_key: PrivateKey) -> bool:
        """Return ``True`` when this public key corresponds to *private_key*."""
        return hmac.compare_digest(self.fingerprint, private_key.fingerprint())

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"PublicKey(key_id={self.key_id!r}, signer_id={self.signer_id!r}, "
            f"fingerprint={self.fingerprint[:16]}..., "
            f"table_size={self.table_size}, "
            f"distribution_fidelity={self.distribution_fidelity:.4f})"
        )


# ---------------------------------------------------------------------------
# Derivation primitives
# ---------------------------------------------------------------------------

def _prf(key: bytes, *parts: bytes) -> bytes:
    """HMAC-SHA256 pseudo-random function over domain-separated *parts*."""
    msg = b"|".join(parts)
    return hmac.new(key, msg, hashlib.sha256).digest()


def message_digest(message: bytes | str) -> bytes:
    """Return the SHA-256 digest of *message*.

    Parameters
    ----------
    message : bytes or str
        Message content.  ``str`` inputs are encoded as UTF-8.

    Returns
    -------
    bytes
        32-byte digest binding the signature to the exact message content.
    """
    if isinstance(message, str):
        message = message.encode("utf-8")
    if not isinstance(message, (bytes, bytearray)):
        raise TypeError(f"message must be bytes or str, got {type(message).__name__}.")
    return hashlib.sha256(bytes(message)).digest()


@lru_cache(maxsize=64)
def _derive_key_table_cached(
    private_seed: bytes,
    table_size: int,
) -> Tuple[str, ...]:
    """Memoised table derivation.

    The table is a pure function of (seed, size), and a 1024-entry table
    costs 1024 HMAC evaluations -- paid on *every* signature without this
    cache, which measured as a 9x end-to-end slowdown. Nothing new is
    exposed: the cache holds material already derivable from the in-memory
    seed, and it is bounded so a long-running process cannot accumulate
    tables for unboundedly many keys.
    """
    n_labels = len(EIGENSTATE_LABELS)
    labels: List[str] = []
    for i in range(table_size):
        digest = _prf(private_seed, _TAG_KEY_TABLE, i.to_bytes(4, "big"))
        labels.append(EIGENSTATE_LABELS[int.from_bytes(digest[:8], "big") % n_labels])
    return tuple(labels)


def derive_key_table(
    private_seed: bytes,
    table_size: int = DEFAULT_KEY_TABLE_SIZE,
) -> Tuple[str, ...]:
    """Derive the signer's eigenstate key table from the private seed.

    ``key_table[i] = LABELS[ HMAC(seed, "QDS-KEYTABLE" || i) mod 6 ]``

    Parameters
    ----------
    private_seed : bytes
        The signer's secret seed.
    table_size : int
        Number of entries to derive.

    Returns
    -------
    tuple[str, ...]
        Eigenstate labels, one per table position.

    Raises
    ------
    ValueError
        If *table_size* < 1.
    """
    if table_size < 1:
        raise ValueError(f"table_size must be >= 1, got {table_size}.")

    return _derive_key_table_cached(bytes(private_seed), int(table_size))


def derive_signature_indices(
    msg_digest: bytes,
    length: int,
    table_size: int = DEFAULT_KEY_TABLE_SIZE,
) -> Tuple[int, ...]:
    """Derive which key-table positions a message's signature uses.

    This derivation is **public** -- it depends only on the message digest,
    so the verifier reproduces it without any secret.  Unforgeability comes
    from the table *contents* (secret), not from the choice of indices.

    Parameters
    ----------
    msg_digest : bytes
        SHA-256 digest of the message, from :func:`message_digest`.
    length : int
        Number of signature elements to select.
    table_size : int
        Size of the signer's key table.

    Returns
    -------
    tuple[int, ...]
        One key-table index per signature position.
    """
    if length < 1:
        raise ValueError(f"length must be >= 1, got {length}.")

    indices: List[int] = []
    for k in range(length):
        digest = hashlib.sha256(
            _TAG_INDEX + b"|" + msg_digest + b"|" + k.to_bytes(4, "big")
        ).digest()
        indices.append(int.from_bytes(digest[:8], "big") % table_size)
    return tuple(indices)


def derive_signature_labels(
    private_key: PrivateKey,
    msg_digest: bytes,
    length: int,
) -> Tuple[Tuple[int, ...], Tuple[str, ...]]:
    """Derive the eigenstate sequence a signer emits for a message.

    Mixes the message hash with the private key exactly as the security
    model requires: the positions come from the message digest, the states
    at those positions come from the HMAC-derived secret key table.  A
    different message, or a different signer, therefore yields a different
    and (without the seed) unpredictable sequence.

    Returns
    -------
    tuple
        ``(indices, labels)`` -- the key-table positions used and the
        eigenstate label emitted at each signature position.
    """
    table = private_key.key_table()
    indices = derive_signature_indices(msg_digest, length, private_key.table_size)
    labels = tuple(table[i] for i in indices)
    return indices, labels


# ---------------------------------------------------------------------------
# Key pair generation
# ---------------------------------------------------------------------------

def generate_key_pair(
    signer_id: str = "signer_alice",
    table_size: int = DEFAULT_KEY_TABLE_SIZE,
    private_seed: Optional[bytes] = None,
    distribute: bool = False,
    noise_type: Optional[str] = None,
    noise_level: float = 0.0,
    shots: int = 1024,
) -> Tuple[PrivateKey, PublicKey]:
    """Generate a QDS private/public key pair.

    The private seed is drawn from the OS CSPRNG via
    ``secrets.token_bytes``.  Passing *private_seed* explicitly is
    supported **only** so tests and experiments can pin a key; production
    callers should leave it ``None``.

    Parameters
    ----------
    signer_id : str
        Identity to bind the key pair to.
    table_size : int
        Number of eigenstates in the key table.
    private_seed : bytes or None
        Fixed seed for reproducible runs.  ``None`` (default) draws fresh
        cryptographic randomness.
    distribute : bool
        When ``True``, the public key is delivered to the verifier by
        quantum teleportation (:mod:`qds.key_distribution`) and the
        measured channel fidelity is recorded on the public key.  When
        ``False`` (default) the verifier's copy is taken directly, which
        is faster and equivalent to a noiseless channel.
    noise_type : str or None
        Channel noise model to apply during distribution.
    noise_level : float
        Channel noise probability in [0, 1].
    shots : int
        Shots per teleported eigenstate during distribution.

    Returns
    -------
    tuple[PrivateKey, PublicKey]

    Raises
    ------
    ValueError
        If *table_size* < 1 or *private_seed* has too little entropy.
    """
    if table_size < 1:
        raise ValueError(f"table_size must be >= 1, got {table_size}.")

    if private_seed is None:
        private_seed = secrets.token_bytes(PRIVATE_SEED_BYTES)
    else:
        private_seed = bytes(private_seed)
        if len(private_seed) < 16:
            raise ValueError(
                f"private_seed must be at least 16 bytes, got {len(private_seed)}."
            )

    key_id = str(uuid.uuid4())
    priv = PrivateKey(
        seed=private_seed,
        key_id=key_id,
        signer_id=signer_id,
        table_size=table_size,
    )

    if distribute:
        # Imported lazily: key_distribution imports quantum/, which pulls in
        # Aer and is comparatively expensive.
        from qds.key_distribution import distribute_public_key

        pub = distribute_public_key(
            priv,
            noise_type=noise_type,
            noise_level=noise_level,
            shots=shots,
        )
    else:
        pub = PublicKey(
            key_id=key_id,
            signer_id=signer_id,
            fingerprint=priv.fingerprint(),
            table_size=table_size,
            distribution_fidelity=1.0,
            _labels=priv.key_table(),
        )

    logger.info(
        "Generated QDS key pair: key_id=%s... signer=%r table_size=%d "
        "distributed=%s fidelity=%.4f",
        key_id[:8], signer_id, table_size, distribute, pub.distribution_fidelity,
    )
    return priv, pub
