# Quantum-Inspired Cyber Threat Detection for Digital Signature Security

**SIH26141 — Blockchain & Cybersecurity**

---

## Problem Statement & Objective

Digital signatures are a cornerstone of blockchain and cybersecurity infrastructure, providing authenticity and non-repudiation guarantees. Classical digital signatures face growing threats from forgery, impersonation, replay, and channel-manipulation attacks — threats that will intensify as quantum computers mature.

This project builds a **Quantum-Inspired Cyber Threat Detection** system that:

1. Implements a **Quantum Digital Signature (QDS)** scheme using Pauli eigenstates and quantum measurement.
2. Detects cyber threats against the QDS protocol using **quantum measurement statistics, mathematical divergence metrics, and threshold-based anomaly detection** — with **no AI/ML whatsoever**.
3. Simulates a comprehensive set of attacks and evaluates detection performance via FAR/FRR, fidelity, and throughput benchmarks.

---

## ⚠️ No AI/ML

> **This project contains zero AI or machine learning.**
> Nothing here is *trained*. Threat detection uses quantum measurement
> statistics, Pauli basis probabilities, Shannon entropy, Hellinger distance,
> KL divergence, and thresholds calibrated from percentiles of observed
> baseline sessions.
> No TensorFlow, PyTorch, scikit-learn, or any other ML framework is used.
>
> Two detection paths are deliberately **classical**, and we say so rather
> than overclaiming: replay is caught by session-consistency checks on
> metadata (a replayed signature's quantum statistics are identical to a
> legitimate one by construction), and unauthorized verification carries a
> classical access-control layer *alongside* its quantum intercept-resend
> detection. See `docs/attack_model.md`.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        main.py  (entry point)                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   quantum/    │
                    │  bell_states  │
                    │  teleportation│
                    │  noise        │
                    │  measurements │
                    └───────┬───────┘
                            │
      Bell pair → Bell measurement → Pauli correction
              (a real Aer circuit, not a stand-in)
                            │
                            ▼
              ┌─────────────────────────────┐
              │  qds/key_distribution.py    │   ◀── the bridge
              │  teleports the signer's key │
              │  table to the verifier      │
              └─────────────┬───────────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │            qds/             │
              │  keygen    CSPRNG seed →    │
              │            HMAC key table   │
              │  signer    SHA-256(msg)     │
              │            + private key    │
              │  verifier  vs public key,   │
              │            Born-rule copies │
              │  scheme    orchestration    │
              │  pauli_states               │
              └─────────────┬───────────────┘
                            │  VerificationResult
                            ▼
              ┌─────────────────────────────┐
              │          security/          │
              │  statistics · fingerprint   │
              │  anomaly · thresholds       │
              │  detector                   │
              └─────────────┬───────────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │          attacks/           │
              │  forgery · impersonation    │
              │  replay · channel_manip.    │
              │  unauthorized_verification  │
              └─────────────┬───────────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │         evaluation/         │
              │  FAR/FRR + confidence       │
              │  intervals · metrics        │
              │  latency · performance      │
              └─────────────┬───────────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │         dashboard/          │
              │  real-time visualisation    │
              └─────────────────────────────┘

  Teleportation is load-bearing: the verifier's public key is the set of
  states it RECEIVED over the quantum channel, not a list it was handed.
  That is what gives a channel adversary something real to attack.

              utils/  ←  config · logger · reproducibility · validation
              config/ ←  quantum_config.yaml · settings.py
```

---

## End-to-End Pipeline

`src/session.py` is the single coherent path through the system. Each stage
consumes the real output of the previous one:

```
MESSAGE
  -> MESSAGE BINDING          SHA-256 digest of the message bytes
  -> QDS SIGNATURE            secret key table indexed by that digest
  -> QUANTUM STATE            one Pauli eigenstate per signature element
  -> [ATTACK INJECTION]       forgery / impersonation / interception
  -> BELL-STATE ENTANGLEMENT  |Phi+> shared between signer and verifier
  -> QUANTUM TELEPORTATION    Bell measurement + 2 classical bits
  -> [CHANNEL ATTACK]         noise injected on the channel qubits
  -> PAULI CORRECTION         X / Z applied from the correction bits
  -> RECEIVED QUANTUM STATE   Bob's actual reduced density matrix
  -> PROJECTIVE MEASUREMENT   sampled shots in the element's Pauli basis
  -> MEASUREMENT STATISTICS   real counts, real finite-shot noise
  -> QDS VERIFICATION         measured eigenvalue vs the verifier's key
  -> THREAT DETECTION         statistical + protocol evidence
```

Two properties are enforced by design, and by a test that fails if either
is violated:

1. **No stage is simulated by adjusting a later stage's number.** There is
   no code path that edits a verification score to represent an attack.
   `tests/test_session_pipeline.py::TestNoFabrication` greps the source for
   result-object mutation and fails the build if it reappears.
2. **The teleported state is the state that gets verified.** Teleportation
   is not run alongside the protocol to produce a fidelity figure; the
   qubit measured is the qubit that came out of the channel.

### Measurement model

A quantum computer measures only in the Z basis, so measuring X or Y means
rotating that eigenbasis onto Z first (`quantum/measurements.py`):

| Basis | Rotation applied | Identity |
|---|---|---|
| Z | none | measured directly |
| X | `H` | `H Z H = X` |
| Y | `S-dagger` then `H` | `H S' Z S H = Y` |

Outcome bit `b` maps to eigenvalue `(-1)**b`. Counts are sampled from Aer,
so they carry genuine shot noise of order `1/sqrt(shots)`; the analytic
Born-rule probability is retained alongside for comparison.

### Simulation assumptions

- **Software simulation only.** No physical quantum hardware is used or
  claimed. The backend is `AerSimulator(method='density_matrix')`.
- **Baseline channel noise floor.** Every session -- legitimate included --
  runs over a depolarizing channel with `p = 0.02`. This is deliberate: on
  a *perfect* channel legitimate sessions have zero variance, any threshold
  separates them from attacks, and the reported FAR/FRR would measure
  nothing. The floor forces the detector to distinguish an attack from
  ordinary hardware imperfection.
- **Channel model.** Depolarizing, `rho' = (1-p) rho + p I/2`, applied to
  the channel qubits only. This is one reasonable model of channel
  interference, not the only possible physical attack.
- **Channel-output caching.** Teleporting the same eigenstate through the
  same channel twice yields the same density matrix, so the result is
  cached. This changes no physics -- per-shot randomness lives in the
  measurement sampling, which is drawn fresh and separately seeded.

---

## Technology Stack

| Component | Library / Tool |
|---|---|
| Quantum circuits & gates | [Qiskit](https://qiskit.org/) ≥ 1.0 |
| Quantum simulation | [Qiskit Aer](https://qiskit.github.io/qiskit-aer/) ≥ 0.14 |
| Numerical computing | NumPy ≥ 1.26 |
| Statistical analysis | SciPy ≥ 1.12 |
| Data management | Pandas ≥ 2.2 |
| Visualisation | Matplotlib ≥ 3.8 |
| Testing | pytest ≥ 8.0 |
| Configuration | PyYAML ≥ 6.0 |
| Python | ≥ 3.10 |

**No AI/ML frameworks (TensorFlow, PyTorch, scikit-learn) are present.**

---

## Project Structure

```
quantum-threat-detection/
├── src/
│   ├── quantum/                 # Bell states, teleportation, noise, measurement
│   │   ├── __init__.py
│   │   ├── bell_states.py       # Phase 1
│   │   ├── teleportation.py     # Phase 2
│   │   ├── noise.py             # Phase 2.5
│   │   └── measurements.py      # Phase 3
│   ├── qds/                     # Quantum Digital Signature scheme
│   │   ├── __init__.py
│   │   ├── pauli_states.py      # Phase 3  (the six Pauli eigenstates)
│   │   ├── keygen.py            # Phase 3  (CSPRNG seed + HMAC key table)
│   │   ├── key_distribution.py  # Phase 3  (teleports the public key)
│   │   ├── signature.py         # Phase 3
│   │   ├── signer.py            # Phase 3  (binds key + message hash)
│   │   ├── verification.py      # Phase 3
│   │   ├── verifier.py          # Phase 3  (verifies against the public key)
│   │   └── scheme.py            # Phase 3  (QDSScheme orchestration)
│   ├── security/                # Statistical threat detection (no ML)
│   │   ├── __init__.py
│   │   ├── statistics.py        # Phase 4
│   │   ├── fingerprint.py       # Phase 4
│   │   ├── anomaly.py           # Phase 4
│   │   ├── calibration.py       # Phase 4
│   │   ├── thresholds.py        # Phase 4
│   │   └── detector.py          # Phase 4
│   ├── attacks/                 # Attack simulations
│   │   ├── __init__.py
│   │   ├── base.py              # Phase 5
│   │   ├── forgery.py           # Phase 5  (random / key_ignorant / learned)
│   │   ├── impersonation.py     # Phase 5  (own_seed / own_keypair)
│   │   ├── replay.py            # Phase 5
│   │   ├── unauthorized_verification.py  # Phase 5  (intercept-resend)
│   │   ├── channel_manipulation.py       # Phase 5  (real quantum channel)
│   │   └── runner.py            # Phase 5
│   ├── evaluation/              # Performance & security evaluation
│   │   ├── __init__.py
│   │   ├── fidelity.py          # Phase 7
│   │   ├── far_frr.py           # Phase 6/7 (FAR/FRR + confidence intervals)
│   │   ├── error_bounds.py      # Phase 6
│   │   ├── metrics.py           # Phase 7
│   │   ├── security_analysis.py # Phase 6
│   │   ├── threshold_optimization.py # Phase 6.5
│   │   ├── latency.py           # Phase 7
│   │   └── performance.py       # Phase 7
│   └── utils/                   # Shared utilities (active from Phase 0)
│       ├── __init__.py
│       ├── config.py            # ConfigLoader (YAML → typed properties)
│       ├── logger.py            # get_logger factory
│       ├── reproducibility.py   # set_seed, get_rng, get_run_context
│       └── validation.py        # Input validators (basis, shots, qubits)
├── tests/
│   └── test_phase0.py           # Phase 0 test suite
├── experiments/                 # Experiment scripts (Phase 1+)
├── dashboard/                   # Real-time visualisation (Phase 8)
├── docs/                        # Technical documentation
├── config/
│   ├── __init__.py
│   ├── quantum_config.yaml      # Master YAML configuration
│   └── settings.py              # Compiled Python-level defaults
├── main.py                      # Entry point
├── requirements.txt
├── pyproject.toml
├── README.md
└── .gitignore
```

---

## Threat Detection

Deterministic and explainable. No AI, no ML, no fitted model. The anomaly
score is a documented linear combination of four indicators, each a
one-sided normalised deviation from a **measured** legitimate baseline
(`src/security/threat_engine.py`):

```
anomaly_score = 0.40 * n_mismatch      # measured disagreement with the key
              + 0.25 * n_fidelity      # physical distance from the sent state
              + 0.25 * n_trace         # single-shot distinguishability
              + 0.10 * n_entropy       # outcome-distribution shape
```

Weights are fixed a priori by how directly each indicator reflects a
protocol violation, not tuned to improve results; they sum to 1.0 so the
score is on the same scale as the threshold. The normalisers are documented
at their definitions.

### Attack classification

A deterministic decision list, evaluated most-specific first. Protocol
violations are conclusive and checked before any statistic:

| Attack | Primary discriminator |
|---|---|
| Unauthorized verification | verifier not on the allow-list |
| Replay | nonce reuse / sequence regression / staleness |
| Impersonation | `key_id` does not match the verifier's public key |
| Forgery | mismatch with purity **intact** (a substituted pure state) |
| Channel manipulation | excess mixedness (purity falls below the noise floor) |

The purity test is what separates forgery from channel noise: substituting
an eigenstate leaves the state pure, while a depolarizing channel decoheres
it. Measured on this run, forgery holds purity at
0.9475 while
channel manipulation drives it to
0.5759.

### Threshold calibration

The threshold is **not** hardcoded. `experiments/run_final_experiment.py`
sweeps candidates over the measured score distributions and selects one by
a stated rule:

> min FAR subject to FRR <= 5%; ties broken by larger threshold

The selected value is written back into `config/quantum_config.yaml`, so
the threshold in force is always the one the experiment chose. This run
selected **0.018625**.

---

## Development Roadmap

| Phase | Title | Status |
|---|---|---|
| **0** | Foundation — project structure, config, utils | ✅ Complete |
| 1 | Bell States & Entanglement | ✅ Complete |
| 2 | Teleportation & Fidelity | ✅ Complete |
| 2.5 | Quantum Noise Models | ✅ Complete |
| 3 | QDS — keygen, teleported key distribution, sign, verify | ✅ Complete |
| 4 | Statistical Threat Detection | ✅ Complete |
| 5 | Attack Simulation | ✅ Complete |
| 6 | Security Analysis (N=1800, with confidence intervals) | ✅ Complete |
| 7 | Performance Evaluation | ✅ Complete |
| 8 | Dashboard | ✅ Complete |
| 9 | Final Integration | ✅ Complete |
| — | **Key-table rotation / signature bound** | ⚠️ Not implemented — see below |
| — | **Signer-repudiation defence** (Gottesman-Chuang two-threshold) | ⛔ Out of scope this version |

### Known limitations

These are stated plainly because they bound what the results above mean:

1. **Key reuse breaks unforgeability.** Signature positions are drawn from a
   finite key table, so indices recur across messages and each recurrence
   leaks a table entry. Measured with `table_size=64`, `signature_length=16`:
   an eavesdropper who observes **5** signatures recovers 48/64 entries and
   forges successfully in **60/60** attempts; 25 signatures recover the whole
   table. Blind forgery without that knowledge succeeds **0/60**. Rotate keys
   well before `table_size / signature_length` messages. This bound is not yet
   enforced in code.
2. **Repudiation is not defended.** A dishonest signer denying their own
   signature is out of scope — see `docs/security_model.md`.
3. **Replay is detected classically**, not by quantum statistics: a replayed
   signature carries genuine undisturbed states, so it is quantum-mechanically
   indistinguishable from a legitimate session by construction.

---

## Measured Results

Every figure below is produced by one run of
`experiments/run_final_experiment.py` and lives in
`experiments/results/final/`. Nothing is hand-entered.

**Configuration**: 200 sessions per class
(200 legitimate,
1000 attack),
signature length 16, 256 shots
per element, seed 42, baseline noise floor
depolarizing p=0.02, threshold 0.018625.

| Metric | Value | 95% CI | n |
|---|---|---|---|
| Accuracy | 99.83% | - | 1200 |
| Precision | 99.80% | - | - |
| Detection rate (recall) | 100.00% | [99.63, 100.00] | 1000 |
| F1 | 99.90% | - | - |
| **FAR** (attack passes) | 0.00% | [0.00, 0.37] | 1000 |
| **FRR** (legitimate denied) | 1.00% | [0.12, 3.57] | 200 |
| Forgery acceptance probability | 60.50% | [53.36, 67.32] | 200 |
| Mean teleportation fidelity | 0.972645 | - | - |
| End-to-end latency | 27.66 ms | - | - |
| Throughput | 36.1 sessions/s | - | - |

### Per-attack detection

| Attack | Detection rate | 95% CI | Classified correctly | Mean fidelity | Mean purity |
|---|---|---|---|---|---|
| Forgery | 100.00% | [98.17, 100.00] | 100.00% | 0.7232 | 0.9475 |
| Impersonation | 100.00% | [98.17, 100.00] | 100.00% | 0.5036 | 0.9474 |
| Replay | 100.00% | [98.17, 100.00] | 100.00% | 0.9728 | 0.9471 |
| Unauthorized Verification | 100.00% | [98.17, 100.00] | 100.00% | 0.8088 | 0.9473 |
| Channel Manipulation | 100.00% | [98.17, 100.00] | 100.00% | 0.6385 | 0.5759 |

### A result worth reading carefully

**Forgery acceptance probability is 60.50%**,
even though forgery detection is 100.00%.
These measure different things, and the gap is the point:

- *Forgery acceptance* asks whether QDS verification **alone** accepted the
  signature -- score above the 0.7 accept threshold with valid bindings.
  At low attack intensities only a few elements are substituted, so the
  score stays above 0.7 and verification accepts.
- *Detection rate* asks whether the **statistical detector** flagged the
  session, which it did every time, using fidelity and trace-distance
  evidence that threshold verification ignores.

In other words, threshold verification on its own is not sufficient against
weak forgeries; the quantum-statistical layer is what catches them. We
report both numbers rather than only the flattering one.

---

## Installation

### Prerequisites

- Python ≥ 3.10
- pip or a virtual environment manager

### Setup

```bash
# Clone / enter the project
cd quantum-threat-detection

# Create and activate virtual environment
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install all dependencies
pip install -r requirements.txt

# Install project in editable mode (enables src-based imports)
pip install -e .
```

---

## Running the Application

```bash
# Phase 0 environment check
python main.py

# With a custom seed
python main.py --seed 123

# With a custom config file
python main.py --config path/to/my_config.yaml
```

---

## Testing

The test suite uses **pytest**. The `pythonpath = ["src"]` setting in
`pyproject.toml` ensures all `src`-based imports resolve correctly.

```bash
# Run the full Phase 0 test suite
pytest tests/test_phase0.py -v

# Run with coverage
pytest tests/test_phase0.py -v --cov=src --cov-report=term-missing

# Run all tests
pytest -v
```

### Phase 0 Test Coverage

| Test | Verifies |
|---|---|
| `test_package_imports` | All six src sub-packages import without error |
| `test_configuration_loading` | ConfigLoader reads YAML and returns correct typed values |
| `test_config_defaults` | seed=42, shots=1024, backend=aer_simulator |
| `test_measurement_bases` | X/Y/Z bases present in config |
| `test_reproducible_numpy_seed` | Same seed → same NumPy random draws |
| `test_get_rng_reproducibility` | `get_rng(42)` produces identical sequences |
| `test_qiskit_circuit_creation` | QuantumCircuit(2) builds and has 2 qubits |
| `test_aer_simulator_available` | AerSimulator instantiates and runs a simple circuit |
| `test_validate_basis_valid` | All of x/y/z/X/Y/Z pass validation |
| `test_validate_basis_invalid` | Invalid bases raise ValueError |
| `test_validate_shots_valid` | Positive integers pass |
| `test_validate_shots_invalid` | Zero and negatives raise ValueError |
| `test_phase_flags` | Phase 0 enabled; Phase 1+ disabled |

---

## Reproducibility

All randomness in the project is controlled through a single seed, set via:

```python
from utils.reproducibility import set_seed
set_seed(42)   # seeds Python random, NumPy legacy state, NumPy Generator
```

The seed is stored in `config/quantum_config.yaml` and can be overridden
at runtime with `python main.py --seed <N>`.

Qiskit Aer jobs will be seeded per-execution in Phase 1+ using the same
seed value propagated through `ConfigLoader.random_seed`.

---

## Configuration Reference

Edit `config/quantum_config.yaml` to change project-wide settings:

```yaml
random_seed: 42
simulator:
  backend: "aer_simulator"
  shots: 1024
measurement_bases:
  X: "x"
  Y: "y"
  Z: "z"
logging:
  level: "INFO"
```

All settings are also accessible as typed Python constants in
`config/settings.py` and via `ConfigLoader` typed properties.

---

## Contributing

This is a research project for SIH26141. Follow the phase roadmap strictly —
do not implement Phase N+1 code until Phase N is complete and tested.

When a phase is marked Complete, the corresponding module must actually be
implemented. Marking a phase Complete while its modules still raise
`NotImplementedError` is what allowed the signature scheme to ship for a time
with no secret key at all.

---

## How to Run

```bash
# 1. Install
pip install -r requirements.txt
pip install streamlit plotly          # dashboard extras

# 2. Environment check
python main.py

# 3. Reproduce ALL published metrics (the canonical experiment)
python experiments/run_final_experiment.py --trials 200

# 4. Dashboard
streamlit run dashboard/app.py        # http://localhost:8501

# 5. Tests
python -m pytest tests/ -q
```

### Reproducing the experiments

`experiments/run_final_experiment.py` is the single source of truth. It
writes everything under `experiments/results/final/`:

```
results/final/
  metrics.json             headline metrics with confidence intervals
  attack_metrics.csv       per-attack detection + classification
  comparison.csv           NORMAL vs ATTACK telemetry
  intensity_analysis.csv   detection rate vs attack intensity
  threshold_analysis.csv   full threshold sweep (FAR/FRR at each point)
  confusion_matrix.csv     2x2 confusion matrix
  sessions.csv             every individual session
  experiment_config.json   seed, trials, noise, commit, timestamp
  plots/                   six figures, all generated from the above
```

The run is reproducible: the seed, trial counts, noise settings, simulator
configuration, selected threshold and git commit are all recorded in
`experiment_config.json`. Re-running with the same `--trials` and `--seed`
reproduces the same figures.

Useful variations:

```bash
python experiments/run_final_experiment.py --quick             # fast smoke run
python experiments/run_final_experiment.py --trials 500        # tighter intervals
python experiments/run_final_experiment.py --max-frr 0.02      # stricter FRR ceiling
```

The dashboard reads only from `results/final/`. If no run exists it says so
rather than displaying placeholder numbers.

---

## Limitations

Stated plainly, because they bound what the results above mean.

1. **Simulation, not hardware.** Everything runs on Qiskit Aer. No physical
   quantum device is used, and no claim about hardware behaviour is made.
   Real devices add gate-level error, crosstalk, measurement error and
   decoherence that this model does not reproduce.

2. **Finite shots.** Measurement statistics come from a finite number of
   shots (256 per element by default), so every probability carries
   sampling error of order `1/sqrt(shots)`. The detector must separate that
   from an attack, which is why the baseline is measured rather than
   assumed.

3. **One channel model.** Channel manipulation is modelled as depolarizing
   noise on the channel qubits. Other physically meaningful attacks --
   coherent rotation, photon loss, side-channel leakage, timing attacks --
   are not simulated.

4. **Threshold depends on calibration data.** The operating point is chosen
   from the measured score distributions of *this* configuration, and it is
   not universal. Measured sensitivity, running 60 legitimate sessions
   against a threshold calibrated at `length=16, shots=256`:

   | Configuration | FRR |
   |---|---|
   | length=16, shots=256 (matches calibration) | 1.7% |
   | length=32, shots=256 | 3.3% |
   | length=8, shots=128 | **11.7%** |

   Shorter signatures make the mismatch rate coarser -- one element out of
   8 moves it by 0.125, versus 0.0625 out of 16 -- so the same threshold
   rejects far more honest sessions. `SessionRunner` now logs a warning when
   the running configuration differs from the one the threshold was
   calibrated for, and `config/quantum_config.yaml` records that
   configuration alongside the value. Recalibrate with
   `--signature-length` / `--shots` rather than reusing a stored threshold.

5. **Detector performance is not protocol security.** The measured FAR/FRR
   describe how well the *detector* separates these simulated attack
   classes under these conditions. They are not a security proof, and they
   do not transfer to attacks outside the modelled set.

6. **No information-theoretic security claim.** Unforgeability here rests on
   a computational assumption -- that HMAC-SHA256 behaves as a
   pseudo-random function, so the key table is unpredictable without the
   256-bit seed. SHA-256 is used for message binding and transcript
   integrity, which are computational properties. The quantum layer
   contributes no-cloning-based *detection* of interception, not
   information-theoretic unforgeability. The prototype as implemented is
   **not** information-theoretically secure, and we do not claim it is.

7. **Key reuse is bounded, and the bound is now derived and enforced.**
   Signature positions index a finite key table, so indices recur across
   messages and each recurrence leaks a table entry. `qds/key_policy.py`
   derives the safe signature count from the geometry:

   ```
   coverage after n signatures   f(n) = 1 - (1 - 1/T)^(n*L)
   attacker match rate           f + (1 - f)/6
   breach when that reaches the 0.7 accept threshold, i.e. f* = 0.64
   ```

   The old default `T = 64` permits exactly **one** safe signature, which
   is why the default is now `T = 1024` (27 signatures). Measured, 60
   forgery attempts each:

   | Table size | Safe limit | Observed sigs | Coverage | Forged |
   |---|---|---|---|---|
   | 64 (old default) | 1 | 5 | 0.716 | **9/60** |
   | 64 (old default) | 1 | 25 | 0.998 | **60/60** |
   | 1024 (new default) | 27 | 5 | 0.075 | 0/60 |
   | 1024 (new default) | 27 | 25 | 0.323 | 2/60 |

   `sign_message` counts signatures per key and warns once the limit is
   passed; set `KeyUsagePolicy(enforce=True)` to raise instead. The bound
   is probabilistic, not absolute -- 2/60 still succeeded at 25 signatures
   within the limit -- so treat it as a rotation trigger, not a guarantee.
   Use `recommend_table_size(n, L)` to size a key for a required volume.

8. **Repudiation is out of scope.** A dishonest signer denying their own
   valid signature is not defended against. Gottesman-Chuang QDS handles
   this with multi-recipient key distribution and a two-threshold
   accept/transfer rule, which this version does not implement.

9. **Scalability.** Cost grows linearly in signature length and shot count.
   The teleportation channel dominates on a cold cache; the cache makes
   repeated runs practical but a hardware backend would not have it.

---

## Future Work

- Enforce a signatures-per-key bound with automatic key rotation (limitation 7).
- Multi-recipient key distribution and the two-threshold rule, to cover
  repudiation (limitation 8).
- Additional channel models: coherent rotation, amplitude damping as an
  attack rather than only a noise study, photon loss.
- Calibration across a sweep of noise floors, so the threshold adapts to
  the deployment's measured channel quality.

---

## License

MIT — see `LICENSE` (to be added).
