"""
sentinel/detection/findings.py
==============================
Data model for detector output.

A :class:`Finding` is one named test with its evidence. An
:class:`Assessment` is the fused decision for a distribution or a signature,
with the decision-list rule that fired and the alternatives the evidence
cannot exclude.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

__all__ = [
    "SEVERITIES",
    "SEVERITY_RANK",
    "SEVERITY_WEIGHT",
    "Finding",
    "Classification",
    "Assessment",
    "max_severity",
    "threat_score",
]

SEVERITIES = ("NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}
SEVERITY_WEIGHT = {"NONE": 0.0, "LOW": 0.15, "MEDIUM": 0.35, "HIGH": 0.7, "CRITICAL": 1.0}


def _clean(v: Any) -> Any:
    """JSON-safe conversion (numpy scalars, NaN/inf)."""
    try:
        import numpy as np

        if isinstance(v, np.generic):
            v = v.item()
        elif isinstance(v, np.ndarray):
            return [_clean(x) for x in v.tolist()]
    except Exception:  # pragma: no cover
        pass
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


@dataclass
class Finding:
    """The result of one detector."""

    id: str
    name: str
    layer: str                    # entanglement|channel|classical|source|security|temporal|protocol|signature
    fired: bool
    severity: str = "NONE"        # severity if fired (NONE when not fired)
    conclusive: bool = False
    statistic: Optional[dict] = None   # {"name": str, "value": float}
    p_value: Optional[float] = None
    alpha: Optional[float] = None
    effect: Optional[dict] = None      # {"name": str, "value": float, "floor": float}
    evidence: str = ""
    link_id: Optional[str] = None
    data: dict = field(default_factory=dict)
    candidate: bool = False            # statistically significant before the effect floor / Holm

    def as_dict(self) -> dict:
        d = asdict(self)
        d["log10_p"] = math.log10(max(self.p_value, 1e-300)) if self.p_value is not None else None
        return _clean(d)

    @property
    def rank(self) -> int:
        return SEVERITY_RANK.get(self.severity, 0) if self.fired else 0


@dataclass
class Classification:
    category: str = "NONE"
    subtype: Optional[str] = None
    confidence: str = "none"        # conclusive | statistical | temporal | design | indicative | none
    rule: str = ""
    explanation: str = ""
    alternatives: list = field(default_factory=list)
    attributed_to: Optional[str] = None

    def as_dict(self) -> dict:
        return _clean(asdict(self))


@dataclass
class Assessment:
    verdict: str                    # CERTIFIED | COMPROMISED | ACCEPTED | REJECTED
    threat_level: str
    threat_score: float
    classification: Classification
    findings: list
    recommended_actions: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "threat_level": self.threat_level,
            "threat_score": float(self.threat_score),
            "classification": self.classification.as_dict(),
            "findings": [f.as_dict() for f in self.findings],
            "recommended_actions": list(self.recommended_actions),
        }

    def fired(self) -> list:
        return [f for f in self.findings if f.fired]


def max_severity(findings) -> str:
    best = "NONE"
    for f in findings:
        if f.fired and SEVERITY_RANK[f.severity] > SEVERITY_RANK[best]:
            best = f.severity
    return best


def threat_score(findings) -> float:
    """UI-only aggregate: 1 - prod(1 - w_sev * E_d). Decisions never use it."""
    prod = 1.0
    for f in findings:
        if not f.fired:
            continue
        if f.conclusive or f.p_value is None or f.alpha is None:
            strength = 1.0
        else:
            strength = min(1.0, math.log10(1.0 / max(f.p_value, 1e-300)) / max(math.log10(1.0 / f.alpha), 1e-9))
        prod *= 1.0 - SEVERITY_WEIGHT.get(f.severity, 0.0) * max(0.0, strength)
    return float(1.0 - prod)
