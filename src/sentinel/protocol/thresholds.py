"""
sentinel/protocol/thresholds.py
===============================
Threshold designer: choose the acceptance thresholds ``s_a`` (first
recipient) and ``s_v`` (transfer) and report the error probabilities they
achieve.

All quantities are exact binomial / hypergeometric tails:

- **Robustness** (honest rejected): a set with ``n`` tested positions and
  honest error rate ``e`` fails when ``Bin(n, e) > floor(s_a n)``.
- **Forgery** (per unseen key): a forger with minimal mismatch rate ``p_f``
  (1/3 for the optimal insider) passes when ``Bin(n, p_f) <= floor(s_v n)``.
- **Repudiation** (per key): a dishonest signer needs one copy whose random
  halves split so that the first recipient's half passes ``s_a`` while the
  transferee's half fails ``s_v`` (hypergeometric split tail).

Tested counts per set are random, ``n ~ Bin(floor(L/2), 1/3)``, so the
designer picks ``n_min`` from that distribution's quantile and reports the
**maximum** tail over every ``n`` in ``[n_min, floor(L/2)]``.

No AI/ML is used.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy import stats as _st

from sentinel.stats import chernoff_lower_tail, hypergeom_split_tail

__all__ = ["ThresholdDesign", "design", "design_for", "repudiation_bound", "min_tested", "pmf_series"]

_EPS_TINY = 1e-300


@dataclass
class ThresholdDesign:
    L: int
    digest_bits: int
    e_ucb: float
    p_forge: float
    n_nom: int
    n_min: int
    c_a: int
    c_v: int
    s_a: float
    s_v: float
    feasible: bool
    eps_rob_msg: float
    eps_rob_set: float
    eps_inconclusive: float
    eps_forge_key: float
    eps_forge_chernoff: float
    eps_rep_key: float
    eps_rep_msg: float
    targets: dict = field(default_factory=dict)
    meets_targets: dict = field(default_factory=dict)
    L_min: int | None = None
    sprt: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                d[k] = None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ThresholdDesign":
        fields = cls.__dataclass_fields__  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in fields})

    def accept_count(self, n: int, transfer: bool = False) -> int:
        """Largest mismatch count accepted in a set with n tested positions."""
        s = self.s_v if transfer else self.s_a
        return int(math.floor(s * n + 1e-9))


def min_tested(L: int, digest_bits: int, budget: float) -> tuple[int, float]:
    """Largest n_min with 4*digest_bits*P(Bin(L//2, 1/3) < n_min) <= budget."""
    half = L // 2
    q = budget / (4.0 * digest_bits)
    n = int(_st.binom.ppf(q, half, 1.0 / 3.0))
    # ppf gives the smallest n with cdf(n) >= q; P(N < n) = cdf(n-1) < q.
    n = max(1, n)
    while n > 1 and _st.binom.cdf(n - 1, half, 1.0 / 3.0) > q:
        n -= 1
    p_short = float(_st.binom.cdf(n - 1, half, 1.0 / 3.0)) if n > 0 else 0.0
    return n, 4.0 * digest_bits * p_short


def _max_rob_tail(n_lo: int, n_hi: int, s_a: float, e: float) -> float:
    ns = np.arange(n_lo, n_hi + 1)
    cs = np.floor(s_a * ns + 1e-9)
    return float(np.max(_st.binom.sf(cs, ns, e)))


def _max_forge_tail(n_lo: int, n_hi: int, s_v: float, p: float) -> float:
    ns = np.arange(n_lo, n_hi + 1)
    cs = np.floor(s_v * ns + 1e-9)
    return float(np.max(_st.binom.cdf(cs, ns, p)))


def repudiation_bound(n_min: int, s_a: float, s_v: float) -> float:
    """Worst-case per-copy probability that the halves split into accept / reject.

    Model: a copy has ``N = 2 n_min`` tested positions containing ``K`` errors
    chosen by the dishonest signer; a uniformly random half (``n1 = n_min``)
    goes to the first recipient. Returns ``max_K P(X <= floor(s_a n1) and
    K - X > floor(s_v n1))``.
    """
    N = 2 * n_min
    n1 = n_min
    a = int(math.floor(s_a * n1 + 1e-9))
    b = int(math.floor(s_v * n1 + 1e-9))
    lo = b + 1
    hi = min(N, a + (N - n1))
    if hi < lo:
        return 0.0
    K = np.arange(lo, hi + 1)
    # P(X <= a and K - X > b) = P(X <= min(a, K - b - 1))
    upper = np.minimum(a, K - b - 1)
    probs = _st.hypergeom.cdf(upper, N, K, n1)
    return float(np.max(np.where(upper >= 0, probs, 0.0)))


def _core(L: int, e_ucb: float, digest_bits: int, eps_rob_target: float, eps_forge_target: float,
          p_forge: float, sprt_alpha: float, delta_pe: float) -> dict:
    half = L // 2
    n_nom = L // 6
    n_min, eps_inc = min_tested(L, digest_bits, 0.1 * eps_rob_target)
    n_min = max(n_min, 1)
    budget = eps_rob_target - eps_inc - 2 * digest_bits * sprt_alpha - delta_pe
    if budget <= 0:
        budget = 0.5 * eps_rob_target
    per_set = budget / (2 * digest_bits)
    e = min(max(e_ucb, 1e-9), 0.5)

    # Smallest c_a with P(Bin(n_min, e) > c_a) <= per_set, then check every n.
    c_a = int(_st.binom.isf(per_set, n_min, e)) if per_set < 1 else 0
    c_a = max(0, min(c_a, n_min))
    while c_a > 0 and _st.binom.sf(c_a - 1, n_min, e) <= per_set:
        c_a -= 1
    while c_a < n_min and _max_rob_tail(n_min, half, c_a / n_min, e) > per_set:
        c_a += 1
    s_a = c_a / n_min
    eps_rob_set = _max_rob_tail(n_min, half, s_a, e)

    # Largest c_v with max_n P(Bin(n, p_f) <= floor(s_v n)) <= eps_forge_target.
    c_v = int(_st.binom.ppf(eps_forge_target, n_min, p_forge))
    c_v = max(-1, min(c_v, n_min))
    while c_v >= 0 and _st.binom.cdf(c_v, n_min, p_forge) > eps_forge_target:
        c_v -= 1
    while c_v >= 0 and _max_forge_tail(n_min, half, c_v / n_min, p_forge) > eps_forge_target:
        c_v -= 1
    s_v = max(c_v, 0) / n_min
    eps_forge = _max_forge_tail(n_min, half, s_v, p_forge) if c_v >= 0 else 0.0

    feasible = c_v >= 0 and c_a < c_v
    eps_rob_msg = min(1.0, 2 * digest_bits * eps_rob_set + eps_inc + 2 * digest_bits * sprt_alpha + delta_pe)
    return {
        "n_nom": n_nom, "n_min": n_min, "c_a": c_a, "c_v": c_v, "s_a": s_a, "s_v": s_v,
        "feasible": feasible, "eps_rob_msg": eps_rob_msg, "eps_rob_set": eps_rob_set,
        "eps_inconclusive": eps_inc, "eps_forge_key": eps_forge,
        "eps_forge_chernoff": chernoff_lower_tail(n_min, p_forge, s_v) if feasible else 1.0,
    }


def design(L: int, e_ucb: float, digest_bits: int = 256, eps_rob_target: float = 1e-9,
           eps_forge_target: float = 1e-6, eps_rep_target: float = 1e-6, p_forge: float = 1.0 / 3.0,
           sprt_alpha: float = 1e-13, sprt_beta: float = 1e-6, delta_pe: float = 1e-10,
           find_L_min: bool = True, with_repudiation: bool = True) -> ThresholdDesign:
    """Design thresholds for keys of length L at a measured honest error bound e_ucb."""
    core = _core(L, e_ucb, digest_bits, eps_rob_target, eps_forge_target, p_forge, sprt_alpha, delta_pe)
    rep_key = rep_msg = float("nan")
    if with_repudiation and core["feasible"]:
        rep_copy = repudiation_bound(core["n_min"], core["s_a"], core["s_v"])
        rep_key = min(1.0, 2 * rep_copy)
        rep_msg = min(1.0, digest_bits * rep_key)
    elif with_repudiation:
        rep_key = rep_msg = 1.0

    meets = {
        "robustness": core["feasible"] and core["eps_rob_msg"] <= eps_rob_target * (1 + 1e-9),
        "forgery": core["feasible"] and core["eps_forge_key"] <= eps_forge_target * (1 + 1e-9),
        "repudiation": (not math.isnan(rep_key)) and rep_key <= eps_rep_target,
    }
    L_min = None
    if find_L_min and not (meets["robustness"] and meets["forgery"]):
        L_min = _search_L_min(L, e_ucb, digest_bits, eps_rob_target, eps_forge_target, p_forge, sprt_alpha, delta_pe)

    sprt = {}
    if core["feasible"]:
        p0 = min(max(e_ucb, 1e-6), p_forge * 0.9)
        sprt = {"p0": p0, "p1": p_forge, "alpha": sprt_alpha, "beta": sprt_beta,
                "A": math.log((1 - sprt_beta) / sprt_alpha), "B": math.log(sprt_beta / (1 - sprt_alpha))}

    return ThresholdDesign(
        L=L, digest_bits=digest_bits, e_ucb=float(e_ucb), p_forge=p_forge,
        n_nom=core["n_nom"], n_min=core["n_min"], c_a=core["c_a"], c_v=core["c_v"],
        s_a=core["s_a"], s_v=core["s_v"], feasible=core["feasible"],
        eps_rob_msg=core["eps_rob_msg"], eps_rob_set=core["eps_rob_set"], eps_inconclusive=core["eps_inconclusive"],
        eps_forge_key=core["eps_forge_key"], eps_forge_chernoff=core["eps_forge_chernoff"],
        eps_rep_key=rep_key, eps_rep_msg=rep_msg,
        targets={"eps_rob": eps_rob_target, "eps_forge": eps_forge_target, "eps_rep": eps_rep_target},
        meets_targets=meets, L_min=L_min, sprt=sprt,
    )


def _search_L_min(L: int, e: float, bits: int, er: float, ef: float, pf: float, sa: float, dp: float) -> int | None:
    def ok(Lc: int) -> bool:
        c = _core(Lc, e, bits, er, ef, pf, sa, dp)
        return c["feasible"] and c["eps_rob_msg"] <= er * (1 + 1e-9) and c["eps_forge_key"] <= ef * (1 + 1e-9)

    hi = max(64, L)
    while not ok(hi):
        hi *= 2
        if hi > 1 << 17:
            return None
    lo = max(64, hi // 2)
    if ok(lo):
        return lo
    while hi - lo > 16:
        mid = (lo + hi) // 2
        if ok(mid):
            hi = mid
        else:
            lo = mid
    return hi


def pmf_series(n: int, p: float, mass: float = 1e-12) -> dict:
    """Trimmed PMF of Bin(n, p) for plotting."""
    ks = np.arange(0, n + 1)
    pmf = _st.binom.pmf(ks, n, p)
    keep = pmf >= mass
    if not keep.any():
        keep[int(round(n * p))] = True
    idx = np.nonzero(keep)[0]
    lo, hi = int(idx[0]), int(idx[-1])
    return {"n": n, "p": p, "k0": lo, "pmf": [float(x) for x in pmf[lo:hi + 1]]}


def design_for(params, e_ucb: float, **kw) -> ThresholdDesign:
    """Design thresholds using a :class:`ProtocolParams` bundle of targets."""
    return design(
        params.L, e_ucb, digest_bits=params.digest_bits, eps_rob_target=params.eps_rob_target,
        eps_forge_target=params.eps_forge_target, eps_rep_target=params.eps_rep_target,
        p_forge=params.p_forge_insider, sprt_alpha=params.sprt_alpha, sprt_beta=params.sprt_beta,
        delta_pe=params.delta_pe, **kw,
    )
