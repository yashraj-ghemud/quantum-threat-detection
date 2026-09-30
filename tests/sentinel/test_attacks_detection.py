"""Every catalog attack is detected and correctly classified; honest traffic raises no alarms."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sentinel.adversary.catalog import CATALOG, AttackSpec, AttackSpecError, validate_spec
from sentinel.network import build_world

REFERENCE = {
    "channel.depolarize": (0.5, {}), "channel.dephase": (0.5, {"axis": "z"}),
    "channel.amplitude_damp": (0.5, {}), "channel.coherent_rotation": (0.5, {"axis": "z"}),
    "channel.intercept_resend": (0.5, {"basis": "random"}), "channel.pauli_frame": (0.3, {"bits": "m1"}),
    "unauthorized.key_harvest_mitm": (0.5, {}), "unauthorized.non_recipient": (0.5, {"verifier": "erin"}),
    "forgery.blind": (0.5, {"mode": "modified_message"}), "forgery.insider": (0.5, {"mode": "modified_message"}),
    "forgery.bit_flip_oracle": (0.5, {"k": 1}), "impersonation.identity_swap": (0.5, {}),
    "impersonation.keyless": (0.5, {}), "replay.resubmit": (0.5, {}), "replay.forward_replay": (0.5, {}),
    "replay.delayed": (0.5, {"delay_s": 300}), "repudiation.inconsistent_keys": (0.5, {}),
}
EXPECTED_SUBTYPE = {
    "channel.amplitude_damp": "amplitude_damping", "channel.coherent_rotation": "coherent_rotation",
    "channel.pauli_frame": "classical_frame", "unauthorized.key_harvest_mitm": "key_harvest",
    "unauthorized.non_recipient": "non_recipient", "forgery.blind": "external_blind", "forgery.insider": "insider",
    "forgery.bit_flip_oracle": "oracle_k_bits", "impersonation.identity_swap": "identity_swap",
    "impersonation.keyless": "keyless", "replay.resubmit": "resubmission", "replay.forward_replay": "forward_replay",
    "replay.delayed": "delay", "repudiation.inconsistent_keys": "inconsistent_keys",
}


def test_catalog_complete():
    assert len(CATALOG) == 17
    assert set(REFERENCE) == {e["id"] for e in CATALOG}
    cats = {e["category"] for e in CATALOG}
    assert cats == {"FORGERY", "IMPERSONATION", "REPLAY", "UNAUTHORIZED_VERIFICATION", "CHANNEL_MANIPULATION", "REPUDIATION"}
    with pytest.raises(AttackSpecError):
        validate_spec(AttackSpec("channel.dephase", 1.5))
    with pytest.raises(AttackSpecError):
        validate_spec(AttackSpec("channel.dephase", 0.5, {"axis": "w"}))


@pytest.mark.parametrize("attack_id", sorted(REFERENCE))
def test_attack_detected_and_classified(attack_id):
    world = build_world(preset="analysis", seed=hash(attack_id) % 10_000)
    intensity, params = REFERENCE[attack_id]
    run = world.run_attack(AttackSpec(attack_id, intensity, params))
    entry = run.entry
    assert run.detected, run.report()["notes"]
    assert run.correctly_classified, (run.assessment.classification.category, entry["category"])
    if attack_id in EXPECTED_SUBTYPE:
        assert run.assessment.classification.subtype == EXPECTED_SUBTYPE[attack_id]
    rep = run.report()
    assert rep["detected"] and rep["correctly_classified"]


def test_insider_attribution_names_the_insider():
    world = build_world(preset="analysis", seed=77)
    run = world.run_attack(AttackSpec("forgery.insider", 0.5))
    assert run.assessment.classification.attributed_to == "bob"


def test_counterfactuals_show_the_defence_matters():
    world = build_world(preset="analysis", seed=78)
    harvest = world.run_attack(AttackSpec("unauthorized.key_harvest_mitm", 1.0, {}, "both"))
    assert harvest.counterfactual["breach"] is True            # Eve's forgery would be accepted
    single = world.run_attack(AttackSpec("unauthorized.key_harvest_mitm", 1.0, {}, "first"))
    assert single.counterfactual["breach"] is False            # symmetrization alone stops single-link harvesting
    rep = world.run_attack(AttackSpec("repudiation.inconsistent_keys", 0.5))
    assert rep.counterfactual["breach"] is True                 # dispute without symmetrization
    replay = world.run_attack(AttackSpec("replay.resubmit"))
    assert replay.counterfactual["breach"] is True              # quantum tests alone accept a replay
    swap = world.run_attack(AttackSpec("impersonation.identity_swap"))
    assert swap.counterfactual["breach"] is True


def test_no_false_alarms_on_honest_traffic():
    world = build_world(preset="analysis", seed=4242)
    for i in range(60):
        d = world.distribute("g-alice" if i % 2 == 0 else "g-diana")
        assert d.assessment.verdict == "CERTIFIED", [f.evidence for f in d.findings if f.fired]
        assert not [f for f in d.findings if f.fired and f.severity in ("HIGH", "CRITICAL")]
    for i in range(60):
        g = "g-alice" if i % 2 == 0 else "g-diana"
        s = world.sign_and_verify(g, f"TX {i:06d} | honest payment {i}")
        assert s.assessment.verdict == "ACCEPTED", [f.evidence for f in s.findings if f.fired]
        assert s.transfer is not None and s.transfer.decision == "ACCEPT"


def test_bundles_are_one_time_and_shredded():
    world = build_world(preset="analysis", seed=5)
    world.distribute("g-alice")
    s = world.sign_and_verify("g-alice", "hello")
    bid = s.envelope.bundle_id
    assert world.bundles.meta(bid)["status"] == "CONSUMED"
    assert world.bundles.get(bid) is None or world.bundles.get(bid).labels is None


def test_adversary_code_never_touches_results():
    """P3: attacks must not mutate reports, findings or assessments."""
    src = Path(__file__).resolve().parents[2] / "src" / "sentinel" / "adversary"
    pattern = re.compile(r"\.(decision|verdict|assessment|findings|fired|threat_level)\s*=(?!=)")
    for path in src.glob("*.py"):
        text = path.read_text()
        assert not pattern.search(text), f"{path.name} assigns to a result field"
        assert "private_labels" not in text or path.name == "runner.py"


def test_flagged_runs_do_not_poison_the_drift_monitor():
    world = build_world(preset="analysis", seed=91)
    world.distribute("g-alice")
    hit = world.run_attack(AttackSpec("channel.dephase", 0.8), counterfactual=False)
    assert hit.detected
    # The strong attack was caught by single-run detectors; the CUSUM kept its state,
    # so the following honest bundles raise no persistent-drift alarm.
    for _ in range(5):
        d = world.distribute("g-alice")
        assert d.assessment.verdict == "CERTIFIED"
        assert not [f for f in d.findings if f.id == "D10.cusum" and f.fired], [f.evidence for f in d.findings if f.fired]


def test_low_and_slow_drift_still_accumulates():
    world = build_world(preset="analysis", seed=92)
    fired = False
    for _ in range(40):
        run = world.run_attack(AttackSpec("channel.depolarize", 0.04), counterfactual=False)
        if any(f.id == "D10.cusum" and f.fired for f in run.distribution.findings):
            fired = True
            break
    assert fired


def test_drift_alarm_restarts_instead_of_flagging_honest_traffic():
    # A moderate attack that single-run detectors rate below HIGH on the attacked link feeds the
    # CUSUM and makes it signal. After the signal the accumulator restarts (Page's renewal rule),
    # so the honest bundles that follow are not flagged while the excess drains.
    world = build_world(preset="analysis", seed=93)
    world.distribute("g-alice")
    hit = world.run_attack(AttackSpec("channel.depolarize", 0.12), counterfactual=False)
    assert any(f.id == "D10.cusum" and f.fired for f in hit.distribution.findings)
    for _ in range(6):
        d = world.distribute("g-alice")
        assert not [f for f in d.findings if f.id == "D10.cusum" and f.fired], [f.evidence for f in d.findings if f.fired]
