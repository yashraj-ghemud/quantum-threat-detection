"""
tests/test_phase0.py
====================
Phase 0 — Foundation test suite for Quantum-Inspired Cyber Threat Detection.
SIH26141 — Blockchain & Cybersecurity.

Test categories
---------------
1. Package imports           — all six src sub-packages import without error
2. Configuration loading     — ConfigLoader reads YAML with correct typed values
3. Reproducibility           — NumPy seed and Generator produce deterministic output
4. Qiskit circuit creation   — QuantumCircuit builds correctly
5. Aer simulator             — AerSimulator instantiates and executes a circuit

No AI/ML libraries are used in this project.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure src/ is on sys.path for direct pytest runs (pyproject.toml also
# sets pythonpath = ["src"] but this guard makes the file self-contained).
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ===========================================================================
# 1. PACKAGE IMPORTS
# ===========================================================================

class TestPackageImports:
    """Verify that every src sub-package can be imported without error."""

    def test_import_quantum(self) -> None:
        """quantum package imports cleanly."""
        import quantum  # noqa: F401

    def test_import_qds(self) -> None:
        """qds package imports cleanly."""
        import qds  # noqa: F401

    def test_import_security(self) -> None:
        """security package imports cleanly."""
        import security  # noqa: F401

    def test_import_attacks(self) -> None:
        """attacks package imports cleanly."""
        import attacks  # noqa: F401

    def test_import_evaluation(self) -> None:
        """evaluation package imports cleanly."""
        import evaluation  # noqa: F401

    def test_import_utils(self) -> None:
        """utils package imports cleanly."""
        import utils  # noqa: F401

    def test_import_utils_config(self) -> None:
        """utils.config module imports cleanly."""
        from utils.config import ConfigLoader  # noqa: F401

    def test_import_utils_logger(self) -> None:
        """utils.logger module imports cleanly."""
        from utils.logger import get_logger  # noqa: F401

    def test_import_utils_reproducibility(self) -> None:
        """utils.reproducibility module imports cleanly."""
        from utils.reproducibility import set_seed, get_rng  # noqa: F401

    def test_import_utils_validation(self) -> None:
        """utils.validation module imports cleanly."""
        from utils.validation import validate_basis, validate_shots  # noqa: F401

    def test_import_qiskit(self) -> None:
        """qiskit core package imports cleanly."""
        import qiskit  # noqa: F401

    def test_import_qiskit_aer(self) -> None:
        """qiskit_aer package imports cleanly."""
        import qiskit_aer  # noqa: F401

    def test_import_numpy(self) -> None:
        """numpy imports cleanly."""
        import numpy  # noqa: F401

    def test_import_scipy(self) -> None:
        """scipy imports cleanly."""
        import scipy  # noqa: F401

    def test_import_pandas(self) -> None:
        """pandas imports cleanly."""
        import pandas  # noqa: F401

    def test_import_matplotlib(self) -> None:
        """matplotlib imports cleanly."""
        import matplotlib  # noqa: F401


# ===========================================================================
# 2. CONFIGURATION LOADING
# ===========================================================================

class TestConfigurationLoading:
    """Verify ConfigLoader reads quantum_config.yaml correctly."""

    @pytest.fixture(scope="class")
    @classmethod
    def cfg(cls):
        """Shared ConfigLoader instance for the class."""
        from utils.config import ConfigLoader
        return ConfigLoader()

    def test_config_loads_without_error(self, cfg) -> None:
        """ConfigLoader instantiates without raising any exception."""
        assert cfg is not None

    def test_random_seed_default(self, cfg) -> None:
        """random_seed reads as 42 from config."""
        assert cfg.random_seed == 42

    def test_shots_default(self, cfg) -> None:
        """shots reads as 1024 from config."""
        assert cfg.shots == 1024

    def test_simulator_backend(self, cfg) -> None:
        """simulator_backend is 'aer_simulator'."""
        assert cfg.simulator_backend == "aer_simulator"

    def test_measurement_bases_present(self, cfg) -> None:
        """measurement_bases dict contains X, Y, Z keys."""
        bases = cfg.measurement_bases
        assert "X" in bases
        assert "Y" in bases
        assert "Z" in bases

    def test_measurement_bases_values(self, cfg) -> None:
        """X/Y/Z map to lowercase 'x'/'y'/'z'."""
        bases = cfg.measurement_bases
        assert bases["X"] == "x"
        assert bases["Y"] == "y"
        assert bases["Z"] == "z"

    def test_log_level_is_string(self, cfg) -> None:
        """log_level returns a non-empty string."""
        assert isinstance(cfg.log_level, str)
        assert cfg.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    def test_default_num_qubits(self, cfg) -> None:
        """default_num_qubits is a positive integer."""
        assert isinstance(cfg.default_num_qubits, int)
        assert cfg.default_num_qubits >= 1

    def test_phase_flags_is_dict(self, cfg) -> None:
        """phase_flags returns a dictionary."""
        assert isinstance(cfg.phase_flags, dict)

    def test_phase0_enabled(self, cfg) -> None:
        """phase0_foundation flag is True."""
        flags = cfg.phase_flags
        assert flags.get("phase0_foundation") is True

    def test_phase1_enabled(self, cfg) -> None:
        """phase1_bell_states flag is True (Phase 1 implemented)."""
        flags = cfg.phase_flags
        assert flags.get("phase1_bell_states") is True

    def test_get_nested(self, cfg) -> None:
        """get_nested traverses YAML keys correctly."""
        shots = cfg.get_nested("simulator", "shots")
        assert shots == 1024

    def test_get_nested_missing_returns_default(self, cfg) -> None:
        """get_nested returns default for missing key."""
        val = cfg.get_nested("nonexistent_key", default="fallback")
        assert val == "fallback"

    def test_config_repr(self, cfg) -> None:
        """__repr__ returns a non-empty string."""
        r = repr(cfg)
        assert "ConfigLoader" in r
        assert "42" in r

    def test_custom_config_path_not_found(self) -> None:
        """ConfigLoader raises FileNotFoundError for a non-existent path."""
        from utils.config import ConfigLoader
        with pytest.raises(FileNotFoundError):
            ConfigLoader(config_path="/nonexistent/path/config.yaml")


# ===========================================================================
# 3. REPRODUCIBILITY
# ===========================================================================

class TestReproducibility:
    """Verify seed management produces deterministic outputs."""

    def test_set_seed_returns_seed(self) -> None:
        """set_seed returns the applied seed value."""
        from utils.reproducibility import set_seed
        applied = set_seed(42)
        assert applied == 42

    def test_set_seed_default(self) -> None:
        """set_seed with no argument uses RANDOM_SEED (42)."""
        from utils.reproducibility import set_seed
        applied = set_seed()
        assert applied == 42

    def test_numpy_seed_reproducibility(self) -> None:
        """Same seed produces identical NumPy random arrays."""
        from utils.reproducibility import set_seed
        set_seed(42)
        arr1 = np.random.rand(10)
        set_seed(42)
        arr2 = np.random.rand(10)
        np.testing.assert_array_equal(arr1, arr2)

    def test_different_seeds_differ(self) -> None:
        """Different seeds produce different NumPy random arrays."""
        from utils.reproducibility import set_seed
        set_seed(1)
        arr1 = np.random.rand(10)
        set_seed(2)
        arr2 = np.random.rand(10)
        assert not np.array_equal(arr1, arr2)

    def test_get_rng_reproducibility(self) -> None:
        """get_rng(42) produces identical sequences across two calls."""
        from utils.reproducibility import get_rng
        rng1 = get_rng(42)
        rng2 = get_rng(42)
        arr1 = rng1.random(10)
        arr2 = rng2.random(10)
        np.testing.assert_array_equal(arr1, arr2)

    def test_get_rng_different_seeds(self) -> None:
        """get_rng with different seeds produces different sequences."""
        from utils.reproducibility import get_rng
        arr1 = get_rng(1).random(10)
        arr2 = get_rng(2).random(10)
        assert not np.array_equal(arr1, arr2)

    def test_get_rng_returns_generator(self) -> None:
        """get_rng returns a numpy.random.Generator instance."""
        from utils.reproducibility import get_rng
        rng = get_rng(42)
        assert isinstance(rng, np.random.Generator)

    def test_get_run_context_contains_seed(self) -> None:
        """get_run_context returns dict with 'seed' key."""
        from utils.reproducibility import get_run_context
        ctx = get_run_context(42)
        assert "seed" in ctx
        assert ctx["seed"] == 42

    def test_get_run_context_numpy_version(self) -> None:
        """get_run_context includes numpy_version."""
        from utils.reproducibility import get_run_context
        ctx = get_run_context(42)
        assert "numpy_version" in ctx
        assert isinstance(ctx["numpy_version"], str)


# ===========================================================================
# 4. QISKIT CIRCUIT CREATION
# ===========================================================================

class TestQiskitCircuitCreation:
    """Verify basic Qiskit QuantumCircuit construction works correctly."""

    def test_create_single_qubit_circuit(self) -> None:
        """QuantumCircuit(1) creates a 1-qubit circuit."""
        from qiskit import QuantumCircuit
        qc = QuantumCircuit(1)
        assert qc.num_qubits == 1

    def test_create_two_qubit_circuit(self) -> None:
        """QuantumCircuit(2) creates a 2-qubit circuit."""
        from qiskit import QuantumCircuit
        qc = QuantumCircuit(2)
        assert qc.num_qubits == 2

    def test_circuit_with_classical_bits(self) -> None:
        """QuantumCircuit(2, 2) has 2 qubits and 2 classical bits."""
        from qiskit import QuantumCircuit
        qc = QuantumCircuit(2, 2)
        assert qc.num_qubits == 2
        assert qc.num_clbits == 2

    def test_apply_hadamard_gate(self) -> None:
        """Applying H gate to qubit 0 increases circuit depth."""
        from qiskit import QuantumCircuit
        qc = QuantumCircuit(1)
        qc.h(0)
        assert qc.depth() >= 1

    def test_apply_cnot_gate(self) -> None:
        """Applying CX gate is recorded in the circuit."""
        from qiskit import QuantumCircuit
        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cx(0, 1)
        assert qc.depth() >= 1

    def test_add_measurement(self) -> None:
        """measure_all() adds classical register to the circuit."""
        from qiskit import QuantumCircuit
        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure_all()
        assert qc.num_clbits == 2

    def test_circuit_num_qubits_from_config(self) -> None:
        """Circuit built with config default_num_qubits has correct qubit count."""
        from qiskit import QuantumCircuit
        from utils.config import ConfigLoader
        cfg = ConfigLoader()
        qc = QuantumCircuit(cfg.default_num_qubits)
        assert qc.num_qubits == cfg.default_num_qubits


# ===========================================================================
# 5. AER SIMULATOR AVAILABILITY
# ===========================================================================

class TestAerSimulatorAvailability:
    """Verify Qiskit Aer simulator instantiates and can run a simple circuit."""

    @pytest.fixture(scope="class")
    @classmethod
    def simulator(cls):
        """Shared AerSimulator instance."""
        from qiskit_aer import AerSimulator
        return AerSimulator()

    def test_aer_simulator_instantiates(self, simulator) -> None:
        """AerSimulator() constructs without error."""
        assert simulator is not None

    def test_aer_simulator_name(self, simulator) -> None:
        """AerSimulator has a non-empty name."""
        assert isinstance(simulator.name, str)
        assert len(simulator.name) > 0

    def test_run_bell_state_circuit(self, simulator) -> None:
        """Run a minimal Bell-state circuit and get non-empty counts."""
        from qiskit import QuantumCircuit, transpile
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])
        compiled = transpile(qc, simulator)
        job = simulator.run(compiled, shots=128, seed_simulator=42)
        result = job.result()
        counts = result.get_counts()
        assert isinstance(counts, dict)
        assert len(counts) > 0

    def test_bell_state_only_correlated_outcomes(self, simulator) -> None:
        """Bell state |Φ+⟩ yields only '00' and '11' outcomes."""
        from qiskit import QuantumCircuit, transpile
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])
        compiled = transpile(qc, simulator)
        job = simulator.run(compiled, shots=1024, seed_simulator=42)
        result = job.result()
        counts = result.get_counts()
        for outcome in counts:
            assert outcome in ("00", "11"), (
                f"Unexpected outcome '{outcome}' from Bell state circuit."
            )

    def test_shot_count_respected(self, simulator) -> None:
        """Total shots in result equal the requested shot count."""
        from qiskit import QuantumCircuit, transpile
        shots = 256
        qc = QuantumCircuit(1, 1)
        qc.h(0)
        qc.measure(0, 0)
        compiled = transpile(qc, simulator)
        job = simulator.run(compiled, shots=shots, seed_simulator=42)
        result = job.result()
        counts = result.get_counts()
        total = sum(counts.values())
        assert total == shots

    def test_deterministic_with_seed(self, simulator) -> None:
        """Same circuit + same seed produces identical counts."""
        from qiskit import QuantumCircuit, transpile
        qc = QuantumCircuit(1, 1)
        qc.h(0)
        qc.measure(0, 0)
        compiled = transpile(qc, simulator)

        job1 = simulator.run(compiled, shots=512, seed_simulator=42)
        job2 = simulator.run(compiled, shots=512, seed_simulator=42)

        counts1 = job1.result().get_counts()
        counts2 = job2.result().get_counts()
        assert counts1 == counts2


# ===========================================================================
# 6. VALIDATION HELPERS
# ===========================================================================

class TestValidationHelpers:
    """Verify input validation functions in utils.validation."""

    # --- validate_basis ---

    def test_validate_basis_lowercase_x(self) -> None:
        """'x' is a valid basis."""
        from utils.validation import validate_basis
        assert validate_basis("x") == "x"

    def test_validate_basis_lowercase_y(self) -> None:
        """'y' is a valid basis."""
        from utils.validation import validate_basis
        assert validate_basis("y") == "y"

    def test_validate_basis_lowercase_z(self) -> None:
        """'z' is a valid basis."""
        from utils.validation import validate_basis
        assert validate_basis("z") == "z"

    def test_validate_basis_uppercase_normalised(self) -> None:
        """Uppercase 'X', 'Y', 'Z' are normalised to lowercase."""
        from utils.validation import validate_basis
        assert validate_basis("X") == "x"
        assert validate_basis("Y") == "y"
        assert validate_basis("Z") == "z"

    def test_validate_basis_invalid_raises_value_error(self) -> None:
        """Invalid basis string raises ValueError."""
        from utils.validation import validate_basis
        with pytest.raises(ValueError):
            validate_basis("w")

    def test_validate_basis_empty_raises_value_error(self) -> None:
        """Empty string raises ValueError."""
        from utils.validation import validate_basis
        with pytest.raises(ValueError):
            validate_basis("")

    def test_validate_basis_non_string_raises_type_error(self) -> None:
        """Non-string input raises TypeError."""
        from utils.validation import validate_basis
        with pytest.raises(TypeError):
            validate_basis(42)

    # --- validate_shots ---

    def test_validate_shots_valid(self) -> None:
        """Positive integer is returned as-is."""
        from utils.validation import validate_shots
        assert validate_shots(1024) == 1024

    def test_validate_shots_string_int(self) -> None:
        """String representation of integer is accepted."""
        from utils.validation import validate_shots
        assert validate_shots("512") == 512

    def test_validate_shots_zero_raises(self) -> None:
        """Zero raises ValueError."""
        from utils.validation import validate_shots
        with pytest.raises(ValueError):
            validate_shots(0)

    def test_validate_shots_negative_raises(self) -> None:
        """Negative value raises ValueError."""
        from utils.validation import validate_shots
        with pytest.raises(ValueError):
            validate_shots(-1)

    def test_validate_shots_non_numeric_raises(self) -> None:
        """Non-numeric string raises TypeError."""
        from utils.validation import validate_shots
        with pytest.raises(TypeError):
            validate_shots("lots")

    # --- validate_num_qubits ---

    def test_validate_num_qubits_valid(self) -> None:
        """Positive integer is returned correctly."""
        from utils.validation import validate_num_qubits
        assert validate_num_qubits(2) == 2

    def test_validate_num_qubits_zero_raises(self) -> None:
        """Zero raises ValueError (min_qubits=1)."""
        from utils.validation import validate_num_qubits
        with pytest.raises(ValueError):
            validate_num_qubits(0)
