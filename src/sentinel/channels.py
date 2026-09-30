"""
sentinel/channels.py
====================
Single-qubit quantum channel library.

Every channel is built from explicit Kraus operators, so complete positivity
is structural, and its Pauli transfer matrix is derived from those operators
(never written by hand). Channels are specified as plain dictionaries so they
can travel through the API and the database unchanged::

    {"type": "depolarizing", "p": 0.02}
    {"type": "dephasing", "p": 0.2, "axis": "z"}
    {"type": "rotation", "axis": [0, 0, 1], "theta": 0.4}

A *list* of specs is a composite channel applied in order (first element
first). ``compose([])`` is the identity.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from sentinel.linalg import I2, X, Y, Z, kraus_to_ptm, ptm_affine, su2_rotation

__all__ = [
    "Channel",
    "ChannelSpecError",
    "CHANNEL_TYPES",
    "channel_from_spec",
    "compose",
    "normalise_spec",
    "normalise_specs",
    "spec_key",
]

_AXES = {"x": np.array([1.0, 0, 0]), "y": np.array([0, 1.0, 0]), "z": np.array([0, 0, 1.0])}
_PAULI_OF_AXIS = {"x": X, "y": Y, "z": Z}


class ChannelSpecError(ValueError):
    """Raised for an invalid channel specification."""


@dataclass(frozen=True, eq=False)
class Channel:
    """An immutable single-qubit CPTP channel."""

    name: str
    params: dict
    kraus: tuple
    ptm: np.ndarray = field(repr=False)

    @property
    def affine(self) -> tuple[np.ndarray, np.ndarray]:
        """``(M, c)`` such that ``r -> M r + c``."""
        return ptm_affine(self.ptm)

    def apply_bloch(self, r: Sequence[float]) -> np.ndarray:
        M, c = self.affine
        return M @ np.asarray(r, dtype=float) + c

    def to_spec(self) -> dict:
        return {"type": self.name, **self.params}


# ---------------------------------------------------------------------------
# Parameter schema (served by the API so the UI can render controls)
# ---------------------------------------------------------------------------

CHANNEL_TYPES: dict[str, dict[str, Any]] = {
    "identity": {"label": "Identity", "params": [], "description": "No change."},
    "depolarizing": {
        "label": "Depolarizing",
        "params": [{"name": "p", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "default": 0.1}],
        "description": "rho -> (1-p) rho + p I/2. Shrinks the Bloch sphere uniformly.",
    },
    "dephasing": {
        "label": "Dephasing",
        "params": [
            {"name": "p", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "default": 0.2},
            {"name": "axis", "type": "enum", "options": ["x", "y", "z"], "default": "z"},
        ],
        "description": "rho -> (1-p) rho + p s rho s for the Pauli s of the axis. Squashes the sphere onto that axis.",
    },
    "bit_flip": {
        "label": "Bit flip",
        "params": [{"name": "p", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "default": 0.1}],
        "description": "X error with probability p.",
    },
    "phase_flip": {
        "label": "Phase flip",
        "params": [{"name": "p", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "default": 0.1}],
        "description": "Z error with probability p.",
    },
    "bit_phase_flip": {
        "label": "Bit-phase flip",
        "params": [{"name": "p", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "default": 0.1}],
        "description": "Y error with probability p.",
    },
    "amplitude_damping": {
        "label": "Amplitude damping",
        "params": [{"name": "gamma", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "default": 0.3}],
        "description": "Energy loss towards |0>. Non-unital: shifts the sphere towards the north pole.",
    },
    "phase_damping": {
        "label": "Phase damping",
        "params": [{"name": "lam", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "default": 0.3}],
        "description": "Loss of coherence without energy loss.",
    },
    "rotation": {
        "label": "Coherent rotation",
        "params": [
            {"name": "axis", "type": "vector3", "default": [0.0, 0.0, 1.0]},
            {"name": "theta", "type": "float", "min": -math.pi, "max": math.pi, "step": 0.01, "default": 0.5, "unit": "rad"},
        ],
        "description": "A unitary rotation exp(-i theta n.sigma/2). Preserves purity.",
    },
    "pauli": {
        "label": "Pauli channel",
        "params": [
            {"name": "px", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "default": 0.05},
            {"name": "py", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "default": 0.0},
            {"name": "pz", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "default": 0.05},
        ],
        "description": "Independent X, Y, Z errors with the given probabilities.",
    },
    "measure_prepare": {
        "label": "Measure & re-prepare",
        "params": [{"name": "basis", "type": "enum", "options": ["x", "y", "z"], "default": "z"}],
        "description": "Measure in a basis and re-prepare the outcome. Entanglement-breaking.",
    },
}


def _float(spec: Mapping, key: str, lo: float, hi: float, default: float | None = None) -> float:
    if key not in spec:
        if default is None:
            raise ChannelSpecError(f"channel {spec.get('type')!r} requires parameter {key!r}")
        return float(default)
    try:
        v = float(spec[key])
    except (TypeError, ValueError):
        raise ChannelSpecError(f"parameter {key!r} must be a number") from None
    if not math.isfinite(v) or v < lo - 1e-12 or v > hi + 1e-12:
        raise ChannelSpecError(f"parameter {key!r}={v} outside [{lo}, {hi}]")
    return float(min(max(v, lo), hi))


def _axis_name(spec: Mapping, key: str = "axis", default: str = "z") -> str:
    a = str(spec.get(key, default)).lower()
    if a not in _AXES:
        raise ChannelSpecError(f"parameter {key!r} must be one of x, y, z")
    return a


def _axis_vector(spec: Mapping) -> np.ndarray:
    a = spec.get("axis", [0.0, 0.0, 1.0])
    if isinstance(a, str):
        return _AXES[_axis_name(spec)].copy()
    try:
        v = np.asarray(a, dtype=float).reshape(3)
    except Exception:
        raise ChannelSpecError("rotation axis must be 'x'|'y'|'z' or a 3-vector") from None
    n = float(np.linalg.norm(v))
    if not math.isfinite(n) or n < 1e-9:
        raise ChannelSpecError("rotation axis must be a non-zero finite vector")
    return v / n


def normalise_spec(spec: Mapping) -> dict:
    """Validate a spec and return its canonical dictionary form."""
    if not isinstance(spec, Mapping):
        raise ChannelSpecError("channel spec must be an object")
    t = str(spec.get("type", "")).strip()
    if t not in CHANNEL_TYPES:
        raise ChannelSpecError(f"unknown channel type {t!r}")
    if t == "identity":
        return {"type": t}
    if t in ("depolarizing", "bit_flip", "phase_flip", "bit_phase_flip"):
        return {"type": t, "p": _float(spec, "p", 0.0, 1.0)}
    if t == "dephasing":
        return {"type": t, "p": _float(spec, "p", 0.0, 1.0), "axis": _axis_name(spec)}
    if t == "amplitude_damping":
        return {"type": t, "gamma": _float(spec, "gamma", 0.0, 1.0)}
    if t == "phase_damping":
        return {"type": t, "lam": _float(spec, "lam", 0.0, 1.0)}
    if t == "rotation":
        axis = _axis_vector(spec)
        return {"type": t, "axis": [float(x) for x in axis], "theta": _float(spec, "theta", -2 * math.pi, 2 * math.pi)}
    if t == "pauli":
        px, py, pz = (_float(spec, k, 0.0, 1.0, 0.0) for k in ("px", "py", "pz"))
        if px + py + pz > 1.0 + 1e-12:
            raise ChannelSpecError("pauli probabilities must sum to at most 1")
        return {"type": t, "px": px, "py": py, "pz": pz}
    if t == "measure_prepare":
        return {"type": t, "basis": _axis_name(spec, "basis")}
    raise ChannelSpecError(f"unhandled channel type {t!r}")  # pragma: no cover


def normalise_specs(specs: Sequence[Mapping] | None) -> list[dict]:
    if specs is None:
        return []
    if isinstance(specs, Mapping):
        specs = [specs]
    return [normalise_spec(s) for s in specs]


def _kraus_for(spec: dict) -> list[np.ndarray]:
    t = spec["type"]
    if t == "identity":
        return [I2.copy()]
    if t == "depolarizing":
        p = spec["p"]
        return [np.sqrt(max(0.0, 1 - 3 * p / 4)) * I2] + [np.sqrt(p / 4) * P for P in (X, Y, Z)]
    if t in ("dephasing", "bit_flip", "phase_flip", "bit_phase_flip"):
        axis = {"bit_flip": "x", "phase_flip": "z", "bit_phase_flip": "y"}.get(t, spec.get("axis", "z"))
        p = spec["p"]
        return [np.sqrt(1 - p) * I2, np.sqrt(p) * _PAULI_OF_AXIS[axis]]
    if t == "amplitude_damping":
        g = spec["gamma"]
        return [np.array([[1, 0], [0, np.sqrt(1 - g)]], dtype=complex), np.array([[0, np.sqrt(g)], [0, 0]], dtype=complex)]
    if t == "phase_damping":
        lam = spec["lam"]
        return [np.array([[1, 0], [0, np.sqrt(1 - lam)]], dtype=complex), np.array([[0, 0], [0, np.sqrt(lam)]], dtype=complex)]
    if t == "rotation":
        return [su2_rotation(spec["axis"], spec["theta"])]
    if t == "pauli":
        px, py, pz = spec["px"], spec["py"], spec["pz"]
        return [np.sqrt(max(0.0, 1 - px - py - pz)) * I2, np.sqrt(px) * X, np.sqrt(py) * Y, np.sqrt(pz) * Z]
    if t == "measure_prepare":
        axis = _AXES[spec["basis"]]
        ops = []
        for sgn in (+1, -1):
            n = sgn * axis
            ket = _ket_of_bloch(n)
            ops.append(np.outer(ket, ket.conj()))
        # |+n><+n| and |-n><-n| as Kraus: measure then keep outcome state.
        return ops
    raise ChannelSpecError(f"unhandled channel type {t!r}")  # pragma: no cover


def _ket_of_bloch(n: np.ndarray) -> np.ndarray:
    theta = math.acos(max(-1.0, min(1.0, float(n[2]))))
    phi = math.atan2(float(n[1]), float(n[0]))
    return np.array([math.cos(theta / 2), np.exp(1j * phi) * math.sin(theta / 2)], dtype=complex)


def _prune(kraus: list[np.ndarray]) -> tuple:
    kept = [K for K in kraus if np.linalg.norm(K) > 1e-14]
    return tuple(kept) if kept else (np.zeros((2, 2), dtype=complex),)


def channel_from_spec(spec: Mapping) -> Channel:
    """Build a :class:`Channel` from one spec."""
    s = normalise_spec(spec)
    kraus = _prune(_kraus_for(s))
    params = {k: v for k, v in s.items() if k != "type"}
    return Channel(name=s["type"], params=params, kraus=kraus, ptm=kraus_to_ptm(kraus))


def compose(specs: Sequence[Mapping] | None) -> Channel:
    """Composite channel applying ``specs`` in order (first element first)."""
    norm = normalise_specs(specs)
    if not norm:
        return channel_from_spec({"type": "identity"})
    if len(norm) == 1:
        return channel_from_spec(norm[0])
    kraus: list[np.ndarray] = [I2.copy()]
    for s in norm:
        step = _kraus_for(s)
        kraus = [K2 @ K1 for K1 in kraus for K2 in step]
        kraus = list(_prune(kraus))
    kraus_t = _prune(kraus)
    return Channel(name="composite", params={"channels": norm}, kraus=kraus_t, ptm=kraus_to_ptm(kraus_t))


def _round(obj: Any) -> Any:
    if isinstance(obj, float):
        return round(obj, 12)
    if isinstance(obj, list):
        return [_round(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in sorted(obj.items())}
    return obj


def spec_key(specs: Sequence[Mapping] | None) -> str:
    """Canonical string key for a list of specs (for caching)."""
    return json.dumps(_round(normalise_specs(specs)), sort_keys=True, separators=(",", ":"))
