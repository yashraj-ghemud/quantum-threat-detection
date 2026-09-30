"""
sentinel/protocol/verification.py
=================================
Signature verification by a recipient, from its :class:`VerifierView` only.

For each signed bit the verifier examines key ``(i, d_i)`` in two sets:

- **own**: its own records at positions it did not forward;
- **recv**: the records its peer forwarded during symmetrization.

In each set a position is *tested* when the verifier's recorded basis equals
the basis of the revealed label, and it is a *mismatch* when the recorded
outcome differs from the revealed label's bit. A set passes when it has at
least ``n_min`` tested positions and ``m <= floor(s * n)``; a key passes when
both sets pass; the signature passes when every key passes.

An SPRT runs over each set's tested positions first, so an obviously forged
signature is rejected after reading a small fraction of it. Acceptance
always requires the fixed test, which is what the forgery bound covers.

Counterfactual modes (for demonstrations, never used for real decisions):
``pooled`` merges the two sets; ``own_only`` ignores symmetrization and
tests the verifier's full own copy.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from sentinel.protocol.keys import VerifierView
from sentinel.protocol.signing import Signature
from sentinel.sequential import Sprt
from sentinel.states import BASIS_OF, BIT_OF

__all__ = ["VerificationReport", "verify", "GRID_KEYS", "GRID_POSITIONS", "SPRT_TRACE_KEYS"]

GRID_KEYS = 16
GRID_POSITIONS = 48
SPRT_TRACE_KEYS = 8


@dataclass
class VerificationReport:
    verifier_id: str
    role: str                 # first | transfer
    mode: str                 # symmetrized | pooled | own_only
    threshold: float
    n_min: int
    decision: str             # ACCEPT | REJECT
    n_own: np.ndarray
    m_own: np.ndarray
    n_recv: np.ndarray
    m_recv: np.ndarray
    passed: np.ndarray        # bool per key
    inconclusive: np.ndarray  # bool per key
    sprt: dict = field(default_factory=dict)
    grid: dict = field(default_factory=dict)
    latency_ms: float = 0.0

    @property
    def failed_keys(self) -> list:
        return [int(i) for i in np.nonzero(~self.passed)[0]]

    @property
    def tested(self) -> int:
        return int(self.n_own.sum() + self.n_recv.sum())

    @property
    def mismatches(self) -> int:
        return int(self.m_own.sum() + self.m_recv.sum())

    def as_dict(self) -> dict:
        tested, mism = self.tested, self.mismatches
        return {
            "verifier_id": self.verifier_id, "role": self.role, "mode": self.mode,
            "threshold": self.threshold, "n_min": self.n_min, "decision": self.decision,
            "keys": {"n_own": self.n_own.tolist(), "m_own": self.m_own.tolist(),
                     "n_recv": self.n_recv.tolist(), "m_recv": self.m_recv.tolist(),
                     "pass": self.passed.astype(int).tolist(), "inconclusive": self.inconclusive.astype(int).tolist()},
            "failed_keys": self.failed_keys,
            "totals": {"tested": tested, "mismatches": mism, "rate": mism / tested if tested else 0.0},
            "sprt": self.sprt, "grid_sample": self.grid, "latency_ms": self.latency_ms,
        }


def _set_counts(rec_basis, rec_out, member, revealed):
    rb = BASIS_OF[revealed]
    rbit = BIT_OF[revealed]
    tested = member & (rec_basis == rb)
    mism = tested & (rec_out != rbit)
    return tested, mism


def verify(view: VerifierView, signature: Signature, threshold: float, n_min: int,
           role: str = "first", sprt: Optional[Sprt] = None, mode: str = "symmetrized") -> VerificationReport:
    """Verify a signature against one recipient's records."""
    t0 = time.perf_counter()
    bits = np.asarray(signature.bits, dtype=np.intp)
    B = bits.size
    idx = np.arange(B)
    revealed = np.asarray(signature.revealed, dtype=np.intp)

    own_b = view.own_basis[idx, bits, :]
    own_o = view.own_outcome[idx, bits, :]
    if mode == "own_only":
        own_member = np.ones_like(own_b, dtype=bool)
        recv_member = np.zeros_like(own_member)
    else:
        own_member = view.own_kept[idx, bits, :]
        recv_member = view.recv_mask[idx, bits, :]
    recv_b = view.recv_basis[idx, bits, :]
    recv_o = view.recv_outcome[idx, bits, :]

    t_own, x_own = _set_counts(own_b, own_o, own_member, revealed)
    t_recv, x_recv = _set_counts(recv_b, recv_o, recv_member, revealed)
    n_own, m_own = t_own.sum(1), x_own.sum(1)
    n_recv, m_recv = t_recv.sum(1), x_recv.sum(1)

    def passes(n, m):
        ok_n = n >= n_min
        return ok_n, ok_n & (m <= np.floor(threshold * n + 1e-9))

    if mode == "pooled":
        n_all, m_all = n_own + n_recv, m_own + m_recv
        enough, passed = passes(n_all, m_all)
        inconclusive = ~enough
    elif mode == "own_only":
        enough, passed = passes(n_own, m_own)
        inconclusive = ~enough
    else:
        e1, p1 = passes(n_own, m_own)
        e2, p2 = passes(n_recv, m_recv)
        passed = p1 & p2
        inconclusive = ~(e1 & e2)

    # SPRT early abort over the tested positions, key by key.
    if mode != "symmetrized":
        sprt = None  # counterfactual verifiers model a naive single test with no per-set SPRT
    sprt_info: dict = {"enabled": sprt is not None}
    if sprt is not None:
        used = 0
        early_key = None
        traces = []
        for i in range(B):
            for set_name, t, x in (("own", t_own[i], x_own[i]), ("recv", t_recv[i], x_recv[i])):
                stream = x[t]
                if stream.size == 0:
                    continue
                r = sprt.run(stream, early_accept=False, trace_points=40 if i < SPRT_TRACE_KEYS else 0)
                if i < SPRT_TRACE_KEYS and r.trace:
                    traces.append({"key": i, "set": set_name, "trace": r.trace, "decision": r.decision})
                if r.decision == "reject":
                    used += r.n_used
                    early_key = i
                    break
                used += int(stream.size)
            if early_key is not None:
                break
        available = int(n_own.sum() + n_recv.sum())
        sprt_info.update({"early_reject": early_key is not None, "reject_key": early_key,
                          "observations_used": int(used), "observations_available": available,
                          "fraction_read": used / available if available else 0.0,
                          "A": sprt.A, "B": sprt.B, "p0": sprt.p0, "p1": sprt.p1, "traces": traces})

    # Display grid: first keys x first positions.
    gk, gp = min(GRID_KEYS, B), min(GRID_POSITIONS, revealed.shape[1])
    cells = []
    for i in range(gk):
        row = []
        for j in range(gp):
            if own_member[i, j]:
                row.append([int(own_b[i, j]), int(own_o[i, j]), 0, int(t_own[i, j]), int(x_own[i, j]), int(revealed[i, j])])
            elif recv_member[i, j]:
                row.append([int(recv_b[i, j]), int(recv_o[i, j]), 1, int(t_recv[i, j]), int(x_recv[i, j]), int(revealed[i, j])])
            else:
                row.append([-1, -1, 2, 0, 0, int(revealed[i, j])])
        cells.append(row)
    grid = {"keys": gk, "positions": gp, "fields": ["basis", "outcome", "set(0=own,1=recv,2=none)", "tested", "mismatch", "label"],
            "cells": cells, "bits": bits[:gk].tolist()}

    decision = "ACCEPT" if bool(np.all(passed)) and not (sprt_info.get("early_reject")) else "REJECT"
    return VerificationReport(
        verifier_id=view.verifier_id, role=role, mode=mode, threshold=float(threshold), n_min=int(n_min),
        decision=decision, n_own=n_own.astype(np.int64), m_own=m_own.astype(np.int64),
        n_recv=n_recv.astype(np.int64), m_recv=m_recv.astype(np.int64),
        passed=passed.astype(bool), inconclusive=inconclusive.astype(bool),
        sprt=sprt_info, grid=grid, latency_ms=(time.perf_counter() - t0) * 1000,
    )
