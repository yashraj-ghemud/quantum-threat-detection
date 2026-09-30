"""
qds/pauli_states.py
====================
Pauli eigenstate definitions for the Quantum Digital Signature scheme.

Phase 3 -- SIH26141 | Blockchain & Cybersecurity.

Defines the six Pauli eigenstates used as the elementary quantum key
material in the QDS protocol:

    Z basis  |0>   |1>
    X basis  |+>   |->
    Y basis  |+i>  |-i>

Each eigenstate is represented by a ``PauliEigenstate`` dataclass that
carries the statevector, Bloch-sphere angles (theta, phi), Pauli
eigenvalue (+1 or -1), measurement basis, and Bloch-vector coordinates.

Projective measurement probabilities are calculated analytically as

    P(+1) = <psi| P+ |psi>    where  P+ = (I + sigma) / 2
    P(-1) = <psi| P- |psi>    where  P- = (I - sigma) / 2

No AI/ML is used in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    # Constants
    "SIGMA_X",
    "SIGMA_Y",
    "SIGMA_Z",
    "IDENTITY",
    "PAULI_MATRICES",
    "PROJECTOR_PLUS",
    "PROJECTOR_MINUS",
    "EIGENSTATE_LABELS",
    # Dataclass
    "PauliEigenstate",
    # Eigenstate constructors
    "make_ket_0",
    "make_ket_1",
    "make_ket_plus",
    "make_ket_minus",
    "make_ket_plus_i",
    "make_ket_minus_i",
    "get_eigenstate",
    "all_eigenstates",
    # Measurement
    "projective_measurement_probs",
    "measure_eigenstate",
    # Validation
    "validate_statevector_norm",
    "validate_eigenvalue_equation",
]

# ---------------------------------------------------------------------------
# Pauli matrices and identity  (dtype complex128)
# ---------------------------------------------------------------------------

SIGMA_X: np.ndarray = np.array([[0, 1], [1, 0]], dtype=complex)
SIGMA_Y: np.ndarray = np.array([[0, -1j], [1j, 0]], dtype=complex)
SIGMA_Z: np.ndarray = np.array([[1, 0], [0, -1]], dtype=complex)
IDENTITY: np.ndarray = np.eye(2, dtype=complex)

#: Mapping from basis label to corresponding Pauli matrix.
PAULI_MATRICES: Dict[str, np.ndarray] = {
    "x": SIGMA_X,
    "y": SIGMA_Y,
    "z": SIGMA_Z,
}

_INV_SQRT2 = 1.0 / np.sqrt(2.0)


def _projector_plus(sigma: np.ndarray) -> np.ndarray:
    """P+ = (I + sigma) / 2  — projector onto +1 eigenspace."""
    return (IDENTITY + sigma) / 2.0


def _projector_minus(sigma: np.ndarray) -> np.ndarray:
    """P- = (I - sigma) / 2  — projector onto -1 eigenspace."""
    return (IDENTITY - sigma) / 2.0


#: Pre-computed projectors for all three bases, keyed by basis label.
PROJECTOR_PLUS: Dict[str, np.ndarray] = {
    basis: _projector_plus(sigma)
    for basis, sigma in PAULI_MATRICES.items()
}
PROJECTOR_MINUS: Dict[str, np.ndarray] = {
    basis: _projector_minus(sigma)
    for basis, sigma in PAULI_MATRICES.items()
}

#: Canonical labels for all six eigenstates.
EIGENSTATE_LABELS: Tuple[str, ...] = ("|0>", "|1>", "|+>", "|->", "|+i>", "|-i>")


# ---------------------------------------------------------------------------
# PauliEigenstate dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PauliEigenstate:
    """Immutable descriptor for a single Pauli eigenstate.

    Attributes
    ----------
    label : str
        Human-readable label, e.g. ``'|+>'``.
    basis : str
        Measurement basis: ``'x'``, ``'y'``, or ``'z'``.
    eigenvalue : int
        Pauli eigenvalue: ``+1`` (positive eigenstate) or ``-1``.
    statevector : np.ndarray, shape (2,), complex128
        Normalised statevector [alpha, beta].
    theta : float
        Bloch-sphere polar angle (radians).  Defined by
        ``|psi> = cos(theta/2)|0> + e^{i*phi}*sin(theta/2)|1>``.
    phi : float
        Bloch-sphere azimuthal angle (radians).
    bloch_vector : np.ndarray, shape (3,), float64
        (bx, by, bz) = (sin(theta)*cos(phi), sin(theta)*sin(phi), cos(theta)).
    """

    label: str
    basis: str
    eigenvalue: int
    statevector: np.ndarray
    theta: float
    phi: float
    bloch_vector: np.ndarray = field(compare=False)

    def __post_init__(self) -> None:
        # Freeze the arrays so the dataclass stays hashable
        object.__setattr__(self, "statevector", np.array(self.statevector, dtype=complex))
        object.__setattr__(self, "bloch_vector", np.array(self.bloch_vector, dtype=float))

    @property
    def density_matrix(self) -> np.ndarray:
        """Pure-state density matrix rho = |psi><psi|."""
        sv = self.statevector
        return np.outer(sv, sv.conj())

    def __repr__(self) -> str:
        return (
            f"PauliEigenstate(label={self.label!r}, basis={self.basis!r}, "
            f"eigenvalue={self.eigenvalue:+d}, "
            f"theta={self.theta:.4f}, phi={self.phi:.4f})"
        )


# ---------------------------------------------------------------------------
# Bloch-vector helper
# ---------------------------------------------------------------------------

def _bloch(theta: float, phi: float) -> np.ndarray:
    """Compute Bloch vector (bx, by, bz) from (theta, phi)."""
    return np.array([
        np.sin(theta) * np.cos(phi),
        np.sin(theta) * np.sin(phi),
        np.cos(theta),
    ], dtype=float)


# ---------------------------------------------------------------------------
# Six eigenstate constructors
# ---------------------------------------------------------------------------

def make_ket_0() -> PauliEigenstate:
    """|0> -- positive Z eigenstate, theta=0, phi=0, Bloch=(0,0,+1)."""
    theta, phi = 0.0, 0.0
    return PauliEigenstate(
        label="|0>",
        basis="z",
        eigenvalue=+1,
        statevector=np.array([1.0, 0.0], dtype=complex),
        theta=theta,
        phi=phi,
        bloch_vector=_bloch(theta, phi),
    )


def make_ket_1() -> PauliEigenstate:
    """|1> -- negative Z eigenstate, theta=pi, phi=0, Bloch=(0,0,-1)."""
    theta, phi = float(np.pi), 0.0
    return PauliEigenstate(
        label="|1>",
        basis="z",
        eigenvalue=-1,
        statevector=np.array([0.0, 1.0], dtype=complex),
        theta=theta,
        phi=phi,
        bloch_vector=_bloch(theta, phi),
    )


def make_ket_plus() -> PauliEigenstate:
    """|+> -- positive X eigenstate, theta=pi/2, phi=0, Bloch=(1,0,0)."""
    theta, phi = float(np.pi / 2), 0.0
    return PauliEigenstate(
        label="|+>",
        basis="x",
        eigenvalue=+1,
        statevector=np.array([_INV_SQRT2, _INV_SQRT2], dtype=complex),
        theta=theta,
        phi=phi,
        bloch_vector=_bloch(theta, phi),
    )


def make_ket_minus() -> PauliEigenstate:
    """|-> -- negative X eigenstate, theta=pi/2, phi=pi, Bloch=(-1,0,0)."""
    theta, phi = float(np.pi / 2), float(np.pi)
    return PauliEigenstate(
        label="|->",
        basis="x",
        eigenvalue=-1,
        statevector=np.array([_INV_SQRT2, -_INV_SQRT2], dtype=complex),
        theta=theta,
        phi=phi,
        bloch_vector=_bloch(theta, phi),
    )


def make_ket_plus_i() -> PauliEigenstate:
    """|+i> -- positive Y eigenstate, theta=pi/2, phi=pi/2, Bloch=(0,1,0)."""
    theta, phi = float(np.pi / 2), float(np.pi / 2)
    return PauliEigenstate(
        label="|+i>",
        basis="y",
        eigenvalue=+1,
        statevector=np.array([_INV_SQRT2, 1j * _INV_SQRT2], dtype=complex),
        theta=theta,
        phi=phi,
        bloch_vector=_bloch(theta, phi),
    )


def make_ket_minus_i() -> PauliEigenstate:
    """|-i> -- negative Y eigenstate, theta=pi/2, phi=3pi/2, Bloch=(0,-1,0)."""
    theta, phi = float(np.pi / 2), float(3 * np.pi / 2)
    return PauliEigenstate(
        label="|-i>",
        basis="y",
        eigenvalue=-1,
        statevector=np.array([_INV_SQRT2, -1j * _INV_SQRT2], dtype=complex),
        theta=theta,
        phi=phi,
        bloch_vector=_bloch(theta, phi),
    )


# ---------------------------------------------------------------------------
# Dispatch and bulk access
# ---------------------------------------------------------------------------

_EIGENSTATE_REGISTRY: Dict[str, object] = {
    "|0>":  make_ket_0,
    "|1>":  make_ket_1,
    "|+>":  make_ket_plus,
    "|->":  make_ket_minus,
    "|+i>": make_ket_plus_i,
    "|-i>": make_ket_minus_i,
}


def get_eigenstate(label: str) -> PauliEigenstate:
    """Return the ``PauliEigenstate`` for the given label.

    Parameters
    ----------
    label : str
        One of ``'|0>'``, ``'|1>'``, ``'|+>'``, ``'|->'``,
        ``'|+i>'``, ``'|-i>'``.

    Returns
    -------
    PauliEigenstate

    Raises
    ------
    ValueError
        If *label* is not a recognised eigenstate.
    """
    factory = _EIGENSTATE_REGISTRY.get(label)
    if factory is None:
        raise ValueError(
            f"Unknown eigenstate label {label!r}. "
            f"Supported: {list(EIGENSTATE_LABELS)}"
        )
    return factory()  # type: ignore[operator]


def all_eigenstates() -> Dict[str, PauliEigenstate]:
    """Return all six eigenstates as a label → PauliEigenstate dict."""
    return {label: get_eigenstate(label) for label in EIGENSTATE_LABELS}


# ---------------------------------------------------------------------------
# Projective measurement
# ---------------------------------------------------------------------------

def projective_measurement_probs(
    statevector: np.ndarray,
    basis: str,
) -> Tuple[float, float]:
    """Compute projective measurement probabilities P(+1) and P(-1).

    Calculates::

        P(+1) = <psi| P+ |psi>   where  P+ = (I + sigma_basis) / 2
        P(-1) = <psi| P- |psi>   where  P- = (I - sigma_basis) / 2

    Parameters
    ----------
    statevector : np.ndarray, shape (2,)
        Normalised single-qubit statevector.
    basis : str
        Measurement basis: ``'x'``, ``'y'``, or ``'z'``.

    Returns
    -------
    tuple[float, float]
        ``(p_plus, p_minus)`` where both are in [0, 1] and sum to 1.

    Raises
    ------
    ValueError
        If *basis* is not one of ``'x'``, ``'y'``, ``'z'``.
    KeyError
        If *basis* is not found in PROJECTOR_PLUS (same condition).
    """
    basis = basis.strip().lower()
    if basis not in PROJECTOR_PLUS:
        raise ValueError(
            f"Unknown basis {basis!r}. Supported: {list(PROJECTOR_PLUS)}"
        )
    sv = np.asarray(statevector, dtype=complex)
    Pp = PROJECTOR_PLUS[basis]
    Pm = PROJECTOR_MINUS[basis]
    p_plus  = float(np.real(sv.conj() @ Pp @ sv))
    p_minus = float(np.real(sv.conj() @ Pm @ sv))
    # Numerical clamp to [0,1]
    p_plus  = float(np.clip(p_plus,  0.0, 1.0))
    p_minus = float(np.clip(p_minus, 0.0, 1.0))
    return p_plus, p_minus


def measure_eigenstate(
    state: PauliEigenstate,
    basis: str | None = None,
) -> Tuple[float, float]:
    """Measure a ``PauliEigenstate`` in a given basis.

    Defaults to the eigenstate's own basis when *basis* is ``None``.

    Parameters
    ----------
    state : PauliEigenstate
        State to measure.
    basis : str or None
        Target basis (``'x'``, ``'y'``, ``'z'``).  Defaults to
        ``state.basis``.

    Returns
    -------
    tuple[float, float]
        ``(p_plus, p_minus)`` probabilities.
    """
    target_basis = state.basis if basis is None else basis.strip().lower()
    return projective_measurement_probs(state.statevector, target_basis)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_statevector_norm(
    statevector: np.ndarray,
    atol: float = 1e-9,
) -> bool:
    """Return True when ||psi|| == 1 within *atol*."""
    norm = float(np.linalg.norm(statevector))
    ok = abs(norm - 1.0) <= atol
    if not ok:
        logger.warning("Statevector norm %.10f deviates from 1.0", norm)
    return ok


def validate_eigenvalue_equation(
    state: PauliEigenstate,
    atol: float = 1e-9,
) -> bool:
    """Return True when sigma|psi> == eigenvalue * |psi> within *atol*.

    Checks the defining eigenvalue equation for the eigenstate's own basis.
    """
    sigma = PAULI_MATRICES[state.basis]
    lhs = sigma @ state.statevector
    rhs = state.eigenvalue * state.statevector
    ok = bool(np.allclose(lhs, rhs, atol=atol))
    if not ok:
        logger.warning(
            "Eigenvalue equation fails for %s (basis=%s, ev=%+d)",
            state.label, state.basis, state.eigenvalue,
        )
    return ok
