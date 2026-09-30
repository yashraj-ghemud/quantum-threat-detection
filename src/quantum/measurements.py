"""
quantum/measurements.py
=======================
Projective measurement in the X, Y, and Z Pauli bases.

Phase 1/3 -- SIH26141 | Blockchain & Cybersecurity.

A quantum computer measures only in the computational (Z) basis, so
measuring an observable P in {X, Y, Z} means rotating P's eigenbasis onto
the Z axis first, measuring, and reading the outcome back:

    Z-basis : measure directly                    (no rotation)
    X-basis : apply H                             (H Z H  = X)
    Y-basis : apply S-dagger then H               (H S' Z S H = Y)

Outcome bit b in {0, 1} maps to Pauli eigenvalue ``(-1)**b``, i.e.
``0 -> +1`` and ``1 -> -1``.

Two measurement paths are provided, and they answer different questions:

``measure_statevector`` / ``measure_density_matrix``
    *Analytic* Born-rule probabilities, computed by projector expectation
    values. Exact, no sampling error. Use when the ideal distribution is
    wanted.

``sample_basis_counts`` / ``measure_all_bases``
    *Sampled* shot statistics from Qiskit Aer, returning real counts.
    These carry genuine finite-shot noise -- the counts fluctuate around
    the analytic probabilities by ~1/sqrt(shots), exactly as a real
    experiment would. Use for anything that models an actual measurement
    run, because the finite-shot spread is itself part of the physics the
    detector has to distinguish from an attack.

Nothing here fabricates an outcome: sampled results come from Aer's
simulation of the rotated circuit.

No AI/ML libraries are used.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from utils.config import ConfigLoader
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "BASES",
    "BasisCounts",
    "measure_in_basis",
    "add_x_basis_measurement",
    "add_y_basis_measurement",
    "add_z_basis_measurement",
    "measure_statevector",
    "measure_density_matrix",
    "sample_basis_counts",
    "measure_all_bases",
    "expectation_value",
    "counts_to_probabilities",
    "shot_noise_sigma",
]

#: The three Pauli measurement bases.
BASES: Tuple[str, str, str] = ("x", "y", "z")


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BasisCounts:
    """Sampled measurement statistics for one basis.

    Attributes
    ----------
    basis : str
        Measurement basis: ``'x'``, ``'y'`` or ``'z'``.
    counts : dict[str, int]
        Raw outcome counts keyed by bit string ``'0'`` / ``'1'``.
    shots : int
        Total shots requested.
    p0, p1 : float
        Empirical probabilities of outcome 0 (+1) and 1 (-1).
    expectation : float
        Empirical ``<P> = p0 - p1`` in [-1, 1].
    analytic_p0 : float or None
        Exact Born-rule probability of outcome 0, when known.
    """

    basis: str
    counts: Dict[str, int]
    shots: int
    p0: float
    p1: float
    expectation: float
    analytic_p0: Optional[float] = None

    @property
    def sampling_error(self) -> Optional[float]:
        """|empirical p0 - analytic p0|, when the analytic value is known."""
        if self.analytic_p0 is None:
            return None
        return abs(self.p0 - self.analytic_p0)

    def as_dict(self) -> Dict[str, float]:
        """Return ``{'0': p0, '1': p1}`` -- the distribution for this basis."""
        return {"0": self.p0, "1": self.p1}

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"BasisCounts({self.basis.upper()}: "
            f"0={self.p0:.4f} 1={self.p1:.4f} "
            f"<P>={self.expectation:+.4f} shots={self.shots})"
        )


# ---------------------------------------------------------------------------
# Circuit construction
# ---------------------------------------------------------------------------

def add_z_basis_measurement(circuit, qubit: int = 0, clbit: int = 0):
    """Measure *qubit* in the Z basis (no rotation required)."""
    circuit.measure(qubit, clbit)
    return circuit


def add_x_basis_measurement(circuit, qubit: int = 0, clbit: int = 0):
    """Measure *qubit* in the X basis.

    Applies ``H`` to map the X eigenbasis onto Z: ``H X H = Z``, so
    ``|+> -> |0>`` and ``|-> -> |1>``.
    """
    circuit.h(qubit)
    circuit.measure(qubit, clbit)
    return circuit


def add_y_basis_measurement(circuit, qubit: int = 0, clbit: int = 0):
    """Measure *qubit* in the Y basis.

    Applies ``S-dagger`` then ``H``. ``S-dagger`` maps the Y eigenbasis
    onto X (``|+i> -> |+>``), and ``H`` then maps X onto Z, so
    ``|+i> -> |0>`` and ``|-i> -> |1>``.
    """
    circuit.sdg(qubit)
    circuit.h(qubit)
    circuit.measure(qubit, clbit)
    return circuit


def measure_in_basis(circuit, basis: str, qubit: int = 0, clbit: int = 0):
    """Append basis-rotation gates and a measurement for *basis*.

    Parameters
    ----------
    circuit : qiskit.QuantumCircuit
        Circuit to extend in place.
    basis : str
        ``'x'``, ``'y'`` or ``'z'`` (case-insensitive).
    qubit, clbit : int
        Qubit to measure and classical bit to store the outcome.

    Returns
    -------
    qiskit.QuantumCircuit
        The same circuit, extended.

    Raises
    ------
    ValueError
        If *basis* is not a recognised Pauli basis.
    """
    b = basis.strip().lower()
    if b == "z":
        return add_z_basis_measurement(circuit, qubit, clbit)
    if b == "x":
        return add_x_basis_measurement(circuit, qubit, clbit)
    if b == "y":
        return add_y_basis_measurement(circuit, qubit, clbit)
    raise ValueError(f"Unknown basis {basis!r}. Supported: {list(BASES)}")


# ---------------------------------------------------------------------------
# Analytic (exact) measurement
# ---------------------------------------------------------------------------

def measure_statevector(statevector, basis: str) -> Tuple[float, float]:
    """Exact Born-rule probabilities for a pure state in *basis*.

    ``P(+1) = <psi|P+|psi>`` with ``P+ = (I + sigma)/2``.

    Returns
    -------
    tuple[float, float]
        ``(p0, p1)`` for outcomes +1 and -1, summing to 1.
    """
    from qds.pauli_states import projective_measurement_probs

    return projective_measurement_probs(statevector, basis)


def measure_density_matrix(rho, basis: str) -> Tuple[float, float]:
    """Exact Born-rule probabilities for a (possibly mixed) state.

    ``P(+1) = Tr(rho P+)``. This is the mixed-state generalisation of
    :func:`measure_statevector` and is the correct path for a state that
    has come through a noisy channel.

    Parameters
    ----------
    rho : DensityMatrix or array-like, shape (2, 2)
        Single-qubit density matrix.
    basis : str
        ``'x'``, ``'y'`` or ``'z'``.

    Returns
    -------
    tuple[float, float]
        ``(p0, p1)``.
    """
    from qds.pauli_states import PROJECTOR_MINUS, PROJECTOR_PLUS

    b = basis.strip().lower()
    if b not in PROJECTOR_PLUS:
        raise ValueError(f"Unknown basis {basis!r}. Supported: {list(BASES)}")

    mat = np.asarray(getattr(rho, "data", rho), dtype=complex)
    p0 = float(np.real(np.trace(mat @ PROJECTOR_PLUS[b])))
    p1 = float(np.real(np.trace(mat @ PROJECTOR_MINUS[b])))
    return float(np.clip(p0, 0.0, 1.0)), float(np.clip(p1, 0.0, 1.0))


def expectation_value(state, basis: str) -> float:
    """Return ``<P> = P(+1) - P(-1)`` in [-1, 1] for *state*.

    Accepts either a statevector (shape ``(2,)``) or a density matrix
    (shape ``(2, 2)``).
    """
    arr = np.asarray(getattr(state, "data", state), dtype=complex)
    if arr.ndim == 1:
        p0, p1 = measure_statevector(arr, basis)
    else:
        p0, p1 = measure_density_matrix(arr, basis)
    return p0 - p1


# ---------------------------------------------------------------------------
# Sampled (finite-shot) measurement
# ---------------------------------------------------------------------------

def shot_noise_sigma(p: float, shots: int) -> float:
    """Standard deviation of an estimated probability from *shots* samples.

    ``sigma = sqrt(p(1-p)/shots)``. Useful for deciding whether an observed
    deviation is explainable by finite sampling alone.
    """
    if shots <= 0:
        return 0.0
    return float(np.sqrt(max(p * (1.0 - p), 0.0) / shots))


def counts_to_probabilities(counts: Dict[str, int], shots: int) -> Tuple[float, float]:
    """Convert raw Aer counts to ``(p0, p1)``."""
    if shots <= 0:
        return 0.0, 0.0
    n0 = int(counts.get("0", 0))
    n1 = int(counts.get("1", 0))
    total = n0 + n1
    if total == 0:
        return 0.0, 0.0
    return n0 / total, n1 / total


def sample_basis_counts(
    statevector,
    basis: str,
    shots: int = 1024,
    seed: Optional[int] = None,
) -> BasisCounts:
    """Measure a single-qubit state *shots* times in *basis* on Aer.

    Builds a one-qubit circuit that initialises *statevector*, applies the
    basis rotation, and measures; then runs it on ``AerSimulator``. The
    returned counts are genuine simulated samples, not analytic values
    rounded to integers -- they carry finite-shot fluctuation of order
    ``1/sqrt(shots)``.

    Parameters
    ----------
    statevector : array-like, shape (2,)
        State to measure.
    basis : str
        ``'x'``, ``'y'`` or ``'z'``.
    shots : int
        Number of repetitions.
    seed : int or None
        Simulator seed for reproducibility. Defaults to the project seed.

    Returns
    -------
    BasisCounts
        Sampled statistics, with the analytic probability attached for
        comparison.

    Raises
    ------
    ValueError
        If *basis* is unknown or *shots* < 1.
    """
    from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, transpile
    from qiskit_aer import AerSimulator

    b = basis.strip().lower()
    if b not in BASES:
        raise ValueError(f"Unknown basis {basis!r}. Supported: {list(BASES)}")
    if shots < 1:
        raise ValueError(f"shots must be >= 1, got {shots}.")

    if seed is None:
        seed = ConfigLoader().random_seed

    sv = np.asarray(getattr(statevector, "data", statevector), dtype=complex).reshape(2)
    norm = float(np.linalg.norm(sv))
    if norm > 0:
        sv = sv / norm

    qr = QuantumRegister(1, "q")
    cr = ClassicalRegister(1, "c")
    qc = QuantumCircuit(qr, cr, name=f"measure_{b}")
    qc.initialize(sv, 0)
    measure_in_basis(qc, b, qubit=0, clbit=0)

    backend = AerSimulator()
    compiled = transpile(qc, backend)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = backend.run(compiled, shots=shots, seed_simulator=seed).result()

    raw = result.get_counts()
    counts = {"0": int(raw.get("0", 0)), "1": int(raw.get("1", 0))}
    p0, p1 = counts_to_probabilities(counts, shots)
    analytic_p0, _ = measure_statevector(sv, b)

    return BasisCounts(
        basis=b,
        counts=counts,
        shots=shots,
        p0=p0,
        p1=p1,
        expectation=p0 - p1,
        analytic_p0=analytic_p0,
    )


def measure_all_bases(
    statevector,
    shots: int = 1024,
    seed: Optional[int] = None,
) -> Dict[str, BasisCounts]:
    """Measure a state in all three Pauli bases.

    Each basis needs its own set of shots: measuring collapses the state,
    so X, Y and Z statistics cannot come from the same copies. Fresh
    preparations are used per basis, matching how tomography works in
    practice.

    Parameters
    ----------
    statevector : array-like, shape (2,)
        State to characterise.
    shots : int
        Shots per basis.
    seed : int or None
        Base seed; each basis uses a distinct derived seed so the three
        runs are independent rather than correlated.

    Returns
    -------
    dict[str, BasisCounts]
        Keyed by ``'x'``, ``'y'``, ``'z'``.
    """
    if seed is None:
        seed = ConfigLoader().random_seed

    return {
        b: sample_basis_counts(statevector, b, shots=shots, seed=seed + i)
        for i, b in enumerate(BASES)
    }
