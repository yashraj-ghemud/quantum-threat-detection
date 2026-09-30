"""
tests/qds/test_pauli_states.py
================================
Phase 3 -- Pauli Eigenstates test suite.
SIH26141 | Blockchain & Cybersecurity.

Categories
----------
1. Statevector normalisation     -- ||psi|| == 1 for all six states
2. Eigenvalue equations          -- sigma|psi> == ev|psi>
3. Bloch vectors                 -- correct (bx,by,bz) values
4. Pauli matrices                -- shape, dtype, Hermitian, trace
5. Projectors                    -- shape, Hermitian, sum to I, rank-1
6. Measurement probabilities     -- in [0,1], sum to 1, eigenstate -> correct probs
7. Metadata                      -- basis, eigenvalue, label
8. Dispatch and bulk access      -- get_eigenstate, all_eigenstates, bad label
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

warnings.filterwarnings("ignore", category=DeprecationWarning)

from qds.pauli_states import (
    EIGENSTATE_LABELS,
    IDENTITY,
    PAULI_MATRICES,
    PROJECTOR_MINUS,
    PROJECTOR_PLUS,
    SIGMA_X,
    SIGMA_Y,
    SIGMA_Z,
    PauliEigenstate,
    all_eigenstates,
    get_eigenstate,
    make_ket_0,
    make_ket_1,
    make_ket_minus,
    make_ket_minus_i,
    make_ket_plus,
    make_ket_plus_i,
    measure_eigenstate,
    projective_measurement_probs,
    validate_eigenvalue_equation,
    validate_statevector_norm,
)

_ATOL = 1e-9
_ALL_LABELS = list(EIGENSTATE_LABELS)


# ===========================================================================
# 1. STATEVECTOR NORMALISATION
# ===========================================================================

class TestStatevectorNorm:
    """All six eigenstates must have unit norm."""

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_norm_is_one(self, label) -> None:
        """||psi|| = 1 for each eigenstate."""
        s = get_eigenstate(label)
        assert abs(np.linalg.norm(s.statevector) - 1.0) <= _ATOL

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_validate_norm_helper_returns_true(self, label) -> None:
        """validate_statevector_norm returns True for all eigenstates."""
        s = get_eigenstate(label)
        assert validate_statevector_norm(s.statevector, atol=_ATOL)

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_statevector_length_is_two(self, label) -> None:
        """Statevector has exactly two complex amplitudes."""
        s = get_eigenstate(label)
        assert s.statevector.shape == (2,)

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_statevector_dtype_complex(self, label) -> None:
        """Statevector dtype is complex."""
        s = get_eigenstate(label)
        assert np.issubdtype(s.statevector.dtype, np.complexfloating)

    def test_validate_norm_fails_for_unnormalized(self) -> None:
        """validate_statevector_norm returns False for unnormalised vector."""
        bad = np.array([1.0, 1.0], dtype=complex)  # norm = sqrt(2)
        assert not validate_statevector_norm(bad, atol=_ATOL)


# ===========================================================================
# 2. EIGENVALUE EQUATIONS
# ===========================================================================

class TestEigenvalueEquations:
    """sigma|psi> = eigenvalue * |psi> for each state in its own basis."""

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_eigenvalue_equation(self, label) -> None:
        """sigma|psi> == eigenvalue * |psi> within atol."""
        s = get_eigenstate(label)
        assert validate_eigenvalue_equation(s, atol=_ATOL)

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_eigenvalue_is_plus_or_minus_one(self, label) -> None:
        """Eigenvalue is exactly +1 or -1."""
        s = get_eigenstate(label)
        assert s.eigenvalue in (+1, -1)

    def test_z_positive_eigenvalue(self) -> None:
        """|0> has Z eigenvalue +1."""
        assert make_ket_0().eigenvalue == +1

    def test_z_negative_eigenvalue(self) -> None:
        """|1> has Z eigenvalue -1."""
        assert make_ket_1().eigenvalue == -1

    def test_x_positive_eigenvalue(self) -> None:
        """|+> has X eigenvalue +1."""
        assert make_ket_plus().eigenvalue == +1

    def test_x_negative_eigenvalue(self) -> None:
        """|-> has X eigenvalue -1."""
        assert make_ket_minus().eigenvalue == -1

    def test_y_positive_eigenvalue(self) -> None:
        """|+i> has Y eigenvalue +1."""
        assert make_ket_plus_i().eigenvalue == +1

    def test_y_negative_eigenvalue(self) -> None:
        """|-i> has Y eigenvalue -1."""
        assert make_ket_minus_i().eigenvalue == -1

    def test_explicit_ket_0_z_equation(self) -> None:
        """Z|0> = +1*|0> numerically."""
        s = make_ket_0()
        assert np.allclose(SIGMA_Z @ s.statevector, +1 * s.statevector, atol=_ATOL)

    def test_explicit_ket_plus_x_equation(self) -> None:
        """X|+> = +1*|+> numerically."""
        s = make_ket_plus()
        assert np.allclose(SIGMA_X @ s.statevector, +1 * s.statevector, atol=_ATOL)

    def test_explicit_ket_plus_i_y_equation(self) -> None:
        """Y|+i> = +1*|+i> numerically."""
        s = make_ket_plus_i()
        assert np.allclose(SIGMA_Y @ s.statevector, +1 * s.statevector, atol=_ATOL)


# ===========================================================================
# 3. BLOCH VECTORS
# ===========================================================================

class TestBlochVectors:
    """Verify Bloch vector (bx, by, bz) values."""

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_bloch_vector_shape(self, label) -> None:
        """Bloch vector has shape (3,)."""
        s = get_eigenstate(label)
        assert s.bloch_vector.shape == (3,)

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_bloch_vector_unit_length(self, label) -> None:
        """Pure state Bloch vector has unit length."""
        s = get_eigenstate(label)
        assert abs(np.linalg.norm(s.bloch_vector) - 1.0) <= _ATOL

    def test_ket_0_bloch(self) -> None:
        """|0> -> Bloch (0, 0, +1)."""
        bv = make_ket_0().bloch_vector
        assert np.allclose(bv, [0, 0, 1], atol=_ATOL)

    def test_ket_1_bloch(self) -> None:
        """|1> -> Bloch (0, 0, -1)."""
        bv = make_ket_1().bloch_vector
        assert np.allclose(bv, [0, 0, -1], atol=_ATOL)

    def test_ket_plus_bloch(self) -> None:
        """|+> -> Bloch (+1, 0, 0)."""
        bv = make_ket_plus().bloch_vector
        assert np.allclose(bv, [1, 0, 0], atol=_ATOL)

    def test_ket_minus_bloch(self) -> None:
        """|-> -> Bloch (-1, 0, 0)."""
        bv = make_ket_minus().bloch_vector
        assert np.allclose(bv, [-1, 0, 0], atol=_ATOL)

    def test_ket_plus_i_bloch(self) -> None:
        """|+i> -> Bloch (0, +1, 0)."""
        bv = make_ket_plus_i().bloch_vector
        assert np.allclose(bv, [0, 1, 0], atol=_ATOL)

    def test_ket_minus_i_bloch(self) -> None:
        """|-i> -> Bloch (0, -1, 0)."""
        bv = make_ket_minus_i().bloch_vector
        assert np.allclose(bv, [0, -1, 0], atol=_ATOL)


# ===========================================================================
# 4. PAULI MATRICES
# ===========================================================================

class TestPauliMatrices:
    """Verify Pauli matrix properties."""

    @pytest.mark.parametrize("sigma", [SIGMA_X, SIGMA_Y, SIGMA_Z])
    def test_shape_2x2(self, sigma) -> None:
        """Each Pauli matrix is 2x2."""
        assert sigma.shape == (2, 2)

    @pytest.mark.parametrize("sigma", [SIGMA_X, SIGMA_Y, SIGMA_Z])
    def test_hermitian(self, sigma) -> None:
        """Pauli matrices are Hermitian: sigma = sigma†."""
        assert np.allclose(sigma, sigma.conj().T, atol=_ATOL)

    @pytest.mark.parametrize("sigma", [SIGMA_X, SIGMA_Y, SIGMA_Z])
    def test_trace_zero(self, sigma) -> None:
        """Tr(sigma) = 0."""
        assert abs(np.trace(sigma)) <= _ATOL

    @pytest.mark.parametrize("sigma", [SIGMA_X, SIGMA_Y, SIGMA_Z])
    def test_unitary(self, sigma) -> None:
        """sigma^2 = I."""
        assert np.allclose(sigma @ sigma, IDENTITY, atol=_ATOL)

    @pytest.mark.parametrize("sigma", [SIGMA_X, SIGMA_Y, SIGMA_Z])
    def test_eigenvalues_pm1(self, sigma) -> None:
        """Eigenvalues of each Pauli are +1 and -1."""
        evals = np.linalg.eigvalsh(sigma)
        assert np.allclose(sorted(evals), [-1.0, 1.0], atol=_ATOL)

    def test_pauli_matrices_dict_has_xyz(self) -> None:
        """PAULI_MATRICES dict has keys x, y, z."""
        assert set(PAULI_MATRICES) == {"x", "y", "z"}

    def test_commutation_xy(self) -> None:
        """[X, Y] = 2iZ."""
        comm = SIGMA_X @ SIGMA_Y - SIGMA_Y @ SIGMA_X
        assert np.allclose(comm, 2j * SIGMA_Z, atol=_ATOL)


# ===========================================================================
# 5. PROJECTORS
# ===========================================================================

class TestProjectors:
    """Verify projector properties P± = (I ± sigma)/2."""

    @pytest.mark.parametrize("basis", ["x", "y", "z"])
    def test_projectors_sum_to_identity(self, basis) -> None:
        """P+ + P- = I for each basis."""
        assert np.allclose(PROJECTOR_PLUS[basis] + PROJECTOR_MINUS[basis], IDENTITY, atol=_ATOL)

    @pytest.mark.parametrize("basis", ["x", "y", "z"])
    def test_projector_plus_idempotent(self, basis) -> None:
        """P+^2 = P+ (idempotent)."""
        Pp = PROJECTOR_PLUS[basis]
        assert np.allclose(Pp @ Pp, Pp, atol=_ATOL)

    @pytest.mark.parametrize("basis", ["x", "y", "z"])
    def test_projector_minus_idempotent(self, basis) -> None:
        """P-^2 = P- (idempotent)."""
        Pm = PROJECTOR_MINUS[basis]
        assert np.allclose(Pm @ Pm, Pm, atol=_ATOL)

    @pytest.mark.parametrize("basis", ["x", "y", "z"])
    def test_projectors_orthogonal(self, basis) -> None:
        """P+ * P- = 0 (orthogonal projectors)."""
        prod = PROJECTOR_PLUS[basis] @ PROJECTOR_MINUS[basis]
        assert np.allclose(prod, np.zeros((2, 2)), atol=_ATOL)

    @pytest.mark.parametrize("basis", ["x", "y", "z"])
    def test_projectors_hermitian(self, basis) -> None:
        """Both projectors are Hermitian."""
        for P in (PROJECTOR_PLUS[basis], PROJECTOR_MINUS[basis]):
            assert np.allclose(P, P.conj().T, atol=_ATOL)

    @pytest.mark.parametrize("basis", ["x", "y", "z"])
    def test_projectors_trace_one(self, basis) -> None:
        """Tr(P+) = Tr(P-) = 1."""
        assert abs(np.trace(PROJECTOR_PLUS[basis]) - 1.0) <= _ATOL
        assert abs(np.trace(PROJECTOR_MINUS[basis]) - 1.0) <= _ATOL


# ===========================================================================
# 6. MEASUREMENT PROBABILITIES
# ===========================================================================

class TestMeasurementProbabilities:
    """projective_measurement_probs returns valid, normalised probabilities."""

    @pytest.mark.parametrize("label", _ALL_LABELS)
    @pytest.mark.parametrize("basis", ["x", "y", "z"])
    def test_probs_sum_to_one(self, label, basis) -> None:
        """P(+1) + P(-1) = 1 for all states and bases."""
        s = get_eigenstate(label)
        pp, pm = projective_measurement_probs(s.statevector, basis)
        assert abs(pp + pm - 1.0) <= _ATOL

    @pytest.mark.parametrize("label", _ALL_LABELS)
    @pytest.mark.parametrize("basis", ["x", "y", "z"])
    def test_probs_in_unit_interval(self, label, basis) -> None:
        """P(+1) and P(-1) are each in [0, 1]."""
        s = get_eigenstate(label)
        pp, pm = projective_measurement_probs(s.statevector, basis)
        assert -_ATOL <= pp <= 1.0 + _ATOL
        assert -_ATOL <= pm <= 1.0 + _ATOL

    def test_ket_0_in_z_gives_p_plus_one(self) -> None:
        """|0> measured in Z: P(+1)=1, P(-1)=0."""
        pp, pm = projective_measurement_probs(make_ket_0().statevector, "z")
        assert abs(pp - 1.0) <= _ATOL
        assert abs(pm) <= _ATOL

    def test_ket_1_in_z_gives_p_minus_one(self) -> None:
        """|1> measured in Z: P(+1)=0, P(-1)=1."""
        pp, pm = projective_measurement_probs(make_ket_1().statevector, "z")
        assert abs(pp) <= _ATOL
        assert abs(pm - 1.0) <= _ATOL

    def test_ket_plus_in_x_gives_p_plus_one(self) -> None:
        """|+> measured in X: P(+1)=1, P(-1)=0."""
        pp, pm = projective_measurement_probs(make_ket_plus().statevector, "x")
        assert abs(pp - 1.0) <= _ATOL
        assert abs(pm) <= _ATOL

    def test_ket_minus_in_x_gives_p_minus_one(self) -> None:
        """|-> measured in X: P(+1)=0, P(-1)=1."""
        pp, pm = projective_measurement_probs(make_ket_minus().statevector, "x")
        assert abs(pp) <= _ATOL
        assert abs(pm - 1.0) <= _ATOL

    def test_ket_plus_i_in_y_gives_p_plus_one(self) -> None:
        """|+i> measured in Y: P(+1)=1, P(-1)=0."""
        pp, pm = projective_measurement_probs(make_ket_plus_i().statevector, "y")
        assert abs(pp - 1.0) <= _ATOL
        assert abs(pm) <= _ATOL

    def test_ket_minus_i_in_y_gives_p_minus_one(self) -> None:
        """|-i> measured in Y: P(+1)=0, P(-1)=1."""
        pp, pm = projective_measurement_probs(make_ket_minus_i().statevector, "y")
        assert abs(pp) <= _ATOL
        assert abs(pm - 1.0) <= _ATOL

    def test_ket_plus_in_z_gives_half_half(self) -> None:
        """|+> in Z: P(+1)=P(-1)=0.5."""
        pp, pm = projective_measurement_probs(make_ket_plus().statevector, "z")
        assert abs(pp - 0.5) <= _ATOL
        assert abs(pm - 0.5) <= _ATOL

    def test_measure_eigenstate_defaults_to_own_basis(self) -> None:
        """measure_eigenstate with basis=None uses the state's own basis."""
        s = make_ket_0()
        pp, pm = measure_eigenstate(s)
        assert abs(pp - 1.0) <= _ATOL

    def test_bad_basis_raises_value_error(self) -> None:
        """projective_measurement_probs raises ValueError for unknown basis."""
        with pytest.raises(ValueError, match="Unknown basis"):
            projective_measurement_probs(make_ket_0().statevector, "w")


# ===========================================================================
# 7. METADATA
# ===========================================================================

class TestMetadata:
    """Verify PauliEigenstate metadata fields."""

    @pytest.mark.parametrize("label,expected_basis", [
        ("|0>", "z"), ("|1>", "z"),
        ("|+>", "x"), ("|->", "x"),
        ("|+i>", "y"), ("|-i>", "y"),
    ])
    def test_basis(self, label, expected_basis) -> None:
        """State reports correct measurement basis."""
        assert get_eigenstate(label).basis == expected_basis

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_label_matches(self, label) -> None:
        """State label attribute matches the requested label."""
        assert get_eigenstate(label).label == label

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_density_matrix_shape(self, label) -> None:
        """density_matrix property returns a 2x2 array."""
        dm = get_eigenstate(label).density_matrix
        assert dm.shape == (2, 2)

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_density_matrix_trace_one(self, label) -> None:
        """Tr(rho) = 1."""
        dm = get_eigenstate(label).density_matrix
        assert abs(float(np.trace(dm).real) - 1.0) <= _ATOL

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_density_matrix_pure_state(self, label) -> None:
        """Tr(rho^2) = 1 (pure state)."""
        dm = get_eigenstate(label).density_matrix
        assert abs(float(np.trace(dm @ dm).real) - 1.0) <= _ATOL


# ===========================================================================
# 8. DISPATCH AND BULK ACCESS
# ===========================================================================

class TestDispatch:
    """get_eigenstate, all_eigenstates, error handling."""

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_get_eigenstate_returns_pauli_eigenstate(self, label) -> None:
        """get_eigenstate returns a PauliEigenstate."""
        assert isinstance(get_eigenstate(label), PauliEigenstate)

    def test_all_eigenstates_returns_six(self) -> None:
        """all_eigenstates returns exactly 6 entries."""
        assert len(all_eigenstates()) == 6

    def test_all_eigenstates_keys(self) -> None:
        """all_eigenstates keys match EIGENSTATE_LABELS."""
        assert set(all_eigenstates()) == set(EIGENSTATE_LABELS)

    def test_unknown_label_raises(self) -> None:
        """get_eigenstate raises ValueError for unknown label."""
        with pytest.raises(ValueError, match="Unknown eigenstate"):
            get_eigenstate("|omega>")

    def test_eigenstate_labels_constant_length(self) -> None:
        """EIGENSTATE_LABELS has exactly 6 entries."""
        assert len(EIGENSTATE_LABELS) == 6

    @pytest.mark.parametrize("label", _ALL_LABELS)
    def test_repeated_calls_consistent(self, label) -> None:
        """get_eigenstate is deterministic across repeated calls."""
        s1 = get_eigenstate(label)
        s2 = get_eigenstate(label)
        assert np.allclose(s1.statevector, s2.statevector, atol=_ATOL)
