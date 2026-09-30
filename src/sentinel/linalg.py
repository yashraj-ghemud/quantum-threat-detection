"""
sentinel/linalg.py
==================
Single-qubit linear algebra: Pauli transfer matrices, Choi matrices, affine
Bloch maps, polar decomposition and partial traces.

Conventions
-----------
- Pauli basis ``sigma_0 = I, sigma_1 = X, sigma_2 = Y, sigma_3 = Z``.
- A state ``rho = (I + r . sigma) / 2`` is carried as the homogeneous vector
  ``v = (1, r)``.
- The Pauli transfer matrix (PTM) of a map ``E`` is
  ``R_ij = 1/2 Tr(sigma_i E(sigma_j))`` so that ``E(rho) <-> R v``.
- A trace-preserving map has ``R = [[1, 0], [c, M]]`` i.e. ``r -> M r + c``.
- Multi-qubit tensors are big-endian: ``kron(q0, kron(q1, q2))``.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

__all__ = [
    "I2",
    "X",
    "Y",
    "Z",
    "H",
    "S",
    "PAULIS",
    "kraus_to_ptm",
    "ptm_to_choi",
    "is_cptp",
    "ptm_affine",
    "affine_ptm",
    "unitary_ptm",
    "pauli_ptm",
    "rodrigues",
    "su2_rotation",
    "polar",
    "rotation_axis_angle",
    "partial_trace",
    "bloch_to_rho",
    "rho_to_bloch",
    "apply_kraus",
]

I2 = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)
H = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2.0)
S = np.array([[1, 0], [0, 1j]], dtype=complex)

#: Pauli basis, shape (4, 2, 2).
PAULIS: np.ndarray = np.stack([I2, X, Y, Z])


def kraus_to_ptm(kraus: Iterable[np.ndarray]) -> np.ndarray:
    """Pauli transfer matrix of the channel with the given Kraus operators."""
    R = np.zeros((4, 4), dtype=complex)
    for K in kraus:
        K = np.asarray(K, dtype=complex)
        Kd = K.conj().T
        # R_ij = 1/2 Tr(sigma_i K sigma_j K^dagger)
        out = np.einsum("ab,jbc,cd->jad", K, PAULIS, Kd)  # E_K(sigma_j), shape (4,2,2)
        R += 0.5 * np.einsum("iab,jba->ij", PAULIS, out)
    return R.real.copy()


def _apply_ptm_to_operator(R: np.ndarray, A: np.ndarray) -> np.ndarray:
    """Apply the map with PTM ``R`` to an arbitrary 2x2 operator ``A``."""
    coeffs = 0.5 * np.einsum("jab,ba->j", PAULIS, A)  # A = sum_j coeffs_j sigma_j
    out_coeffs = R @ coeffs
    return np.einsum("i,iab->ab", out_coeffs, PAULIS)


def ptm_to_choi(R: np.ndarray) -> np.ndarray:
    """Choi matrix ``J = sum_ab |a><b| (x) E(|a><b|)`` (input (x) output)."""
    J = np.zeros((4, 4), dtype=complex)
    for a in range(2):
        for b in range(2):
            E = np.zeros((2, 2), dtype=complex)
            E[a, b] = 1.0
            J += np.kron(E, _apply_ptm_to_operator(np.asarray(R, dtype=float), E))
    return J


def is_cptp(R: np.ndarray, tol: float = 1e-10) -> tuple[bool, dict]:
    """Check complete positivity and trace preservation of a PTM.

    Returns ``(ok, info)`` with the Choi eigenvalues and the trace error.
    """
    J = ptm_to_choi(R)
    eig = np.linalg.eigvalsh((J + J.conj().T) / 2.0)
    # Partial trace over the output: Tr_out J must equal I_in.
    tr_out = np.einsum("aibi->ab", J.reshape(2, 2, 2, 2))
    tp_err = float(np.max(np.abs(tr_out - I2)))
    ok = bool(eig.min() >= -tol and tp_err <= max(tol, 1e-9))
    return ok, {"choi_eigenvalues": eig.real.tolist(), "tp_error": tp_err, "min_eig": float(eig.min())}


def ptm_affine(R: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split a trace-preserving PTM into its affine Bloch map ``(M, c)``."""
    R = np.asarray(R, dtype=float)
    return R[1:, 1:].copy(), R[1:, 0].copy()


def affine_ptm(M: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Assemble a PTM from an affine Bloch map."""
    R = np.zeros((4, 4))
    R[0, 0] = 1.0
    R[1:, 1:] = M
    R[1:, 0] = c
    return R


def unitary_ptm(U: np.ndarray) -> np.ndarray:
    """PTM of conjugation by a unitary."""
    return kraus_to_ptm([U])


def pauli_ptm(index: int) -> np.ndarray:
    """PTM of conjugation by Pauli ``index`` (0=I, 1=X, 2=Y, 3=Z)."""
    signs = {0: (1, 1, 1), 1: (1, -1, -1), 2: (-1, 1, -1), 3: (-1, -1, 1)}[int(index)]
    return np.diag((1.0,) + tuple(float(s) for s in signs))


def rodrigues(axis: Sequence[float], theta: float) -> np.ndarray:
    """3x3 rotation matrix about ``axis`` by ``theta`` (right-hand rule)."""
    n = np.asarray(axis, dtype=float)
    norm = np.linalg.norm(n)
    if norm == 0:
        raise ValueError("rotation axis must be non-zero")
    n = n / norm
    K = np.array([[0, -n[2], n[1]], [n[2], 0, -n[0]], [-n[1], n[0], 0]])
    return np.eye(3) + np.sin(theta) * K + (1 - np.cos(theta)) * (K @ K)


def su2_rotation(axis: Sequence[float], theta: float) -> np.ndarray:
    """``U = exp(-i theta n.sigma / 2)``; acts on the Bloch sphere as ``rodrigues(n, theta)``."""
    n = np.asarray(axis, dtype=float)
    n = n / np.linalg.norm(n)
    ns = n[0] * X + n[1] * Y + n[2] * Z
    return np.cos(theta / 2) * I2 - 1j * np.sin(theta / 2) * ns


def polar(M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Polar decomposition ``M = U P`` with ``U`` a proper rotation.

    When ``det(M) < 0`` the sign of the smallest singular direction is moved
    into ``P`` so that ``U`` stays in SO(3); ``P`` is then symmetric but has
    one (small) negative eigenvalue.
    """
    W, s, Vt = np.linalg.svd(np.asarray(M, dtype=float))
    D = np.eye(3)
    if np.linalg.det(W @ Vt) < 0:
        D[2, 2] = -1.0
    U = W @ D @ Vt
    P = Vt.T @ np.diag(s) @ D @ Vt
    return U, P


def rotation_axis_angle(U: np.ndarray) -> tuple[np.ndarray, float]:
    """Axis (unit vector) and angle in [0, pi] of a rotation matrix."""
    U = np.asarray(U, dtype=float)
    cos_t = np.clip((np.trace(U) - 1.0) / 2.0, -1.0, 1.0)
    theta = float(np.arccos(cos_t))
    if theta < 1e-9:
        return np.array([0.0, 0.0, 1.0]), 0.0
    if np.pi - theta < 1e-6:
        B = (U + np.eye(3)) / 2.0
        col = int(np.argmax(np.diag(B)))
        axis = B[:, col] / np.sqrt(max(B[col, col], 1e-15))
        return axis / np.linalg.norm(axis), theta
    axis = np.array([U[2, 1] - U[1, 2], U[0, 2] - U[2, 0], U[1, 0] - U[0, 1]]) / (2 * np.sin(theta))
    return axis / np.linalg.norm(axis), theta


def partial_trace(rho: np.ndarray, keep: Sequence[int], dims: Sequence[int]) -> np.ndarray:
    """Partial trace keeping subsystems ``keep`` (big-endian order)."""
    dims = list(dims)
    n = len(dims)
    keep = sorted(keep)
    rho_t = np.asarray(rho).reshape(dims + dims)
    trace_out = [i for i in range(n) if i not in keep]
    # Contract traced subsystems pairwise.
    letters = "abcdefghijklmnopqrstuvwxyz"
    ket = list(letters[:n])
    bra = list(letters[n:2 * n])
    for i in trace_out:
        bra[i] = ket[i]
    out_ket = "".join(ket[i] for i in keep)
    out_bra = "".join(bra[i] for i in keep)
    expr = f"{''.join(ket)}{''.join(bra)}->{out_ket}{out_bra}"
    res = np.einsum(expr, rho_t)
    d = int(np.prod([dims[i] for i in keep])) if keep else 1
    return res.reshape(d, d)


def bloch_to_rho(r: Sequence[float]) -> np.ndarray:
    """Density matrix of a Bloch vector."""
    r = np.asarray(r, dtype=float)
    return 0.5 * (I2 + r[0] * X + r[1] * Y + r[2] * Z)


def rho_to_bloch(rho: np.ndarray) -> np.ndarray:
    """Bloch vector of a single-qubit density matrix."""
    rho = np.asarray(rho, dtype=complex)
    return np.real(np.array([np.trace(rho @ P) for P in (X, Y, Z)]))


def apply_kraus(rho: np.ndarray, kraus: Iterable[np.ndarray], on: int, n_qubits: int) -> np.ndarray:
    """Apply a single-qubit channel (Kraus list) to qubit ``on`` of an n-qubit state."""
    out = np.zeros_like(rho, dtype=complex)
    for K in kraus:
        ops = [I2] * n_qubits
        ops[on] = np.asarray(K, dtype=complex)
        full = ops[0]
        for op in ops[1:]:
            full = np.kron(full, op)
        out += full @ rho @ full.conj().T
    return out
