"""
sentinel/network.py
===================
Load the network topology (``config/network.yaml``) and engine settings
(``config/sentinel.yaml``), and build a :class:`~sentinel.world.World`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from sentinel.channels import normalise_specs
from sentinel.detection.config import DetectionConfig
from sentinel.protocol.link import HardwareModel, LinkSpec
from sentinel.protocol.params import params_for
from sentinel.world import GroupSpec, World

__all__ = ["CONFIG_DIR", "load_network", "load_settings", "build_world", "params_from_settings"]

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def load_network(path: Optional[Path] = None) -> dict:
    path = Path(path) if path else CONFIG_DIR / "network.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for link in data.get("links", []):
        link["baseline_channel"] = normalise_specs(link.get("baseline_channel") or [])
    return data


def load_settings(path: Optional[Path] = None) -> dict:
    path = Path(path) if path else CONFIG_DIR / "sentinel.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def params_from_settings(settings: dict, preset: Optional[str] = None, **overrides):
    preset = preset or settings.get("server", {}).get("active_preset", "standard")
    base = dict(settings.get("protocol", {}))
    base.pop("bundle_ttl_s", None)
    return params_for(preset, base=base, presets=settings.get("presets"), **overrides)


def build_world(network: Optional[dict] = None, settings: Optional[dict] = None, preset: Optional[str] = None,
                seed: Optional[int] = None, **kw: Any) -> World:
    network = network or load_network()
    settings = settings or load_settings()
    groups = {g["id"]: GroupSpec(g["id"], g["signer"], tuple(g["recipients"]), bool(g.get("hidden", False)))
              for g in network["groups"]}
    links = {}
    for l in network["links"]:
        if l.get("kind") != "quantum":
            continue
        links[l["id"]] = LinkSpec(l["id"], l["a"], l["b"], list(l.get("baseline_channel", [])),
                                  float(l.get("length_km", 0)), bool(l.get("authenticated_classical", False)),
                                  l.get("mac_key"))
    hw = settings.get("hardware_model", {})
    hardware = HardwareModel(float(hw.get("source_rate_hz", 1e7)), float(hw.get("fibre_loss_db_per_km", 0.2)),
                             float(hw.get("detector_efficiency", 0.9)))
    principals = {n["id"] for n in network["nodes"] if n.get("role") in ("signer", "verifier")}
    kw.setdefault("detection", DetectionConfig.from_dict(settings.get("detection")))
    return World(groups, links, params_from_settings(settings, preset), hardware=hardware, seed=seed,
                 principals=principals, **kw)
