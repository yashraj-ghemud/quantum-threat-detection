"""
sentinel/protocol/guard.py
==========================
Protocol guard: the classical, conclusive checks a verifier runs before the
quantum tests.

========  =====================================  =========================
 order     check                                  failure means
========  =====================================  =========================
 S1        verifier is a recipient of the bundle  unauthorized verification
 S2        bundle belongs to the claimed signer   impersonation
 S3        bundle usable and not yet consumed     replay / policy block
 S4        nonce never seen by this verifier      replay
 S5        sequence number strictly increasing    replay
 S6        timestamp inside the freshness window  replay (delay attack)
========  =====================================  =========================

State lives behind :class:`GuardStore` so the engine can run in memory
(tests, analytics) and the server can back it with SQLite.
"""

from __future__ import annotations

import time
from typing import Optional, Protocol

from sentinel.detection.findings import Finding
from sentinel.protocol.encoding import Envelope

__all__ = ["GuardStore", "MemoryGuardStore", "check_guard", "USABLE_STATUSES"]

USABLE_STATUSES = ("ACTIVE", "SIGNED", "CONSUMED", "BURNED")
CLOCK_SKEW_S = 5.0


class GuardStore(Protocol):
    def nonce_seen(self, verifier_id: str, nonce: str) -> bool: ...
    def last_seq(self, signer_id: str, verifier_id: str) -> Optional[int]: ...
    def consumed(self, bundle_id: str, verifier_id: str) -> bool: ...
    def commit(self, verifier_id: str, envelope: Envelope, session_id: str, accepted: bool) -> None: ...


class MemoryGuardStore:
    """In-memory guard state (tests and analytics)."""

    def __init__(self) -> None:
        self._nonces: set = set()
        self._seq: dict = {}
        self._consumed: set = set()

    def nonce_seen(self, verifier_id: str, nonce: str) -> bool:
        return (verifier_id, nonce) in self._nonces

    def last_seq(self, signer_id: str, verifier_id: str) -> Optional[int]:
        return self._seq.get((signer_id, verifier_id))

    def consumed(self, bundle_id: str, verifier_id: str) -> bool:
        return (bundle_id, verifier_id) in self._consumed

    def commit(self, verifier_id: str, envelope: Envelope, session_id: str, accepted: bool) -> None:
        self._nonces.add((verifier_id, envelope.nonce))
        self._consumed.add((envelope.bundle_id, verifier_id))
        if accepted:
            key = (envelope.signer_id, verifier_id)
            self._seq[key] = max(self._seq.get(key, -1), int(envelope.seq))


def check_guard(envelope: Envelope, bundle_meta: dict, verifier_id: str, store: GuardStore,
                now: Optional[float] = None, freshness_window_s: float = 120.0,
                known_principals: Optional[set] = None) -> list:
    """Run S1-S6 and return one Finding per check (fired or not)."""
    now = time.time() if now is None else now
    out = []
    recipients = list(bundle_meta.get("recipients", []))

    # S1 authorization
    unknown = known_principals is not None and verifier_id not in known_principals
    authorized = verifier_id in recipients
    out.append(Finding(
        id="S1.authorization", name="Verifier authorization", layer="protocol",
        fired=not authorized, severity="CRITICAL" if not authorized else "NONE", conclusive=True,
        evidence=(f"{verifier_id!r} is {'an unknown principal and ' if unknown else ''}not a recipient of bundle "
                  f"{bundle_meta.get('bundle_id', '?')[:8]} (recipients: {', '.join(recipients)})")
        if not authorized else f"{verifier_id!r} is a recipient of this bundle",
        data={"verifier_id": verifier_id, "recipients": recipients, "unknown_principal": unknown},
    ))

    # S2 key binding
    bound = (bundle_meta.get("signer_id") == envelope.signer_id and bundle_meta.get("group_id") == envelope.group_id)
    out.append(Finding(
        id="S2.key_binding", name="Signer key binding", layer="protocol",
        fired=not bound, severity="CRITICAL" if not bound else "NONE", conclusive=True,
        evidence=(f"signature claims signer {envelope.signer_id!r} / group {envelope.group_id!r} but bundle "
                  f"belongs to {bundle_meta.get('signer_id')!r} / {bundle_meta.get('group_id')!r}")
        if not bound else f"bundle belongs to {envelope.signer_id!r}",
        data={"claimed_signer": envelope.signer_id, "bundle_signer": bundle_meta.get("signer_id")},
    ))

    # S3 bundle state / one-time consumption
    status = bundle_meta.get("status", "ACTIVE")
    consumed = store.consumed(envelope.bundle_id, verifier_id)
    policy = status not in USABLE_STATUSES
    fired3 = consumed or policy
    if consumed:
        ev3 = f"bundle {envelope.bundle_id[:8]} was already consumed by {verifier_id} (one-time key reused)"
    elif policy:
        ev3 = f"bundle {envelope.bundle_id[:8]} is {status} and may not verify signatures"
    else:
        ev3 = f"bundle {envelope.bundle_id[:8]} is {status} and unused by {verifier_id}"
    out.append(Finding(
        id="S3.bundle_state", name="One-time bundle state", layer="protocol",
        fired=fired3, severity="CRITICAL" if fired3 else "NONE", conclusive=True, evidence=ev3,
        data={"status": status, "consumed": consumed, "policy_block": policy},
    ))

    # S4 nonce
    seen = store.nonce_seen(verifier_id, envelope.nonce)
    out.append(Finding(
        id="S4.nonce", name="Nonce freshness", layer="protocol", fired=seen,
        severity="CRITICAL" if seen else "NONE", conclusive=True,
        evidence=f"nonce {envelope.nonce[:12]}… already seen by {verifier_id}" if seen
        else f"nonce {envelope.nonce[:12]}… is new",
        data={"nonce": envelope.nonce},
    ))

    # S5 sequence
    last = store.last_seq(envelope.signer_id, verifier_id)
    regress = last is not None and int(envelope.seq) <= last
    out.append(Finding(
        id="S5.sequence", name="Sequence monotonicity", layer="protocol", fired=regress,
        severity="CRITICAL" if regress else "NONE", conclusive=True,
        evidence=f"sequence {envelope.seq} is not greater than last accepted {last}" if regress
        else f"sequence {envelope.seq} > last accepted {last if last is not None else '—'}",
        data={"seq": int(envelope.seq), "last": last},
    ))

    # S6 freshness window
    age = now - float(envelope.timestamp)
    stale = age > freshness_window_s or age < -CLOCK_SKEW_S
    out.append(Finding(
        id="S6.freshness", name="Freshness window", layer="protocol", fired=stale,
        severity="CRITICAL" if stale else "NONE", conclusive=True,
        statistic={"name": "age_s", "value": age},
        evidence=(f"signature is {age:.1f}s old; window is {freshness_window_s:.0f}s" if age >= 0
                  else f"timestamp is {-age:.1f}s in the future") if stale
        else f"age {age:.1f}s within {freshness_window_s:.0f}s window",
        data={"age_s": age, "window_s": freshness_window_s},
    ))
    return out
