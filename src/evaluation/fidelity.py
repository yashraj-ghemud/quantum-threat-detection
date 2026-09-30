"""
evaluation/fidelity.py
======================
State-comparison metrics: fidelity, trace distance, purity.

Phase 2/7 -- SIH26141 | Blockchain & Cybersecurity.

These quantify how far a *received* quantum state has drifted from the
state that was *sent*. They are the physical half of the threat-detection
evidence: an attack on the channel shows up here before it shows up in the
signature match rate.

Definitions
-----------
Fidelity (Uhlmann), for states rho and sigma::

    F(rho, sigma) = ( Tr sqrt( sqrt(rho) sigma sqrt(rho) ) )^2

with the pure-state special cases ``F = |<psi|phi>|^2`` and
``F = <psi| rho |psi>``. We use the **squared** convention throughout, so
``F = 1`` means identical and ``F`` is comparable with Qiskit's
``state_fidelity``.

Trace distance::

    T(rho, sigma) = (1/2) * Tr | rho - sigma |
                  = (1/2) * sum |eigenvalues of (rho - sigma)|

``T`` is a true metric and bounds the probability of distinguishing the two
states in a single measurement, which makes it the natural quantity for
"how detectable is this disturbance". For a single qubit it equals half the
Euclidean distance between Bloch vectors.

Purity::

    P(rho) = Tr(rho^2)  in [1/2, 1] for a qubit

``P = 1`` is pure; ``P = 1/2`` is maximally mixed. A depolarizing channel
drives purity down, so it separates *decoherence* from a *unitary* error --
a rotated but still pure state keeps ``P = 1`` while its fidelity falls.

No AI/ML libraries are used.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "to_density_matrix",
    "state_fidelity",
    "trace_distance",
    "purity",
    "bloch_vector",
    "bloch_distance",
    "fidelity_bounds_from_trace_distance",
]


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

def to_density_matrix(state) -> np.ndarray:
    """Coerce a statevector or density matrix to a 2x2 density matrix.

    Accepts a Qiskit ``Statevector`` / ``DensityMatrix``, a NumPy array of
    shape ``(2,)`` (pure state, converted via ``|psi><psi|``) or ``(2, 2)``.

    Raises
    ------
    ValueError
        If the input is not a single-qubit state.
    """
    arr = np.asarray(getattr(state, "data", state), dtype=complex)

    if arr.ndim == 1:
        if arr.shape[0] != 2:
            raise ValueError(
                f"Expected a single-qubit statevector of shape (2,), got {arr.shape}."
            )
        norm = float(np.linalg.norm(arr))
        if norm > 0:
            arr = arr / norm
        return np.outer(arr, arr.conj())

    if arr.shape != (2, 2):
        raise ValueError(
            f"Expected a single-qubit density matrix of shape (2,2), got {arr.shape}."
        )
    return arr


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def state_fidelity(state_a, state_b) -> float:
    """Return the squared Uhlmann fidelity ``F(a, b)`` in [0, 1].

    Falls back to the closed form when either argument is pure, and uses
    the matrix square root otherwise.

    Parameters
    ----------
    state_a, state_b : Statevector, DensityMatrix or array-like
        States to compare.

    Returns
    -------
    float
        ``1.0`` for identical states, ``0.0`` for orthogonal ones.
    """
    rho = to_density_matrix(state_a)
    sigma = to_density_matrix(state_b)

    # Pure-state shortcut: F = <psi| sigma |psi>, exact and cheap.
    if abs(float(np.real(np.trace(rho @ rho))) - 1.0) < 1e-9:
        eigvals, eigvecs = np.linalg.eigh(rho)
        psi = eigvecs[:, int(np.argmax(eigvals.real))]
        return float(np.clip(np.real(psi.conj() @ sigma @ psi), 0.0, 1.0))

    if abs(float(np.real(np.trace(sigma @ sigma))) - 1.0) < 1e-9:
        eigvals, eigvecs = np.linalg.eigh(sigma)
        phi = eigvecs[:, int(np.argmax(eigvals.real))]
        return float(np.clip(np.real(phi.conj() @ rho @ phi), 0.0, 1.0))

    # General mixed-mixed case via the matrix square root.
    sqrt_rho = _matrix_sqrt(rho)
    inner = _matrix_sqrt(sqrt_rho @ sigma @ sqrt_rho)
    f = float(np.real(np.trace(inner))) ** 2
    return float(np.clip(f, 0.0, 1.0))


def _matrix_sqrt(mat: np.ndarray) -> np.ndarray:
    """Principal square root of a Hermitian positive-semidefinite matrix."""
    eigvals, eigvecs = np.linalg.eigh(mat)
    eigvals = np.clip(eigvals.real, 0.0, None)
    return (eigvecs * np.sqrt(eigvals)) @ eigvecs.conj().T


def trace_distance(state_a, state_b) -> float:
    """Return the trace distance ``T(a, b)`` in [0, 1].

    ``T = 0`` means indistinguishable; ``T = 1`` means perfectly
    distinguishable by a single optimal measurement.
    """
    rho = to_density_matrix(state_a)
    sigma = to_density_matrix(state_b)
    diff = rho - sigma
    eigvals = np.linalg.eigvalsh(diff)
    return float(np.clip(0.5 * np.sum(np.abs(eigvals.real)), 0.0, 1.0))


def purity(state) -> float:
    """Return ``Tr(rho^2)`` in [0.5, 1] for a single qubit.

    Distinguishes decoherence from unitary error: a depolarized state loses
    purity, a merely rotated state does not.
    """
    rho = to_density_matrix(state)
    return float(np.clip(np.real(np.trace(rho @ rho)), 0.0, 1.0))


def bloch_vector(state) -> np.ndarray:
    """Return the Bloch vector ``(x, y, z)`` with ``b_k = Tr(rho sigma_k)``."""
    from qds.pauli_states import PAULI_MATRICES

    rho = to_density_matrix(state)
    return np.array(
        [float(np.real(np.trace(rho @ PAULI_MATRICES[b]))) for b in ("x", "y", "z")],
        dtype=float,
    )


def bloch_distance(state_a, state_b) -> float:
    """Euclidean distance between two Bloch vectors, in [0, 2].

    Related to trace distance by ``T = |b_a - b_b| / 2`` for a qubit;
    exposed separately because the raw length is easier to reason about
    when visualising states on the sphere.
    """
    return float(np.linalg.norm(bloch_vector(state_a) - bloch_vector(state_b)))


def fidelity_bounds_from_trace_distance(t: float) -> Tuple[float, float]:
    """Bound fidelity given trace distance via Fuchs-van de Graaf.

    ``1 - T <= sqrt(F) <= sqrt(1 - T^2)``, rearranged to bound ``F``:

        (1 - T)^2  <=  F  <=  1 - T^2

    Used as an internal consistency check: a measured (F, T) pair that
    violates these bounds indicates a computation error, not an attack.
    """
    t = float(np.clip(t, 0.0, 1.0))
    return (1.0 - t) ** 2, 1.0 - t**2
