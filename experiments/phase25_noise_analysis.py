"""
experiments/phase25_noise_analysis.py
=======================================
Phase 2.5 -- Quantum Channel Noise Baseline Analysis.
SIH26141 | Blockchain & Cybersecurity.

Runs a full fidelity-vs-noise sweep across all four noise models and six
standard input states, stores results in a pandas DataFrame, generates one
fidelity-vs-p plot per noise model, and prints a concise summary report.

Usage
-----
    python experiments/phase25_noise_analysis.py
    python experiments/phase25_noise_analysis.py --shots 2048 --seed 42

No AI/ML libraries used.
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")            # non-interactive backend; works without display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=DeprecationWarning)

_ROOT = Path(__file__).resolve().parent.parent
_SRC  = _ROOT / "src"
for _p in (_SRC, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from quantum.noise import (
    NOISE_STRENGTHS,
    NOISE_TYPES,
    results_to_dataframe,
    sweep_noise_fidelity,
)
from quantum.teleportation import STANDARD_STATES
from utils.config import ConfigLoader
from utils.logger import get_logger
from utils.reproducibility import get_run_context, set_seed

logger = get_logger(__name__)

_SEP  = "=" * 72
_THIN = "-" * 72
_OUT_DIR = _ROOT / "experiments" / "outputs"


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def _plot_noise_model(
    df: pd.DataFrame,
    noise_type: str,
    out_dir: Path,
) -> Path:
    """Generate fidelity-vs-noise-strength plot for one noise model.

    Parameters
    ----------
    df : pd.DataFrame
        Full results DataFrame (all types).
    noise_type : str
        The noise type to plot.
    out_dir : Path
        Directory to save the figure.

    Returns
    -------
    Path
        Path to the saved PNG file.
    """
    subset = df[df["noise_type"] == noise_type].copy()
    state_names = sorted(subset["state_name"].unique())

    fig, ax = plt.subplots(figsize=(7, 4.5))
    markers = ["o", "s", "^", "D", "v", "P"]

    for idx, sname in enumerate(state_names):
        sdata = subset[subset["state_name"] == sname].sort_values("p")
        ax.plot(
            sdata["p"],
            sdata["fidelity"],
            marker=markers[idx % len(markers)],
            linewidth=1.6,
            markersize=5,
            label=sname,
        )

    ax.set_xlabel("Noise strength  p", fontsize=11)
    ax.set_ylabel("Teleportation fidelity  F", fontsize=11)
    ax.set_title(
        f"Fidelity vs Noise Strength\n"
        f"Channel: {noise_type.replace('_', ' ').title()}",
        fontsize=12,
    )
    ax.set_xlim(-0.01, max(NOISE_STRENGTHS) + 0.01)
    ax.set_ylim(-0.05, 1.10)
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, label="ideal")
    ax.legend(fontsize=9, loc="upper right")
    ax.grid(True, alpha=0.35)
    fig.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"fidelity_{noise_type}.png"
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    logger.info("Saved plot: %s", out_path)
    return out_path


def _plot_all_noise_models_combined(
    df: pd.DataFrame,
    out_dir: Path,
    state_name: str = "|+>",
) -> Path:
    """One figure with all four noise models for a single representative state."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharey=True)
    axes = axes.flatten()

    for ax, noise_type in zip(axes, NOISE_TYPES):
        subset = df[
            (df["noise_type"] == noise_type) &
            (df["state_name"] == state_name)
        ].sort_values("p")
        ax.plot(subset["p"], subset["fidelity"], "o-", linewidth=1.8, markersize=5)
        ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8)
        ax.set_title(noise_type.replace("_", " ").title(), fontsize=11)
        ax.set_xlabel("p")
        ax.set_ylabel("F")
        ax.set_ylim(-0.05, 1.10)
        ax.grid(True, alpha=0.35)

    fig.suptitle(
        f"Fidelity vs Noise Strength  --  Input state {state_name}",
        fontsize=13, y=1.01,
    )
    fig.tight_layout()
    out_path = out_dir / f"fidelity_all_models_{state_name.strip('|<>').replace('+','plus').replace('-','minus')}.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved combined plot: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def _print_summary(df: pd.DataFrame) -> None:
    """Print concise noise-severity comparison table."""
    print(f"\n{_SEP}")
    print("  NOISE SEVERITY SUMMARY  (mean fidelity across all states, p > 0)")
    print(_SEP)
    print(f"  {'Noise Type':<22}  {'p=0.01':>8}  {'p=0.05':>8}  "
          f"{'p=0.10':>8}  {'p=0.20':>8}  {'p=0.30':>8}")
    print(f"  {'-'*22}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")

    for ntype in NOISE_TYPES:
        row_parts = [f"  {ntype:<22}"]
        for p_val in [0.01, 0.05, 0.10, 0.20, 0.30]:
            mask = (df["noise_type"] == ntype) & (np.isclose(df["p"], p_val))
            mean_f = df.loc[mask, "fidelity"].mean() if mask.any() else float("nan")
            row_parts.append(f"  {mean_f:>8.4f}")
        print("".join(row_parts))
    print(_THIN)


def _print_per_state_table(df: pd.DataFrame) -> None:
    """Print per-state fidelity at p=0.10 for each noise type."""
    print(f"\n{_SEP}")
    print("  PER-STATE FIDELITY AT p=0.10")
    print(_SEP)
    state_names = [s[0] for s in STANDARD_STATES]
    header = f"  {'Noise Type':<22}  " + "  ".join(f"{s:>7}" for s in state_names)
    print(header)
    print(f"  {'-'*22}  " + "  ".join("-" * 7 for _ in state_names))
    for ntype in NOISE_TYPES:
        row = f"  {ntype:<22}  "
        for sname in state_names:
            mask = (
                (df["noise_type"] == ntype)
                & (np.isclose(df["p"], 0.10))
                & (df["state_name"] == sname)
            )
            val = df.loc[mask, "fidelity"].values
            cell = f"{val[0]:.4f}" if len(val) > 0 else "  N/A "
            row += f"  {cell:>7}"
        print(row)
    print(_THIN)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_analysis(shots: int, seed: int) -> bool:
    """Run the full Phase 2.5 noise analysis.

    Parameters
    ----------
    shots : int
        Aer shots per (noise_type, p, state) combination.
    seed : int
        Random seed.

    Returns
    -------
    bool
        True when all p=0 baseline fidelities are within tolerance.
    """
    cfg = ConfigLoader()
    ctx = get_run_context(seed)
    set_seed(seed)

    print(_SEP)
    print("  PHASE 2.5 -- Quantum Channel Noise Baseline Analysis")
    print("  SIH26141 | Quantum-Inspired Cyber Threat Detection")
    print(_SEP)
    print(f"  Seed          : {ctx['seed']}")
    print(f"  NumPy version : {ctx['numpy_version']}")
    print(f"  Simulator     : density_matrix ({cfg.simulator_backend})")
    print(f"  Shots/run     : {shots}")
    print(f"  Noise types   : {list(NOISE_TYPES)}")
    print(f"  Strengths     : {list(NOISE_STRENGTHS)}")
    print(f"  States        : {[s[0] for s in STANDARD_STATES]}")
    total_runs = len(NOISE_TYPES) * len(NOISE_STRENGTHS) * len(STANDARD_STATES)
    print(f"  Total runs    : {total_runs}")
    print(f"  Timestamp     : {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print(_SEP)

    t0 = time.perf_counter()

    # Run sweep
    print("\n  Running sweep ...")
    results = sweep_noise_fidelity(
        noise_types=NOISE_TYPES,
        noise_strengths=NOISE_STRENGTHS,
        states=STANDARD_STATES,
        shots=shots,
        seed=seed,
    )
    df = results_to_dataframe(results)
    elapsed_sweep = time.perf_counter() - t0
    print(f"  Sweep complete: {len(df)} rows in {elapsed_sweep:.1f}s")

    # Save DataFrame
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = _OUT_DIR / "phase25_noise_results.csv"
    df.to_csv(csv_path, index=False)
    print(f"  DataFrame saved: {csv_path}")

    # Verify p=0 baseline
    atol = 1e-6
    p0_df = df[np.isclose(df["p"], 0.0)]
    baseline_ok = (p0_df["fidelity"] >= 1.0 - atol).all()
    print(f"\n  p=0 baseline check: {'PASS' if baseline_ok else 'FAIL'}")
    if not baseline_ok:
        bad = p0_df[p0_df["fidelity"] < 1.0 - atol]
        print(f"  FAILING rows:\n{bad[['noise_type','state_name','fidelity']]}")

    # Print summary tables
    _print_per_state_table(df)
    _print_summary(df)

    # Generate plots
    print(f"\n{_SEP}")
    print("  PLOTS")
    print(_SEP)
    plot_paths = []
    for ntype in NOISE_TYPES:
        p = _plot_noise_model(df, ntype, _OUT_DIR)
        plot_paths.append(p)
        print(f"  Saved: {p.name}")

    combined = _plot_all_noise_models_combined(df, _OUT_DIR, state_name="|+>")
    plot_paths.append(combined)
    print(f"  Saved: {combined.name}")

    total_elapsed = time.perf_counter() - t0
    print(_THIN)
    print(f"  Total elapsed : {total_elapsed:.1f}s")
    print(f"  Plots saved to: {_OUT_DIR}")
    print(f"  Overall baseline: {'PASS' if baseline_ok else 'FAIL'}")
    print(_SEP)

    return baseline_ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 2.5 Noise Analysis -- SIH26141",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--seed",  type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ok = run_analysis(shots=args.shots, seed=args.seed)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
