"""
sentinel/adversary/catalog.py
=============================
The attack catalog: 17 variants across the problem statement's threat classes.

Each entry is data (served verbatim by ``GET /api/v1/attacks/catalog``): id,
category, phase, physics, adversary knowledge, parameter schema, intensity
mapping and the detection layers expected to fire.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

__all__ = ["AttackSpec", "CATALOG", "catalog_entry", "validate_spec", "CATEGORIES", "AttackSpecError"]


class AttackSpecError(ValueError):
    pass


@dataclass
class AttackSpec:
    attack_id: str
    intensity: float = 0.5
    params: dict = field(default_factory=dict)
    target: str = "first"          # first | second | both (distribution attacks)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AttackSpec":
        return cls(attack_id=d["attack_id"], intensity=float(d.get("intensity", 0.5)),
                   params=dict(d.get("params") or {}), target=d.get("target", "first"))


CATEGORIES = {
    "FORGERY": "Forgery",
    "IMPERSONATION": "Impersonation",
    "REPLAY": "Replay",
    "UNAUTHORIZED_VERIFICATION": "Unauthorized verification",
    "CHANNEL_MANIPULATION": "Quantum channel manipulation",
    "REPUDIATION": "Repudiation",
}

_TARGET = {"name": "target", "type": "enum", "options": ["first", "second", "both"], "default": "first",
           "description": "Which recipient's link the adversary works on."}
_MODE = {"name": "mode", "type": "enum", "options": ["modified_message", "oracle_k_bits"], "default": "modified_message",
         "description": "Change the message text (≈ half the digest bits differ), or assume a hash near-collision oracle."}


def _e(**kw) -> dict:
    kw.setdefault("params", [])
    kw.setdefault("intensity", None)
    return kw


CATALOG: list[dict[str, Any]] = [
    # ------------------------------------------------------------------ channel manipulation
    _e(id="channel.depolarize", category="CHANNEL_MANIPULATION", subtype="isotropic", phase="distribution",
       name="Depolarizing tamper", icon="waves",
       summary="Eve scrambles the receiver's Bell half with isotropic noise.",
       physics="Adds ρ → (1−p)ρ + p I/2 on the verifier's half. The Bloch sphere shrinks uniformly; CHSH falls as 2√2(1−p).",
       knowledge=["Physical access to the quantum fibre"],
       intensity={"param": "p", "scale": 0.5, "formula": "p = 0.5 · I"},
       params=[_TARGET], detection=["D2", "D3b", "D4", "D5 (isotropic)", "D10 at low intensity"]),
    _e(id="channel.dephase", category="CHANNEL_MANIPULATION", subtype="dephasing", phase="distribution",
       name="Dephasing tamper", icon="minimize-2",
       summary="Eve destroys coherence along one axis.",
       physics="Adds (1−p)ρ + p σρσ. The sphere is squashed onto the chosen axis; only two bases see errors.",
       knowledge=["Physical access to the quantum fibre"],
       intensity={"param": "p", "scale": 0.5, "formula": "p = 0.5 · I"},
       params=[_TARGET, {"name": "axis", "type": "enum", "options": ["x", "y", "z"], "default": "z"}],
       detection=["D4 (two bases)", "D5 (dephasing, axis)"]),
    _e(id="channel.amplitude_damp", category="CHANNEL_MANIPULATION", subtype="amplitude_damping", phase="distribution",
       name="Energy-drain tamper", icon="battery-low",
       summary="A lossy, non-unital channel that pulls states toward |0⟩.",
       physics="Amplitude damping γ: shifts the sphere toward |0⟩. Teleportation's Pauli twirl hides the shift in averaged "
               "statistics; Pauli-frame de-twirling tomography recovers it.",
       knowledge=["Physical access to the quantum fibre"],
       intensity={"param": "gamma", "scale": 0.6, "formula": "γ = 0.6 · I"},
       params=[_TARGET], detection=["D5 de-twirled translation", "D4"]),
    _e(id="channel.coherent_rotation", category="CHANNEL_MANIPULATION", subtype="coherent_rotation", phase="distribution",
       name="Coherent rotation", icon="rotate-cw",
       summary="A stealthy unitary rotation that preserves purity.",
       physics="Applies exp(−iθ n·σ/2). Averaged over teleportation frames it looks like dephasing; de-twirling exposes the "
               "rotation axis and angle.",
       knowledge=["Physical access to the quantum fibre", "A polarization rotator"],
       intensity={"param": "theta", "scale": math.pi / 2, "formula": "θ = (π/2) · I"},
       params=[_TARGET, {"name": "axis", "type": "enum", "options": ["x", "y", "z"], "default": "z"}],
       detection=["D5 de-twirled rotation", "D2", "D4"]),
    _e(id="channel.intercept_resend", category="CHANNEL_MANIPULATION", subtype="intercept_resend", phase="distribution",
       name="Intercept–resend", icon="scan-eye",
       summary="Eve measures a fraction of the receiver's Bell halves and resends what she saw.",
       physics="Measuring breaks entanglement: those pairs become classically correlated. CHSH falls toward the local bound; "
               "the channel becomes dephasing (fixed basis) or depolarizing (random basis).",
       knowledge=["Physical access to the quantum fibre", "A single-photon detector and source"],
       intensity={"param": "fraction", "scale": 1.0, "formula": "f = I"},
       params=[_TARGET, {"name": "basis", "type": "enum", "options": ["random", "x", "y", "z"], "default": "random"}],
       detection=["D1/D3a when f is large", "D2", "D4", "D5"]),
    _e(id="channel.pauli_frame", category="CHANNEL_MANIPULATION", subtype="classical_frame", phase="distribution",
       name="Pauli-frame tampering", icon="binary",
       summary="Eve flips the teleportation correction bits on the classical channel.",
       physics="The verifier applies the wrong Pauli correction. The quantum channel is untouched, so only the classical "
               "frame comparison (or a Wegman–Carter MAC) reveals it.",
       knowledge=["Write access to the classical channel"],
       intensity={"param": "flip_probability", "scale": 0.5, "formula": "q = 0.5 · I"},
       params=[_TARGET, {"name": "bits", "type": "enum", "options": ["m0", "m1", "both"], "default": "m1"}],
       detection=["D6 (conclusive)", "D4 on the effective map"]),
    # ------------------------------------------------------------------ unauthorized verification
    _e(id="unauthorized.key_harvest_mitm", category="UNAUTHORIZED_VERIFICATION", subtype="key_harvest", phase="distribution",
       name="MITM key harvesting", icon="spy",
       summary="Eve relays teleportation through her own lab to read the public-key states.",
       physics="Eve substitutes the verifier's Bell halves with her own pairs, receives each key state, measures it, and "
               "re-teleports her result. She gains verification ability she was never granted, at the cost of entanglement "
               "(CHSH), frame consistency (her Bell outcomes differ from the signer's) and a QBER deficit against the Bell test.",
       knowledge=["Control of the quantum fibre", "Read/write on the classical channel", "Quantum memory for one qubit"],
       intensity={"param": "fraction", "scale": 1.0, "formula": "f = I"},
       params=[_TARGET], detection=["D6", "D1/D2", "D7 deficit"],
       counterfactual="If the bundle were used anyway, Eve forges a message to the harvested recipient."),
    _e(id="unauthorized.non_recipient", category="UNAUTHORIZED_VERIFICATION", subtype="non_recipient", phase="signing",
       name="Non-recipient verification", icon="user-x",
       summary="A party outside the bundle's recipient set tries to verify a signature.",
       physics="The public key is quantum: only the recipients hold measurement records. Anyone else has nothing to verify "
               "against, and the protocol refuses them.",
       knowledge=["A captured signature"],
       params=[{"name": "verifier", "type": "enum", "options": ["erin", "eve"], "default": "erin"}],
       detection=["S1 (conclusive)"]),
    # ------------------------------------------------------------------ forgery
    _e(id="forgery.blind", category="FORGERY", subtype="external_blind", phase="signing",
       name="Blind forgery", icon="pen-off",
       summary="Eve intercepts a signature in transit and alters the message.",
       physics="Bits that change need labels of keys that were never revealed. Guessing gives mismatch ½ on tested positions.",
       knowledge=["The intercepted genuine signature", "All public parameters"],
       params=[_MODE, {"name": "k", "type": "int", "min": 1, "max": 64, "default": 1,
                       "description": "Differing bits for oracle mode"}],
       detection=["S7", "S8", "S9 (external blind)"]),
    _e(id="forgery.insider", category="FORGERY", subtype="insider", phase="signing",
       name="Insider forgery", icon="user-cog",
       summary="The first recipient forges a message and forwards it to the second.",
       physics="The insider declares its own measurement records as labels (optimal single-copy strategy, mismatch ⅓) and "
               "knows the records its peer forwarded. Testing the two halves separately catches it, and the pattern points at it.",
       knowledge=["Its own measurement records", "The peer's forwarded records", "The genuine signature"],
       params=[_MODE, {"name": "k", "type": "int", "min": 1, "max": 64, "default": 1}],
       detection=["S7", "S9 (insider attribution)"],
       counterfactual="Pooling the two halves into one test lets the insider's forgery pass."),
    _e(id="forgery.bit_flip_oracle", category="FORGERY", subtype="oracle_k_bits", phase="signing",
       name="Near-collision oracle", icon="target",
       summary="A hypothetical attacker who can find a message whose digest differs in only k bits.",
       physics="Measures the per-key forgery bound directly: only k unseen keys must be guessed.",
       knowledge=["A (hypothetical) SHA-256 near-collision oracle", "The genuine signature"],
       params=[{"name": "k", "type": "int", "min": 1, "max": 64, "default": 1}],
       detection=["S7 on the k keys"]),
    # ------------------------------------------------------------------ impersonation
    _e(id="impersonation.identity_swap", category="IMPERSONATION", subtype="identity_swap", phase="signing",
       name="Identity swap", icon="venetian-mask",
       summary="Mallory signs with her own valid keys but claims to be Alice.",
       physics="Her signature verifies against her own bundle. The protocol binds bundles to signers, so the claim fails.",
       knowledge=["Mallory's own legitimately distributed bundle"],
       detection=["S2 (conclusive)"], counterfactual="Without key binding the quantum tests accept her signature."),
    _e(id="impersonation.keyless", category="IMPERSONATION", subtype="keyless", phase="signing",
       name="Keyless impersonation", icon="key-round",
       summary="Mallory claims one of Alice's bundles with no key material at all.",
       physics="Every key must be guessed; nearly every key fails at mismatch ½.",
       knowledge=["The public id of one of Alice's bundles"], detection=["S7", "S9 (keyless)"]),
    # ------------------------------------------------------------------ replay
    _e(id="replay.resubmit", category="REPLAY", subtype="resubmission", phase="signing",
       name="Resubmission replay", icon="repeat",
       summary="A captured, accepted signature is sent again.",
       physics="The replayed states are genuine, so physics cannot see it. One-time bundles, nonces and sequence numbers can.",
       knowledge=["A captured accepted signature"], detection=["S3", "S4", "S5"],
       counterfactual="Quantum tests alone accept the replay."),
    _e(id="replay.forward_replay", category="REPLAY", subtype="forward_replay", phase="signing",
       name="Forward replay", icon="forward",
       summary="A forwarded signature is presented to the second recipient as a fresh delivery.",
       physics="The second recipient already consumed the bundle while checking the transfer.",
       knowledge=["A captured forwarded signature"], detection=["S3", "S4"]),
    _e(id="replay.delayed", category="REPLAY", subtype="delay", phase="signing",
       name="Delay attack", icon="timer",
       summary="Eve holds a signature and delivers it late.",
       physics="The timestamp is signed, so it cannot be refreshed; it falls outside the freshness window.",
       knowledge=["An intercepted signature"],
       params=[{"name": "delay_s", "type": "float", "min": 1, "max": 3600, "default": 300, "unit": "s"}],
       detection=["S6"]),
    # ------------------------------------------------------------------ repudiation
    _e(id="repudiation.inconsistent_keys", category="REPUDIATION", subtype="inconsistent_keys", phase="distribution",
       name="Inconsistent key distribution", icon="split",
       summary="A dishonest Alice sends one recipient corrupted states so she can later disown her signature.",
       physics="She teleports the orthogonal state on a fraction of one copy while claiming the original labels. "
               "Symmetrization mixes the copies so both recipients decide alike; the Bell-vs-key test exposes her.",
       knowledge=["She is the signer"],
       intensity={"param": "fraction", "scale": 0.5, "formula": "r = 0.5 · I"},
       params=[{"name": "victim", "type": "enum", "options": ["first", "second"], "default": "second"}],
       detection=["D7 excess", "D8"],
       counterfactual="Without symmetrization the recipients disagree: the dispute she wanted."),
]

_BY_ID = {e["id"]: e for e in CATALOG}


def catalog_entry(attack_id: str) -> dict:
    try:
        return _BY_ID[attack_id]
    except KeyError:
        raise AttackSpecError(f"unknown attack {attack_id!r}") from None


def validate_spec(spec: AttackSpec) -> AttackSpec:
    entry = catalog_entry(spec.attack_id)
    if not (0.0 <= spec.intensity <= 1.0) or math.isnan(spec.intensity):
        raise AttackSpecError("intensity must be in [0, 1]")
    params = dict(spec.params)
    for p in entry["params"]:
        name = p["name"]
        if name == "target":
            continue
        val = params.get(name, p.get("default"))
        if p["type"] == "enum" and val not in p["options"]:
            raise AttackSpecError(f"{name} must be one of {p['options']}")
        if p["type"] in ("int", "float"):
            try:
                val = int(val) if p["type"] == "int" else float(val)
            except (TypeError, ValueError):
                raise AttackSpecError(f"{name} must be a number") from None
            if val < p.get("min", -math.inf) or val > p.get("max", math.inf):
                raise AttackSpecError(f"{name} must be in [{p.get('min')}, {p.get('max')}]")
        params[name] = val
    target = spec.params.get("target", spec.target)
    if target not in ("first", "second", "both"):
        raise AttackSpecError("target must be first, second or both")
    return AttackSpec(spec.attack_id, float(spec.intensity), params, target)
