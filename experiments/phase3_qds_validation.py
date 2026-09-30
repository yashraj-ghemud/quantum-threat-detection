"""
experiments/phase3_qds_validation.py
======================================
Phase 3 -- QDS + Pauli Eigenstates Validation Report.
SIH26141 | Blockchain & Cybersecurity.

Sections
--------
1.  Six Pauli eigenstates + basis + Bloch vector
2.  Projective measurement probabilities for all states x all bases
3.  Generated QDS signature summary
4.  Legitimate verification result
5.  Modified-signature verification result
6.  Teleportation inside the live QDSScheme key-distribution path
7.  End-to-end keygen -> sign -> verify round trip

Usage
-----
    python experiments/phase3_qds_validation.py
    python experiments/phase3_qds_validation.py --length 16 --seed 42

No AI/ML libraries used.
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

from qds.pauli_states import (
    EIGENSTATE_LABELS,
    all_eigenstates,
    projective_measurement_probs,
)
from qds.key_distribution import distribute_public_key_verbose
from qds.keygen import generate_key_pair
from qds.scheme import QDSScheme
from qds.signature import generate_signature, signature_summary
from qds.verification import DEFAULT_ACCEPT_THRESHOLD, verify_signature
from quantum.teleportation import (
    FIDELITY_THRESHOLD,
    STANDARD_STATES,
    calculate_teleportation_fidelity,
)
from utils.config import ConfigLoader
from utils.logger import get_logger
from utils.reproducibility import get_run_context, set_seed

logger = get_logger(__name__)

_SEP  = "=" * 72
_THIN = "-" * 72


# ---------------------------------------------------------------------------
# Section 1: Eigenstates
# ---------------------------------------------------------------------------

def _section_eigenstates() -> None:
    print(f"\n{_SEP}")
    print("  SECTION 1 -- Six Pauli Eigenstates")
    print(_SEP)
    states = all_eigenstates()
    rows = []
    for lbl, s in states.items():
        bv = s.bloch_vector
        rows.append({
            "Label":      lbl,
            "Basis":      s.basis.upper(),
            "Eigenvalue": f"{s.eigenvalue:+d}",
            "alpha":      f"{s.statevector[0].real:+.4f}+{s.statevector[0].imag:+.4f}j",
            "beta":       f"{s.statevector[1].real:+.4f}+{s.statevector[1].imag:+.4f}j",
            "Bloch(x,y,z)": f"({bv[0]:+.3f},{bv[1]:+.3f},{bv[2]:+.3f})",
            "Norm":       round(float(np.linalg.norm(s.statevector)), 9),
        })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))


# ---------------------------------------------------------------------------
# Section 2: Measurement probabilities
# ---------------------------------------------------------------------------

def _section_measurement_probs() -> None:
    print(f"\n{_SEP}")
    print("  SECTION 2 -- Projective Measurement Probabilities")
    print(_SEP)
    states = all_eigenstates()
    rows = []
    for lbl, s in states.items():
        for basis in ("x", "y", "z"):
            pp, pm = projective_measurement_probs(s.statevector, basis)
            rows.append({
                "State": lbl,
                "Meas basis": basis.upper(),
                "P(+1)": round(pp, 6),
                "P(-1)": round(pm, 6),
                "Sum":   round(pp + pm, 9),
            })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))


# ---------------------------------------------------------------------------
# Section 3: Signature summary
# ---------------------------------------------------------------------------

def _section_signature(length: int, seed: int) -> object:
    print(f"\n{_SEP}")
    print("  SECTION 3 -- QDS Signature Generation")
    print(_SEP)
    sig = generate_signature("phase3_demo", length=length, seed=seed)
    print(signature_summary(sig))
    return sig


# ---------------------------------------------------------------------------
# Section 4: Legitimate verification
# ---------------------------------------------------------------------------

def _section_legit_verification(sig) -> None:
    print(f"\n{_SEP}")
    print("  SECTION 4 -- Legitimate Verification (unmodified signature)")
    print(_SEP)
    r = verify_signature(sig, threshold=DEFAULT_ACCEPT_THRESHOLD)
    verdict = "ACCEPTED" if r.accepted else "REJECTED"
    print(f"  Verdict            : {verdict}")
    print(f"  Verification score : {r.verification_score:.6f}")
    print(f"  Threshold          : {r.threshold:.4f}")
    print(f"  Matches / Total    : {r.matches} / {r.total_elements}")
    print(f"  Mismatches         : {r.mismatches}")
    print(f"\n  Per-element results:")
    print(f"  {'Pos':>4}  {'Expected':>8}  {'Basis':>5}  {'P(+1)':>7}  {'P(-1)':>7}  {'Meas EV':>7}  {'Match'}")
    print(f"  {'-'*4}  {'-'*8}  {'-'*5}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*5}")
    for er in r.element_results:
        match_str = "OK" if er.match else "FAIL"
        print(
            f"  {er.position:>4}  {er.expected_label:>8}  {er.expected_basis:>5}  "
            f"{er.p_plus:>7.4f}  {er.p_minus:>7.4f}  {er.measured_eigenvalue:>+7d}  {match_str}"
        )


# ---------------------------------------------------------------------------
# Section 5: Modified-signature verification
# ---------------------------------------------------------------------------

def _section_modified_verification(sig) -> None:
    print(f"\n{_SEP}")
    print("  SECTION 5 -- Modified Signature Verification")
    print(_SEP)
    # Replace first 3 elements with a different state
    states = all_eigenstates()
    received = [e.statevector.copy() for e in sig.elements]
    n_tampered = 3
    for i in range(min(n_tampered, sig.length)):
        original_label = sig.elements[i].label
        alt_label = next(l for l in EIGENSTATE_LABELS if l != original_label)
        received[i] = states[alt_label].statevector
        print(f"  Tampered pos {i}: replaced {original_label!r} -> {alt_label!r}")

    r = verify_signature(sig, received_statevectors=received, threshold=DEFAULT_ACCEPT_THRESHOLD)
    verdict = "ACCEPTED" if r.accepted else "REJECTED"
    print(f"\n  Verdict            : {verdict}")
    print(f"  Verification score : {r.verification_score:.6f}")
    print(f"  Threshold          : {r.threshold:.4f}")
    print(f"  Matches / Total    : {r.matches} / {r.total_elements}")
    print(f"  Mismatches         : {r.mismatches}")


# ---------------------------------------------------------------------------
# Section 6: Teleportation fidelity
# ---------------------------------------------------------------------------

def _section_teleportation(seed: int) -> bool:
    """Validate the teleportation step the live QDS scheme actually runs.

    This is deliberately **not** a standalone fidelity check on abstract
    Bloch angles.  It teleports a real signer key table through
    ``qds.key_distribution`` -- the same code path ``QDSScheme`` uses when
    ``distribute=True`` -- and asserts both that fidelity meets the Phase 2
    threshold and that the verifier reconstructs the key table correctly.
    """
    print(f"\n{_SEP}")
    print("  SECTION 6 -- Teleportation Inside QDS Key Distribution")
    print(_SEP)

    table_size = 12
    priv, _ = generate_key_pair(
        signer_id="signer_alice",
        table_size=table_size,
        private_seed=bytes([seed % 256]) * 32,
    )

    print("  Teleporting the signer's key table to the verifier")
    print(f"  (Bell pair -> Bell measurement -> Pauli correction), n={table_size}\n")

    res = distribute_public_key_verbose(priv, shots=1024, seed=seed)

    print(f"  {'idx':>4}  {'sent':>6}  {'received':>9}  {'corr':>6}  "
          f"{'fidelity':>12}  {'status'}")
    print(f"  {'-'*4}  {'-'*6}  {'-'*9}  {'-'*6}  {'-'*12}  {'-'*6}")

    all_pass = True
    for i, (sent, got, fid, bits) in enumerate(
        zip(res.sent_labels, res.received_labels, res.fidelities, res.correction_bits)
    ):
        ok = (sent == got) and (fid >= FIDELITY_THRESHOLD)
        all_pass = all_pass and ok
        print(
            f"  {i:>4}  {sent:>6}  {got:>9}  {str(bits):>6}  "
            f"{fid:>12.10f}  {'PASS' if ok else 'FAIL'}"
        )

    print(_THIN)
    print(f"  Mean channel fidelity       : {res.mean_fidelity:.10f}")
    print(f"  Key-table reconstruction    : "
          f"{res.table_size - res.reconstruction_errors}/{res.table_size} "
          f"({res.reconstruction_accuracy * 100:.2f}%)")
    print(f"  All states pass F >= {FIDELITY_THRESHOLD}: {all_pass}")

    # Noise sweep on the same live path, so channel-manipulation attacks
    # can be related to a measured baseline.
    print(f"\n  Channel degradation on the live key-distribution path:")
    print(f"  {'noise':>14}  {'p':>6}  {'mean_F':>12}  {'recon_acc':>10}")
    print(f"  {'-'*14}  {'-'*6}  {'-'*12}  {'-'*10}")
    for noise in ("depolarizing", "bit_flip"):
        for p_noise in (0.05, 0.20):
            r = distribute_public_key_verbose(
                priv, noise_type=noise, noise_level=p_noise,
                shots=512, seed=seed, max_states=6,
            )
            print(f"  {noise:>14}  {p_noise:>6.2f}  {r.mean_fidelity:>12.6f}  "
                  f"{r.reconstruction_accuracy:>10.4f}")

    return all_pass


def _section_end_to_end(length: int, seed: int) -> bool:
    """Full keygen -> teleported distribution -> sign -> verify round trip."""
    print(f"\n{_SEP}")
    print("  SECTION 7 -- End-to-End QDSScheme Round Trip")
    print(_SEP)

    message = b"SIH26141 phase-3 end-to-end validation message"
    scheme = QDSScheme(
        signature_length=length,
        table_size=16,
        distribute=True,
        shots=512,
    )
    scheme.generate_keys(signer_id="signer_alice")
    sig = scheme.sign(message)
    ok_res = scheme.verify(sig, message)
    tampered = scheme.verify(sig, message + b"!")

    print(f"  Key id                  : {sig.key_id[:8]}...")
    print(f"  Distribution fidelity   : {scheme.public_key.distribution_fidelity:.10f}")
    print(f"  Message digest          : {sig.message_hash[:32]}...")
    print(f"  Key-derived signature   : {sig.is_key_derived}")
    print(f"  Honest verification     : score={ok_res.verification_score:.4f} "
          f"accepted={ok_res.accepted}")
    print(f"  Tampered message        : score={tampered.verification_score:.4f} "
          f"accepted={tampered.accepted}")
    print(_THIN)

    passed = ok_res.accepted and not tampered.accepted
    print(f"  Round trip: {'PASS' if passed else 'FAIL'}")
    return passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_validation(length: int, seed: int) -> bool:
    cfg = ConfigLoader()
    ctx = get_run_context(seed)
    set_seed(seed)

    print(_SEP)
    print("  PHASE 3 -- QDS + Pauli Eigenstates Validation Report")
    print("  SIH26141 | Quantum-Inspired Cyber Threat Detection")
    print(_SEP)
    print(f"  Seed          : {ctx['seed']}")
    print(f"  NumPy version : {ctx['numpy_version']}")
    print(f"  Sig length    : {length}")
    print(f"  Threshold     : {DEFAULT_ACCEPT_THRESHOLD}")
    print(f"  Timestamp     : {time.strftime('%Y-%m-%dT%H:%M:%S')}")

    t0 = time.perf_counter()

    _section_eigenstates()
    _section_measurement_probs()
    sig = _section_signature(length, seed)
    _section_legit_verification(sig)
    _section_modified_verification(sig)
    teleport_ok = _section_teleportation(seed)
    e2e_ok = _section_end_to_end(length, seed)

    elapsed = time.perf_counter() - t0
    print(f"\n{_SEP}")
    print(f"  Elapsed : {elapsed:.2f}s")
    print(f"  Teleportation in key distribution : "
          f"{'PASS' if teleport_ok else 'FAIL'}")
    print(f"  End-to-end QDSScheme round trip   : "
          f"{'PASS' if e2e_ok else 'FAIL'}")
    print(_SEP)
    return teleport_ok and e2e_ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 3 QDS Validation -- SIH26141",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--length", type=int, default=12)
    parser.add_argument("--seed",   type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ok = run_validation(length=args.length, seed=args.seed)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
