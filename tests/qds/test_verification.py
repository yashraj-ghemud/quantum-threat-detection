"""
tests/qds/test_verification.py
================================
Phase 3 -- QDS Verification test suite.
SIH26141 | Blockchain & Cybersecurity.

Categories
----------
1. Legitimate verification      -- unmodified signature is accepted, score=1.0
2. Modified-state rejection     -- one wrong state lowers score; full replacement rejects
3. VerificationResult fields    -- all dataclass fields correct
4. ElementVerificationResult    -- per-element fields
5. Threshold sensitivity        -- score/threshold boundary
6. Teleportation integration    -- all six eigenstates teleport with F >= 0.999999
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

from qds.pauli_states import EIGENSTATE_LABELS, get_eigenstate
from qds.signature import generate_signature, QDSSignature
from qds.verification import (
    DEFAULT_ACCEPT_THRESHOLD,
    ElementVerificationResult,
    VerificationResult,
    verify_element,
    verify_signature,
)
from quantum.teleportation import calculate_teleportation_fidelity, STANDARD_STATES

_SEED  = 42
_ATOL  = 1e-9
_SIG_LEN = 16


# ===========================================================================
# 1. LEGITIMATE VERIFICATION
# ===========================================================================

class TestLegitimateVerification:
    """Unmodified signature verifies with score=1.0 and is accepted."""

    @pytest.fixture(scope="class")
    @classmethod
    def sig(cls) -> QDSSignature:
        return generate_signature("legit_msg", length=_SIG_LEN, seed=_SEED)

    @pytest.fixture(scope="class")
    @classmethod
    def result(cls, sig) -> VerificationResult:
        return verify_signature(sig)

    def test_returns_verification_result(self, sig) -> None:
        """verify_signature returns a VerificationResult."""
        r = verify_signature(sig)
        assert isinstance(r, VerificationResult)

    def test_legit_score_is_one(self, result) -> None:
        """Legitimate (unmodified) verification score == 1.0."""
        assert abs(result.verification_score - 1.0) <= _ATOL

    def test_legit_accepted(self, result) -> None:
        """Legitimate verification is accepted."""
        assert result.accepted is True

    def test_legit_all_matches(self, result) -> None:
        """All elements match in legitimate verification."""
        assert result.matches == result.total_elements
        assert result.mismatches == 0

    def test_total_elements_equals_sig_length(self, sig, result) -> None:
        """total_elements == signature length."""
        assert result.total_elements == sig.length

    def test_signature_id_stored(self, sig, result) -> None:
        """result.signature_id matches the signature."""
        assert result.signature_id == sig.signature_id

    def test_message_id_stored(self, sig, result) -> None:
        """result.message_id matches the signature."""
        assert result.message_id == sig.message_id

    @pytest.mark.parametrize("label", list(EIGENSTATE_LABELS))
    def test_single_state_signature_accepted(self, label) -> None:
        """Single-element signature with one eigenstate is accepted."""
        sig = generate_signature("m", length=1, seed=_SEED, label_pool=[label])
        r = verify_signature(sig)
        assert r.accepted is True
        assert abs(r.verification_score - 1.0) <= _ATOL


# ===========================================================================
# 2. MODIFIED-STATE REJECTION
# ===========================================================================

class TestModifiedStateRejection:
    """Replacing received states with wrong ones reduces the score."""

    @pytest.fixture(scope="class")
    @classmethod
    def sig(cls) -> QDSSignature:
        return generate_signature("tampered_msg", length=_SIG_LEN, seed=_SEED)

    def _opposite_state(self, label: str) -> np.ndarray:
        """Return a statevector from a different state to force a mismatch."""
        others = [l for l in EIGENSTATE_LABELS if l != label]
        opposite_label = others[0]
        return get_eigenstate(opposite_label).statevector

    def test_one_wrong_state_reduces_score(self, sig) -> None:
        """Replacing one element's state reduces score below 1.0."""
        received = [e.statevector.copy() for e in sig.elements]
        # Replace position 0 with a different state
        received[0] = self._opposite_state(sig.elements[0].label)
        r = verify_signature(sig, received_statevectors=received)
        assert r.verification_score < 1.0

    def test_one_wrong_state_increases_mismatches(self, sig) -> None:
        """One wrong state produces at least one mismatch."""
        received = [e.statevector.copy() for e in sig.elements]
        received[0] = self._opposite_state(sig.elements[0].label)
        r = verify_signature(sig, received_statevectors=received)
        assert r.mismatches >= 1

    def test_all_wrong_states_rejected(self, sig) -> None:
        """All-wrong received states give score near 0 and are rejected."""
        received = [self._opposite_state(e.label) for e in sig.elements]
        r = verify_signature(sig, received_statevectors=received, threshold=0.7)
        assert r.accepted is False

    def test_score_matches_plus_mismatches_equals_total(self, sig) -> None:
        """matches + mismatches == total_elements always."""
        received = [e.statevector.copy() for e in sig.elements]
        received[0] = self._opposite_state(sig.elements[0].label)
        r = verify_signature(sig, received_statevectors=received)
        assert r.matches + r.mismatches == r.total_elements

    def test_score_formula(self, sig) -> None:
        """verification_score == matches / total_elements."""
        received = [e.statevector.copy() for e in sig.elements]
        received[0] = self._opposite_state(sig.elements[0].label)
        r = verify_signature(sig, received_statevectors=received)
        expected = r.matches / r.total_elements
        assert abs(r.verification_score - expected) <= _ATOL


# ===========================================================================
# 3. VERIFICATIONRESULT FIELDS
# ===========================================================================

class TestVerificationResultFields:
    """All VerificationResult dataclass fields are populated correctly."""

    @pytest.fixture(scope="class")
    @classmethod
    def result(cls) -> VerificationResult:
        sig = generate_signature("fields_msg", length=8, seed=_SEED)
        return verify_signature(sig)

    def test_score_in_unit_interval(self, result) -> None:
        """verification_score in [0, 1]."""
        assert 0.0 - _ATOL <= result.verification_score <= 1.0 + _ATOL

    def test_accepted_is_bool(self, result) -> None:
        """accepted is a Python bool."""
        assert isinstance(result.accepted, bool)

    def test_threshold_stored(self, result) -> None:
        """threshold stored is DEFAULT_ACCEPT_THRESHOLD."""
        assert abs(result.threshold - DEFAULT_ACCEPT_THRESHOLD) <= _ATOL

    def test_element_results_length(self, result) -> None:
        """element_results list has total_elements entries."""
        assert len(result.element_results) == result.total_elements

    def test_element_results_type(self, result) -> None:
        """Every entry in element_results is an ElementVerificationResult."""
        for er in result.element_results:
            assert isinstance(er, ElementVerificationResult)

    def test_custom_threshold_stored(self) -> None:
        """Custom threshold is stored in the result."""
        sig = generate_signature("m", length=4, seed=_SEED)
        r = verify_signature(sig, threshold=0.5)
        assert abs(r.threshold - 0.5) <= _ATOL


# ===========================================================================
# 4. ELEMENT VERIFICATION RESULT
# ===========================================================================

class TestElementVerificationResult:
    """Per-element verification results have correct structure."""

    @pytest.fixture(scope="class")
    @classmethod
    def element_results(cls):
        sig = generate_signature("elem_msg", length=8, seed=_SEED)
        r = verify_signature(sig)
        return r.element_results

    def test_positions_sequential(self, element_results) -> None:
        """Element positions run 0, 1, 2, …"""
        for i, er in enumerate(element_results):
            assert er.position == i

    def test_p_plus_in_unit_interval(self, element_results) -> None:
        """P(+1) in [0, 1] for every element."""
        for er in element_results:
            assert -_ATOL <= er.p_plus <= 1.0 + _ATOL

    def test_p_minus_in_unit_interval(self, element_results) -> None:
        """P(-1) in [0, 1] for every element."""
        for er in element_results:
            assert -_ATOL <= er.p_minus <= 1.0 + _ATOL

    def test_probs_sum_to_one(self, element_results) -> None:
        """P(+1) + P(-1) == 1 for each element."""
        for er in element_results:
            assert abs(er.p_plus + er.p_minus - 1.0) <= _ATOL

    def test_measured_eigenvalue_pm1(self, element_results) -> None:
        """Measured eigenvalue is +1 or -1."""
        for er in element_results:
            assert er.measured_eigenvalue in (+1, -1)

    def test_match_consistent_with_eigenvalues(self, element_results) -> None:
        """match == (measured_eigenvalue == expected_eigenvalue)."""
        for er in element_results:
            expected = er.measured_eigenvalue == er.expected_eigenvalue
            assert er.match == expected

    def test_legit_all_match_true(self, element_results) -> None:
        """In unmodified verification, all element match flags are True."""
        for er in element_results:
            assert er.match is True

    def test_verify_element_direct(self) -> None:
        """verify_element on an unmodified element returns match=True."""
        sig = generate_signature("direct", length=4, seed=_SEED)
        for element in sig.elements:
            er = verify_element(element)
            assert er.match is True


# ===========================================================================
# 5. THRESHOLD SENSITIVITY
# ===========================================================================

class TestThresholdSensitivity:
    """Score / threshold boundary determines accepted status."""

    def test_threshold_zero_always_accepts(self) -> None:
        """threshold=0.0 always accepts (even all-wrong states)."""
        sig = generate_signature("m", length=4, seed=_SEED)
        others = [get_eigenstate(l).statevector
                  for l in EIGENSTATE_LABELS
                  if l != sig.elements[0].label]
        received = [others[0]] * sig.length
        r = verify_signature(sig, received_statevectors=received, threshold=0.0)
        assert r.accepted is True

    def test_threshold_one_rejects_any_mismatch(self) -> None:
        """threshold=1.0 rejects if even one element mismatches."""
        sig = generate_signature("m", length=4, seed=_SEED)
        # Replace first state with a different one
        first_label = sig.elements[0].label
        alt = next(l for l in EIGENSTATE_LABELS if l != first_label)
        received = [e.statevector.copy() for e in sig.elements]
        received[0] = get_eigenstate(alt).statevector
        r = verify_signature(sig, received_statevectors=received, threshold=1.0)
        assert r.accepted is False

    def test_score_exactly_at_threshold_accepted(self) -> None:
        """score >= threshold means accepted (boundary inclusive)."""
        # Build a 4-element sig where exactly 3/4 match -> score=0.75
        sig = generate_signature("m", length=4, seed=_SEED)
        first_label = sig.elements[0].label
        alt = next(l for l in EIGENSTATE_LABELS if l != first_label)
        received = [e.statevector.copy() for e in sig.elements]
        received[0] = get_eigenstate(alt).statevector
        expected_score = 3 / 4
        r = verify_signature(sig, received_statevectors=received, threshold=expected_score)
        assert r.accepted == (r.verification_score >= expected_score)

    def test_default_threshold_value(self) -> None:
        """DEFAULT_ACCEPT_THRESHOLD is 0.7."""
        assert abs(DEFAULT_ACCEPT_THRESHOLD - 0.7) <= _ATOL


# ===========================================================================
# 6. TELEPORTATION INTEGRATION
# ===========================================================================

class TestTeleportationIntegration:
    """All six Pauli eigenstates teleport with fidelity >= FIDELITY_THRESHOLD."""

    @pytest.mark.parametrize("name,theta,phi", STANDARD_STATES)
    def test_eigenstate_teleports_with_high_fidelity(
        self, name: str, theta: float, phi: float
    ) -> None:
        """Teleportation fidelity >= 0.999999 for each Pauli eigenstate."""
        from quantum.teleportation import FIDELITY_THRESHOLD
        f = calculate_teleportation_fidelity(
            theta, phi, shots=4096, seed=_SEED
        )
        assert f >= FIDELITY_THRESHOLD, (
            f"{name}: teleportation fidelity {f:.10f} < {FIDELITY_THRESHOLD}"
        )
