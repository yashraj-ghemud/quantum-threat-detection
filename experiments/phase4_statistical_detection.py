"""
experiments/phase4_statistical_detection.py
=============================================
Phase 4 -- Statistical Threat Detection Experiment.
SIH26141 | Blockchain & Cybersecurity.

Steps
-----
1.  Generate legitimate baseline sessions using Phase 3 QDS.
2.  Build ThreatDetector and calibrate thresholds.
3.  Create test sessions with controlled deviation levels.
4.  Compute fingerprints and anomaly scores.
5.  Classify each session.
6.  Print a clear pandas table of results.
7.  Print calibrated thresholds.
8.  Print a short statistical interpretation.

No AI/ML used.
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=DeprecationWarning)

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from qds.pauli_states import EIGENSTATE_LABELS, get_eigenstate
from qds.signature import generate_signature
from qds.verification import verify_signature
from security.detector import ThreatDetector
from security.fingerprint import build_fingerprint
from security.anomaly import compute_anomaly_score
from security.thresholds import percentile_calibrate
from utils.config import ConfigLoader
from utils.logger import get_logger
from utils.reproducibility import get_run_context, set_seed

logger = get_logger(__name__)

_SEP  = "=" * 72
_THIN = "-" * 72


# ---------------------------------------------------------------------------
# Session generators
# ---------------------------------------------------------------------------

def _legit_vr(length, seed):
    sig = generate_signature("legit", length=length, seed=seed)
    return verify_signature(sig)


def _partial_tamper_vr(length, seed, tamper_frac):
    """Replace tamper_frac fraction of elements with wrong states."""
    sig = generate_signature("tamper", length=length, seed=seed)
    received = [e.statevector.copy() for e in sig.elements]
    n_tamper = max(1, int(length * tamper_frac))
    for i in range(n_tamper):
        orig = sig.elements[i].label
        alt  = next(l for l in EIGENSTATE_LABELS if l != orig)
        received[i] = get_eigenstate(alt).statevector
    return verify_signature(sig, received_statevectors=received)


def _full_tamper_vr(length, seed):
    return _partial_tamper_vr(length, seed, tamper_frac=1.0)


# ---------------------------------------------------------------------------
# Build test sessions
# ---------------------------------------------------------------------------

def _build_test_sessions(length: int, seed_offset: int):
    """Return list of (session_type, VerificationResult)."""
    sessions = []
    for i in range(3):
        sessions.append(("LEGIT",         _legit_vr(length, seed_offset + i)))
    for frac, label in [(0.10, "TAMPER_10%"), (0.30, "TAMPER_30%"),
                        (0.50, "TAMPER_50%"), (0.75, "TAMPER_75%"),
                        (1.00, "TAMPER_100%")]:
        sessions.append((label, _partial_tamper_vr(length, seed_offset + 10, frac)))
    return sessions


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

def run_experiment(n_baseline: int, sig_length: int, seed: int) -> bool:
    cfg = ConfigLoader()
    ctx = get_run_context(seed)
    set_seed(seed)

    print(_SEP)
    print("  PHASE 4 -- Statistical Threat Detection Experiment")
    print("  SIH26141 | Quantum-Inspired Cyber Threat Detection")
    print(_SEP)
    print(f"  Seed           : {ctx['seed']}")
    print(f"  NumPy          : {ctx['numpy_version']}")
    print(f"  Baseline size  : {n_baseline} sessions")
    print(f"  Signature len  : {sig_length} elements")
    print(f"  Timestamp      : {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print(_SEP)

    t0 = time.perf_counter()

    # ------------------------------------------------------------------
    # 1. Build baseline
    # ------------------------------------------------------------------
    print(f"\n  [1] Building legitimate baseline ({n_baseline} sessions)...")
    detector = ThreatDetector(calibration_method="percentile",
                              warn_percentile=75.0, crit_percentile=95.0)
    baseline_vrs = [_legit_vr(sig_length, seed=i) for i in range(n_baseline)]
    detector.add_baseline_sessions(baseline_vrs)
    detector.calibrate()

    cal = detector.calibration
    bl_scores = cal.baseline_scores
    print(f"  Baseline anomaly scores: mean={cal.baseline_mean:.4f} "
          f"std={cal.baseline_std:.4f} "
          f"min={cal.baseline_min:.4f} max={cal.baseline_max:.4f}")

    # ------------------------------------------------------------------
    # 2. Print calibrated thresholds
    # ------------------------------------------------------------------
    print(f"\n{_SEP}")
    print("  CALIBRATED THRESHOLDS")
    print(_SEP)
    print(f"  Method   : {detector.thresholds.method}")
    print(f"  Warning  : {detector.thresholds.warning:.6f}  "
          f"(score >= warning -> SUSPICIOUS)")
    print(f"  Critical : {detector.thresholds.critical:.6f}  "
          f"(score >= critical -> THREAT)")

    # ------------------------------------------------------------------
    # 3. Run test sessions and collect results
    # ------------------------------------------------------------------
    print(f"\n{_SEP}")
    print("  [3] Running test sessions...")
    test_sessions = _build_test_sessions(sig_length, seed_offset=200)
    rows = []
    for session_type, vr in test_sessions:
        dr = detector.detect(vr)
        rows.append({
            "session_type":   session_type,
            "mismatch_rate":  round(dr.mismatch_rate, 4),
            "anomaly_score":  round(dr.anomaly_score, 6),
            "z_score":        round(dr.z_score, 3),
            "classification": dr.classification,
        })

    # ------------------------------------------------------------------
    # 4. Print results table
    # ------------------------------------------------------------------
    df = pd.DataFrame(rows)
    print(f"\n{_SEP}")
    print("  DETECTION RESULTS TABLE")
    print(_SEP)
    print(df.to_string(index=False))
    print(_THIN)

    # ------------------------------------------------------------------
    # 5. Baseline statistics section
    # ------------------------------------------------------------------
    print(f"\n{_SEP}")
    print("  BASELINE MEASUREMENT STATISTICS (mean over all baseline sessions)")
    print(_SEP)
    from security.statistics import stats_from_verification
    bl_stats = [stats_from_verification(vr) for vr in baseline_vrs]
    print(f"  mean(match_rate)     : {np.mean([s.match_rate for s in bl_stats]):.6f}")
    print(f"  mean(mismatch_rate)  : {np.mean([s.mismatch_rate for s in bl_stats]):.6f}")
    print(f"  mean(mean_outcome)   : {np.mean([s.mean for s in bl_stats]):.6f}")
    print(f"  mean(variance)       : {np.mean([s.variance for s in bl_stats]):.6f}")
    print(f"  mean(p_plus)         : {np.mean([s.p_plus for s in bl_stats]):.6f}")

    # Per-basis
    for basis in ("x", "y", "z"):
        mm_vals = [s.basis_stats[basis].mismatch_rate for s in bl_stats
                   if s.basis_stats[basis].count > 0]
        if mm_vals:
            print(f"  baseline {basis.upper()} mismatch  : {np.mean(mm_vals):.6f}")

    # ------------------------------------------------------------------
    # 6. Statistical interpretation
    # ------------------------------------------------------------------
    print(f"\n{_SEP}")
    print("  STATISTICAL INTERPRETATION")
    print(_SEP)
    print(
        "  - Anomaly score = 0.40*|delta_mismatch| + 0.25*|delta_mean|/2\n"
        "                  + 0.20*|delta_p_plus| + 0.15*|delta_basis_mismatch|\n"
        "  - Thresholds derived from 75th/95th percentile of baseline scores.\n"
        "  - Legitimate sessions score near 0 (baseline reproduces itself).\n"
        "  - 100% tampered sessions show high mismatch_rate and THREAT classification.\n"
        "  - Z-score measures how many standard deviations the observed mismatch\n"
        "    rate lies above the baseline mean."
    )
    for row in rows:
        verdict = row["classification"]
        if verdict == "NORMAL":
            interp = "within expected baseline variation"
        elif verdict == "SUSPICIOUS":
            interp = "elevated deviation -- possible tampering"
        else:
            interp = "high deviation -- likely attack"
        print(f"  {row['session_type']:15s}  score={row['anomaly_score']:.4f}  "
              f"z={row['z_score']:+.2f}  -> {interp}")

    elapsed = time.perf_counter() - t0
    print(f"\n{_SEP}")
    print(f"  Elapsed: {elapsed:.2f}s")
    print(_SEP)

    # Success check: legit sessions should not be THREAT
    legit_rows = [r for r in rows if r["session_type"] == "LEGIT"]
    all_legit_ok = all(r["classification"] != "THREAT" for r in legit_rows)
    print(f"  Legit sessions not classified as THREAT: {all_legit_ok}")
    return all_legit_ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 4 Statistical Detection -- SIH26141",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--baseline", type=int, default=12,
                        help="Number of legitimate baseline sessions.")
    parser.add_argument("--length",   type=int, default=32,
                        help="Signature length (elements per session).")
    parser.add_argument("--seed",     type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ok = run_experiment(
        n_baseline=args.baseline,
        sig_length=args.length,
        seed=args.seed,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
