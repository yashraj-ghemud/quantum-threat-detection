"""
evaluation/latency.py
=====================
Timing instrumentation for the QDS pipeline.

Phase 7 -- SIH26141 | Blockchain & Cybersecurity.

Measures wall-clock latency of the stages that matter operationally:
circuit execution, signature generation, verification, and the full
session. Uses ``time.perf_counter`` (monotonic, highest available
resolution) rather than ``time.time``, which can jump backwards.

Every function reports a **distribution**, not a single number. One timing
is close to meaningless: the first call pays import and transpilation
costs, and any run can be interrupted by the OS scheduler. Median and
percentiles describe behaviour far better than a mean over a handful of
noisy samples, so both are reported and the mean is never given alone.

No AI/ML libraries are used.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "LatencyStats",
    "measure",
    "time_circuit_execution",
    "time_qds_cycle",
    "summarize",
]


@dataclass
class LatencyStats:
    """Timing distribution for one repeated operation.

    Attributes
    ----------
    label : str
        Name of the operation measured.
    samples_ms : list[float]
        Individual timings in milliseconds, in execution order.
    warmup : int
        Number of leading samples discarded before statistics.
    """

    label: str
    samples_ms: List[float] = field(default_factory=list)
    warmup: int = 0

    @property
    def n(self) -> int:
        """Number of samples retained after warm-up."""
        return len(self.samples_ms)

    @property
    def mean(self) -> float:
        return float(np.mean(self.samples_ms)) if self.samples_ms else 0.0

    @property
    def median(self) -> float:
        return float(np.median(self.samples_ms)) if self.samples_ms else 0.0

    @property
    def stdev(self) -> float:
        return float(np.std(self.samples_ms)) if self.samples_ms else 0.0

    @property
    def p95(self) -> float:
        return float(np.percentile(self.samples_ms, 95)) if self.samples_ms else 0.0

    @property
    def p99(self) -> float:
        return float(np.percentile(self.samples_ms, 99)) if self.samples_ms else 0.0

    @property
    def minimum(self) -> float:
        return float(np.min(self.samples_ms)) if self.samples_ms else 0.0

    @property
    def maximum(self) -> float:
        return float(np.max(self.samples_ms)) if self.samples_ms else 0.0

    @property
    def throughput_per_sec(self) -> float:
        """Operations per second implied by the median latency."""
        return 1000.0 / self.median if self.median > 0 else 0.0

    def as_dict(self) -> Dict[str, Any]:
        """Flat dict for CSV/JSON export."""
        return {
            "label": self.label,
            "n": self.n,
            "warmup_discarded": self.warmup,
            "mean_ms": self.mean,
            "median_ms": self.median,
            "stdev_ms": self.stdev,
            "p95_ms": self.p95,
            "p99_ms": self.p99,
            "min_ms": self.minimum,
            "max_ms": self.maximum,
            "throughput_per_sec": self.throughput_per_sec,
        }

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"LatencyStats({self.label}: median={self.median:.2f}ms "
            f"mean={self.mean:.2f}+-{self.stdev:.2f} "
            f"p95={self.p95:.2f} n={self.n})"
        )


def measure(
    fn: Callable[[], Any],
    repeats: int = 20,
    warmup: int = 1,
    label: str = "operation",
) -> LatencyStats:
    """Time *fn* repeatedly and return its latency distribution.

    Parameters
    ----------
    fn : callable
        Zero-argument callable to time. Its return value is discarded.
    repeats : int
        Timed repetitions after warm-up.
    warmup : int
        Leading calls to run and discard. The first call to anything
        touching Qiskit pays import, transpilation and cache-population
        costs that are not representative of steady-state behaviour;
        including them would inflate the mean by an order of magnitude.
    label : str
        Name recorded on the result.

    Returns
    -------
    LatencyStats

    Raises
    ------
    ValueError
        If *repeats* < 1 or *warmup* < 0.
    """
    if repeats < 1:
        raise ValueError(f"repeats must be >= 1, got {repeats}.")
    if warmup < 0:
        raise ValueError(f"warmup must be >= 0, got {warmup}.")

    for _ in range(warmup):
        fn()

    samples: List[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)

    stats = LatencyStats(label=label, samples_ms=samples, warmup=warmup)
    logger.info("%s", stats)
    return stats


def time_circuit_execution(
    circuit,
    shots: int = 1024,
    repeats: int = 10,
    warmup: int = 1,
    backend=None,
) -> LatencyStats:
    """Time execution of a Qiskit circuit on Aer.

    Transpilation happens once, outside the timed region, so the figure
    reflects execution rather than compilation.

    Parameters
    ----------
    circuit : qiskit.QuantumCircuit
        Circuit to run.
    shots : int
        Shots per execution.
    repeats, warmup : int
        Timing repetitions and discarded warm-up calls.
    backend : AerSimulator or None
        Backend to use; a default ``AerSimulator`` is created when ``None``.

    Returns
    -------
    LatencyStats
    """
    import warnings

    from qiskit import transpile
    from qiskit_aer import AerSimulator

    if backend is None:
        backend = AerSimulator()
    compiled = transpile(circuit, backend)

    def _run() -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            backend.run(compiled, shots=shots).result()

    return measure(_run, repeats=repeats, warmup=warmup,
                   label=f"circuit_execution(shots={shots})")


def time_qds_cycle(
    signature_length: int = 16,
    shots: int = 256,
    repeats: int = 10,
    warmup: int = 1,
    seed: int = 42,
    use_teleportation: bool = True,
) -> Dict[str, LatencyStats]:
    """Time a full sign -> transmit -> verify -> detect cycle.

    Runs the real :class:`session.SessionRunner`, so the timings describe
    the actual pipeline rather than a stand-in.

    Parameters
    ----------
    signature_length : int
        Elements per signature.
    shots : int
        Measurement shots per element.
    repeats, warmup : int
        Timing repetitions and discarded warm-up calls.
    seed : int
        Base seed.
    use_teleportation : bool
        Whether the quantum channel is exercised.

    Returns
    -------
    dict[str, LatencyStats]
        Keyed ``'end_to_end'``, plus per-stage breakdowns recorded by the
        session itself.
    """
    from session import SessionRunner

    runner = SessionRunner(
        signature_length=signature_length,
        shots=shots,
        seed=seed,
        use_teleportation=use_teleportation,
    )
    runner.setup(private_seed=bytes([seed % 256]) * 32)
    runner.calibrate_baseline(n_sessions=max(3, warmup + 2))

    counter = {"i": 0}
    stage_samples: Dict[str, List[float]] = {
        "signature_generation": [], "quantum_channel": [],
        "measurement_verification": [], "threat_detection": [],
    }

    def _cycle() -> None:
        counter["i"] += 1
        res = runner.run(message=f"latency probe {counter['i']}".encode())
        stage_samples["signature_generation"].append(res.latency_sign_ms)
        stage_samples["quantum_channel"].append(res.latency_channel_ms)
        stage_samples["measurement_verification"].append(res.latency_measure_ms)
        stage_samples["threat_detection"].append(res.latency_detect_ms)

    end_to_end = measure(_cycle, repeats=repeats, warmup=warmup,
                         label=f"qds_cycle(len={signature_length})")

    out: Dict[str, LatencyStats] = {"end_to_end": end_to_end}
    for name, samples in stage_samples.items():
        # Drop the warm-up entries so stages align with end_to_end.
        kept = samples[warmup:] if len(samples) > warmup else samples
        out[name] = LatencyStats(label=name, samples_ms=kept, warmup=warmup)
    return out


def summarize(stats: Sequence[LatencyStats]) -> "Any":
    """Return a DataFrame summarising several latency distributions."""
    import pandas as pd

    return pd.DataFrame([s.as_dict() for s in stats])
