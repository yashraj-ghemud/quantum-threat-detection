"""
sentinel/bell.py
================
Bell-pair statistics: CHSH and the |Phi+> fidelity witness.

Sacrificial Bell pairs certify that the link really distributes entanglement
before a single key qubit is trusted. Two families of settings are measured
on independent random subsets of pairs:

* **CHSH**: Alice A0 = Z, A1 = X; Bob B0 = (Z+X)/sqrt2, B1 = (Z-X)/sqrt2.
  ``S = E(A0,B0) + E(A0,B1) + E(A1,B0) - E(A1,B1)``. Any local (classical)
  source has ``S <= 2``; ideal |Phi+> reaches ``2 sqrt2``.
* **Witness**: XX, YY, ZZ correlators give the fidelity with |Phi+>,
  ``F = (1 + <XX> - <YY> + <ZZ>) / 4``. ``F > 1/2`` certifies entanglement.

For a pair whose receiver half went through a channel with affine map
``(M, c)``, the correlation tensor is ``T = T0 M^T`` with
``T0 = diag(1, -1, 1)``. Hence ``F = (1 + tr M)/4`` and the per-basis
disagreement fractions of the witness settings are exactly the teleportation
error rates ``(1 - M_bb)/2``. That identity drives the source-honesty
detector.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from sentinel.channels import Channel
from sentinel.linalg import I2, X, Y, Z
from sentinel.stats import cp_lower, cp_upper
from sentinel.teleport import PHI_PLUS

__all__ = [
    "BellSetting",
    "SETTINGS",
    "CHSH_SETTINGS",
    "WITNESS_SETTINGS",
    "bell_state",
    "correlation_tensor",
    "setting_probs",
    "mixed_setting_probs",
    "sample_bell_test",
    "BellEstimate",
    "estimate_bell",
    "predicted",
    "OUTCOMES",
]

_SIG = (X, Y, Z)
_R2 = 1.0 / math.sqrt(2.0)


@dataclass(frozen=True)
class BellSetting:
    name: str
    alpha: tuple  # Alice's measurement direction
    beta: tuple   # Bob's measurement direction


SETTINGS: tuple[BellSetting, ...] = (
    BellSetting("A0B0", (0, 0, 1), (_R2, 0, _R2)),
    BellSetting("A0B1", (0, 0, 1), (-_R2, 0, _R2)),
    BellSetting("A1B0", (1, 0, 0), (_R2, 0, _R2)),
    BellSetting("A1B1", (1, 0, 0), (-_R2, 0, _R2)),
    BellSetting("XX", (1, 0, 0), (1, 0, 0)),
    BellSetting("YY", (0, 1, 0), (0, 1, 0)),
    BellSetting("ZZ", (0, 0, 1), (0, 0, 1)),
)
CHSH_SETTINGS = (0, 1, 2, 3)
WITNESS_SETTINGS = (4, 5, 6)
#: CHSH signs for S = E00 + E01 + E10 - E11.
_CHSH_SIGNS = (1.0, 1.0, 1.0, -1.0)
#: Outcome order within each setting: (++, +-, -+, --).
OUTCOMES = ("++", "+-", "-+", "--")
#: Ideal |Phi+> correlation per witness setting: XX -> +1, YY -> -1, ZZ -> +1.
_IDEAL_WITNESS = (1.0, -1.0, 1.0)


def bell_state(channel_B: Channel | None, channel_A: Channel | None = None) -> np.ndarray:
    """(N_A (x) N_B)(|Phi+><Phi+|)."""
    rho = PHI_PLUS.copy()
    for ch, first in ((channel_B, False), (channel_A, True)):
        if ch is None:
            continue
        out = np.zeros((4, 4), dtype=complex)
        for K in ch.kraus:
            full = np.kron(K, I2) if first else np.kron(I2, K)
            out += full @ rho @ full.conj().T
        rho = out
    return rho


def correlation_tensor(rho: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``T_ij = Tr[rho (s_i (x) s_j)]`` and the local Bloch vectors ``a``, ``b``."""
    T = np.array([[np.real(np.trace(rho @ np.kron(si, sj))) for sj in _SIG] for si in _SIG])
    a = np.array([np.real(np.trace(rho @ np.kron(s, I2))) for s in _SIG])
    b = np.array([np.real(np.trace(rho @ np.kron(I2, s))) for s in _SIG])
    return T, a, b


def setting_probs(rho: np.ndarray) -> np.ndarray:
    """Outcome probabilities for the 7 settings, shape (7, 4) in (++, +-, -+, --) order."""
    T, a, b = correlation_tensor(rho)
    out = np.zeros((len(SETTINGS), 4))
    for s, st in enumerate(SETTINGS):
        al, be = np.asarray(st.alpha, float), np.asarray(st.beta, float)
        A, B, E = float(a @ al), float(b @ be), float(al @ T @ be)
        for i, (x, y) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
            out[s, i] = 0.25 * (1 + x * A + y * B + x * y * E)
    out = np.clip(out, 0.0, 1.0)
    return out / out.sum(axis=1, keepdims=True)


def mixed_setting_probs(components: list[tuple[float, np.ndarray]]) -> np.ndarray:
    """Probabilities for a per-pair mixture ``sum_i w_i rho_i`` (pairs independent)."""
    total = sum(w for w, _ in components)
    return sum(w * setting_probs(rho) for w, rho in components) / total


def sample_bell_test(probs: np.ndarray, n_per_setting: int, rng: np.random.Generator) -> np.ndarray:
    """Multinomial outcome counts, shape (7, 4)."""
    return np.stack([rng.multinomial(int(n_per_setting), p) for p in probs]).astype(np.int64)


@dataclass
class BellEstimate:
    n_per_setting: list
    E: dict                      # setting -> estimated correlation
    S: float
    S_lcb: float
    S_se: float
    F: float
    F_lcb: float
    F_se: float
    predicted_error: dict        # basis -> {"errors": int, "n": int, "rate": float}
    counts: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "n_per_setting": self.n_per_setting,
            "E": self.E,
            "S": self.S,
            "S_lcb": self.S_lcb,
            "S_se": self.S_se,
            "F": self.F,
            "F_lcb": self.F_lcb,
            "F_se": self.F_se,
            "predicted_error": self.predicted_error,
            "counts": self.counts,
        }


def estimate_bell(counts: np.ndarray, delta: float = 1e-5) -> BellEstimate:
    """Estimate CHSH S, witness F and Bell-predicted error rates with exact bounds.

    Each correlator is ``E = 2q - 1`` with ``q = P(product = +1)``. The lower
    bound on S uses one-sided Clopper-Pearson bounds on the four CHSH ``q``s
    (lower for the + terms, upper for the - term) at ``delta/4`` each, so the
    certificate holds with probability at least ``1 - delta``.
    """
    counts = np.asarray(counts, dtype=np.int64)
    n = counts.sum(axis=1)
    agree = counts[:, 0] + counts[:, 3]
    E = {}
    for s, st in enumerate(SETTINGS):
        E[st.name] = float(2 * agree[s] / n[s] - 1) if n[s] else 0.0

    S = 0.0
    S_lcb = 0.0
    var = 0.0
    for sign, s in zip(_CHSH_SIGNS, CHSH_SETTINGS):
        e = E[SETTINGS[s].name]
        S += sign * e
        if sign > 0:
            S_lcb += 2 * cp_lower(int(agree[s]), int(n[s]), delta / 4) - 1
        else:
            S_lcb -= 2 * cp_upper(int(agree[s]), int(n[s]), delta / 4) - 1
        var += (1 - e * e) / max(int(n[s]), 1)

    signs_w = (1.0, -1.0, 1.0)
    F = 0.25
    F_lcb = 0.25
    fvar = 0.0
    for sign, s in zip(signs_w, WITNESS_SETTINGS):
        e = E[SETTINGS[s].name]
        F += 0.25 * sign * e
        if sign > 0:
            F_lcb += 0.25 * (2 * cp_lower(int(agree[s]), int(n[s]), delta / 3) - 1)
        else:
            F_lcb -= 0.25 * (2 * cp_upper(int(agree[s]), int(n[s]), delta / 3) - 1)
        fvar += (1 - e * e) / max(int(n[s]), 1) / 16

    pred = {}
    for basis, s, ideal in zip(("x", "y", "z"), WITNESS_SETTINGS, _IDEAL_WITNESS):
        # "Error" = outcome pair that disagrees with the ideal |Phi+> correlation.
        errors = int(counts[s, 1] + counts[s, 2]) if ideal > 0 else int(counts[s, 0] + counts[s, 3])
        pred[basis] = {"errors": errors, "n": int(n[s]), "rate": errors / int(n[s]) if n[s] else 0.0}

    return BellEstimate(
        n_per_setting=[int(x) for x in n],
        E=E,
        S=float(S),
        S_lcb=float(S_lcb),
        S_se=float(math.sqrt(var)),
        F=float(F),
        F_lcb=float(F_lcb),
        F_se=float(math.sqrt(fvar)),
        predicted_error=pred,
        counts=counts.tolist(),
    )


def predicted(rho: np.ndarray) -> dict:
    """Exact S, F and per-basis error rates of a two-qubit state."""
    T, _, _ = correlation_tensor(rho)
    E = {}
    for st in SETTINGS:
        E[st.name] = float(np.asarray(st.alpha, float) @ T @ np.asarray(st.beta, float))
    S = E["A0B0"] + E["A0B1"] + E["A1B0"] - E["A1B1"]
    F = (1 + E["XX"] - E["YY"] + E["ZZ"]) / 4
    errs = {"x": (1 - E["XX"]) / 2, "y": (1 + E["YY"]) / 2, "z": (1 - E["ZZ"]) / 2}
    return {"S": float(S), "F": float(F), "E": E, "error": errs, "qber": float(np.mean(list(errs.values())))}
