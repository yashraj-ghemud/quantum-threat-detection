"""
sentinel/protocol/params.py
===========================
Protocol parameters and presets.

The defaults mirror ``config/sentinel.yaml``; the server loads that file and
builds :class:`ProtocolParams` from it, so the YAML is the single place an
operator changes them.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping

__all__ = ["ProtocolParams", "PRESETS", "params_for", "ParamsError"]


class ParamsError(ValueError):
    """Invalid protocol parameters."""


@dataclass(frozen=True)
class ProtocolParams:
    preset: str = "standard"
    digest_bits: int = 256
    L: int = 4096
    f_pe: float = 0.10
    bell_pairs_per_setting: int = 2000
    eps_rob_target: float = 1e-9
    eps_forge_target: float = 1e-6
    eps_rep_target: float = 1e-6
    delta_pe: float = 1e-10
    delta_bell: float = 1e-5
    p_forge_insider: float = 1.0 / 3.0
    freshness_window_s: float = 120.0
    sprt_alpha: float = 1e-13
    sprt_beta: float = 1e-6
    analysis_only: bool = False

    # -- derived -------------------------------------------------------------
    @property
    def L_dist(self) -> int:
        """Positions distributed per key (kept + parameter estimation)."""
        return int(math.ceil(self.L / (1.0 - self.f_pe)))

    @property
    def n_pe(self) -> int:
        """Parameter-estimation positions per key."""
        return self.L_dist - self.L

    @property
    def n_keys(self) -> int:
        return 2 * self.digest_bits

    @property
    def n_nom(self) -> int:
        """Nominal tested positions per verification set (L/2 positions x 1/3 basis match)."""
        return self.L // 6

    def qubits_per_recipient(self) -> int:
        return self.digest_bits * 2 * self.L_dist

    def qubits(self, n_recipients: int = 2) -> int:
        return self.qubits_per_recipient() * n_recipients

    def bell_pairs(self, n_recipients: int = 2) -> int:
        return 7 * self.bell_pairs_per_setting * n_recipients

    # -- validation ----------------------------------------------------------
    def validate(self) -> "ProtocolParams":
        if self.digest_bits not in (32, 64, 128, 256):
            raise ParamsError("digest_bits must be one of 32, 64, 128, 256")
        if self.digest_bits != 256 and not self.analysis_only:
            raise ParamsError("digest_bits below 256 is allowed only for analysis runs")
        min_L = 16 if self.analysis_only else 64
        if not (min_L <= self.L <= 16384):
            raise ParamsError(f"L must be in [{min_L}, 16384]")
        if not (0.02 <= self.f_pe <= 0.5):
            raise ParamsError("f_pe must be in [0.02, 0.5]")
        if not (100 <= self.bell_pairs_per_setting <= 50000):
            raise ParamsError("bell_pairs_per_setting must be in [100, 50000]")
        for name in ("eps_rob_target", "eps_forge_target", "eps_rep_target", "delta_pe", "delta_bell",
                     "sprt_alpha", "sprt_beta"):
            v = getattr(self, name)
            if not (0 < v < 1):
                raise ParamsError(f"{name} must be in (0, 1)")
        if not (5 <= self.freshness_window_s <= 3600):
            raise ParamsError("freshness_window_s must be in [5, 3600]")
        return self

    def with_(self, **kw) -> "ProtocolParams":
        return replace(self, **kw).validate()

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update({"L_dist": self.L_dist, "n_pe": self.n_pe, "n_keys": self.n_keys,
                  "n_nom": self.n_nom,
                  "qubits": self.qubits(), "bell_pairs": self.bell_pairs()})
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ProtocolParams":
        fields = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in fields}).validate()


#: Built-in presets. The server overlays ``config/sentinel.yaml`` on top.
PRESETS: dict[str, dict] = {
    "demo": {"L": 1024, "bell_pairs_per_setting": 1000,
             "eps_rob_target": 1e-6, "eps_forge_target": 1e-4, "eps_rep_target": 1e-3,
             "delta_pe": 1e-8, "sprt_alpha": 1e-11},
    "standard": {"L": 4096, "bell_pairs_per_setting": 2000,
                 "eps_rob_target": 1e-9, "eps_forge_target": 1e-6, "eps_rep_target": 1e-6,
                 "delta_pe": 1e-10, "sprt_alpha": 1e-13},
    "high": {"L": 8192, "bell_pairs_per_setting": 4000,
             "eps_rob_target": 1e-12, "eps_forge_target": 1e-12, "eps_rep_target": 1e-12,
             "delta_pe": 1e-14, "sprt_alpha": 1e-17},
    "analysis": {"L": 1024, "bell_pairs_per_setting": 1000, "digest_bits": 32, "analysis_only": True, "f_pe": 0.25,
                 "eps_rob_target": 1e-6, "eps_forge_target": 1e-3, "eps_rep_target": 1e-3,
                 "delta_pe": 1e-8, "sprt_alpha": 1e-10},
}


def params_for(preset: str = "standard", base: Mapping[str, Any] | None = None,
               presets: Mapping[str, Mapping] | None = None, **overrides) -> ProtocolParams:
    """Build parameters for a preset, with optional base settings and overrides."""
    table = dict(PRESETS)
    if presets:
        table.update({k: dict(v) for k, v in presets.items()})
    if preset not in table:
        raise ParamsError(f"unknown preset {preset!r}")
    d: dict = {}
    if base:
        d.update(base)
    d.update(table[preset])
    d.update(overrides)
    d["preset"] = preset
    return ProtocolParams.from_dict(d)
