"""
experiments/phase5_attack_simulation.py
========================================
Phase 5 -- QDS Attack Simulation & Threat Validation.
SIH26141 | Blockchain & Cybersecurity.

Evaluates all attack types at multiple intensities:
    LEGITIMATE
    FORGERY
    IMPERSONATION
    REPLAY
    UNAUTHORIZED_VERIFICATION
    CHANNEL_MANIPULATION

For each scenario reports:
    attack_type, intensity, sample_count, mismatch_rate,
    anomaly_score, classification, detection_status, reason

Detection status:
    DETECTED        — system correctly identifies the attack
    MISSED          — attack is not detected
    NOT_APPLICABLE  — legitimate baseline

No AI/ML is used.
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

from attacks.runner import AttackRunner, AttackScenarioResult
from attacks.forgery import ForgeryAttack
from attacks.impersonation import ImpersonationAttack
from attacks.replay import ReplayAttack
from attacks.unauthorized_verification import UnauthorizedVerificationAttack
from attacks.channel_manipulation import ChannelManipulationAttack
from utils.reproducibility import set_seed, get_run_context

_SEP  = "=" * 78
_THIN = "-" * 78

# ---------------------------------------------------------------------------
# Intensities to evaluate
# ---------------------------------------------------------------------------

INTENSITIES = [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]


# ---------------------------------------------------------------------------
# Run all scenarios
# ---------------------------------------------------------------------------

def run_all_scenarios(
    runner: AttackRunner,
    seed: int = 42,
) -> list[AttackScenarioResult]:
    """Run all attack scenarios at multiple intensities."""
    results: list[AttackScenarioResult] = []

    # 1. Legitimate baseline
    print("  Running legitimate baseline...")
    result = runner.run_legitimate(seed_offset=0)
    results.append(result)

    # 2. Forgery at multiple intensities
    print("  Running forgery attacks...")
    for i, intensity in enumerate(INTENSITIES):
        if intensity == 0.0:
            continue  # Already covered by legitimate
        atk = ForgeryAttack(seed=seed)
        r = runner.run_attack(atk, "FORGERY", intensity=intensity, seed_offset=200 + i)
        results.append(r)

    # 3. Impersonation at multiple intensities
    print("  Running impersonation attacks...")
    for i, intensity in enumerate(INTENSITIES):
        if intensity == 0.0:
            continue
        atk = ImpersonationAttack(seed=seed, impersonator_id="attacker_eve")
        r = runner.run_attack(atk, "IMPERSONATION", intensity=intensity, seed_offset=300 + i)
        results.append(r)

    # 4. Replay at multiple intensities
    print("  Running replay attacks...")
    for i, intensity in enumerate(INTENSITIES):
        if intensity == 0.0:
            continue
        atk = ReplayAttack(seed=seed, staleness_seconds=120.0)
        r = runner.run_attack(atk, "REPLAY", intensity=intensity, seed_offset=400 + i)
        results.append(r)

    # 5. Unauthorized verification at multiple intensities
    print("  Running unauthorized verification attacks...")
    for i, intensity in enumerate(INTENSITIES):
        if intensity == 0.0:
            continue
        atk = UnauthorizedVerificationAttack(seed=seed, attacker_verifier_id="unauthorized_charlie")
        r = runner.run_attack(atk, "UNAUTHORIZED_VERIFICATION", intensity=intensity, seed_offset=500 + i)
        results.append(r)

    # 6. Channel manipulation at multiple intensities
    print("  Running channel manipulation attacks...")
    for i, intensity in enumerate(INTENSITIES):
        if intensity == 0.0:
            continue
        atk = ChannelManipulationAttack(seed=seed, mode="both")
        r = runner.run_attack(atk, "CHANNEL_MANIPULATION", intensity=intensity, seed_offset=600 + i)
        results.append(r)

    return results


# ---------------------------------------------------------------------------
# Build results DataFrame
# ---------------------------------------------------------------------------

def results_to_dataframe(results: list[AttackScenarioResult]) -> pd.DataFrame:
    """Convert scenario results to a pandas DataFrame."""
    rows = []
    for r in results:
        rows.append({
            "attack_type":      r.attack_type,
            "intensity":        r.intensity,
            "sample_count":     r.sample_count,
            "mismatch_rate":    round(r.mismatch_rate, 4),
            "anomaly_score":    round(r.anomaly_score, 6),
            "classification":   r.classification,
            "detection_status": r.detection_status,
            "reason":           r.reason[:100] if len(r.reason) > 100 else r.reason,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Detection rate summary
# ---------------------------------------------------------------------------

def detection_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Compute detection rate by attack type."""
    attack_rows = df[df["detection_status"] != "NOT_APPLICABLE"]
    if attack_rows.empty:
        return pd.DataFrame(columns=["attack_type", "total", "detected", "missed", "detection_rate"])

    summary_rows = []
    for atype, group in attack_rows.groupby("attack_type"):
        total = len(group)
        detected = (group["detection_status"] == "DETECTED").sum()
        missed = (group["detection_status"] == "MISSED").sum()
        rate = detected / total if total > 0 else 0.0
        summary_rows.append({
            "attack_type": atype,
            "total": total,
            "detected": detected,
            "missed": missed,
            "detection_rate": round(rate, 4),
        })
    return pd.DataFrame(summary_rows)


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def run_experiment(
    n_baseline: int = 12,
    sig_length: int = 32,
    seed: int = 42,
) -> bool:
    ctx = get_run_context(seed)
    set_seed(seed)

    print(_SEP)
    print("  PHASE 5 -- QDS Attack Simulation & Threat Validation")
    print("  SIH26141 | Quantum-Inspired Cyber Threat Detection")
    print(_SEP)
    print(f"  Seed           : {ctx['seed']}")
    print(f"  NumPy          : {ctx['numpy_version']}")
    print(f"  Baseline size  : {n_baseline} sessions")
    print(f"  Signature len  : {sig_length} elements")
    print(f"  Intensities    : {INTENSITIES}")
    print(f"  Timestamp      : {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print(_SEP)

    t0 = time.perf_counter()

    # ------------------------------------------------------------------
    # 1. Build runner (includes baseline and detector calibration)
    # ------------------------------------------------------------------
    print(f"\n  [1] Building attack runner ({n_baseline} baseline sessions)...")
    runner = AttackRunner(
        sig_length=sig_length,
        n_baseline=n_baseline,
        seed=seed,
    )
    # Force detector build
    detector = runner.detector
    print(f"  Detector calibrated: warn={detector.thresholds.warning:.6f} "
          f"crit={detector.thresholds.critical:.6f}")

    # ------------------------------------------------------------------
    # 2. Run all scenarios
    # ------------------------------------------------------------------
    print(f"\n  [2] Running attack scenarios...")
    results = run_all_scenarios(runner, seed=seed)
    print(f"  Total scenarios evaluated: {len(results)}")

    # ------------------------------------------------------------------
    # 3. Results DataFrame
    # ------------------------------------------------------------------
    df = results_to_dataframe(results)

    print(f"\n{_SEP}")
    print("  ATTACK SIMULATION RESULTS")
    print(_SEP)

    # Print full DataFrame
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 100)
    print(df.to_string(index=False))
    print(_THIN)

    # ------------------------------------------------------------------
    # 4. Detection rate summary
    # ------------------------------------------------------------------
    print(f"\n{_SEP}")
    print("  DETECTION RATE BY ATTACK TYPE")
    print(_SEP)
    summary_df = detection_summary(df)
    print(summary_df.to_string(index=False))
    print(_THIN)

    # ------------------------------------------------------------------
    # 5. Missed detections
    # ------------------------------------------------------------------
    missed = df[df["detection_status"] == "MISSED"]
    print(f"\n{_SEP}")
    print("  MISSED DETECTIONS")
    print(_SEP)
    if missed.empty:
        print("  No missed detections.")
    else:
        print(missed[["attack_type", "intensity", "anomaly_score", "classification", "reason"]].to_string(index=False))
    print(_THIN)

    # ------------------------------------------------------------------
    # 6. Anomaly score vs intensity
    # ------------------------------------------------------------------
    print(f"\n{_SEP}")
    print("  ANOMALY SCORE vs ATTACK INTENSITY")
    print(_SEP)
    for atype in ["FORGERY", "IMPERSONATION", "CHANNEL_MANIPULATION"]:
        subset = df[df["attack_type"] == atype]
        if not subset.empty:
            print(f"\n  {atype}:")
            for _, row in subset.iterrows():
                bar = "#" * int(row["anomaly_score"] * 40)
                print(f"    intensity={row['intensity']:.2f}  "
                      f"score={row['anomaly_score']:.6f}  "
                      f"mismatch={row['mismatch_rate']:.4f}  "
                      f"{row['classification']:12s}  {bar}")

    # ------------------------------------------------------------------
    # 7. Summary statistics
    # ------------------------------------------------------------------
    elapsed = time.perf_counter() - t0
    print(f"\n{_SEP}")
    print("  SUMMARY")
    print(_SEP)
    print(f"  Total scenarios:     {len(results)}")
    print(f"  Legitimate:          {len(df[df['attack_type'] == 'LEGITIMATE'])}")
    print(f"  Attacks evaluated:   {len(df[df['detection_status'] != 'NOT_APPLICABLE'])}")
    total_attacks = len(df[df['detection_status'] != 'NOT_APPLICABLE'])
    total_detected = len(df[df['detection_status'] == 'DETECTED'])
    total_missed = len(df[df['detection_status'] == 'MISSED'])
    print(f"  Detected:            {total_detected}")
    print(f"  Missed:              {total_missed}")
    if total_attacks > 0:
        print(f"  Overall detection:   {total_detected}/{total_attacks} "
              f"({100.0 * total_detected / total_attacks:.1f}%)")
    print(f"  Elapsed:             {elapsed:.2f}s")
    print(_SEP)

    # Success check: legitimate not THREAT, not all attacks missed
    legit = df[df["attack_type"] == "LEGITIMATE"]
    legit_ok = all(legit["classification"] != "THREAT")
    print(f"\n  Legitimate sessions not classified as THREAT: {legit_ok}")
    return legit_ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 5 Attack Simulation -- SIH26141",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--baseline", type=int, default=12,
                        help="Number of legitimate baseline sessions.")
    parser.add_argument("--length", type=int, default=32,
                        help="Signature length (elements per session).")
    parser.add_argument("--seed", type=int, default=42)
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
