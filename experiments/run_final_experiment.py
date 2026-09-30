"""
experiments/run_final_experiment.py
===================================
THE canonical experiment. Single source of truth for every published metric.

SIH26141 | Blockchain & Cybersecurity.

Everything under ``experiments/results/final/`` is produced here, in one
run, from one configuration, with one seed. Nothing is copied in from an
older run and nothing is written by hand. If a number appears in the
README, the documentation or the dashboard, it came from this script.

Pipeline
--------
1. Calibrate a baseline from measured legitimate sessions.
2. Run N legitimate sessions.
3. Run N sessions for each attack class, swept across intensities.
4. Sweep candidate thresholds over the measured score distributions and
   select an operating point by a documented rule.
5. Re-score every session at the selected threshold.
6. Compute metrics with confidence intervals.
7. Write results and plots.

Usage
-----
    python experiments/run_final_experiment.py
    python experiments/run_final_experiment.py --trials 500
    python experiments/run_final_experiment.py --trials 50 --quick

No AI/ML libraries are used.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
import warnings
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=DeprecationWarning)

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from attacks.channel_manipulation import ChannelManipulationAttack  # noqa: E402
from attacks.forgery import ForgeryAttack  # noqa: E402
from attacks.unauthorized_verification import UnauthorizedVerificationAttack  # noqa: E402
from evaluation.far_frr import compute_far, compute_frr, rate_with_interval  # noqa: E402
from qds.keygen import generate_key_pair  # noqa: E402
from security.threat_engine import (  # noqa: E402
    NORM_ENTROPY, NORM_FIDELITY, NORM_MISMATCH, NORM_TRACE, WEIGHTS, ThreatEngine,
)
from session import SessionRunner  # noqa: E402
from utils.logger import get_logger  # noqa: E402
from utils.reproducibility import set_seed  # noqa: E402

logger = get_logger(__name__)

RESULTS_DIR = _ROOT / "experiments" / "results" / "final"
PLOTS_DIR = RESULTS_DIR / "plots"

#: Attack classes evaluated. LEGITIMATE is the negative class.
ATTACK_CLASSES: Tuple[str, ...] = (
    "FORGERY",
    "IMPERSONATION",
    "REPLAY",
    "UNAUTHORIZED_VERIFICATION",
    "CHANNEL_MANIPULATION",
)

#: Non-zero intensities swept for every attack class.
INTENSITIES: Tuple[float, ...] = (0.1, 0.25, 0.5, 0.75, 1.0)

_SEP = "=" * 74


# ---------------------------------------------------------------------------
# Session generation
# ---------------------------------------------------------------------------

def run_legitimate(runner: SessionRunner, n: int) -> List:
    """Run *n* legitimate sessions."""
    out = []
    for i in range(n):
        out.append(runner.run(message=f"legit payment {i}".encode(),
                              seed_offset=i))
    return out


def run_attack_class(
    runner: SessionRunner,
    attack_class: str,
    n: int,
    seed: int,
) -> List:
    """Run *n* sessions of one attack class, swept across intensities.

    Each class perturbs the pipeline at its natural point:

    - FORGERY / UNAUTHORIZED_VERIFICATION: statevectors, before the channel
    - IMPERSONATION: signed with an attacker-owned key pair
    - CHANNEL_MANIPULATION: noise injected on the channel qubits
    - REPLAY: a consumed session context is presented again
    """
    import copy

    out = []
    per_intensity = max(1, n // len(INTENSITIES))
    idx = 0

    for intensity in INTENSITIES:
        for rep in range(per_intensity):
            msg = f"attack {attack_class} {idx}".encode()
            so = 10_000 + idx

            if attack_class == "FORGERY":
                res = runner.run(
                    message=msg, attack=ForgeryAttack(seed=seed + idx),
                    attack_type=attack_class, intensity=intensity, seed_offset=so,
                )

            elif attack_class == "UNAUTHORIZED_VERIFICATION":
                res = runner.run(
                    message=msg,
                    attack=UnauthorizedVerificationAttack(seed=seed + idx),
                    attack_type=attack_class, intensity=intensity, seed_offset=so,
                )

            elif attack_class == "IMPERSONATION":
                # A genuine, valid key pair that simply is not Alice's.
                priv, _ = generate_key_pair(
                    signer_id="attacker_mallory", table_size=runner.table_size
                )
                res = runner.run(
                    message=msg, attack_type=attack_class,
                    intensity=intensity, signing_key=priv, seed_offset=so,
                )

            elif attack_class == "CHANNEL_MANIPULATION":
                res = runner.run(
                    message=msg, attack_type=attack_class, intensity=intensity,
                    channel_noise="depolarizing", channel_noise_level=intensity,
                    seed_offset=so,
                )

            elif attack_class == "REPLAY":
                ctx = runner.next_context(f"replay_{idx}")
                runner.run(message=msg, context=copy.deepcopy(ctx),
                           detect=False, seed_offset=so)
                res = runner.run(
                    message=msg, attack_type=attack_class, intensity=intensity,
                    context=copy.deepcopy(ctx), seed_offset=so,
                )

            else:
                raise ValueError(f"Unknown attack class {attack_class!r}")

            out.append(res)
            idx += 1

    return out


# ---------------------------------------------------------------------------
# Threshold calibration (Phase 7)
# ---------------------------------------------------------------------------

def calibrate_threshold(
    legit_scores: Sequence[float],
    attack_scores: Sequence[float],
    max_frr: float = 0.05,
    n_points: int = 200,
) -> Tuple[float, pd.DataFrame, str]:
    """Sweep thresholds and select an operating point by a stated rule.

    Selection rule, in order:

    1. Consider only thresholds whose FRR (legitimate sessions wrongly
       denied) is at most *max_frr*. Rejecting honest users is the error
       this system can least afford to make silently.
    2. Among those, take the threshold with the lowest FAR (attacks that
       slipped through).
    3. Break ties by the larger threshold, which keeps a wider margin above
       the legitimate score distribution.

    If no threshold satisfies (1), the constraint is reported as unmet and
    the minimum-FAR threshold is returned so the failure is visible rather
    than silently absorbed.

    Returns
    -------
    tuple
        ``(selected_threshold, sweep_dataframe, rule_description)``.
    """
    legit = np.asarray(legit_scores, dtype=float)
    attack = np.asarray(attack_scores, dtype=float)

    lo = float(min(legit.min(), attack.min()))
    hi = float(max(legit.max(), attack.max()))
    if np.isclose(lo, hi):
        hi = lo + 1e-3
    candidates = np.linspace(lo, hi, n_points)

    rows = []
    for t in candidates:
        # A session is flagged when its score reaches the threshold.
        fp = int((legit >= t).sum())      # legitimate flagged  -> false reject
        fn = int((attack < t).sum())      # attack not flagged  -> false accept
        tp = int(attack.size - fn)
        tn = int(legit.size - fp)

        far = fn / attack.size if attack.size else 0.0
        frr = fp / legit.size if legit.size else 0.0
        acc = (tp + tn) / (attack.size + legit.size)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

        rows.append({
            "threshold": float(t), "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "far": far, "frr": frr, "accuracy": acc,
            "precision": prec, "recall": rec, "f1": f1,
            "detection_rate": rec,
        })

    df = pd.DataFrame(rows)

    feasible = df[df["frr"] <= max_frr]
    if len(feasible):
        best_far = feasible["far"].min()
        tied = feasible[np.isclose(feasible["far"], best_far)]
        selected = float(tied["threshold"].max())
        rule = (f"min FAR subject to FRR <= {max_frr:.0%}; "
                f"ties broken by larger threshold")
    else:
        selected = float(df.loc[df["far"].idxmin(), "threshold"])
        rule = (f"NO threshold met FRR <= {max_frr:.0%}; "
                f"fell back to min-FAR threshold")
        logger.warning("Threshold constraint unmet: %s", rule)

    return selected, df, rule


# ---------------------------------------------------------------------------
# Metrics (Phase 9)
# ---------------------------------------------------------------------------

def rescore(results: List, threshold: float, baseline: Dict[str, float]) -> None:
    """Re-evaluate every session at the calibrated threshold, in place."""
    engine = ThreatEngine(
        baseline,
        warning_threshold=threshold,
        critical_threshold=min(1.0, threshold * 2.5),
    )
    for r in results:
        engine.evaluate(r)


def compute_metrics(
    legit: List, attacks: Dict[str, List], threshold: float
) -> Dict[str, Any]:
    """Compute the full metric set with confidence intervals."""
    all_attacks = [r for rs in attacks.values() for r in rs]

    tp = sum(1 for r in all_attacks if r.decision != "LEGITIMATE")
    fn = len(all_attacks) - tp
    fp = sum(1 for r in legit if r.decision != "LEGITIMATE")
    tn = len(legit) - fp
    total = len(all_attacks) + len(legit)

    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    far_est = compute_far(fn, len(all_attacks), method="clopper_pearson")
    frr_est = compute_frr(fp, len(legit), method="clopper_pearson")
    dr_est = rate_with_interval(tp, len(all_attacks), method="clopper_pearson")

    # Forgery acceptance probability: forged sessions that the QDS
    # verification itself accepted (score >= 0.7 and bindings valid),
    # independent of whether the detector also flagged them.
    forged = attacks.get("FORGERY", [])
    accepted_forgeries = sum(1 for r in forged if r.accepted)
    fap_est = rate_with_interval(
        accepted_forgeries, len(forged), method="clopper_pearson"
    ) if forged else None

    lat_sign = [r.latency_sign_ms for r in legit]
    lat_verify = [r.latency_measure_ms for r in legit]
    lat_channel = [r.latency_channel_ms for r in legit]
    lat_detect = [r.latency_detect_ms for r in legit]
    lat_total = [r.latency_total_ms for r in legit]

    return {
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "detection_rate": dr_est.rate,
        "detection_rate_ci": [dr_est.lower, dr_est.upper],
        "far": far_est.rate,
        "far_ci": [far_est.lower, far_est.upper],
        "far_n": far_est.trials,
        "frr": frr_est.rate,
        "frr_ci": [frr_est.lower, frr_est.upper],
        "frr_n": frr_est.trials,
        "forgery_acceptance_probability": fap_est.rate if fap_est else None,
        "forgery_acceptance_ci": [fap_est.lower, fap_est.upper] if fap_est else None,
        "threshold": threshold,
        "latency_ms": {
            "signature_generation_mean": float(np.mean(lat_sign)),
            "quantum_channel_mean": float(np.mean(lat_channel)),
            "verification_mean": float(np.mean(lat_verify)),
            "detection_mean": float(np.mean(lat_detect)),
            "end_to_end_mean": float(np.mean(lat_total)),
            "end_to_end_median": float(np.median(lat_total)),
        },
        "throughput_sessions_per_sec": (
            1000.0 / float(np.mean(lat_total)) if np.mean(lat_total) > 0 else 0.0
        ),
        "mean_teleportation_fidelity": float(
            np.mean([r.telemetry.mean_fidelity for r in legit])
        ),
    }


def per_attack_table(attacks: Dict[str, List]) -> pd.DataFrame:
    """Detection rate per attack class, each with a confidence interval."""
    rows = []
    for name, rs in attacks.items():
        det = sum(1 for r in rs if r.decision != "LEGITIMATE")
        est = rate_with_interval(det, len(rs), method="clopper_pearson")
        correct = sum(1 for r in rs if r.detected_attack == name)
        rows.append({
            "attack_type": name,
            "trials": len(rs),
            "detected": det,
            "missed": len(rs) - det,
            "detection_rate": est.rate,
            "ci_lower": est.lower,
            "ci_upper": est.upper,
            "correctly_classified": correct,
            "classification_accuracy": correct / len(rs) if rs else 0.0,
            "mean_anomaly_score": float(np.mean([r.anomaly_score for r in rs])),
            "mean_fidelity": float(np.mean([r.telemetry.mean_fidelity for r in rs])),
            "mean_purity": float(np.mean([r.telemetry.mean_purity for r in rs])),
            "mean_verification_score": float(
                np.mean([r.verification_score for r in rs])
            ),
        })
    return pd.DataFrame(rows)


def comparison_table(legit: List, attacks: Dict[str, List]) -> pd.DataFrame:
    """NORMAL vs ATTACK, side by side, for every metric (Phase 11)."""
    def agg(rs: List) -> Dict[str, float]:
        return {
            "fidelity": float(np.mean([r.telemetry.mean_fidelity for r in rs])),
            "trace_distance": float(np.mean([r.telemetry.mean_trace_distance for r in rs])),
            "purity": float(np.mean([r.telemetry.mean_purity for r in rs])),
            "entropy": float(np.mean([r.telemetry.measurement_entropy for r in rs])),
            "mismatch_rate": float(np.mean([r.telemetry.mismatch_rate for r in rs])),
            "verification_score": float(np.mean([r.verification_score for r in rs])),
            "anomaly_score": float(np.mean([r.anomaly_score for r in rs])),
        }

    base = agg(legit)
    rows = [{"condition": "NORMAL", **base}]
    for name, rs in attacks.items():
        a = agg(rs)
        row = {"condition": name, **a}
        for k in base:
            row[f"delta_{k}"] = a[k] - base[k]
        rows.append(row)
    return pd.DataFrame(rows)


def intensity_table(attacks: Dict[str, List]) -> pd.DataFrame:
    """Detection rate as a function of attack intensity."""
    rows = []
    for name, rs in attacks.items():
        for inten in sorted({r.attack_intensity for r in rs}):
            sub = [r for r in rs if r.attack_intensity == inten]
            det = sum(1 for r in sub if r.decision != "LEGITIMATE")
            rows.append({
                "attack_type": name,
                "intensity": inten,
                "trials": len(sub),
                "detected": det,
                "detection_rate": det / len(sub) if sub else 0.0,
                "mean_anomaly_score": float(np.mean([r.anomaly_score for r in sub])),
                "mean_fidelity": float(np.mean([r.telemetry.mean_fidelity for r in sub])),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Scalability (Phase 9/19)
# ---------------------------------------------------------------------------

def scalability_sweep(
    lengths: Sequence[int] = (4, 8, 16, 24, 32),
    shot_counts: Sequence[int] = (64, 128, 256, 512),
    trials: int = 12,
    seed: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Measure how cost scales with signature length and shot count.

    Both sweeps run the real pipeline, so the timings include the quantum
    channel rather than a model of it. Each configuration gets its own
    calibrated baseline, because the threshold and the deviation metrics
    are only meaningful against a baseline measured under the same
    conditions.

    Returns
    -------
    tuple[DataFrame, DataFrame]
        ``(length_sweep, shots_sweep)``.
    """
    length_rows = []
    for L in lengths:
        r = SessionRunner(signature_length=L, shots=256, teleport_shots=128,
                          seed=seed)
        r.setup(private_seed=bytes([seed % 256]) * 32)
        r.calibrate_baseline(n_sessions=6)
        sessions = [r.run(message=f"scale {L} {i}".encode(), seed_offset=i)
                    for i in range(trials)]
        length_rows.append({
            "signature_length": L,
            "trials": trials,
            "sign_ms": float(np.mean([x.latency_sign_ms for x in sessions])),
            "channel_ms": float(np.mean([x.latency_channel_ms for x in sessions])),
            "measure_ms": float(np.mean([x.latency_measure_ms for x in sessions])),
            "detect_ms": float(np.mean([x.latency_detect_ms for x in sessions])),
            "total_ms": float(np.mean([x.latency_total_ms for x in sessions])),
            "median_total_ms": float(np.median([x.latency_total_ms for x in sessions])),
            "throughput_per_sec": 1000.0 / float(np.mean(
                [x.latency_total_ms for x in sessions])),
            "mean_fidelity": float(np.mean(
                [x.telemetry.mean_fidelity for x in sessions])),
        })
        print(f"      length={L:>3}  "
              f"{length_rows[-1]['total_ms']:7.2f} ms  "
              f"{length_rows[-1]['throughput_per_sec']:6.1f} sessions/s")

    shots_rows = []
    for sh in shot_counts:
        r = SessionRunner(signature_length=16, shots=sh, teleport_shots=128,
                          seed=seed)
        r.setup(private_seed=bytes([seed % 256]) * 32)
        r.calibrate_baseline(n_sessions=6)
        sessions = [r.run(message=f"shots {sh} {i}".encode(), seed_offset=i)
                    for i in range(trials)]
        scores = [x.anomaly_score for x in sessions]
        shots_rows.append({
            "shots_per_element": sh,
            "trials": trials,
            "total_ms": float(np.mean([x.latency_total_ms for x in sessions])),
            "throughput_per_sec": 1000.0 / float(np.mean(
                [x.latency_total_ms for x in sessions])),
            # Baseline score spread narrows as shots rise: more shots mean
            # less sampling noise, so legitimate sessions cluster tighter
            # and the detector can run a tighter threshold.
            "baseline_score_std": float(np.std(scores)),
            "mean_fidelity": float(np.mean(
                [x.telemetry.mean_fidelity for x in sessions])),
        })
        print(f"      shots={sh:>4}  "
              f"{shots_rows[-1]['total_ms']:7.2f} ms  "
              f"score std={shots_rows[-1]['baseline_score_std']:.5f}")

    return pd.DataFrame(length_rows), pd.DataFrame(shots_rows)


def make_scalability_plots(length_df: pd.DataFrame, shots_df: pd.DataFrame) -> List[str]:
    """Render the scalability figures."""
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    made: List[str] = []

    # Latency breakdown vs signature length (stacked stages)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    bottom = np.zeros(len(length_df))
    for col, label in (("sign_ms", "signature generation"),
                       ("channel_ms", "quantum channel"),
                       ("measure_ms", "measurement + verification"),
                       ("detect_ms", "threat detection")):
        ax.bar(length_df["signature_length"].astype(str), length_df[col],
               bottom=bottom, label=label)
        bottom += length_df[col].to_numpy()
    ax.set_xlabel("Signature length (elements)")
    ax.set_ylabel("Mean latency (ms)")
    ax.set_title("Latency Breakdown vs Signature Length")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "latency_vs_length.png", dpi=140)
    plt.close(fig)
    made.append("latency_vs_length.png")

    # Throughput vs signature length
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(length_df["signature_length"], length_df["throughput_per_sec"],
            marker="o", color="seagreen")
    ax.set_xlabel("Signature length (elements)")
    ax.set_ylabel("Sessions per second")
    ax.set_title("Throughput vs Signature Length")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "throughput_vs_length.png", dpi=140)
    plt.close(fig)
    made.append("throughput_vs_length.png")

    # Shot count: cost vs statistical precision
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(shots_df["shots_per_element"], shots_df["total_ms"],
            marker="o", color="steelblue", label="latency (ms)")
    ax.set_xlabel("Shots per element")
    ax.set_ylabel("Mean latency (ms)")
    ax2 = ax.twinx()
    ax2.plot(shots_df["shots_per_element"], shots_df["baseline_score_std"],
             marker="s", color="darkorange", label="baseline score std")
    ax2.set_ylabel("Baseline anomaly-score std")
    ax.set_title("Shot Count: Cost vs Statistical Precision")
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [l.get_label() for l in lines], fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "scalability_vs_shots.png", dpi=140)
    plt.close(fig)
    made.append("scalability_vs_shots.png")

    return made



# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def make_plots(
    metrics: Dict[str, Any],
    per_attack: pd.DataFrame,
    sweep: pd.DataFrame,
    intensity: pd.DataFrame,
    comparison: pd.DataFrame,
    threshold: float,
) -> List[str]:
    """Render every figure from the measured data."""
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    made: List[str] = []

    # Confusion matrix
    c = metrics["confusion"]
    cm = np.array([[c["tn"], c["fp"]], [c["fn"], c["tp"]]])
    fig, ax = plt.subplots(figsize=(5.5, 4.8))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks([0, 1], ["Pred. Legitimate", "Pred. Attack"])
    ax.set_yticks([0, 1], ["Actual Legitimate", "Actual Attack"])
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{cm[i, j]}", ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black",
                    fontsize=14)
    ax.set_title("Confusion Matrix")
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "confusion_matrix.png", dpi=140)
    plt.close(fig)
    made.append("confusion_matrix.png")

    # FAR / FRR vs threshold
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(sweep["threshold"], sweep["far"], label="FAR (attack passes)")
    ax.plot(sweep["threshold"], sweep["frr"], label="FRR (legitimate denied)")
    ax.axvline(threshold, color="crimson", ls="--",
               label=f"selected = {threshold:.4f}")
    ax.set_xlabel("Anomaly-score threshold")
    ax.set_ylabel("Rate")
    ax.set_title("FAR / FRR vs Threshold")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "far_frr_vs_threshold.png", dpi=140)
    plt.close(fig)
    made.append("far_frr_vs_threshold.png")

    # Detection rate vs intensity
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for name in sorted(intensity["attack_type"].unique()):
        sub = intensity[intensity["attack_type"] == name]
        ax.plot(sub["intensity"], sub["detection_rate"], marker="o", label=name)
    ax.set_xlabel("Attack intensity")
    ax.set_ylabel("Detection rate")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("Detection Rate vs Attack Intensity")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "detection_vs_intensity.png", dpi=140)
    plt.close(fig)
    made.append("detection_vs_intensity.png")

    # Fidelity vs channel noise
    chan = intensity[intensity["attack_type"] == "CHANNEL_MANIPULATION"]
    if len(chan):
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax.plot(chan["intensity"], chan["mean_fidelity"], marker="s", color="darkorange")
        ax.set_xlabel("Depolarizing probability p")
        ax.set_ylabel("Mean teleportation fidelity")
        ax.set_title("Fidelity vs Channel Noise")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(PLOTS_DIR / "fidelity_vs_noise.png", dpi=140)
        plt.close(fig)
        made.append("fidelity_vs_noise.png")

    # Attack comparison
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(per_attack))
    ax.bar(x, per_attack["detection_rate"], color="steelblue")
    ax.errorbar(
        x, per_attack["detection_rate"],
        yerr=[per_attack["detection_rate"] - per_attack["ci_lower"],
              per_attack["ci_upper"] - per_attack["detection_rate"]],
        fmt="none", ecolor="black", capsize=4,
    )
    ax.set_xticks(x, [t.replace("_", "\n") for t in per_attack["attack_type"]], fontsize=8)
    ax.set_ylabel("Detection rate (95% CI)")
    ax.set_ylim(0, 1.08)
    ax.set_title("Detection Rate by Attack Class")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "attack_comparison.png", dpi=140)
    plt.close(fig)
    made.append("attack_comparison.png")

    # Normal vs attack telemetry
    fig, ax = plt.subplots(figsize=(8, 4.5))
    metrics_to_plot = ["fidelity", "purity", "anomaly_score", "mismatch_rate"]
    width = 0.2
    xs = np.arange(len(comparison))
    for i, m in enumerate(metrics_to_plot):
        ax.bar(xs + i * width, comparison[m], width, label=m)
    ax.set_xticks(xs + 1.5 * width,
                  [c.replace("_", "\n") for c in comparison["condition"]], fontsize=7)
    ax.set_title("Normal vs Attack Telemetry")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "normal_vs_attack.png", dpi=140)
    plt.close(fig)
    made.append("normal_vs_attack.png")

    return made


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def git_commit() -> Optional[str]:
    """Return the current commit hash, or ``None`` outside a git repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_ROOT, capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=200,
                    help="sessions per class (legitimate and each attack)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--signature-length", type=int, default=16)
    ap.add_argument("--shots", type=int, default=256)
    ap.add_argument("--baseline-sessions", type=int, default=40)
    ap.add_argument("--max-frr", type=float, default=0.05,
                    help="FRR ceiling used when selecting the threshold")
    ap.add_argument("--quick", action="store_true",
                    help="small, fast run for smoke-testing")
    ap.add_argument("--no-scalability", action="store_true",
                    help="skip the scalability sweep (it recalibrates per config)")
    args = ap.parse_args()

    if args.quick:
        args.trials = min(args.trials, 30)
        args.baseline_sessions = min(args.baseline_sessions, 10)

    set_seed(args.seed)
    t_start = time.perf_counter()

    print(_SEP)
    print("  FINAL EXPERIMENT -- Quantum-Inspired Cyber Threat Detection")
    print("  SIH26141 | canonical source of all published metrics")
    print(_SEP)
    print(f"  trials/class     : {args.trials}")
    print(f"  signature length : {args.signature_length}")
    print(f"  shots/element    : {args.shots}")
    print(f"  seed             : {args.seed}")
    print(_SEP)

    runner = SessionRunner(
        signature_length=args.signature_length,
        shots=args.shots,
        teleport_shots=128,
        seed=args.seed,
        use_teleportation=True,
    )
    runner.setup(private_seed=bytes([args.seed % 256]) * 32)

    # --- 1. Baseline -------------------------------------------------
    print(f"\n[1/7] Calibrating baseline from {args.baseline_sessions} "
          f"legitimate sessions...")
    baseline = runner.calibrate_baseline(n_sessions=args.baseline_sessions)
    print(f"      mismatch={baseline['mismatch_mean']:.4f}"
          f"+-{baseline['mismatch_std']:.4f}  "
          f"fidelity={baseline['fidelity_mean']:.4f}  "
          f"entropy={baseline['entropy_mean']:.4f}")

    # --- 2. Legitimate sessions ---------------------------------------
    print(f"\n[2/7] Running {args.trials} legitimate sessions...")
    legit = run_legitimate(runner, args.trials)

    # --- 3. Attack sessions -------------------------------------------
    print(f"\n[3/7] Running {args.trials} sessions per attack class...")
    attacks: Dict[str, List] = {}
    for name in ATTACK_CLASSES:
        t0 = time.perf_counter()
        attacks[name] = run_attack_class(runner, name, args.trials, args.seed)
        print(f"      {name:<28} {len(attacks[name]):>4} sessions "
              f"({time.perf_counter() - t0:5.1f}s)")

    # --- 4. Threshold calibration --------------------------------------
    print(f"\n[4/7] Calibrating detection threshold "
          f"(rule: min FAR s.t. FRR <= {args.max_frr:.0%})...")
    legit_scores = [r.anomaly_score for r in legit]
    attack_scores = [r.anomaly_score for rs in attacks.values() for r in rs]
    threshold, sweep, rule = calibrate_threshold(
        legit_scores, attack_scores, max_frr=args.max_frr
    )
    print(f"      selected threshold = {threshold:.6f}")
    print(f"      rule: {rule}")

    # --- 5. Re-score at the calibrated threshold ------------------------
    print("\n[5/7] Re-scoring all sessions at the calibrated threshold...")
    rescore(legit, threshold, baseline)
    for rs in attacks.values():
        rescore(rs, threshold, baseline)

    # --- 6. Metrics -----------------------------------------------------
    print("\n[6/7] Computing metrics...")
    metrics = compute_metrics(legit, attacks, threshold)
    per_attack = per_attack_table(attacks)
    comparison = comparison_table(legit, attacks)
    intensity = intensity_table(attacks)

    # --- 7. Write results ------------------------------------------------
    print("\n[7/7] Writing results and plots...")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    config = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "seed": args.seed,
        "trials_per_class": args.trials,
        "baseline_sessions": args.baseline_sessions,
        "signature_length": args.signature_length,
        "shots_per_element": args.shots,
        "teleport_shots": runner.teleport_shots,
        "key_table_size": runner.table_size,
        "attack_intensities": list(INTENSITIES),
        "attack_classes": list(ATTACK_CLASSES),
        "channel_noise_model": "depolarizing (Qiskit Aer, channel qubits only)",
        "simulator": "AerSimulator(method='density_matrix')",
        "teleportation_enabled": runner.use_teleportation,
        "threshold_rule": rule,
        "selected_threshold": threshold,
        "max_frr_constraint": args.max_frr,
        "detector_weights": WEIGHTS,
        "detector_normalisers": {
            "mismatch": NORM_MISMATCH, "fidelity": NORM_FIDELITY,
            "trace_distance": NORM_TRACE, "entropy": NORM_ENTROPY,
        },
        "baseline": baseline,
        "runtime_seconds": None,
    }

    all_sessions = legit + [r for rs in attacks.values() for r in rs]
    pd.DataFrame([r.as_row() for r in all_sessions]).to_csv(
        RESULTS_DIR / "sessions.csv", index=False)
    per_attack.to_csv(RESULTS_DIR / "attack_metrics.csv", index=False)
    comparison.to_csv(RESULTS_DIR / "comparison.csv", index=False)
    intensity.to_csv(RESULTS_DIR / "intensity_analysis.csv", index=False)
    sweep.to_csv(RESULTS_DIR / "threshold_analysis.csv", index=False)

    c = metrics["confusion"]
    pd.DataFrame(
        [[c["tn"], c["fp"]], [c["fn"], c["tp"]]],
        columns=["Predicted Legitimate", "Predicted Attack"],
        index=["Actual Legitimate", "Actual Attack"],
    ).to_csv(RESULTS_DIR / "confusion_matrix.csv")

    plots = make_plots(metrics, per_attack, sweep, intensity, comparison, threshold)

    # --- Scalability -----------------------------------------------------
    if not args.no_scalability:
        print("\n      Scalability sweep (signature length, then shot count):")
        length_df, shots_df = scalability_sweep(
            trials=6 if args.quick else 12, seed=args.seed
        )
        length_df.to_csv(RESULTS_DIR / "scalability_length.csv", index=False)
        shots_df.to_csv(RESULTS_DIR / "scalability_shots.csv", index=False)
        plots += make_scalability_plots(length_df, shots_df)
        metrics["scalability"] = {
            "by_signature_length": length_df.to_dict(orient="records"),
            "by_shot_count": shots_df.to_dict(orient="records"),
        }

    runtime = time.perf_counter() - t_start
    config["runtime_seconds"] = round(runtime, 2)
    (RESULTS_DIR / "experiment_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8")
    (RESULTS_DIR / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8")

    # Persist the calibrated threshold so the engine picks it up.
    _write_threshold_to_config(
        threshold,
        signature_length=args.signature_length,
        shots=args.shots,
    )

    # --- Report ---------------------------------------------------------
    print(f"\n{_SEP}")
    print("  RESULTS")
    print(_SEP)
    print(f"  Sessions            : {len(legit)} legitimate, "
          f"{sum(len(v) for v in attacks.values())} attack")
    print(f"  Threshold           : {threshold:.6f}")
    print(f"  Accuracy            : {metrics['accuracy'] * 100:.2f}%")
    print(f"  Precision           : {metrics['precision'] * 100:.2f}%")
    print(f"  Recall / Detection  : {metrics['detection_rate'] * 100:.2f}% "
          f"[{metrics['detection_rate_ci'][0] * 100:.2f}, "
          f"{metrics['detection_rate_ci'][1] * 100:.2f}]")
    print(f"  F1                  : {metrics['f1'] * 100:.2f}%")
    print(f"  FAR (attack passes) : {metrics['far'] * 100:.2f}% "
          f"[{metrics['far_ci'][0] * 100:.2f}, {metrics['far_ci'][1] * 100:.2f}] "
          f"n={metrics['far_n']}")
    print(f"  FRR (legit denied)  : {metrics['frr'] * 100:.2f}% "
          f"[{metrics['frr_ci'][0] * 100:.2f}, {metrics['frr_ci'][1] * 100:.2f}] "
          f"n={metrics['frr_n']}")
    if metrics["forgery_acceptance_probability"] is not None:
        print(f"  Forgery acceptance  : "
              f"{metrics['forgery_acceptance_probability'] * 100:.2f}% "
              f"[{metrics['forgery_acceptance_ci'][0] * 100:.2f}, "
              f"{metrics['forgery_acceptance_ci'][1] * 100:.2f}]")
    print(f"  Mean teleport F     : {metrics['mean_teleportation_fidelity']:.6f}")
    print(f"  End-to-end latency  : "
          f"{metrics['latency_ms']['end_to_end_mean']:.2f} ms")
    print(f"  Throughput          : "
          f"{metrics['throughput_sessions_per_sec']:.2f} sessions/s")

    print(f"\n  Per-attack detection:")
    for _, r in per_attack.iterrows():
        print(f"    {r['attack_type']:<28} {r['detection_rate'] * 100:6.2f}% "
              f"[{r['ci_lower'] * 100:5.2f}, {r['ci_upper'] * 100:6.2f}]  "
              f"classified {r['classification_accuracy'] * 100:5.1f}%")

    print(f"\n  Wrote {len(plots)} plots + {7 if args.no_scalability else 9} data files to")
    print(f"    {RESULTS_DIR}")
    print(f"  Runtime: {runtime:.1f}s")
    print(_SEP)
    return 0


def _write_threshold_to_config(
    threshold: float,
    signature_length: Optional[int] = None,
    shots: Optional[int] = None,
) -> None:
    """Persist the calibrated threshold into quantum_config.yaml.

    Makes calibration reproducible *and* effective: the engine reads this
    value on its next run, so the threshold in force is always the one the
    experiment selected, never a hand-picked constant.
    """
    import yaml

    path = _ROOT / "config" / "quantum_config.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("detection", {})
    data["detection"]["warning_threshold"] = round(float(threshold), 6)
    data["detection"]["critical_threshold"] = round(min(1.0, threshold * 2.5), 6)
    data["detection"]["calibrated_by"] = "experiments/run_final_experiment.py"
    # Record the configuration this threshold is valid for. A threshold is
    # not universal: signature length and shot count change the granularity
    # and spread of the mismatch rate, so reusing it under a different
    # configuration inflates the false-rejection rate.
    if signature_length is not None:
        data["detection"]["calibrated_for_signature_length"] = int(signature_length)
    if shots is not None:
        data["detection"]["calibrated_for_shots"] = int(shots)
    data["detection"]["calibrated_at"] = datetime.now(timezone.utc).isoformat()

    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    logger.info("Calibrated threshold %.6f written to %s", threshold, path)


if __name__ == "__main__":
    raise SystemExit(main())
