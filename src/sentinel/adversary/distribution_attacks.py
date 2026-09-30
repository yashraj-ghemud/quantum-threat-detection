"""
sentinel/adversary/distribution_attacks.py
==========================================
Translate a distribution-phase :class:`AttackSpec` into per-link physics
(:class:`LinkPlan`). Nothing here sees evidence, findings or decisions.
"""

from __future__ import annotations

import math

from sentinel.adversary.catalog import AttackSpec, validate_spec
from sentinel.protocol.link import LinkPlan

__all__ = ["plans_for", "DISTRIBUTION_ATTACKS"]

DISTRIBUTION_ATTACKS = {
    "channel.depolarize", "channel.dephase", "channel.amplitude_damp", "channel.coherent_rotation",
    "channel.intercept_resend", "channel.pauli_frame", "unauthorized.key_harvest_mitm",
    "repudiation.inconsistent_keys",
}

_AXIS = {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]}


def _plan(spec: AttackSpec) -> LinkPlan:
    I = spec.intensity
    a = spec.attack_id
    p = spec.params
    if a == "channel.depolarize":
        return LinkPlan(extra_channel=[{"type": "depolarizing", "p": 0.5 * I}])
    if a == "channel.dephase":
        return LinkPlan(extra_channel=[{"type": "dephasing", "p": 0.5 * I, "axis": p.get("axis", "z")}])
    if a == "channel.amplitude_damp":
        return LinkPlan(extra_channel=[{"type": "amplitude_damping", "gamma": 0.6 * I}])
    if a == "channel.coherent_rotation":
        return LinkPlan(extra_channel=[{"type": "rotation", "axis": _AXIS[p.get("axis", "z")], "theta": (math.pi / 2) * I}])
    if a == "channel.intercept_resend":
        return LinkPlan(substitute_fraction=I, substitute_mode="intercept_resend", intercept_basis=p.get("basis", "random"))
    if a == "channel.pauli_frame":
        q = 0.5 * I
        bits = p.get("bits", "m1")
        return LinkPlan(flip_c0=q if bits in ("m0", "both") else 0.0, flip_c1=q if bits in ("m1", "both") else 0.0)
    if a == "unauthorized.key_harvest_mitm":
        return LinkPlan(substitute_fraction=I, substitute_mode="mitm", intercept_basis="random")
    if a == "repudiation.inconsistent_keys":
        return LinkPlan(source_flip_fraction=0.5 * I)
    raise ValueError(f"{a} is not a distribution attack")


def plans_for(spec: AttackSpec, recipients: tuple) -> dict:
    """Map a spec to {verifier_id: LinkPlan} for the targeted recipient(s)."""
    spec = validate_spec(spec)
    plan = _plan(spec)
    if spec.attack_id == "repudiation.inconsistent_keys":
        target = spec.params.get("victim", "second")
    else:
        target = spec.target
    if target == "first":
        return {recipients[0]: plan}
    if target == "second":
        return {recipients[1]: plan}
    return {recipients[0]: plan, recipients[1]: _plan(spec)}
