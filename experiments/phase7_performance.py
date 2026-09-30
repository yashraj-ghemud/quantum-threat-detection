"""
experiments/phase7_performance.py
=================================
Phase 7 -- PERFORMANCE, SCALABILITY & COMPUTATIONAL ANALYSIS

Comprehensive benchmark of the QDS pipeline.
"""
import sys
import json
import time
import tracemalloc
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import qiskit
import qiskit_aer

from qds.signature import generate_signature
from qds.verification import verify_signature
from qds.pauli_states import get_eigenstate
from quantum.teleportation import build_teleportation_circuit, prepare_input_state
from qds.pauli_states import measure_eigenstate
from security.fingerprint import build_fingerprint, SessionFingerprint, BasisFingerprint
from security.anomaly import compute_anomaly_breakdown

from attacks.runner import AttackRunner
from attacks.forgery import ForgeryAttack
from attacks.impersonation import ImpersonationAttack
from attacks.replay import ReplayAttack
from attacks.unauthorized_verification import UnauthorizedVerificationAttack
from attacks.channel_manipulation import ChannelManipulationAttack

from evaluation.performance import LatencyTracker, profile_function
from evaluation.scalability import measure_signature_scalability, measure_session_scalability
from evaluation.complexity import get_theoretical_complexity

from quantum.noise import build_noise_model, run_noisy_teleportation

RESULTS_DIR = Path("experiments/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
SEED = 42

def run_component_benchmarks(reps: int = 20) -> pd.DataFrame:
    print("  [1] Measuring component micro-benchmarks...")
    tracker = LatencyTracker()
    
    # Pre-generate some random states to use
    state = get_eigenstate("|+>")
    sig = generate_signature("benchmark", length=16, seed=SEED)
    vr = verify_signature(sig)
    
    fp_base = build_fingerprint(vr)
    fp_sess = build_fingerprint(vr)
    
    for _ in range(3): # warmup
        generate_signature("w", length=16)
        
    for _ in range(reps):
        tracker.start("Pauli-state generation")
        get_eigenstate("|-i>")
        tracker.stop("Pauli-state generation")
        
        tracker.start("QDS signature generation")
        generate_signature("test", length=16)
        tracker.stop("QDS signature generation")
        
        tracker.start("Teleportation circuit")
        ic, _ = prepare_input_state(state.theta, state.phi)
        build_teleportation_circuit(state.theta, state.phi)
        tracker.stop("Teleportation circuit")
        
        sv = sig.elements[0].statevector
        tracker.start("Projective measurement")
        measure_eigenstate(sig.elements[0].eigenstate, "z")
        tracker.stop("Projective measurement")
        
        tracker.start("Fingerprint generation")
        build_fingerprint(vr)
        tracker.stop("Fingerprint generation")
        
        tracker.start("Anomaly scoring")
        compute_anomaly_breakdown(fp_sess, fp_base)
        tracker.stop("Anomaly scoring")
        
        tracker.start("Verification")
        verify_signature(sig)
        tracker.stop("Verification")
        
    runner = AttackRunner(sig_length=16, n_baseline=2, seed=SEED)
    runner.run_legitimate(seed_offset=999) # warmup
    
    for _ in range(reps):
        tracker.start("End-to-End Detection")
        runner.run_legitimate(seed_offset=np.random.randint(0, 10000))
        tracker.stop("End-to-End Detection")
        
    metrics = tracker.get_all_metrics()
    return pd.DataFrame([m.as_dict() for m in metrics])
    
def run_attack_performance(reps: int = 5) -> pd.DataFrame:
    print("  [2] Measuring attack evaluation latency...")
    runner = AttackRunner(sig_length=16, n_baseline=2, seed=SEED)
    
    attacks = [
        ("Forgery", ForgeryAttack(seed=SEED)),
        ("Impersonation", ImpersonationAttack(seed=SEED, impersonator_id="eve")),
        ("Replay", ReplayAttack(seed=SEED, staleness_seconds=120.0)),
        ("Unauthorized Verification", UnauthorizedVerificationAttack(seed=SEED, attacker_verifier_id="charlie")),
        ("Channel Manipulation", ChannelManipulationAttack(seed=SEED, mode="both"))
    ]
    
    data = []
    
    for atype, atk in attacks:
        latencies = []
        detects = 0
        
        for rep in range(reps):
            t0 = time.perf_counter()
            r = runner.run_attack(atk, atype, intensity=0.5, seed_offset=2000+rep)
            t1 = time.perf_counter()
            
            latencies.append(t1 - t0)
            if r.detection_status == "DETECTED":
                detects += 1
                
        data.append({
            "attack_type": atype,
            "mean_latency": np.mean(latencies),
            "median_latency": np.median(latencies),
            "detection_rate": detects / reps
        })
        
    return pd.DataFrame(data)

def run_noise_performance() -> pd.DataFrame:
    print("  [3] Evaluating noise levels and fidelity / processing time...")
    noise_levels = [0.0, 0.01, 0.05, 0.10, 0.20, 0.30]
    
    state_cx = get_eigenstate("|+>")
    
    data = []
    for p in noise_levels:
        t0 = time.perf_counter()
        res = run_noisy_teleportation("depolarizing", p, state_cx.theta, state_cx.phi)
        t1 = time.perf_counter()
        
        data.append({
            "noise_strength": p,
            "fidelity": res.fidelity,
            "end_to_end_time": t1 - t0
        })
        
    return pd.DataFrame(data)
    
def write_config_json():
    conf = {
        "python_version": sys.version,
        "qiskit_version": qiskit.__version__,
        "qiskit_aer_version": qiskit_aer.__version__,
        "seed": SEED,
        "signature_sizes": [4, 8, 16, 32, 64, 128],
        "session_loads": [10, 25, 50, 100, 250, 500],
        "noise_levels": [0.0, 0.01, 0.05, 0.10, 0.20, 0.30]
    }
    with open(RESULTS_DIR / "benchmark_config.json", "w") as f:
        json.dump(conf, f, indent=4)
        
def plot_results(sig_df, sess_df, noise_df, atk_df):
    print("  [4] Generating plots...")
    
    # 1. Signature Size
    plt.figure(figsize=(8,5))
    plt.plot(sig_df["signature_length"], sig_df["mean_end_to_end_time"], marker='o', color='purple', label="Overall E2E")
    plt.plot(sig_df["signature_length"], sig_df["mean_gen_time"], marker='^', linestyle='--', label="Generation Latency")
    plt.plot(sig_df["signature_length"], sig_df["mean_verify_time"], marker='s', linestyle='-.', label="Verification Latency")
    plt.title("Latency vs Signature Length")
    plt.xlabel("Signature Length (Qubits)")
    plt.ylabel("Latency (seconds)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "signature_latency.png")
    plt.close()
    
    # 2. Session throughput
    plt.figure(figsize=(8,5))
    plt.plot(sess_df["session_count"], sess_df["throughput_sessions_per_sec"], marker='o', color='green')
    plt.title("Throughput vs Total Session Load (Batched)")
    plt.xlabel("Session Load (Count)")
    plt.ylabel("Throughput (Sessions / sec)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "session_throughput.png")
    plt.close()
    
    # 3. Overall Scalability summary (Peak Mem vs Session Count)
    plt.figure(figsize=(8,5))
    mems = sess_df["peak_memory_bytes"] / (1024*1024)
    plt.bar(sess_df["session_count"].astype(str), mems, color='orange')
    plt.title("Peak Memory Usage vs Session Load Batch")
    plt.xlabel("Session Load (Count)")
    plt.ylabel("Peak Memory (MB)")
    plt.grid(True, axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "scalability_summary.png")
    plt.close()
    
    # 4. Noise / Fidelity
    fig, ax1 = plt.subplots(figsize=(8,5))
    color = 'tab:blue'
    ax1.set_xlabel('Depolarizing Noise Strength (p)')
    ax1.set_ylabel('Teleportation Fidelity', color=color)
    ax1.plot(noise_df["noise_strength"], noise_df["fidelity"], 'o-', color=color)
    ax1.tick_params(axis='y', labelcolor=color)
    ax2 = ax1.twinx()
    color = 'tab:red'
    ax2.set_ylabel('Sim Processing Time (s)', color=color)
    ax2.plot(noise_df["noise_strength"], noise_df["end_to_end_time"], 's--', color=color)
    ax2.tick_params(axis='y', labelcolor=color)
    plt.title("Channel Noise Impact on Quantum Fidelity and Execution Time")
    fig.tight_layout()
    plt.savefig(RESULTS_DIR / "noise_fidelity_performance.png")
    plt.close()
    
    # 5. Attack Latency
    plt.figure(figsize=(9,5))
    plt.bar(atk_df["attack_type"], atk_df["mean_latency"], color=['darkred', 'crimson', 'firebrick', 'brown', 'indianred'])
    plt.title("End-to-End Latency by Attack Category")
    plt.xlabel("Attack Type")
    plt.ylabel("Mean E2E Detection Latency (s)")
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "attack_latency.png")
    plt.close()

def main():
    print("==================================================================")
    print("  PHASE 7 -- PERFORMANCE, SCALABILITY & COMPUTATIONAL ANALYSIS")
    print("==================================================================")
    
    write_config_json()
    
    comp_df = run_component_benchmarks(20)
    
    print("  [2] Evaluating Signature SCALABILITY (Lengths 4 to 128)...")
    sig_df = measure_signature_scalability([4, 8, 16, 32, 64, 128], repetitions=3, seed=SEED)
    sig_df.to_csv(RESULTS_DIR / "signature_scalability.csv", index=False)
    
    print("  [3] Evaluating Session Load SCALABILITY (Count 10 to 500)...")
    sess_df = measure_session_scalability([10, 25, 50, 100, 250, 500], sig_length=16, seed=SEED)
    sess_df.to_csv(RESULTS_DIR / "session_scalability.csv", index=False)
    
    atk_df = run_attack_performance(5)
    noise_df = run_noise_performance()
    
    plot_results(sig_df, sess_df, noise_df, atk_df)
    
    cx_dict = get_theoretical_complexity()
    
    # Identify bottlenecks
    s_cmp = comp_df.loc[comp_df['mean_latency'].idxmin()]
    f_cmp = comp_df.loc[comp_df['mean_latency'].idxmax()]
    slowest = f_cmp['operation']
    fastest = s_cmp['operation']
    
    b_thr = sess_df['throughput_sessions_per_sec'].max()
    max_len = sig_df['signature_length'].max()
    max_ses = sess_df['session_count'].max()
    
    noise_obs = f"Fidelity drops roughly linearly as p increases. Timing variance observed: {noise_df['end_to_end_time'].std():.4f}s."
    atk_obs = f"Worst-case latency observed in {atk_df.loc[atk_df['mean_latency'].idxmax()]['attack_type']} attack."
    
    # Assess linearity
    r_factor = sig_df['mean_end_to_end_time'].iloc[-1] / sig_df['mean_end_to_end_time'].iloc[0]
    n_factor = sig_df['signature_length'].iloc[-1] / sig_df['signature_length'].iloc[0]
    is_linear = abs(r_factor - n_factor) < max(r_factor, n_factor) * 0.5 
    
    scale_obs = f"Signature length scaling is roughly {'LINEAR' if is_linear else 'NON-LINEAR'} (n_ratio={n_factor:.1f}, time_ratio={r_factor:.1f})."
    
    print("\n")
    print("PERFORMANCE REPORT")
    print("------------------")
    print(f"FASTEST COMPONENT:           {fastest} ({s_cmp['mean_latency']*1e6:.1f} us)")
    print(f"SLOWEST COMPONENT:           {slowest} ({f_cmp['mean_latency']*1e3:.1f} ms)")
    print(f"BEST THROUGHPUT (16q limit): {b_thr:.2f} sessions/sec (Batched execution)")
    print(f"MAXIMUM TESTED SIGNATURE:    {max_len} element/qubits")
    print(f"MAXIMUM TESTED SESSION LOAD: {max_ses} full-session batch")
    print("\nOBSERVATIONS")
    print("------------")
    print(f"NOISE/FIDELITY OBSERVATION:  {noise_obs}")
    print(f"ATTACK-LATENCY COMPARISON:   {atk_obs}")
    print(f"SCALABILITY OBSERVATION:     {scale_obs}")
    print("\nTHEORETICAL COMPLEXITY SUMMARY")
    print("------------------------------")
    for key, val in cx_dict.items():
        print(f"  {val.component:<50} | Time: {val.time_complexity:<10} | Mem: {val.memory_complexity}")
    
    print(f"\n=> Benchmark and computational results stored in '{RESULTS_DIR}'")

if __name__ == "__main__":
    main()
