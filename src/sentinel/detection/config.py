"""
sentinel/detection/config.py
============================
Detection configuration (mirrors ``config/sentinel.yaml -> detection``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

__all__ = ["DetectionConfig"]


@dataclass
class DetectionConfig:
    alpha_family: float = 1e-6
    enforce: bool = True
    floor_chsh_drop: float = 0.10
    floor_fidelity_drop: float = 0.02
    floor_qber_rise: float = 0.01
    floor_tomography: float = 0.04
    floor_consistency: float = 0.01
    cusum_qber_k: float = 0.0025
    cusum_qber_h: float = 0.015
    cusum_chsh_k: float = 0.02
    cusum_chsh_h: float = 0.12
    ewma_lambda: float = 0.2
    calibration_pe_samples: int = 400_000
    calibration_bell_per_setting: int = 20_000

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "DetectionConfig":
        d = d or {}
        flat = dict(d)
        floors = flat.pop("floors", None) or {}
        cusum = flat.pop("cusum", None) or {}
        cal = flat.pop("calibration", None) or {}
        mapping = {
            "chsh_drop": "floor_chsh_drop", "fidelity_drop": "floor_fidelity_drop", "qber_rise": "floor_qber_rise",
            "tomography_max_dev": "floor_tomography", "consistency": "floor_consistency",
        }
        for k, v in floors.items():
            if k in mapping:
                flat[mapping[k]] = v
        for k, v in cusum.items():
            key = {"qber_k": "cusum_qber_k", "qber_h": "cusum_qber_h", "chsh_k": "cusum_chsh_k",
                   "chsh_h": "cusum_chsh_h", "ewma_lambda": "ewma_lambda"}.get(k)
            if key:
                flat[key] = v
        if "pe_samples" in cal:
            flat["calibration_pe_samples"] = cal["pe_samples"]
        if "bell_pairs_per_setting" in cal:
            flat["calibration_bell_per_setting"] = cal["bell_pairs_per_setting"]
        fields = cls.__dataclass_fields__  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in flat.items() if k in fields})

    def validate(self) -> "DetectionConfig":
        if not (1e-12 <= self.alpha_family <= 1e-2):
            raise ValueError("alpha_family must be in [1e-12, 1e-2]")
        for name in ("floor_chsh_drop", "floor_fidelity_drop", "floor_qber_rise", "floor_tomography",
                     "floor_consistency", "cusum_qber_k", "cusum_qber_h", "cusum_chsh_k", "cusum_chsh_h"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if not (0 < self.ewma_lambda <= 1):
            raise ValueError("ewma_lambda must be in (0, 1]")
        return self
