"""
sentinel/analysis/evaluation.py
===============================
Evaluation jobs that run the real engine many times:

- ``detection_matrix``      detection and classification rate per attack x intensity, FAR/FRR, confusion
- ``roc``                   per-detector ROC curves from stored p-values
- ``channel_fingerprint``   channel-shape classifier accuracy
- ``repudiation_analysis``  dispute rate with and without symmetrization
- ``threshold_design``      design table over (e, L)
- ``sprt_efficiency``       ASN and operating characteristic
- ``cusum_arl``             average run length to alarm vs shift
- ``performance``           latency and throughput vs L, NumPy vs Aer

Every result carries its parameters, seed and duration.
"""

from __future__ import annotations

import copy
import math
import time
import warnings

import numpy as np

from sentinel.adversary.catalog import CATALOG, AttackSpec, catalog_entry
from sentinel.adversary.distribution_attacks import plans_for
from sentinel.detection.monitor import noise_aware_limits
from sentinel.network import build_world
from sentinel.protocol.guard import MemoryGuardStore
from sentinel.protocol.signing import sign as _sign
from sentinel.protocol.thresholds import design
from sentinel.sequential import Cusum, Sprt
from sentinel.stats import clopper_pearson

__all__ = [
    "detection_matrix", "roc", "channel_fingerprint", "repudiation_analysis", "threshold_design_table",
    "sprt_efficiency", "cusum_arl", "performance",
]

CATEGORIES = ["NONE", "FORGERY", "IMPERSONATION", "REPLAY", "UNAUTHORIZED_VERIFICATION", "CHANNEL_MANIPULATION",
              "REPUDIATION"]


def _cat_index(category: str) -> int:
    return CATEGORIES.index(category) if category in CATEGORIES else 0


def _eval_world(seed: int, preset: str = "analysis"):
    w = build_world(preset=preset, seed=seed)
    w.monitors_enabled = False  # each trial is independent; temporal accumulation is evaluated separately
    return w


def _tick(progress, done, total, msg):
    if progress and total:
        progress(min(1.0, done / total), msg)


def detection_matrix(params: dict, progress=None, cancel=None) -> dict:
    t0 = time.time()
    seed = int(params.get("seed", 11))
    intensities = [float(x) for x in params.get("intensities", [0.25, 0.5, 1.0])]
    trials = int(params.get("trials", 6))
    legit = int(params.get("legit", 60))
    attack_ids = params.get("attacks") or [e["id"] for e in CATALOG]
    w = _eval_world(seed, params.get("preset", "analysis"))
    confusion = np.zeros((len(CATEGORIES), len(CATEGORIES)), dtype=int)
    rows = []
    total = len(attack_ids) * len(intensities) * trials + 2 * legit
    done = 0
    for aid in attack_ids:
        entry = catalog_entry(aid)
        points = []
        for I in intensities:
            det = corr = sub_ok = 0
            for _ in range(trials):
                if cancel is not None and cancel.is_set():
                    return {"partial": True, "attacks": rows}
                run = w.run_attack(AttackSpec(aid, I), counterfactual=False, origin="ANALYTICS")
                a = run.assessment
                det += int(run.detected)
                corr += int(run.correctly_classified)
                sub_ok += int(a.classification.subtype == entry["subtype"])
                predicted = a.classification.category if run.detected else "NONE"
                confusion[CATEGORIES.index(entry["category"]), _cat_index(predicted)] += 1
                done += 1
                _tick(progress, done, total, f"{aid} I={I}")
            lo, hi = clopper_pearson(det, trials, 0.05)
            points.append({"intensity": I, "runs": trials, "detected": det, "rate": det / trials, "ci": [lo, hi],
                           "correct": corr, "classification_rate": corr / trials, "subtype_rate": sub_ok / trials})
        rows.append({"attack_id": aid, "category": entry["category"], "phase": entry["phase"], "name": entry["name"],
                     "points": points})
    # Legitimate traffic: false rejections at both phases.
    fr_d = fr_s = 0
    for i in range(legit):
        g = "g-alice" if i % 2 == 0 else "g-diana"
        d = w.distribute(g, origin="ANALYTICS")
        flagged = d.assessment.verdict != "CERTIFIED"
        fr_d += int(flagged)
        confusion[0, _cat_index(d.assessment.classification.category if flagged else "NONE")] += 1
        done += 1
        _tick(progress, done, total, "legitimate distributions")
    for i in range(legit):
        g = "g-alice" if i % 2 == 0 else "g-diana"
        try:
            s = w.sign_and_verify(g, f"TX {i:06d} | evaluation payment", origin="ANALYTICS")
            bad = s.assessment.verdict != "ACCEPTED"
        except Exception:
            w.distribute(g, origin="ANALYTICS")
            s = w.sign_and_verify(g, f"TX {i:06d} | evaluation payment", origin="ANALYTICS")
            bad = s.assessment.verdict != "ACCEPTED"
        fr_s += int(bad)
        confusion[0, _cat_index(s.assessment.classification.category if bad else "NONE")] += 1
        done += 1
        _tick(progress, done, total, "legitimate signatures")
    attack_runs = sum(p["runs"] for r in rows for p in r["points"])
    detected = sum(p["detected"] for r in rows for p in r["points"])
    correct = sum(p["correct"] for r in rows for p in r["points"])
    far_lo, far_hi = clopper_pearson(attack_runs - detected, attack_runs, 0.05)
    frr_n = 2 * legit
    frr_lo, frr_hi = clopper_pearson(fr_d + fr_s, frr_n, 0.05)
    return {
        "attacks": rows, "intensities": intensities,
        "legit": {"runs": frr_n, "false_rejections": fr_d + fr_s, "distribution_flags": fr_d, "signature_rejects": fr_s,
                  "frr": (fr_d + fr_s) / frr_n if frr_n else 0.0, "frr_ci": [frr_lo, frr_hi]},
        "far": {"attack_runs": attack_runs, "missed": attack_runs - detected,
                "far": (attack_runs - detected) / attack_runs if attack_runs else 0.0, "far_ci": [far_lo, far_hi],
                "classification_accuracy": correct / attack_runs if attack_runs else 0.0},
        "confusion": {"labels": CATEGORIES, "matrix": confusion.tolist()},
        "params": {"seed": seed, "intensities": intensities, "trials": trials, "legit": legit,
                   "preset": params.get("preset", "analysis")},
        "duration_s": time.time() - t0,
    }


_ROC_IDS = ["D2.chsh_drift", "D3b.witness_drift", "D4.qber_excess", "D5.tomography_deviation", "D7.bell_consistency"]


def _pvals(run) -> dict:
    out = {}
    for f in run.findings:
        if f.id in _ROC_IDS and f.p_value is not None:
            out[f.id] = min(out.get(f.id, 1.0), f.p_value)
    out["fused"] = min(1.0, min(out.values()) * len(_ROC_IDS)) if out else 1.0
    return out


def roc(params: dict, progress=None, cancel=None) -> dict:
    t0 = time.time()
    seed = int(params.get("seed", 13))
    n = int(params.get("runs", 150))
    attacks = params.get("attacks") or [["channel.depolarize", 0.04], ["channel.amplitude_damp", 0.08],
                                        ["channel.coherent_rotation", 0.08]]
    w = _eval_world(seed, params.get("preset", "analysis"))
    total = n * (1 + len(attacks))
    done = 0
    legit = []
    for i in range(n):
        if cancel is not None and cancel.is_set():
            break
        legit.append(_pvals(w.distribute("g-alice", origin="ANALYTICS")))
        done += 1
        _tick(progress, done, total, "legitimate runs")
    alphas = np.logspace(-14, -0.01, 48)
    curves = []
    for aid, I in attacks:
        att = []
        for i in range(n):
            if cancel is not None and cancel.is_set():
                break
            plans = plans_for(AttackSpec(aid, float(I)), ("bob", "charlie"))
            att.append(_pvals(w.distribute("g-alice", plans=plans, origin="ANALYTICS", store=False)))
            done += 1
            _tick(progress, done, total, f"{aid} I={I}")
        for det in _ROC_IDS + ["fused"]:
            lp = np.array([r.get(det, 1.0) for r in legit])
            ap = np.array([r.get(det, 1.0) for r in att])
            pts = [{"alpha": float(a), "fpr": float(np.mean(lp <= a)), "tpr": float(np.mean(ap <= a))} for a in alphas]
            xs = [0.0] + [p["fpr"] for p in pts] + [1.0]
            ys = [0.0] + [p["tpr"] for p in pts] + [1.0]
            order = np.argsort(xs, kind="stable")
            auc = float(np.trapezoid(np.array(ys)[order], np.array(xs)[order]))
            curves.append({"attack_id": aid, "intensity": float(I), "detector": det, "points": pts, "auc": auc})
    return {"curves": curves, "detectors": _ROC_IDS + ["fused"], "runs": n,
            "params": {"seed": seed, "runs": n, "attacks": attacks}, "duration_s": time.time() - t0}


_FP_FAMILIES = [
    ("depolarizing", "channel.depolarize", {}, "isotropic"),
    ("dephasing (z)", "channel.dephase", {"axis": "z"}, "dephasing"),
    ("dephasing (x)", "channel.dephase", {"axis": "x"}, "dephasing"),
    ("amplitude damping", "channel.amplitude_damp", {}, "amplitude_damping"),
    ("coherent rotation", "channel.coherent_rotation", {"axis": "z"}, "coherent_rotation"),
    ("intercept–resend (z)", "channel.intercept_resend", {"basis": "z"}, "dephasing"),
    ("intercept–resend (random)", "channel.intercept_resend", {"basis": "random"}, "isotropic"),
    ("frame tampering", "channel.pauli_frame", {"bits": "m1"}, "none"),
    ("honest", None, {}, "none"),
]
_SHAPES = ["none", "isotropic", "dephasing", "amplitude_damping", "coherent_rotation", "non_unital", "general_pauli"]


def channel_fingerprint(params: dict, progress=None, cancel=None) -> dict:
    t0 = time.time()
    seed = int(params.get("seed", 17))
    strengths = [float(x) for x in params.get("strengths", [0.3, 0.6, 1.0])]
    trials = int(params.get("trials", 10))
    w = _eval_world(seed, params.get("preset", "analysis"))
    mat = np.zeros((len(_FP_FAMILIES), len(_SHAPES)), dtype=int)
    per = []
    total = len(_FP_FAMILIES) * len(strengths) * trials
    done = 0
    for fi, (label, aid, p, expected) in enumerate(_FP_FAMILIES):
        for s in (strengths if aid else [0.0]):
            ok = 0
            for _ in range(trials):
                if cancel is not None and cancel.is_set():
                    break
                plans = plans_for(AttackSpec(aid, s, p), ("bob", "charlie")) if aid else None
                d = w.distribute("g-alice", plans=plans, origin="ANALYTICS", store=False)
                d5 = next(f for f in d.findings if f.id.startswith("D5.") and f.link_id == "alice-bob")
                shape = (d5.data.get("fingerprint") or {}).get("shape", "none")
                mat[fi, _SHAPES.index(shape)] += 1
                ok += int(shape == expected)
                done += 1
                _tick(progress, done, total, f"{label} {s}")
            per.append({"family": label, "strength": s, "expected": expected, "accuracy": ok / max(trials, 1)})
    return {"labels": [f[0] for f in _FP_FAMILIES], "shapes": _SHAPES, "matrix": mat.tolist(),
            "expected": [f[3] for f in _FP_FAMILIES], "per_family": per,
            "params": {"seed": seed, "strengths": strengths, "trials": trials}, "duration_s": time.time() - t0}


def repudiation_analysis(params: dict, progress=None, cancel=None) -> dict:
    t0 = time.time()
    seed = int(params.get("seed", 19))
    rs_grid = [float(x) for x in params.get("fractions", np.linspace(0, 0.5, 11).round(3).tolist())]
    runs = int(params.get("runs", 30))
    w = _eval_world(seed, params.get("preset", "analysis"))
    g = w.group("g-alice")
    out = []
    total = len(rs_grid) * runs
    done = 0
    for r in rs_grid:
        d_with = d_without = compromised = 0
        for _ in range(runs):
            if cancel is not None and cancel.is_set():
                break
            plans = {"charlie": plans_for(AttackSpec("repudiation.inconsistent_keys", min(1.0, 2 * r)), ("bob", "charlie"))["charlie"]} if r > 0 else None
            dist = w.distribute("g-alice", plans=plans, origin="ANALYTICS", keep_copy=True, store=False)
            compromised += int(dist.assessment.verdict == "COMPROMISED")
            b = dist.bundle_copy
            b.design = w.baseline_design("g-alice", b.params).as_dict()
            b.status = "ACTIVE"
            meta = {**b.meta(), "status": "ACTIVE"}
            env = w.make_envelope(g, b.bundle_id, "Alice will later deny this")
            sig = _sign(copy.deepcopy(b), env)
            for mode, key in (("symmetrized", "with"), ("own_only", "without")):
                run = w.deliver(sig.copy(), bundle=copy.deepcopy(b), meta=meta, counterfactual=True, commit=False,
                                guard_store=MemoryGuardStore(), mode_first=mode, mode_transfer=mode)
                dispute = run.primary is not None and run.primary.decision == "ACCEPT" and \
                    run.transfer is not None and run.transfer.decision == "REJECT"
                if key == "with":
                    d_with += int(dispute)
                else:
                    d_without += int(dispute)
            done += 1
            _tick(progress, done, total, f"r={r}")
        out.append({"r": r, "runs": runs, "dispute_with_sym": d_with / runs, "dispute_without_sym": d_without / runs,
                    "ci_with": list(clopper_pearson(d_with, runs, 0.05)),
                    "ci_without": list(clopper_pearson(d_without, runs, 0.05)),
                    "detected_at_distribution": compromised / runs})
    return {"points": out, "params": {"seed": seed, "runs": runs}, "duration_s": time.time() - t0}


def threshold_design_table(params: dict, progress=None, cancel=None) -> dict:
    t0 = time.time()
    es = [float(x) for x in params.get("e_grid", [0.005, 0.01, 0.02, 0.04])]
    Ls = [int(x) for x in params.get("L_grid", [256, 512, 1024, 2048, 4096, 8192, 16384])]
    tg = {k: float(params.get(k, v)) for k, v in
          {"eps_rob_target": 1e-9, "eps_forge_target": 1e-6, "eps_rep_target": 1e-6}.items()}
    rows = []
    total = len(es) * len(Ls)
    for i, e in enumerate(es):
        for j, L in enumerate(Ls):
            d = design(L, e, digest_bits=256, find_L_min=False, **tg)
            rows.append({"e": e, "L": L, "s_a": d.s_a, "s_v": d.s_v, "feasible": d.feasible, "eps_rob": d.eps_rob_msg,
                         "eps_forge": d.eps_forge_key, "eps_rep_key": d.eps_rep_key, "eps_rep_msg": d.eps_rep_msg,
                         "n_min": d.n_min, "meets": d.meets_targets})
            _tick(progress, i * len(Ls) + j + 1, total, f"e={e} L={L}")
    return {"rows": rows, "targets": tg, "duration_s": time.time() - t0}


def sprt_efficiency(params: dict, progress=None, cancel=None) -> dict:
    t0 = time.time()
    p0 = float(params.get("p0", 0.013))
    p1 = float(params.get("p1", 1 / 3))
    alpha = float(params.get("alpha", 1e-13))
    beta = float(params.get("beta", 1e-6))
    n = int(params.get("n", 682))
    paths = int(params.get("paths", 500))
    seed = int(params.get("seed", 23))
    rng = np.random.default_rng(seed)
    s = Sprt(p0, p1, alpha, beta)
    ps = np.linspace(0.0, 0.5, 26)
    pts = []
    for i, p in enumerate(ps):
        used, rej = [], 0
        for _ in range(paths):
            r = s.run(rng.random(n) < p)
            used.append(r.n_used)
            rej += int(r.decision == "reject")
        pts.append({"p": float(p), "asn_mc": float(np.mean(used)), "asn_wald": s.asn(float(p)) if 0 < p < 1 else None,
                    "reject_rate": rej / paths, "oc_wald": s.oc(float(p)) if 0 < p < 1 else None})
        _tick(progress, i + 1, len(ps), f"p={p:.2f}")
    return {"points": pts, "fixed_n": n, "A": s.A, "B": s.B,
            "params": {"p0": p0, "p1": p1, "alpha": alpha, "beta": beta, "paths": paths, "seed": seed},
            "duration_s": time.time() - t0}


def cusum_arl(params: dict, progress=None, cancel=None) -> dict:
    t0 = time.time()
    seed = int(params.get("seed", 29))
    runs = int(params.get("runs", 200))
    horizon = int(params.get("horizon", 500))
    shifts = [float(x) for x in params.get("shifts", [0.0, 0.0025, 0.005, 0.01, 0.02])]
    w = build_world(preset=params.get("preset", "standard"), seed=seed)
    link = w.links["alice-bob"]
    base = w.calibrate([link.link_id])[link.link_id]
    e0, n0 = base.qber["rate"], base.qber["n"]
    pr = w.params
    n_run = int(pr.digest_bits * 2 * pr.n_pe / 3)  # basis-matched PE positions per copy
    rng = np.random.default_rng(seed)
    k_cfg, h_cfg = w.detection.cusum_qber_k, w.detection.cusum_qber_h
    pts = []
    for i, shift in enumerate(shifts):
        lengths = []
        censored = 0
        for _ in range(runs):
            c = Cusum(k_cfg, h_cfg)
            t_alarm = None
            for t in range(1, horizon + 1):
                q = rng.binomial(n_run, min(1.0, e0 + shift)) / n_run
                k, h, _ = noise_aware_limits(q, n_run, e0, n0, k_cfg, h_cfg)
                _, alarm = c.update(q - e0, k, h)
                if alarm:
                    t_alarm = t
                    break
            if t_alarm is None:
                censored += 1
                lengths.append(horizon)
            else:
                lengths.append(t_alarm)
        arr = np.array(lengths, dtype=float)
        pts.append({"shift": shift, "arl_mean": float(arr.mean()), "arl_median": float(np.median(arr)),
                    "censored": censored, "runs": runs, "horizon": horizon,
                    "false_alarm_rate": (runs - censored) / runs if shift == 0 else None})
        _tick(progress, i + 1, len(shifts), f"shift={shift}")
    return {"points": pts, "e0": e0, "n_per_bundle": n_run,
            "params": {"seed": seed, "runs": runs, "horizon": horizon, "k": k_cfg, "h": h_cfg},
            "duration_s": time.time() - t0}


def performance(params: dict, progress=None, cancel=None) -> dict:
    t0 = time.time()
    Ls = [int(x) for x in params.get("L_grid", [512, 1024, 2048, 4096])]
    reps = int(params.get("reps", 3))
    w = build_world(preset="standard", seed=int(params.get("seed", 31)))
    w.monitors_enabled = False
    w.ensure_baselines(w.group("g-alice"))
    rows = []
    total = len(Ls) * reps + 1
    done = 0
    for L in Ls:
        pr = w.params.with_(L=L)
        d_ms, s_ms, v_ms, det_ms, q, refused = [], [], [], [], 0, 0
        for _ in range(reps):
            if cancel is not None and cancel.is_set():
                break
            d = w.distribute("g-alice", params=pr, origin="ANALYTICS")
            d_ms.append(d.outcome.timings["total_ms"])
            det_ms.append(d.detect_ms)
            q = d.outcome.qubits
            if d.status != "ACTIVE":
                refused += 1
            else:
                s = w.sign_and_verify("g-alice", "performance probe", bundle_id=d.bundle_id, origin="ANALYTICS")
                s_ms.append(s.latency_ms["sign"])
                v_ms.append(s.latency_ms["verify_first"] + s.latency_ms["verify_transfer"])
            done += 1
            _tick(progress, done, total, f"L={L}")
        dm = float(np.mean(d_ms)) if d_ms else None
        rows.append({"L": L, "qubits": q, "distribution_ms": dm, "detect_ms": float(np.mean(det_ms)) if det_ms else None,
                     "sign_ms": float(np.mean(s_ms)) if s_ms else None, "verify_ms": float(np.mean(v_ms)) if v_ms else None,
                     "qubits_per_s": q / (dm / 1000) if dm else None,
                     "signing_refused": refused,
                     "note": (f"no feasible threshold design at L={L} under the standard targets: the engine refuses to sign"
                              if refused and not s_ms else None)})
    aer = _aer_speed()
    done += 1
    _tick(progress, done, total, "Aer comparison")
    numpy_rate = max((r["qubits_per_s"] or 0) for r in rows) if rows else None
    return {"rows": rows, "aer": aer,
            "speedup": (numpy_rate / aer["qubits_per_s"]) if aer.get("qubits_per_s") and numpy_rate else None,
            "params": {"L_grid": Ls, "reps": reps}, "duration_s": time.time() - t0}


def _aer_speed() -> dict:
    try:
        from qiskit import transpile
        from qiskit_aer import AerSimulator

        from sentinel.analysis.validation import aer_available
        if not aer_available():
            return {"available": False}
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from quantum.teleportation import build_teleportation_circuit

        sim = AerSimulator(method="density_matrix")
        qc = build_teleportation_circuit(math.pi / 2, 0.0)
        compiled = transpile(qc, sim)
        shots = 256
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sim.run(compiled, shots=8).result()
            t = time.perf_counter()
            circuits = 20
            for i in range(circuits):
                sim.run(compiled, shots=shots, seed_simulator=i).result()
            dt = time.perf_counter() - t
        return {"available": True, "qubits_per_s": circuits * shots / dt, "circuits": circuits, "shots": shots,
                "note": "Qiskit Aer density-matrix simulation of v1's teleportation circuit, one trajectory per shot."}
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"available": False, "error": str(exc)}
