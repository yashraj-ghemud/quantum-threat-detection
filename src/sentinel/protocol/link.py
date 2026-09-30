"""
sentinel/protocol/link.py
=========================
Physical description of one signer -> verifier link, and the adversary's
plan for it.

:class:`LinkSpec` is the network's configuration of the link: the baseline
channel (which the *detector never reads*; it measures a baseline instead),
the fibre length, and whether the classical correction bits are
authenticated.

:class:`LinkPlan` is what an adversary (or a dishonest signer) does to that
link during one distribution. A clean link has the default plan.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

import numpy as np

__all__ = ["LinkSpec", "LinkPlan", "HardwareModel", "wc_tag", "wc_keys", "P61"]

P61 = (1 << 61) - 1


@dataclass
class LinkSpec:
    link_id: str
    signer_id: str
    verifier_id: str
    baseline: list = field(default_factory=list)      # channel specs
    length_km: float = 0.0
    authenticated: bool = False
    mac_key: bytes | None = None


@dataclass
class LinkPlan:
    extra_channel: list = field(default_factory=list)   # channel specs applied after the baseline
    substitute_fraction: float = 0.0
    substitute_mode: str = "none"                       # none | intercept_resend | mitm
    intercept_basis: str = "random"                     # random | x | y | z
    flip_c0: float = 0.0
    flip_c1: float = 0.0
    source_flip_fraction: float = 0.0                   # dishonest signer sends orthogonal states

    @property
    def is_clean(self) -> bool:
        return (not self.extra_channel and self.substitute_fraction <= 0 and self.flip_c0 <= 0
                and self.flip_c1 <= 0 and self.source_flip_fraction <= 0)

    def as_dict(self) -> dict:
        return {
            "extra_channel": list(self.extra_channel), "substitute_fraction": self.substitute_fraction,
            "substitute_mode": self.substitute_mode, "intercept_basis": self.intercept_basis,
            "flip_c0": self.flip_c0, "flip_c1": self.flip_c1, "source_flip_fraction": self.source_flip_fraction,
        }


@dataclass
class HardwareModel:
    """Modelled (not measured) hardware timing for entanglement distribution."""

    source_rate_hz: float = 1.0e7
    loss_db_per_km: float = 0.2
    detector_efficiency: float = 0.9

    def transmittance(self, length_km: float) -> float:
        return float(10 ** (-self.loss_db_per_km * length_km / 10.0))

    def time_ms(self, pairs: int, length_km: float) -> float:
        rate = self.source_rate_hz * self.transmittance(length_km) * self.detector_efficiency
        return float(1000.0 * pairs / rate) if rate > 0 else float("inf")


def wc_keys(mac_key: bytes, context: str) -> tuple[int, int]:
    """One-time Wegman-Carter keys (r, s) for a context (bundle, verifier)."""
    d = hmac.new(mac_key, context.encode("utf-8"), hashlib.sha256).digest()
    r = int.from_bytes(d[:8], "big") % P61
    s = int.from_bytes(d[8:16], "big") % P61
    return max(r, 2), s


def wc_tag(symbols: np.ndarray, r: int, s: int) -> int:
    """Wegman-Carter polynomial MAC over 2-bit symbols, modulo p = 2^61 - 1.

    Symbols are packed 30 per 60-bit word; the tag is ``(sum_i w_i r^(m-i+1) + s) mod p``
    with the stream length as the first word. Two different streams of equal
    length collide with probability at most ``m / p``.
    """
    sym = np.asarray(symbols, dtype=np.uint64).ravel()
    pad = (-sym.size) % 30
    if pad:
        sym = np.concatenate([sym, np.zeros(pad, dtype=np.uint64)])
    weights = (np.uint64(4) ** np.arange(30, dtype=np.uint64)).astype(np.uint64)
    words = (sym.reshape(-1, 30) * weights).sum(axis=1, dtype=np.uint64)
    h = 0
    for w in [int(symbols.size)] + [int(x) for x in words]:
        h = ((h + w) * r) % P61
    return (h + s) % P61
