"""Shared fixtures for Sentinel tests."""

from __future__ import annotations

import time

import pytest

from sentinel.protocol.link import LinkSpec

BASE_BOB = [{"type": "depolarizing", "p": 0.012}, {"type": "amplitude_damping", "gamma": 0.004}]
BASE_CHARLIE = [{"type": "depolarizing", "p": 0.016}, {"type": "amplitude_damping", "gamma": 0.006}]


@pytest.fixture
def links():
    return {
        "bob": LinkSpec("alice-bob", "alice", "bob", list(BASE_BOB), 22.0),
        "charlie": LinkSpec("alice-charlie", "alice", "charlie", list(BASE_CHARLIE), 35.0),
    }


@pytest.fixture
def now():
    return time.time()
