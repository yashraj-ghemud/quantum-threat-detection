"""
tests/attacks/test_channel_manipulation.py
===========================================
Tests for the ChannelManipulationAttack (Phase 5).

Validates:
- Implements BaseAttack interface
- Does not mutate original input
- Deterministic results with same seed
- Different intensities produce valid outputs
- Channel manipulation produces valid disturbed quantum data
- Statevectors remain normalized after disturbance
- Phase 4 detector receives real attack-generated measurements
- No NaN/inf
- Anomaly score in [0, 1]
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from attacks.base import BaseAttack, SessionMetadata
from attacks.channel_manipulation import ChannelManipulationAttack
from qds.signature import generate_signature
from qds.verification import verify_signature
from security.detector import ThreatDetector


def _make_legit_data(seed=42, length=16):
    sig = generate_signature("test_channel", length=length, seed=seed)
    svs = [e.statevector.copy() for e in sig.elements]
    meta = SessionMetadata(message_id="test_channel", sequence_number=1)
    return sig, svs, meta


def _build_detector(seed=42, length=16, n_baseline=8):
    detector = ThreatDetector(calibration_method="percentile")
    for i in range(n_baseline):
        sig = generate_signature(f"bl_{i}", length=length, seed=seed + i)
        vr = verify_signature(sig)
        detector.add_baseline_session(vr)
    detector.calibrate()
    return detector


class TestChannelInterface:
    def test_is_base_attack(self):
        assert isinstance(ChannelManipulationAttack(seed=42), BaseAttack)

    def test_has_name(self):
        assert ChannelManipulationAttack(seed=42).name == "ChannelManipulationAttack"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            ChannelManipulationAttack(seed=42, mode="invalid")


class TestChannelNoMutation:
    def test_original_statevectors_unchanged(self):
        _, svs, meta = _make_legit_data()
        originals = [sv.copy() for sv in svs]
        attack = ChannelManipulationAttack(seed=42)
        attack.execute(svs, meta, intensity=1.0)
        for orig, current in zip(originals, svs):
            np.testing.assert_array_equal(orig, current)


class TestChannelDeterminism:
    def test_deterministic_with_same_seed(self):
        _, svs1, meta1 = _make_legit_data()
        _, svs2, meta2 = _make_legit_data()
        atk1 = ChannelManipulationAttack(seed=42, mode="depolarizing")
        atk2 = ChannelManipulationAttack(seed=42, mode="depolarizing")
        r1 = atk1.execute(svs1, meta1, intensity=0.5)
        r2 = atk2.execute(svs2, meta2, intensity=0.5)
        for sv1, sv2 in zip(r1.statevectors, r2.statevectors):
            np.testing.assert_array_almost_equal(sv1, sv2)


class TestChannelIntensity:
    @pytest.mark.parametrize("intensity", [0.0, 0.1, 0.25, 0.5, 0.75, 1.0])
    def test_intensity_valid_output(self, intensity):
        _, svs, meta = _make_legit_data()
        attack = ChannelManipulationAttack(seed=42)
        result = attack.execute(svs, meta, intensity=intensity)
        assert len(result.statevectors) == len(svs)
        assert result.intensity == intensity

    def test_intensity_zero_no_change(self):
        _, svs, meta = _make_legit_data()
        originals = [sv.copy() for sv in svs]
        attack = ChannelManipulationAttack(seed=42)
        result = attack.execute(svs, meta, intensity=0.0)
        for orig, out in zip(originals, result.statevectors):
            np.testing.assert_array_equal(orig, out)


class TestChannelQuantumValidity:
    """Channel manipulation must produce valid quantum state data."""

    @pytest.mark.parametrize("mode", ["depolarizing", "dephasing", "both"])
    def test_statevectors_normalized(self, mode):
        _, svs, meta = _make_legit_data()
        attack = ChannelManipulationAttack(seed=42, mode=mode)
        result = attack.execute(svs, meta, intensity=1.0)
        for sv in result.statevectors:
            norm = float(np.linalg.norm(sv))
            assert abs(norm - 1.0) < 1e-9, f"Statevector norm={norm} != 1.0"

    @pytest.mark.parametrize("mode", ["depolarizing", "dephasing", "both"])
    def test_no_nan_inf_in_statevectors(self, mode):
        _, svs, meta = _make_legit_data()
        attack = ChannelManipulationAttack(seed=42, mode=mode)
        result = attack.execute(svs, meta, intensity=1.0)
        for sv in result.statevectors:
            assert not np.any(np.isnan(sv))
            assert not np.any(np.isinf(sv))

    @pytest.mark.parametrize("mode", ["depolarizing", "dephasing", "both"])
    def test_disturbed_positions_recorded(self, mode):
        _, svs, meta = _make_legit_data()
        attack = ChannelManipulationAttack(seed=42, mode=mode)
        result = attack.execute(svs, meta, intensity=1.0)
        positions = result.attack_indicators.get("disturbed_positions", [])
        assert all(0 <= p < len(svs) for p in positions)

    def test_evidence_contains_channel_disturbance(self):
        _, svs, meta = _make_legit_data()
        attack = ChannelManipulationAttack(seed=42, mode="both")
        result = attack.execute(svs, meta, intensity=1.0)
        assert any("channel_disturbance" in e or "channel_manipulation" in e
                    for e in result.evidence)


class TestChannelPhase4:
    def test_detector_receives_channel_manipulation(self):
        sig, svs, meta = _make_legit_data()
        detector = _build_detector()
        attack = ChannelManipulationAttack(seed=42, mode="both")
        result = attack.execute(svs, meta, intensity=1.0)
        vr = verify_signature(sig, received_statevectors=result.statevectors)
        dr = detector.detect(vr)
        assert 0.0 <= dr.anomaly_score <= 1.0
        assert not np.isnan(dr.anomaly_score)
        assert not np.isinf(dr.anomaly_score)

    @pytest.mark.parametrize("intensity", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_no_nan_inf_at_various_intensities(self, intensity):
        sig, svs, meta = _make_legit_data()
        detector = _build_detector()
        _, svs_copy, meta_copy = _make_legit_data()
        attack = ChannelManipulationAttack(seed=42, mode="both")
        result = attack.execute(svs_copy, meta_copy, intensity=intensity)
        vr = verify_signature(sig, received_statevectors=result.statevectors)
        dr = detector.detect(vr)
        assert not np.isnan(dr.anomaly_score)
        assert not np.isinf(dr.anomaly_score)
        assert 0.0 <= dr.anomaly_score <= 1.0
