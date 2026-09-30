"""
experiments/phase1_bell_validation.py
======================================
Phase 1 — Bell State & Entanglement Validation Report.
SIH26141 | Blockchain & Cybersecurity.

Produces a concise, formatted validation report for all four Bell states by:
    1. Building each circuit and printing its gate decomposition.
    2. Computing exact Pauli correlators from the statevector.
    3. Running AerSimulator shot-based measurement.
    4. Validating against expected correlator signatures.
    5. Printing a per-state summary and an overall PASS/FAIL banner.

Usage
-----
    python experiments/phase1_bell_validation.py
    python experiments/phase1_bell_validation.py --shots 2048 --seed 0

No AI/ML libraries are used in this project.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

# Ensure both src/ and project root are importable when running as a script
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
for _p in (_SRC, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from qiskit_aer import AerSimulator

from quantum.bell_states import (
    BELL_CORRELATORS,
    compute_pauli_correlations,
    get_density_matrix,
    get_statevector,
    prepare_bell_state,
    simulate_bell_state,
    validate_all_bell_states,
)
from utils.config import ConfigLoader
from utils.logger import get_logger
from utils.reproducibility import set_seed, get_run_context

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_SEP = "=" * 72
_THIN = "-" * 72
_STATE_SEP = "-" * 72


def _corr_bar(value: float, width: int = 20) -> str:
    """Render a simple ASCII bar for a correlator in [-1, +1]."""
    half = width // 2
    pos = int(round((value + 1.0) / 2.0 * (width - 1)))
    pos = max(0, min(width - 1, pos))
    bar = [" "] * width
    bar[half] = "|"       # zero line
    lo, hi = min(pos, half), max(pos, half)
    for i in range(lo, hi + 1):
        bar[i] = "#"
    label = f"{value:+.4f}"
    return "[" + "".join(bar) + f"]  {label}"


def _print_circuit_summary(label: str) -> None:
    """Print gate-level circuit summary for a Bell state."""
    qc = prepare_bell_state(label)
    print(f"\n  Circuit: |{label}>")
    print(f"  Qubits : {qc.num_qubits}   Depth: {qc.depth()}")
    gates = [f"{instr.operation.name}({','.join(str(q._index) for q in instr.qubits)})"
             for instr in qc.data]
    print(f"  Gates  : {' -> '.join(gates)}")


def _print_statevector(label: str) -> None:
    """Print the non-zero amplitudes of the Bell state."""
    qc = prepare_bell_state(label)
    sv = get_statevector(qc).data
    basis = ["|00>", "|01>", "|10>", "|11>"]
    terms = []
    for i, amp in enumerate(sv):
        if abs(amp) > 1e-9:
            sign = "+" if amp.real >= 0 else "-"
            terms.append(f"{sign}{abs(amp):.4f}*{basis[i]}")
    expr = " ".join(terms).lstrip("+").strip()
    norm = float(np.linalg.norm(sv))
    print(f"  |psi>   = {expr}")
    print(f"  norm    = {norm:.8f}  {'OK' if abs(norm - 1.0) < 1e-6 else 'NORM FAIL'}")


def _print_pauli_correlators(label: str) -> None:
    """Print Pauli correlators with ASCII bar visualisation."""
    qc = prepare_bell_state(label)
    xx, yy, zz = compute_pauli_correlations(qc)
    exp_xx, exp_yy, exp_zz = BELL_CORRELATORS[label]
    atol = 1e-6

    ok = lambda v, e: "OK" if abs(v - e) <= atol else f"FAIL (expect {e:+.1f})"
    print(f"  <XX>  = {_corr_bar(xx)}  {ok(xx, exp_xx)}")
    print(f"  <YY>  = {_corr_bar(yy)}  {ok(yy, exp_yy)}")
    print(f"  <ZZ>  = {_corr_bar(zz)}  {ok(zz, exp_zz)}")


def _print_shot_results(label: str, shots: int, seed: int,
                        backend: AerSimulator) -> None:
    """Print shot-based measurement outcome distribution."""
    qc = prepare_bell_state(label)
    counts = simulate_bell_state(qc, shots=shots, seed=seed, backend=backend)
    total = sum(counts.values())
    print(f"  Shots  : {total}")
    for outcome in sorted(counts):
        p = counts[outcome] / total
        bar = "#" * int(p * 40)
        print(f"  |{outcome}>  : {counts[outcome]:5d} / {total}  ({p:.3f})  {bar}")


def _print_density_matrix_info(label: str) -> None:
    """Print density matrix diagnostics."""
    qc = prepare_bell_state(label)
    dm = get_density_matrix(qc)
    rho = dm.data
    trace = float(np.trace(rho).real)
    tr_rho2 = float(np.trace(rho @ rho).real)
    hermitian = np.allclose(rho, rho.conj().T, atol=1e-9)
    print(f"  Tr(rho)   = {trace:.8f}  {'OK' if abs(trace - 1.0) < 1e-6 else 'FAIL'}")
    print(f"  Tr(rho^2) = {tr_rho2:.8f}  {'OK pure state' if abs(tr_rho2 - 1.0) < 1e-6 else 'FAIL mixed state'}")
    print(f"  rho=rho+  : {'OK Hermitian' if hermitian else 'FAIL NOT Hermitian'}")


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

def run_report(shots: int, seed: int) -> bool:
    """Run the full Phase 1 validation report.

    Parameters
    ----------
    shots:
        Number of AerSimulator shots per state.
    seed:
        Random seed for reproducibility.

    Returns
    -------
    bool
        ``True`` if all four Bell states pass validation.
    """
    cfg = ConfigLoader()
    ctx = get_run_context(seed)
    set_seed(seed)
    backend = AerSimulator()

    print(_SEP)
    print("  PHASE 1 -- Bell State & Entanglement Validation Report")
    print("  SIH26141 | Quantum-Inspired Cyber Threat Detection")
    print(_SEP)
    print(f"  Python seed   : {ctx['seed']}")
    print(f"  NumPy version : {ctx['numpy_version']}")
    print(f"  Simulator     : {cfg.simulator_backend}")
    print(f"  Shots/state   : {shots}")
    print(f"  Timestamp     : {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print(_SEP)

    t_start = time.perf_counter()

    # --- per-state detail ---
    for label in ("phi+", "phi-", "psi+", "psi-"):
        exp_xx, exp_yy, exp_zz = BELL_CORRELATORS[label]
        print(f"\n{_STATE_SEP}")
        print(f"  STATE  :  |{label}>     Expected correlators: "
              f"<XX>={exp_xx:+.0f}  <YY>={exp_yy:+.0f}  <ZZ>={exp_zz:+.0f}")
        print(f"{_STATE_SEP}")
        _print_circuit_summary(label)
        _print_statevector(label)
        print()
        _print_pauli_correlators(label)
        print()
        _print_shot_results(label, shots=shots, seed=seed, backend=backend)
        print()
        _print_density_matrix_info(label)

    # --- bulk validation ---
    print(f"\n{_SEP}")
    print("  VALIDATION SUMMARY")
    print(_SEP)

    results = validate_all_bell_states(shots=shots, seed=seed, backend=backend)
    all_pass = True

    for label, r in results.items():
        status = "PASS" if r.passed else "FAIL"
        all_pass = all_pass and r.passed
        print(
            f"  {status}  |{r.label:<5}  detected={r.detected:<5}  "
            f"XX={r.xx:+.4f}  YY={r.yy:+.4f}  ZZ={r.zz:+.4f}  "
            f"norm={r.norm:.6f}"
        )

    elapsed = time.perf_counter() - t_start
    print(_THIN)
    print(f"  Overall result : {'ALL 4 STATES PASS' if all_pass else 'SOME STATES FAILED'}")
    print(f"  Elapsed time   : {elapsed:.3f}s")
    print(_SEP)

    # --- correlator reference table ---
    print("\n  Expected Pauli Correlator Reference Table")
    print(f"  {'State':<8}  {'<XX>':>6}  {'<YY>':>6}  {'<ZZ>':>6}")
    print(f"  {'--------'}  {'------'}  {'------'}  {'------'}")
    for label, (xx, yy, zz) in BELL_CORRELATORS.items():
        print(f"  |{label:<7}  {xx:>+6.1f}  {yy:>+6.1f}  {zz:>+6.1f}")
    print()

    return all_pass


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Phase 1 Bell State Validation — SIH26141",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--shots", type=int, default=2048,
        help="Number of AerSimulator shots per Bell state.",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    success = run_report(shots=args.shots, seed=args.seed)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
