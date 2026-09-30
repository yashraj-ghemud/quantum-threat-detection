"""
quantum/bell_states.py
======================
Bell state preparation, simulation, and entanglement validation.

Phase 1 — SIH26141 | Blockchain & Cybersecurity.

All four maximally-entangled two-qubit Bell states are implemented:

    |Φ+⟩ = (|00⟩ + |11⟩) / √2   — circuit: H(0), CX(0→1)
    |Φ-⟩ = (|00⟩ - |11⟩) / √2   — circuit: H(0), Z(0), CX(0→1)
    |Ψ+⟩ = (|01⟩ + |10⟩) / √2   — circuit: X(1), H(0), CX(0→1)
    |Ψ-⟩ = (|01⟩ - |10⟩) / √2   — circuit: X(1), H(0), Z(0), CX(0→1)

Entanglement is validated through Pauli two-qubit correlators ⟨XX⟩, ⟨YY⟩,
⟨ZZ⟩ computed from exact statevectors (no AI/ML).

Expected correlators per state
-------------------------------
    |Φ+⟩ : ⟨XX⟩ = +1,  ⟨YY⟩ = −1,  ⟨ZZ⟩ = +1
    |Φ-⟩ : ⟨XX⟩ = −1,  ⟨YY⟩ = +1,  ⟨ZZ⟩ = +1
    |Ψ+⟩ : ⟨XX⟩ = +1,  ⟨YY⟩ = +1,  ⟨ZZ⟩ = −1
    |Ψ-⟩ : ⟨XX⟩ = −1,  ⟨YY⟩ = −1,  ⟨ZZ⟩ = −1

No AI/ML libraries are used in this project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import DensityMatrix, SparsePauliOp, Statevector
from qiskit_aer import AerSimulator

from utils.config import ConfigLoader
from utils.logger import get_logger
from utils.reproducibility import set_seed

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "BellLabel",
    "BellValidationResult",
    "BELL_CORRELATORS",
    "prepare_phi_plus",
    "prepare_phi_minus",
    "prepare_psi_plus",
    "prepare_psi_minus",
    "prepare_bell_state",
    "simulate_bell_state",
    "get_statevector",
    "get_density_matrix",
    "compute_pauli_correlations",
    "identify_bell_state",
    "validate_bell_state",
    "validate_all_bell_states",
]

# ---------------------------------------------------------------------------
# Type aliases and constants
# ---------------------------------------------------------------------------

#: Canonical names for the four Bell states.
BellLabel = str  # Literal["phi+", "phi-", "psi+", "psi-"]

#: Pauli correlator signature: (XX, YY, ZZ)
_Correlators = Tuple[float, float, float]

#: Numerical tolerance for floating-point comparisons.
_ATOL: float = 1e-6

#: Expected (XX, YY, ZZ) correlators for each Bell state.
#: Signs are exact for ideal (noiseless) statevectors.
BELL_CORRELATORS: Dict[BellLabel, _Correlators] = {
    "phi+": (+1.0, -1.0, +1.0),
    "phi-": (-1.0, +1.0, +1.0),
    "psi+": (+1.0, +1.0, -1.0),
    "psi-": (-1.0, -1.0, -1.0),
}

# Pre-built SparsePauliOp objects (qubit ordering: q0 is rightmost in Qiskit).
_XX = SparsePauliOp("XX")
_YY = SparsePauliOp("YY")
_ZZ = SparsePauliOp("ZZ")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BellValidationResult:
    """Result of a single Bell-state entanglement validation run.

    Attributes
    ----------
    label:
        The Bell state that was *expected* / prepared (e.g. ``'phi+'``).
    detected:
        The Bell state *identified* from Pauli correlators.
    xx:
        Measured ⟨XX⟩ correlator.
    yy:
        Measured ⟨YY⟩ correlator.
    zz:
        Measured ⟨ZZ⟩ correlator.
    norm:
        Euclidean norm of the statevector (should be ≈ 1.0).
    passed:
        ``True`` when *detected* == *label* and all correlators match
        expected values within tolerance.
    message:
        Human-readable summary.
    counts:
        Shot-count dictionary from Aer simulation (optional; ``{}`` when
        statevector-only mode is used).
    """

    label: BellLabel
    detected: BellLabel
    xx: float
    yy: float
    zz: float
    norm: float
    passed: bool
    message: str
    counts: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Circuit preparation — one function per Bell state
# ---------------------------------------------------------------------------

def prepare_phi_plus() -> QuantumCircuit:
    """Build the |Φ+⟩ Bell state circuit (no measurement).

    Circuit: H(0) → CX(0, 1)

    Returns
    -------
    qiskit.QuantumCircuit
        Two-qubit circuit producing |Φ+⟩ = (|00⟩ + |11⟩) / √2.
    """
    qc = QuantumCircuit(2, name="Phi+")
    qc.h(0)
    qc.cx(0, 1)
    logger.debug("Prepared |Phi+> circuit: %d qubits, depth %d", qc.num_qubits, qc.depth())
    return qc


def prepare_phi_minus() -> QuantumCircuit:
    """Build the |Φ-⟩ Bell state circuit (no measurement).

    Circuit: H(0) → Z(0) → CX(0, 1)

    Returns
    -------
    qiskit.QuantumCircuit
        Two-qubit circuit producing |Φ-⟩ = (|00⟩ − |11⟩) / √2.
    """
    qc = QuantumCircuit(2, name="Phi-")
    qc.h(0)
    qc.z(0)
    qc.cx(0, 1)
    logger.debug("Prepared |Phi-> circuit: %d qubits, depth %d", qc.num_qubits, qc.depth())
    return qc


def prepare_psi_plus() -> QuantumCircuit:
    """Build the |Ψ+⟩ Bell state circuit (no measurement).

    Circuit: X(1) → H(0) → CX(0, 1)

    Returns
    -------
    qiskit.QuantumCircuit
        Two-qubit circuit producing |Ψ+⟩ = (|01⟩ + |10⟩) / √2.
    """
    qc = QuantumCircuit(2, name="Psi+")
    qc.x(1)
    qc.h(0)
    qc.cx(0, 1)
    logger.debug("Prepared |Psi+> circuit: %d qubits, depth %d", qc.num_qubits, qc.depth())
    return qc


def prepare_psi_minus() -> QuantumCircuit:
    """Build the |Ψ-⟩ Bell state circuit (no measurement).

    Circuit: X(1) → H(0) → Z(0) → CX(0, 1)

    Returns
    -------
    qiskit.QuantumCircuit
        Two-qubit circuit producing |Ψ-⟩ = (|01⟩ − |10⟩) / √2.
    """
    qc = QuantumCircuit(2, name="Psi-")
    qc.x(1)
    qc.h(0)
    qc.z(0)
    qc.cx(0, 1)
    logger.debug("Prepared |Psi-> circuit: %d qubits, depth %d", qc.num_qubits, qc.depth())
    return qc


# ---------------------------------------------------------------------------
# Dispatch helper
# ---------------------------------------------------------------------------

#: Internal mapping from label to builder function.
_BUILDERS: Dict[BellLabel, object] = {
    "phi+": prepare_phi_plus,
    "phi-": prepare_phi_minus,
    "psi+": prepare_psi_plus,
    "psi-": prepare_psi_minus,
}


def prepare_bell_state(label: BellLabel) -> QuantumCircuit:
    """Dispatch to the correct Bell-state circuit builder by label.

    Parameters
    ----------
    label:
        One of ``'phi+'``, ``'phi-'``, ``'psi+'``, ``'psi-'``
        (case-insensitive).

    Returns
    -------
    qiskit.QuantumCircuit
        Unmeasured two-qubit Bell-state circuit.

    Raises
    ------
    ValueError
        If *label* is not a recognised Bell-state name.
    """
    key = label.strip().lower()
    builder = _BUILDERS.get(key)
    if builder is None:
        raise ValueError(
            f"Unknown Bell state label {label!r}. "
            f"Choose from {sorted(_BUILDERS)}."
        )
    return builder()  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------

def simulate_bell_state(
    circuit: QuantumCircuit,
    shots: int = 1024,
    seed: int | None = None,
    backend: AerSimulator | None = None,
) -> Dict[str, int]:
    """Run a Bell-state circuit on Qiskit Aer and return shot-count results.

    The circuit is automatically augmented with ``measure_all()`` before
    execution so the caller can pass measurement-free preparation circuits.

    Parameters
    ----------
    circuit:
        Unmeasured Bell-state circuit (2 qubits).
    shots:
        Number of measurement shots.
    seed:
        Simulator seed for reproducibility.  Defaults to ``ConfigLoader``
        ``random_seed`` (42).
    backend:
        Optional pre-constructed ``AerSimulator``.  A fresh instance is
        created if ``None``.

    Returns
    -------
    dict[str, int]
        Measurement outcome string → count, e.g. ``{'00': 512, '11': 512}``.
    """
    if seed is None:
        cfg = ConfigLoader()
        seed = cfg.random_seed
    if backend is None:
        backend = AerSimulator()

    # Clone so we don't mutate the caller's circuit
    measured_qc = circuit.copy()
    measured_qc.measure_all()

    compiled = transpile(measured_qc, backend)
    job = backend.run(compiled, shots=shots, seed_simulator=seed)
    result = job.result()
    counts: Dict[str, int] = result.get_counts()
    logger.debug(
        "Simulated %s: shots=%d, outcomes=%s", circuit.name, shots, counts
    )
    return counts


def get_statevector(circuit: QuantumCircuit) -> Statevector:
    """Compute the exact statevector of a Bell-state circuit.

    Uses ``qiskit.quantum_info.Statevector`` for noiseless exact simulation
    (no shot noise).

    Parameters
    ----------
    circuit:
        Unmeasured quantum circuit.

    Returns
    -------
    qiskit.quantum_info.Statevector
        Normalised statevector.
    """
    sv = Statevector(circuit)
    logger.debug("Statevector for %s: %s", circuit.name, sv.data)
    return sv


def get_density_matrix(circuit: QuantumCircuit) -> DensityMatrix:
    """Compute the exact density matrix of a Bell-state circuit.

    Parameters
    ----------
    circuit:
        Unmeasured quantum circuit.

    Returns
    -------
    qiskit.quantum_info.DensityMatrix
        Density matrix ρ with Tr(ρ) ≈ 1.
    """
    dm = DensityMatrix(circuit)
    logger.debug(
        "DensityMatrix for %s: trace=%.6f", circuit.name, np.trace(dm.data).real
    )
    return dm


# ---------------------------------------------------------------------------
# Pauli correlation computation
# ---------------------------------------------------------------------------

def compute_pauli_correlations(
    circuit: QuantumCircuit,
) -> Tuple[float, float, float]:
    """Compute ⟨XX⟩, ⟨YY⟩, ⟨ZZ⟩ two-qubit Pauli correlators.

    Uses the exact ``Statevector`` (no shot noise) so results are
    deterministic and comparable against integer ±1 expectations.

    Parameters
    ----------
    circuit:
        Unmeasured two-qubit circuit.

    Returns
    -------
    tuple[float, float, float]
        ``(xx, yy, zz)`` correlator values in the range ``[−1, +1]``.
    """
    sv = get_statevector(circuit)
    xx = float(sv.expectation_value(_XX).real)
    yy = float(sv.expectation_value(_YY).real)
    zz = float(sv.expectation_value(_ZZ).real)
    logger.debug(
        "Pauli correlators for %s: XX=%.6f  YY=%.6f  ZZ=%.6f",
        circuit.name, xx, yy, zz,
    )
    return xx, yy, zz


# ---------------------------------------------------------------------------
# Bell-state identification
# ---------------------------------------------------------------------------

def identify_bell_state(
    xx: float,
    yy: float,
    zz: float,
    atol: float = _ATOL,
) -> BellLabel:
    """Identify the Bell state from ⟨XX⟩, ⟨YY⟩, ⟨ZZ⟩ correlators.

    Compares against the known signatures in ``BELL_CORRELATORS`` using
    Euclidean distance with tolerance *atol*.

    Parameters
    ----------
    xx:
        Measured ⟨XX⟩ correlator.
    yy:
        Measured ⟨YY⟩ correlator.
    zz:
        Measured ⟨ZZ⟩ correlator.
    atol:
        Absolute tolerance for matching each component.

    Returns
    -------
    str
        Identified Bell-state label, e.g. ``'phi+'``.

    Raises
    ------
    ValueError
        If the correlators do not match any known Bell state within *atol*.
    """
    observed = np.array([xx, yy, zz])
    for label, expected in BELL_CORRELATORS.items():
        if np.allclose(observed, expected, atol=atol):
            logger.debug(
                "Identified Bell state: %s  (XX=%.4f YY=%.4f ZZ=%.4f)",
                label, xx, yy, zz,
            )
            return label
    raise ValueError(
        f"Cannot identify Bell state from correlators "
        f"XX={xx:.6f}, YY={yy:.6f}, ZZ={zz:.6f} "
        f"(tolerance={atol})."
    )


# ---------------------------------------------------------------------------
# Full validation pipeline
# ---------------------------------------------------------------------------

def validate_bell_state(
    label: BellLabel,
    shots: int = 1024,
    seed: int | None = None,
    atol: float = _ATOL,
    backend: AerSimulator | None = None,
) -> BellValidationResult:
    """Validate a single Bell state: prepare → simulate → correlate → identify.

    Steps
    -----
    1. Build the circuit for *label*.
    2. Run Aer shot simulation to obtain measurement counts.
    3. Compute exact Pauli correlators from ``Statevector``.
    4. Check statevector normalisation (‖ψ‖ ≈ 1).
    5. Identify the Bell state from correlators.
    6. Assert detected label matches expected *label*.

    Parameters
    ----------
    label:
        Expected Bell state (``'phi+'`` / ``'phi-'`` / ``'psi+'`` / ``'psi-'``).
    shots:
        Number of measurement shots for the Aer simulation.
    seed:
        Simulator seed.  Defaults to project ``random_seed`` (42).
    atol:
        Absolute tolerance for correlator comparison.
    backend:
        Optional pre-constructed ``AerSimulator``.

    Returns
    -------
    BellValidationResult
        Complete validation result including PASS/FAIL status.
    """
    if seed is None:
        cfg = ConfigLoader()
        seed = cfg.random_seed

    logger.info("Validating Bell state |%s>  (shots=%d, seed=%d)", label, shots, seed)
    set_seed(seed)

    # 1. Build circuit
    qc = prepare_bell_state(label)

    # 2. Shot simulation
    counts = simulate_bell_state(qc, shots=shots, seed=seed, backend=backend)

    # 3. Exact Pauli correlators
    xx, yy, zz = compute_pauli_correlations(qc)

    # 4. Normalisation check
    sv = get_statevector(qc)
    norm = float(np.linalg.norm(sv.data))

    # 5. Identify state
    try:
        detected = identify_bell_state(xx, yy, zz, atol=atol)
    except ValueError as exc:
        result = BellValidationResult(
            label=label,
            detected="unknown",
            xx=xx, yy=yy, zz=zz,
            norm=norm,
            passed=False,
            message=str(exc),
            counts=counts,
        )
        logger.warning("FAIL: %s", result.message)
        return result

    # 6. Cross-check
    norm_ok = abs(norm - 1.0) <= atol
    state_ok = detected == label.strip().lower()
    exp_xx, exp_yy, exp_zz = BELL_CORRELATORS[label.strip().lower()]
    corr_ok = (
        abs(xx - exp_xx) <= atol
        and abs(yy - exp_yy) <= atol
        and abs(zz - exp_zz) <= atol
    )
    passed = norm_ok and state_ok and corr_ok

    if passed:
        msg = (
            f"PASS | |{label}>  detected={detected} | "
            f"XX={xx:+.4f} YY={yy:+.4f} ZZ={zz:+.4f} | norm={norm:.6f}"
        )
        logger.info(msg)
    else:
        reasons: list[str] = []
        if not norm_ok:
            reasons.append(f"norm={norm:.6f} (expected 1.0 ±{atol})")
        if not state_ok:
            reasons.append(f"detected={detected!r} ≠ expected={label!r}")
        if not corr_ok:
            reasons.append(
                f"correlators ({xx:+.4f},{yy:+.4f},{zz:+.4f}) "
                f"do not match expected ({exp_xx:+.1f},{exp_yy:+.1f},{exp_zz:+.1f})"
            )
        msg = "FAIL | |{}> — {}".format(label, "; ".join(reasons))
        logger.warning(msg)

    return BellValidationResult(
        label=label,
        detected=detected,
        xx=xx, yy=yy, zz=zz,
        norm=norm,
        passed=passed,
        message=msg,
        counts=counts,
    )


def validate_all_bell_states(
    shots: int = 1024,
    seed: int | None = None,
    atol: float = _ATOL,
    backend: AerSimulator | None = None,
) -> Dict[BellLabel, BellValidationResult]:
    """Validate all four Bell states in a single call.

    Parameters
    ----------
    shots:
        Number of measurement shots per state.
    seed:
        Simulator seed for reproducibility.
    atol:
        Absolute tolerance for correlator comparison.
    backend:
        Optional shared ``AerSimulator`` instance.

    Returns
    -------
    dict[BellLabel, BellValidationResult]
        Mapping from Bell-state label to its validation result.
    """
    if backend is None:
        backend = AerSimulator()

    results: Dict[BellLabel, BellValidationResult] = {}
    for label in BELL_CORRELATORS:
        results[label] = validate_bell_state(
            label, shots=shots, seed=seed, atol=atol, backend=backend
        )
    return results
