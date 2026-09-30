"""
sentinel/sequential.py
======================
Sequential statistics: Wald's SPRT, Page's CUSUM and an EWMA.

- **SPRT** decides between two mismatch rates while reading tested positions
  one at a time, stopping as soon as the evidence is decisive. Verification
  uses it only to *reject early*; acceptance always needs the fixed test.
- **CUSUM** accumulates small persistent shifts in a per-link statistic
  (QBER, CHSH) that no single run would flag.
- **EWMA** is a smoothed trace for display.

No AI/ML is used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

__all__ = ["Sprt", "SprtResult", "Cusum", "Ewma"]


@dataclass
class SprtResult:
    decision: str            # 'reject' (H1), 'accept' (H0) or 'continue'
    n_used: int
    llr: float
    trace: list = field(default_factory=list)   # [(n, llr)] downsampled


class Sprt:
    """Wald's SPRT between H0: rate = p0 and H1: rate = p1 (> p0)."""

    def __init__(self, p0: float, p1: float, alpha: float = 1e-9, beta: float = 1e-6) -> None:
        if not (0 < p0 < p1 < 1):
            raise ValueError("require 0 < p0 < p1 < 1")
        self.p0, self.p1, self.alpha, self.beta = p0, p1, alpha, beta
        self.A = math.log((1 - beta) / alpha)
        self.B = math.log(beta / (1 - alpha))
        self.inc_mismatch = math.log(p1 / p0)
        self.inc_match = math.log((1 - p1) / (1 - p0))

    def run(self, mismatches: np.ndarray, early_accept: bool = True, trace_points: int = 0) -> SprtResult:
        """Process a boolean mismatch stream in order."""
        x = np.asarray(mismatches, dtype=bool)
        if x.size == 0:
            return SprtResult("continue", 0, 0.0, [])
        inc = np.where(x, self.inc_mismatch, self.inc_match)
        llr = np.cumsum(inc)
        up = np.nonzero(llr >= self.A)[0]
        down = np.nonzero(llr <= self.B)[0] if early_accept else np.array([], dtype=int)
        first_up = int(up[0]) if up.size else None
        first_down = int(down[0]) if down.size else None
        if first_up is not None and (first_down is None or first_up < first_down):
            decision, stop = "reject", first_up
        elif first_down is not None:
            decision, stop = "accept", first_down
        else:
            decision, stop = "continue", x.size - 1
        trace = []
        if trace_points:
            idx = np.unique(np.linspace(0, stop, min(trace_points, stop + 1)).astype(int))
            trace = [[int(i + 1), float(llr[i])] for i in idx]
        return SprtResult(decision, stop + 1, float(llr[stop]), trace)

    # -- Wald approximations --------------------------------------------------
    def _h(self, p: float) -> float:
        """Non-zero root h of p a^h + (1-p) b^h = 1 (a = p1/p0, b = (1-p1)/(1-p0))."""
        a, b = self.p1 / self.p0, (1 - self.p1) / (1 - self.p0)

        def f(h):
            return p * a ** h + (1 - p) * b ** h - 1.0

        drift = p * math.log(a) + (1 - p) * math.log(b)
        if abs(drift) < 1e-12:
            return 0.0
        # Root has the opposite sign to the drift.
        if drift < 0:
            lo, hi = 1e-9, 1.0
            while f(hi) < 0 and hi < 1e4:
                hi *= 2
            return brentq(f, lo, hi) if f(hi) > 0 else hi
        lo, hi = -1.0, -1e-9
        while f(lo) < 0 and lo > -1e4:
            lo *= 2
        return brentq(f, lo, hi) if f(lo) > 0 else lo

    def oc(self, p: float) -> float:
        """Operating characteristic: probability of accepting H0 at true rate p."""
        h = self._h(p)
        A_w, B_w = math.exp(self.A), math.exp(self.B)
        if abs(h) < 1e-12:
            return self.A / (self.A - self.B)
        try:
            num = A_w ** h - 1.0
            den = A_w ** h - B_w ** h
            return float(num / den)
        except OverflowError:
            return 1.0 if h > 0 else 0.0

    def asn(self, p: float) -> float:
        """Wald's approximation to the expected number of observations."""
        ez = p * self.inc_mismatch + (1 - p) * self.inc_match
        L = self.oc(p)
        if abs(ez) < 1e-12:
            ez2 = p * self.inc_mismatch ** 2 + (1 - p) * self.inc_match ** 2
            return float(-self.A * self.B / ez2)
        return float((L * self.B + (1 - L) * self.A) / ez)


class Cusum:
    """One-sided upper CUSUM: C_t = max(0, C_{t-1} + x_t - k); alarm when C_t > h."""

    def __init__(self, k: float, h: float, value: float = 0.0, n: int = 0, alarms: int = 0) -> None:
        self.k, self.h = float(k), float(h)
        self.value, self.n, self.alarms = float(value), int(n), int(alarms)

    def update(self, x: float, k: float | None = None, h: float | None = None) -> tuple[float, bool]:
        """Add one observation. ``k``/``h`` override the reference value and limit for this step."""
        k = self.k if k is None else k
        h = self.h if h is None else h
        self.value = max(0.0, self.value + float(x) - k)
        self.n += 1
        alarm = self.value > h
        if alarm:
            self.alarms += 1
        return self.value, alarm

    def reset(self) -> None:
        self.value = 0.0

    def state(self) -> dict:
        return {"k": self.k, "h": self.h, "value": self.value, "n": self.n, "alarms": self.alarms}

    @classmethod
    def from_state(cls, s: dict) -> "Cusum":
        return cls(s["k"], s["h"], s.get("value", 0.0), s.get("n", 0), s.get("alarms", 0))


class Ewma:
    """Exponentially weighted moving average."""

    def __init__(self, lam: float = 0.2, value: float | None = None) -> None:
        self.lam = float(lam)
        self.value = value

    def update(self, x: float) -> float:
        self.value = float(x) if self.value is None else self.lam * float(x) + (1 - self.lam) * self.value
        return self.value

    def state(self) -> dict:
        return {"lam": self.lam, "value": self.value}

    @classmethod
    def from_state(cls, s: dict) -> "Ewma":
        return cls(s.get("lam", 0.2), s.get("value"))
