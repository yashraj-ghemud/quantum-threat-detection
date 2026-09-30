"""
evaluation/scalability.py
=========================
Phase 7 -- Scalability evaluation (Signature Length, Session Load, Noise).
"""
import time
import tracemalloc
import pandas as pd
from typing import List, Sequence, Tuple, Optional
import numpy as np

from evaluation.performance import LatencyTracker
from attacks.runner import AttackRunner, AttackScenarioResult
from qds.signature import generate_signature
from qds.verification import verify_signature

__all__ = ["measure_signature_scalability", "measure_session_scalability"]

def measure_signature_scalability(
    lengths: Sequence[int], 
    repetitions: int = 5,
    seed: int = 42
) -> pd.DataFrame:
    data = []
    
    for length in lengths:
        gen_times = []
        ver_times = []
        end_times = []
        mem_peaks = []
        
        for rep in range(repetitions):
            cur_seed = seed + length + rep
            
            tracemalloc.start()
            t0 = time.perf_counter()
            
            # Genesis
            t_gen_0 = time.perf_counter()
            sig = generate_signature(f"scalability_{length}", length=length, seed=cur_seed)
            t_gen_1 = time.perf_counter()
            
            # Verify
            t_ver_0 = time.perf_counter()
            vr = verify_signature(sig)
            t_ver_1 = time.perf_counter()
            
            t1 = time.perf_counter()
            
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            
            gen_times.append(max(0.0, t_gen_1 - t_gen_0))
            ver_times.append(max(0.0, t_ver_1 - t_ver_0))
            end_times.append(max(0.0, t1 - t0))
            mem_peaks.append(peak)
            
        data.append({
            "signature_length": length,
            "mean_gen_time": np.mean(gen_times),
            "mean_verify_time": np.mean(ver_times),
            "mean_end_to_end_time": np.mean(end_times),
            "peak_memory_bytes": np.mean(mem_peaks)
        })
        
    return pd.DataFrame(data)


def measure_session_scalability(
    session_counts: Sequence[int],
    sig_length: int = 16,
    seed: int = 42
) -> pd.DataFrame:
    data = []
    runner = AttackRunner(sig_length=sig_length, n_baseline=2, seed=seed)
    
    # Warmup
    runner.run_legitimate(seed_offset=9999)
    
    for count in session_counts:
        tracemalloc.start()
        t0 = time.perf_counter()
        
        # Batch execute
        for i in range(count):
            runner.run_legitimate(seed_offset=seed + count + i)
            
        t1 = time.perf_counter()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        elapsed = max(1e-9, t1 - t0)
        throughput = count / elapsed
        
        data.append({
            "session_count": count,
            "total_execution_time": elapsed,
            "avg_time_per_session": elapsed / count if count > 0 else 0,
            "throughput_sessions_per_sec": throughput,
            "peak_memory_bytes": peak
        })
        
    return pd.DataFrame(data)
