"""
qds/key_policy.py
=================
Signature-count limits for a finite QDS key table.

SIH26141 | Blockchain & Cybersecurity.

The problem this solves
-----------------------
A signature selects ``L`` entries from a key table of size ``T``, at
positions derived publicly from the message digest. Those positions recur
across messages, and **every recurrence leaks that table entry** to anyone
who can observe signatures. Past some number of signatures the attacker
knows enough of the table to forge.

The bound is derived, not guessed. After ``n`` signatures the expected
fraction of the table an observer has seen is::

    f(n) = 1 - (1 - 1/T)^(n*L)

An attacker who knows a fraction ``f`` replays those entries and guesses
the rest, matching each element with probability::

    match(f) = f + (1 - f) * p_guess        p_guess = 1/6

Verification accepts at ``match >= accept_threshold``, so the scheme is
broken once ``f`` reaches::

    f* = (accept_threshold - p_guess) / (1 - p_guess)

For the default ``accept_threshold = 0.7`` that is ``f* = 0.64``.

This is not hypothetical. Measured with ``T=64, L=16``: after 5 observed
signatures coverage reaches 0.716, giving a match rate of 0.764 -- above
the 0.7 threshold -- and forged signatures were accepted in 60 of 60
attempts. The formula above predicts exactly that.

:func:`max_signatures` returns the largest ``n`` keeping coverage below a
conservative safety margin (default 0.35, roughly half of ``f*``).

Consequences for defaults
-------------------------
``T = 64`` permits only **one** signature at that margin, which is why the
default table size is now 1024 (27 signatures) rather than 64. Use
:func:`recommend_table_size` to size a key for a required signature count.

No AI/ML libraries are used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "KeyUsagePolicy",
    "KeyExhaustedError",
    "KeyUsageTracker",
    "coverage_after",
    "critical_coverage",
    "max_signatures",
    "recommend_table_size",
    "DEFAULT_SAFETY_MARGIN",
    "GUESS_PROBABILITY",
]

#: Probability a blind guess matches, over the six Pauli eigenstates.
GUESS_PROBABILITY: float = 1.0 / 6.0

#: Coverage fraction treated as the safe ceiling. Roughly half of the
#: critical coverage at the default threshold, leaving room for an
#: adversary cleverer than the model assumes.
DEFAULT_SAFETY_MARGIN: float = 0.35


class KeyExhaustedError(RuntimeError):
    """Raised when a key has signed more messages than its policy allows."""


def coverage_after(n_signatures: int, table_size: int, signature_length: int) -> float:
    """Expected fraction of the key table exposed after *n_signatures*.

    ``f(n) = 1 - (1 - 1/T)^(n*L)``
    """
    if table_size < 1:
        raise ValueError(f"table_size must be >= 1, got {table_size}.")
    if n_signatures <= 0:
        return 0.0
    return 1.0 - (1.0 - 1.0 / table_size) ** (n_signatures * signature_length)


def critical_coverage(
    accept_threshold: float = 0.7,
    guess_probability: float = GUESS_PROBABILITY,
) -> float:
    """Coverage at which an attacker's match rate reaches acceptance.

    ``f* = (threshold - p_guess) / (1 - p_guess)``
    """
    if not (0.0 < accept_threshold <= 1.0):
        raise ValueError(
            f"accept_threshold must be in (0,1], got {accept_threshold}."
        )
    f = (accept_threshold - guess_probability) / (1.0 - guess_probability)
    return float(min(max(f, 0.0), 1.0))


def max_signatures(
    table_size: int,
    signature_length: int,
    safety_margin: float = DEFAULT_SAFETY_MARGIN,
) -> int:
    """Largest signature count keeping coverage below *safety_margin*.

    Returns
    -------
    int
        Maximum signatures for this key. May be ``0`` when the table is too
        small to sign even once safely -- which is itself the answer, and
        should be treated as a configuration error rather than rounded up.
    """
    if table_size < 1 or signature_length < 1:
        raise ValueError("table_size and signature_length must be >= 1.")
    if not (0.0 < safety_margin < 1.0):
        raise ValueError(f"safety_margin must be in (0,1), got {safety_margin}.")

    # Solve 1 - (1-1/T)^(nL) < margin  for n.
    denom = math.log(1.0 - 1.0 / table_size)
    if denom == 0:  # pragma: no cover - only for absurd table sizes
        return 0
    max_draws = math.log(1.0 - safety_margin) / denom
    return int(max(0, math.floor(max_draws / signature_length)))


def recommend_table_size(
    required_signatures: int,
    signature_length: int,
    safety_margin: float = DEFAULT_SAFETY_MARGIN,
) -> int:
    """Smallest power-of-two table supporting *required_signatures*.

    Powers of two are used so the recommendation is a round, memorable
    configuration value rather than an arbitrary integer.
    """
    if required_signatures < 1:
        raise ValueError("required_signatures must be >= 1.")

    size = 64
    while size <= 2 ** 20:
        if max_signatures(size, signature_length, safety_margin) >= required_signatures:
            return size
        size *= 2
    raise ValueError(
        f"No practical table size supports {required_signatures} signatures "
        f"at length {signature_length}; shorten the signature or rotate keys."
    )


@dataclass
class KeyUsagePolicy:
    """The signing limit for one key configuration.

    Attributes
    ----------
    table_size, signature_length : int
        Key geometry the limit is derived from.
    accept_threshold : float
        Verification threshold the breach point is computed against.
    safety_margin : float
        Coverage ceiling used to pick the limit.
    enforce : bool
        ``True`` raises :class:`KeyExhaustedError` once the limit is passed.
        ``False`` (default) logs a warning instead, so existing flows and
        evaluation harnesses keep working while still being told.
    """

    table_size: int
    signature_length: int
    accept_threshold: float = 0.7
    safety_margin: float = DEFAULT_SAFETY_MARGIN
    enforce: bool = False

    @property
    def limit(self) -> int:
        """Maximum signatures permitted for a key under this policy."""
        return max_signatures(
            self.table_size, self.signature_length, self.safety_margin
        )

    @property
    def critical(self) -> float:
        """Coverage at which forgery becomes feasible."""
        return critical_coverage(self.accept_threshold)

    def describe(self) -> str:
        """One-line human-readable summary."""
        return (
            f"table_size={self.table_size}, length={self.signature_length}: "
            f"limit={self.limit} signatures "
            f"(coverage ceiling {self.safety_margin:.2f}, "
            f"breach at {self.critical:.2f})"
        )


class KeyUsageTracker:
    """Counts signatures per key and applies a :class:`KeyUsagePolicy`.

    Deliberately in-process and explicit. A production deployment would
    persist these counts with the key material; the point here is that the
    limit is computed, checked and surfaced rather than left implicit.
    """

    def __init__(self, policy: KeyUsagePolicy) -> None:
        self.policy = policy
        self._counts: Dict[str, int] = {}
        self._warned: set[str] = set()

    def count(self, key_id: str) -> int:
        """Signatures recorded against *key_id*."""
        return self._counts.get(key_id, 0)

    def remaining(self, key_id: str) -> int:
        """Signatures still permitted for *key_id* (never negative)."""
        return max(0, self.policy.limit - self.count(key_id))

    def coverage(self, key_id: str) -> float:
        """Expected table coverage leaked by this key so far."""
        return coverage_after(
            self.count(key_id), self.policy.table_size,
            self.policy.signature_length,
        )

    def record(self, key_id: str) -> int:
        """Record one signature, applying the policy.

        Returns
        -------
        int
            The new signature count.

        Raises
        ------
        KeyExhaustedError
            If the limit is exceeded and the policy enforces it.
        """
        n = self._counts.get(key_id, 0) + 1
        self._counts[key_id] = n

        if n > self.policy.limit:
            msg = (
                f"Key {key_id[:8]}... has signed {n} messages, exceeding its "
                f"safe limit of {self.policy.limit} "
                f"({self.policy.describe()}). Expected table coverage is now "
                f"{self.coverage(key_id):.3f}; forgery becomes feasible at "
                f"{self.policy.critical:.3f}. Rotate the key, or enlarge the "
                f"table (recommended size for {n} signatures: "
                f"{recommend_table_size(n, self.policy.signature_length)})."
            )
            if self.policy.enforce:
                raise KeyExhaustedError(msg)
            if key_id not in self._warned:
                logger.warning("%s", msg)
                self._warned.add(key_id)

        return n

    def reset(self, key_id: Optional[str] = None) -> None:
        """Clear counts for one key, or all keys when *key_id* is ``None``."""
        if key_id is None:
            self._counts.clear()
            self._warned.clear()
        else:
            self._counts.pop(key_id, None)
            self._warned.discard(key_id)
