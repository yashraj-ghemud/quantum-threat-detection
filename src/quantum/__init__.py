"""
quantum -- Quantum circuit primitives package.

Modules
-------
bell_states   : Preparation, simulation, and validation of all four Bell states (Phase 1)
teleportation : Quantum teleportation protocol with fidelity validation (Phase 2)
noise         : Channel noise models and fidelity-vs-noise sweep (Phase 2.5)
measurements  : Single- and multi-qubit measurement helpers in X/Y/Z bases (Phase 3)
"""

# ----- Phase 1: Bell states -----
from quantum.bell_states import (
    BellLabel,
    BellValidationResult,
    BELL_CORRELATORS,
    prepare_phi_plus,
    prepare_phi_minus,
    prepare_psi_plus,
    prepare_psi_minus,
    prepare_bell_state,
    simulate_bell_state,
    get_statevector,
    get_density_matrix,
    compute_pauli_correlations,
    identify_bell_state,
    validate_bell_state,
    validate_all_bell_states,
)

# ----- Phase 2: Teleportation -----
from quantum.teleportation import (
    TeleportationResult,
    STANDARD_STATES,
    FIDELITY_THRESHOLD,
    prepare_input_state,
    build_teleportation_circuit,
    extract_bob_density_matrix,
    ideal_density_matrix,
    calculate_teleportation_fidelity,
    teleport_state,
    validate_teleportation,
    validate_all_standard_states,
)

# ----- Phase 2.5: Noise -----
from quantum.noise import (
    NoiseType,
    NoiseResult,
    NOISE_STRENGTHS,
    NOISE_TYPES,
    CHANNEL_GATES_1Q,
    CHANNEL_GATES_2Q,
    build_noise_model,
    run_noisy_teleportation,
    sweep_noise_fidelity,
    results_to_dataframe,
)

__all__: list[str] = [
    # Phase 1
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
    # Phase 2
    "TeleportationResult",
    "STANDARD_STATES",
    "FIDELITY_THRESHOLD",
    "prepare_input_state",
    "build_teleportation_circuit",
    "extract_bob_density_matrix",
    "ideal_density_matrix",
    "calculate_teleportation_fidelity",
    "teleport_state",
    "validate_teleportation",
    "validate_all_standard_states",
    # Phase 2.5
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
