"""
tests/quantum/test_bell_states.py
==================================
Phase 1 — Bell State & Entanglement Validation test suite.
SIH26141 | Blockchain & Cybersecurity.

Test categories
---------------
1. Circuit creation       — qubit count, gate presence, circuit name, depth
2. State normalisation    — statevector ‖ψ‖ = 1 for all four Bell states
3. Bell-state amplitude   — exact amplitudes via Statevector
4. Pauli correlations     — ⟨XX⟩, ⟨YY⟩, ⟨ZZ⟩ match expected signatures
5. Bell-state identity    — identify_bell_state dispatches correctly
6. Shot simulation        — AerSimulator counts, correlated outcomes, shot totals
7. Validation pipeline    — validate_bell_state returns PASS for all four states
8. Dispatch helper        — prepare_bell_state + case-insensitivity + bad label
9. Density matrix         — trace ≈ 1, hermitian
10. Error handling        — ValueError on unknown label / bad correlators

All tests are deterministic (seed=42).  No AI/ML libraries used.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure src/ is on sys.path for direct pytest runs in addition to pyproject.toml
_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from quantum.bell_states import (
    BELL_CORRELATORS,
    BellValidationResult,
    compute_pauli_correlations,
    get_density_matrix,
    get_statevector,
    identify_bell_state,
    prepare_bell_state,
    prepare_phi_minus,
    prepare_phi_plus,
    prepare_psi_minus,
    prepare_psi_plus,
    simulate_bell_state,
    validate_all_bell_states,
    validate_bell_state,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_SEED: int = 42
_SHOTS: int = 4096          # generous shot count for statistical stability
_ATOL: float = 1e-6         # tolerance for exact statevector comparisons
_STAT_ATOL: float = 0.05    # tolerance for shot-based statistical checks


# ===========================================================================
# 1. CIRCUIT CREATION
# ===========================================================================

class TestCircuitCreation:
    """Verify that all four circuit builders return correct QuantumCircuit objects."""

    @pytest.mark.parametrize("builder,expected_name", [
        (prepare_phi_plus,  "Phi+"),
        (prepare_phi_minus, "Phi-"),
        (prepare_psi_plus,  "Psi+"),
        (prepare_psi_minus, "Psi-"),
    ])
    def test_returns_quantum_circuit(self, builder, expected_name) -> None:
        """Builder returns a QuantumCircuit instance."""
        qc = builder()
        assert isinstance(qc, QuantumCircuit)

    @pytest.mark.parametrize("builder", [
        prepare_phi_plus, prepare_phi_minus, prepare_psi_plus, prepare_psi_minus,
    ])
    def test_two_qubits(self, builder) -> None:
        """Circuit has exactly 2 qubits."""
        assert builder().num_qubits == 2

    @pytest.mark.parametrize("builder", [
        prepare_phi_plus, prepare_phi_minus, prepare_psi_plus, prepare_psi_minus,
    ])
    def test_no_classical_bits_before_measurement(self, builder) -> None:
        """Preparation circuit has no classical bits (measurement-free)."""
        assert builder().num_clbits == 0

    @pytest.mark.parametrize("builder,expected_name", [
        (prepare_phi_plus,  "Phi+"),
        (prepare_phi_minus, "Phi-"),
        (prepare_psi_plus,  "Psi+"),
        (prepare_psi_minus, "Psi-"),
    ])
    def test_circuit_name(self, builder, expected_name) -> None:
        """Circuit name matches the Bell-state label."""
        assert builder().name == expected_name

    @pytest.mark.parametrize("builder", [
        prepare_phi_plus, prepare_phi_minus, prepare_psi_plus, prepare_psi_minus,
    ])
    def test_non_zero_depth(self, builder) -> None:
        """Circuit depth is at least 1 (gates were added)."""
        assert builder().depth() >= 1

    def test_phi_plus_contains_h_gate(self) -> None:
        """Phi+ circuit contains an H gate."""
        qc = prepare_phi_plus()
        gate_names = [instr.operation.name for instr in qc.data]
        assert "h" in gate_names

    def test_phi_plus_contains_cx_gate(self) -> None:
        """Phi+ circuit contains a CX gate."""
        qc = prepare_phi_plus()
        gate_names = [instr.operation.name for instr in qc.data]
        assert "cx" in gate_names

    def test_phi_minus_contains_z_gate(self) -> None:
        """Phi- circuit contains a Z gate."""
        qc = prepare_phi_minus()
        gate_names = [instr.operation.name for instr in qc.data]
        assert "z" in gate_names

    def test_psi_plus_contains_x_gate(self) -> None:
        """Psi+ circuit contains an X gate."""
        qc = prepare_psi_plus()
        gate_names = [instr.operation.name for instr in qc.data]
        assert "x" in gate_names

    def test_psi_minus_contains_z_gate(self) -> None:
        """Psi- circuit contains a Z gate."""
        qc = prepare_psi_minus()
        gate_names = [instr.operation.name for instr in qc.data]
        assert "z" in gate_names


# ===========================================================================
# 2. STATE NORMALISATION
# ===========================================================================

class TestStateNormalisation:
    """Verify statevector norm = 1 for all Bell states."""

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_statevector_norm_is_one(self, label) -> None:
        """‖ψ‖ = 1.0 within numerical tolerance."""
        qc = prepare_bell_state(label)
        sv = get_statevector(qc)
        norm = float(np.linalg.norm(sv.data))
        assert abs(norm - 1.0) <= _ATOL, (
            f"|{label}> norm={norm:.8f}, expected 1.0 ± {_ATOL}"
        )

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_statevector_length(self, label) -> None:
        """Statevector has 2^2 = 4 amplitudes."""
        qc = prepare_bell_state(label)
        sv = get_statevector(qc)
        assert len(sv.data) == 4

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_only_two_nonzero_amplitudes(self, label) -> None:
        """Bell states have exactly 2 non-zero amplitudes."""
        qc = prepare_bell_state(label)
        sv = get_statevector(qc)
        nonzero = np.count_nonzero(np.abs(sv.data) > _ATOL)
        assert nonzero == 2, (
            f"|{label}> should have 2 non-zero amplitudes, got {nonzero}"
        )


# ===========================================================================
# 3. BELL-STATE AMPLITUDES
# ===========================================================================

class TestBellStateAmplitudes:
    """Verify exact statevector amplitudes for each Bell state.

    Qiskit qubit ordering: qubit 0 is the *rightmost* bit in the ket label.
    Index mapping: |q1 q0⟩ → index = 2*q1 + q0.
        index 0 → |00⟩
        index 1 → |01⟩
        index 2 → |10⟩
        index 3 → |11⟩
    """

    _INV_SQRT2 = 1.0 / np.sqrt(2)

    def test_phi_plus_amplitudes(self) -> None:
        """|Φ+⟩ = (|00⟩ + |11⟩)/√2 → indices 0 and 3 each +1/√2."""
        sv = get_statevector(prepare_phi_plus()).data
        assert abs(sv[0] - self._INV_SQRT2) <= _ATOL
        assert abs(sv[3] - self._INV_SQRT2) <= _ATOL
        assert abs(sv[1]) <= _ATOL
        assert abs(sv[2]) <= _ATOL

    def test_phi_minus_amplitudes(self) -> None:
        """|Φ-⟩ = (|00⟩ - |11⟩)/√2 → index 0: +1/√2, index 3: −1/√2."""
        sv = get_statevector(prepare_phi_minus()).data
        assert abs(abs(sv[0]) - self._INV_SQRT2) <= _ATOL
        assert abs(abs(sv[3]) - self._INV_SQRT2) <= _ATOL
        # Relative phase: amplitudes must have opposite signs
        assert np.real(sv[0] * np.conj(sv[3])) < 0
        assert abs(sv[1]) <= _ATOL
        assert abs(sv[2]) <= _ATOL

    def test_psi_plus_amplitudes(self) -> None:
        """|Ψ+⟩ = (|01⟩ + |10⟩)/√2 → indices 1 and 2 each 1/√2."""
        sv = get_statevector(prepare_psi_plus()).data
        assert abs(abs(sv[1]) - self._INV_SQRT2) <= _ATOL
        assert abs(abs(sv[2]) - self._INV_SQRT2) <= _ATOL
        assert abs(sv[0]) <= _ATOL
        assert abs(sv[3]) <= _ATOL

    def test_psi_minus_amplitudes(self) -> None:
        """|Ψ-⟩ = (|01⟩ - |10⟩)/√2 → indices 1 and 2, opposite phase."""
        sv = get_statevector(prepare_psi_minus()).data
        assert abs(abs(sv[1]) - self._INV_SQRT2) <= _ATOL
        assert abs(abs(sv[2]) - self._INV_SQRT2) <= _ATOL
        # Relative phase: amplitudes must have opposite signs
        assert np.real(sv[1] * np.conj(sv[2])) < 0
        assert abs(sv[0]) <= _ATOL
        assert abs(sv[3]) <= _ATOL


# ===========================================================================
# 4. PAULI CORRELATIONS
# ===========================================================================

class TestPauliCorrelations:
    """Verify ⟨XX⟩, ⟨YY⟩, ⟨ZZ⟩ match the expected correlator signatures."""

    @pytest.mark.parametrize("label,exp_xx,exp_yy,exp_zz", [
        ("phi+", +1.0, -1.0, +1.0),
        ("phi-", -1.0, +1.0, +1.0),
        ("psi+", +1.0, +1.0, -1.0),
        ("psi-", -1.0, -1.0, -1.0),
    ])
    def test_xx_correlator(self, label, exp_xx, exp_yy, exp_zz) -> None:
        """⟨XX⟩ matches expected value within tolerance."""
        qc = prepare_bell_state(label)
        xx, _, _ = compute_pauli_correlations(qc)
        assert abs(xx - exp_xx) <= _ATOL, (
            f"|{label}> XX={xx:.6f}, expected {exp_xx:+.1f}"
        )

    @pytest.mark.parametrize("label,exp_xx,exp_yy,exp_zz", [
        ("phi+", +1.0, -1.0, +1.0),
        ("phi-", -1.0, +1.0, +1.0),
        ("psi+", +1.0, +1.0, -1.0),
        ("psi-", -1.0, -1.0, -1.0),
    ])
    def test_yy_correlator(self, label, exp_xx, exp_yy, exp_zz) -> None:
        """⟨YY⟩ matches expected value within tolerance."""
        qc = prepare_bell_state(label)
        _, yy, _ = compute_pauli_correlations(qc)
        assert abs(yy - exp_yy) <= _ATOL, (
            f"|{label}> YY={yy:.6f}, expected {exp_yy:+.1f}"
        )

    @pytest.mark.parametrize("label,exp_xx,exp_yy,exp_zz", [
        ("phi+", +1.0, -1.0, +1.0),
        ("phi-", -1.0, +1.0, +1.0),
        ("psi+", +1.0, +1.0, -1.0),
        ("psi-", -1.0, -1.0, -1.0),
    ])
    def test_zz_correlator(self, label, exp_xx, exp_yy, exp_zz) -> None:
        """⟨ZZ⟩ matches expected value within tolerance."""
        qc = prepare_bell_state(label)
        _, _, zz = compute_pauli_correlations(qc)
        assert abs(zz - exp_zz) <= _ATOL, (
            f"|{label}> ZZ={zz:.6f}, expected {exp_zz:+.1f}"
        )

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_correlators_in_valid_range(self, label) -> None:
        """All correlators lie within [-1, +1]."""
        qc = prepare_bell_state(label)
        xx, yy, zz = compute_pauli_correlations(qc)
        for name, val in [("XX", xx), ("YY", yy), ("ZZ", zz)]:
            assert -1.0 - _ATOL <= val <= 1.0 + _ATOL, (
                f"|{label}> {name}={val:.6f} out of range [-1,+1]"
            )

    def test_bell_correlators_constant_fixture(self) -> None:
        """BELL_CORRELATORS dict has all four labels and correct tuple length."""
        assert set(BELL_CORRELATORS.keys()) == {"phi+", "phi-", "psi+", "psi-"}
        for label, corr in BELL_CORRELATORS.items():
            assert len(corr) == 3, f"{label}: correlator tuple must have 3 elements"


# ===========================================================================
# 5. BELL-STATE IDENTIFICATION
# ===========================================================================

class TestBellStateIdentification:
    """Verify identify_bell_state returns the correct label from correlators."""

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_identify_from_exact_correlators(self, label) -> None:
        """identify_bell_state returns the correct label for exact correlators."""
        xx, yy, zz = BELL_CORRELATORS[label]
        detected = identify_bell_state(xx, yy, zz)
        assert detected == label

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_identify_from_near_integer_correlators(self, label) -> None:
        """identify_bell_state handles near-integer correlators (1e-10 noise)."""
        xx, yy, zz = BELL_CORRELATORS[label]
        # Add tiny floating-point noise
        xx += 1e-10
        yy -= 5e-11
        zz += 3e-11
        detected = identify_bell_state(xx, yy, zz, atol=1e-6)
        assert detected == label

    def test_identify_unknown_correlators_raises(self) -> None:
        """identify_bell_state raises ValueError for unknown correlator pattern."""
        with pytest.raises(ValueError, match="Cannot identify Bell state"):
            identify_bell_state(0.5, 0.5, 0.5)

    def test_identify_returns_string(self) -> None:
        """Return value is a string."""
        result = identify_bell_state(+1.0, -1.0, +1.0)
        assert isinstance(result, str)

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_identify_from_statevector_derived_correlators(self, label) -> None:
        """Correlators computed from Statevector correctly identify the state."""
        qc = prepare_bell_state(label)
        xx, yy, zz = compute_pauli_correlations(qc)
        detected = identify_bell_state(xx, yy, zz)
        assert detected == label


# ===========================================================================
# 6. SHOT SIMULATION
# ===========================================================================

class TestShotSimulation:
    """Verify AerSimulator produces correct measurement statistics."""

    @pytest.fixture(scope="class")
    @classmethod
    def simulator(cls) -> AerSimulator:
        """Shared AerSimulator instance."""
        return AerSimulator()

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_simulate_returns_dict(self, simulator, label) -> None:
        """simulate_bell_state returns a dict."""
        qc = prepare_bell_state(label)
        counts = simulate_bell_state(qc, shots=256, seed=_SEED, backend=simulator)
        assert isinstance(counts, dict)

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_simulate_total_shots(self, simulator, label) -> None:
        """Total shot count equals the requested number."""
        shots = 512
        qc = prepare_bell_state(label)
        counts = simulate_bell_state(qc, shots=shots, seed=_SEED, backend=simulator)
        assert sum(counts.values()) == shots

    def test_phi_plus_only_correlated_outcomes(self, simulator) -> None:
        """|Φ+⟩ yields only '00' and '11' (never '01' or '10')."""
        qc = prepare_phi_plus()
        counts = simulate_bell_state(qc, shots=_SHOTS, seed=_SEED, backend=simulator)
        for outcome in counts:
            assert outcome in ("00", "11"), (
                f"|Phi+> unexpected outcome: {outcome!r}"
            )

    def test_phi_minus_only_correlated_outcomes(self, simulator) -> None:
        """|Φ-⟩ yields only '00' and '11'."""
        qc = prepare_phi_minus()
        counts = simulate_bell_state(qc, shots=_SHOTS, seed=_SEED, backend=simulator)
        for outcome in counts:
            assert outcome in ("00", "11"), (
                f"|Phi-> unexpected outcome: {outcome!r}"
            )

    def test_psi_plus_only_anticorrelated_outcomes(self, simulator) -> None:
        """|Ψ+⟩ yields only '01' and '10'."""
        qc = prepare_psi_plus()
        counts = simulate_bell_state(qc, shots=_SHOTS, seed=_SEED, backend=simulator)
        for outcome in counts:
            assert outcome in ("01", "10"), (
                f"|Psi+> unexpected outcome: {outcome!r}"
            )

    def test_psi_minus_only_anticorrelated_outcomes(self, simulator) -> None:
        """|Ψ-⟩ yields only '01' and '10'."""
        qc = prepare_psi_minus()
        counts = simulate_bell_state(qc, shots=_SHOTS, seed=_SEED, backend=simulator)
        for outcome in counts:
            assert outcome in ("01", "10"), (
                f"|Psi-> unexpected outcome: {outcome!r}"
            )

    @pytest.mark.parametrize("label,outcomes", [
        ("phi+", ("00", "11")),
        ("phi-", ("00", "11")),
        ("psi+", ("01", "10")),
        ("psi-", ("01", "10")),
    ])
    def test_both_outcomes_present(self, simulator, label, outcomes) -> None:
        """Both expected outcomes appear in simulation results."""
        qc = prepare_bell_state(label)
        counts = simulate_bell_state(qc, shots=_SHOTS, seed=_SEED, backend=simulator)
        for outcome in outcomes:
            assert outcome in counts, (
                f"|{label}> expected outcome {outcome!r} not found in {counts}"
            )

    @pytest.mark.parametrize("label,outcomes", [
        ("phi+", ("00", "11")),
        ("phi-", ("00", "11")),
        ("psi+", ("01", "10")),
        ("psi-", ("01", "10")),
    ])
    def test_approximately_equal_outcome_probabilities(
        self, simulator, label, outcomes
    ) -> None:
        """Each outcome should have probability ≈ 0.5 (±5%)."""
        qc = prepare_bell_state(label)
        counts = simulate_bell_state(qc, shots=_SHOTS, seed=_SEED, backend=simulator)
        total = sum(counts.values())
        for outcome in outcomes:
            p = counts.get(outcome, 0) / total
            assert abs(p - 0.5) <= _STAT_ATOL, (
                f"|{label}> P(|{outcome}>) = {p:.4f}, expected 0.5 ± {_STAT_ATOL}"
            )

    def test_deterministic_with_seed(self, simulator) -> None:
        """Same circuit + same seed → identical counts."""
        qc = prepare_phi_plus()
        c1 = simulate_bell_state(qc, shots=256, seed=_SEED, backend=simulator)
        c2 = simulate_bell_state(qc, shots=256, seed=_SEED, backend=simulator)
        assert c1 == c2


# ===========================================================================
# 7. FULL VALIDATION PIPELINE
# ===========================================================================

class TestValidationPipeline:
    """Verify validate_bell_state and validate_all_bell_states."""

    @pytest.fixture(scope="class")
    @classmethod
    def all_results(cls) -> dict:
        """Run validate_all_bell_states once and share results."""
        return validate_all_bell_states(shots=1024, seed=_SEED)

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_validation_returns_result_type(self, label) -> None:
        """validate_bell_state returns a BellValidationResult."""
        result = validate_bell_state(label, shots=256, seed=_SEED)
        assert isinstance(result, BellValidationResult)

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_validation_passes(self, label) -> None:
        """validate_bell_state returns passed=True for all four states."""
        result = validate_bell_state(label, shots=1024, seed=_SEED)
        assert result.passed is True, (
            f"|{label}> validation FAILED: {result.message}"
        )

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_detected_matches_label(self, label, all_results) -> None:
        """detected field equals the label that was prepared."""
        r = all_results[label]
        assert r.detected == label

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_norm_is_one(self, label, all_results) -> None:
        """Statevector norm stored in result ≈ 1.0."""
        r = all_results[label]
        assert abs(r.norm - 1.0) <= _ATOL, (
            f"|{label}> norm={r.norm:.8f}"
        )

    @pytest.mark.parametrize("label,exp_xx,exp_yy,exp_zz", [
        ("phi+", +1.0, -1.0, +1.0),
        ("phi-", -1.0, +1.0, +1.0),
        ("psi+", +1.0, +1.0, -1.0),
        ("psi-", -1.0, -1.0, -1.0),
    ])
    def test_correlators_stored_correctly(
        self, label, exp_xx, exp_yy, exp_zz, all_results
    ) -> None:
        """BellValidationResult stores correct XX/YY/ZZ values."""
        r = all_results[label]
        assert abs(r.xx - exp_xx) <= _ATOL
        assert abs(r.yy - exp_yy) <= _ATOL
        assert abs(r.zz - exp_zz) <= _ATOL

    def test_validate_all_returns_four_entries(self, all_results) -> None:
        """validate_all_bell_states returns exactly 4 entries."""
        assert len(all_results) == 4

    def test_validate_all_all_pass(self, all_results) -> None:
        """All four Bell states pass validation."""
        failed = [lbl for lbl, r in all_results.items() if not r.passed]
        assert failed == [], f"Failed states: {failed}"

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_counts_non_empty(self, label, all_results) -> None:
        """Simulation counts dict is non-empty."""
        r = all_results[label]
        assert isinstance(r.counts, dict)
        assert len(r.counts) > 0

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_message_is_string(self, label, all_results) -> None:
        """result.message is a non-empty string."""
        r = all_results[label]
        assert isinstance(r.message, str) and len(r.message) > 0


# ===========================================================================
# 8. DISPATCH HELPER
# ===========================================================================

class TestDispatchHelper:
    """Verify prepare_bell_state dispatches correctly."""

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_dispatch_returns_circuit(self, label) -> None:
        """prepare_bell_state returns a QuantumCircuit for each valid label."""
        qc = prepare_bell_state(label)
        assert isinstance(qc, QuantumCircuit)

    @pytest.mark.parametrize("label,variant", [
        ("phi+", "PHI+"),
        ("phi-", "PHI-"),
        ("psi+", "PSI+"),
        ("psi-", "PSI-"),
    ])
    def test_case_insensitive(self, label, variant) -> None:
        """prepare_bell_state is case-insensitive."""
        qc = prepare_bell_state(variant)
        assert isinstance(qc, QuantumCircuit)

    def test_unknown_label_raises_value_error(self) -> None:
        """prepare_bell_state raises ValueError for unrecognised label."""
        with pytest.raises(ValueError, match="Unknown Bell state"):
            prepare_bell_state("omega")

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_dispatch_circuit_has_two_qubits(self, label) -> None:
        """Dispatched circuit always has 2 qubits."""
        assert prepare_bell_state(label).num_qubits == 2


# ===========================================================================
# 9. DENSITY MATRIX
# ===========================================================================

class TestDensityMatrix:
    """Verify density matrix properties for each Bell state."""

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_trace_is_one(self, label) -> None:
        """Tr(ρ) = 1.0 (normalisation)."""
        dm = get_density_matrix(prepare_bell_state(label))
        trace = float(np.trace(dm.data).real)
        assert abs(trace - 1.0) <= _ATOL, (
            f"|{label}> trace={trace:.8f}"
        )

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_density_matrix_is_hermitian(self, label) -> None:
        """ρ = ρ† (Hermitian property)."""
        dm = get_density_matrix(prepare_bell_state(label))
        rho = dm.data
        assert np.allclose(rho, rho.conj().T, atol=_ATOL), (
            f"|{label}> density matrix is not Hermitian"
        )

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_density_matrix_shape(self, label) -> None:
        """ρ is a 4×4 matrix."""
        dm = get_density_matrix(prepare_bell_state(label))
        assert dm.data.shape == (4, 4)

    @pytest.mark.parametrize("label", ["phi+", "phi-", "psi+", "psi-"])
    def test_pure_state_tr_rho_squared_is_one(self, label) -> None:
        """Tr(ρ²) = 1.0 for a pure state."""
        dm = get_density_matrix(prepare_bell_state(label))
        rho = dm.data
        tr_rho2 = float(np.trace(rho @ rho).real)
        assert abs(tr_rho2 - 1.0) <= _ATOL, (
            f"|{label}> Tr(ρ²)={tr_rho2:.8f}, expected 1.0 for pure state"
        )
