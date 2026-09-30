"""
evaluation/performance.py
=========================
Phase 7 -- Performance measurement primitives.
"""
import time
from dataclasses import dataclass
from typing import List, Dict, Callable, Any, Optional
import numpy as np

__all__ = ["PerformanceMetrics", "LatencyTracker", "profile_function"]

@dataclass
class PerformanceMetrics:
    operation: str
    trials: int
    mean_latency: float
    median_latency: float
    std_latency: float
    min_latency: float
    max_latency: float
    
    def as_dict(self) -> dict:
        return {
            "operation": self.operation,
            "trials": self.trials,
            "mean_latency": self.mean_latency,
            "median_latency": self.median_latency,
            "std_latency": self.std_latency,
            "min_latency": self.min_latency,
            "max_latency": self.max_latency
        }

class LatencyTracker:
    """Tracks latencies for various operations."""
    def __init__(self):
        self.records: Dict[str, List[float]] = {}
        self._start_times: Dict[str, float] = {}
        
    def start(self, op: str) -> None:
        self._start_times[op] = time.perf_counter()
        
    def stop(self, op: str) -> None:
        end = time.perf_counter()
        if op in self._start_times:
            elapsed = max(0.0, end - self._start_times[op])
            if op not in self.records:
                self.records[op] = []
            self.records[op].append(elapsed)
            
    def get_metrics(self, op: str) -> Optional[PerformanceMetrics]:
        if op not in self.records or not self.records[op]:
            return None
            
        latencies = self.records[op]
        return PerformanceMetrics(
            operation=op,
            trials=len(latencies),
            mean_latency=float(np.mean(latencies)),
            median_latency=float(np.median(latencies)),
            std_latency=float(np.std(latencies)),
            min_latency=float(np.min(latencies)),
            max_latency=float(np.max(latencies))
        )
        
    def get_all_metrics(self) -> List[PerformanceMetrics]:
        return [self.get_metrics(op) for op in sorted(self.records.keys()) if self.get_metrics(op) is not None]

def profile_function(tracker: LatencyTracker, op_name: str):
    """Decorator to profile a function and record explicitly to a tracker."""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            tracker.start(op_name)
            result = func(*args, **kwargs)
            tracker.stop(op_name)
            return result
        return wrapper
    return decorator
