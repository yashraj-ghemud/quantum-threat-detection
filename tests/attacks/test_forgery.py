"""
tests/attacks/test_forgery.py
==============================
Tests for the ForgeryAttack (Phase 5).

Validates:
- Implements the BaseAttack interface
- Does not mutate original input
- Deterministic results with same seed
- Different intensities produce valid outputs
- Forgery changes controlled signature elements
- Phase 4 detector receives real attack-generated measurements
- No NaN/inf
- Anomaly score in [0, 1]
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from attacks.base import BaseAttack, SessionMetadata
from attacks.forgery import ForgeryAttack
from qds.signature import generate_signature
from qds.verification import verify_signature
from security.detector import ThreatDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_legit_data(seed=42, length=16):
    sig = generate_signature("test_forgery", length=length, seed=seed)
    svs = [e.statevector.copy() for e in sig.elements]
    meta = SessionMetadata(message_id="test_forgery", sequence_number=1)
    return sig, svs, meta


def _build_detector(seed=42, length=16, n_baseline=8):
    detector = ThreatDetector(calibration_method="percentile")
    for i in range(n_baseline):
        sig = generate_signature(f"bl_{i}", length=length, seed=seed + i)
        vr = verify_signature(sig)
        detector.add_baseline_session(vr)
    detector.calibrate()
    return detector


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestForgeryAttackInterface:
    """Test ForgeryAttack implements the common BaseAttack interface."""

    def test_is_base_attack(self):
        attack = ForgeryAttack(seed=42)
        assert isinstance(attack, BaseAttack)

    def test_has_name(self):
        attack = ForgeryAttack(seed=42)
        assert attack.name == "ForgeryAttack"

    def test_has_seed(self):
        attack = ForgeryAttack(seed=123)
        assert attack.seed == 123


class TestForgeryNoMutation:
    """Forgery attacks must not mutate the original input."""

    def test_original_statevectors_unchanged(self):
        _, svs, meta = _make_legit_data()
        originals = [sv.copy() for sv in svs]
        attack = ForgeryAttack(seed=42)
        attack.execute(svs, meta, intensity=1.0)
        for orig, current in zip(originals, svs):
            np.testing.assert_array_equal(orig, current)

    def test_original_metadata_unchanged(self):
        _, svs, meta = _make_legit_data()
        orig_meta = copy.deepcopy(meta)
        attack = ForgeryAttack(seed=42)
        attack.execute(svs, meta, intensity=1.0)
        assert meta.session_id == orig_meta.session_id
        assert meta.message_id == orig_meta.message_id


class TestForgeryDeterminism:
    """Same seed must produce identical results."""

    def test_deterministic_with_same_seed(self):
        _, svs1, meta1 = _make_legit_data()
        _, svs2, meta2 = _make_legit_data()
        atk1 = ForgeryAttack(seed=42)
        atk2 = ForgeryAttack(seed=42)
        r1 = atk1.execute(svs1, meta1, intensity=0.5)
        r2 = atk2.execute(svs2, meta2, intensity=0.5)
        for sv1, sv2 in zip(r1.statevectors, r2.statevectors):
            np.testing.assert_array_equal(sv1, sv2)

    def test_different_seed_different_result(self):
        _, svs1, meta1 = _make_legit_data()
        _, svs2, meta2 = _make_legit_data()
        atk1 = ForgeryAttack(seed=42)
        atk2 = ForgeryAttack(seed=999)
        r1 = atk1.execute(svs1, meta1, intensity=0.5)
        r2 = atk2.execute(svs2, meta2, intensity=0.5)
        # They may differ (not guaranteed, but very likely)
        differs = any(
            not np.allclose(sv1, sv2)
            for sv1, sv2 in zip(r1.statevectors, r2.statevectors)
        )
        assert differs


class TestForgeryIntensity:
    """Different attack intensities produce valid outputs."""

    @pytest.mark.parametrize("intensity", [0.0, 0.1, 0.25, 0.5, 0.75, 1.0])
    def test_intensity_valid_output(self, intensity):
        _, svs, meta = _make_legit_data()
        attack = ForgeryAttack(seed=42)
        result = attack.execute(svs, meta, intensity=intensity)
        assert len(result.statevectors) == len(svs)
        assert result.intensity == intensity
        assert result.attack_name == "ForgeryAttack"

    def test_intensity_zero_no_change(self):
        sig, svs, meta = _make_legit_data()
        originals = [sv.copy() for sv in svs]
        attack = ForgeryAttack(seed=42)
        result = attack.execute(svs, meta, intensity=0.0)
        for orig, out in zip(originals, result.statevectors):
            np.testing.assert_array_equal(orig, out)

    def test_intensity_one_changes_elements(self):
        sig, svs, meta = _make_legit_data()
        originals = [sv.copy() for sv in svs]
        attack = ForgeryAttack(seed=42)
        result = attack.execute(svs, meta, intensity=1.0)
        changed = sum(
            1 for orig, out in zip(originals, result.statevectors)
            if not np.allclose(orig, out)
        )
        # At intensity 1.0, some elements should be changed
        # (not all may change since random could pick the same state)
        assert changed > 0

    def test_invalid_intensity_raises(self):
        _, svs, meta = _make_legit_data()
        attack = ForgeryAttack(seed=42)
        with pytest.raises(ValueError):
            attack.execute(svs, meta, intensity=1.5)
        with pytest.raises(ValueError):
            attack.execute(svs, meta, intensity=-0.1)


class TestForgerySignatureElements:
    """Forgery must change controlled signature elements."""

    def test_forged_positions_recorded(self):
        _, svs, meta = _make_legit_data()
        attack = ForgeryAttack(seed=42)
        result = attack.execute(svs, meta, intensity=0.5)
        positions = result.attack_indicators.get("forged_positions", [])
        assert len(positions) > 0
        assert all(0 <= p < len(svs) for p in positions)

    def test_evidence_explains_forgery(self):
        _, svs, meta = _make_legit_data()
        attack = ForgeryAttack(seed=42)
        result = attack.execute(svs, meta, intensity=0.5)
        assert any("signature_mismatch" in e for e in result.evidence)


class TestForgeryPhase4Integration:
    """Forgery measurements must be processable by Phase 4 detector."""

    def test_detector_receives_forgery(self):
        sig, svs, meta = _make_legit_data()
        detector = _build_detector()
        attack = ForgeryAttack(seed=42)
        result = attack.execute(svs, meta, intensity=1.0)
        vr = verify_signature(sig, received_statevectors=result.statevectors)
        dr = detector.detect(vr)
        assert 0.0 <= dr.anomaly_score <= 1.0
        assert not np.isnan(dr.anomaly_score)
        assert not np.isinf(dr.anomaly_score)

    def test_no_nan_inf_at_various_intensities(self):
        sig, svs, meta = _make_legit_data()
        detector = _build_detector()
        for intensity in [0.0, 0.25, 0.5, 0.75, 1.0]:
            _, svs_copy, meta_copy = _make_legit_data()
            attack = ForgeryAttack(seed=42)
            result = attack.execute(svs_copy, meta_copy, intensity=intensity)
            vr = verify_signature(sig, received_statevectors=result.statevectors)
            dr = detector.detect(vr)
            assert not np.isnan(dr.anomaly_score)
            assert not np.isinf(dr.anomaly_score)
            assert 0.0 <= dr.anomaly_score <= 1.0
