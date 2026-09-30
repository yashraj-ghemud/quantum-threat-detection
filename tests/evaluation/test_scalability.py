"""
tests/evaluation/test_scalability.py
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import pytest
from evaluation.scalability import measure_signature_scalability, measure_session_scalability

def test_signature_scalability():
    # Use small lengths and reps for quick test
    df = measure_signature_scalability(lengths=[4, 8], repetitions=2, seed=42)
    
    assert not df.empty
    assert len(df) == 2
    assert "signature_length" in df.columns
    assert "mean_gen_time" in df.columns
    assert "mean_end_to_end_time" in df.columns
    
    assert not df.isnull().values.any()
    assert (df["mean_end_to_end_time"] >= 0).all()

def test_session_scalability():
    df = measure_session_scalability(session_counts=[1, 2], sig_length=8, seed=42)
    assert not df.empty
    assert len(df) == 2
    assert "session_count" in df.columns
    assert "throughput_sessions_per_sec" in df.columns
    assert not df.isnull().values.any()
    assert (df["total_execution_time"] > 0).all()
