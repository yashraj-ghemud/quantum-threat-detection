"""
sentinel/adversary/runner.py
============================
Runs catalog attacks end to end through a :class:`~sentinel.world.World`.

Adversary knowledge is obtained only through what the adversary could
observe or legitimately hold:

- a signature **intercepted in transit** (before the recipient sees it),
- a signature **captured** after delivery (public classical channel),
- an insider's **own verifier view** (its records + what its peer forwarded),
- harvested measurement results from a MITM distribution (the adversary's
  own measurements, returned as distribution artifacts),
- the rogue signer's **own** legitimately distributed bundle.

Counterfactuals rerun the real code paths with one defence switched off, on
copies, with a scratch guard store, so real state is never touched.
"""

from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from sentinel.adversary.catalog import AttackSpec, catalog_entry, validate_spec
from sentinel.adversary.distribution_attacks import DISTRIBUTION_ATTACKS, plans_for
from sentinel.protocol.encoding import encode_bits
from sentinel.protocol.guard import MemoryGuardStore
from sentinel.protocol.signing import Signature, sign as _sign
from sentinel.rng import RandomSource
from sentinel.states import label_from

__all__ = ["AttackRun", "run_attack", "tamper_message"]

DEFAULT_MESSAGE = "Pay 250 QVC to Bob"


@dataclass
class AttackRun:
    spec: AttackSpec
    entry: dict
    distribution: object = None          # DistributionRun
    signature: object = None             # SignatureRun (the attack's main verification)
    setup: list = field(default_factory=list)   # SignatureRuns needed to set the attack up (captures)
    counterfactual: Optional[dict] = None
    notes: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def assessment(self):
        if self.entry["phase"] == "distribution":
            return self.distribution.assessment if self.distribution else None
        return self.signature.assessment if self.signature else None

    @property
    def detected(self) -> bool:
        a = self.assessment
        if a is None:
            return False
        if self.entry["phase"] == "distribution":
            return a.classification.category not in ("NONE",) or a.verdict == "COMPROMISED"
        return a.verdict == "REJECTED" or a.classification.category not in ("NONE",)

    @property
    def correctly_classified(self) -> bool:
        a = self.assessment
        return bool(a and a.classification.category == self.entry["category"])

    def report(self) -> dict:
        a = self.assessment
        return {
            "attack": self.spec.as_dict(), "catalog_entry": self.entry, "phase": self.entry["phase"],
            "distribution": self.distribution.report() if self.distribution else None,
            "signature": self.signature.report() if self.signature else None,
            "setup": [s.summary() for s in self.setup],
            "counterfactual": self.counterfactual,
            "detected": self.detected, "correctly_classified": self.correctly_classified,
            "expected_category": self.entry["category"],
            "detected_category": a.classification.category if a else None,
            "detected_subtype": a.classification.subtype if a else None,
            "verdict": a.verdict if a else None, "threat_level": a.threat_level if a else None,
            "notes": self.notes, "created_at": self.created_at,
        }


def tamper_message(msg: str) -> str:
    """The attacker's altered message (redirects funds / changes the order)."""
    m = re.search(r"\d+", msg)
    if m:
        return msg[: m.start()] + "9" + msg[m.start():] + " (to eve)"
    return msg + " — amended by eve"


def _injected(spec: AttackSpec, entry: dict) -> dict:
    return {**spec.as_dict(), "category": entry["category"], "subtype": entry["subtype"]}


def _intercept(world, group_id: str, message: str, now: float):
    """Signer signs; the adversary holds the signature before any recipient sees it."""
    bundle = world.pick_bundle_or_distribute(group_id)
    _, sig, _ = world.sign(group_id, message, "sha256", bundle, now)
    return bundle, sig


def _captured(world, group_id: str, message: str, now: float, run: AttackRun):
    """A delivered, accepted signature seen on the public channel."""
    for c in reversed(world.capture):
        if c.group_id == group_id and c.transferred:
            return c.signature.copy()
    world.pick_bundle_or_distribute(group_id)
    legit = world.sign_and_verify(group_id, message, now=now, origin="LAB")
    run.setup.append(legit)
    run.notes.append("No captured signature was available, so a legitimate session ran first and its signature was captured.")
    return world.capture[-1].signature.copy()


def _forge_labels(genuine: Signature, target_bits: np.ndarray, guess_fn) -> np.ndarray:
    """Reuse revealed labels where bits agree; call guess_fn(i, bit) for keys that were never revealed."""
    out = genuine.revealed.copy()
    for i in np.nonzero(target_bits != genuine.bits)[0]:
        out[i] = guess_fn(int(i), int(target_bits[i]))
    return out


def _counterfactual_signature(world, sig, bundle, meta, description, **kw):
    run = world.deliver(sig.copy(), bundle=copy.deepcopy(bundle), meta=meta, counterfactual=True, commit=False,
                        guard_store=MemoryGuardStore(), **kw)
    return run


def run_attack(world, spec, group_id: str = "g-alice", message: Optional[str] = None,
               counterfactual: bool = True, now: Optional[float] = None, origin: str = "LAB") -> AttackRun:
    if isinstance(spec, dict):
        spec = AttackSpec.from_dict(spec)
    spec = validate_spec(spec)
    entry = catalog_entry(spec.attack_id)
    run = AttackRun(spec=spec, entry=entry)
    now = world.clock() if now is None else now
    message = message or DEFAULT_MESSAGE
    group = world.group(group_id)
    inj = _injected(spec, entry)
    rs = RandomSource() if world._seed is None else world.rs()
    a = spec.attack_id

    # ------------------------------------------------------------------ distribution attacks
    if a in DISTRIBUTION_ATTACKS:
        plans = plans_for(spec, tuple(group.recipients))
        dist = world.distribute(group_id, plans=plans, origin=origin, injected_attack=inj, keep_copy=counterfactual)
        run.distribution = dist
        if counterfactual and dist.bundle_copy is not None:
            b = dist.bundle_copy
            # A system without per-bundle parameter estimation would verify with thresholds
            # designed for the link's calibrated baseline, not for the attacked channel.
            b.design = world.baseline_design(group_id, b.params).as_dict()
            b.status = "ACTIVE"
            meta = {**b.meta(), "status": "ACTIVE"}
            if a == "unauthorized.key_harvest_mitm":
                victim = next(iter(plans))
                harvested = dist.outcome.artifacts.get(victim, {}).get("harvested")
                env = world.make_envelope(group, b.bundle_id, tamper_message(message), "sha256", now, rs)
                bits = encode_bits(env, b.params.digest_bits)
                B, L = b.params.digest_bits, b.params.L
                declared = rs.labels(B * L).reshape(B, L)
                if harvested is not None and len(harvested["kept_positions"]):
                    pos = harvested["kept_positions"]
                    bi, vv, jj = np.unravel_index(pos, (B, 2, L))
                    sel = vv == bits[bi]
                    lab = (2 * harvested["basis"] + harvested["outcome"]).astype(np.uint8)
                    declared[bi[sel], jj[sel]] = lab[sel]
                sig = Signature(env, bits, declared)
                role = "first" if victim == group.recipients[0] else "transfer"
                cf = _counterfactual_signature(world, sig, b, meta, "", to=victim, role=role, forward=False, now=now)
                acc = cf.primary is not None and cf.primary.decision == "ACCEPT"
                p = cf.primary
                own = float(p.m_own.sum() / max(p.n_own.sum(), 1)) if p else 0.0
                recv = float(p.m_recv.sum() / max(p.n_recv.sum(), 1)) if p else 0.0
                both = len(plans) == 2
                if acc:
                    sentence = (f"{victim} would ACCEPT Eve's forged message: mismatch {100 * own:.2f}% on its own records "
                                f"and {100 * recv:.2f}% on the records its peer forwarded, both under the "
                                f"{100 * p.threshold:.2f}% threshold. Only the Sentinel's abort stops this.")
                elif not both:
                    sentence = (f"Even without the Sentinel, {victim} rejects Eve's forgery: its own records match her "
                                f"labels ({100 * own:.2f}% mismatch) but the records forwarded by its peer, whose copy she "
                                f"never touched, show {100 * recv:.2f}%. Symmetrization alone defeats single-link harvesting; "
                                f"she would need both links.")
                else:
                    sentence = (f"{victim} rejects Eve's forgery at this intensity: mismatch {100 * own:.2f}% (own) / "
                                f"{100 * recv:.2f}% (forwarded) against {100 * p.threshold:.2f}%. She harvested too few states.")
                run.counterfactual = {
                    "description": "If the harvested bundle had been used, Eve forges a message to the recipient whose key states she read.",
                    "signature": cf.report(), "outcome_sentence": sentence, "breach": acc,
                }
            elif a == "repudiation.inconsistent_keys":
                b2 = copy.deepcopy(b)
                env = world.make_envelope(group, b2.bundle_id, message, "sha256", now, rs)
                sig = _sign(b2, env)
                with_sym = _counterfactual_signature(world, sig, b, meta, "", now=now)
                without = _counterfactual_signature(world, sig, b, meta, "", now=now, mode_first="own_only",
                                                    mode_transfer="own_only")
                d1 = (without.primary.decision if without.primary else "REJECT",
                      without.transfer.decision if without.transfer else "SKIPPED")
                d2 = (with_sym.primary.decision if with_sym.primary else "REJECT",
                      with_sym.transfer.decision if with_sym.transfer else "SKIPPED")
                dispute = d1[0] == "ACCEPT" and d1[1] == "REJECT"
                run.counterfactual = {
                    "description": "Alice signs honestly with the inconsistent bundle and later disowns the signature. "
                                   "Compare verification with and without symmetrization.",
                    "signature": without.report(), "with_symmetrization": with_sym.report(),
                    "outcome_sentence": (f"Without symmetrization: {group.recipients[0]} {d1[0]}, {group.recipients[1]} {d1[1]}"
                                         + (" — the dispute Alice wanted." if dispute else ".")
                                         + f" With symmetrization: {group.recipients[0]} {d2[0]}, {group.recipients[1]} {d2[1]}."),
                    "breach": dispute,
                }
            else:
                b2 = copy.deepcopy(b)
                env = world.make_envelope(group, b2.bundle_id, message, "sha256", now, rs)
                sig = _sign(b2, env)
                cf = _counterfactual_signature(world, sig, b, meta, "", now=now)
                first = cf.primary.decision if cf.primary else "REJECT"
                nfail = len(cf.primary.failed_keys) if cf.primary else 0
                run.counterfactual = {
                    "description": "Alice signs an honest message with the tampered bundle anyway, verified with the "
                                   "thresholds designed for the link's calibrated baseline.",
                    "signature": cf.report(),
                    "outcome_sentence": (f"The honest signature would be {'ACCEPTED' if first == 'ACCEPT' else 'REJECTED'} by "
                                         f"{group.recipients[0]}: overall mismatch "
                                         f"{100 * cf.primary.mismatches / max(cf.primary.tested, 1):.2f}% against a per-key "
                                         f"threshold of {100 * cf.primary.threshold:.2f}%, with {nfail} of "
                                         f"{cf.primary.passed.size} keys failing"
                                         + (" — a denial of service against Alice." if first != "ACCEPT"
                                            else ", at a reduced margin on a channel an attacker controls.")),
                    "breach": first != "ACCEPT",
                }
        return run

    # ------------------------------------------------------------------ signing attacks
    if a in ("forgery.blind", "forgery.bit_flip_oracle"):
        bundle, genuine = _intercept(world, group_id, message, now)
        oracle = a == "forgery.bit_flip_oracle" or spec.params.get("mode") == "oracle_k_bits"
        if oracle:
            k = int(spec.params.get("k", 1))
            env = genuine.envelope.with_(message=tamper_message(message))
            flip = np.zeros_like(genuine.bits)
            idx = rs.choose_mask(genuine.bits.size, k)
            flip[idx] = 1
            bits = genuine.bits ^ flip
            run.notes.append(f"Oracle mode: the attacker is assumed to hold a message whose digest differs in exactly {k} bit(s).")
        else:
            env = genuine.envelope.with_(message=tamper_message(message))
            bits = encode_bits(env, genuine.bits.size)
        L = genuine.revealed.shape[1]
        declared = _forge_labels(genuine, bits, lambda i, b: rs.labels(L))
        forged = Signature(env, bits, declared, oracle=oracle)
        run.signature = world.deliver(forged, now=now, origin=origin, injected_attack=inj)
        run.notes.append(f"{int((bits != genuine.bits).sum())} of {bits.size} digest bits differ from the genuine message.")
        return run

    if a == "forgery.insider":
        bundle = world.pick_bundle_or_distribute(group_id)
        v1, v2 = group.recipients
        _, genuine, _ = world.sign(group_id, message, "sha256", bundle, now)
        first = world.deliver(genuine.copy(), to=v1, forward=False, now=now, origin=origin)
        run.setup.append(first)
        view = bundle.view_for(v1)  # the insider's legitimate knowledge
        oracle = spec.params.get("mode") == "oracle_k_bits"
        env = genuine.envelope.with_(message=tamper_message(message))
        if oracle:
            k = int(spec.params.get("k", 1))
            flip = np.zeros_like(genuine.bits)
            flip[rs.choose_mask(genuine.bits.size, k)] = 1
            bits = genuine.bits ^ flip
        else:
            bits = encode_bits(env, genuine.bits.size)

        def insider_guess(i: int, b: int) -> np.ndarray:
            return (2 * view.own_basis[i, b] + view.own_outcome[i, b]).astype(np.uint8)

        forged = Signature(env, bits, _forge_labels(genuine, bits, insider_guess), oracle=oracle)
        run.signature = world.deliver(forged, to=v2, role="transfer", forward=False, now=now, origin=origin,
                                      injected_attack=inj, stage="transfer")
        run.notes.append(f"{v1} verified the genuine signature, then forwarded a forgery to {v2} as a transfer.")
        if counterfactual:
            b = world.bundles.get(bundle.bundle_id) or bundle
            meta = {**(world.bundles.meta(bundle.bundle_id) or bundle.meta())}
            cf = _counterfactual_signature(world, forged, b, meta, "", to=v2, role="transfer", forward=False, now=now,
                                           mode_first="pooled", use_guard=False, stage="transfer")
            acc = cf.primary is not None and cf.primary.decision == "ACCEPT"
            run.counterfactual = {
                "description": "The same forgery checked with the two halves pooled into one test.",
                "signature": cf.report(),
                "outcome_sentence": (f"Pooled, the insider's forgery would be ACCEPTED by {v2}: its half matches the "
                                     f"records it forwarded, diluting the mismatch." if acc else
                                     f"Pooled, the forgery would still be rejected here; separate sets give the attribution."),
                "breach": acc,
            }
        return run

    if a == "impersonation.identity_swap":
        mg = next((g for g in world.groups.values() if g.signer_id == "mallory"), None)
        if mg is None:
            raise KeyError("identity swap needs a rogue signer group for 'mallory'")
        mb = world.pick_bundle_or_distribute(mg.group_id)
        env = world.make_envelope(mg, mb.bundle_id, message, "sha256", now, rs)
        env = env.with_(signer_id=group.signer_id, group_id=group.group_id, recipients=list(group.recipients))
        sig = _sign(mb, env)
        world.bundles.set_status(mb.bundle_id, "SIGNED")
        run.signature = world.deliver(sig, to=group.recipients[0], now=now, origin=origin, injected_attack=inj)
        run.notes.append(f"Mallory signed with her own certified bundle {mb.bundle_id[:8]} and claimed to be {group.signer_id}.")
        if counterfactual:
            cf = _counterfactual_signature(world, sig, world.bundles.get(mb.bundle_id) or mb,
                                           world.bundles.meta(mb.bundle_id), "", use_guard=False, now=now)
            acc = cf.primary is not None and cf.primary.decision == "ACCEPT"
            run.counterfactual = {"description": "The same signature without key binding (quantum tests only).",
                                  "signature": cf.report(), "breach": acc,
                                  "outcome_sentence": "Without key binding, the quantum tests ACCEPT Mallory's signature: "
                                                      "a valid key is not the right key." if acc else
                                                      "Quantum tests alone rejected it at this run."}
        return run

    if a == "impersonation.keyless":
        bundle = world.pick_bundle_or_distribute(group_id)
        env = world.make_envelope(group, bundle.bundle_id, "Mallory: " + message, "sha256", now, rs)
        bits = encode_bits(env, bundle.params.digest_bits)
        declared = rs.labels(bits.size * bundle.params.L).reshape(bits.size, bundle.params.L)
        run.signature = world.deliver(Signature(env, bits, declared), now=now, origin=origin, injected_attack=inj)
        run.notes.append(f"Mallory claimed {group.signer_id}'s unused bundle {bundle.bundle_id[:8]} without its labels.")
        return run

    if a == "replay.resubmit":
        sig = _captured(world, group_id, message, now, run)
        run.signature = world.deliver(sig, now=now, origin=origin, injected_attack=inj)
        if counterfactual:
            cf = world.deliver(sig.copy(), use_guard=False, counterfactual=True, commit=False, now=now,
                               bundle=world.bundles.get(sig.envelope.bundle_id), meta=world.bundles.meta(sig.envelope.bundle_id))
            run.counterfactual = _replay_cf(cf)
        return run

    if a == "replay.forward_replay":
        sig = _captured(world, group_id, message, now, run)
        run.signature = world.deliver(sig, to=group.recipients[1], forward=False, now=now, origin=origin,
                                      injected_attack=inj, stage="forward_replay")
        return run

    if a == "replay.delayed":
        bundle, sig = _intercept(world, group_id, message, now)
        delay = float(spec.params.get("delay_s", 300.0))
        run.signature = world.deliver(sig, now=now + delay, origin=origin, injected_attack=inj)
        run.notes.append(f"The signature was held for {delay:.0f} s before delivery.")
        return run

    if a == "unauthorized.non_recipient":
        bundle, sig = _intercept(world, group_id, message, now)
        who = spec.params.get("verifier", "erin")
        run.signature = world.deliver(sig, to=who, forward=False, now=now, origin=origin, injected_attack=inj)
        run.notes.append(f"{who} is not a recipient of {group_id}; it holds no measurement records of this public key.")
        return run

    raise ValueError(f"attack {a} not implemented")


def _replay_cf(cf) -> dict:
    acc = cf.primary is not None and cf.primary.decision == "ACCEPT"
    return {"description": "The replayed signature checked by the quantum tests only (protocol guard off).",
            "signature": cf.report(), "breach": acc,
            "outcome_sentence": "Quantum tests alone ACCEPT the replay: its states are genuine. Only the protocol layer "
                                "(one-time bundles, nonces, sequence numbers) stops it." if acc else
                                "Quantum tests rejected it (unexpected for a replay)."}
