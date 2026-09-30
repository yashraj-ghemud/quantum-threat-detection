"""
tests/evaluation/test_security_analysis.py
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import pytest
import pandas as pd
from evaluation.security_analysis import AttackMetrics, analyze_attacks, analyze_intensity, generate_security_report
from evaluation.metrics import ClassificationMetrics
from attacks.runner import AttackScenarioResult

def test_attack_metrics():
    am = AttackMetrics("FORGERY")
    am.add_result(AttackScenarioResult("FORGERY", 0.5, 10, 0.5, 0.4, "THREAT", "DETECTED", ""))
    am.add_result(AttackScenarioResult("FORGERY", 0.1, 10, 0.1, 0.1, "NORMAL", "MISSED", ""))
    
    # Should ignore other attacks
    am.add_result(AttackScenarioResult("REPLAY", 0.5, 10, 0.5, 0.4, "THREAT", "DETECTED", ""))
    
    assert am.trials == 2
    assert am.detected == 1
    assert am.missed == 1
    assert am.detection_rate == 0.5
    assert am.mean_score == 0.25
    assert am.min_score == 0.1
    assert am.max_score == 0.4

def test_analyze_attacks():
    results = [
        AttackScenarioResult("LEGITIMATE", 0.0, 10, 0, 0, "NORMAL", "NOT_APPLICABLE", ""),
        AttackScenarioResult("FORGERY", 0.5, 10, 0.5, 0.4, "THREAT", "DETECTED", ""),
        AttackScenarioResult("REPLAY", 0.5, 10, 0.5, 0.4, "THREAT", "DETECTED", ""),
    ]
    
    metrics_list = analyze_attacks(results)
    
    assert len(metrics_list) == 2
    assert metrics_list[0].attack_type == "FORGERY"
    assert metrics_list[1].attack_type == "REPLAY"

def test_analyze_intensity():
    results = [
        AttackScenarioResult("FORGERY", 0.1, 10, 0.1, 0.1, "NORMAL", "MISSED", ""),
        AttackScenarioResult("FORGERY", 0.1, 10, 0.1, 0.1, "NORMAL", "MISSED", ""),
        AttackScenarioResult("FORGERY", 0.5, 10, 0.5, 0.4, "THREAT", "DETECTED", ""),
    ]
    
    df = analyze_intensity(results)
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert getattr(df.iloc[0], "intensity") == 0.1
    assert getattr(df.iloc[0], "trials") == 2
    assert getattr(df.iloc[0], "detection_rate") == 0.0
    
    assert getattr(df.iloc[1], "intensity") == 0.5
    assert getattr(df.iloc[1], "trials") == 1
    assert getattr(df.iloc[1], "detection_rate") == 1.0


def test_generate_security_report():
    metrics = ClassificationMetrics(
        tp=10, tn=20, fp=5, fn=2,
        accuracy=0.8, precision=0.7, recall=0.8, f1_score=0.75, specificity=0.8,
        far=0.2, frr=0.2, total=37
    )
    
    am1 = AttackMetrics("FORGERY")
    am1.trials = 5; am1.detected = 5; am1.anomaly_scores = [0.8]*5
    am2 = AttackMetrics("CHANNEL_MANIPULATION")
    am2.trials = 5; am2.detected = 1; am2.anomaly_scores = [0.2]*5
    
    report = generate_security_report(metrics, [am1, am2])
    
    assert "PHASE 6" in report
    assert "FORGERY" in report
    assert "CHANNEL_MANIPULATION" in report
    assert "95% CI" in report
    assert "LIMITATIONS" in report
