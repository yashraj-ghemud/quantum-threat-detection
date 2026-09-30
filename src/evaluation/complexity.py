"""
evaluation/complexity.py
========================
Phase 7 -- Theoretical complexity analysis for QDS Threat Detection components.

No AI/ML libraries used.
"""

from typing import Dict, Any

__all__ = ["get_theoretical_complexity", "ComplexityAnalysis"]

class ComplexityAnalysis:
    """Stores the theoretical complexity bound for a specific component."""
    def __init__(self, component: str, time_complexity: str, memory_complexity: str, notes: str):
        self.component = component
        self.time_complexity = time_complexity
        self.memory_complexity = memory_complexity
        self.notes = notes
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "component": self.component,
            "time_complexity": self.time_complexity,
            "memory_complexity": self.memory_complexity,
            "notes": self.notes
        }

def get_theoretical_complexity() -> Dict[str, ComplexityAnalysis]:
    """Returns theoretical asymptotic complexity bounds.
    
    Notation:
    n = signature length (number of elements)
    m = number of baseline sessions for calibration
    b = number of measurement bases (typically 3: X, Y, Z)
    s = statevector size (2^k for k qubits, here roughly fixed as k=1 or 2)
    """
    return {
        "Signature Generation": ComplexityAnalysis(
            component="qds.signature.generate_signature",
            time_complexity="O(n)",
            memory_complexity="O(n)",
            notes="Linear in signature length n. Processes teleportation sequentially."
        ),
        "Measurement Statistics": ComplexityAnalysis(
            component="security.statistics.stats_from_verification",
            time_complexity="O(n)",
            memory_complexity="O(b)",
            notes="Requires 1 pass through n measurement outputs, grouping by b discrete bases."
        ),
        "Fingerprint Generation": ComplexityAnalysis(
            component="security.fingerprint.build_fingerprint",
            time_complexity="O(n)",
            memory_complexity="O(b)",
            notes="Computes mean/var aggregations from measurement stats."
        ),
        "Threshold Calibration": ComplexityAnalysis(
            component="security.thresholds.percentile_calibrate",
            time_complexity="O(m log m)",
            memory_complexity="O(m)",
            notes="Requires sorting m empirical baseline anomaly scores."
        ),
        "Anomaly Assessment": ComplexityAnalysis(
            component="security.anomaly.compute_anomaly_breakdown",
            time_complexity="O(b)",
            memory_complexity="O(b)",
            notes="Compares session fingerprint against baseline (fixed feature vector of size ~8)."
        ),
        "Replay Attack": ComplexityAnalysis(
            component="attacks.replay.ReplayAttack",
            time_complexity="O(1)",
            memory_complexity="O(1)",
            notes="Metadata validation is independent of n."
        ),
        "Teleportation Circuit": ComplexityAnalysis(
            component="quantum.teleportation.build_teleportation_circuit",
            time_complexity="O(1)",
            memory_complexity="O(1)",
            notes="Circuit scaling is fixed for 1 ebit protocol. No quantum-computational advantage is claimed, as this implements a standard primitive."
        )
    }
