"""
dashboard/data_source.py
========================
The dashboard's single data contract.

SIH26141 | Blockchain & Cybersecurity.

Every number the UI displays is loaded from ``experiments/results/final/``,
which is written only by ``experiments/run_final_experiment.py``. This
module **loads**; it never computes a security metric. Keeping that rule
means the dashboard cannot drift away from the experiment, and cannot
invent a figure that no run produced.

If the canonical results are missing, the loaders return ``None`` and the
UI says so. Showing a plausible placeholder instead would be worse than
showing nothing, because a placeholder is indistinguishable from a real
measurement once it is on screen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
FINAL_DIR = _ROOT / "experiments" / "results" / "final"
PLOTS_DIR = FINAL_DIR / "plots"

for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

__all__ = [
    "FINAL_DIR",
    "PLOTS_DIR",
    "results_available",
    "load_metrics",
    "load_experiment_config",
    "load_attack_metrics",
    "load_comparison",
    "load_intensity",
    "load_threshold_analysis",
    "load_confusion_matrix",
    "load_sessions",
    "plot_path",
    "missing_results_message",
]


def results_available() -> bool:
    """True when a canonical experiment run is present on disk."""
    return (FINAL_DIR / "metrics.json").exists()


def missing_results_message() -> str:
    """The instruction shown wherever results are required but absent."""
    return (
        "No canonical results found. Generate them with:\n\n"
        "    python experiments/run_final_experiment.py --trials 200\n\n"
        "Every figure in this dashboard comes from that run; nothing is "
        "displayed until it exists."
    )


def _read_json(name: str) -> Optional[Dict[str, Any]]:
    path = FINAL_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_csv(name: str, **kwargs) -> Optional[pd.DataFrame]:
    path = FINAL_DIR / name
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, **kwargs)
    except Exception:
        return None


def load_metrics() -> Optional[Dict[str, Any]]:
    """Headline metrics: accuracy, detection rate, FAR/FRR with intervals."""
    return _read_json("metrics.json")


def load_experiment_config() -> Optional[Dict[str, Any]]:
    """Provenance: seed, trial counts, noise settings, timestamp, commit."""
    return _read_json("experiment_config.json")


def load_attack_metrics() -> Optional[pd.DataFrame]:
    """Per-attack detection rates with confidence intervals."""
    return _read_csv("attack_metrics.csv")


def load_comparison() -> Optional[pd.DataFrame]:
    """NORMAL vs ATTACK telemetry comparison."""
    return _read_csv("comparison.csv")


def load_intensity() -> Optional[pd.DataFrame]:
    """Detection rate as a function of attack intensity."""
    return _read_csv("intensity_analysis.csv")


def load_threshold_analysis() -> Optional[pd.DataFrame]:
    """Threshold sweep with FAR/FRR at each candidate."""
    return _read_csv("threshold_analysis.csv")


def load_confusion_matrix() -> Optional[pd.DataFrame]:
    """2x2 confusion matrix."""
    return _read_csv("confusion_matrix.csv", index_col=0)


def load_sessions() -> Optional[pd.DataFrame]:
    """Every individual session from the canonical run."""
    return _read_csv("sessions.csv")


def plot_path(name: str) -> Optional[str]:
    """Absolute path to a generated plot, or ``None`` when absent."""
    p = PLOTS_DIR / name
    return str(p) if p.exists() else None


# ---------------------------------------------------------------------------
# Formatting helpers (presentation only -- no metric is computed here)
# ---------------------------------------------------------------------------

def pct(value: Optional[float], digits: int = 2) -> str:
    """Render a rate in [0,1] as a percentage string."""
    if value is None:
        return "N/A"
    return f"{value * 100:.{digits}f}%"


def pct_ci(value: Optional[float], ci: Optional[List[float]]) -> str:
    """Render a rate with its confidence interval.

    Rates are always shown with their interval: a rate without one invites
    the reader to trust a point estimate the sample size does not support.
    """
    if value is None:
        return "N/A"
    if not ci or len(ci) != 2:
        return pct(value)
    return f"[{ci[0] * 100:.2f}, {ci[1] * 100:.2f}]"
