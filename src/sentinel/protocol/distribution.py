"""
sentinel/protocol/distribution.py
=================================
The distribution phase of TQDS: from fresh private labels to a certified-or-
not key bundle, with the evidence the detectors need.

For each recipient ``V`` over link ``(S, V)``:

1. Bell test on sacrificial pairs (7 settings) -> CHSH, witness, predicted errors.
2. Teleport every key position's eigenstate over its own Bell pair; ``V``
   measures immediately in a CSPRNG basis and records ``(basis, outcome, c)``.
3. Parameter estimation on ``n_pe`` random positions per key: the signer
   reveals ``(label, k)``, the verifier reveals ``(basis, outcome, c)``.
4. Optional Wegman-Carter MAC over the correction-bit stream.

Then: threshold design from the measured QBER upper bound, and
symmetrization (each recipient forwards a random half of its kept records
to the other).

Adversary behaviour arrives as a :class:`~sentinel.protocol.link.LinkPlan`
per link and changes only physics: channels, which pairs Eve holds, what
correction bits arrive, or (for a dishonest signer) which states are sent.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Mapping, Optional

import numpy as np

from sentinel.bell import BellEstimate, estimate_bell, sample_bell_test, setting_probs
from sentinel.protocol.keys import KeyBundle, VerifierRecords
from sentinel.protocol.link import HardwareModel, LinkPlan, LinkSpec, wc_keys, wc_tag
from sentinel.protocol.params import ProtocolParams
from sentinel.protocol.thresholds import ThresholdDesign, design_for
from sentinel.rng import RandomSource
from sentinel.stats import cp_upper
from sentinel.teleport import get_model, sample_teleportations
from sentinel.tomography import ChannelEstimate, PECounts, aggregate_pe, detwirl, effective, frame_matrix, qber_counts

__all__ = ["LinkEvidence", "DistributionOutcome", "distribute", "SAMPLE_POSITIONS"]

SAMPLE_POSITIONS = 64
_BASIS_IDX = {"x": 0, "y": 1, "z": 2}


@dataclass
class LinkEvidence:
    link_id: str
    verifier_id: str
    bell: BellEstimate
    pe: PECounts
    qber: dict
    detwirled: ChannelEstimate
    effective: ChannelEstimate
    frame: dict
    hardware_time_ms: float
    sample: list = field(default_factory=list)

    def as_dict(self) -> dict:
        fm = self.frame
        return {
            "link_id": self.link_id,
            "verifier_id": self.verifier_id,
            "bell": self.bell.as_dict(),
            "pe": {"n": self.pe.total, "qber": self.qber["rate"], "errors": self.qber["errors"],
                   "matched": self.qber["n"], "per_basis": self.qber["per_basis"]},
            "tomography": {"detwirled": self.detwirled.as_dict(), "effective": self.effective.as_dict()},
            "frame": fm,
            "hardware_time_ms_modelled": self.hardware_time_ms,
            "sample": self.sample,
        }


@dataclass
class DistributionOutcome:
    bundle: KeyBundle
    evidence: dict              # verifier_id -> LinkEvidence
    design: ThresholdDesign
    e_ucb: float
    qubits: int
    bell_pairs: int
    timings: dict
    plans: dict                 # verifier_id -> LinkPlan (ground truth, never shown to detectors)
    artifacts: dict = field(default_factory=dict)   # adversary artifacts (e.g. harvested knowledge)


def _exact_k_mask(rs: RandomSource, shape: tuple, k: int) -> np.ndarray:
    """Boolean mask with exactly k uniformly placed True entries along the last axis."""
    mask = np.zeros(shape, dtype=bool)
    if k <= 0:
        return mask
    if k >= shape[-1]:
        mask[...] = True
        return mask
    part = np.argpartition(rs.sort_keys(shape), k - 1, axis=-1)[..., :k]
    np.put_along_axis(mask, part, True, axis=-1)
    return mask


def _intercept_rhos(baseline: list, extra: list, basis: str) -> list:
    bases = ["x", "y", "z"] if basis == "random" else [basis]
    return [get_model(baseline + [{"type": "measure_prepare", "basis": b}] + extra).rho_ab for b in bases]


def _bell_probs(spec: LinkSpec, plan: LinkPlan) -> np.ndarray:
    model = get_model(list(spec.baseline) + list(plan.extra_channel))
    probs = setting_probs(model.rho_ab)
    f = float(plan.substitute_fraction)
    if f <= 0 or plan.substitute_mode == "none":
        return probs
    if plan.substitute_mode == "mitm":
        sub = np.full_like(probs, 0.25)  # Alice's and Bob's halves belong to different pairs: I/4
    else:
        rhos = _intercept_rhos(list(spec.baseline), list(plan.extra_channel), plan.intercept_basis)
        sub = sum(setting_probs(r) for r in rhos) / len(rhos)
    return (1 - f) * probs + f * sub


def _teleport_copy(spec: LinkSpec, plan: LinkPlan, sent: np.ndarray, bases: np.ndarray,
                   rs: RandomSource, artifacts: dict, eve_memory: dict | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Teleport one recipient's copy. Returns (k sent, c received, outcome)."""
    n = sent.size
    rng = rs.physics
    baseline = list(spec.baseline)
    direct_model = get_model(baseline + list(plan.extra_channel))
    k = np.empty(n, dtype=np.uint8)
    c = np.empty(n, dtype=np.uint8)
    o = np.empty(n, dtype=np.uint8)

    sub = np.zeros(n, dtype=bool)
    if plan.substitute_fraction > 0 and plan.substitute_mode != "none":
        sub = rng.random(n) < plan.substitute_fraction
    direct = ~sub

    f0 = rng.random(n) < plan.flip_c0 if plan.flip_c0 > 0 else None
    f1 = rng.random(n) < plan.flip_c1 if plan.flip_c1 > 0 else None
    kd, cd, od = sample_teleportations(
        direct_model, sent[direct], bases[direct], rng,
        None if f0 is None else f0[direct], None if f1 is None else f1[direct])
    k[direct], c[direct], o[direct] = kd, cd, od

    if sub.any():
        idx = np.nonzero(sub)[0]
        m = idx.size
        if plan.intercept_basis == "random":
            eve_basis = rng.integers(0, 3, m).astype(np.uint8)
        else:
            eve_basis = np.full(m, _BASIS_IDX[plan.intercept_basis], dtype=np.uint8)
        if plan.substitute_mode == "mitm":
            # Signer -> Eve: Eve holds the signer's partner, reads k on the classical
            # channel, corrects, and measures the key state in her basis.
            ea = get_model(baseline)
            kA, _, oE = sample_teleportations(ea, sent[idx], eve_basis, rng)
            eve_label = (2 * eve_basis + oE).astype(np.uint8)
            if eve_memory is not None:
                # An Eve attacking both copies re-sends the state she already measured on
                # the other copy, so both recipients hold records of the same eigenstate.
                known = eve_memory.setdefault("label", np.full(sent.size, 255, dtype=np.uint8))
                have = known[idx] != 255
                eve_label[have] = known[idx][have]
                eve_basis[have] = eve_label[have] // 2
                oE[have] = eve_label[have] % 2
                known[idx[~have]] = eve_label[~have]
            # Eve -> verifier through her own pair; the verifier receives Eve's bits.
            kE, cE, oB = sample_teleportations(get_model(baseline), eve_label, bases[idx], rng)
            k[idx], c[idx], o[idx] = kA, kE, oB
            artifacts["harvested"] = {"positions": idx, "basis": eve_basis, "outcome": oE}
        else:
            # Intercept-resend on the verifier's Bell half, before teleportation.
            for b in range(3):
                sel = eve_basis == b
                if not sel.any():
                    continue
                model = get_model(baseline + [{"type": "measure_prepare", "basis": "xyz"[b]}] + list(plan.extra_channel))
                ii = idx[sel]
                kk, cc, oo = sample_teleportations(model, sent[ii], bases[ii], rng,
                                                   None if f0 is None else f0[ii], None if f1 is None else f1[ii])
                k[ii], c[ii], o[ii] = kk, cc, oo
    return k, c, o


def distribute(
    group_id: str,
    signer_id: str,
    recipients: tuple,
    links: Mapping[str, LinkSpec],
    params: ProtocolParams,
    rs: Optional[RandomSource] = None,
    plans: Optional[Mapping[str, LinkPlan]] = None,
    bundle_id: Optional[str] = None,
    hardware: Optional[HardwareModel] = None,
) -> DistributionOutcome:
    """Run the distribution phase for one bundle."""
    t_start = time.perf_counter()
    rs = rs or RandomSource()
    plans = {v: (plans or {}).get(v) or LinkPlan() for v in recipients}
    hardware = hardware or HardwareModel()
    bundle_id = bundle_id or str(uuid.uuid4())
    B, Ld, L, n_pe = params.digest_bits, params.L_dist, params.L, params.n_pe
    shape_d = (B, 2, Ld)
    N = B * 2 * Ld

    timings: dict = {}
    t0 = time.perf_counter()
    labels_d = rs.labels(N).reshape(shape_d)
    # Parameter-estimation positions: exactly n_pe per key, uniformly placed.
    pe_mask = _exact_k_mask(rs, shape_d, n_pe)
    timings["keygen_ms"] = (time.perf_counter() - t0) * 1000

    evidence: dict = {}
    eve_memory: dict = {}
    kept_records: dict = {}
    artifacts: dict = {}
    ucbs = []
    t0 = time.perf_counter()
    for v in recipients:
        spec, plan = links[v], plans[v]
        flat_labels = labels_d.reshape(-1)
        sent = flat_labels.copy()
        if plan.source_flip_fraction > 0:
            flip = rs.uniform(N) < plan.source_flip_fraction
            sent[flip] ^= 1  # orthogonal eigenstate in the same basis
        bases = rs.bases(N)
        art: dict = {}
        k, c, o = _teleport_copy(spec, plan, sent, bases, rs, art, eve_memory)
        if art:
            artifacts[v] = art

        # Bell test.
        bell_counts = sample_bell_test(_bell_probs(spec, plan), params.bell_pairs_per_setting, rs.physics)
        bell = estimate_bell(bell_counts, params.delta_bell)

        # Parameter estimation (the signer reveals its *claimed* labels).
        pe_flat = pe_mask.reshape(-1)
        pe = aggregate_pe(flat_labels[pe_flat], k[pe_flat], c[pe_flat], bases[pe_flat], o[pe_flat])
        q = qber_counts(pe)
        fm = frame_matrix(pe)
        compared = int(fm.sum())
        mismatched = int(compared - np.trace(fm))
        flips_m0 = int(fm[[0, 1, 2, 3], [2, 3, 0, 1]].sum() + fm[[0, 1, 2, 3], [3, 2, 1, 0]].sum())
        flips_m1 = int(fm[[0, 1, 2, 3], [1, 0, 3, 2]].sum() + fm[[0, 1, 2, 3], [3, 2, 1, 0]].sum())
        mac = "absent"
        if spec.authenticated:
            key = spec.mac_key or b"\x00" * 32
            r, s = wc_keys(key, f"{bundle_id}|{v}")
            mac = "ok" if wc_tag(k, r, s) == wc_tag(c, r, s) else "fail"
        frame = {
            "compared": compared, "mismatched": mismatched,
            "rate": mismatched / compared if compared else 0.0,
            "flip_rates": {"m0": flips_m0 / compared if compared else 0.0, "m1": flips_m1 / compared if compared else 0.0},
            "matrix": fm.tolist(), "mac": mac,
        }

        # Display sample: the first positions of key (bit 0, value 0).
        sample = []
        for j in range(min(SAMPLE_POSITIONS, Ld)):
            sample.append({"label": int(labels_d[0, 0, j]), "sent": int(sent[j]), "k": int(k[j]), "c": int(c[j]),
                           "basis": int(bases[j]), "outcome": int(o[j]), "pe": bool(pe_mask[0, 0, j])})

        pairs = N + 7 * params.bell_pairs_per_setting
        evidence[v] = LinkEvidence(
            link_id=spec.link_id, verifier_id=v, bell=bell, pe=pe, qber=q,
            detwirled=detwirl(pe), effective=effective(pe), frame=frame,
            hardware_time_ms=hardware.time_ms(pairs, spec.length_km), sample=sample,
        )
        ucbs.append(cp_upper(q["errors"], q["n"], params.delta_pe))

        keep = ~pe_mask
        kept_records[v] = (
            bases.reshape(shape_d)[keep].reshape(B, 2, L),
            o.reshape(shape_d)[keep].reshape(B, 2, L),
        )
        if art.get("harvested") is not None:
            # Map harvested flat positions to kept (b, v, j) coordinates for the counterfactual.
            h = art["harvested"]
            kept_index = np.full(N, -1, dtype=np.int64)
            kept_flat = keep.reshape(-1)
            kept_index[kept_flat] = np.arange(int(kept_flat.sum()))
            pos = kept_index[h["positions"]]
            ok = pos >= 0
            art["harvested"] = {"kept_positions": pos[ok], "basis": h["basis"][ok], "outcome": h["outcome"][ok]}
    timings["teleport_ms"] = (time.perf_counter() - t0) * 1000

    # Threshold design from the measured QBER upper bound.
    t0 = time.perf_counter()
    e_ucb = float(max(ucbs)) if ucbs else 0.0
    dsg = design_for(params, e_ucb)
    timings["design_ms"] = (time.perf_counter() - t0) * 1000

    # Symmetrization: each recipient forwards exactly L//2 kept positions per key.
    t0 = time.perf_counter()
    records = {}
    for v in recipients:
        fwd = _exact_k_mask(rs, (B, 2, L), L // 2)
        basis_k, out_k = kept_records[v]
        records[v] = VerifierRecords(basis=basis_k.astype(np.uint8), outcome=out_k.astype(np.uint8), fwd=fwd)
    timings["symmetrize_ms"] = (time.perf_counter() - t0) * 1000

    labels_kept = labels_d[~pe_mask].reshape(B, 2, L).astype(np.uint8)
    bundle = KeyBundle(
        bundle_id=bundle_id, group_id=group_id, signer_id=signer_id, recipients=tuple(recipients),
        params=params, labels=labels_kept, records=records, design=dsg.as_dict(), status="DISTRIBUTING",
    )
    timings["total_ms"] = (time.perf_counter() - t_start) * 1000
    return DistributionOutcome(
        bundle=bundle, evidence=evidence, design=dsg, e_ucb=e_ucb,
        qubits=N * len(recipients), bell_pairs=7 * params.bell_pairs_per_setting * len(recipients),
        timings=timings, plans=plans, artifacts=artifacts,
    )
