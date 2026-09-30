"""
evaluation/metrics.py
=====================
Classification metrics for QDS threat detection.

Phase 6 -- SIH26141 | Blockchain & Cybersecurity.

Computes TP, TN, FP, FN, Accuracy, Precision, Recall, F1, FAR, FRR,
and generates confusion matrices.

No AI/ML libraries used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from attacks.runner import AttackScenarioResult

__all__: list[str] = [
    "ClassificationMetrics",
    "calculate_metrics",
    "generate_confusion_matrix",
    "print_confusion_matrix",
]


@dataclass
class ClassificationMetrics:
    """Standard binary classification metrics."""
    tp: int
    tn: int
    fp: int
    fn: int
    
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    specificity: float
    
    far: float  # False Acceptance Rate
    frr: float  # False Rejection Rate
    
    total: int
    
    
def calculate_metrics(results: Sequence[AttackScenarioResult]) -> ClassificationMetrics:
    """Calculate classification metrics from execution results.
    
    Definitions:
    - Positive = Attack
    - Negative = Legitimate
    - TP = Attack correctly DETECTED
    - FN = Attack incorrectly MISSED 
    - TN = Legitimate correctly accepted (classification == NORMAL)
    - FP = Legitimate incorrectly rejected (classification in SUSPICIOUS/THREAT)
    
    Parameters
    ----------
    results : Sequence[AttackScenarioResult]
        Combined legitimate and attack results.
        
    Returns
    -------
    ClassificationMetrics
    """
    tp = 0
    tn = 0
    fp = 0
    fn = 0
    
    for r in results:
        is_attack = r.attack_type != "LEGITIMATE"
        
        if is_attack:
            if r.detection_status == "DETECTED":
                tp += 1
            else:
                fn += 1
        else:
            # LEGITIMATE
            if r.classification == "NORMAL":
                tn += 1
            else:
                fp += 1
                
    total = tp + tn + fp + fn
    
    # Safe division helpers
    def safe_div(num: float, den: float) -> float:
        return num / den if den > 0 else 0.0
        
    accuracy = safe_div(tp + tn, total)
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1_score = safe_div(2 * precision * recall, precision + recall)
    specificity = safe_div(tn, tn + fp)
    
    # The positive class here is "attack" (see the TP/FN assignment above),
    # so the error types map to the security rates as follows:
    #
    #   FN = an attack session that was NOT detected -> the system ACCEPTED
    #        a forgery. That is a false ACCEPTANCE.
    #   FP = a legitimate session flagged as an attack -> the system REJECTED
    #        an honest user. That is a false REJECTION.
    #
    # An earlier revision had these two the wrong way round (far = fp/(fp+tn),
    # frr = fn/(fn+tp)), which inverted every headline security number: the
    # figure published as "FAR - risk of an attack passing" was in fact the
    # rate of turning away legitimate users, and vice versa.
    #
    # FAR = FN / (FN + TP)   -- attack sessions that slipped through
    far = safe_div(fn, fn + tp)
    # FRR = FP / (FP + TN)   -- legitimate sessions wrongly denied
    frr = safe_div(fp, fp + tn)
    
    return ClassificationMetrics(
        tp=tp, tn=tn, fp=fp, fn=fn,
        accuracy=accuracy, precision=precision,
        recall=recall, f1_score=f1_score,
        specificity=specificity,
        far=far, frr=frr,
        total=total
    )


def generate_confusion_matrix(metrics: ClassificationMetrics) -> List[List[int]]:
    """Format TP, TN, FP, FN as a 2x2 confusion matrix list.
    
    Returns
    -------
    List[List[int]]
        [[TN, FP],
         [FN, TP]]
    """
    return [
        [metrics.tn, metrics.fp],
        [metrics.fn, metrics.tp]
    ]


def print_confusion_matrix(metrics: ClassificationMetrics) -> str:
    """Return a formatted string representation of the confusion matrix."""
    lines = [
        "CONFUSION MATRIX",
        "================",
        "                  Predicted Legitimate    Predicted Attack",
        f"Actual Legitimate | TN: {metrics.tn:<15} | FP: {metrics.fp:<15}",
        f"Actual Attack     | FN: {metrics.fn:<15} | TP: {metrics.tp:<15}"
    ]
    return "\n".join(lines)
