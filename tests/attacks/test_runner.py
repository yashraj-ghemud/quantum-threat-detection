"""
tests/attacks/test_runner.py
=============================
Tests for the AttackRunner (Phase 5).

Validates:
- Runner executes all attack scenarios
- Generates legitimate baseline unchanged
- Phase 4 detector receives real attack-generated measurements
- Structured results are returned
- No NaN/inf
- Anomaly scores in [0, 1]
"""

from __future__ import annotations

import numpy as np
import pytest

from attacks.runner import AttackRunner, AttackScenarioResult
from attacks.forgery import ForgeryAttack
from attacks.impersonation import ImpersonationAttack
from attacks.replay import ReplayAttack
from attacks.unauthorized_verification import UnauthorizedVerificationAttack
from attacks.channel_manipulation import ChannelManipulationAttack


# Use small signature and baseline for speed
_SIG_LEN = 16
_N_BASELINE = 6
_SEED = 42


@pytest.fixture(scope="module")
def runner():
    """Shared runner for all test_runner tests (module-scoped for speed)."""
    return AttackRunner(
        sig_length=_SIG_LEN,
        n_baseline=_N_BASELINE,
        seed=_SEED,
    )


class TestRunnerLegitimate:
    def test_legitimate_session(self, runner):
        result = runner.run_legitimate(seed_offset=0)
        assert isinstance(result, AttackScenarioResult)
        assert result.attack_type == "LEGITIMATE"
        assert result.detection_status == "NOT_APPLICABLE"
        assert result.authorization_status == "AUTHORIZED"
        assert 0.0 <= result.anomaly_score <= 1.0
        assert not np.isnan(result.anomaly_score)


class TestRunnerAttacks:
    def test_forgery_attack(self, runner):
        attack = ForgeryAttack(seed=42)
        result = runner.run_attack(attack, "FORGERY", intensity=1.0)
        assert isinstance(result, AttackScenarioResult)
        assert result.attack_type == "FORGERY"
        assert 0.0 <= result.anomaly_score <= 1.0
        assert not np.isnan(result.anomaly_score)

    def test_impersonation_attack(self, runner):
        attack = ImpersonationAttack(seed=42)
        result = runner.run_attack(attack, "IMPERSONATION", intensity=1.0)
        assert isinstance(result, AttackScenarioResult)
        assert result.attack_type == "IMPERSONATION"
        assert 0.0 <= result.anomaly_score <= 1.0

    def test_replay_attack(self, runner):
        attack = ReplayAttack(seed=42)
        result = runner.run_attack(attack, "REPLAY", intensity=1.0)
        assert isinstance(result, AttackScenarioResult)
        assert result.attack_type == "REPLAY"
        # Replay should be detected via consistency checks
        assert result.replay_detected is True

    def test_unauthorized_attack(self, runner):
        attack = UnauthorizedVerificationAttack(seed=42)
        result = runner.run_attack(attack, "UNAUTHORIZED_VERIFICATION", intensity=1.0)
        assert isinstance(result, AttackScenarioResult)
        assert result.attack_type == "UNAUTHORIZED_VERIFICATION"
        assert result.authorization_status == "UNAUTHORIZED"
        assert result.detection_status == "DETECTED"

    def test_channel_manipulation_attack(self, runner):
        attack = ChannelManipulationAttack(seed=42, mode="both")
        result = runner.run_attack(attack, "CHANNEL_MANIPULATION", intensity=1.0)
        assert isinstance(result, AttackScenarioResult)
        assert result.attack_type == "CHANNEL_MANIPULATION"
        assert 0.0 <= result.anomaly_score <= 1.0


class TestRunnerAllScenarios:
    """Runner must execute all attack types."""

    def test_all_scenarios_run(self, runner):
        results = []
        results.append(runner.run_legitimate())
        results.append(runner.run_attack(ForgeryAttack(seed=42), "FORGERY", intensity=0.5))
        results.append(runner.run_attack(ImpersonationAttack(seed=42), "IMPERSONATION", intensity=0.5))
        results.append(runner.run_attack(ReplayAttack(seed=42), "REPLAY", intensity=0.5))
        results.append(runner.run_attack(
            UnauthorizedVerificationAttack(seed=42), "UNAUTHORIZED_VERIFICATION", intensity=0.5
        ))
        results.append(runner.run_attack(
            ChannelManipulationAttack(seed=42), "CHANNEL_MANIPULATION", intensity=0.5
        ))
        assert len(results) == 6
        types = {r.attack_type for r in results}
        assert "LEGITIMATE" in types
        assert "FORGERY" in types
        assert "IMPERSONATION" in types
        assert "REPLAY" in types
        assert "UNAUTHORIZED_VERIFICATION" in types
        assert "CHANNEL_MANIPULATION" in types


class TestRunnerNumericalValidity:
    @pytest.mark.parametrize("intensity", [0.0, 0.5, 1.0])
    def test_no_nan_inf_forgery(self, runner, intensity):
        result = runner.run_attack(ForgeryAttack(seed=42), "FORGERY", intensity=intensity)
        assert not np.isnan(result.anomaly_score)
        assert not np.isinf(result.anomaly_score)
        assert 0.0 <= result.anomaly_score <= 1.0

    @pytest.mark.parametrize("intensity", [0.0, 0.5, 1.0])
    def test_no_nan_inf_channel(self, runner, intensity):
        result = runner.run_attack(
            ChannelManipulationAttack(seed=42), "CHANNEL_MANIPULATION", intensity=intensity
        )
        assert not np.isnan(result.anomaly_score)
        assert not np.isinf(result.anomaly_score)
        assert 0.0 <= result.anomaly_score <= 1.0
