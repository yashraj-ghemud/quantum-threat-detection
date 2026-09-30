"""
tests/quantum/test_teleportation.py
=====================================
Phase 2 -- Quantum Teleportation & Fidelity test suite.
SIH26141 | Blockchain & Cybersecurity.

Test categories
---------------
1. Input state preparation     -- statevector shape, norm, amplitude correctness
2. Circuit construction        -- qubit/bit count, stages, gate presence, save_dm
3. Bob state extraction        -- DensityMatrix returned, shape, trace, Hermitian
4. Ideal density matrix        -- pure-state properties, matches input
5. Fidelity calculation        -- all six standard states >= FIDELITY_THRESHOLD
6. Full teleport_state()       -- TeleportationResult fields, PASS status
7. Bulk validation             -- validate_all_standard_states completeness
8. Determinism                 -- same seed -> same fidelity
9. Edge cases & error handling -- unknown label, bad circuit, arbitrary angles

All tests are deterministic (seed=42).  No AI/ML used.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

# Ensure src/ on sys.path (mirrors pyproject.toml pythonpath = ["src"])
_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
for _p in (_SRC, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

warnings.filterwarnings("ignore", category=DeprecationWarning)

from qiskit import QuantumCircuit
from qiskit.quantum_info import DensityMatrix, state_fidelity
from qiskit_aer import AerSimulator

from quantum.teleportation import (
    FIDELITY_THRESHOLD,
    STANDARD_STATES,
    TeleportationResult,
    build_teleportation_circuit,
    calculate_teleportation_fidelity,
    extract_bob_density_matrix,
    ideal_density_matrix,
    prepare_input_state,
    teleport_state,
    validate_all_standard_states,
    validate_teleportation,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------
_SEED: int = 42
_SHOTS: int = 4096
_ATOL: float = 1e-6          # tolerance for statevector / matrix checks
_FIDELITY_ATOL: float = 1e-6 # tolerance around fidelity comparisons


# ===========================================================================
# 1. INPUT STATE PREPARATION
# ===========================================================================

class TestInputStatePreparation:
    """Verify prepare_input_state produces correct statevectors."""

    @pytest.mark.parametrize("theta,phi", [
        (0.0,          0.0),
        (np.pi,        0.0),
        (np.pi / 2,    0.0),
        (np.pi / 2,    np.pi),
        (np.pi / 2,    np.pi / 2),
        (np.pi / 2,    3 * np.pi / 2),
    ])
    def test_returns_length_two_array(self, theta, phi) -> None:
        """prepare_input_state returns a length-2 complex array."""
        sv = prepare_input_state(theta, phi)
        assert sv.shape == (2,)
        assert sv.dtype == complex

    @pytest.mark.parametrize("theta,phi", [
        (0.0,       0.0),
        (np.pi,     0.0),
        (np.pi / 2, 0.0),
        (np.pi / 2, np.pi),
    ])
    def test_norm_is_one(self, theta, phi) -> None:
        """Statevector norm is 1.0."""
        sv = prepare_input_state(theta, phi)
        assert abs(np.linalg.norm(sv) - 1.0) <= _ATOL

    def test_zero_state(self) -> None:
        """|0> -> alpha=1, beta=0."""
        sv = prepare_input_state(0.0, 0.0)
        assert abs(sv[0] - 1.0) <= _ATOL
        assert abs(sv[1])       <= _ATOL

    def test_one_state(self) -> None:
        """|1> -> alpha=0, beta=1."""
        sv = prepare_input_state(float(np.pi), 0.0)
        assert abs(sv[0])       <= _ATOL
        assert abs(abs(sv[1]) - 1.0) <= _ATOL

    def test_plus_state(self) -> None:
        """|+> -> alpha=beta=1/sqrt(2)."""
        sv = prepare_input_state(float(np.pi / 2), 0.0)
        inv_sqrt2 = 1.0 / np.sqrt(2)
        assert abs(abs(sv[0]) - inv_sqrt2) <= _ATOL
        assert abs(abs(sv[1]) - inv_sqrt2) <= _ATOL

    def test_minus_state(self) -> None:
        """|-> -> alpha=1/sqrt(2), beta=-1/sqrt(2)."""
        sv = prepare_input_state(float(np.pi / 2), float(np.pi))
        inv_sqrt2 = 1.0 / np.sqrt(2)
        assert abs(abs(sv[0]) - inv_sqrt2) <= _ATOL
        assert abs(abs(sv[1]) - inv_sqrt2) <= _ATOL
        # Relative phase must be negative real
        assert np.real(sv[0] * np.conj(sv[1])) < 0

    def test_plus_i_state(self) -> None:
        """|+i> -> beta has phase +i."""
        sv = prepare_input_state(float(np.pi / 2), float(np.pi / 2))
        inv_sqrt2 = 1.0 / np.sqrt(2)
        assert abs(abs(sv[0]) - inv_sqrt2) <= _ATOL
        assert abs(abs(sv[1]) - inv_sqrt2) <= _ATOL
        # beta = e^{i*pi/2} / sqrt(2) = i/sqrt(2)
        expected_beta = 1j / np.sqrt(2)
        assert abs(sv[1] - expected_beta) <= _ATOL

    def test_minus_i_state(self) -> None:
        """|-i> -> beta has phase -i."""
        sv = prepare_input_state(float(np.pi / 2), float(3 * np.pi / 2))
        expected_beta = -1j / np.sqrt(2)
        assert abs(sv[1] - expected_beta) <= _ATOL

    @pytest.mark.parametrize("theta", [0.1, 0.5, 1.0, 1.5, 2.0, 2.5])
    def test_arbitrary_theta_norm(self, theta) -> None:
        """Norm is 1.0 for arbitrary theta values."""
        sv = prepare_input_state(theta, 1.23)
        assert abs(np.linalg.norm(sv) - 1.0) <= _ATOL

    def test_bloch_sphere_formula(self) -> None:
        """Amplitude magnitudes match cos(th/2) and sin(th/2)."""
        theta, phi = 0.8, 1.2
        sv = prepare_input_state(theta, phi)
        assert abs(abs(sv[0]) - np.cos(theta / 2)) <= _ATOL
        assert abs(abs(sv[1]) - np.sin(theta / 2)) <= _ATOL


# ===========================================================================
# 2. CIRCUIT CONSTRUCTION
# ===========================================================================

class TestCircuitConstruction:
    """Verify build_teleportation_circuit returns a correct circuit."""

    def test_returns_quantum_circuit(self) -> None:
        """build_teleportation_circuit returns a QuantumCircuit."""
        qc = build_teleportation_circuit(np.pi / 2, 0.0)
        assert isinstance(qc, QuantumCircuit)

    def test_three_qubits(self) -> None:
        """Circuit has exactly 3 qubits."""
        qc = build_teleportation_circuit(0.5, 0.3)
        assert qc.num_qubits == 3

    def test_two_classical_bits(self) -> None:
        """Circuit has exactly 2 classical bits."""
        qc = build_teleportation_circuit(0.5, 0.3)
        assert qc.num_clbits == 2

    def test_circuit_name(self) -> None:
        """Circuit name is 'teleport'."""
        qc = build_teleportation_circuit(0.0, 0.0)
        assert qc.name == "teleport"

    def test_non_zero_depth(self) -> None:
        """Circuit depth > 0."""
        qc = build_teleportation_circuit(1.0, 0.5)
        assert qc.depth() > 0

    def test_contains_ry_gate(self) -> None:
        """Circuit contains Ry gate for state preparation."""
        qc = build_teleportation_circuit(0.7, 0.3)
        gate_names = [i.operation.name for i in qc.data]
        assert "ry" in gate_names

    def test_contains_rz_gate(self) -> None:
        """Circuit contains Rz gate for state preparation."""
        qc = build_teleportation_circuit(0.7, 0.3)
        gate_names = [i.operation.name for i in qc.data]
        assert "rz" in gate_names

    def test_contains_h_gate(self) -> None:
        """Circuit contains H gate (Bell pair + Alice's basis rotation)."""
        qc = build_teleportation_circuit(0.5, 0.0)
        gate_names = [i.operation.name for i in qc.data]
        assert "h" in gate_names

    def test_contains_cx_gate(self) -> None:
        """Circuit contains CX gate."""
        qc = build_teleportation_circuit(0.5, 0.0)
        gate_names = [i.operation.name for i in qc.data]
        assert "cx" in gate_names

    def test_contains_measure(self) -> None:
        """Circuit contains measurement operations."""
        qc = build_teleportation_circuit(0.5, 0.0)
        gate_names = [i.operation.name for i in qc.data]
        assert "measure" in gate_names

    def test_contains_save_density_matrix(self) -> None:
        """Circuit contains save_density_matrix instruction."""
        qc = build_teleportation_circuit(0.5, 0.0)
        gate_names = [i.operation.name for i in qc.data]
        assert any("save_density_matrix" in n for n in gate_names)

    def test_no_barriers_when_disabled(self) -> None:
        """No barrier instructions when add_barriers=False."""
        qc = build_teleportation_circuit(0.5, 0.0, add_barriers=False)
        gate_names = [i.operation.name for i in qc.data]
        assert "barrier" not in gate_names

    def test_barriers_present_by_default(self) -> None:
        """Barrier instructions present with default add_barriers=True."""
        qc = build_teleportation_circuit(0.5, 0.0, add_barriers=True)
        gate_names = [i.operation.name for i in qc.data]
        assert "barrier" in gate_names

    @pytest.mark.parametrize("theta,phi", [
        (0.0, 0.0), (np.pi, 0.0), (np.pi / 2, np.pi / 2),
    ])
    def test_circuit_consistent_across_states(self, theta, phi) -> None:
        """All state inputs produce a 3-qubit, 2-clbit circuit."""
        qc = build_teleportation_circuit(theta, phi)
        assert qc.num_qubits == 3
        assert qc.num_clbits == 2


# ===========================================================================
# 3. BOB STATE EXTRACTION
# ===========================================================================

class TestBobStateExtraction:
    """Verify extract_bob_density_matrix returns a valid DensityMatrix."""

    @pytest.fixture(scope="class")
    @classmethod
    def backend(cls) -> AerSimulator:
        """Shared density-matrix AerSimulator."""
        return AerSimulator(method="density_matrix")

    @pytest.mark.parametrize("theta,phi", [
        (0.0,       0.0),
        (np.pi,     0.0),
        (np.pi / 2, 0.0),
    ])
    def test_returns_density_matrix(self, backend, theta, phi) -> None:
        """extract_bob_density_matrix returns a DensityMatrix."""
        qc = build_teleportation_circuit(theta, phi)
        dm = extract_bob_density_matrix(qc, shots=256, seed=_SEED, backend=backend)
        assert isinstance(dm, DensityMatrix)

    @pytest.mark.parametrize("theta,phi", [
        (0.0,       0.0),
        (np.pi / 2, np.pi / 4),
    ])
    def test_density_matrix_shape(self, backend, theta, phi) -> None:
        """Bob's DensityMatrix is 2x2."""
        qc = build_teleportation_circuit(theta, phi)
        dm = extract_bob_density_matrix(qc, shots=256, seed=_SEED, backend=backend)
        assert np.asarray(dm).shape == (2, 2)

    @pytest.mark.parametrize("theta,phi", [
        (0.0,       0.0),
        (np.pi,     0.0),
        (np.pi / 2, 0.0),
    ])
    def test_trace_is_one(self, backend, theta, phi) -> None:
        """Tr(rho_Bob) = 1.0."""
        qc = build_teleportation_circuit(theta, phi)
        dm = extract_bob_density_matrix(qc, shots=_SHOTS, seed=_SEED, backend=backend)
        trace = float(np.trace(np.asarray(dm)).real)
        assert abs(trace - 1.0) <= _ATOL

    @pytest.mark.parametrize("theta,phi", [
        (0.0,       0.0),
        (np.pi / 2, 0.0),
    ])
    def test_density_matrix_hermitian(self, backend, theta, phi) -> None:
        """Bob's DensityMatrix is Hermitian."""
        qc = build_teleportation_circuit(theta, phi)
        dm = extract_bob_density_matrix(qc, shots=_SHOTS, seed=_SEED, backend=backend)
        rho = np.asarray(dm)
        assert np.allclose(rho, rho.conj().T, atol=_ATOL)

    def test_missing_save_dm_raises(self, backend) -> None:
        """extract_bob_density_matrix raises KeyError if 'bob' label absent."""
        qc = QuantumCircuit(3, 2)
        qc.h(0); qc.cx(0, 1)
        qc.measure(0, 0); qc.measure(1, 1)
        with pytest.raises(KeyError, match="bob"):
            extract_bob_density_matrix(qc, shots=64, seed=_SEED, backend=backend)


# ===========================================================================
# 4. IDEAL DENSITY MATRIX
# ===========================================================================

class TestIdealDensityMatrix:
    """Verify ideal_density_matrix builds correct pure-state rho."""

    @pytest.mark.parametrize("theta,phi", [
        (0.0, 0.0), (np.pi, 0.0), (np.pi / 2, 0.0), (0.7, 1.2),
    ])
    def test_trace_is_one(self, theta, phi) -> None:
        """Tr(rho_ideal) = 1.0."""
        dm = ideal_density_matrix(theta, phi)
        assert abs(float(np.trace(np.asarray(dm)).real) - 1.0) <= _ATOL

    @pytest.mark.parametrize("theta,phi", [
        (0.0, 0.0), (np.pi, 0.0), (np.pi / 2, np.pi),
    ])
    def test_pure_state(self, theta, phi) -> None:
        """Tr(rho^2) = 1 for a pure state."""
        rho = np.asarray(ideal_density_matrix(theta, phi))
        tr_rho2 = float(np.trace(rho @ rho).real)
        assert abs(tr_rho2 - 1.0) <= _ATOL

    @pytest.mark.parametrize("theta,phi", [
        (0.0, 0.0), (np.pi / 2, 0.0),
    ])
    def test_hermitian(self, theta, phi) -> None:
        """rho = rho_dagger (Hermitian)."""
        rho = np.asarray(ideal_density_matrix(theta, phi))
        assert np.allclose(rho, rho.conj().T, atol=_ATOL)

    def test_zero_state_dm(self) -> None:
        """|0><0| = [[1,0],[0,0]]."""
        rho = np.asarray(ideal_density_matrix(0.0, 0.0))
        expected = np.array([[1, 0], [0, 0]], dtype=complex)
        assert np.allclose(rho, expected, atol=_ATOL)

    def test_one_state_dm(self) -> None:
        """|1><1| = [[0,0],[0,1]]."""
        rho = np.asarray(ideal_density_matrix(float(np.pi), 0.0))
        expected = np.array([[0, 0], [0, 1]], dtype=complex)
        assert np.allclose(rho, expected, atol=_ATOL)

    def test_plus_state_dm(self) -> None:
        """|+><+| = [[0.5,0.5],[0.5,0.5]]."""
        rho = np.asarray(ideal_density_matrix(float(np.pi / 2), 0.0))
        expected = np.array([[0.5, 0.5], [0.5, 0.5]], dtype=complex)
        assert np.allclose(rho, expected, atol=_ATOL)

    def test_consistent_with_prepare_input_state(self) -> None:
        """ideal_density_matrix matches outer(sv, sv*) from prepare_input_state."""
        theta, phi = 0.9, 1.1
        sv = prepare_input_state(theta, phi)
        expected = np.outer(sv, sv.conj())
        rho = np.asarray(ideal_density_matrix(theta, phi))
        assert np.allclose(rho, expected, atol=_ATOL)


# ===========================================================================
# 5. FIDELITY CALCULATION
# ===========================================================================

class TestFidelityCalculation:
    """Verify calculate_teleportation_fidelity for all standard states."""

    @pytest.fixture(scope="class")
    @classmethod
    def backend(cls) -> AerSimulator:
        """Shared density-matrix AerSimulator."""
        return AerSimulator(method="density_matrix")

    @pytest.mark.parametrize("name,theta,phi", STANDARD_STATES)
    def test_fidelity_above_threshold(self, backend, name, theta, phi) -> None:
        """Fidelity >= FIDELITY_THRESHOLD for all six standard states."""
        f = calculate_teleportation_fidelity(
            theta, phi, shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert f >= FIDELITY_THRESHOLD, (
            f"{name}: F={f:.10f} < threshold={FIDELITY_THRESHOLD}"
        )

    @pytest.mark.parametrize("name,theta,phi", STANDARD_STATES)
    def test_fidelity_at_most_one_plus_tolerance(self, backend, name, theta, phi) -> None:
        """Fidelity <= 1.0 + small numerical tolerance."""
        f = calculate_teleportation_fidelity(
            theta, phi, shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert f <= 1.0 + _FIDELITY_ATOL, (
            f"{name}: F={f:.10f} unexpectedly > 1"
        )

    @pytest.mark.parametrize("name,theta,phi", STANDARD_STATES)
    def test_fidelity_returns_float(self, backend, name, theta, phi) -> None:
        """calculate_teleportation_fidelity returns a Python float."""
        f = calculate_teleportation_fidelity(
            theta, phi, shots=256, seed=_SEED, backend=backend
        )
        assert isinstance(f, float)

    def test_fidelity_zero_state(self, backend) -> None:
        """|0> teleportation fidelity >= 0.999999."""
        f = calculate_teleportation_fidelity(
            0.0, 0.0, shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert f >= FIDELITY_THRESHOLD

    def test_fidelity_one_state(self, backend) -> None:
        """|1> teleportation fidelity >= 0.999999."""
        f = calculate_teleportation_fidelity(
            float(np.pi), 0.0, shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert f >= FIDELITY_THRESHOLD

    def test_fidelity_plus_state(self, backend) -> None:
        """|+> teleportation fidelity >= 0.999999."""
        f = calculate_teleportation_fidelity(
            float(np.pi / 2), 0.0, shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert f >= FIDELITY_THRESHOLD

    def test_fidelity_minus_state(self, backend) -> None:
        """|-> teleportation fidelity >= 0.999999."""
        f = calculate_teleportation_fidelity(
            float(np.pi / 2), float(np.pi), shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert f >= FIDELITY_THRESHOLD

    def test_fidelity_plus_i_state(self, backend) -> None:
        """|+i> teleportation fidelity >= 0.999999."""
        f = calculate_teleportation_fidelity(
            float(np.pi / 2), float(np.pi / 2), shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert f >= FIDELITY_THRESHOLD

    def test_fidelity_minus_i_state(self, backend) -> None:
        """|-i> teleportation fidelity >= 0.999999."""
        f = calculate_teleportation_fidelity(
            float(np.pi / 2), float(3 * np.pi / 2), shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert f >= FIDELITY_THRESHOLD

    @pytest.mark.parametrize("theta,phi", [
        (0.3, 0.7), (1.1, 2.3), (2.0, 4.5), (0.01, 6.0),
    ])
    def test_fidelity_arbitrary_angles(self, backend, theta, phi) -> None:
        """Fidelity >= threshold for arbitrary (theta, phi) angles."""
        f = calculate_teleportation_fidelity(
            theta, phi, shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert f >= FIDELITY_THRESHOLD, (
            f"theta={theta} phi={phi}: F={f:.10f}"
        )


# ===========================================================================
# 6. FULL teleport_state() RESULT
# ===========================================================================

class TestTeleportState:
    """Verify teleport_state returns a fully populated TeleportationResult."""

    @pytest.fixture(scope="class")
    @classmethod
    def backend(cls) -> AerSimulator:
        return AerSimulator(method="density_matrix")

    @pytest.fixture(scope="class")
    @classmethod
    def result_plus(cls, backend) -> TeleportationResult:
        """Shared result for |+> state."""
        return teleport_state(
            float(np.pi / 2), 0.0, name="|+>",
            shots=_SHOTS, seed=_SEED, backend=backend,
        )

    def test_returns_teleportation_result(self, backend) -> None:
        """teleport_state returns a TeleportationResult."""
        r = teleport_state(0.0, 0.0, name="|0>", shots=256, seed=_SEED, backend=backend)
        assert isinstance(r, TeleportationResult)

    def test_result_name(self, result_plus) -> None:
        """result.name matches the provided label."""
        assert result_plus.name == "|+>"

    def test_result_passed(self, result_plus) -> None:
        """result.passed is True for |+>."""
        assert result_plus.passed is True

    def test_result_fidelity_above_threshold(self, result_plus) -> None:
        """result.fidelity >= FIDELITY_THRESHOLD."""
        assert result_plus.fidelity >= FIDELITY_THRESHOLD

    def test_result_fidelity_at_most_one(self, result_plus) -> None:
        """result.fidelity <= 1.0 + tolerance."""
        assert result_plus.fidelity <= 1.0 + _FIDELITY_ATOL

    def test_result_theta_phi_stored(self, result_plus) -> None:
        """result.theta and result.phi match the input."""
        assert abs(result_plus.theta - np.pi / 2) <= _ATOL
        assert abs(result_plus.phi - 0.0) <= _ATOL

    def test_result_input_statevector_shape(self, result_plus) -> None:
        """result.input_statevector has shape (2,)."""
        assert result_plus.input_statevector.shape == (2,)

    def test_result_input_statevector_norm(self, result_plus) -> None:
        """result.input_statevector is normalised."""
        norm = float(np.linalg.norm(result_plus.input_statevector))
        assert abs(norm - 1.0) <= _ATOL

    def test_result_bob_density_matrix_type(self, result_plus) -> None:
        """result.bob_density_matrix is a DensityMatrix."""
        assert isinstance(result_plus.bob_density_matrix, DensityMatrix)

    def test_result_bob_dm_trace(self, result_plus) -> None:
        """Tr(rho_Bob) = 1.0."""
        trace = float(np.trace(np.asarray(result_plus.bob_density_matrix)).real)
        assert abs(trace - 1.0) <= _ATOL

    def test_result_message_is_string(self, result_plus) -> None:
        """result.message is a non-empty string."""
        assert isinstance(result_plus.message, str)
        assert len(result_plus.message) > 0

    def test_result_message_contains_pass(self, result_plus) -> None:
        """result.message contains 'PASS' for a passing result."""
        assert "PASS" in result_plus.message

    def test_result_shots_stored(self, result_plus) -> None:
        """result.shots equals the requested shot count."""
        assert result_plus.shots == _SHOTS

    def test_result_seed_stored(self, result_plus) -> None:
        """result.seed equals the provided seed."""
        assert result_plus.seed == _SEED

    @pytest.mark.parametrize("name,theta,phi", STANDARD_STATES)
    def test_all_standard_states_pass(self, backend, name, theta, phi) -> None:
        """teleport_state returns passed=True for all six standard states."""
        r = teleport_state(
            theta, phi, name=name, shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert r.passed is True, f"{name}: {r.message}"

    def test_auto_generated_name(self, backend) -> None:
        """Name is auto-generated when empty string provided."""
        r = teleport_state(0.5, 0.5, name="", shots=256, seed=_SEED, backend=backend)
        assert len(r.name) > 0
        assert "state" in r.name.lower() or "th=" in r.name


# ===========================================================================
# 7. BULK VALIDATION
# ===========================================================================

class TestBulkValidation:
    """Verify validate_all_standard_states and validate_teleportation."""

    @pytest.fixture(scope="class")
    @classmethod
    def all_results(cls) -> dict:
        """Run validate_all_standard_states once and share."""
        backend = AerSimulator(method="density_matrix")
        return validate_all_standard_states(shots=_SHOTS, seed=_SEED, backend=backend)

    def test_returns_six_results(self, all_results) -> None:
        """validate_all_standard_states returns exactly 6 entries."""
        assert len(all_results) == 6

    def test_all_six_states_present(self, all_results) -> None:
        """All six standard state names are keys in the result dict."""
        expected_names = {s[0] for s in STANDARD_STATES}
        assert set(all_results.keys()) == expected_names

    def test_all_pass(self, all_results) -> None:
        """All six standard states pass validation."""
        failed = [n for n, r in all_results.items() if not r.passed]
        assert failed == [], f"Failed states: {failed}"

    @pytest.mark.parametrize("name", [s[0] for s in STANDARD_STATES])
    def test_fidelity_above_threshold(self, name, all_results) -> None:
        """Each state's fidelity >= FIDELITY_THRESHOLD."""
        r = all_results[name]
        assert r.fidelity >= FIDELITY_THRESHOLD, (
            f"{name}: F={r.fidelity:.10f}"
        )

    @pytest.mark.parametrize("name", [s[0] for s in STANDARD_STATES])
    def test_result_type(self, name, all_results) -> None:
        """Each entry is a TeleportationResult."""
        assert isinstance(all_results[name], TeleportationResult)

    @pytest.mark.parametrize("name", [s[0] for s in STANDARD_STATES])
    def test_bob_dm_trace(self, name, all_results) -> None:
        """Tr(rho_Bob) = 1.0 for each state."""
        rho = np.asarray(all_results[name].bob_density_matrix)
        assert abs(float(np.trace(rho).real) - 1.0) <= _ATOL

    def test_validate_teleportation_custom_list(self) -> None:
        """validate_teleportation accepts a custom state list."""
        custom = [
            ("|0>", 0.0,        0.0),
            ("|1>", float(np.pi), 0.0),
        ]
        backend = AerSimulator(method="density_matrix")
        results = validate_teleportation(
            custom, shots=_SHOTS, seed=_SEED, backend=backend
        )
        assert len(results) == 2
        assert all(r.passed for r in results.values())

    def test_validate_teleportation_uses_standard_states_by_default(self) -> None:
        """validate_teleportation() with no states arg uses STANDARD_STATES."""
        backend = AerSimulator(method="density_matrix")
        results = validate_teleportation(shots=_SHOTS, seed=_SEED, backend=backend)
        assert len(results) == len(STANDARD_STATES)


# ===========================================================================
# 8. DETERMINISM
# ===========================================================================

class TestDeterminism:
    """Verify identical results with the same seed."""

    @pytest.fixture(scope="class")
    @classmethod
    def backend(cls) -> AerSimulator:
        return AerSimulator(method="density_matrix")

    def test_same_seed_same_fidelity(self, backend) -> None:
        """Two runs with same seed return identical fidelity."""
        theta, phi = float(np.pi / 2), float(np.pi / 4)
        f1 = calculate_teleportation_fidelity(
            theta, phi, shots=512, seed=_SEED, backend=backend
        )
        f2 = calculate_teleportation_fidelity(
            theta, phi, shots=512, seed=_SEED, backend=backend
        )
        assert abs(f1 - f2) <= _FIDELITY_ATOL

    def test_same_seed_same_bob_dm(self, backend) -> None:
        """Two runs with same seed produce identical Bob DensityMatrix."""
        theta, phi = 0.5, 1.0
        qc = build_teleportation_circuit(theta, phi)
        dm1 = np.asarray(extract_bob_density_matrix(
            qc, shots=512, seed=_SEED, backend=backend
        ))
        dm2 = np.asarray(extract_bob_density_matrix(
            qc, shots=512, seed=_SEED, backend=backend
        ))
        assert np.allclose(dm1, dm2, atol=_ATOL)

    def test_different_seeds_may_differ(self, backend) -> None:
        """Different seeds can produce different fidelities (shot noise)."""
        theta, phi = float(np.pi / 3), float(np.pi / 5)
        f1 = calculate_teleportation_fidelity(
            theta, phi, shots=16, seed=1, backend=backend
        )
        f2 = calculate_teleportation_fidelity(
            theta, phi, shots=16, seed=99, backend=backend
        )
        # With very few shots the values may differ; both should still be > 0
        assert f1 >= 0.0
        assert f2 >= 0.0


# ===========================================================================
# 9. STANDARD_STATES CONSTANT
# ===========================================================================

class TestStandardStates:
    """Verify the STANDARD_STATES constant is correctly defined."""

    def test_six_entries(self) -> None:
        """STANDARD_STATES has exactly 6 entries."""
        assert len(STANDARD_STATES) == 6

    def test_each_entry_is_three_tuple(self) -> None:
        """Each entry is a (name, theta, phi) triple."""
        for entry in STANDARD_STATES:
            assert len(entry) == 3

    def test_names_are_strings(self) -> None:
        """State names are non-empty strings."""
        for name, _, _ in STANDARD_STATES:
            assert isinstance(name, str) and len(name) > 0

    def test_angles_are_floats(self) -> None:
        """theta and phi are floats."""
        for _, theta, phi in STANDARD_STATES:
            assert isinstance(theta, float)
            assert isinstance(phi, float)

    def test_fidelity_threshold_value(self) -> None:
        """FIDELITY_THRESHOLD is 0.999999."""
        assert abs(FIDELITY_THRESHOLD - 0.999_999) <= 1e-10

    def test_zero_state_angles(self) -> None:
        """|0> has theta=0, phi=0."""
        zero = next(e for e in STANDARD_STATES if e[0] == "|0>")
        assert zero[1] == 0.0 and zero[2] == 0.0

    def test_one_state_theta_is_pi(self) -> None:
        """|1> has theta=pi."""
        one = next(e for e in STANDARD_STATES if e[0] == "|1>")
        assert abs(one[1] - np.pi) <= _ATOL
