"""
tests/security/test_calibration.py
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import pytest
import numpy as np
from security.fingerprint import SessionFingerprint

from security.calibration import calculate_baseline_stats, cross_validate_split

def _mock_fingerprint(match_r, mismatch_r):
    return SessionFingerprint(
        session_id="test_sess",
        total=10,
        p_plus=0.5, p_minus=0.5, mean=0.0, variance=1.0,
        match_rate=match_r, mismatch_rate=mismatch_r, avg_p_plus_expected=0.5
    )

def test_calculate_baseline_stats():
    sessions = [
        _mock_fingerprint(0.9, 0.1),
        _mock_fingerprint(1.0, 0.0),
        _mock_fingerprint(0.8, 0.2)
    ]
    stats = calculate_baseline_stats(sessions)
    assert stats.session_count == 3
    assert pytest.approx(stats.mean_match_rate) == 0.9
    assert pytest.approx(stats.mean_mismatch_rate) == 0.1
    assert stats.mismatch_variance > 0
    assert stats.mismatch_std > 0

def test_cross_validate_split():
    sessions = [_mock_fingerprint(1, 0) for _ in range(6)]
    train, val = cross_validate_split(sessions, train_ratio=0.5)
    assert len(train) == 3
    assert len(val) == 3

    # Small size test
    small = [_mock_fingerprint(1, 0) for _ in range(2)]
    train_small, val_small = cross_validate_split(small, train_ratio=0.5)
    assert len(train_small) == 2
    assert len(val_small) == 0
