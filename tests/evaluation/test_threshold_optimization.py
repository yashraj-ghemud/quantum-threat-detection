"""
tests/evaluation/test_threshold_optimization.py
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import pytest
from attacks.runner import AttackScenarioResult
from evaluation.threshold_optimization import optimize_threshold, calculate_weighted_security_score
from security.detector import DetectionResult
from evaluation.metrics import ClassificationMetrics

def _mock_result(attack_type, anomaly_score):
    return AttackScenarioResult(
        attack_type=attack_type,
        anomaly_score=anomaly_score,
        classification="NORMAL" if anomaly_score < 0.2 else "THREAT",
        detection_status="MISSED" if anomaly_score < 0.2 else "DETECTED"
    )

def test_optimize_threshold():
    legit = [
        _mock_result("LEGITIMATE", 0.05),
        _mock_result("LEGITIMATE", 0.08),
        _mock_result("LEGITIMATE", 0.15) # highest legit score
    ]
    attacks = [
        _mock_result("FORGERY", 0.25),
        _mock_result("REPLAY", 0.30),
        _mock_result("ATTACK", 0.12) # very low score attack
    ]
    
    # Sweep thresholds: 0.0, 0.1, 0.2, 0.3
    # If 0.1: legit[2] is False Positive. FRR is FN/(FN+TP). 
    # With max_frr=0.20, maybe 0.1 gives FAR=0.33, 0.2 gives FAR=0.
    
    res = optimize_threshold(legit, attacks, candidate_thresholds=[0.10, 0.18, 0.28], max_frr=0.50, critical_offset=0.0)
    
    # Sweep (FAR = missed attacks, FRR = legitimate wrongly denied):
    #   t=0.10 -> all 3 attacks caught, 1 legit flagged: FAR=0.000, FRR=0.333
    #   t=0.18 -> 1 attack missed, 0 legit flagged:      FAR=0.333, FRR=0.000
    #   t=0.28 -> 2 attacks missed, 0 legit flagged:     FAR=0.667, FRR=0.000
    # The optimiser minimises FAR subject to FRR <= max_frr (0.50), so it
    # picks t=0.10 -- the point that lets no attack through.
    assert res.best_threshold == 0.10
    assert res.best_metrics.far == 0.0
    assert pytest.approx(res.best_metrics.frr) == 1/3
    
def test_weighted_security_score():
    attacks = [
        _mock_result("FORGERY", 0.25), # DETECTED
        _mock_result("FORGERY", 0.30), # DETECTED
        _mock_result("CHANNEL_MANIPULATION", 0.15), # MISSED
    ]
    
    weights = {"FORGERY": 2.0, "CHANNEL_MANIPULATION": 1.0}
    # DR forgery = 2/2 = 1.0
    # DR channel = 0/1 = 0.0
    # Weighted = (1.0 * 2.0 + 0.0 * 1.0) / 3.0 = 2.0 / 3.0
    score = calculate_weighted_security_score(attacks, weights)
    assert pytest.approx(score) == 2.0 / 3.0
