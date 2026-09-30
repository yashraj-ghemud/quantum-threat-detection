"""
tests/evaluation/test_metrics.py
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import pytest
from evaluation.metrics import ClassificationMetrics, calculate_metrics, generate_confusion_matrix, print_confusion_matrix
from attacks.runner import AttackScenarioResult

def test_calculate_metrics():
    # 2 Legitimate (1 NORMAL, 1 SUSPICIOUS -> FP)
    # 2 Attacks (1 DETECTED -> TP, 1 MISSED -> FN)
    results = [
        AttackScenarioResult("LEGITIMATE", 0.0, 10, 0.0, 0.0, "NORMAL", "NOT_APPLICABLE", ""),
        AttackScenarioResult("LEGITIMATE", 0.0, 10, 0.5, 0.5, "SUSPICIOUS", "DETECTED", ""),
        AttackScenarioResult("FORGERY", 0.5, 10, 0.5, 0.5, "THREAT", "DETECTED", ""),
        AttackScenarioResult("FORGERY", 0.1, 10, 0.01, 0.01, "NORMAL", "MISSED", ""),
    ]
    
    metrics = calculate_metrics(results)
    
    assert metrics.tp == 1
    assert metrics.fn == 1
    assert metrics.tn == 1
    assert metrics.fp == 1
    assert metrics.total == 4
    
    assert metrics.accuracy == 2.0 / 4.0
    assert metrics.precision == 1.0 / 2.0
    assert metrics.recall == 1.0 / 2.0  # Detection rate
    assert metrics.f1_score == 0.5
    assert metrics.specificity == 1.0 / 2.0
    
    # FAR = FN/(FN+TP): attacks that slipped through.
    # FRR = FP/(FP+TN): legitimate sessions wrongly denied.
    # (Symmetric here -- see test_far_frr_not_swapped for the asymmetric case.)
    assert metrics.far == 1.0 / (1.0 + 1.0)
    assert metrics.frr == 1.0 / (1.0 + 1.0)


def test_far_frr_not_swapped():
    """FAR must count missed attacks, FRR must count rejected legitimates.

    Uses deliberately asymmetric counts so a swap cannot pass: 3 attacks all
    missed (FN=3, TP=0) and 4 legitimate sessions all correct (FP=0, TN=4).
    Every attack got through, so FAR must be 1.0; no honest user was turned
    away, so FRR must be 0.0.
    """
    results = [
        AttackScenarioResult("LEGITIMATE", 0.0, 10, 0.0, 0.0, "NORMAL", "NOT_APPLICABLE", ""),
        AttackScenarioResult("LEGITIMATE", 0.0, 10, 0.0, 0.0, "NORMAL", "NOT_APPLICABLE", ""),
        AttackScenarioResult("LEGITIMATE", 0.0, 10, 0.0, 0.0, "NORMAL", "NOT_APPLICABLE", ""),
        AttackScenarioResult("LEGITIMATE", 0.0, 10, 0.0, 0.0, "NORMAL", "NOT_APPLICABLE", ""),
        AttackScenarioResult("FORGERY", 1.0, 10, 0.01, 0.01, "NORMAL", "MISSED", ""),
        AttackScenarioResult("FORGERY", 1.0, 10, 0.01, 0.01, "NORMAL", "MISSED", ""),
        AttackScenarioResult("FORGERY", 1.0, 10, 0.01, 0.01, "NORMAL", "MISSED", ""),
    ]
    metrics = calculate_metrics(results)

    assert metrics.tp == 0
    assert metrics.fn == 3
    assert metrics.fp == 0
    assert metrics.tn == 4

    assert metrics.far == 1.0, "every attack passed -> FAR must be 1.0"
    assert metrics.frr == 0.0, "no legitimate session denied -> FRR must be 0.0"


def test_zero_denominator_handling():
    # Only 1 Legitimate, NO Attacks
    results = [
        AttackScenarioResult("LEGITIMATE", 0.0, 10, 0.0, 0.0, "NORMAL", "NOT_APPLICABLE", "")
    ]
    metrics = calculate_metrics(results)
    
    # Should not throw ZeroDivisionError
    assert metrics.tp == 0
    assert metrics.fn == 0
    assert metrics.tn == 1
    assert metrics.fp == 0
    
    assert metrics.accuracy == 1.0
    assert metrics.precision == 0.0 # tp=0, fp=0 -> 0/(0+0) -> 0.0
    assert metrics.recall == 0.0
    assert metrics.f1_score == 0.0
    assert metrics.specificity == 1.0
    
    assert metrics.far == 0.0
    assert metrics.frr == 0.0


def test_generate_confusion_matrix():
    metrics = ClassificationMetrics(
        tp=10, tn=20, fp=5, fn=2,
        accuracy=0, precision=0, recall=0, f1_score=0, specificity=0,
        far=0, frr=0, total=37
    )
    cm = generate_confusion_matrix(metrics)
    assert cm == [
        [20, 5],
        [2, 10]
    ]

def test_print_confusion_matrix():
    metrics = ClassificationMetrics(
        tp=10, tn=20, fp=5, fn=2,
        accuracy=0, precision=0, recall=0, f1_score=0, specificity=0,
        far=0, frr=0, total=37
    )
    s = print_confusion_matrix(metrics)
    assert "TN: 20" in s
    assert "FP: 5" in s
    assert "FN: 2" in s
    assert "TP: 10" in s
