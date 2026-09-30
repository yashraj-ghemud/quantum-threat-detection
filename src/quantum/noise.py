"""
quantum/noise.py
================
Quantum channel noise models and noisy teleportation fidelity analysis.

Phase 2.5 -- SIH26141 | Blockchain & Cybersecurity.

Four noise channels are modelled and applied to the *quantum communication
stage* of the teleportation protocol -- the Bell-pair creation (CX on
qubits 1 and 2) and Bob's correction gates (single-qubit on qubit 2).
Alice's state-preparation and measurement stages are kept noiseless so
the noise source is isolated to the channel.

Noise models
------------
bit_flip          : X error with probability p on channel qubits
phase_flip        : Z error with probability p on channel qubits
depolarizing      : Uniform Pauli {I,X,Y,Z} depolarizing on channel qubits
amplitude_damping : Energy-relaxation (|1> -> |0>) on channel qubits

Fidelity sweep
--------------
``sweep_noise_fidelity`` runs the teleportation for every combination of
noise type, noise strength, and input state, returning a tidy
``pandas.DataFrame``.

No AI/ML is used anywhere in this module.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from qiskit import transpile
from qiskit.quantum_info import DensityMatrix, state_fidelity
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (
    NoiseModel,
    amplitude_damping_error,
    depolarizing_error,
    pauli_error,
    phase_damping_error,
)

from quantum.teleportation import (
    STANDARD_STATES,
    build_teleportation_circuit,
    ideal_density_matrix,
    prepare_input_state,
)
from utils.config import ConfigLoader
from utils.logger import get_logger
from utils.reproducibility import set_seed

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "NoiseType",
    "NoiseResult",
    "NOISE_STRENGTHS",
    "NOISE_TYPES",
    "CHANNEL_GATES_1Q",
    "CHANNEL_GATES_2Q",
    "build_noise_model",
    "run_noisy_teleportation",
    "sweep_noise_fidelity",
    "results_to_dataframe",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Canonical noise-type identifiers.
NoiseType = str  # Literal["bit_flip","phase_flip","depolarizing","amplitude_damping"]

#: Standard noise-strength sweep points.
NOISE_STRENGTHS: Tuple[float, ...] = (0.00, 0.01, 0.05, 0.10, 0.20, 0.30)

#: Supported noise type labels.
NOISE_TYPES: Tuple[NoiseType, ...] = (
    "bit_flip",
    "phase_flip",
    "depolarizing",
    "amplitude_damping",
)

# Channel qubit indices in the 3-qubit teleportation circuit:
#   q[0] = Alice input (noiseless)
#   q[1] = Alice's Bell-pair half  (channel start)
#   q[2] = Bob's qubit             (channel end)
_CHANNEL_Q1 = 1   # Alice's entangled qubit
_CHANNEL_Q2 = 2   # Bob's qubit

#: Single-qubit gate names that appear on channel qubits after transpilation.
CHANNEL_GATES_1Q: Tuple[str, ...] = ("x", "z", "id", "sx", "rz", "h")

#: Two-qubit gate names on the channel (Bell-pair CX).
CHANNEL_GATES_2Q: Tuple[str, ...] = ("cx",)

#: Absolute tolerance for the p=0 baseline fidelity check.
_BASELINE_ATOL: float = 1e-6


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class NoiseResult:
    """Result of a single noisy teleportation run.

    Attributes
    ----------
    noise_type : str
        One of the four noise-type identifiers.
    p : float
        Noise strength parameter in [0, 1].
    state_name : str
        Human-readable label for the input state (e.g. ``'|+>'``).
    theta : float
        Polar angle of the input state (radians).
    phi : float
        Azimuthal angle of the input state (radians).
    fidelity : float
        F(rho_Bob, |psi><psi|).  Ideal noiseless value is 1.0.
    bob_density_matrix : DensityMatrix
        Bob's recovered 2x2 density matrix.
    shots : int
        Number of Aer shots used.
    seed : int
        Simulator seed used.
    """

    noise_type: NoiseType
    p: float
    state_name: str
    theta: float
    phi: float
    fidelity: float
    bob_density_matrix: DensityMatrix
    shots: int
    seed: int


# ---------------------------------------------------------------------------
# Noise model construction
# ---------------------------------------------------------------------------

def build_noise_model(
    noise_type: NoiseType,
    p: float,
) -> NoiseModel:
    """Build a channel-targeted ``NoiseModel`` for the teleportation circuit.

    Noise is applied only to the quantum *channel* qubits (q[1] and q[2])
    — the qubits that form the shared Bell pair and carry the teleported
    state across the channel.  Alice's input qubit (q[0]) is kept noiseless
    so noise is isolated to the transmission stage.

    Noise application
    -----------------
    Single-qubit gates on q[1] and q[2]:
        ``x``, ``z``, ``id``, ``sx``, ``rz``, ``h``
    Two-qubit CX on (q[1], q[2]) for depolarizing only.

    Parameters
    ----------
    noise_type : str
        One of ``'bit_flip'``, ``'phase_flip'``, ``'depolarizing'``,
        ``'amplitude_damping'``.
    p : float
        Noise probability / damping parameter in [0, 1].

    Returns
    -------
    qiskit_aer.noise.NoiseModel
        Configured noise model.  Returns an *empty* model when p == 0
        so the noiseless baseline is exact.

    Raises
    ------
    ValueError
        If ``noise_type`` is not in ``NOISE_TYPES`` or p is out of [0, 1].
    """
    if noise_type not in NOISE_TYPES:
        raise ValueError(
            f"Unknown noise type {noise_type!r}. "
            f"Supported: {NOISE_TYPES}"
        )
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"Noise probability p must be in [0,1], got {p}.")

    noise_model = NoiseModel()

    # p=0 -> empty model (exact noiseless simulation)
    if p == 0.0:
        logger.debug("build_noise_model: p=0 -> empty model (noiseless)")
        return noise_model

    # Build the 1-qubit error channel
    if noise_type == "bit_flip":
        error_1q = pauli_error([("X", p), ("I", 1.0 - p)])
    elif noise_type == "phase_flip":
        error_1q = pauli_error([("Z", p), ("I", 1.0 - p)])
    elif noise_type == "depolarizing":
        error_1q = depolarizing_error(p, 1)
    elif noise_type == "amplitude_damping":
        error_1q = amplitude_damping_error(p)
    else:  # pragma: no cover
        raise ValueError(noise_type)

    # Apply single-qubit error to channel gates on both channel qubits
    for qubit in (_CHANNEL_Q1, _CHANNEL_Q2):
        for gate in CHANNEL_GATES_1Q:
            noise_model.add_quantum_error(error_1q, [gate], [qubit])

    # For depolarizing: also add 2-qubit error on the Bell-pair CX gate
    if noise_type == "depolarizing":
        # Clamp 2-qubit p so it stays in valid range (4^2-1 denominator)
        p_2q = min(p, 1.0 - 1e-9)
        error_2q = depolarizing_error(p_2q, 2)
        noise_model.add_quantum_error(
            error_2q, list(CHANNEL_GATES_2Q), [_CHANNEL_Q1, _CHANNEL_Q2]
        )

    logger.debug(
        "build_noise_model: type=%s  p=%.4f  basis_gates=%s",
        noise_type, p, noise_model.basis_gates,
    )
    return noise_model


# ---------------------------------------------------------------------------
# Single noisy teleportation run
# ---------------------------------------------------------------------------

def run_noisy_teleportation(
    noise_type: NoiseType,
    p: float,
    theta: float,
    phi: float,
    state_name: str = "",
    shots: int = 4096,
    seed: Optional[int] = None,
) -> NoiseResult:
    """Run the full teleportation protocol under a specified noise channel.

    Builds the noise model, transpiles the teleportation circuit against
    ``AerSimulator(method='density_matrix')``, extracts Bob's density
    matrix, and computes fidelity against the ideal input state.

    Parameters
    ----------
    noise_type : str
        Noise channel identifier.
    p : float
        Noise strength in [0, 1].
    theta : float
        Polar angle of input state (radians).
    phi : float
        Azimuthal angle of input state (radians).
    state_name : str
        Human-readable label (auto-generated from theta/phi if empty).
    shots : int
        Number of Aer simulation shots.
    seed : int or None
        Simulator seed.  Defaults to project ``random_seed`` (42).

    Returns
    -------
    NoiseResult
        Complete result including fidelity and Bob's density matrix.
    """
    if seed is None:
        cfg = ConfigLoader()
        seed = cfg.random_seed
    if not state_name:
        state_name = f"(th={theta:.3f},ph={phi:.3f})"

    logger.debug(
        "run_noisy_teleportation: %s p=%.4f state=%s shots=%d seed=%d",
        noise_type, p, state_name, shots, seed,
    )

    noise_model = build_noise_model(noise_type, p)
    backend = AerSimulator(method="density_matrix", noise_model=noise_model)

    qc = build_teleportation_circuit(theta, phi)
    compiled = transpile(qc, backend)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = backend.run(compiled, shots=shots, seed_simulator=seed).result()

    bob_dm: DensityMatrix = result.data()["bob"]
    target_dm = ideal_density_matrix(theta, phi)
    fidelity = float(state_fidelity(bob_dm, target_dm).real)

    logger.debug(
        "  -> F=%.8f  (noise=%s p=%.4f state=%s)",
        fidelity, noise_type, p, state_name,
    )
    return NoiseResult(
        noise_type=noise_type,
        p=p,
        state_name=state_name,
        theta=theta,
        phi=phi,
        fidelity=fidelity,
        bob_density_matrix=bob_dm,
        shots=shots,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Full parameter sweep
# ---------------------------------------------------------------------------

def sweep_noise_fidelity(
    noise_types: Sequence[NoiseType] = NOISE_TYPES,
    noise_strengths: Sequence[float] = NOISE_STRENGTHS,
    states: Sequence[Tuple[str, float, float]] = STANDARD_STATES,
    shots: int = 4096,
    seed: Optional[int] = None,
) -> List[NoiseResult]:
    """Sweep all combinations of noise type, strength, and input state.

    Parameters
    ----------
    noise_types : sequence of str
        Noise type identifiers to sweep.
    noise_strengths : sequence of float
        Noise probability values to sweep.
    states : sequence of (name, theta, phi)
        Input states to evaluate.  Defaults to ``STANDARD_STATES``.
    shots : int
        Aer shots per combination.
    seed : int or None
        Simulator seed for reproducibility.

    Returns
    -------
    list[NoiseResult]
        Flat list of all results; length = len(noise_types) *
        len(noise_strengths) * len(states).
    """
    if seed is None:
        cfg = ConfigLoader()
        seed = cfg.random_seed

    results: List[NoiseResult] = []
    total = len(noise_types) * len(noise_strengths) * len(states)
    done = 0

    for noise_type in noise_types:
        for p in noise_strengths:
            for state_name, theta, phi in states:
                r = run_noisy_teleportation(
                    noise_type=noise_type,
                    p=p,
                    theta=theta,
                    phi=phi,
                    state_name=state_name,
                    shots=shots,
                    seed=seed,
                )
                results.append(r)
                done += 1
                logger.info(
                    "[%3d/%d] %s p=%.2f %s -> F=%.6f",
                    done, total, noise_type, p, state_name, r.fidelity,
                )
    return results


# ---------------------------------------------------------------------------
# DataFrame conversion
# ---------------------------------------------------------------------------

def results_to_dataframe(results: List[NoiseResult]) -> pd.DataFrame:
    """Convert a list of ``NoiseResult`` objects to a tidy pandas DataFrame.

    Columns
    -------
    noise_type, p, state_name, theta, phi, fidelity, shots, seed

    Parameters
    ----------
    results : list[NoiseResult]
        Output of ``sweep_noise_fidelity``.

    Returns
    -------
    pandas.DataFrame
        Tidy long-format DataFrame sorted by (noise_type, p, state_name).
    """
    rows = [
        {
            "noise_type":  r.noise_type,
            "p":           r.p,
            "state_name":  r.state_name,
            "theta":       r.theta,
            "phi":         r.phi,
            "fidelity":    r.fidelity,
            "shots":       r.shots,
            "seed":        r.seed,
        }
        for r in results
    ]
    if not rows:
        return pd.DataFrame(
            columns=["noise_type", "p", "state_name", "theta",
                     "phi", "fidelity", "shots", "seed"]
        )
    df = pd.DataFrame(rows)
    df = df.sort_values(["noise_type", "p", "state_name"]).reset_index(drop=True)
    return df
