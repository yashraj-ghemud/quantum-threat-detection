"""
quantum/teleportation.py
========================
Quantum teleportation protocol — Phase 2.
SIH26141 | Blockchain & Cybersecurity.

Implements the standard three-qubit quantum teleportation protocol using
Qiskit and Qiskit Aer density-matrix simulation:

    Qubit layout
    ------------
    q[0]  Alice's input qubit  — carries |ψ⟩ = cos(θ/2)|0⟩ + e^{iφ}sin(θ/2)|1⟩
    q[1]  Alice's half of the shared Bell pair
    q[2]  Bob's qubit          — receives the teleported state after correction

    Protocol steps
    --------------
    1. Prepare |ψ⟩ on q[0] via Ry(θ) · Rz(φ).
    2. Create |Φ+⟩ Bell pair on q[1], q[2] (H → CX).
    3. Alice's Bell-basis measurement: CX(q[0]→q[1]) → H(q[0]) → measure q[0], q[1].
    4. Classical feed-forward corrections on Bob's qubit q[2]:
           if c[1] == 1  →  X(q[2])
           if c[0] == 1  →  Z(q[2])
    5. Extract Bob's density matrix via Aer ``save_density_matrix``.
    6. Compute fidelity against the ideal input state.

Fidelity is computed analytically as F(ρ_Bob, |ψ⟩⟨ψ|) using
``qiskit.quantum_info.state_fidelity`` — no AI/ML used.

No noise is modelled in Phase 2; that is reserved for Phase 2.5.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Dict, Sequence, Tuple

import numpy as np
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, transpile
from qiskit.quantum_info import DensityMatrix, Statevector, state_fidelity
from qiskit_aer import AerSimulator

from utils.config import ConfigLoader
from utils.logger import get_logger
from utils.reproducibility import set_seed

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "TeleportationResult",
    "STANDARD_STATES",
    "prepare_input_state",
    "build_teleportation_circuit",
    "extract_bob_density_matrix",
    "ideal_density_matrix",
    "calculate_teleportation_fidelity",
    "teleport_state",
    "validate_teleportation",
    "validate_all_standard_states",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Numerical tolerance for fidelity comparisons.
_FIDELITY_ATOL: float = 1e-6

#: Required fidelity threshold for PASS status.
FIDELITY_THRESHOLD: float = 0.999_999

#: Six standard single-qubit test states as (name, θ, φ).
#: |ψ⟩ = cos(θ/2)|0⟩ + e^{iφ}sin(θ/2)|1⟩
STANDARD_STATES: Tuple[Tuple[str, float, float], ...] = (
    ("|0>",  0.0,           0.0),
    ("|1>",  float(np.pi),  0.0),
    ("|+>",  float(np.pi / 2), 0.0),
    ("|->",  float(np.pi / 2), float(np.pi)),
    ("|+i>", float(np.pi / 2), float(np.pi / 2)),
    ("|-i>", float(np.pi / 2), float(3 * np.pi / 2)),
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class TeleportationResult:
    """Complete result of a single teleportation validation run.

    Attributes
    ----------
    name:
        Human-readable label for the input state (e.g. ``'|+>'``).
    theta:
        Polar angle θ of the input state (radians).
    phi:
        Azimuthal angle φ of the input state (radians).
    fidelity:
        F(ρ_Bob, |ψ⟩⟨ψ|) — ideal is 1.0.
    passed:
        ``True`` when fidelity ≥ ``FIDELITY_THRESHOLD``.
    input_statevector:
        Exact input statevector [α, β] as a complex NumPy array.
    bob_density_matrix:
        Bob's recovered ``DensityMatrix`` after feed-forward corrections.
    shots:
        Number of Aer shots used.
    seed:
        Simulator seed used.
    message:
        Human-readable PASS/FAIL summary line.
    """

    name: str
    theta: float
    phi: float
    fidelity: float
    passed: bool
    input_statevector: np.ndarray
    bob_density_matrix: DensityMatrix
    shots: int
    seed: int
    message: str = field(default="")


# ---------------------------------------------------------------------------
# State preparation
# ---------------------------------------------------------------------------

def prepare_input_state(theta: float, phi: float) -> np.ndarray:
    """Compute the exact input statevector for given Bloch-sphere angles.

    The state is:

        |ψ⟩ = cos(θ/2)|0⟩ + e^{iφ}sin(θ/2)|1⟩

    Parameters
    ----------
    theta:
        Polar angle θ ∈ [0, π] (radians).
    phi:
        Azimuthal angle φ ∈ [0, 2π) (radians).

    Returns
    -------
    numpy.ndarray, shape (2,), dtype complex128
        Normalised statevector [α, β].
    """
    alpha = np.cos(theta / 2.0)
    beta = np.exp(1j * phi) * np.sin(theta / 2.0)
    sv = np.array([alpha, beta], dtype=complex)
    # Numerical safety: re-normalise
    sv /= np.linalg.norm(sv) if np.linalg.norm(sv) > 0 else 1.0
    return sv


# ---------------------------------------------------------------------------
# Circuit construction
# ---------------------------------------------------------------------------

def build_teleportation_circuit(
    theta: float,
    phi: float,
    *,
    add_barriers: bool = True,
) -> QuantumCircuit:
    """Build the complete 3-qubit quantum teleportation circuit.

    Layout
    ------
    q[0]  : Alice's input qubit — prepared as |ψ⟩ via Ry(θ)·Rz(φ)
    q[1]  : Alice's Bell-pair qubit
    q[2]  : Bob's qubit (receives the teleported state)
    c[0]  : Alice's measurement result for q[0]
    c[1]  : Alice's measurement result for q[1]

    The circuit ends with ``save_density_matrix(qubits=[2], label='bob')``
    so that Aer's density-matrix simulator captures Bob's reduced state
    after all classical corrections are applied.

    Parameters
    ----------
    theta:
        Polar angle θ for the input state (radians).
    phi:
        Azimuthal angle φ for the input state (radians).
    add_barriers:
        Insert ``barrier()`` instructions between logical stages for
        readability and to prevent compiler optimisations across stages.

    Returns
    -------
    qiskit.QuantumCircuit
        Three-qubit, two-classical-bit teleportation circuit with
        ``save_density_matrix`` appended.
    """
    qr = QuantumRegister(3, "q")
    cr = ClassicalRegister(2, "c")
    qc = QuantumCircuit(qr, cr, name="teleport")

    # --- Stage 1: Prepare input state on q[0] ---
    qc.ry(theta, qr[0])
    qc.rz(phi,   qr[0])
    if add_barriers:
        qc.barrier()

    # --- Stage 2: Create |Φ+⟩ Bell pair on q[1], q[2] ---
    qc.h(qr[1])
    qc.cx(qr[1], qr[2])
    if add_barriers:
        qc.barrier()

    # --- Stage 3: Alice's Bell-basis operations ---
    qc.cx(qr[0], qr[1])
    qc.h(qr[0])
    if add_barriers:
        qc.barrier()

    # --- Stage 4: Alice measures her two qubits ---
    qc.measure(qr[0], cr[0])
    qc.measure(qr[1], cr[1])
    if add_barriers:
        qc.barrier()

    # --- Stage 5: Bob applies classical feed-forward corrections ---
    with qc.if_test((cr[1], 1)):
        qc.x(qr[2])
    with qc.if_test((cr[0], 1)):
        qc.z(qr[2])
    if add_barriers:
        qc.barrier()

    # --- Stage 6: Save Bob's density matrix for extraction ---
    qc.save_density_matrix(qubits=[qr[2]], label="bob")

    logger.debug(
        "Built teleportation circuit: theta=%.4f phi=%.4f depth=%d",
        theta, phi, qc.depth(),
    )
    return qc


# ---------------------------------------------------------------------------
# Bob state extraction
# ---------------------------------------------------------------------------

def extract_bob_density_matrix(
    circuit: QuantumCircuit,
    shots: int = 4096,
    seed: int | None = None,
    backend: AerSimulator | None = None,
) -> DensityMatrix:
    """Run the teleportation circuit and extract Bob's density matrix.

    Uses ``AerSimulator(method='density_matrix')`` with classical
    feed-forward support.  The ``save_density_matrix`` instruction in the
    circuit causes Aer to return the averaged reduced density matrix of
    Bob's qubit across all measurement branches.

    Parameters
    ----------
    circuit:
        Teleportation circuit produced by ``build_teleportation_circuit``.
        Must contain a ``save_density_matrix`` instruction labelled ``'bob'``.
    shots:
        Number of simulation shots (more shots → better averaging).
    seed:
        Simulator seed.  Defaults to project ``random_seed`` (42).
    backend:
        Optional pre-constructed ``AerSimulator``.  A new density-matrix
        backend is created when ``None``.

    Returns
    -------
    qiskit.quantum_info.DensityMatrix
        Bob's reduced 2×2 density matrix after corrections.

    Raises
    ------
    KeyError
        If the result data does not contain the ``'bob'`` key.
    RuntimeError
        If the Aer job fails.
    """
    if seed is None:
        cfg = ConfigLoader()
        seed = cfg.random_seed
    if backend is None:
        backend = AerSimulator(method="density_matrix")

    compiled = transpile(circuit, backend)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        job = backend.run(compiled, shots=shots, seed_simulator=seed)
        result = job.result()

    if not result.success:
        raise RuntimeError(
            f"Aer job failed: {result.status}"
        )

    data = result.data()
    if "bob" not in data:
        raise KeyError(
            "Result data missing 'bob' key. "
            "Ensure the circuit contains save_density_matrix(label='bob')."
        )

    bob_dm: DensityMatrix = data["bob"]
    logger.debug(
        "Extracted Bob DM: trace=%.6f",
        float(np.trace(np.asarray(bob_dm)).real),
    )
    return bob_dm


# ---------------------------------------------------------------------------
# Ideal density matrix helper
# ---------------------------------------------------------------------------

def ideal_density_matrix(theta: float, phi: float) -> DensityMatrix:
    """Build the ideal target density matrix |ψ⟩⟨ψ| for the input state.

    Parameters
    ----------
    theta:
        Polar angle θ (radians).
    phi:
        Azimuthal angle φ (radians).

    Returns
    -------
    qiskit.quantum_info.DensityMatrix
        Pure-state density matrix ρ = |ψ⟩⟨ψ|.
    """
    sv = prepare_input_state(theta, phi)
    rho = np.outer(sv, sv.conj())
    return DensityMatrix(rho)


# ---------------------------------------------------------------------------
# Fidelity calculation
# ---------------------------------------------------------------------------

def calculate_teleportation_fidelity(
    theta: float,
    phi: float,
    shots: int = 4096,
    seed: int | None = None,
    backend: AerSimulator | None = None,
) -> float:
    """Calculate the teleportation fidelity F(ρ_Bob, |ψ⟩⟨ψ|) for a given state.

    This is the primary metric for Phase 2.  Ideal (noiseless) fidelity
    is 1.0; values < 1 indicate imperfection (due to shot noise at finite
    shots).

    Parameters
    ----------
    theta:
        Polar angle θ of the input state (radians).
    phi:
        Azimuthal angle φ of the input state (radians).
    shots:
        Number of Aer shots.
    seed:
        Simulator seed.
    backend:
        Optional pre-constructed ``AerSimulator``.

    Returns
    -------
    float
        Fidelity value in [0, 1].
    """
    qc = build_teleportation_circuit(theta, phi)
    bob_dm = extract_bob_density_matrix(qc, shots=shots, seed=seed, backend=backend)
    target_dm = ideal_density_matrix(theta, phi)
    fidelity = float(state_fidelity(bob_dm, target_dm).real)
    logger.debug(
        "Fidelity for theta=%.4f phi=%.4f : F=%.8f",
        theta, phi, fidelity,
    )
    return fidelity


# ---------------------------------------------------------------------------
# Full teleportation run with result
# ---------------------------------------------------------------------------

def teleport_state(
    theta: float,
    phi: float,
    name: str = "",
    shots: int = 4096,
    seed: int | None = None,
    backend: AerSimulator | None = None,
) -> TeleportationResult:
    """Execute and record a complete single-state teleportation run.

    Steps
    -----
    1. Compute input statevector.
    2. Build the circuit.
    3. Extract Bob's density matrix.
    4. Compute fidelity.
    5. Determine PASS/FAIL.

    Parameters
    ----------
    theta:
        Polar angle θ (radians).
    phi:
        Azimuthal angle φ (radians).
    name:
        Human-readable state label (e.g. ``'|+>'``).  Auto-generated if empty.
    shots:
        Aer simulation shots.
    seed:
        Simulator seed.
    backend:
        Optional pre-constructed ``AerSimulator``.

    Returns
    -------
    TeleportationResult
        Full result including fidelity, PASS/FAIL, and both state matrices.
    """
    if seed is None:
        cfg = ConfigLoader()
        seed = cfg.random_seed
    if not name:
        name = f"state(th={theta:.3f},ph={phi:.3f})"

    logger.info(
        "Teleporting %s  theta=%.4f phi=%.4f  shots=%d seed=%d",
        name, theta, phi, shots, seed,
    )
    set_seed(seed)

    input_sv = prepare_input_state(theta, phi)
    qc = build_teleportation_circuit(theta, phi)
    bob_dm = extract_bob_density_matrix(qc, shots=shots, seed=seed, backend=backend)
    target_dm = ideal_density_matrix(theta, phi)
    fidelity = float(state_fidelity(bob_dm, target_dm).real)
    passed = fidelity >= FIDELITY_THRESHOLD

    if passed:
        msg = (
            f"PASS | {name}  F={fidelity:.8f} >= {FIDELITY_THRESHOLD}"
        )
    else:
        msg = (
            f"FAIL | {name}  F={fidelity:.8f} < {FIDELITY_THRESHOLD}"
        )
    logger.info(msg)

    return TeleportationResult(
        name=name,
        theta=theta,
        phi=phi,
        fidelity=fidelity,
        passed=passed,
        input_statevector=input_sv,
        bob_density_matrix=bob_dm,
        shots=shots,
        seed=seed,
        message=msg,
    )


# ---------------------------------------------------------------------------
# Bulk validation
# ---------------------------------------------------------------------------

def validate_teleportation(
    states: Sequence[Tuple[str, float, float]] | None = None,
    shots: int = 4096,
    seed: int | None = None,
    backend: AerSimulator | None = None,
) -> Dict[str, TeleportationResult]:
    """Validate teleportation for a list of (name, θ, φ) states.

    Parameters
    ----------
    states:
        Sequence of ``(name, theta, phi)`` tuples.  Defaults to
        ``STANDARD_STATES`` when ``None``.
    shots:
        Aer simulation shots per state.
    seed:
        Simulator seed.
    backend:
        Optional shared ``AerSimulator``.

    Returns
    -------
    dict[str, TeleportationResult]
        Mapping from state name to its ``TeleportationResult``.
    """
    if states is None:
        states = STANDARD_STATES
    if backend is None:
        backend = AerSimulator(method="density_matrix")

    results: Dict[str, TeleportationResult] = {}
    for name, theta, phi in states:
        results[name] = teleport_state(
            theta, phi, name=name,
            shots=shots, seed=seed, backend=backend,
        )
    return results


def validate_all_standard_states(
    shots: int = 4096,
    seed: int | None = None,
    backend: AerSimulator | None = None,
) -> Dict[str, TeleportationResult]:
    """Validate teleportation for all six standard Bloch-sphere states.

    States validated: |0⟩, |1⟩, |+⟩, |−⟩, |+i⟩, |−i⟩.

    Parameters
    ----------
    shots:
        Aer simulation shots per state.
    seed:
        Simulator seed for reproducibility.
    backend:
        Optional shared ``AerSimulator``.

    Returns
    -------
    dict[str, TeleportationResult]
        Results for all six standard states.
    """
    return validate_teleportation(
        states=STANDARD_STATES,
        shots=shots,
        seed=seed,
        backend=backend,
    )
