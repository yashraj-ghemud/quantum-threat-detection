"""
sentinel/states.py
==================
The six-state Pauli-eigenstate alphabet and the Pauli-frame algebra on it.

Label order is fixed and chosen so that ``basis index == Bloch component``::

    label  ket    basis  bit  eigenvalue  Bloch
      0    |+>     X      0      +1      (+1, 0, 0)
      1    |->     X      1      -1      (-1, 0, 0)
      2    |+i>    Y      0      +1      (0, +1, 0)
      3    |-i>    Y      1      -1      (0, -1, 0)
      4    |0>     Z      0      +1      (0, 0, +1)
      5    |1>     Z      1      -1      (0, 0, -1)

A measurement outcome ``o = 0`` means eigenvalue ``+1``.

Pauli frames
------------
A teleportation Bell outcome ``k = 2*m0 + m1`` leaves the receiver holding
``sigma_k rho sigma_k`` with ``sigma_k = X^m1 Z^m0``. Conjugation by a Pauli
flips the signs of two Bloch components:

====  =========  ==================
 k    sigma_k    Bloch signs (x,y,z)
====  =========  ==================
 0    I          (+, +, +)
 1    X          (+, -, -)
 2    Z          (-, -, +)
 3    XZ ~ Y     (-, +, -)
====  =========  ==================

The correction applied for received bits ``c`` is ``Z^c0 X^c1``, whose
conjugation has the same sign pattern as ``sigma_c``.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "N_LABELS",
    "LABELS",
    "KETS",
    "BASIS_NAMES",
    "BASIS_OF",
    "BIT_OF",
    "BLOCH",
    "V4",
    "FRAME_SIGNS",
    "FRAME_PTM",
    "FRAME_PERM",
    "label_from",
    "bloch_of",
]

N_LABELS: int = 6
LABELS: tuple[str, ...] = ("+", "-", "+i", "-i", "0", "1")
KETS: tuple[str, ...] = ("|+>", "|->", "|+i>", "|-i>", "|0>", "|1>")
BASIS_NAMES: tuple[str, ...] = ("x", "y", "z")

BASIS_OF: np.ndarray = np.array([0, 0, 1, 1, 2, 2], dtype=np.uint8)
BIT_OF: np.ndarray = np.array([0, 1, 0, 1, 0, 1], dtype=np.uint8)

#: Bloch vectors, shape (6, 3).
BLOCH: np.ndarray = np.zeros((N_LABELS, 3), dtype=float)
for _l in range(N_LABELS):
    BLOCH[_l, BASIS_OF[_l]] = 1.0 if BIT_OF[_l] == 0 else -1.0

#: Homogeneous Bloch 4-vectors (1, r), shape (6, 4).
V4: np.ndarray = np.hstack([np.ones((N_LABELS, 1)), BLOCH])

#: Sign pattern of conjugation by sigma_k on (x, y, z), shape (4, 3).
FRAME_SIGNS: np.ndarray = np.array(
    [
        [+1.0, +1.0, +1.0],  # I
        [+1.0, -1.0, -1.0],  # X
        [-1.0, -1.0, +1.0],  # Z
        [-1.0, +1.0, -1.0],  # XZ
    ]
)

#: Pauli transfer matrices of the frame conjugations, shape (4, 4, 4).
FRAME_PTM: np.ndarray = np.stack([np.diag(np.concatenate([[1.0], s])) for s in FRAME_SIGNS])


def label_from(basis: int, bit: int) -> int:
    """Label index for a basis (0=X, 1=Y, 2=Z) and a bit (0 = eigenvalue +1)."""
    if basis not in (0, 1, 2) or bit not in (0, 1):
        raise ValueError(f"invalid basis/bit ({basis}, {bit})")
    return 2 * int(basis) + int(bit)


def bloch_of(label: int) -> np.ndarray:
    """Bloch vector of a label (copy)."""
    return BLOCH[int(label)].copy()


def _frame_perm() -> np.ndarray:
    perm = np.zeros((4, N_LABELS), dtype=np.uint8)
    for k in range(4):
        for l in range(N_LABELS):
            target = FRAME_SIGNS[k] * BLOCH[l]
            match = np.where(np.all(np.isclose(BLOCH, target), axis=1))[0]
            perm[k, l] = int(match[0])
    return perm


#: ``FRAME_PERM[k, l]`` is the label whose Bloch vector is ``P_k r_l``.
FRAME_PERM: np.ndarray = _frame_perm()
