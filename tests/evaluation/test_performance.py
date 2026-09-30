"""
tests/evaluation/test_performance.py
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import pytest
import time
from evaluation.performance import LatencyTracker, profile_function

def test_performance_tracking():
    tracker = LatencyTracker()
    
    @profile_function(tracker, "dummy_op")
    def dummy():
        time.sleep(0.01)
        
    dummy()
    dummy()
    
    metrics = tracker.get_metrics("dummy_op")
    assert metrics is not None
    assert metrics.trials == 2
    assert metrics.mean_latency > 0
    assert metrics.max_latency >= metrics.min_latency
    
    all_m = tracker.get_all_metrics()
    assert len(all_m) == 1
    
    # Missing op
    assert tracker.get_metrics("non_existent") is None
