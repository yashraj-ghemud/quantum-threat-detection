"""
security/calibration.py
=======================
Phase 6.5 -- THREAT DETECTOR HARDENING.

Multi-session baseline estimation and threshold calibration.
"""
from dataclasses import dataclass
from typing import List, Sequence, Tuple
import numpy as np

from security.fingerprint import SessionFingerprint
from utils.logger import get_logger

logger = get_logger(__name__)

__all__ = ["BaselineStats", "calculate_baseline_stats", "cross_validate_split"]

@dataclass
class BaselineStats:
    session_count: int
    mean_match_rate: float
    mean_mismatch_rate: float
    mismatch_variance: float
    mismatch_std: float

def calculate_baseline_stats(sessions: Sequence[SessionFingerprint]) -> BaselineStats:
    """Calculate statistical properties of multiple baseline sessions."""
    mm_rates = [s.mismatch_rate for s in sessions]
    m_rates = [s.match_rate for s in sessions]
    
    if not mm_rates:
        return BaselineStats(0, 0.0, 0.0, 0.0, 0.0)
        
    return BaselineStats(
        session_count=len(sessions),
        mean_match_rate=float(np.mean(m_rates)),
        mean_mismatch_rate=float(np.mean(mm_rates)),
        mismatch_variance=float(np.var(mm_rates)),
        mismatch_std=float(np.std(mm_rates))
    )

def cross_validate_split(
    sessions: Sequence[SessionFingerprint], 
    train_ratio: float = 0.5
) -> Tuple[List[SessionFingerprint], List[SessionFingerprint]]:
    """Split legitimate sequences into calibration (train) and validation sets."""
    n = len(sessions)
    if n < 4:
        logger.warning(f"insufficient data for reliable holdout calibration (n={n})")
        return list(sessions), []
        
    n_train = max(2, int(n * train_ratio))
    return list(sessions[:n_train]), list(sessions[n_train:])
