"""
sentinel/rng.py
===============
Randomness sources.

Two very different kinds of randomness appear in the simulation:

* **Key material and secret choices**: private labels, verifier bases,
  parameter-estimation positions, symmetrization subsets, nonces. In secure
  mode these come from the operating system CSPRNG (``secrets``), because in
  a real deployment they *are* cryptographic secrets.
* **Physics**: Bell-measurement and projective-measurement outcomes. These
  simulate nature and come from a PCG64DXSM generator seeded from the CSPRNG.

``seed`` mode makes both reproducible for tests and published experiments.
It is refused when ``QVERIS_ENV=production``.
"""

from __future__ import annotations

import os
import secrets
from typing import Optional

import numpy as np

__all__ = ["RandomSource", "SeededModeRefused"]


class SeededModeRefused(RuntimeError):
    """Seeded (non-cryptographic) randomness requested in production."""


def _uniform_mod(nbytes_fn, n: int, modulus: int) -> np.ndarray:
    """Exactly-uniform values in [0, modulus) by rejection sampling on bytes."""
    limit = 256 - (256 % modulus)
    out = np.empty(n, dtype=np.uint8)
    filled = 0
    while filled < n:
        need = n - filled
        raw = np.frombuffer(nbytes_fn(int(need * 256 / limit * 1.02) + 64), dtype=np.uint8)
        good = raw[raw < limit]
        take = min(need, good.size)
        out[filled:filled + take] = good[:take] % modulus
        filled += take
    return out


class RandomSource:
    """Randomness for one run (a distribution, a signing session, a job)."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self.seeded = seed is not None
        if self.seeded:
            if os.environ.get("QVERIS_ENV", "").lower() == "production":
                raise SeededModeRefused("seeded randomness is disabled in production")
            ss = np.random.SeedSequence(int(seed))
            key_ss, phys_ss = ss.spawn(2)
            self._key = np.random.Generator(np.random.PCG64DXSM(key_ss))
            self.physics = np.random.Generator(np.random.PCG64DXSM(phys_ss))
        else:
            self._key = None
            self.physics = np.random.Generator(np.random.PCG64DXSM(secrets.randbits(128)))

    # -- secret material ----------------------------------------------------
    def _bytes(self, n: int) -> bytes:
        if self._key is not None:
            return self._key.integers(0, 256, size=n, dtype=np.uint8).tobytes()
        return secrets.token_bytes(n)

    def labels(self, n: int) -> np.ndarray:
        """Uniform six-state labels (uint8)."""
        return _uniform_mod(self._bytes, int(n), 6)

    def bases(self, n: int) -> np.ndarray:
        """Uniform measurement bases 0/1/2 (uint8)."""
        return _uniform_mod(self._bytes, int(n), 3)

    def bits(self, n: int) -> np.ndarray:
        """Uniform bits (uint8)."""
        return np.unpackbits(np.frombuffer(self._bytes((int(n) + 7) // 8), dtype=np.uint8))[: int(n)]

    def sort_keys(self, shape) -> np.ndarray:
        """Uniform 32-bit keys; ``argsort`` along an axis gives a uniform permutation."""
        count = int(np.prod(shape))
        return np.frombuffer(self._bytes(4 * count), dtype=np.uint32).reshape(shape)

    def secret_uniform(self, n: int) -> np.ndarray:
        """Uniform floats in [0, 1) from secret-grade randomness (53-bit)."""
        raw = np.frombuffer(self._bytes(8 * int(n)), dtype=np.uint64)
        return (raw >> np.uint64(11)).astype(np.float64) * (1.0 / (1 << 53))

    def choose_mask(self, n: int, k: int) -> np.ndarray:
        """Boolean mask of length n with exactly k True entries, uniformly placed."""
        order = np.argsort(self.sort_keys((n,)), kind="stable")
        mask = np.zeros(n, dtype=bool)
        mask[order[:k]] = True
        return mask

    def token_hex(self, nbytes: int = 16) -> str:
        return self._bytes(nbytes).hex()

    def randbelow(self, n: int) -> int:
        if self._key is not None:
            return int(self._key.integers(0, n))
        return secrets.randbelow(n)

    # -- physics --------------------------------------------------------------
    def uniform(self, n: int) -> np.ndarray:
        return self.physics.random(int(n))
