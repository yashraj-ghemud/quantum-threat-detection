"""
evaluation/threshold_optimization.py
====================================
Phase 6.5 -- THREAT DETECTOR HARDENING & FAR/FRR OPTIMIZATION.

Sweep thresholds on existing execution results to find optimal operating point.
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence
from copy import deepcopy

from attacks.runner import AttackScenarioResult
from evaluation.metrics import ClassificationMetrics, calculate_metrics
from utils.logger import get_logger

logger = get_logger(__name__)

__all__ = ["ThresholdSweepPoint", "OperatingPointResult", "optimize_threshold", "calculate_weighted_security_score"]

def calculate_weighted_security_score(
    attack_results: Sequence[AttackScenarioResult], 
    weights: dict[str, float]
) -> float:
    """Calculate an attack-weighted security score (0.0 to 1.0).
    
    Raw FAR/FRR is not altered. This just computes a DR weighted sum.
    """
    detect_map = {}
    total_map = {}
    
    for r in attack_results:
        if r.attack_type == "LEGITIMATE": continue
        
        t = r.attack_type.upper()
        if t not in total_map:
            total_map[t] = 0
            detect_map[t] = 0
            
        total_map[t] += 1
        if r.detection_status == "DETECTED":
            detect_map[t] += 1
            
    if not total_map:
        return 0.0
        
    num = 0.0
    den = 0.0
    
    for t, total in total_map.items():
        w = weights.get(t, 1.0)
        dr = detect_map[t] / total if total > 0 else 0.0
        num += dr * w
        den += w
        
    return num / den if den > 0 else 0.0

@dataclass
class ThresholdSweepPoint:
    threshold: float
    metrics: ClassificationMetrics
    satisfies_constraint: bool

@dataclass
class OperatingPointResult:
    best_threshold: Optional[float]
    best_metrics: Optional[ClassificationMetrics]
    sweep_results: List[ThresholdSweepPoint]
    constraint_max_frr: float

def apply_threshold_to_results(
    results: Sequence[AttackScenarioResult],
    warning_threshold: float,
    critical_threshold: float = 1.0
) -> List[AttackScenarioResult]:
    """Recalculate detection status purely based on new thresholds without running simulations."""
    new_results = []
    for r in results:
        new_r = deepcopy(r)
        
        # Determine new classification
        if new_r.anomaly_score >= critical_threshold:
            new_r.classification = "THREAT"
        elif new_r.anomaly_score >= warning_threshold:
            new_r.classification = "SUSPICIOUS"
        else:
            new_r.classification = "NORMAL"
            
        # Determine new detection status based on classification & replay
        detected = False
        reasons = []
        if new_r.classification in ("SUSPICIOUS", "THREAT"):
            detected = True
            reasons.append(f"classification={new_r.classification}")
        if new_r.replay_detected:
            detected = True
            reasons.append("replay consistency check failed")
            
        # Unauthorized check forces REJECTED (already handled in runner, but if it has it, we keep it)
        if new_r.authorization_status == "UNAUTHORIZED":
            new_r.classification = "REJECTED"
            new_r.detection_status = "DETECTED"
        else:
            new_r.detection_status = "DETECTED" if detected else "MISSED"
            
        new_results.append(new_r)
        
    return new_results

def optimize_threshold(
    legitimate_results: Sequence[AttackScenarioResult],
    attack_results: Sequence[AttackScenarioResult],
    candidate_thresholds: Sequence[float],
    max_frr: float = 0.10,
    critical_offset: float = 0.10,
) -> OperatingPointResult:
    """Find threshold that minimizes FAR while keeping FRR <= max_frr."""
    all_results = list(legitimate_results) + list(attack_results)
    
    sweep_results = []
    
    best_t = None
    best_m = None
    best_far = float('inf')
    
    for t in sorted(candidate_thresholds):
        # We sweep warning threshold. Critical is just warning + offset
        warn_t = t
        crit_t = min(1.0, t + critical_offset)
        
        eval_results = apply_threshold_to_results(all_results, warn_t, crit_t)
        metrics = calculate_metrics(eval_results)
        
        satisfies = metrics.frr <= max_frr
        sweep_results.append(ThresholdSweepPoint(t, metrics, satisfies))
        
        if satisfies and metrics.far < best_far:
            best_far = metrics.far
            best_t = t
            best_m = metrics
            
    if best_t is None:
        logger.warning(f"No threshold satisfied FRR <= {max_frr:.2f}")
    else:
        logger.info(f"Selected threshold={best_t:.4f} with FAR={best_m.far:.4f}, FRR={best_m.frr:.4f}")
        
    return OperatingPointResult(
        best_threshold=best_t,
        best_metrics=best_m,
        sweep_results=sweep_results,
        constraint_max_frr=max_frr
    )
