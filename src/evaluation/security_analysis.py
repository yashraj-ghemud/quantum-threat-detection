"""
evaluation/security_analysis.py
===============================
In-depth security analysis for QDS Threat Detection.

Phase 6 -- SIH26141 | Blockchain & Cybersecurity.

Analyzes attack-specific metrics, intensity effects, threshold sweeping,
and generates structured result records.

No AI/ML libraries used.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd

from attacks.runner import AttackRunner, AttackScenarioResult
from attacks.base import BaseAttack
from evaluation.metrics import ClassificationMetrics, calculate_metrics
from evaluation.error_bounds import wilson_interval


__all__: list[str] = [
    "AttackMetrics",
    "analyze_attacks",
    "analyze_intensity",
    "sweep_thresholds",
    "generate_security_report",
]


class AttackMetrics:
    """Stores performance metrics specific to one attack type."""
    def __init__(self, attack_type: str):
        self.attack_type = attack_type
        self.trials: int = 0
        self.detected: int = 0
        self.missed: int = 0

        self.anomaly_scores: List[float] = []

    def add_result(self, result: AttackScenarioResult) -> None:
        if result.attack_type != self.attack_type:
            return

        self.trials += 1
        if result.detection_status == "DETECTED":
            self.detected += 1
        else:
            self.missed += 1

        self.anomaly_scores.append(result.anomaly_score)

    @property
    def detection_rate(self) -> float:
        if self.trials == 0:
            return 0.0
        return self.detected / self.trials

    @property
    def mean_score(self) -> float:
        if not self.anomaly_scores:
            return 0.0
        return sum(self.anomaly_scores) / len(self.anomaly_scores)

    @property
    def min_score(self) -> float:
        return min(self.anomaly_scores, default=0.0)

    @property
    def max_score(self) -> float:
        return max(self.anomaly_scores, default=0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attack_type": self.attack_type,
            "trials": self.trials,
            "detected": self.detected,
            "missed": self.missed,
            "detection_rate": round(self.detection_rate, 4),
            "mean_score": round(self.mean_score, 6),
            "min_score": round(self.min_score, 6),
            "max_score": round(self.max_score, 6),
        }


def analyze_attacks(results: Sequence[AttackScenarioResult]) -> List[AttackMetrics]:
    """Group experimental results by attack type and compute metrics."""
    metrics_map: Dict[str, AttackMetrics] = {}

    for r in results:
        t = r.attack_type
        if t == "LEGITIMATE":
            continue
        if t not in metrics_map:
            metrics_map[t] = AttackMetrics(t)
        metrics_map[t].add_result(r)

    sorted_types = sorted(list(metrics_map.keys()))
    return [metrics_map[t] for t in sorted_types]


def analyze_intensity(results: Sequence[AttackScenarioResult]) -> pd.DataFrame:
    """Analyze the effect of attack intensity on detection probability.

    Returns a DataFrame containing average score and detection rate per intensity
    for each attack type.
    """
    data = []

    # Group by (attack_type, intensity)
    groups: Dict[Tuple[str, float], List[AttackScenarioResult]] = {}
    for r in results:
        if r.attack_type == "LEGITIMATE":
            continue
        k = (r.attack_type, float(r.intensity))
        if k not in groups:
            groups[k] = []
        groups[k].append(r)

    for (atype, intensity), rlist in groups.items():
        total = len(rlist)
        detected = sum(1 for x in rlist if x.detection_status == "DETECTED")
        scores = [x.anomaly_score for x in rlist]
        mean_score = sum(scores) / total if total > 0 else 0.0

        data.append({
            "attack_type": atype,
            "intensity": intensity,
            "trials": total,
            "detected": detected,
            "detection_rate": detected / total if total > 0 else 0.0,
            "mean_score": mean_score
        })

    # Sort
    if data:
        df = pd.DataFrame(data).sort_values(["attack_type", "intensity"])
    else:
        df = pd.DataFrame(columns=[
            "attack_type", "intensity", "trials", "detected", "detection_rate", "mean_score"
        ])

    return df


def sweep_thresholds(
    runner: "AttackRunner",
    attacks_to_eval: List["BaseAttack"],
    threshold_range: Sequence[float]
) -> pd.DataFrame:
    """Evaluate detector performance across multiple critical thresholds.

    Since changing thresholds via property works, we temporarily override
    the detector's critical threshold, evaluate, and record FAR/FRR/DetectionRate.

    Returns
    -------
    pd.DataFrame
        DataFrame with threshold evaluation.
    """
    data = []

    orig_warn = runner.detector.thresholds.warning
    orig_crit = runner.detector.thresholds.critical

    for t in threshold_range:
        runner.detector.thresholds.critical = t
        runner.detector.thresholds.warning = t * 0.5  # Scale warning proportionally

        # We need to rerun evaluation logically or reclassify existing raw scores.
        # Rerunning is cleaner and ensures everything propagates correctly.
        results: list[AttackScenarioResult] = []

        # Collect legit
        results.append(runner.run_legitimate(seed_offset=8000 + int(t*100)))

        # Collect attacks (we use intensity=0.5 for sweeping)
        for i, atk in enumerate(attacks_to_eval):
            atype = atk.__class__.__name__.replace("Attack", "").upper()
            if atype == "UNAUTHORIZEDVERIFICATION":
                atype = "UNAUTHORIZED_VERIFICATION"
            elif atype == "CHANNELMANIPULATION":
                atype = "CHANNEL_MANIPULATION"

            r = runner.run_attack(atk, atype, intensity=0.5, seed_offset=8100 + i)
            results.append(r)

        m = calculate_metrics(results)

        data.append({
            "threshold": t,
            "far": m.far,
            "frr": m.frr,
            "detection_rate": m.recall,
            "accuracy": m.accuracy,
            "f1_score": m.f1_score
        })

    # Restore
    runner.detector.thresholds.critical = orig_crit
    runner.detector.thresholds.warning = orig_warn

    return pd.DataFrame(data)


def generate_security_report(
    metrics: ClassificationMetrics,
    attack_metrics: List[AttackMetrics],
    far_estimate=None,
    frr_estimate=None,
    dr_estimate=None,
) -> str:
    """Generate a cohesive, text-based security analysis report.

    Parameters
    ----------
    metrics : ClassificationMetrics
        Aggregate confusion-matrix metrics.
    attack_metrics : list[AttackMetrics]
        Per-attack-category breakdown.
    far_estimate, frr_estimate, dr_estimate : RateEstimate or None
        Rates with confidence intervals, from :mod:`evaluation.far_frr`.
        When supplied, every headline rate is printed with its interval and
        sample size.  Rates are binomial estimates from a finite sample, so
        a bare "FAR = 0.00%" is not a defensible claim -- the interval is
        what tells the reader how much the number is worth.
    """
    if not attack_metrics:
        return "NO ATTACK DATA"

    strongest = max(attack_metrics, key=lambda x: x.detection_rate)
    weakest = min(attack_metrics, key=lambda x: x.detection_rate)

    def _fmt(estimate, fallback_rate: float, trials: int) -> str:
        """Render a rate with its confidence interval.

        Falls back to a Wilson interval computed on the spot, so a rate is
        never printed as a bare point estimate.
        """
        if estimate is not None:
            return estimate.as_percent()
        successes = int(round(fallback_rate * trials))
        ci = wilson_interval(successes, trials) if trials > 0 else None
        if ci is None:
            return f"{fallback_rate * 100:.2f}% (n=0)"
        return (
            f"{fallback_rate * 100:.2f}% "
            f"(95% CI [{ci.lower * 100:.2f}%, {ci.upper * 100:.2f}%], n={trials})"
        )

    n_legit = metrics.tn + metrics.fp
    n_attack = metrics.tp + metrics.fn

    lines = [
        "==================================================",
        "  PHASE 6 -- SECURITY ANALYSIS & EVALUATION",
        "==================================================",
        "",
        "OVERALL BEHAVIOR",
        "----------------",
        f"Legitimate Sessions Evaluated: {metrics.tn + metrics.fp}",
        f"Attack Sessions Evaluated:     {metrics.tp + metrics.fn}",
        f"Overall Accuracy:              {metrics.accuracy * 100:.2f}%",
        f"Overall Detection Rate:        "
        f"{_fmt(dr_estimate, metrics.recall, n_attack)}",
        "",
        "RISK ANALYSIS",
        "-------------",
        "All rates below are binomial point estimates shown with their",
        "confidence interval and sample size.  A rate is only as strong as",
        "its upper bound: 0% observed over 25 trials still admits a true",
        "rate near 14%.",
        "",
        f"False Acceptance Rate (FAR):   "
        f"{_fmt(far_estimate, metrics.far, n_attack)}",
        "                               (risk of an attack passing)",
        f"False Rejection Rate (FRR):    "
        f"{_fmt(frr_estimate, metrics.frr, n_attack)}",
        "                               (risk of a legitimate session denied)",
        "",
        "ATTACK PROFILE VULNERABILITY",
        "----------------------------",
        f"Strongest detection:           {strongest.attack_type} ({strongest.detection_rate * 100:.1f}%)",
        f"Weakest detection:             {weakest.attack_type} ({weakest.detection_rate * 100:.1f}%)",
        "",
        "DETAILED ANALYSIS",
        "-----------------"
    ]

    for am in attack_metrics:
        lines.append(
            f"  {am.attack_type:<25} | "
            f"DR: {am.detection_rate*100:>5.1f}% | "
            f"Scores [min: {am.min_score:.4f}, mean: {am.mean_score:.4f}, max: {am.max_score:.4f}]"
        )

    lines.extend([
        "",
        "LIMITATIONS",
        "-----------",
        "1. Metrics are derived from deterministic software simulation, not physical hardware.",
        "2. The channel manipulation attack evaluates specific depolarizing/dephasing noise models;",
        "   other physical side-channel conditions were not simulated.",
        "3. Statistical baseline relies on stable session variance; abruptly varying legitimate",
        "   conditions could induce temporary higher FRR until recalibrated.",
        "=================================================="
    ])

    return "\n".join(lines)
