"""
tests/qds/test_signature.py
=============================
Phase 3 -- QDS Signature generation test suite.
SIH26141 | Blockchain & Cybersecurity.

Categories
----------
1. generate_signature output type and fields
2. Reproducibility -- same seed -> same sequence
3. Signature length -- configurable, default
4. Element fields -- position, basis, eigenvalue, statevector
5. Statevector validity -- norm, dtype
6. Custom label pool
7. Error handling -- bad length, empty pool
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

from qds.pauli_states import EIGENSTATE_LABELS
from qds.signature import (
    DEFAULT_SIGNATURE_LENGTH,
    QDSSignature,
    SignatureElement,
    generate_signature,
    signature_summary,
)

_SEED = 42
_ATOL = 1e-9


# ===========================================================================
# 1. OUTPUT TYPE AND FIELDS
# ===========================================================================

class TestGenerateSignatureOutput:
    """generate_signature returns a correctly shaped QDSSignature."""

    def test_returns_qds_signature(self) -> None:
        """generate_signature returns a QDSSignature."""
        sig = generate_signature("msg_test", length=8, seed=_SEED)
        assert isinstance(sig, QDSSignature)

    def test_signature_id_is_string(self) -> None:
        """signature_id is a non-empty string."""
        sig = generate_signature("msg_test", length=4, seed=_SEED)
        assert isinstance(sig.signature_id, str) and len(sig.signature_id) > 0

    def test_signature_id_unique(self) -> None:
        """Two signatures have different IDs (UUID4)."""
        s1 = generate_signature("m1", length=4, seed=_SEED)
        s2 = generate_signature("m2", length=4, seed=_SEED)
        assert s1.signature_id != s2.signature_id

    def test_message_id_stored(self) -> None:
        """signature.message_id matches the provided message_id."""
        sig = generate_signature("transaction_007", length=4, seed=_SEED)
        assert sig.message_id == "transaction_007"

    def test_seed_stored(self) -> None:
        """signature.seed matches the provided seed."""
        sig = generate_signature("m", length=4, seed=99)
        assert sig.seed == 99

    def test_length_field(self) -> None:
        """signature.length equals the requested length."""
        for n in (1, 4, 8, 16, 32):
            sig = generate_signature("m", length=n, seed=_SEED)
            assert sig.length == n

    def test_elements_list_length(self) -> None:
        """len(signature.elements) equals the requested length."""
        for n in (1, 8, 16):
            sig = generate_signature("m", length=n, seed=_SEED)
            assert len(sig.elements) == n

    def test_default_length(self) -> None:
        """No length argument uses DEFAULT_SIGNATURE_LENGTH."""
        sig = generate_signature("m", seed=_SEED)
        assert sig.length == DEFAULT_SIGNATURE_LENGTH
        assert len(sig.elements) == DEFAULT_SIGNATURE_LENGTH


# ===========================================================================
# 2. REPRODUCIBILITY
# ===========================================================================

class TestReproducibility:
    """Same seed produces identical signature label sequences."""

    def test_same_seed_same_labels(self) -> None:
        """Same seed -> identical label sequence."""
        s1 = generate_signature("msg", length=16, seed=_SEED)
        s2 = generate_signature("msg", length=16, seed=_SEED)
        assert s1.label_sequence() == s2.label_sequence()

    def test_same_seed_different_msg_same_labels(self) -> None:
        """message_id does not affect the state sequence (seed-only)."""
        s1 = generate_signature("msg_A", length=8, seed=_SEED)
        s2 = generate_signature("msg_B", length=8, seed=_SEED)
        assert s1.label_sequence() == s2.label_sequence()

    def test_different_seed_may_differ(self) -> None:
        """Different seeds produce different sequences (almost surely)."""
        s1 = generate_signature("msg", length=16, seed=1)
        s2 = generate_signature("msg", length=16, seed=2)
        # With 16 elements from a pool of 6, almost certainly different
        assert s1.label_sequence() != s2.label_sequence()

    def test_same_seed_same_statevectors(self) -> None:
        """Same seed -> identical statevectors at each position."""
        s1 = generate_signature("msg", length=8, seed=_SEED)
        s2 = generate_signature("msg", length=8, seed=_SEED)
        for e1, e2 in zip(s1.elements, s2.elements):
            assert np.allclose(e1.statevector, e2.statevector, atol=_ATOL)


# ===========================================================================
# 3. SIGNATURE LENGTH
# ===========================================================================

class TestSignatureLength:
    """Configurable length works correctly."""

    @pytest.mark.parametrize("n", [1, 4, 8, 16, 32, 64])
    def test_length_n(self, n) -> None:
        """Signature with length n has exactly n elements."""
        sig = generate_signature("m", length=n, seed=_SEED)
        assert len(sig.elements) == n

    def test_zero_length_raises(self) -> None:
        """length=0 raises ValueError."""
        with pytest.raises(ValueError, match="length must be"):
            generate_signature("m", length=0, seed=_SEED)

    def test_negative_length_raises(self) -> None:
        """Negative length raises ValueError."""
        with pytest.raises(ValueError, match="length must be"):
            generate_signature("m", length=-1, seed=_SEED)


# ===========================================================================
# 4. ELEMENT FIELDS
# ===========================================================================

class TestElementFields:
    """SignatureElement has correct fields."""

    @pytest.fixture(scope="class")
    @classmethod
    def sig(cls) -> QDSSignature:
        return generate_signature("msg_elem", length=16, seed=_SEED)

    def test_elements_are_signature_elements(self, sig) -> None:
        """Every element is a SignatureElement."""
        for e in sig.elements:
            assert isinstance(e, SignatureElement)

    def test_positions_sequential(self, sig) -> None:
        """Positions are 0, 1, 2, ... length-1."""
        for i, e in enumerate(sig.elements):
            assert e.position == i

    def test_labels_from_pool(self, sig) -> None:
        """All labels come from EIGENSTATE_LABELS."""
        valid = set(EIGENSTATE_LABELS)
        for e in sig.elements:
            assert e.label in valid

    def test_basis_in_xyz(self, sig) -> None:
        """All element bases are in {x, y, z}."""
        for e in sig.elements:
            assert e.basis in {"x", "y", "z"}

    def test_eigenvalue_pm1(self, sig) -> None:
        """All eigenvalues are +1 or -1."""
        for e in sig.elements:
            assert e.eigenvalue in (+1, -1)

    def test_statevector_shape(self, sig) -> None:
        """All element statevectors have shape (2,)."""
        for e in sig.elements:
            assert e.statevector.shape == (2,)

    def test_get_element_by_position(self, sig) -> None:
        """get_element(i) returns the element at position i."""
        for i in range(sig.length):
            e = sig.get_element(i)
            assert e.position == i

    def test_get_element_out_of_range_raises(self, sig) -> None:
        """get_element raises IndexError for out-of-range position."""
        with pytest.raises(IndexError):
            sig.get_element(sig.length)

    def test_basis_sequence_length(self, sig) -> None:
        """basis_sequence() returns a list of length == sig.length."""
        assert len(sig.basis_sequence()) == sig.length

    def test_label_sequence_length(self, sig) -> None:
        """label_sequence() returns a list of length == sig.length."""
        assert len(sig.label_sequence()) == sig.length

    def test_eigenvalue_sequence_length(self, sig) -> None:
        """eigenvalue_sequence() returns a list of length == sig.length."""
        assert len(sig.eigenvalue_sequence()) == sig.length


# ===========================================================================
# 5. STATEVECTOR VALIDITY
# ===========================================================================

class TestStatevectorValidity:
    """Every element statevector is normalised and complex."""

    @pytest.fixture(scope="class")
    @classmethod
    def sig(cls) -> QDSSignature:
        return generate_signature("msg_sv", length=16, seed=_SEED)

    def test_all_statevectors_normalised(self, sig) -> None:
        """All element statevectors have unit norm."""
        for e in sig.elements:
            assert abs(np.linalg.norm(e.statevector) - 1.0) <= _ATOL

    def test_signature_validate_method(self, sig) -> None:
        """sig.validate() returns True for a fresh signature."""
        assert sig.validate(atol=_ATOL)

    def test_all_statevectors_complex(self, sig) -> None:
        """All element statevectors are complex-typed."""
        for e in sig.elements:
            assert np.issubdtype(e.statevector.dtype, np.complexfloating)


# ===========================================================================
# 6. CUSTOM LABEL POOL
# ===========================================================================

class TestCustomLabelPool:
    """label_pool restriction limits which states appear."""

    def test_z_basis_only_pool(self) -> None:
        """With pool [|0>, |1>], only Z-basis states appear."""
        sig = generate_signature("m", length=20, seed=_SEED, label_pool=["|0>", "|1>"])
        for e in sig.elements:
            assert e.label in ("|0>", "|1>")

    def test_single_state_pool(self) -> None:
        """Pool of one state -> all elements identical."""
        sig = generate_signature("m", length=8, seed=_SEED, label_pool=["|+>"])
        assert all(e.label == "|+>" for e in sig.elements)

    def test_empty_pool_raises(self) -> None:
        """Empty label_pool raises ValueError."""
        with pytest.raises(ValueError, match="label_pool must not be empty"):
            generate_signature("m", length=4, seed=_SEED, label_pool=[])


# ===========================================================================
# 7. SIGNATURE SUMMARY
# ===========================================================================

class TestSignatureSummary:
    """signature_summary returns non-empty string."""

    def test_summary_is_string(self) -> None:
        """signature_summary returns a str."""
        sig = generate_signature("msg_sum", length=8, seed=_SEED)
        s = signature_summary(sig)
        assert isinstance(s, str) and len(s) > 0

    def test_summary_contains_message_id(self) -> None:
        """Summary text contains the message_id."""
        sig = generate_signature("unique_msg_42", length=4, seed=_SEED)
        assert "unique_msg_42" in signature_summary(sig)
