"""
sentinel/world.py
=================
The engine's world: network, stores, and the end-to-end flows.

:class:`World` owns everything a run needs: groups and links, the measured
baselines, per-link monitors, the guard state, the bundle store, per-group
sequence counters and a capture buffer of signatures seen on public
channels. Storage is pluggable: the server backs these with SQLite and
keystore files, and tests and analytics use the in-memory defaults.

Flows
-----
- :meth:`World.distribute`      distribution + D1-D10 + fusion -> DistributionRun
- :meth:`World.sign`            one-time signing with an ACTIVE bundle
- :meth:`World.deliver`         verification at a recipient (+ transfer) -> SignatureRun
- :meth:`World.sign_and_verify` the honest end-to-end session
- :meth:`World.run_attack`      any catalog attack, with counterfactuals -> AttackRun
"""

from __future__ import annotations

import copy
import itertools
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

import numpy as np

from sentinel.detection.baseline import LinkBaseline, calibrate_link
from sentinel.detection.config import DetectionConfig
from sentinel.detection.distribution_detectors import apply_holm, copy_consistency, link_detectors, margin_finding
from sentinel.detection.findings import SEVERITY_RANK, Assessment, Finding
from sentinel.detection.fusion import fuse_distribution, fuse_signature
from sentinel.detection.monitor import LinkMonitor
from sentinel.detection.signature_detectors import forensics, key_tests, sprt_finding, transfer_consistency
from sentinel.protocol.distribution import DistributionOutcome, distribute as _distribute
from sentinel.protocol.encoding import Envelope, digest_hex, encode_bits
from sentinel.protocol.guard import GuardStore, MemoryGuardStore, check_guard
from sentinel.protocol.keys import KeyBundle
from sentinel.protocol.link import HardwareModel, LinkPlan, LinkSpec
from sentinel.protocol.params import ProtocolParams
from sentinel.protocol.signing import Signature, sign as _sign
from sentinel.protocol.verification import VerificationReport, verify as _verify
from sentinel.rng import RandomSource
from sentinel.sequential import Sprt

__all__ = [
    "GroupSpec", "BundleStore", "MemoryBundleStore", "World", "DistributionRun", "SignatureRun",
    "BundleUnavailable", "BundleCompromised", "LinkQuarantined", "CapturedSignature",
]


class BundleUnavailable(RuntimeError):
    """No ACTIVE bundle for the group."""


class BundleCompromised(RuntimeError):
    """The requested bundle may not sign (COMPROMISED / REVOKED / EXPIRED)."""


class LinkQuarantined(RuntimeError):
    """A link of the group is quarantined."""


@dataclass
class GroupSpec:
    group_id: str
    signer_id: str
    recipients: tuple
    hidden: bool = False


class BundleStore(Protocol):
    def put(self, bundle: KeyBundle) -> None: ...
    def get(self, bundle_id: str) -> Optional[KeyBundle]: ...
    def meta(self, bundle_id: str) -> Optional[dict]: ...
    def set_status(self, bundle_id: str, status: str) -> None: ...
    def active_ids(self, group_id: str) -> list: ...
    def shred(self, bundle_id: str, labels_only: bool = False) -> None: ...


class MemoryBundleStore:
    def __init__(self) -> None:
        self._b: dict = {}
        self._meta: dict = {}
        self._lock = threading.RLock()

    def put(self, bundle: KeyBundle) -> None:
        with self._lock:
            self._b[bundle.bundle_id] = bundle
            self._meta[bundle.bundle_id] = {**bundle.meta(), "status": bundle.status}

    def get(self, bundle_id: str) -> Optional[KeyBundle]:
        return self._b.get(bundle_id)

    def meta(self, bundle_id: str) -> Optional[dict]:
        return self._meta.get(bundle_id)

    def set_status(self, bundle_id: str, status: str) -> None:
        with self._lock:
            if bundle_id in self._meta:
                self._meta[bundle_id]["status"] = status
            if bundle_id in self._b:
                self._b[bundle_id].status = status

    def active_ids(self, group_id: str) -> list:
        with self._lock:
            items = [m for m in self._meta.values() if m["group_id"] == group_id and m["status"] == "ACTIVE"]
            return [m["bundle_id"] for m in sorted(items, key=lambda m: m["created_at"])]

    def shred(self, bundle_id: str, labels_only: bool = False) -> None:
        with self._lock:
            b = self._b.get(bundle_id)
            if b is None:
                return
            b.shred_labels()
            if not labels_only:
                self._b.pop(bundle_id, None)


@dataclass
class CapturedSignature:
    signature: Signature
    session_id: str
    group_id: str
    delivered: bool
    transferred: bool
    at: float


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Run results
# ---------------------------------------------------------------------------

@dataclass
class DistributionRun:
    session_id: str
    group: GroupSpec
    outcome: DistributionOutcome
    findings: list
    assessment: Assessment
    monitor_points: dict
    baselines: dict
    detect_ms: float
    counterfactual: bool = False
    injected_attack: Optional[dict] = None
    origin: str = "API"
    created_at: float = field(default_factory=_now)
    bundle_copy: Optional[KeyBundle] = None    # retained only for counterfactual demonstrations

    @property
    def bundle_id(self) -> str:
        return self.outcome.bundle.bundle_id

    @property
    def status(self) -> str:
        return "ACTIVE" if self.assessment.verdict == "CERTIFIED" else "COMPROMISED"

    def report(self) -> dict:
        o = self.outcome
        links = []
        for v in self.group.recipients:
            ev = o.evidence[v]
            d = ev.as_dict()
            base = self.baselines.get(ev.link_id)
            d["baseline"] = base.summary() if base else None
            d["monitor"] = self.monitor_points.get(ev.link_id)
            d["findings"] = [f.id for f in self.findings if f.link_id == ev.link_id and f.fired]
            links.append(d)
        p = o.bundle.params
        return {
            "session_id": self.session_id, "kind": "distribution", "created_at": self.created_at, "origin": self.origin,
            "bundle_id": self.bundle_id, "group_id": self.group.group_id, "signer_id": self.group.signer_id,
            "recipients": list(self.group.recipients), "preset": p.preset, "params": p.as_dict(),
            "qubits_teleported": o.qubits, "bell_pairs": o.bell_pairs, "links": links,
            "symmetrization": {"forwarded_per_key": p.L // 2, "kept_per_key": p.L},
            "design": o.design.as_dict(), "e_ucb": o.e_ucb, "assessment": self.assessment.as_dict(),
            "verdict": self.assessment.verdict, "status": self.status,
            "latency_ms": {**{k: float(v) for k, v in o.timings.items()}, "detect_ms": self.detect_ms,
                           "total": float(o.timings.get("total_ms", 0)) + self.detect_ms},
            "hardware_time_ms_modelled": max(ev.hardware_time_ms for ev in o.evidence.values()),
            "injected_attack": self.injected_attack, "counterfactual": self.counterfactual,
        }

    def summary(self) -> dict:
        a = self.assessment
        return {
            "id": self.session_id, "kind": "distribution", "created_at": self.created_at, "origin": self.origin,
            "group_id": self.group.group_id, "signer_id": self.group.signer_id, "recipients": list(self.group.recipients),
            "bundle_id": self.bundle_id, "verdict": a.verdict, "threat_level": a.threat_level,
            "category": a.classification.category, "subtype": a.classification.subtype, "threat_score": a.threat_score,
            "injected_attack": ({"attack_id": self.injected_attack["attack_id"], "category": self.injected_attack.get("category")}
                                if self.injected_attack else None),
            "qubits": self.outcome.qubits,
            "latency_ms": float(self.outcome.timings.get("total_ms", 0)) + self.detect_ms,
            "links": [{"link_id": self.outcome.evidence[v].link_id, "verifier_id": v,
                       "S": self.outcome.evidence[v].bell.S, "qber": self.outcome.evidence[v].qber["rate"],
                       "frame_mismatch": self.outcome.evidence[v].frame["mismatched"]} for v in self.group.recipients],
        }


@dataclass
class SignatureRun:
    session_id: str
    group_id: str
    signature: Signature
    primary_verifier: str
    primary: Optional[VerificationReport]
    transfer: Optional[VerificationReport]
    guard: dict                 # verifier -> [Finding]
    findings: list
    assessment: Assessment
    design: Optional[dict]
    latency_ms: dict
    counterfactual: bool = False
    injected_attack: Optional[dict] = None
    origin: str = "API"
    stage: str = "first"
    created_at: float = field(default_factory=_now)
    notes: list = field(default_factory=list)

    @property
    def envelope(self) -> Envelope:
        return self.signature.envelope

    def report(self) -> dict:
        env = self.envelope
        d = self.design or {}
        eps = {"rob_msg": d.get("eps_rob_msg"), "forge_key": d.get("eps_forge_key"), "rep_msg": d.get("eps_rep_msg")}
        verifs = []
        for rep, role in ((self.primary, self.stage), (self.transfer, "transfer")):
            if rep is None:
                continue
            item = rep.as_dict()
            item["role"] = role if rep is self.primary else "transfer"
            item["guard"] = [f.as_dict() for f in self.guard.get(rep.verifier_id, [])]
            verifs.append(item)
        if self.primary is None:
            verifs.append({"verifier_id": self.primary_verifier, "role": self.stage, "decision": "REJECT",
                           "guard": [f.as_dict() for f in self.guard.get(self.primary_verifier, [])],
                           "note": "no measurement records: this party never received the quantum public key"})
        sample = self.signature.revealed[:16, :48].tolist()
        return {
            "session_id": self.session_id, "kind": "signature", "created_at": self.created_at, "origin": self.origin,
            "group_id": self.group_id, "bundle_id": env.bundle_id, "encoding": env.encoding,
            "envelope": env.as_dict(),
            "digest": {"hex": digest_hex(env) if not self.signature.oracle else None,
                       "bits": "".join(str(int(b)) for b in self.signature.bits), "oracle": self.signature.oracle},
            "signature": {"sha256": self.signature.sha256(), "size_bytes": self.signature.size_bytes,
                          "revealed_sample": sample},
            "verifications": verifs, "assessment": self.assessment.as_dict(), "verdict": self.assessment.verdict,
            "design": d, "eps": eps, "latency_ms": self.latency_ms, "stage": self.stage,
            "injected_attack": self.injected_attack, "counterfactual": self.counterfactual, "notes": self.notes,
        }

    def summary(self) -> dict:
        a = self.assessment
        env = self.envelope
        return {
            "id": self.session_id, "kind": "signature", "created_at": self.created_at, "origin": self.origin,
            "group_id": self.group_id, "signer_id": env.signer_id, "recipients": list(env.recipients),
            "message_preview": env.message[:80], "bundle_id": env.bundle_id, "verdict": a.verdict,
            "threat_level": a.threat_level, "category": a.classification.category, "subtype": a.classification.subtype,
            "threat_score": a.threat_score,
            "injected_attack": ({"attack_id": self.injected_attack["attack_id"], "category": self.injected_attack.get("category")}
                                if self.injected_attack else None),
            "latency_ms": self.latency_ms.get("total"),
            "decisions": {"first": self.primary.decision if self.primary else "REJECT",
                          "transfer": self.transfer.decision if self.transfer else "SKIPPED"},
        }


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------

class World:
    def __init__(
        self,
        groups: dict,
        links: dict,
        params: ProtocolParams,
        detection: Optional[DetectionConfig] = None,
        guard: Optional[GuardStore] = None,
        bundles: Optional[BundleStore] = None,
        baselines: Optional[dict] = None,
        monitor_states: Optional[dict] = None,
        hardware: Optional[HardwareModel] = None,
        seed: Optional[int] = None,
        principals: Optional[set] = None,
        next_seq: Optional[Callable[[str], int]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.groups = dict(groups)
        self.links = dict(links)
        self.params = params
        self.detection = detection or DetectionConfig()
        self.guard = guard or MemoryGuardStore()
        self.bundles = bundles or MemoryBundleStore()
        self.baselines: dict = dict(baselines or {})
        self.monitor_states: dict = dict(monitor_states or {})
        self.hardware = hardware or HardwareModel()
        self.principals = principals
        self.clock = clock
        self.capture: deque = deque(maxlen=16)
        self._seed = seed
        self._seed_counter = itertools.count()
        self._seq: dict = {}
        self._next_seq = next_seq
        self._lock = threading.RLock()
        self.quarantined: set = set()
        self.monitors_enabled = True

    # -- helpers -------------------------------------------------------------
    def rs(self) -> RandomSource:
        if self._seed is None:
            return RandomSource()
        return RandomSource(self._seed * 100_003 + next(self._seed_counter))

    def group(self, group_id: str) -> GroupSpec:
        if group_id not in self.groups:
            raise KeyError(f"unknown group {group_id!r}")
        return self.groups[group_id]

    def link_between(self, signer: str, verifier: str) -> LinkSpec:
        for spec in self.links.values():
            if spec.signer_id == signer and spec.verifier_id == verifier:
                return spec
        raise KeyError(f"no quantum link {signer} -> {verifier}")

    def group_links(self, group: GroupSpec) -> dict:
        return {v: self.link_between(group.signer_id, v) for v in group.recipients}

    def calibrate(self, link_ids=None) -> dict:
        ids = list(link_ids) if link_ids else list(self.links)
        for lid in ids:
            spec = self.links[lid]
            self.baselines[lid] = calibrate_link(spec, self.rs(), self.detection.calibration_pe_samples,
                                                 self.detection.calibration_bell_per_setting)
            self.monitor_states.pop(lid, None)
        return {lid: self.baselines[lid] for lid in ids}

    def ensure_baselines(self, group: GroupSpec) -> None:
        missing = [self.link_between(group.signer_id, v).link_id for v in group.recipients
                   if self.link_between(group.signer_id, v).link_id not in self.baselines]
        if missing:
            self.calibrate(missing)

    def seq_for(self, group_id: str) -> int:
        if self._next_seq is not None:
            return int(self._next_seq(group_id))
        with self._lock:
            self._seq[group_id] = self._seq.get(group_id, 0) + 1
            return self._seq[group_id]

    # -- distribution ----------------------------------------------------------
    def distribute(self, group_id: str, plans: Optional[dict] = None, params: Optional[ProtocolParams] = None,
                   counterfactual: bool = False, update_monitors: bool = True, origin: str = "API",
                   injected_attack: Optional[dict] = None, keep_copy: bool = False, store: bool = True) -> DistributionRun:
        group = self.group(group_id)
        links = self.group_links(group)
        for spec in links.values():
            if spec.link_id in self.quarantined and not counterfactual:
                raise LinkQuarantined(f"link {spec.link_id} is quarantined")
        self.ensure_baselines(group)
        params = params or self.params
        outcome = _distribute(group.group_id, group.signer_id, tuple(group.recipients), links, params, self.rs(),
                              plans=plans, hardware=self.hardware)
        t0 = time.perf_counter()
        findings: list = []
        for v in group.recipients:
            ev = outcome.evidence[v]
            findings += link_detectors(ev, self.baselines[ev.link_id], self.detection)
        a, b = group.recipients
        findings.append(copy_consistency(outcome.evidence[a], outcome.evidence[b], self.detection))
        findings.append(margin_finding(outcome.design))
        apply_holm(findings, self.detection.alpha_family)
        points = {}
        if update_monitors and self.monitors_enabled and not counterfactual:
            for v in group.recipients:
                ev = outcome.evidence[v]
                mon = LinkMonitor(ev.link_id, self.detection, self.monitor_states.get(ev.link_id))
                f, point = mon.update(ev, self.baselines[ev.link_id])
                # CUSUM exists for shifts too small for any single run. A run that single-run
                # detectors already flagged (HIGH or worse on this link) is handled by them; feeding
                # it into the accumulator would make the next honest bundles alarm for a long time.
                caught = [g.id for g in findings if g.fired and g.link_id == ev.link_id
                          and SEVERITY_RANK.get(g.severity, 0) >= SEVERITY_RANK["HIGH"]]
                if caught:
                    point["excluded"] = True
                    f.fired, f.severity = False, "NONE"
                    f.evidence = (f"Run excluded from the drift accumulator: already flagged by {', '.join(sorted(set(caught)))}. "
                                  f"The monitor keeps its previous state.")
                else:
                    self.monitor_states[ev.link_id] = mon.state()
                findings.append(f)
                points[ev.link_id] = point
        assessment = fuse_distribution(findings)
        detect_ms = (time.perf_counter() - t0) * 1000

        bundle = outcome.bundle
        bundle.status = "ACTIVE" if assessment.verdict == "CERTIFIED" else "COMPROMISED"
        run = DistributionRun(
            session_id=str(uuid.uuid4()), group=group, outcome=outcome, findings=findings, assessment=assessment,
            monitor_points=points, baselines={ev.link_id: self.baselines[ev.link_id] for ev in outcome.evidence.values()},
            detect_ms=detect_ms, counterfactual=counterfactual, injected_attack=injected_attack, origin=origin,
            bundle_copy=copy.deepcopy(bundle) if keep_copy else None,
        )
        if store and not counterfactual:
            self.bundles.put(bundle)
            if bundle.status == "COMPROMISED":
                self.bundles.shred(bundle.bundle_id, labels_only=True)
        return run

    # -- signing -------------------------------------------------------------
    def pick_bundle(self, group_id: str) -> KeyBundle:
        for bid in self.bundles.active_ids(group_id):
            b = self.bundles.get(bid)
            if b is not None and b.labels is not None and not b.signed:
                return b
        raise BundleUnavailable(f"no ACTIVE bundle for group {group_id}")

    def baseline_design(self, group_id: str, params: Optional[ProtocolParams] = None):
        """Thresholds designed at the links' calibrated baselines (no per-bundle estimation)."""
        from sentinel.protocol.thresholds import design_for
        from sentinel.stats import cp_upper

        group = self.group(group_id)
        self.ensure_baselines(group)
        params = params or self.params
        ucbs = []
        for v in group.recipients:
            q = self.baselines[self.link_between(group.signer_id, v).link_id].qber
            ucbs.append(cp_upper(q["errors"], q["n"], params.delta_pe))
        return design_for(params, max(ucbs))

    def pick_bundle_or_distribute(self, group_id: str, origin: str = "LAB") -> KeyBundle:
        """An ACTIVE bundle, distributing a fresh one if the reservoir is empty."""
        try:
            return self.pick_bundle(group_id)
        except BundleUnavailable:
            run = self.distribute(group_id, origin=origin)
            if run.status != "ACTIVE":
                raise BundleUnavailable(f"fresh distribution for {group_id} was {run.status}")
            return self.bundles.get(run.bundle_id)

    def make_envelope(self, group: GroupSpec, bundle_id: str, message: str, encoding: str = "sha256",
                      now: Optional[float] = None, rs: Optional[RandomSource] = None) -> Envelope:
        rs = rs or self.rs()
        return Envelope(group_id=group.group_id, signer_id=group.signer_id, recipients=tuple(group.recipients),
                        bundle_id=bundle_id, seq=self.seq_for(group.group_id),
                        timestamp=self.clock() if now is None else now, nonce=rs.token_hex(16),
                        message=message, encoding=encoding)

    def sign(self, group_id: str, message: str, encoding: str = "sha256", bundle: Optional[KeyBundle] = None,
             now: Optional[float] = None, allow_compromised: bool = False) -> tuple:
        group = self.group(group_id)
        if not allow_compromised:
            # A quarantined link is no longer trusted: bundles certified over it earlier must not sign either.
            bad = [s.link_id for s in self.group_links(group).values() if s.link_id in self.quarantined]
            if bad:
                raise LinkQuarantined(f"link {', '.join(bad)} is quarantined")
        if bundle is None:
            bundle = self.pick_bundle(group_id)
        if bundle.status not in ("ACTIVE",) and not allow_compromised:
            raise BundleCompromised(f"bundle {bundle.bundle_id} is {bundle.status}")
        t0 = time.perf_counter()
        env = self.make_envelope(group, bundle.bundle_id, message, encoding, now)
        sig = _sign(bundle, env)
        if not allow_compromised:
            self.bundles.set_status(bundle.bundle_id, "SIGNED")
        return bundle, sig, (time.perf_counter() - t0) * 1000

    # -- verification ------------------------------------------------------------
    def _verify_at(self, signature: Signature, verifier_id: str, role: str, now: float, mode: str,
                   use_guard: bool, commit: bool, session_id: str, guard_store: GuardStore,
                   bundle: Optional[KeyBundle], meta: Optional[dict]) -> tuple:
        env = signature.envelope
        if not signature.oracle:
            signature.bits = encode_bits(env, (bundle.params.digest_bits if bundle else self.params.digest_bits))
        bundle = bundle if bundle is not None else self.bundles.get(env.bundle_id)
        meta = meta if meta is not None else (self.bundles.meta(env.bundle_id) or {
            "bundle_id": env.bundle_id, "status": "UNKNOWN", "recipients": [], "signer_id": None, "group_id": None})
        guard = check_guard(env, meta, verifier_id, guard_store, now, self.params.freshness_window_s,
                            self.principals) if use_guard else []
        report = None
        if bundle is not None and verifier_id in bundle.recipients:
            d = bundle.design or {}
            s = d.get("s_a") if role != "transfer" else d.get("s_v")
            sp = d.get("sprt") or {}
            sprt = Sprt(sp["p0"], sp["p1"], sp["alpha"], sp["beta"]) if sp else None
            report = _verify(bundle.view_for(verifier_id), signature, float(s if s is not None else 0.0),
                             int(d.get("n_min", 1)), "transfer" if role == "transfer" else "first", sprt, mode)
        guard_fired = any(f.fired for f in guard)
        accepted = report is not None and report.decision == "ACCEPT" and not guard_fired
        if commit and use_guard and verifier_id in meta.get("recipients", []):
            guard_store.commit(verifier_id, env, session_id, accepted)
            current = (self.bundles.meta(env.bundle_id) or {}).get("status")
            if current == "ACTIVE":
                # A recipient consumed an unsigned bundle (someone presented labels the
                # signer never revealed): the signer can no longer use it.
                self.bundles.set_status(env.bundle_id, "BURNED")
            self._maybe_consume(env.bundle_id, meta)
        return report, guard, accepted

    def _maybe_consume(self, bundle_id: str, meta: dict) -> None:
        recips = meta.get("recipients", [])
        if recips and all(self.guard.consumed(bundle_id, r) for r in recips):
            self.bundles.set_status(bundle_id, "CONSUMED")
            # The signer's labels are now public anyway; destroy the private copy.
            # Recipients keep their own measurement records (forensics, audits).
            self.bundles.shred(bundle_id, labels_only=True)

    def deliver(self, signature: Signature, to: Optional[str] = None, role: str = "first", forward: bool = True,
                now: Optional[float] = None, mode_first: str = "symmetrized", mode_transfer: str = "symmetrized",
                use_guard: bool = True, commit: bool = True, stage: str = "first", counterfactual: bool = False,
                origin: str = "API", injected_attack: Optional[dict] = None, sign_ms: float = 0.0,
                bundle: Optional[KeyBundle] = None, meta: Optional[dict] = None,
                guard_store: Optional[GuardStore] = None) -> SignatureRun:
        env = signature.envelope
        now = self.clock() if now is None else now
        session_id = str(uuid.uuid4())
        guard_store = guard_store or (self.guard if not counterfactual else MemoryGuardStore())
        b = bundle if bundle is not None else self.bundles.get(env.bundle_id)
        to = to or env.recipients[0]
        t0 = time.perf_counter()
        primary, g1, acc1 = self._verify_at(signature, to, role, now, mode_first, use_guard, commit, session_id,
                                            guard_store, b, meta)
        t1 = time.perf_counter()
        transfer = None
        guard = {to: g1}
        if forward and acc1 and role != "transfer" and b is not None:
            peer = b.peer_of(to)
            transfer, g2, _ = self._verify_at(signature, peer, "transfer", now, mode_transfer, use_guard, commit,
                                              session_id, guard_store, b, meta)
            guard[peer] = g2
        t2 = time.perf_counter()

        findings: list = []
        for v, gf in guard.items():
            findings += gf
        e_ucb = float((b.design or {}).get("e_ucb", 0.0)) if b else 0.0
        reports = [r for r in (primary, transfer) if r is not None]
        for r in reports:
            findings.append(key_tests(r, e_ucb))
            if r.sprt.get("enabled"):
                findings.append(sprt_finding(r))
            fz = forensics(r, e_ucb, b.peer_of(r.verifier_id)) if b else None
            if fz:
                findings.append(fz)
        if role != "transfer":
            findings.append(transfer_consistency(primary, transfer))
        assessment = fuse_signature(findings, acc1, stage)
        run = SignatureRun(
            session_id=session_id, group_id=env.group_id, signature=signature, primary_verifier=to,
            primary=primary, transfer=transfer, guard=guard, findings=findings, assessment=assessment,
            design=(b.design if b else None),
            latency_ms={"sign": sign_ms, "verify_first": (t1 - t0) * 1000, "verify_transfer": (t2 - t1) * 1000,
                        "total": sign_ms + (t2 - t0) * 1000},
            counterfactual=counterfactual, injected_attack=injected_attack, origin=origin, stage=stage,
        )
        return run

    def sign_and_verify(self, group_id: str, message: str, encoding: str = "sha256",
                        bundle_id: Optional[str] = None, now: Optional[float] = None, origin: str = "API",
                        capture: bool = True) -> SignatureRun:
        bundle = self.bundles.get(bundle_id) if bundle_id else None
        if bundle_id and bundle is None:
            raise BundleUnavailable(f"bundle {bundle_id} not found or already consumed")
        bundle, sig, sign_ms = self.sign(group_id, message, encoding, bundle, now)
        run = self.deliver(sig, now=now, origin=origin, sign_ms=sign_ms)
        if capture:
            self.capture.append(CapturedSignature(sig.copy(), run.session_id, group_id, True,
                                                  run.transfer is not None, self.clock()))
        return run

    # -- attacks -------------------------------------------------------------
    def run_attack(self, spec, group_id: str = "g-alice", message: Optional[str] = None,
                   counterfactual: bool = True, now: Optional[float] = None, origin: str = "LAB"):
        from sentinel.adversary.runner import run_attack

        return run_attack(self, spec, group_id=group_id, message=message, counterfactual=counterfactual,
                          now=now, origin=origin)
