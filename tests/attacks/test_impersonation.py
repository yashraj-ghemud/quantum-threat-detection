"""
tests/attacks/test_impersonation.py
====================================
Tests for the ImpersonationAttack (Phase 5).

Validates:
- Implements BaseAttack interface
- Does not mutate original input
- Deterministic results with same seed
- Different intensities produce valid outputs
- Impersonation produces unauthorized/mismatched identity context
- Phase 4 detector receives real attack-generated measurements
- No NaN/inf
- Anomaly score in [0, 1]
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from attacks.base import BaseAttack, SessionMetadata
from attacks.impersonation import ImpersonationAttack
from qds.signature import generate_signature
from qds.verification import verify_signature
from security.detector import ThreatDetector


def _make_legit_data(seed=42, length=16):
    sig = generate_signature("test_impersonation", length=length, seed=seed)
    svs = [e.statevector.copy() for e in sig.elements]
    meta = SessionMetadata(
        message_id="test_impersonation",
        sequence_number=1,
        signer_id="signer_alice",
    )
    return sig, svs, meta


def _build_detector(seed=42, length=16, n_baseline=8):
    detector = ThreatDetector(calibration_method="percentile")
    for i in range(n_baseline):
        sig = generate_signature(f"bl_{i}", length=length, seed=seed + i)
        vr = verify_signature(sig)
        detector.add_baseline_session(vr)
    detector.calibrate()
    return detector


class TestImpersonationInterface:
    def test_is_base_attack(self):
        assert isinstance(ImpersonationAttack(seed=42), BaseAttack)

    def test_has_name(self):
        assert ImpersonationAttack(seed=42).name == "ImpersonationAttack"


class TestImpersonationNoMutation:
    def test_original_statevectors_unchanged(self):
        _, svs, meta = _make_legit_data()
        originals = [sv.copy() for sv in svs]
        attack = ImpersonationAttack(seed=42)
        attack.execute(svs, meta, intensity=1.0)
        for orig, current in zip(originals, svs):
            np.testing.assert_array_equal(orig, current)

    def test_original_metadata_unchanged(self):
        _, svs, meta = _make_legit_data()
        orig_signer = meta.signer_id
        attack = ImpersonationAttack(seed=42)
        attack.execute(svs, meta, intensity=1.0)
        assert meta.signer_id == orig_signer


class TestImpersonationDeterminism:
    def test_deterministic_with_same_seed(self):
        _, svs1, meta1 = _make_legit_data()
        _, svs2, meta2 = _make_legit_data()
        atk1 = ImpersonationAttack(seed=42)
        atk2 = ImpersonationAttack(seed=42)
        r1 = atk1.execute(svs1, meta1, intensity=0.5)
        r2 = atk2.execute(svs2, meta2, intensity=0.5)
        for sv1, sv2 in zip(r1.statevectors, r2.statevectors):
            np.testing.assert_array_equal(sv1, sv2)


class TestImpersonationIntensity:
    @pytest.mark.parametrize("intensity", [0.0, 0.1, 0.25, 0.5, 0.75, 1.0])
    def test_intensity_valid_output(self, intensity):
        _, svs, meta = _make_legit_data()
        attack = ImpersonationAttack(seed=42)
        result = attack.execute(svs, meta, intensity=intensity)
        assert len(result.statevectors) == len(svs)
        assert result.intensity == intensity

    def test_intensity_zero_no_change(self):
        _, svs, meta = _make_legit_data()
        originals = [sv.copy() for sv in svs]
        attack = ImpersonationAttack(seed=42)
        result = attack.execute(svs, meta, intensity=0.0)
        for orig, out in zip(originals, result.statevectors):
            np.testing.assert_array_equal(orig, out)


class TestImpersonationIdentity:
    """Impersonation must produce unauthorized/mismatched identity context."""

    def test_signer_id_changed(self):
        _, svs, meta = _make_legit_data()
        attack = ImpersonationAttack(seed=42, impersonator_id="attacker_eve")
        result = attack.execute(svs, meta, intensity=1.0)
        assert result.metadata.signer_id == "attacker_eve"

    def test_evidence_has_identity_mismatch(self):
        _, svs, meta = _make_legit_data()
        attack = ImpersonationAttack(seed=42)
        result = attack.execute(svs, meta, intensity=1.0)
        assert any("identity_mismatch" in e or "identity_context_mismatch" in e
                    for e in result.evidence)

    def test_impersonator_id_in_indicators(self):
        _, svs, meta = _make_legit_data()
        attack = ImpersonationAttack(seed=42, impersonator_id="attacker_eve")
        result = attack.execute(svs, meta, intensity=0.5)
        assert result.attack_indicators["impersonator_id"] == "attacker_eve"
        assert result.attack_indicators["legitimate_signer_id"] == "signer_alice"


class TestImpersonationPhase4:
    def test_detector_receives_impersonation(self):
        sig, svs, meta = _make_legit_data()
        detector = _build_detector()
        attack = ImpersonationAttack(seed=42)
        result = attack.execute(svs, meta, intensity=1.0)
        vr = verify_signature(sig, received_statevectors=result.statevectors)
        dr = detector.detect(vr)
        assert 0.0 <= dr.anomaly_score <= 1.0
        assert not np.isnan(dr.anomaly_score)
        assert not np.isinf(dr.anomaly_score)

    @pytest.mark.parametrize("intensity", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_no_nan_inf(self, intensity):
        sig, svs, meta = _make_legit_data()
        detector = _build_detector()
        _, svs_copy, meta_copy = _make_legit_data()
        attack = ImpersonationAttack(seed=42)
        result = attack.execute(svs_copy, meta_copy, intensity=intensity)
        vr = verify_signature(sig, received_statevectors=result.statevectors)
        dr = detector.detect(vr)
        assert not np.isnan(dr.anomaly_score)
        assert not np.isinf(dr.anomaly_score)
        assert 0.0 <= dr.anomaly_score <= 1.0
