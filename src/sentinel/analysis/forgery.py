"""
sentinel/analysis/forgery.py
============================
Forgery-probability analysis.

1. **Exact and Chernoff curves** of the per-key forgery probability against
   key length L, for the external blind forger (mismatch 1/2, must pass both
   sets) and the optimal insider (mismatch 1/3, passes the forwarded set for
   free, must pass the transferee's own set).
2. **Monte Carlo** with the real engine at small L, where passes are frequent
   enough to count, so the formulas are checked against actual verification.
3. **Insider optimality**: a search over single-copy measurement directions
   and every outcome-to-label map, confirming nothing beats mismatch 1/3.
4. **Message level**: probability of forging a message whose digest differs
   in k bits.
"""

from __future__ import annotations

import math
import time

import numpy as np

from sentinel.protocol.distribution import distribute
from sentinel.protocol.encoding import Envelope
from sentinel.protocol.params import params_for
from sentinel.protocol.signing import Signature
from sentinel.protocol.verification import verify
from sentinel.rng import RandomSource
from sentinel.states import BASIS_OF, BIT_OF, BLOCH
from sentinel.stats import binom_cdf, chernoff_lower_tail, clopper_pearson

__all__ = ["exact_curves", "monte_carlo", "insider_optimum", "message_level", "run_forgery_analysis"]


def _n(L: int) -> int:
    return max(1, L // 6)


def _set_pass(L: int, s_v: float, p: float, n_min: int = 1) -> float:
    """P(a verification set passes) with n ~ Bin(L/2, 1/3) tested positions and mismatch rate p."""
    from scipy import stats as _st

    half = L // 2
    ns = np.arange(0, half + 1)
    w = _st.binom.pmf(ns, half, 1 / 3)
    cs = np.floor(s_v * ns + 1e-9)
    ok = ns >= n_min
    return float(np.sum(w[ok] * _st.binom.cdf(cs[ok], ns[ok], p)))


def exact_curves(Ls, s_v: float = 0.2, e: float = 0.012) -> dict:
    """Exact per-key forgery probability.

    External blind forger: mismatch 1/2 on both sets, which must both pass.
    Optimal insider: the forwarded set passes at honest noise; the transferee's
    own set has mismatch 1/3 + (2/3) e (1 - e) (both copies carry noise).
    Tested counts per set are random, n ~ Bin(L/2, 1/3); the Chernoff column is
    the bound at the nominal n = L/6 for reference.
    """
    p_ins = 1 / 3 + (2 / 3) * e * (1 - e)
    out = {"L": [int(L) for L in Ls], "n": [], "external": {"exact": [], "chernoff": []},
           "insider": {"exact": [], "chernoff": []}, "s_v": s_v, "e": e, "p_insider": p_ins}
    for L in Ls:
        n = _n(L)
        ext = _set_pass(L, s_v, 0.5) ** 2
        ins = _set_pass(L, s_v, p_ins) * _set_pass(L, s_v, e)
        out["n"].append(n)
        out["external"]["exact"].append(ext)
        out["external"]["chernoff"].append(chernoff_lower_tail(n, 0.5, s_v) ** 2)
        out["insider"]["exact"].append(ins)
        out["insider"]["chernoff"].append(chernoff_lower_tail(n, p_ins, s_v))
    return out


def _links():
    from sentinel.protocol.link import LinkSpec

    base = [{"type": "depolarizing", "p": 0.012}, {"type": "amplitude_damping", "gamma": 0.004}]
    return {v: LinkSpec(f"alice-{v}", "alice", v, list(base), 20.0) for v in ("bob", "charlie")}


def monte_carlo(Ls, trials_per_L: int = 2000, s_v: float = 0.2, seed: int = 7, progress=None, cancel=None) -> list:
    """Per-key forgery pass rates measured through the real verification code."""
    rs = RandomSource(seed)
    links = _links()
    rows = []
    total = len(Ls) * 2
    step = 0
    for L in Ls:
        params = params_for("analysis", L=int(L), f_pe=0.1)
        for strategy in ("external", "insider"):
            if cancel is not None and cancel.is_set():
                return rows
            passes = trials = 0
            while trials < trials_per_L:
                out = distribute("g", "alice", ("bob", "charlie"), links, params, rs)
                b = out.bundle
                B = params.digest_bits
                bits = np.zeros(B, dtype=np.uint8)
                env = Envelope("g", "alice", ("bob", "charlie"), b.bundle_id, 1, 0.0, "00", "forged")
                # Forge every key (i, 1) whose labels were never revealed (the signer revealed (i, 0)).
                forged_bits = 1 - bits
                if strategy == "external":
                    declared = rs.labels(B * params.L).reshape(B, params.L)
                    view = b.view_for("bob")
                else:
                    ins = b.view_for("bob")
                    declared = (2 * ins.own_basis[:, 1, :] + ins.own_outcome[:, 1, :]).astype(np.uint8)
                    view = b.view_for("charlie")
                sig = Signature(env, forged_bits, declared, oracle=True)
                rep = verify(view, sig, s_v, 1, "transfer" if strategy == "insider" else "first", None)
                passes += int(rep.passed.sum())
                trials += B
            lo, hi = clopper_pearson(passes, trials, 0.05)
            rows.append({"L": int(L), "n": _n(L), "strategy": strategy, "trials": trials, "passes": passes,
                         "rate": passes / trials, "ci": [lo, hi]})
            step += 1
            if progress:
                progress(step / total, f"Monte Carlo L={L} {strategy}: {passes}/{trials}")
    return rows


def _fibonacci_sphere(n: int) -> np.ndarray:
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    theta = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)


def _mismatch_table(dirs: np.ndarray) -> np.ndarray:
    """Expected tested-mismatch for every direction and every (+, -) -> (label, label) map.

    Returns shape (n_dirs, 6, 6): [d, label_if_plus, label_if_minus].
    """
    p_plus = (1 + dirs @ BLOCH.T) / 2                         # (d, true label)
    # Mismatch at the transferee if it holds the true state and tests declared label l.
    sign = np.where(BIT_OF == 0, 1.0, -1.0)
    mism = np.zeros((6, 6))
    for t in range(6):
        for l in range(6):
            mism[t, l] = (1 - sign[l] * BLOCH[t, BASIS_OF[l]]) / 2
    # E[mismatch] = mean_t [ P(+|t) mism[t, lp] + P(-|t) mism[t, lm] ]
    a = np.einsum("dt,tl->dl", p_plus, mism) / 6.0            # (d, lp)
    b = np.einsum("dt,tl->dl", 1 - p_plus, mism) / 6.0        # (d, lm)
    return a[:, :, None] + b[:, None, :]


def insider_optimum(n_dirs: int = 4000, grid: tuple = (36, 72)) -> dict:
    dirs = _fibonacci_sphere(n_dirs)
    table = _mismatch_table(dirs)
    best = table.reshape(n_dirs, -1).min(axis=1)
    k = int(np.argmin(best))
    lp, lm = np.unravel_index(int(np.argmin(table[k])), (6, 6))
    lat = np.linspace(-90, 90, grid[0])
    lon = np.linspace(-180, 180, grid[1])
    la, lo = np.meshgrid(np.radians(lat), np.radians(lon), indexing="ij")
    gdirs = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=-1).reshape(-1, 3)
    gbest = _mismatch_table(gdirs).reshape(gdirs.shape[0], -1).min(axis=1).reshape(grid)
    return {"min": float(best.min()), "argmin_direction": dirs[k].tolist(), "labels": [int(lp), int(lm)],
            "grid_points": n_dirs, "maps_per_direction": 36, "external_reference": 0.5,
            "sphere": {"lat": lat.tolist(), "lon": lon.tolist(), "values": gbest.tolist()}}


def message_level(eps_key: float, kmax: int = 8, digest_bits: int = 256) -> dict:
    ks = list(range(1, kmax + 1))
    log10 = [k * math.log10(max(eps_key, 1e-300)) for k in ks]
    # A random second message differs in ~Bin(256, 1/2) bits; its log10 forgery probability is ~128 x log10(eps).
    return {"k": ks, "log10_eps": log10, "random_message_log10_eps": (digest_bits / 2) * math.log10(max(eps_key, 1e-300))}


def run_forgery_analysis(params: dict, progress=None, cancel=None) -> dict:
    t0 = time.time()
    s_v = float(params.get("s_v", 0.2))
    Ls = [int(x) for x in params.get("L_grid", [32, 64, 128, 256, 512, 1024, 2048, 4096])]
    mc_Ls = [int(x) for x in params.get("mc_L", [32, 48, 64, 96, 128])]
    trials = int(params.get("mc_trials", 2000))
    # The honest error rate enters the insider's mismatch; measure it, do not assume it.
    from sentinel.detection.baseline import calibrate_link

    e = calibrate_link(_links()["bob"], RandomSource(int(params.get("seed", 7)) + 1), 200_000, 2000).qber["rate"]
    curves = exact_curves(Ls, s_v, e)
    if progress:
        progress(0.05, "exact curves")
    mc = monte_carlo(mc_Ls, trials, s_v, int(params.get("seed", 7)),
                     (lambda f, m: progress(0.05 + 0.8 * f, m)) if progress else None, cancel)
    # Exact predictions at the MC lengths for overlay.
    mc_exact = exact_curves(mc_Ls, s_v, e)
    opt = insider_optimum(int(params.get("directions", 4000)))
    if progress:
        progress(0.95, "insider optimum")
    ref_L = int(params.get("reference_L", 4096))
    ref = exact_curves([ref_L], s_v, e)
    msg = message_level(ref["insider"]["exact"][0])
    return {"curves": curves, "mc": mc, "mc_exact": mc_exact, "insider_optimum": opt,
            "message_level": {**msg, "reference_L": ref_L, "eps_key": ref["insider"]["exact"][0]},
            "params": {"s_v": s_v, "L_grid": Ls, "mc_L": mc_Ls, "mc_trials": trials, "measured_e": e},
            "duration_s": time.time() - t0}
