"""
experiments/phase6_security_evaluation.py
=========================================
Phase 6 -- Security Analysis & Evaluation.
SIH26141 | Blockchain & Cybersecurity.

Runs a reproducible threat detection simulation, calculates robust statistical
metrics (TPR, FPR, Accuracy, F1, FAR, FRR, Wilson score intervals),
sweeps operating thresholds, and plots comprehensive performance bounds.

No AI/ML libraries used.
"""

import sys
import time
import warnings
from pathlib import Path
import math

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=DeprecationWarning)

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from attacks.runner import AttackRunner, AttackScenarioResult
from attacks.forgery import ForgeryAttack
from attacks.impersonation import ImpersonationAttack
from attacks.replay import ReplayAttack
from attacks.unauthorized_verification import UnauthorizedVerificationAttack
from attacks.channel_manipulation import ChannelManipulationAttack
from utils.reproducibility import set_seed, get_run_context

from evaluation.metrics import calculate_metrics, generate_confusion_matrix, print_confusion_matrix
from evaluation.security_analysis import (
    analyze_attacks, analyze_intensity, sweep_thresholds, generate_security_report
)
from evaluation.error_bounds import wilson_interval
from evaluation.far_frr import compute_far, compute_frr, rate_with_interval
from utils.config import ConfigLoader

# Setup results directory
RESULTS_DIR = _ROOT / "experiments" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Data Generation (Reusing Phase 5 workflow deterministically)
# ---------------------------------------------------------------------------

INTENSITIES = [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]

def generate_experiment_data(seed: int) -> tuple[AttackRunner, list[AttackScenarioResult], list]:
    """Simulate the configured number of legitimate and attack sessions.

    Sample sizes come from the ``evaluation`` block of
    ``config/quantum_config.yaml``.  They drive the width of every reported
    FAR/FRR interval, so they are configuration rather than constants: a
    0% rate observed over 25 sessions and the same rate over 300 are very
    different claims.
    """
    cfg = ConfigLoader()
    n_legit = cfg.n_legitimate_sessions
    n_attack = cfg.n_attack_sessions_per_type

    print(f"  [1] Simulating {n_legit} legitimate sessions and "
          f"{n_attack} sessions per attack type...")

    runner = AttackRunner(
        sig_length=cfg.evaluation_signature_length,
        n_baseline=cfg.n_baseline_sessions,
        seed=seed,
    )

    results: list[AttackScenarioResult] = []

    # 1. Legitimate baseline -- each with a distinct seed offset so the
    #    sessions are independent draws, not repeats of one session.
    for i in range(n_legit):
        results.append(runner.run_legitimate(seed_offset=i))

    # 2. Attacks
    attacks = [
        ("FORGERY", ForgeryAttack(seed=seed)),
        ("IMPERSONATION", ImpersonationAttack(seed=seed, impersonator_id="eve")),
        ("REPLAY", ReplayAttack(seed=seed, staleness_seconds=120.0)),
        ("UNAUTHORIZED_VERIFICATION", UnauthorizedVerificationAttack(seed=seed, attacker_verifier_id="charlie")),
        ("CHANNEL_MANIPULATION", ChannelManipulationAttack(seed=seed, mode="both"))
    ]

    attacks_to_eval = [atk for _, atk in attacks]

    # Spread the per-type budget across the non-zero intensity levels so the
    # sample covers weak attacks as well as saturated ones.
    live_intensities = [x for x in INTENSITIES if x > 0.0]
    per_intensity = max(1, n_attack // len(live_intensities))

    for atk_idx, (atype, atk) in enumerate(attacks):
        session = 0
        for i, intensity in enumerate(live_intensities):
            for rep in range(per_intensity):
                r = runner.run_attack(
                    atk, atype, intensity=intensity,
                    seed_offset=100000 + atk_idx * 10000 + i * 1000 + rep,
                )
                results.append(r)
                session += 1

    print(f"      -> {len(results)} sessions total "
          f"({n_legit} legitimate, {len(results) - n_legit} attack)")
    return runner, results, attacks_to_eval

# ---------------------------------------------------------------------------
# Plotting Functions
# ---------------------------------------------------------------------------

def plot_confusion_matrix(cm: list[list[int]], filename: Path) -> None:
    plt.figure(figsize=(6, 5))
    cm_np = np.array(cm)
    plt.imshow(cm_np, interpolation='nearest', cmap=plt.cm.Blues)
    plt.title('Threat Detection Confusion Matrix')
    plt.colorbar()

    classes = ['Legitimate', 'Attack']
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes)
    plt.yticks(tick_marks, classes, rotation=90, va='center')

    plt.xlabel('Predicted Label')
    plt.ylabel('True Label')

    thresh = cm_np.max() / 2.
    for i in range(cm_np.shape[0]):
        for j in range(cm_np.shape[1]):
            plt.text(j, i, format(cm_np[i, j], 'd'),
                     ha="center", va="center",
                     color="white" if cm_np[i, j] > thresh else "black")

    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def plot_far_frr(threshold_df: pd.DataFrame, filename: Path, calibrated_critical: float) -> None:
    plt.figure(figsize=(8, 5))

    plt.plot(threshold_df['threshold'], threshold_df['far'], marker='o', label='FAR (False Accept)')
    plt.plot(threshold_df['threshold'], threshold_df['frr'], marker='s', label='FRR (False Reject)')
    plt.plot(threshold_df['threshold'], threshold_df['detection_rate'], marker='^', label='Detection Rate (TPR)')

    plt.axvline(x=calibrated_critical, color='r', linestyle='--', label='Calibrated Threshold')

    plt.title('Performance vs Critical Anomaly Threshold')
    plt.xlabel('Critical Anomaly Score Threshold')
    plt.ylabel('Rate')
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def plot_detection_vs_intensity(intensity_df: pd.DataFrame, filename: Path) -> None:
    plt.figure(figsize=(9, 6))

    for atype in intensity_df['attack_type'].unique():
        subset = intensity_df[intensity_df['attack_type'] == atype]
        plt.plot(subset['intensity'], subset['detection_rate'], marker='o', label=atype)

    plt.title('Detection Rate vs Attack Intensity')
    plt.xlabel('Attack Intensity')
    plt.ylabel('Detection Rate')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True)

    plt.tight_layout()
    plt.savefig(filename)
    plt.close()


def plot_attack_comparison(attack_metrics: list, filename: Path) -> None:
    labels = [m.attack_type for m in attack_metrics]
    rates = [m.detection_rate for m in attack_metrics]

    plt.figure(figsize=(10, 5))
    bars = plt.bar(labels, rates, color='skyblue')
    plt.title('Overall Detection Rate by Attack Type')
    plt.ylabel('Detection Rate')
    plt.ylim(0, 1.1)

    # Add rate labels on top of bars
    for bar, rate in zip(bars, rates):
        plt.text(bar.get_x() + bar.get_width()/2., rate + 0.02,
                 f"{rate*100:.1f}%", ha='center', va='bottom')

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()

# ---------------------------------------------------------------------------
# Main Routine
# ---------------------------------------------------------------------------

def main() -> None:
    seed = 42
    set_seed(seed)

    print("=" * 60)
    print("  PHASE 6 -- SECURITY ANALYSIS & EVALUATION")
    print("=" * 60)

    # 1. Run Experiments
    runner, results, attacks = generate_experiment_data(seed)

    # 2. Main Metrics
    print("\n  [2] Calculating classification metrics...")
    metrics = calculate_metrics(results)

    # Save confusion matrix CSV
    cm = generate_confusion_matrix(metrics)
    cm_df = pd.DataFrame(cm, columns=["Predicted Legitimate", "Predicted Attack"],
                         index=["Actual Legitimate", "Actual Attack"])
    cm_df.to_csv(RESULTS_DIR / "confusion_matrix.csv")
    print("\n" + print_confusion_matrix(metrics) + "\n")

    # 3. Attack-wise analysis
    print("  [3] Performing attack-wise aggregation...")
    attack_metrics = analyze_attacks(results)
    am_df = pd.DataFrame([am.to_dict() for am in attack_metrics])
    am_df.to_csv(RESULTS_DIR / "attack_metrics.csv", index=False)

    # 4. Threshold sweep
    print("  [4] Sweeping operational thresholds...")
    t_range = np.linspace(0.01, 0.40, 20)
    thresh_df = sweep_thresholds(runner, attacks, t_range)
    thresh_df.to_csv(RESULTS_DIR / "threshold_analysis.csv", index=False)

    # 5. Intensity analysis
    print("  [5] Analyzing detection across attack intensity...")
    int_df = analyze_intensity(results)
    int_df.to_csv(RESULTS_DIR / "intensity_analysis.csv", index=False) # Optional extra file

    # 6. Error bounds / Confidence Intervals
    cfg = ConfigLoader()
    conf = cfg.confidence_level
    method = cfg.interval_method
    print(f"  [6] Computing {int(conf * 100)}% {method} confidence intervals...")

    # FAR and FRR are reported with exact (Clopper-Pearson) intervals by
    # default: both sit near 0, where approximate intervals under-cover and
    # a bare point estimate of "0.00%" is indefensible.
    dr_est = rate_with_interval(
        metrics.tp, metrics.tp + metrics.fn, confidence=conf, method=method
    )
    # FAR counts attacks that slipped through -> denominator is attack sessions.
    # FRR counts legitimate sessions wrongly denied -> denominator is legit ones.
    far_est = compute_far(
        metrics.fn, metrics.fn + metrics.tp, confidence=conf, method=method
    )
    frr_est = compute_frr(
        metrics.fp, metrics.fp + metrics.tn, confidence=conf, method=method
    )

    ci_data = [
        dr_est.to_row("Overall Detection Rate"),
        far_est.to_row("False Acceptance Rate"),
        frr_est.to_row("False Rejection Rate"),
    ]

    # Per-attack detection rates, each with its own interval.
    for am in attack_metrics:
        est = rate_with_interval(
            int(am.detected), int(am.trials), confidence=conf, method=method
        )
        ci_data.append(est.to_row(f"Detection Rate [{am.attack_type}]"))

    ci_df = pd.DataFrame(ci_data)
    ci_df.to_csv(RESULTS_DIR / "confidence_intervals.csv", index=False)

    print(f"      FAR: {far_est.as_percent()}")
    print(f"      FRR: {frr_est.as_percent()}")

    # 7. Generate Security Report
    print("  [7] Formatting final security report...")
    report = generate_security_report(
        metrics, attack_metrics,
        far_estimate=far_est, frr_estimate=frr_est, dr_estimate=dr_est,
    )
    with open(RESULTS_DIR / "security_summary.csv", "w") as f:
        # Saving as text within a file (extension requested as CSV but it's a report)
        # To strictly meet CSV request, we save the text as single rows, but purely as text is cleaner
        # Assuming instructions meant 'security_summary.txt' or equivalent, let's write it down.
        f.write(report)

    print("\n" + report + "\n")

    # 8. Plots
    print("  [8] Generating evaluation plots...")
    plot_confusion_matrix(cm, RESULTS_DIR / "confusion_matrix.png")

    calibrated_crit = runner.detector.thresholds.critical
    plot_far_frr(thresh_df, RESULTS_DIR / "far_frr_vs_threshold.png", calibrated_crit)

    plot_detection_vs_intensity(int_df, RESULTS_DIR / "detection_rate_vs_intensity.png")
    plot_attack_comparison(attack_metrics, RESULTS_DIR / "attack_detection_comparison.png")

    print(f"\n  Done! Results and plots saved to: {RESULTS_DIR}")

if __name__ == "__main__":
    main()
