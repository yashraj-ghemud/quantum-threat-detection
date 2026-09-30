"""
server/services/selftest.py
===========================
Startup self-checks (backend plan section 14.6). Results stream over the
``system`` topic and drive the frontend's boot sequence.
"""

from __future__ import annotations

import math
import threading
import time

import numpy as np

__all__ = ["SelfTest"]


def _check_channels():
    from sentinel.channels import channel_from_spec
    from sentinel.linalg import is_cptp

    worst = 0.0
    n = 0
    for t, grid in {"depolarizing": [{"p": p} for p in (0, .1, .5, 1)],
                    "dephasing": [{"p": p, "axis": a} for p in (.2, 1) for a in "xyz"],
                    "amplitude_damping": [{"gamma": g} for g in (0, .3, 1)], "phase_damping": [{"lam": .4}],
                    "rotation": [{"axis": [1, 1, 0], "theta": 1.1}], "pauli": [{"px": .1, "py": .2, "pz": .05}],
                    "measure_prepare": [{"basis": b} for b in "xyz"]}.items():
        for p in grid:
            ok, info = is_cptp(channel_from_spec({"type": t, **p}).ptm)
            n += 1
            worst = min(worst, info["min_eig"])
            if not ok:
                return False, f"{t} {p} not CPTP", {}
    return True, f"{n} channels CPTP (min Choi eigenvalue {worst:.1e})", {"channels": n}


def _check_teleport_ideal():
    from sentinel.states import BLOCH
    from sentinel.teleport import get_model

    m = get_model([])
    dev = max(float(np.max(np.abs(m.p_k - 0.25))),
              max(float(np.max(np.abs(m.bloch[l, k, k] - BLOCH[l]))) for l in range(6) for k in range(4)))
    return dev < 1e-12, f"noiseless teleportation exact (max deviation {dev:.1e})", {"max_dev": dev}


def _check_aer():
    from sentinel.analysis.validation import DEFAULT_CHANNELS, aer_available, validate_all

    if not aer_available():
        return None, "qiskit-aer not installed", {}
    r = validate_all(DEFAULT_CHANNELS[:4])
    return bool(r["pass"]), f"superoperators = Qiskit Aer, max|Δρ| = {r['max_dev']:.1e} over {len(r['checks'])} channels", \
        {"max_dev": r["max_dev"], "aer_version": r.get("aer_version")}


def _check_bell():
    from sentinel.bell import bell_state, predicted
    from sentinel.channels import channel_from_spec

    s0 = predicted(bell_state(None))["S"]
    s1 = predicted(bell_state(channel_from_spec({"type": "depolarizing", "p": 0.2})))["S"]
    ok = abs(s0 - 2 * math.sqrt(2)) < 1e-12 and abs(s1 - 2 * math.sqrt(2) * 0.8) < 1e-12
    return ok, f"CHSH ideal S = {s0:.6f} (2√2), depolarized p=0.2 → {s1:.6f}", {"S": s0}


def _check_tomography():
    from sentinel.channels import compose
    from sentinel.rng import RandomSource
    from sentinel.teleport import get_model, sample_teleportations
    from sentinel.tomography import aggregate_pe, detwirl, effective

    rs = RandomSource(99)
    spec = [{"type": "amplitude_damping", "gamma": 0.3}]
    n = 200_000
    labels, bases = rs.labels(n), rs.bases(n)
    k, c, o = sample_teleportations(get_model(spec), labels, bases, rs.physics)
    pe = aggregate_pe(labels, k, c, bases, o)
    d, e = detwirl(pe), effective(pe)
    cz = float(d.c[2])
    ok = abs(cz - 0.3) < 6 * float(d.c_se[2]) + 1e-3 and abs(float(e.c[2])) < 0.03
    return ok, f"de-twirling recovers amplitude damping γ = {cz:.3f} (twirled view {float(e.c[2]):+.3f})", {"gamma_hat": cz}


def _check_stats():
    from sentinel.stats import binom_sf

    exact = sum(math.comb(12, k) * 0.3 ** k * 0.7 ** (12 - k) for k in range(5, 13))
    ok = abs(binom_sf(5, 12, 0.3) - exact) < 1e-12
    return ok, "exact binomial tails match brute force", {}


def _check_rng():
    from scipy.stats import chisquare

    from sentinel.rng import RandomSource

    counts = np.bincount(RandomSource().labels(60_000), minlength=6)
    p = float(chisquare(counts).pvalue)
    return p > 1e-6, f"CSPRNG six-state labels uniform (χ² p = {p:.3f})", {"p": p}


class SelfTest:
    def __init__(self, hub, ledger=None, engine=None) -> None:
        self.hub = hub
        self.ledger = ledger
        self.engine = engine
        self.state = "idle"
        self.started_at = None
        self.finished_at = None
        self.checks = []
        self._lock = threading.Lock()

    def _plan(self):
        plan = [("channels.cptp", "Channel library is CPTP", _check_channels),
                ("teleport.ideal", "Ideal teleportation", _check_teleport_ideal),
                ("teleport.aer", "Cross-check against Qiskit Aer", _check_aer),
                ("bell.chsh", "CHSH closed forms", _check_bell),
                ("tomography.detwirl", "Pauli-frame de-twirling", _check_tomography),
                ("stats.tails", "Exact statistics", _check_stats),
                ("rng.labels", "Key randomness", _check_rng)]
        if self.ledger is not None:
            plan.append(("ledger.chain", "Ledger integrity",
                         lambda: (lambda r: (r["valid"], f"{r['checked_blocks']} blocks verified" if r["valid"] else
                                             f"invalid from height {r['first_invalid_height']}", {}))(self.ledger.verify())))
        if self.engine is not None:
            plan.append(("protocol.roundtrip", "Honest protocol round trip", self._roundtrip))
        return plan

    def _roundtrip(self):
        from sentinel.network import build_world

        w = build_world(preset="analysis", seed=1)
        w.detection.calibration_pe_samples = 100_000
        w.detection.calibration_bell_per_setting = 5000
        d = w.distribute("g-alice")
        s = w.sign_and_verify("g-alice", "self-test")
        ok = d.assessment.verdict == "CERTIFIED" and s.assessment.verdict == "ACCEPTED"
        return ok, f"distribution {d.assessment.verdict.lower()}, signature {s.assessment.verdict.lower()} by both recipients", {}

    def snapshot(self) -> dict:
        return {"state": self.state, "started_at": self.started_at, "finished_at": self.finished_at,
                "checks": list(self.checks)}

    def run(self) -> dict:
        with self._lock:
            plan = self._plan()
            self.state = "running"
            self.started_at = time.time()
            self.finished_at = None
            self.checks = [{"id": i, "name": n, "status": "pending", "detail": "", "duration_ms": None, "metrics": {}}
                           for i, n, _ in plan]
            self.hub.publish("system", "selftest.start", self.snapshot())
            for idx, (cid, name, fn) in enumerate(plan):
                self.checks[idx]["status"] = "running"
                t0 = time.perf_counter()
                try:
                    ok, detail, metrics = fn()
                    status = "skip" if ok is None else ("pass" if ok else "fail")
                except Exception as exc:  # pragma: no cover - surfaced to the UI
                    status, detail, metrics = "fail", f"{type(exc).__name__}: {exc}", {}
                self.checks[idx].update(status=status, detail=detail, metrics=metrics,
                                        duration_ms=(time.perf_counter() - t0) * 1000)
                self.hub.publish("system", "selftest.check", self.checks[idx])
            self.state = "done"
            self.finished_at = time.time()
            self.hub.publish("system", "selftest.done", self.snapshot())
            return self.snapshot()
