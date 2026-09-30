"""
sentinel/analysis/jobs.py
=========================
Registry of analytics jobs served by ``/api/v1/analytics``.

Each job is ``run(params, progress, cancel) -> dict``. ``quick`` presets are
sized to finish in well under a minute on the build container; ``full``
presets tighten confidence intervals.
"""

from __future__ import annotations

from sentinel.analysis import evaluation as ev
from sentinel.analysis.forgery import run_forgery_analysis
from sentinel.analysis.validation import EXTENDED_CHANNELS, DEFAULT_CHANNELS, validate_all

__all__ = ["JOB_KINDS", "run_job", "kinds_public"]


def _validation(params, progress=None, cancel=None):
    chans = EXTENDED_CHANNELS if params.get("extended") else DEFAULT_CHANNELS
    return validate_all(chans, progress, cancel)


JOB_KINDS = {
    "detection_matrix": {
        "title": "Detection matrix",
        "description": "Every catalog attack across intensities, plus honest traffic: detection rate, "
                       "classification accuracy, FAR and FRR with Clopper-Pearson intervals, and a confusion matrix.",
        "run": ev.detection_matrix,
        "presets": {"quick": {"intensities": [0.25, 0.5, 1.0], "trials": 4, "legit": 40},
                    "full": {"intensities": [0.1, 0.25, 0.5, 0.75, 1.0], "trials": 20, "legit": 200}},
        "est_seconds": {"quick": 25, "full": 240},
    },
    "roc": {
        "title": "ROC curves",
        "description": "Per-detector true- and false-positive rates for weak channel attacks, swept over the "
                       "significance level, with the fused family test.",
        "run": ev.roc,
        "presets": {"quick": {"runs": 60}, "full": {"runs": 300}},
        "est_seconds": {"quick": 30, "full": 150},
    },
    "forgery_analysis": {
        "title": "Forgery probability",
        "description": "Exact per-key forgery probability vs key length for the blind and insider forgers, "
                       "Monte Carlo through the real verifier, and a search proving the insider cannot beat 1/3.",
        "run": run_forgery_analysis,
        "presets": {"quick": {"mc_L": [32, 64, 96], "mc_trials": 1000},
                    "full": {"mc_L": [32, 48, 64, 96, 128, 192], "mc_trials": 5000}},
        "est_seconds": {"quick": 20, "full": 120},
    },
    "threshold_design": {
        "title": "Threshold design table",
        "description": "Designed thresholds and achieved robustness, forgery and repudiation bounds over a grid "
                       "of honest error rates and key lengths.",
        "run": ev.threshold_design_table,
        "presets": {"quick": {}, "full": {"e_grid": [0.0025, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04]}},
        "est_seconds": {"quick": 10, "full": 25},
    },
    "sprt_efficiency": {
        "title": "Sequential test efficiency",
        "description": "Average number of observations Wald's SPRT reads before deciding, against the true "
                       "mismatch rate, vs the fixed-length test.",
        "run": ev.sprt_efficiency,
        "presets": {"quick": {"paths": 300}, "full": {"paths": 2000}},
        "est_seconds": {"quick": 5, "full": 25},
    },
    "channel_fingerprint": {
        "title": "Channel fingerprint accuracy",
        "description": "How often de-twirled tomography names the right channel shape for each attack family.",
        "run": ev.channel_fingerprint,
        "presets": {"quick": {"strengths": [0.5, 1.0], "trials": 6}, "full": {"strengths": [0.3, 0.5, 0.75, 1.0], "trials": 25}},
        "est_seconds": {"quick": 15, "full": 120},
    },
    "cusum_arl": {
        "title": "CUSUM run length",
        "description": "Bundles until the temporal monitor alarms, for persistent QBER shifts too small for any "
                       "single run to flag, and the false-alarm rate with no shift.",
        "run": ev.cusum_arl,
        "presets": {"quick": {"runs": 150}, "full": {"runs": 1000}},
        "est_seconds": {"quick": 10, "full": 60},
    },
    "performance": {
        "title": "Performance",
        "description": "Measured latency of distribution, signing, verification and detection vs key length, "
                       "qubits per second, and speed-up over Qiskit Aer circuit simulation.",
        "run": ev.performance,
        "presets": {"quick": {"L_grid": [512, 1024, 2048, 4096], "reps": 2},
                    "full": {"L_grid": [256, 512, 1024, 2048, 4096, 8192], "reps": 5}},
        "est_seconds": {"quick": 15, "full": 60},
    },
    "repudiation_analysis": {
        "title": "Repudiation",
        "description": "Dispute rate a dishonest signer achieves with and without symmetrization, and how often "
                       "the distribution-time source test already exposes her.",
        "run": ev.repudiation_analysis,
        "presets": {"quick": {"fractions": [0.0, 0.05, 0.1, 0.2, 0.3, 0.5], "runs": 12},
                    "full": {"runs": 60}},
        "est_seconds": {"quick": 20, "full": 150},
    },
    "engine_validation": {
        "title": "Engine validation",
        "description": "Sentinel teleportation superoperators against Qiskit Aer, per Bell outcome, for every "
                       "channel family.",
        "run": _validation,
        "presets": {"quick": {}, "full": {"extended": True}},
        "est_seconds": {"quick": 5, "full": 10},
    },
}


def kinds_public() -> list:
    return [{"kind": k, "title": v["title"], "description": v["description"], "presets": v["presets"],
             "est_seconds": v["est_seconds"]} for k, v in JOB_KINDS.items()]


def run_job(kind: str, params: dict | None = None, preset: str = "quick", progress=None, cancel=None) -> dict:
    if kind not in JOB_KINDS:
        raise KeyError(f"unknown job kind {kind!r}")
    spec = JOB_KINDS[kind]
    merged = dict(spec["presets"].get(preset, {}))
    merged.update(params or {})
    result = spec["run"](merged, progress, cancel)
    result.setdefault("params", merged)
    result["kind"] = kind
    result["preset"] = preset
    return result
