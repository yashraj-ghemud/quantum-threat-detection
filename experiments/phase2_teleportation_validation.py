"""
experiments/phase2_teleportation_validation.py
===============================================
Phase 2 -- Quantum Teleportation & Fidelity Validation Report.
SIH26141 | Blockchain & Cybersecurity.

Produces a concise ASCII validation report:
    1. Circuit overview for one representative state.
    2. Per-state fidelity results for all six standard states.
    3. Bob's recovered density matrix vs. ideal for each state.
    4. PASS/FAIL summary table.

Usage
-----
    python experiments/phase2_teleportation_validation.py
    python experiments/phase2_teleportation_validation.py --shots 2048 --seed 42

No AI/ML libraries used.
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Ensure src/ and project root importable
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
for _p in (_SRC, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from qiskit_aer import AerSimulator

from quantum.teleportation import (
    FIDELITY_THRESHOLD,
    STANDARD_STATES,
    build_teleportation_circuit,
    ideal_density_matrix,
    validate_all_standard_states,
)
from utils.config import ConfigLoader
from utils.logger import get_logger
from utils.reproducibility import get_run_context, set_seed

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_SEP  = "=" * 72
_THIN = "-" * 72


def _fidelity_bar(f: float, width: int = 30) -> str:
    """ASCII progress bar for fidelity in [0, 1]."""
    filled = int(round(f * width))
    filled = max(0, min(width, filled))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def _fmt_complex(z: complex, precision: int = 4) -> str:
    """Format a complex number compactly."""
    r, i = round(z.real, precision), round(z.imag, precision)
    if abs(i) < 1e-9:
        return f"{r:+.{precision}f}"
    sign = "+" if i >= 0 else "-"
    return f"{r:+.{precision}f}{sign}{abs(i):.{precision}f}j"


def _print_circuit_overview(theta: float, phi: float, label: str) -> None:
    """Print a brief circuit overview for one state."""
    qc = build_teleportation_circuit(theta, phi, add_barriers=False)
    print(f"\n  Representative circuit: {label}")
    print(f"  Qubits: {qc.num_qubits}  Classical bits: {qc.num_clbits}  "
          f"Depth: {qc.depth()}  Gates: {qc.size()}")
    gates = {}
    for instr in qc.data:
        name = instr.operation.name
        gates[name] = gates.get(name, 0) + 1
    gate_str = "  ".join(f"{k}x{v}" for k, v in sorted(gates.items()))
    print(f"  Gate counts: {gate_str}")


def _print_dm_comparison(name: str, bob_dm, theta: float, phi: float) -> None:
    """Print side-by-side Bob DM vs ideal DM."""
    rho_bob   = np.asarray(bob_dm)
    rho_ideal = np.asarray(ideal_density_matrix(theta, phi))
    print(f"\n  {name}  --  Bob DM vs Ideal DM (2x2)")
    print(f"  {'Bob':^40s}  {'Ideal':^40s}")
    for row_b, row_i in zip(rho_bob, rho_ideal):
        b_str = "  ".join(_fmt_complex(z) for z in row_b)
        i_str = "  ".join(_fmt_complex(z) for z in row_i)
        print(f"  [{b_str:^38s}]  [{i_str:^38s}]")
    trace_bob   = float(np.trace(rho_bob).real)
    trace_ideal = float(np.trace(rho_ideal).real)
    print(f"  Tr(rho_Bob)={trace_bob:.6f}  Tr(rho_ideal)={trace_ideal:.6f}")


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

def run_report(shots: int, seed: int) -> bool:
    """Run the full Phase 2 validation report.

    Parameters
    ----------
    shots : int
        AerSimulator shots per state.
    seed : int
        Random seed.

    Returns
    -------
    bool
        True when all states pass.
    """
    cfg = ConfigLoader()
    ctx = get_run_context(seed)
    set_seed(seed)
    backend = AerSimulator(method="density_matrix")

    print(_SEP)
    print("  PHASE 2 -- Quantum Teleportation & Fidelity Validation Report")
    print("  SIH26141 | Quantum-Inspired Cyber Threat Detection")
    print(_SEP)
    print(f"  Python seed   : {ctx['seed']}")
    print(f"  NumPy version : {ctx['numpy_version']}")
    print(f"  Simulator     : density_matrix ({cfg.simulator_backend})")
    print(f"  Shots/state   : {shots}")
    print(f"  Protocol      : Standard 3-qubit teleportation with feed-forward")
    print(f"  Threshold     : F >= {FIDELITY_THRESHOLD}")
    print(f"  Timestamp     : {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print(_SEP)

    # Circuit overview
    print("\n  CIRCUIT OVERVIEW")
    print(_THIN)
    _print_circuit_overview(float(np.pi / 2), 0.0, "|+>")
    print()
    print("  Protocol stages:")
    print("    1. State prep   : q[0] = Ry(theta) Rz(phi) |0>  (Alice's input)")
    print("    2. Bell pair    : q[1],q[2] = H(q[1]) CX(q[1]->q[2])  (shared entanglement)")
    print("    3. Alice encode : CX(q[0]->q[1])  H(q[0])")
    print("    4. Alice measure: m[0]=q[0], m[1]=q[1]")
    print("    5. Bob correct  : if m[1]=1 -> X(q[2]);  if m[0]=1 -> Z(q[2])")
    print("    6. Extract Bob  : save_density_matrix(q[2])")

    t_start = time.perf_counter()

    # Run full validation
    print(f"\n{_SEP}")
    print("  PER-STATE VALIDATION")
    print(_SEP)

    results = validate_all_standard_states(shots=shots, seed=seed, backend=backend)

    for name, r in results.items():
        status = "PASS" if r.passed else "FAIL"
        bar    = _fidelity_bar(min(r.fidelity, 1.0))
        print(
            f"\n  {status}  {name:<6}  "
            f"F={r.fidelity:.10f}  {bar}"
        )
        _print_dm_comparison(name, r.bob_density_matrix, r.theta, r.phi)

    # Summary table
    elapsed   = time.perf_counter() - t_start
    all_pass  = all(r.passed for r in results.values())
    n_pass    = sum(r.passed for r in results.values())

    print(f"\n{_SEP}")
    print("  SUMMARY TABLE")
    print(_SEP)
    print(f"  {'State':<8}  {'theta':>8}  {'phi':>8}  {'Fidelity':>14}  {'Status'}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*14}  {'-'*6}")
    for name, r in results.items():
        status = "PASS" if r.passed else "FAIL"
        print(
            f"  {name:<8}  {r.theta:>8.4f}  {r.phi:>8.4f}  "
            f"{r.fidelity:>14.10f}  {status}"
        )
    print(_THIN)
    print(f"  Result  : {n_pass}/6 states PASS")
    print(f"  Overall : {'ALL STATES PASS' if all_pass else 'SOME STATES FAILED'}")
    print(f"  Elapsed : {elapsed:.3f}s")
    print(_SEP)

    # Correlator reference
    print("\n  STANDARD STATE REFERENCE (Bloch sphere angles)")
    print(f"  {'Name':<8}  {'theta/pi':>10}  {'phi/pi':>10}  {'alpha':>18}  {'beta':>20}")
    print(f"  {'-'*8}  {'-'*10}  {'-'*10}  {'-'*18}  {'-'*20}")
    for name, theta, phi in STANDARD_STATES:
        from quantum.teleportation import prepare_input_state
        sv = prepare_input_state(theta, phi)
        print(
            f"  {name:<8}  {theta/np.pi:>10.4f}  {phi/np.pi:>10.4f}  "
            f"  {_fmt_complex(sv[0]):>18}  {_fmt_complex(sv[1]):>20}"
        )
    print()
    return all_pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 2 Teleportation Validation -- SIH26141",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--shots", type=int, default=4096,
                        help="AerSimulator shots per state.")
    parser.add_argument("--seed",  type=int, default=42,
                        help="Random seed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    success = run_report(shots=args.shots, seed=args.seed)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
