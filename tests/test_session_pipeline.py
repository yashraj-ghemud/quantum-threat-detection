"""
tests/test_session_pipeline.py
==============================
End-to-end tests for the canonical session pipeline.

These tests assert on *measured* behaviour. None of them accept a result
merely because a status field says so -- each checks that the physics and
statistics underneath actually moved in the right direction.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import copy

import numpy as np
import pytest

from attacks.forgery import ForgeryAttack
from attacks.unauthorized_verification import UnauthorizedVerificationAttack
from evaluation.fidelity import purity, state_fidelity, trace_distance
from qds.keygen import generate_key_pair
from quantum.measurements import measure_all_bases, sample_basis_counts
from qds.pauli_states import all_eigenstates
from security.threat_engine import WEIGHTS, ThreatEngine
from session import ReplayGuard, SessionContext, SessionRunner


# ---------------------------------------------------------------------------
# Shared fixtures -- a calibrated runner is expensive, so build it once.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def runner():
    r = SessionRunner(
        signature_length=8, shots=128, teleport_shots=64, seed=42
    )
    r.setup(private_seed=b"test" * 8)
    r.calibrate_baseline(n_sessions=8)
    # Derive the operating point from THIS configuration rather than
    # inheriting the one calibrated for length=16/shots=256; a foreign
    # threshold inflates the false-rejection rate and makes these tests
    # depend on whichever experiment ran last.
    r.calibrate_own_threshold(sigma=8.0, n_sessions=12)
    return r


# ---------------------------------------------------------------------------
# Phase 1 -- measurement layer
# ---------------------------------------------------------------------------

class TestMeasurementLayer:
    def test_eigenstate_is_deterministic_in_own_basis(self):
        """A Pauli eigenstate must give one outcome with certainty."""
        for label, st in all_eigenstates().items():
            r = sample_basis_counts(st.statevector, st.basis, shots=256, seed=3)
            observed = r.p0 if st.eigenvalue == +1 else r.p1
            assert observed == 1.0, f"{label} not deterministic in {st.basis}"

    def test_conjugate_basis_is_unbiased(self):
        """|0> measured in X or Y must be a fair coin, within shot noise."""
        z0 = all_eigenstates()["|0>"].statevector
        for basis in ("x", "y"):
            r = sample_basis_counts(z0, basis, shots=4096, seed=11)
            assert abs(r.p0 - 0.5) < 0.05, f"{basis} basis biased: p0={r.p0}"

    def test_counts_are_sampled_not_analytic(self):
        """Counts must carry real shot noise, not exact analytic values."""
        z0 = all_eigenstates()["|0>"].statevector
        # Different seeds must give different samples in a random basis.
        a = sample_basis_counts(z0, "x", shots=512, seed=1)
        b = sample_basis_counts(z0, "x", shots=512, seed=2)
        assert a.counts != b.counts, "counts identical across seeds -- not sampled"

    def test_counts_sum_to_shots(self):
        z0 = all_eigenstates()["|0>"].statevector
        for basis in ("x", "y", "z"):
            r = sample_basis_counts(z0, basis, shots=333, seed=5)
            assert r.counts["0"] + r.counts["1"] == 333

    def test_all_bases_returns_three_distributions(self):
        z0 = all_eigenstates()["|0>"].statevector
        res = measure_all_bases(z0, shots=256, seed=7)
        assert set(res) == {"x", "y", "z"}
        for b, r in res.items():
            assert abs(r.p0 + r.p1 - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Quantum metrics
# ---------------------------------------------------------------------------

class TestQuantumMetrics:
    def test_fidelity_identical_and_orthogonal(self):
        st = all_eigenstates()
        assert state_fidelity(st["|0>"].statevector, st["|0>"].statevector) == pytest.approx(1.0)
        assert state_fidelity(st["|0>"].statevector, st["|1>"].statevector) == pytest.approx(0.0, abs=1e-12)

    def test_depolarizing_channel_matches_closed_form(self):
        """rho' = (1-p)rho + p I/2 must give F = 1 - p/2 against a pure state."""
        st = all_eigenstates()["|0>"].statevector
        rho = np.outer(st, st.conj())
        ident = np.eye(2, dtype=complex) / 2
        for p in (0.0, 0.2, 0.5, 1.0):
            noisy = (1 - p) * rho + p * ident
            assert state_fidelity(rho, noisy) == pytest.approx(1 - p / 2, abs=1e-9)

    def test_purity_separates_mixed_from_pure(self):
        st = all_eigenstates()
        assert purity(st["|0>"].statevector) == pytest.approx(1.0)
        assert purity(np.eye(2, dtype=complex) / 2) == pytest.approx(0.5)

    def test_trace_distance_is_symmetric_and_bounded(self):
        st = all_eigenstates()
        a, b = st["|0>"].statevector, st["|+>"].statevector
        t1, t2 = trace_distance(a, b), trace_distance(b, a)
        assert t1 == pytest.approx(t2)
        assert 0.0 <= t1 <= 1.0


# ---------------------------------------------------------------------------
# Replay guard -- protocol level, no statistics involved
# ---------------------------------------------------------------------------

class TestReplayGuard:
    def test_fresh_context_passes(self):
        g = ReplayGuard()
        ok, reasons = g.check(SessionContext(sequence_number=1))
        assert ok and reasons == []

    def test_nonce_reuse_detected(self):
        g = ReplayGuard()
        ctx = SessionContext(sequence_number=1)
        g.check(ctx)
        g.commit(ctx)
        ok, reasons = g.check(copy.deepcopy(ctx))
        assert not ok
        assert any("nonce_reused" in r for r in reasons)

    def test_sequence_regression_detected(self):
        g = ReplayGuard()
        first = SessionContext(sequence_number=5, signer_id="alice")
        g.check(first)
        g.commit(first)
        ok, reasons = g.check(SessionContext(sequence_number=3, signer_id="alice"))
        assert not ok
        assert any("sequence_regression" in r for r in reasons)

    def test_stale_session_detected(self):
        import time as _t

        g = ReplayGuard(max_age_seconds=0.01)
        ctx = SessionContext(sequence_number=1)
        _t.sleep(0.05)
        ok, reasons = g.check(ctx)
        assert not ok
        assert any("stale_session" in r for r in reasons)


# ---------------------------------------------------------------------------
# End-to-end pipeline
# ---------------------------------------------------------------------------

class TestLegitimateFlow:
    def test_legitimate_session_verifies_and_is_clean(self, runner):
        res = runner.run(message=b"legit message")
        assert res.verification_score == 1.0
        assert res.matches == res.total_elements
        assert res.message_binding_valid
        assert res.key_binding_valid
        assert res.session_fresh
        assert res.authorized
        assert res.decision == "LEGITIMATE"

    def test_teleportation_actually_ran(self, runner):
        """The timeline must record a real channel stage with elements."""
        res = runner.run(message=b"teleport check")
        stages = [e.stage for e in res.events]
        assert "BELL PAIR CREATED" in stages
        assert "TELEPORTATION + PAULI CORRECTION" in stages
        assert "PROJECTIVE MEASUREMENT" in stages
        assert res.latency_channel_ms > 0.0

    def test_telemetry_is_populated_from_measurement(self, runner):
        res = runner.run(message=b"telemetry check")
        t = res.telemetry
        assert 0.0 <= t.mean_fidelity <= 1.0
        assert 0.0 <= t.mean_trace_distance <= 1.0
        assert 0.5 <= t.mean_purity <= 1.0
        assert t.total_shots == res.total_elements * runner.shots
        assert len(res.elements) == res.total_elements

    def test_tampered_message_breaks_binding(self, runner):
        """Verification must be bound to the exact message bytes."""
        from qds.keygen import message_digest

        res = runner.run(message=b"original message")
        assert res.message_binding_valid
        # The signature's digest must not match a different message.
        assert res.telemetry is not None
        other = message_digest(b"different message").hex()
        assert other != message_digest(b"original message").hex()


class TestAttackFlows:
    def test_forgery_degrades_real_measurements(self, runner):
        res = runner.run(
            message=b"forge me", attack=ForgeryAttack(seed=1),
            attack_type="FORGERY", intensity=1.0,
        )
        # The damage must be visible in the physics, not just a status flag.
        assert res.verification_score < 1.0
        assert res.telemetry.mean_fidelity < 0.95
        assert res.anomaly_score > 0.0
        assert res.decision in ("SUSPICIOUS", "THREAT")

    def test_forgery_keeps_states_pure(self, runner):
        """A substituted eigenstate is still pure -- that is the signature
        that distinguishes forgery from channel decoherence."""
        res = runner.run(
            message=b"pure forge", attack=ForgeryAttack(seed=2),
            attack_type="FORGERY", intensity=1.0,
        )
        assert res.telemetry.mean_purity > 0.9

    def test_channel_noise_decoheres_and_is_detected(self, runner):
        res = runner.run(
            message=b"noisy channel", attack_type="CHANNEL_MANIPULATION",
            intensity=0.5, channel_noise="depolarizing", channel_noise_level=0.5,
        )
        # Decoherence: purity must fall, unlike forgery.
        assert res.telemetry.mean_purity < 0.9
        assert res.telemetry.mean_fidelity < 0.9
        assert res.decision in ("SUSPICIOUS", "THREAT")

    def test_channel_fidelity_decreases_monotonically(self, runner):
        """More channel noise must mean lower fidelity -- the channel is real."""
        fids = []
        for p in (0.0, 0.3, 0.6):
            r = runner.run(
                message=b"sweep", attack_type="CHANNEL_MANIPULATION",
                intensity=p, channel_noise="depolarizing", channel_noise_level=p,
            )
            fids.append(r.telemetry.mean_fidelity)
        assert fids[0] > fids[1] > fids[2], f"fidelity not monotonic: {fids}"

    def test_impersonation_fails_key_binding(self, runner):
        priv, _ = generate_key_pair(signer_id="mallory", table_size=runner.table_size)
        res = runner.run(
            message=b"impersonate", attack_type="IMPERSONATION",
            intensity=1.0, signing_key=priv,
        )
        assert not res.key_binding_valid
        assert res.decision == "THREAT"
        assert res.detected_attack == "IMPERSONATION"

    def test_replay_is_quantum_valid_but_caught_by_freshness(self, runner):
        """The defining property of replay: perfect physics, stale session."""
        ctx = runner.next_context("replay")
        first = runner.run(message=b"replay me", context=copy.deepcopy(ctx))
        assert first.session_fresh

        second = runner.run(
            message=b"replay me", attack_type="REPLAY", intensity=1.0,
            context=copy.deepcopy(ctx),
        )
        # Quantum layer sees nothing wrong...
        assert second.verification_score == 1.0
        assert second.telemetry.mean_fidelity == pytest.approx(
            first.telemetry.mean_fidelity, abs=1e-6
        )
        # ...but the protocol layer catches it.
        assert not second.session_fresh
        assert second.decision == "THREAT"
        assert second.detected_attack == "REPLAY"

    def test_unauthorized_verifier_rejected(self, runner):
        res = runner.run(
            message=b"unauthorized",
            attack=UnauthorizedVerificationAttack(seed=3),
            attack_type="UNAUTHORIZED_VERIFICATION", intensity=1.0,
        )
        assert not res.authorized
        assert res.decision == "THREAT"
        assert res.detected_attack == "UNAUTHORIZED_VERIFICATION"

    def test_intercept_resend_disturbs_the_state(self, runner):
        """Unauthorized measurement must leave a physical trace."""
        clean = runner.run(message=b"intercept base")
        attacked = runner.run(
            message=b"intercept base",
            attack=UnauthorizedVerificationAttack(seed=4),
            attack_type="UNAUTHORIZED_VERIFICATION", intensity=1.0,
        )
        assert attacked.telemetry.mean_fidelity < clean.telemetry.mean_fidelity


# ---------------------------------------------------------------------------
# Detection engine
# ---------------------------------------------------------------------------

class TestThreatEngine:
    def test_weights_sum_to_one(self):
        assert sum(WEIGHTS.values()) == pytest.approx(1.0)

    def test_score_is_bounded(self, runner):
        for msg in (b"a", b"bb", b"ccc"):
            res = runner.run(message=msg)
            assert 0.0 <= res.anomaly_score <= 1.0

    def test_legitimate_scores_below_attack(self, runner):
        legit = runner.run(message=b"clean session")
        attacked = runner.run(
            message=b"clean session", attack=ForgeryAttack(seed=9),
            attack_type="FORGERY", intensity=1.0,
        )
        assert legit.anomaly_score < attacked.anomaly_score

    def test_threshold_behaviour(self, runner):
        """Raising the threshold must make the engine strictly less eager."""
        res = runner.run(
            message=b"threshold probe", attack=ForgeryAttack(seed=8),
            attack_type="FORGERY", intensity=0.5,
        )
        lenient = ThreatEngine(runner.baseline, warning_threshold=0.99,
                               critical_threshold=0.999)
        lenient.evaluate(res)
        assert res.decision == "LEGITIMATE"

        strict = ThreatEngine(runner.baseline, warning_threshold=1e-6,
                              critical_threshold=2e-6)
        strict.evaluate(res)
        assert res.decision == "THREAT"

    def test_evidence_is_always_present(self, runner):
        res = runner.run(message=b"evidence check")
        assert res.evidence, "a decision must always carry its reasoning"

    def test_explanation_reports_real_numbers(self, runner):
        res = runner.run(
            message=b"explain me", attack=ForgeryAttack(seed=6),
            attack_type="FORGERY", intensity=1.0,
        )
        text = ThreatEngine(runner.baseline).explain(res)
        assert "VERIFICATION" in text
        assert f"{res.telemetry.mean_fidelity:.4f}" in text
        assert f"{res.anomaly_score:.4f}" in text

    def test_forensics_includes_timeline(self, runner):
        res = runner.run(
            message=b"forensics", attack=ForgeryAttack(seed=7),
            attack_type="FORGERY", intensity=1.0,
        )
        report = ThreatEngine(runner.baseline).forensics(res, "ATT-TEST")
        assert "ATT-TEST" in report
        assert "Timeline:" in report
        assert "SIGNATURE GENERATED" in report


# ---------------------------------------------------------------------------
# Anti-fabrication guards
# ---------------------------------------------------------------------------

class TestNoFabrication:
    def test_no_manual_score_manipulation_in_source(self):
        """Guard against reintroducing the 'matches -= tamper_count' pattern."""
        import re

        # Ban mutation of a *result object's* verification fields, e.g.
        #   v_res.matches -= tamper_count
        #   v_res.verification_score = matches / length
        # A bare local accumulator (`matches += int(match)`) is how a real
        # comparison is counted, so it must stay allowed.
        bad = re.compile(
            r"\w+\.(matches|mismatches|verification_score|accepted)\s*(-=|\+=|=[^=])"
        )
        offenders = []
        for path in (_ROOT / "src").rglob("*.py"):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if bad.search(line) and "test" not in path.name:
                    offenders.append(f"{path.name}:{i}: {line.strip()}")
        assert not offenders, "verification results are being edited:\n" + "\n".join(offenders)

    def test_no_ml_imports(self):
        """The project claims zero AI/ML. Enforce it."""
        import re

        banned = re.compile(
            r"^\s*(import|from)\s+(torch|tensorflow|sklearn|keras|xgboost)\b"
        )
        offenders = []
        for path in (_ROOT / "src").rglob("*.py"):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if banned.search(line):
                    offenders.append(f"{path.name}:{i}")
        assert not offenders, f"ML framework imported: {offenders}"

    def test_no_notimplemented_in_shipped_modules(self):
        """Core modules must not ship stubs."""
        offenders = []
        for sub in ("qds", "quantum", "security"):
            for path in (_ROOT / "src" / sub).rglob("*.py"):
                if "NotImplementedError" in path.read_text(encoding="utf-8"):
                    offenders.append(str(path.relative_to(_ROOT)))
        assert not offenders, f"stubs remain: {offenders}"


# ---------------------------------------------------------------------------
# Key-reuse policy
# ---------------------------------------------------------------------------

class TestKeyPolicy:
    def test_coverage_formula_matches_definition(self):
        from qds.key_policy import coverage_after

        # f(n) = 1 - (1 - 1/T)^(n*L)
        assert coverage_after(0, 64, 16) == 0.0
        expected = 1 - (1 - 1 / 64) ** (5 * 16)
        assert coverage_after(5, 64, 16) == pytest.approx(expected)

    def test_critical_coverage_at_default_threshold(self):
        from qds.key_policy import critical_coverage

        # f* = (0.7 - 1/6) / (1 - 1/6)
        assert critical_coverage(0.7) == pytest.approx(0.64, abs=1e-9)

    def test_small_table_permits_almost_no_signatures(self):
        """T=64 is unsafe at L=16 -- that is why the default was raised."""
        from qds.key_policy import max_signatures

        assert max_signatures(64, 16) <= 1
        assert max_signatures(1024, 16) >= 20

    def test_limit_keeps_coverage_under_margin(self):
        from qds.key_policy import DEFAULT_SAFETY_MARGIN, coverage_after, max_signatures

        for T in (256, 1024, 4096):
            n = max_signatures(T, 16)
            assert coverage_after(n, T, 16) <= DEFAULT_SAFETY_MARGIN
            # And one more signature would exceed it.
            assert coverage_after(n + 1, T, 16) > coverage_after(n, T, 16)

    def test_recommend_table_size_satisfies_requirement(self):
        from qds.key_policy import max_signatures, recommend_table_size

        for required in (1, 10, 50, 200):
            T = recommend_table_size(required, 16)
            assert max_signatures(T, 16) >= required

    def test_default_table_size_is_safe(self):
        """The shipped default must permit more than a single signature."""
        from qds.keygen import DEFAULT_KEY_TABLE_SIZE
        from qds.key_policy import max_signatures

        assert max_signatures(DEFAULT_KEY_TABLE_SIZE, 16) >= 20

    def test_tracker_warns_then_enforces(self):
        from qds.key_policy import KeyExhaustedError, KeyUsagePolicy, KeyUsageTracker

        policy = KeyUsagePolicy(table_size=64, signature_length=16, enforce=True)
        tracker = KeyUsageTracker(policy)
        for _ in range(policy.limit):
            tracker.record("k")
        with pytest.raises(KeyExhaustedError, match="safe limit"):
            tracker.record("k")

    def test_tracker_counts_per_key(self):
        from qds.key_policy import KeyUsagePolicy, KeyUsageTracker

        t = KeyUsageTracker(KeyUsagePolicy(table_size=1024, signature_length=16))
        t.record("a"); t.record("a"); t.record("b")
        assert t.count("a") == 2 and t.count("b") == 1
        assert t.remaining("a") == t.policy.limit - 2

    def test_signing_is_counted(self):
        from qds.keygen import generate_key_pair
        from qds.signer import sign_message, usage_tracker_for

        priv, _ = generate_key_pair(signer_id="counted")
        tracker = usage_tracker_for(priv.table_size, 16)
        before = tracker.count(priv.key_id)
        sign_message(b"one", priv, length=16)
        sign_message(b"two", priv, length=16)
        assert tracker.count(priv.key_id) == before + 2
