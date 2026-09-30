"""
tests/quantum/test_noise.py
============================
Phase 2.5 -- Quantum Channel Noise Baseline test suite.
SIH26141 | Blockchain & Cybersecurity.

Test categories
---------------
1. NoiseModel construction     -- all types build without error, p=0 empty model
2. p=0 baseline                -- noiseless fidelity == 1.0 for all noise types
3. Noisy simulation execution  -- runs succeed, return NoiseResult, fidelity in [0,1]
4. Fidelity bounds             -- 0 <= F <= 1 for all (type, p, state) combinations
5. Reproducibility             -- same seed -> same fidelity
6. DataFrame output            -- schema, dtypes, length, no NaNs
7. Constants                   -- NOISE_TYPES, NOISE_STRENGTHS, NOISE_TYPES cardinality
8. Error handling              -- bad noise_type, p out of range

All tests are deterministic (seed=42).  No AI/ML used.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC  = _ROOT / "src"
for _p in (_SRC, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

warnings.filterwarnings("ignore", category=DeprecationWarning)

from qiskit_aer.noise import NoiseModel
from qiskit.quantum_info import DensityMatrix

from quantum.noise import (
    NOISE_STRENGTHS,
    NOISE_TYPES,
    CHANNEL_GATES_1Q,
    CHANNEL_GATES_2Q,
    NoiseResult,
    build_noise_model,
    results_to_dataframe,
    run_noisy_teleportation,
    sweep_noise_fidelity,
)
from quantum.teleportation import STANDARD_STATES

_SEED:       int   = 42
_SHOTS:      int   = 4096
_ATOL:       float = 1e-6
_FIDELITY_LO: float = 0.0
_FIDELITY_HI: float = 1.0 + 1e-6   # small numerical tolerance above 1


# ===========================================================================
# 1. NOISE MODEL CONSTRUCTION
# ===========================================================================

class TestNoiseModelConstruction:
    """Verify build_noise_model returns a valid NoiseModel for every type."""

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_returns_noise_model(self, noise_type) -> None:
        """build_noise_model returns a NoiseModel instance."""
        nm = build_noise_model(noise_type, 0.10)
        assert isinstance(nm, NoiseModel)

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_p_zero_returns_empty_model(self, noise_type) -> None:
        """p=0 produces an empty NoiseModel (no errors added)."""
        nm = build_noise_model(noise_type, 0.0)
        assert isinstance(nm, NoiseModel)
        # Empty model has no noise qubits
        assert len(nm.noise_qubits) == 0

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    @pytest.mark.parametrize("p", [0.01, 0.10, 0.30])
    def test_noisy_model_targets_channel_qubits(self, noise_type, p) -> None:
        """Noisy model has noise on channel qubits only (not qubit 0)."""
        nm = build_noise_model(noise_type, p)
        noisy_qubits = set(nm.noise_qubits)
        # Channel qubits 1 and 2 should be noisy
        assert 1 in noisy_qubits or 2 in noisy_qubits
        # Alice's input qubit 0 must NOT be noisy
        assert 0 not in noisy_qubits

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_model_has_basis_gates(self, noise_type) -> None:
        """Noisy model includes recognised basis gate names."""
        nm = build_noise_model(noise_type, 0.10)
        assert len(nm.basis_gates) > 0

    def test_unknown_noise_type_raises(self) -> None:
        """build_noise_model raises ValueError for unknown type."""
        with pytest.raises(ValueError, match="Unknown noise type"):
            build_noise_model("quantum_foam", 0.1)

    @pytest.mark.parametrize("bad_p", [-0.01, 1.01, 2.0])
    def test_p_out_of_range_raises(self, bad_p) -> None:
        """build_noise_model raises ValueError when p is outside [0, 1]."""
        with pytest.raises(ValueError, match="p must be in"):
            build_noise_model("bit_flip", bad_p)

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_p_one_does_not_raise(self, noise_type) -> None:
        """p=1.0 is accepted (boundary case)."""
        # amplitude_damping at p=1 means full decay; others are valid Pauli errors
        nm = build_noise_model(noise_type, 1.0)
        assert isinstance(nm, NoiseModel)


# ===========================================================================
# 2. p=0 BASELINE (NOISELESS)
# ===========================================================================

class TestBaselineNoiseless:
    """Verify p=0 reproduces the ideal noiseless fidelity within tolerance."""

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    @pytest.mark.parametrize("state_name,theta,phi", [
        ("|0>",  0.0,              0.0),
        ("|+>",  float(np.pi/2),  0.0),
        ("|1>",  float(np.pi),    0.0),
    ])
    def test_p_zero_fidelity_is_one(self, noise_type, state_name, theta, phi) -> None:
        """p=0 gives fidelity = 1.0 (ideal baseline) within tolerance."""
        r = run_noisy_teleportation(
            noise_type, p=0.0,
            theta=theta, phi=phi, state_name=state_name,
            shots=_SHOTS, seed=_SEED,
        )
        assert abs(r.fidelity - 1.0) <= _ATOL, (
            f"{noise_type} p=0 {state_name}: F={r.fidelity:.10f}"
        )

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_p_zero_returns_noise_result(self, noise_type) -> None:
        """p=0 run returns a NoiseResult."""
        r = run_noisy_teleportation(
            noise_type, p=0.0,
            theta=0.0, phi=0.0, state_name="|0>",
            shots=256, seed=_SEED,
        )
        assert isinstance(r, NoiseResult)


# ===========================================================================
# 3. NOISY SIMULATION EXECUTION
# ===========================================================================

class TestNoisySimulationExecution:
    """Verify noisy simulations complete and return valid NoiseResult objects."""

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_run_returns_noise_result(self, noise_type) -> None:
        """run_noisy_teleportation returns a NoiseResult."""
        r = run_noisy_teleportation(
            noise_type, p=0.10,
            theta=float(np.pi/2), phi=0.0, state_name="|+>",
            shots=256, seed=_SEED,
        )
        assert isinstance(r, NoiseResult)

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_result_stores_noise_type(self, noise_type) -> None:
        """NoiseResult.noise_type matches the requested type."""
        r = run_noisy_teleportation(
            noise_type, p=0.05,
            theta=0.0, phi=0.0, state_name="|0>",
            shots=256, seed=_SEED,
        )
        assert r.noise_type == noise_type

    @pytest.mark.parametrize("p", [0.01, 0.05, 0.10, 0.20, 0.30])
    def test_result_stores_p(self, p) -> None:
        """NoiseResult.p matches the requested noise strength."""
        r = run_noisy_teleportation(
            "bit_flip", p=p,
            theta=float(np.pi/2), phi=0.0, state_name="|+>",
            shots=256, seed=_SEED,
        )
        assert abs(r.p - p) < 1e-12

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_bob_dm_is_density_matrix(self, noise_type) -> None:
        """NoiseResult.bob_density_matrix is a DensityMatrix."""
        r = run_noisy_teleportation(
            noise_type, p=0.10,
            theta=float(np.pi/2), phi=0.0, state_name="|+>",
            shots=256, seed=_SEED,
        )
        assert isinstance(r.bob_density_matrix, DensityMatrix)

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_bob_dm_trace_is_one(self, noise_type) -> None:
        """Tr(rho_Bob) = 1.0 under noise."""
        r = run_noisy_teleportation(
            noise_type, p=0.10,
            theta=float(np.pi/2), phi=0.0, state_name="|+>",
            shots=_SHOTS, seed=_SEED,
        )
        trace = float(np.trace(np.asarray(r.bob_density_matrix)).real)
        assert abs(trace - 1.0) <= _ATOL

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_bob_dm_shape(self, noise_type) -> None:
        """Bob's density matrix is 2x2."""
        r = run_noisy_teleportation(
            noise_type, p=0.10,
            theta=0.0, phi=0.0, state_name="|0>",
            shots=256, seed=_SEED,
        )
        assert np.asarray(r.bob_density_matrix).shape == (2, 2)

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_result_shots_stored(self, noise_type) -> None:
        """NoiseResult.shots stores requested shot count."""
        r = run_noisy_teleportation(
            noise_type, p=0.05,
            theta=0.0, phi=0.0, state_name="|0>",
            shots=128, seed=_SEED,
        )
        assert r.shots == 128

    def test_auto_state_name_generated(self) -> None:
        """State name auto-generated when empty string provided."""
        r = run_noisy_teleportation(
            "bit_flip", p=0.05,
            theta=0.5, phi=0.7, state_name="",
            shots=128, seed=_SEED,
        )
        assert len(r.state_name) > 0


# ===========================================================================
# 4. FIDELITY BOUNDS
# ===========================================================================

class TestFidelityBounds:
    """Fidelity must stay in [0, 1] for all valid inputs."""

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    @pytest.mark.parametrize("p", [0.0, 0.05, 0.10, 0.20, 0.30])
    def test_fidelity_non_negative(self, noise_type, p) -> None:
        """Fidelity >= 0 for all (noise_type, p) combinations on |+>."""
        r = run_noisy_teleportation(
            noise_type, p=p,
            theta=float(np.pi/2), phi=0.0, state_name="|+>",
            shots=_SHOTS, seed=_SEED,
        )
        assert r.fidelity >= _FIDELITY_LO - _ATOL, (
            f"{noise_type} p={p}: F={r.fidelity:.8f} < 0"
        )

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    @pytest.mark.parametrize("p", [0.0, 0.05, 0.10, 0.20, 0.30])
    def test_fidelity_at_most_one(self, noise_type, p) -> None:
        """Fidelity <= 1 + tolerance for all (noise_type, p) on |+>."""
        r = run_noisy_teleportation(
            noise_type, p=p,
            theta=float(np.pi/2), phi=0.0, state_name="|+>",
            shots=_SHOTS, seed=_SEED,
        )
        assert r.fidelity <= _FIDELITY_HI, (
            f"{noise_type} p={p}: F={r.fidelity:.8f} > 1"
        )

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    @pytest.mark.parametrize("state_name,theta,phi", STANDARD_STATES)
    def test_fidelity_in_range_all_states(
        self, noise_type, state_name, theta, phi
    ) -> None:
        """Fidelity in [0, 1] at p=0.10 for every standard state."""
        r = run_noisy_teleportation(
            noise_type, p=0.10,
            theta=theta, phi=phi, state_name=state_name,
            shots=_SHOTS, seed=_SEED,
        )
        assert _FIDELITY_LO - _ATOL <= r.fidelity <= _FIDELITY_HI, (
            f"{noise_type} {state_name}: F={r.fidelity:.8f}"
        )


# ===========================================================================
# 5. REPRODUCIBILITY
# ===========================================================================

class TestReproducibility:
    """Identical seed and parameters produce identical fidelity."""

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_same_seed_same_fidelity(self, noise_type) -> None:
        """Two runs with same seed return identical fidelity."""
        kwargs = dict(
            noise_type=noise_type, p=0.10,
            theta=float(np.pi/2), phi=0.0, state_name="|+>",
            shots=512, seed=_SEED,
        )
        f1 = run_noisy_teleportation(**kwargs).fidelity
        f2 = run_noisy_teleportation(**kwargs).fidelity
        assert abs(f1 - f2) <= _ATOL, (
            f"{noise_type}: f1={f1:.10f}  f2={f2:.10f}"
        )

    @pytest.mark.parametrize("noise_type", NOISE_TYPES)
    def test_same_seed_same_bob_dm(self, noise_type) -> None:
        """Same seed produces identical Bob density matrix entries."""
        kwargs = dict(
            noise_type=noise_type, p=0.10,
            theta=float(np.pi/2), phi=0.0, state_name="|+>",
            shots=512, seed=_SEED,
        )
        dm1 = np.asarray(run_noisy_teleportation(**kwargs).bob_density_matrix)
        dm2 = np.asarray(run_noisy_teleportation(**kwargs).bob_density_matrix)
        assert np.allclose(dm1, dm2, atol=_ATOL)


# ===========================================================================
# 6. DATAFRAME OUTPUT
# ===========================================================================

class TestDataFrameOutput:
    """Verify results_to_dataframe produces a correctly structured DataFrame."""

    @pytest.fixture(scope="class")
    @classmethod
    def small_results(cls):
        """Tiny 2-type x 2-strength x 2-state sweep for fast schema checks."""
        return sweep_noise_fidelity(
            noise_types=["bit_flip", "depolarizing"],
            noise_strengths=[0.0, 0.10],
            states=[
                ("|0>", 0.0,         0.0),
                ("|+>", float(np.pi/2), 0.0),
            ],
            shots=256,
            seed=_SEED,
        )

    def test_returns_dataframe(self, small_results) -> None:
        """results_to_dataframe returns a pandas DataFrame."""
        df = results_to_dataframe(small_results)
        assert isinstance(df, pd.DataFrame)

    def test_correct_row_count(self, small_results) -> None:
        """DataFrame has 2 types x 2 strengths x 2 states = 8 rows."""
        df = results_to_dataframe(small_results)
        assert len(df) == 8

    def test_required_columns_present(self, small_results) -> None:
        """DataFrame contains all required columns."""
        df = results_to_dataframe(small_results)
        required = {"noise_type", "p", "state_name", "theta", "phi",
                    "fidelity", "shots", "seed"}
        assert required.issubset(set(df.columns))

    def test_no_null_values(self, small_results) -> None:
        """DataFrame has no NaN or None values."""
        df = results_to_dataframe(small_results)
        assert not df.isnull().any().any()

    def test_fidelity_column_dtype_float(self, small_results) -> None:
        """fidelity column is numeric (float)."""
        df = results_to_dataframe(small_results)
        assert pd.api.types.is_float_dtype(df["fidelity"])

    def test_p_column_dtype_float(self, small_results) -> None:
        """p column is numeric (float)."""
        df = results_to_dataframe(small_results)
        assert pd.api.types.is_float_dtype(df["p"])

    def test_noise_type_values(self, small_results) -> None:
        """noise_type column contains only expected values."""
        df = results_to_dataframe(small_results)
        assert set(df["noise_type"].unique()) == {"bit_flip", "depolarizing"}

    def test_fidelity_all_in_range(self, small_results) -> None:
        """All fidelity values are in [0, 1+tol]."""
        df = results_to_dataframe(small_results)
        assert (df["fidelity"] >= -_ATOL).all()
        assert (df["fidelity"] <= 1.0 + _ATOL).all()

    def test_p_zero_fidelity_is_one(self, small_results) -> None:
        """Rows with p=0 have fidelity == 1.0."""
        df = results_to_dataframe(small_results)
        p0_rows = df[df["p"] == 0.0]
        assert len(p0_rows) > 0
        assert (p0_rows["fidelity"] >= 1.0 - _ATOL).all()

    def test_empty_list_returns_empty_df(self) -> None:
        """results_to_dataframe([]) returns an empty DataFrame."""
        df = results_to_dataframe([])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


# ===========================================================================
# 7. CONSTANTS
# ===========================================================================

class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_noise_types_count(self) -> None:
        """NOISE_TYPES has exactly 4 entries."""
        assert len(NOISE_TYPES) == 4

    def test_noise_types_values(self) -> None:
        """NOISE_TYPES contains expected channel names."""
        assert set(NOISE_TYPES) == {
            "bit_flip", "phase_flip", "depolarizing", "amplitude_damping"
        }

    def test_noise_strengths_contains_zero(self) -> None:
        """NOISE_STRENGTHS includes 0.0 (baseline)."""
        assert 0.0 in NOISE_STRENGTHS

    def test_noise_strengths_all_in_range(self) -> None:
        """All NOISE_STRENGTHS values are in [0, 1]."""
        for p in NOISE_STRENGTHS:
            assert 0.0 <= p <= 1.0

    def test_noise_strengths_length(self) -> None:
        """NOISE_STRENGTHS has exactly 6 entries."""
        assert len(NOISE_STRENGTHS) == 6

    def test_channel_gates_1q_nonempty(self) -> None:
        """CHANNEL_GATES_1Q is non-empty."""
        assert len(CHANNEL_GATES_1Q) > 0

    def test_channel_gates_2q_nonempty(self) -> None:
        """CHANNEL_GATES_2Q is non-empty."""
        assert len(CHANNEL_GATES_2Q) > 0
