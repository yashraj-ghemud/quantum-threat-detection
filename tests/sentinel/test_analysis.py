"""Analysis jobs return their schemas and agree with theory."""

from __future__ import annotations

import pytest

from sentinel.analysis.forgery import exact_curves, insider_optimum, monte_carlo
from sentinel.analysis.jobs import JOB_KINDS, kinds_public, run_job


def test_insider_cannot_beat_one_third():
    opt = insider_optimum(2000)
    assert opt["min"] == pytest.approx(1 / 3, abs=1e-3)
    assert max(abs(x) for x in opt["argmin_direction"]) > 0.99  # an axis direction


def test_monte_carlo_agrees_with_exact():
    mc = monte_carlo([48], trials_per_L=1500, s_v=0.2, seed=3)
    exact = exact_curves([48], 0.2, e=0.0075)
    for row in mc:
        predicted = exact[row["strategy"]]["exact"][0]
        lo, hi = row["ci"]
        assert lo - 0.01 <= predicted <= hi + 0.01, (row, predicted)


def test_exact_decreases_with_L():
    c = exact_curves([64, 256, 1024, 4096], 0.2)
    ins = c["insider"]["exact"]
    assert all(a > b for a, b in zip(ins, ins[1:]))


def test_registry_public():
    kinds = {k["kind"] for k in kinds_public()}
    assert kinds == set(JOB_KINDS) and len(kinds) == 10


@pytest.mark.parametrize("kind,params", [
    ("threshold_design", {"e_grid": [0.01], "L_grid": [1024, 4096]}),
    ("sprt_efficiency", {"paths": 30}),
    ("cusum_arl", {"runs": 20, "horizon": 100, "shifts": [0.0, 0.02]}),
    ("detection_matrix", {"attacks": ["forgery.blind", "channel.dephase"], "intensities": [1.0], "trials": 1, "legit": 2}),
    ("roc", {"runs": 6, "attacks": [["channel.depolarize", 0.2]]}),
    ("channel_fingerprint", {"strengths": [1.0], "trials": 1}),
    ("repudiation_analysis", {"fractions": [0.0, 0.4], "runs": 2}),
    ("engine_validation", {}),
])
def test_jobs_run_small(kind, params):
    r = run_job(kind, params, preset="quick")
    assert r["kind"] == kind
    if kind == "detection_matrix":
        assert r["far"]["far"] == 0.0 and r["legit"]["frr"] == 0.0
        assert len(r["confusion"]["matrix"]) == len(r["confusion"]["labels"])
    if kind == "cusum_arl":
        assert r["points"][0]["censored"] == 20  # no false alarm in 100 bundles
        assert r["points"][1]["arl_mean"] < 10
    if kind == "repudiation_analysis":
        assert r["points"][1]["dispute_with_sym"] == 0.0
        assert r["points"][1]["dispute_without_sym"] == 1.0
    if kind == "threshold_design":
        assert any(row["feasible"] for row in r["rows"])
    if kind == "engine_validation" and r.get("status") == "done":
        assert r["pass"] is True
