# Architecture Overview

## System Design

The Quantum-Inspired Digital Signature (QDS) threat-detection framework is a
hardware-agnostic digital signature scheme whose security rests on a
cryptographic secret **and** on quantum-mechanical bounds. It is composed of
several subsystems; end-to-end scenarios are driven either by
`attacks/runner.py::AttackRunner` (the reference path used by the Phase 6/6.5
evaluations) or by `pipeline.py::EndToEndPipeline` (the integration demo).
Both apply attacks to real signature statevectors and score the result with
the same detector, so their numbers are comparable.

No AI/ML is used anywhere. Nothing in this system is *trained*: every
threshold is either computed analytically or calibrated from a percentile of
observed baseline statistics.

### Data flow

```
quantum/            bell_states → teleportation → noise
    │
    │   Bell pair → Bell measurement → Pauli correction
    ▼
qds/key_distribution.py        ← the bridge between quantum/ and qds/
    │   teleports the signer's key table to the verifier
    ▼
qds/                keygen → signer → verifier → scheme
    │
    ▼   VerificationResult
security/           statistics → fingerprint → anomaly → thresholds → detector
    │
    ▼   DetectionResult
attacks/  +  evaluation/  +  dashboard/
```

### Core Modules

1. **QDS Protocol Layer (`src/qds/`)**
   - **Key generation** (`keygen.py`): draws a 256-bit private seed from the
     OS CSPRNG and derives a key table of Pauli eigenstates via HMAC-SHA256.
     The public key is the verifier's copy of that table.
   - **Key distribution** (`key_distribution.py`): teleports each key
     eigenstate to the verifier over a real simulated quantum channel and
     reconstructs it from the received Bloch vector. This module is the
     functional link between `quantum/` and `qds/` — the public key is what
     the verifier *received*, not a list it was handed.
   - **Signing** (`signer.py`): the emitted eigenstate sequence is a function
     of both `SHA-256(message)` and the signer's private key.
   - **Verification** (`verifier.py`): projective measurement of the received
     states against the verifier's own public key, sampled under the Born
     rule across multiple distributed copies. Projective measurement is
     destructive — that is precisely why key elements are distributed as
     multiple copies rather than measured twice.
   - `verification.py` retains the single-copy deterministic check used by the
     statistical detector for baseline traffic.

2. **Quantum Mechanics Kernel (`src/quantum/`)**
   - Constructs the four Bell states and validates them by Pauli correlations.
   - Implements the 3-qubit teleportation circuit with classical feed-forward
     correction, executed on `AerSimulator(method='density_matrix')`.
   - Applies bit-flip, phase-flip, depolarizing, and amplitude-damping noise
     to the *channel* qubits only, leaving the input qubit clean so noise is
     isolated to transmission.

3. **Statistical Threat Detection (`src/security/`)**
   - **Fingerprinting**: profiles per-session measurement statistics (basis
     probabilities, Shannon entropy, mean/variance of ±1 outcomes).
   - **Threshold logic**: an anomaly score combining divergence measures
     against a calibrated baseline. Thresholds come from percentiles of
     baseline sessions, not from any fitted model.

4. **Attack Simulation (`src/attacks/`)**
   - Forgery (three adversary models), impersonation (two), replay,
     unauthorized verification, and channel manipulation.
   - Each attack mutates real statevectors and/or session metadata; the
     detector then scores the result. See `docs/attack_model.md`.

5. **Evaluation (`src/evaluation/`)**
   - `far_frr.py` computes FAR/FRR with Wilson or exact Clopper-Pearson
     confidence intervals; rates are never reported as bare point estimates.
   - `metrics.py` defines FAR = FN/(FN+TP) (attacks that passed) and
     FRR = FP/(FP+TN) (legitimate sessions denied).

### Configuration

`config/quantum_config.yaml` holds the simulator settings, the project seed
(used for reproducibility of *simulation*, never for key material), and the
`evaluation` block that sets security-evaluation sample sizes and the
confidence-interval method.
