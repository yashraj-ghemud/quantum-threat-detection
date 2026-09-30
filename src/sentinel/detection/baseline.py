"""
sentinel/detection/baseline.py
==============================
Per-link baseline, measured during a trusted calibration window.

The detector never reads a link's configured channel. It measures what an
undisturbed link looks like by running the same physics the protocol runs
(parameter-estimation positions and Bell-test pairs) with no adversary, and
stores the raw counts. Every later test compares *counts to counts*, so the
baseline's own sampling error is part of every p-value.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass

import numpy as np

from sentinel.bell import BellEstimate, estimate_bell, sample_bell_test, setting_probs
from sentinel.protocol.link import LinkSpec
from sentinel.rng import RandomSource
from sentinel.teleport import get_model, sample_teleportations
from sentinel.tomography import ChannelEstimate, PECounts, aggregate_pe, detwirl, effective, qber_counts

__all__ = ["LinkBaseline", "calibrate_link", "spec_hash"]


def spec_hash(specs) -> str:
    return hashlib.sha256(json.dumps(specs, sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class LinkBaseline:
    link_id: str
    calibrated_at: float
    samples: int
    spec_hash: str
    pe: PECounts
    bell_counts: np.ndarray
    # derived
    qber: dict
    bell: BellEstimate
    detwirled: ChannelEstimate
    effective: ChannelEstimate

    @classmethod
    def from_counts(cls, link_id: str, pe: PECounts, bell_counts: np.ndarray, calibrated_at: float,
                    samples: int, spec_hash_: str) -> "LinkBaseline":
        return cls(link_id=link_id, calibrated_at=calibrated_at, samples=samples, spec_hash=spec_hash_,
                   pe=pe, bell_counts=np.asarray(bell_counts, dtype=np.int64), qber=qber_counts(pe),
                   bell=estimate_bell(bell_counts), detwirled=detwirl(pe), effective=effective(pe))

    def to_dict(self) -> dict:
        return {"link_id": self.link_id, "calibrated_at": self.calibrated_at, "samples": self.samples,
                "spec_hash": self.spec_hash, "pe": self.pe.to_list(), "bell_counts": self.bell_counts.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> "LinkBaseline":
        return cls.from_counts(d["link_id"], PECounts.from_list(d["pe"]), np.asarray(d["bell_counts"]),
                               d["calibrated_at"], d["samples"], d["spec_hash"])

    def summary(self) -> dict:
        return {
            "link_id": self.link_id, "calibrated_at": self.calibrated_at, "samples": self.samples,
            "qber": self.qber["rate"], "qber_per_basis": {k: v["rate"] for k, v in self.qber["per_basis"].items()},
            "S": self.bell.S, "S_se": self.bell.S_se, "F": self.bell.F,
            "M": self.detwirled.M.tolist(), "c": self.detwirled.c.tolist(),
        }


def calibrate_link(spec: LinkSpec, rs: RandomSource | None = None, pe_samples: int = 400_000,
                   bell_per_setting: int = 20_000) -> LinkBaseline:
    """Measure an undisturbed link."""
    rs = rs or RandomSource()
    model = get_model(list(spec.baseline))
    labels = rs.labels(pe_samples)
    bases = rs.bases(pe_samples)
    k, c, o = sample_teleportations(model, labels, bases, rs.physics)
    pe = aggregate_pe(labels, k, c, bases, o)
    counts = sample_bell_test(setting_probs(model.rho_ab), bell_per_setting, rs.physics)
    return LinkBaseline.from_counts(spec.link_id, pe, counts, time.time(), pe_samples, spec_hash(list(spec.baseline)))
