"""
tests/evaluation/test_error_bounds.py
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import pytest
from evaluation.error_bounds import wilson_interval, ConfidenceInterval

def test_wilson_interval_valid():
    # 50 successes out of 100 trials, 95% confidence
    ci = wilson_interval(50, 100, 0.95)
    assert isinstance(ci, ConfidenceInterval)
    assert 0.0 < ci.lower < 0.5 < ci.upper < 1.0
    
    # Values should be bounded
    assert ci.lower >= 0.0
    assert ci.upper <= 1.0

def test_wilson_interval_zero_trials():
    ci = wilson_interval(0, 0, 0.95)
    assert ci.lower == 0.0
    assert ci.upper == 0.0
    
def test_wilson_interval_perfect_classifier():
    # 100 successes out of 100 trials
    ci = wilson_interval(100, 100, 0.95)
    assert ci.upper > 0.999
    assert ci.lower > 0.9 # Should be > 90% bounded

def test_wilson_interval_failed_classifier():
    # 0 successes out of 100 trials
    ci = wilson_interval(0, 100, 0.95)
    assert ci.lower == 0.0
    assert ci.upper < 0.1 # Should be bounded small

def test_wilson_interval_invalid_inputs():
    with pytest.raises(ValueError):
        wilson_interval(10, 5, 0.95) # more successes than trials
        
    with pytest.raises(ValueError):
        wilson_interval(-1, 10, 0.95) # negative successes
        
    with pytest.raises(ValueError):
        wilson_interval(5, 10, 0.50) # unsupported confidence
