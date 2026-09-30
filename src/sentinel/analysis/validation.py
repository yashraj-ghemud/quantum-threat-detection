"""
sentinel/analysis/validation.py
===============================
Cross-validation of the Sentinel teleportation superoperators against
Qiskit Aer.

The reference circuit is v1's teleportation layout
(``quantum.teleportation.build_teleportation_circuit``) with the link channel
inserted as an explicit ``Kraus`` instruction on the receiver's half, right
after the Bell pair is created. Aer's density-matrix simulator saves the
receiver's state *conditioned on each Bell outcome*. Each of those four
conditional states must equal the Sentinel prediction ``bloch[label, k, k]``,
and the outcome frequencies must be consistent with ``p_k``.

Qiskit is optional: if it is not importable the check reports ``skip``.
"""

from __future__ import annotations

import math
import time
import warnings
from typing import Mapping, Sequence

import numpy as np

from sentinel.channels import compose
from sentinel.linalg import bloch_to_rho
from sentinel.states import BLOCH, KETS
from sentinel.teleport import get_model

__all__ = ["DEFAULT_CHANNELS", "EXTENDED_CHANNELS", "aer_available", "validate_channel", "validate_all"]

DEFAULT_CHANNELS: list[list[dict]] = [
    [],
    [{"type": "depolarizing", "p": 0.1}],
    [{"type": "dephasing", "p": 0.2, "axis": "z"}],
    [{"type": "amplitude_damping", "gamma": 0.3}],
    [{"type": "rotation", "axis": [0, 0, 1], "theta": 0.4}],
    [{"type": "measure_prepare", "basis": "z"}],
]

EXTENDED_CHANNELS: list[list[dict]] = DEFAULT_CHANNELS + [
    [{"type": "bit_flip", "p": 0.15}],
    [{"type": "phase_damping", "lam": 0.4}],
    [{"type": "pauli", "px": 0.05, "py": 0.1, "pz": 0.02}],
    [{"type": "rotation", "axis": [1, 1, 0], "theta": 1.1}],
    [{"type": "measure_prepare", "basis": "x"}],
    [{"type": "depolarizing", "p": 0.02}, {"type": "amplitude_damping", "gamma": 0.05}],
]


def aer_available() -> bool:
    try:
        import qiskit  # noqa: F401
        import qiskit_aer  # noqa: F401
        return True
    except Exception:
        return False


def _angles(r: np.ndarray) -> tuple[float, float]:
    theta = math.acos(max(-1.0, min(1.0, float(r[2]))))
    phi = math.atan2(float(r[1]), float(r[0]))
    return theta, phi


def _aer_conditional(specs: Sequence[Mapping], label: int, shots: int, seed: int) -> dict:
    from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, transpile
    from qiskit.quantum_info import Kraus
    from qiskit_aer import AerSimulator

    theta, phi = _angles(BLOCH[label])
    qr, cr = QuantumRegister(3, "q"), ClassicalRegister(2, "c")
    qc = QuantumCircuit(qr, cr)
    qc.ry(theta, 0)
    qc.rz(phi, 0)
    qc.h(1)
    qc.cx(1, 2)
    ch = compose(specs)
    if specs:
        qc.append(Kraus([np.asarray(K) for K in ch.kraus]), [2])
    qc.cx(0, 1)
    qc.h(0)
    qc.measure(0, 0)
    qc.measure(1, 1)
    with qc.if_test((cr[1], 1)):
        qc.x(2)
    with qc.if_test((cr[0], 1)):
        qc.z(2)
    qc.save_density_matrix([2], label="bob", conditional=True)
    sim = AerSimulator(method="density_matrix")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = sim.run(transpile(qc, sim), shots=shots, seed_simulator=seed).result()
    data = res.data()["bob"]
    out = {}
    for key, dm in data.items():
        v = int(key, 16)
        m0, m1 = v & 1, (v >> 1) & 1
        out[2 * m0 + m1] = np.asarray(dm)
    return out


def validate_channel(specs: Sequence[Mapping], shots: int = 256, seed: int = 11) -> dict:
    """Compare Sentinel conditional states with Aer for all six labels."""
    model = get_model(specs)
    per_label = []
    max_dev = 0.0
    missing = 0
    for label in range(6):
        cond = _aer_conditional(specs, label, shots, seed + label)
        devs = []
        for k in range(4):
            if k not in cond:
                missing += 1
                continue
            predicted = bloch_to_rho(model.bloch[label, k, k])
            dev = float(np.max(np.abs(cond[k] - predicted)))
            devs.append(dev)
            max_dev = max(max_dev, dev)
        per_label.append({"label": KETS[label], "max_dev": max(devs) if devs else None, "outcomes_seen": len(cond)})
    return {
        "channel": list(specs),
        "name": " + ".join(s.get("type", "?") for s in specs) or "identity",
        "max_dev": max_dev,
        "per_label": per_label,
        "missing_outcomes": missing,
        "pass": bool(max_dev < 1e-9 and missing == 0),
    }


def validate_all(channels: Sequence[Sequence[Mapping]] | None = None, progress=None, cancel=None) -> dict:
    """Validate a list of channel configurations. Returns a job-style result."""
    t0 = time.perf_counter()
    if not aer_available():
        return {"status": "skip", "reason": "qiskit / qiskit-aer not importable", "checks": [], "pass": None}
    import qiskit
    import qiskit_aer

    channels = list(channels if channels is not None else DEFAULT_CHANNELS)
    checks = []
    for i, specs in enumerate(channels):
        if cancel is not None and cancel.is_set():
            break
        checks.append(validate_channel(specs))
        if progress:
            progress((i + 1) / len(channels), f"validated {checks[-1]['name']}")
    return {
        "status": "done",
        "checks": checks,
        "pass": all(c["pass"] for c in checks) if checks else None,
        "max_dev": max((c["max_dev"] for c in checks), default=None),
        "qiskit_version": qiskit.__version__,
        "aer_version": qiskit_aer.__version__,
        "duration_s": time.perf_counter() - t0,
    }
