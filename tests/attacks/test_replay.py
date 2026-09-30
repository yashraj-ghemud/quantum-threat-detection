"""
tests/attacks/test_replay.py
==============================
Tests for the ReplayAttack and replay detection (Phase 5).

Validates:
- Implements BaseAttack interface
- Does not mutate original input
- Deterministic results with same seed
- Different intensities produce valid outputs
- Replay reuses old session but fails new-session consistency
- check_replay detects session/sequence/timestamp mismatches
- No NaN/inf
"""

from __future__ import annotations

import copy
import time

import numpy as np
import pytest

from attacks.base import BaseAttack, SessionMetadata
from attacks.replay import ReplayAttack, ReplayCheckResult, check_replay
from qds.signature import generate_signature
from qds.verification import verify_signature
from security.detector import ThreatDetector


def _make_legit_data(seed=42, length=16):
    sig = generate_signature("test_replay", length=length, seed=seed)
    svs = [e.statevector.copy() for e in sig.elements]
    meta = SessionMetadata(
        message_id="test_replay",
        sequence_number=1,
        signer_id="signer_alice",
        verifier_id="verifier_bob",
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


class TestReplayInterface:
    def test_is_base_attack(self):
        assert isinstance(ReplayAttack(seed=42), BaseAttack)

    def test_has_name(self):
        assert ReplayAttack(seed=42).name == "ReplayAttack"


class TestReplayNoMutation:
    def test_original_statevectors_unchanged(self):
        _, svs, meta = _make_legit_data()
        originals = [sv.copy() for sv in svs]
        attack = ReplayAttack(seed=42)
        attack.execute(svs, meta, intensity=1.0)
        for orig, current in zip(originals, svs):
            np.testing.assert_array_equal(orig, current)

    def test_original_metadata_unchanged(self):
        _, svs, meta = _make_legit_data()
        orig_sid = meta.session_id
        orig_seq = meta.sequence_number
        attack = ReplayAttack(seed=42)
        attack.execute(svs, meta, intensity=1.0)
        assert meta.session_id == orig_sid
        assert meta.sequence_number == orig_seq


class TestReplayDeterminism:
    def test_deterministic_with_same_seed(self):
        _, svs1, meta1 = _make_legit_data()
        _, svs2, meta2 = _make_legit_data()
        atk1 = ReplayAttack(seed=42)
        atk2 = ReplayAttack(seed=42)
        r1 = atk1.execute(svs1, meta1, intensity=1.0)
        r2 = atk2.execute(svs2, meta2, intensity=1.0)
        assert r1.metadata.sequence_number == r2.metadata.sequence_number


class TestReplayIntensity:
    @pytest.mark.parametrize("intensity", [0.0, 0.1, 0.25, 0.5, 0.75, 1.0])
    def test_intensity_valid_output(self, intensity):
        _, svs, meta = _make_legit_data()
        attack = ReplayAttack(seed=42)
        result = attack.execute(svs, meta, intensity=intensity)
        assert len(result.statevectors) == len(svs)
        assert result.intensity == intensity

    def test_intensity_zero_no_change(self):
        _, svs, meta = _make_legit_data()
        originals = [sv.copy() for sv in svs]
        attack = ReplayAttack(seed=42)
        result = attack.execute(svs, meta, intensity=0.0)
        for orig, out in zip(originals, result.statevectors):
            np.testing.assert_array_equal(orig, out)


class TestReplaySessionConsistency:
    """Replay must reuse old session but fail consistency checks."""

    def test_replayed_session_fails_check(self):
        _, svs, meta = _make_legit_data()
        attack = ReplayAttack(seed=42, staleness_seconds=120.0)
        result = attack.execute(svs, meta, intensity=1.0)

        # Create expected new-session metadata
        expected = SessionMetadata(
            message_id="test_replay",
            sequence_number=1,
        )

        check = check_replay(
            received=result.metadata,
            expected=expected,
            max_staleness_seconds=60.0,
        )
        assert check.is_replay
        assert len(check.reasons) > 0

    def test_legitimate_session_passes_check(self):
        meta = SessionMetadata(
            message_id="test",
            sequence_number=1,
        )
        expected = copy.deepcopy(meta)
        check = check_replay(received=meta, expected=expected)
        assert not check.is_replay
        assert len(check.reasons) == 0

    def test_session_id_mismatch_detected(self):
        received = SessionMetadata(session_id="old-session", message_id="msg", sequence_number=1)
        expected = SessionMetadata(session_id="new-session", message_id="msg", sequence_number=1)
        # Force matching timestamps
        expected.timestamp = received.timestamp
        check = check_replay(received=received, expected=expected)
        assert check.is_replay
        assert not check.session_id_match

    def test_sequence_mismatch_detected(self):
        now = time.time()
        received = SessionMetadata(message_id="msg", sequence_number=5, timestamp=now)
        expected = SessionMetadata(message_id="msg", sequence_number=10, timestamp=now)
        received.session_id = expected.session_id
        check = check_replay(received=received, expected=expected)
        assert check.is_replay
        assert not check.sequence_valid

    def test_timestamp_staleness_detected(self):
        now = time.time()
        received = SessionMetadata(message_id="msg", sequence_number=1, timestamp=now - 200)
        expected = SessionMetadata(message_id="msg", sequence_number=1, timestamp=now)
        received.session_id = expected.session_id
        check = check_replay(received=received, expected=expected, max_staleness_seconds=60.0)
        assert check.is_replay
        assert not check.timestamp_valid

    def test_evidence_contains_replay_reason(self):
        _, svs, meta = _make_legit_data()
        attack = ReplayAttack(seed=42)
        result = attack.execute(svs, meta, intensity=1.0)
        assert any("replay" in e.lower() for e in result.evidence)


class TestReplayPhase4:
    def test_detector_processes_replay(self):
        sig, svs, meta = _make_legit_data()
        detector = _build_detector()
        attack = ReplayAttack(seed=42)
        result = attack.execute(svs, meta, intensity=1.0)
        vr = verify_signature(sig, received_statevectors=result.statevectors)
        dr = detector.detect(vr)
        assert not np.isnan(dr.anomaly_score)
        assert not np.isinf(dr.anomaly_score)
        assert 0.0 <= dr.anomaly_score <= 1.0
