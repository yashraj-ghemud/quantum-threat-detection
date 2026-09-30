"""
server/settings.py
==================
Server settings: environment variables over ``config/sentinel.yaml``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from sentinel.network import CONFIG_DIR, load_settings

__all__ = ["Settings", "ROOT"]

ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 8000
    data_dir: Path = ROOT / "data"
    env: str = "development"
    preset: str = "standard"
    autostart_traffic: bool = True
    allow_tamper_demo: bool = True
    cors_origins: list = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    seed: int | None = None
    skip_calibration: bool = False
    api_key: str | None = None
    log_level: str = "INFO"
    compute_workers: int = 2
    traffic_rate_per_min: int = 12
    reservoir_target: int = 3
    block_max_txs: int = 16
    block_max_age_s: float = 8.0
    idle_pause_s: float = 120.0
    heavy_rate_capacity: float = 12.0   # burst of heavy (compute) requests per client
    heavy_rate_refill: float = 1.0      # tokens per second
    background: bool = True          # start workers (tests switch this off)
    session_report_retention: int = 600
    web_dist: Path = ROOT / "web" / "dist"
    config_dir: Path = CONFIG_DIR
    yaml: dict = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "qveris.db"

    @property
    def keystore_dir(self) -> Path:
        return self.data_dir / "keystore"

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        y = load_settings()
        srv = y.get("server", {})
        env = os.environ.get("QVERIS_ENV", "development").lower()
        s = cls(
            host=os.environ.get("QVERIS_HOST", "0.0.0.0"),
            port=int(os.environ.get("QVERIS_PORT", "8000")),
            data_dir=Path(os.environ.get("QVERIS_DATA_DIR", str(ROOT / "data"))),
            env=env,
            preset=os.environ.get("QVERIS_PRESET", srv.get("active_preset", "standard")),
            autostart_traffic=_bool("QVERIS_AUTOSTART_TRAFFIC", True),
            allow_tamper_demo=_bool("QVERIS_ALLOW_TAMPER_DEMO", env != "production"),
            cors_origins=[o.strip() for o in os.environ.get(
                "QVERIS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()],
            seed=int(os.environ["QVERIS_SEED"]) if os.environ.get("QVERIS_SEED") else None,
            skip_calibration=_bool("QVERIS_SKIP_CALIBRATION", False),
            api_key=os.environ.get("QVERIS_API_KEY") or None,
            log_level=os.environ.get("QVERIS_LOG_LEVEL", "INFO"),
            compute_workers=int(srv.get("compute_workers", 2)),
            traffic_rate_per_min=int(srv.get("traffic_rate_per_min", 12)),
            reservoir_target=int(srv.get("reservoir_target", 3)),
            block_max_txs=int(srv.get("block_max_txs", 16)),
            block_max_age_s=float(srv.get("block_max_age_s", 8)),
            heavy_rate_capacity=float(os.environ.get("QVERIS_HEAVY_BURST", srv.get("heavy_rate_capacity", 12))),
            heavy_rate_refill=float(os.environ.get("QVERIS_HEAVY_REFILL", srv.get("heavy_rate_refill", 1.0))),
            yaml=y,
        )
        for k, v in overrides.items():
            setattr(s, k, v)
        return s
