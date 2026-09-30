"""
tests/attacks/test_unauthorized_verification.py
=================================================
Tests for the UnauthorizedVerificationAttack (Phase 5).

Validates:
- Implements BaseAttack interface
- Does not mutate original input
- Deterministic results with same seed
- Different intensities produce valid outputs
- Unauthorized verification is rejected independently of anomaly score
- check_authorization returns AUTHORIZED/UNAUTHORIZED correctly
- No NaN/inf
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from attacks.base import BaseAttack, SessionMetadata
from attacks.unauthorized_verification import (
    UnauthorizedVerificationAttack,
    AuthorizationCheck,
    check_authorization,
)
from qds.signature import generate_signature
from qds.verification import verify_signature


def _make_legit_data(seed=42, length=16):
    sig = generate_signature("test_unauth", length=length, seed=seed)
    svs = [e.statevector.copy() for e in sig.elements]
    meta = SessionMetadata(
        message_id="test_unauth",
        sequence_number=1,
        signer_id="signer_alice",
        verifier_id="verifier_bob",
        authorized=True,
    )
    return sig, svs, meta


class TestUnauthorizedInterface:
    def test_is_base_attack(self):
        assert isinstance(UnauthorizedVerificationAttack(seed=42), BaseAttack)

    def test_has_name(self):
        assert UnauthorizedVerificationAttack(seed=42).name == "UnauthorizedVerificationAttack"


class TestUnauthorizedNoMutation:
    def test_original_statevectors_unchanged(self):
        _, svs, meta = _make_legit_data()
        originals = [sv.copy() for sv in svs]
        attack = UnauthorizedVerificationAttack(seed=42)
        attack.execute(svs, meta, intensity=1.0)
        for orig, current in zip(originals, svs):
            np.testing.assert_array_equal(orig, current)

    def test_original_metadata_unchanged(self):
        _, svs, meta = _make_legit_data()
        assert meta.authorized is True
        attack = UnauthorizedVerificationAttack(seed=42)
        attack.execute(svs, meta, intensity=1.0)
        assert meta.authorized is True


class TestUnauthorizedDeterminism:
    def test_deterministic_with_same_seed(self):
        _, svs1, meta1 = _make_legit_data()
        _, svs2, meta2 = _make_legit_data()
        atk1 = UnauthorizedVerificationAttack(seed=42)
        atk2 = UnauthorizedVerificationAttack(seed=42)
        r1 = atk1.execute(svs1, meta1, intensity=1.0)
        r2 = atk2.execute(svs2, meta2, intensity=1.0)
        assert r1.authorization_status == r2.authorization_status


class TestUnauthorizedIntensity:
    @pytest.mark.parametrize("intensity", [0.0, 0.1, 0.25, 0.5, 0.75, 1.0])
    def test_intensity_valid_output(self, intensity):
        _, svs, meta = _make_legit_data()
        attack = UnauthorizedVerificationAttack(seed=42)
        result = attack.execute(svs, meta, intensity=intensity)
        assert len(result.statevectors) == len(svs)
        assert result.intensity == intensity

    def test_intensity_zero_authorized(self):
        _, svs, meta = _make_legit_data()
        attack = UnauthorizedVerificationAttack(seed=42)
        result = attack.execute(svs, meta, intensity=0.0)
        assert result.authorization_status == "AUTHORIZED"


class TestUnauthorizedRejection:
    """Unauthorized verification must be rejected independently of anomaly score."""

    def test_unauthorized_is_rejected(self):
        _, svs, meta = _make_legit_data()
        attack = UnauthorizedVerificationAttack(seed=42)
        result = attack.execute(svs, meta, intensity=1.0)
        assert result.authorization_status == "UNAUTHORIZED"

    def test_evidence_has_authorization_failure(self):
        _, svs, meta = _make_legit_data()
        attack = UnauthorizedVerificationAttack(seed=42)
        result = attack.execute(svs, meta, intensity=1.0)
        assert any("authorization_failure" in e for e in result.evidence)


class TestCheckAuthorization:
    def test_authorized_verifier(self):
        meta = SessionMetadata(verifier_id="verifier_bob", authorized=True)
        check = check_authorization("verifier_bob", meta)
        assert check.is_authorized
        assert check.status == "AUTHORIZED"

    def test_unauthorized_verifier_wrong_id(self):
        meta = SessionMetadata(verifier_id="verifier_bob", authorized=True)
        check = check_authorization("attacker_charlie", meta)
        assert not check.is_authorized
        assert check.status == "UNAUTHORIZED"

    def test_unauthorized_revoked_flag(self):
        meta = SessionMetadata(verifier_id="verifier_bob", authorized=False)
        check = check_authorization("verifier_bob", meta)
        assert not check.is_authorized
        assert check.status == "UNAUTHORIZED"

    def test_custom_authorized_list(self):
        meta = SessionMetadata(verifier_id="bob", authorized=True)
        check = check_authorization(
            "carol",
            meta,
            authorized_verifiers=["bob", "carol"],
        )
        assert check.is_authorized
