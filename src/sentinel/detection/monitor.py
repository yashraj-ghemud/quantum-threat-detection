"""
sentinel/detection/monitor.py
=============================
Per-link temporal monitoring (D10).

A single distribution's effect floor deliberately ignores small shifts. A
persistent low-intensity attack adds a small shift *every* time, which
Page's CUSUM accumulates:

    C_t = max(0, C_{t-1} + (qber_t - qber_0) - k)      alarm when C_t > h
    D_t = max(0, D_{t-1} + (S_0 - S_t) - k_S)          alarm when D_t > h_S

After an alarm the statistic restarts at 0 (renewal CUSUM).
"""

from __future__ import annotations

import math

from sentinel.detection.baseline import LinkBaseline
from sentinel.detection.config import DetectionConfig
from sentinel.detection.findings import Finding
from sentinel.protocol.distribution import LinkEvidence
from sentinel.sequential import Cusum, Ewma

__all__ = ["LinkMonitor", "noise_aware_limits"]


def noise_aware_limits(q: float, n: int, q0: float, n0: int, k_cfg: float, h_cfg: float) -> tuple[float, float, float]:
    """(k, h, sigma) for a QBER CUSUM step: k >= 2 sigma and h >= 6 sigma of one run's noise."""
    se = math.hypot(math.sqrt(max(q * (1 - q), 1e-12) / max(n, 1)), math.sqrt(max(q0 * (1 - q0), 1e-12) / max(n0, 1)))
    return max(k_cfg, 2 * se), max(h_cfg, 6 * se), se


class LinkMonitor:
    def __init__(self, link_id: str, cfg: DetectionConfig, state: dict | None = None) -> None:
        self.link_id = link_id
        state = state or {}
        self.qber = Cusum.from_state(state["qber"]) if "qber" in state else Cusum(cfg.cusum_qber_k, cfg.cusum_qber_h)
        self.chsh = Cusum.from_state(state["chsh"]) if "chsh" in state else Cusum(cfg.cusum_chsh_k, cfg.cusum_chsh_h)
        self.ewma = Ewma.from_state(state["ewma"]) if "ewma" in state else Ewma(cfg.ewma_lambda)

    def state(self) -> dict:
        return {"qber": self.qber.state(), "chsh": self.chsh.state(), "ewma": self.ewma.state()}

    def reset(self) -> None:
        self.qber.reset()
        self.chsh.reset()

    def update(self, ev: LinkEvidence, base: LinkBaseline) -> tuple[Finding, dict]:
        # The reference value k and limit h never sit below the sampling noise of a
        # single run (k >= 2 sigma, h >= 6 sigma): otherwise honest noise alone drifts.
        q, q0 = ev.qber["rate"], base.qber["rate"]
        kq, hq, _ = noise_aware_limits(q, ev.qber["n"], q0, base.qber["n"], self.qber.k, self.qber.h)
        se_s = math.hypot(ev.bell.S_se, base.bell.S_se)
        ks, hs = max(self.chsh.k, 2 * se_s), max(self.chsh.h, 6 * se_s)
        cq, aq = self.qber.update(q - q0, kq, hq)
        cs, as_ = self.chsh.update(base.bell.S - ev.bell.S, ks, hs)
        ew = self.ewma.update(ev.qber["rate"])
        alarm = aq or as_
        # Page's restart rule: once a CUSUM signals, the alarm is handed to the incident and the
        # accumulator starts again from zero. A drift that persists re-alarms after its run length;
        # one that stopped does not keep flagging every honest bundle while the excess drains.
        if aq:
            self.qber.reset()
        if as_:
            self.chsh.reset()
        point = {"qber": ev.qber["rate"], "chsh": ev.bell.S, "fidelity": ev.bell.F, "cusum_qber": cq,
                 "cusum_chsh": cs, "ewma_qber": ew, "alarm": alarm, "h_qber": hq, "h_chsh": hs,
                 "k_qber": kq, "k_chsh": ks}
        which = [n for n, a in (("QBER", aq), ("CHSH", as_)) if a]
        f = Finding(
            id="D10.cusum", name="Temporal drift (CUSUM)", layer="temporal", link_id=self.link_id, fired=alarm,
            severity="MEDIUM" if alarm else "NONE",
            statistic={"name": "cusum_qber", "value": cq},
            evidence=(f"Persistent drift on {self.link_id}: {' and '.join(which)} CUSUM crossed its limit "
                      f"(QBER C = {cq:.4f} / h = {hq:.4f}, CHSH C = {cs:.3f} / h = {hs:.3f}). Each run alone "
                      f"was within tolerance; together they are not.") if alarm else
            f"QBER CUSUM {cq:.4f} / {hq:.4f}, CHSH CUSUM {cs:.3f} / {hs:.3f}: no persistent drift.",
            data=point,
        )
        return f, point
