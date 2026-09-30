"""
tests/evaluation/test_complexity.py
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import pytest
from evaluation.complexity import get_theoretical_complexity

def test_complexity():
    complexities = get_theoretical_complexity()
    assert len(complexities) > 0
    assert "Signature Generation" in complexities
    
    ca = complexities["Signature Generation"]
    assert ca.time_complexity == "O(n)"
    d = ca.to_dict()
    assert d["component"] == ca.component
