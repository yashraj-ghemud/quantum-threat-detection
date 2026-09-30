"""Sentinel teleportation superoperators agree with Qiskit Aer to machine precision."""

from __future__ import annotations

import pytest

from sentinel.analysis.validation import DEFAULT_CHANNELS, aer_available, validate_all, validate_channel

pytestmark = pytest.mark.skipif(not aer_available(), reason="qiskit-aer not installed")


@pytest.mark.parametrize("specs", DEFAULT_CHANNELS, ids=lambda s: "+".join(x["type"] for x in s) or "identity")
def test_conditional_states_match_aer(specs):
    res = validate_channel(specs)
    assert res["missing_outcomes"] == 0
    assert res["max_dev"] < 1e-9, res


def test_validate_all_reports():
    res = validate_all(DEFAULT_CHANNELS[:2])
    assert res["status"] == "done" and res["pass"] is True
    assert res["aer_version"]
