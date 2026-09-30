"""
sentinel/tomography.py
======================
Pauli-frame de-twirling channel tomography from teleported key samples.

Why de-twirl
------------
After Bell outcome ``k`` the receiver holds ``N(sigma_k rho sigma_k)`` and
applies the correction ``c``. For an untampered frame the corrected state is
``P_c N(P_k r)``. Averaged over the uniformly random ``k`` this is the *Pauli
twirl* of ``N``: it erases the non-unital shift ``c`` (amplitude damping)
and the coherent (off-diagonal) part of ``M`` (unitary rotations). A detector
that only looks at averaged statistics is blind to both.

De-twirling identity
--------------------
Because ``P_c`` is its own inverse::

    N( r_{pi_k(l)} ) = P_c r_fin

so every parameter-estimation observation ``(label l, sent k, received c,
basis b, outcome o)`` is a single-shot sample of the ``b`` component of
``N`` applied to input ``pi_k(l)``, with the outcome sign multiplied by
``(P_c)_bb``. Using the *true* ``k`` for the input and the *received* ``c``
for the sign recovers the quantum channel even under classical tampering of
the correction bits. That tampering then shows up in the frame matrix.

Linear inversion from the six inputs ``+-e_j``::

    M[:, j] = (r(+j) - r(-j)) / 2
    c       = mean_j (r(+j) + r(-j)) / 2
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sentinel.states import BASIS_OF, BIT_OF, FRAME_PERM, FRAME_SIGNS, N_LABELS

__all__ = [
    "PECounts",
    "ChannelEstimate",
    "aggregate_pe",
    "qber_counts",
    "detwirl",
    "effective",
    "frame_matrix",
    "estimate_from_cells",
]

_SHAPE = (N_LABELS, 4, 4, 3, 2)  # label, sent k, received c, basis, outcome
_NCELLS = int(np.prod(_SHAPE))


@dataclass
class PECounts:
    """Parameter-estimation counts per (label, k, c, basis, outcome)."""

    cells: np.ndarray  # int64, shape (6, 4, 4, 3, 2)

    @property
    def total(self) -> int:
        return int(self.cells.sum())

    def __add__(self, other: "PECounts") -> "PECounts":
        return PECounts(self.cells + other.cells)

    def to_list(self) -> list:
        return self.cells.tolist()

    @classmethod
    def from_list(cls, data) -> "PECounts":
        return cls(np.asarray(data, dtype=np.int64).reshape(_SHAPE))

    @classmethod
    def empty(cls) -> "PECounts":
        return cls(np.zeros(_SHAPE, dtype=np.int64))


def aggregate_pe(labels, k, c, bases, outcomes) -> PECounts:
    """Aggregate per-position PE data into cell counts."""
    labels = np.asarray(labels, dtype=np.int64)
    idx = ((((labels * 4 + np.asarray(k, np.int64)) * 4 + np.asarray(c, np.int64)) * 3
            + np.asarray(bases, np.int64)) * 2 + np.asarray(outcomes, np.int64))
    cells = np.bincount(idx, minlength=_NCELLS).reshape(_SHAPE)
    return PECounts(cells.astype(np.int64))


def qber_counts(pe: PECounts) -> dict:
    """Mismatch counts on basis-matched positions, per basis and overall."""
    per = {}
    tot_e = tot_n = 0
    for b, name in enumerate(("x", "y", "z")):
        e = n = 0
        for l in range(N_LABELS):
            if BASIS_OF[l] != b:
                continue
            cnt = pe.cells[l, :, :, b, :].sum(axis=(0, 1))  # outcome counts
            n += int(cnt.sum())
            e += int(cnt[1 - BIT_OF[l]])  # outcome differs from the label's bit
        per[name] = {"errors": e, "n": n, "rate": e / n if n else 0.0}
        tot_e += e
        tot_n += n
    return {"per_basis": per, "errors": tot_e, "n": tot_n, "rate": tot_e / tot_n if tot_n else 0.0}


@dataclass
class ChannelEstimate:
    """Estimated affine Bloch map with the underlying two-outcome cells."""

    M: np.ndarray        # (3, 3)
    c: np.ndarray        # (3,)
    M_se: np.ndarray     # (3, 3)
    c_se: np.ndarray     # (3,)
    r: np.ndarray        # (6, 3) estimated output Bloch component per input label
    n: np.ndarray        # (6, 3) observations per (input, basis)
    plus: np.ndarray     # (6, 3) +1 outcomes per (input, basis) after sign correction

    def as_dict(self) -> dict:
        return {
            "M": self.M.tolist(),
            "c": self.c.tolist(),
            "M_se": self.M_se.tolist(),
            "c_se": self.c_se.tolist(),
            "r": self.r.tolist(),
            "n": self.n.tolist(),
            "plus": self.plus.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChannelEstimate":
        return cls(*(np.asarray(d[k], dtype=float) for k in ("M", "c", "M_se", "c_se", "r", "n", "plus")))


def estimate_from_cells(n: np.ndarray, plus: np.ndarray) -> ChannelEstimate:
    """Linear-inversion estimate from per-(input, basis) counts."""
    n = np.asarray(n, dtype=float)
    plus = np.asarray(plus, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(n > 0, (2 * plus - n) / np.where(n > 0, n, 1), 0.0)
        se = np.where(n > 0, np.sqrt(np.clip(1 - r ** 2, 1e-12, None) / np.where(n > 0, n, 1)), 1.0)
    M = np.zeros((3, 3))
    M_se = np.zeros((3, 3))
    c_parts = np.zeros((3, 3))
    c_var = np.zeros(3)
    for j in range(3):
        lp, lm = 2 * j, 2 * j + 1  # labels with Bloch +e_j and -e_j
        M[:, j] = (r[lp] - r[lm]) / 2
        M_se[:, j] = 0.5 * np.sqrt(se[lp] ** 2 + se[lm] ** 2)
        c_parts[:, j] = (r[lp] + r[lm]) / 2
        c_var += 0.25 * (se[lp] ** 2 + se[lm] ** 2)
    c = c_parts.mean(axis=1)
    c_se = np.sqrt(c_var) / 3.0
    return ChannelEstimate(M=M, c=c, M_se=M_se, c_se=c_se, r=r, n=n, plus=plus)


def detwirl(pe: PECounts) -> ChannelEstimate:
    """Estimate the physical channel N (de-twirled, frame-tamper corrected)."""
    n = np.zeros((N_LABELS, 3))
    plus = np.zeros((N_LABELS, 3))
    cells = pe.cells
    for l in range(N_LABELS):
        for k in range(4):
            lin = int(FRAME_PERM[k, l])
            for c in range(4):
                for b in range(3):
                    n0, n1 = cells[l, k, c, b, 0], cells[l, k, c, b, 1]
                    if n0 + n1 == 0:
                        continue
                    n[lin, b] += n0 + n1
                    # Outcome 0 is eigenvalue +1; multiply by the correction sign.
                    plus[lin, b] += n0 if FRAME_SIGNS[c, b] > 0 else n1
    return estimate_from_cells(n, plus)


def effective(pe: PECounts) -> ChannelEstimate:
    """Estimate the effective (twirled) map as verification experiences it."""
    per = pe.cells.sum(axis=(1, 2))  # (6, 3, 2)
    n = per.sum(axis=2).astype(float)
    plus = per[:, :, 0].astype(float)
    return estimate_from_cells(n, plus)


def frame_matrix(pe: PECounts) -> np.ndarray:
    """Counts of (sent k, received c), shape (4, 4). Diagonal when untampered."""
    return pe.cells.sum(axis=(0, 3, 4))
