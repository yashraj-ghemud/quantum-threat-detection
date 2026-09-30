# QVeris — Quantum Signature Defense

**SIH 26141 · Quantum-Inspired Cyber Threat Detection for Digital Signature Security** (Egreen Quanta · Blockchain & Cybersecurity)

QVeris signs messages with **teleportation-based quantum digital signatures** (QDS) and defends them with **QSentinel**, a physics-grounded threat detector. Every stage is measured, and every verdict comes with the evidence behind it. A live mission-control web app shows the engine at work. It includes the original QVeris cinematic story and 3D scenes, upgraded to run on real engine data.

> **No AI/ML. No fabricated data.** Decisions come from exact statistics over measured quantum data: Clopper–Pearson bounds, binomial tails, sequential tests and Holm–Bonferroni control. Nothing is trained. Every number in the UI is computed by the engine or read from rows it wrote.

---

## What it does

| Layer | What happens |
|---|---|
| **Key distribution** | For each digest bit the signer holds two one-time keys (Lamport style). Each key is a string of random **six-state qubits**, and every qubit is **teleported** to each recipient over a Bell pair. A recipient measures in a random basis and keeps records it cannot forge. |
| **Certification** | Sacrificial Bell pairs must beat the **CHSH** classical bound (lower confidence bound S > 2). A fidelity witness, per-basis QBER, **de-twirled channel tomography**, frame integrity and source/copy consistency all run on every bundle. |
| **Symmetrization** | Recipients swap a random half of their records, so a dishonest signer cannot make one recipient accept and the other reject. |
| **Sign & verify** | The SHA-256 digest of the envelope (message, signer, recipients, sequence, time, nonce) reveals one key per bit. Verifiers accept a key when mismatches m ≤ s·n. An **SPRT** aborts forgeries early. A protocol guard enforces authorization, key binding, one-time use, nonce, sequence and freshness. |
| **Detection & response** | 20 detectors (D1–D10 distribution, S1–S10 signature) feed a deterministic fusion that names the attack class and subtype. Each finding opens an incident with recommended responses: quarantine, re-certify, revoke, MAC, suspend. |
| **Audit** | Everything is appended to a **hash-chained Merkle ledger**. The tamper demo rewrites one stored row in SQLite, and verification pinpoints the broken block. Inclusion proofs can be re-hashed in the browser. |

**17 attacks in 6 classes:**
- **Forgery:** blind, insider, hash-oracle.
- **Impersonation:** identity swap, keyless.
- **Replay:** resubmission, forward, delayed.
- **Unauthorized verification:** non-recipient, MITM key harvesting.
- **Channel manipulation:** depolarizing, dephasing, amplitude damping, coherent rotation, intercept–resend, Pauli-frame tampering.
- **Repudiation:** inconsistent keys.

Each run also reports a **counterfactual**: what would have happened with the corresponding defence switched off.

## Measured results

These come from the built-in analysis jobs (quick presets, run on this code; reproduce them in **Analytics**):

| Result | Value |
|---|---|
| Attacks detected (all 17 attacks × 3 intensities × 4 trials) | **204 / 204**, miss rate 0 % [0, 1.8 %] |
| Correct classification of detected attacks | **100 %** |
| False rejections of honest traffic | **0 / 80** (live Command Center: 0 / 800) |
| Insider-optimal forgery mismatch over all measurement directions | **0.3333** (six-state optimum 1/3) |
| ε_forge per key at L = 4096 (standard preset) | **7.1 × 10⁻⁷**; ε_rob 8 × 10⁻¹⁰; ε_rep 1.5 × 10⁻¹⁴ |
| Repudiation disputes with / without symmetrization | 0 % / up to 100 % |
| Engine vs Qiskit Aer (teleportation, 6 channels) | max deviation **4.4 × 10⁻¹⁶** |
| Throughput | ≈ 9 M teleported qubits/s, **≈ 430× faster** than Aer density-matrix simulation |
| CUSUM drift monitor | no false alarm in 500 bundles; a 0.5 % QBER shift is caught in ≈ 6.5 bundles |

## Quick start

```bash
pip install -r requirements.txt
cd web && npm ci && cd ..
./scripts/start.sh            # builds the UI once, then serves everything on http://localhost:8000
```

- Development (hot reload): `./scripts/dev.sh`. The backend runs on :8000 and Vite on http://localhost:5173.
- Docker: `docker compose up --build`, then open http://localhost:8000.
- API docs: http://localhost:8000/docs.
- Tests:
  - `make test`: 150+ Python tests plus web type-check and unit tests.
  - `make e2e`: Playwright on desktop and mobile.

Configuration lives in `config/network.yaml` (topology, links and baselines) and `config/sentinel.yaml` (presets, detection, server). Environment overrides:
- `QVERIS_PRESET` (`demo` | `standard` | `high`)
- `QVERIS_DATA_DIR`
- `QVERIS_PORT`
- `QVERIS_AUTOSTART_TRAFFIC`
- `QVERIS_ALLOW_TAMPER_DEMO`
- `QVERIS_API_KEY`

## The web app

| Page | Highlights |
|---|---|
| **Overview** | The original QVeris intro film and scroll-scrubbed 3D story, with chapters rewritten for this engine and finale metrics taken from the live engine. Below it: live proof, the 8 pipeline steps bound to the latest real runs, the threat catalog, and evidence charts. |
| **Command Center** | 3D network driven by live events: qubit pulses, signature packets, and lightning plus Eve on compromise. Also a threat ring, KPIs with confidence intervals, liquid key-reservoir gauges, link health (CHSH gauge, QBER, CUSUM), attack campaigns and a live feed. |
| **Signature Studio** | Sign any message and watch 8 stages replay the real report, from digest bits to the ledger block. Includes the original *Signature Constellation* scene fed with sampled verification records. |
| **Attack Lab** | Pick any of the 17 attacks with an exact-algebra preview, then hold to launch. The original attack film replays the measured run. Also: de-twirled Bloch ellipsoid vs baseline, the evidence cascade, counterfactuals and one-click responses. |
| **Playground** | Draggable Bloch sphere, gates, a channel designer (PTM, Choi, CPTP), twirled vs raw ellipsoids, a teleportation circuit with frame tampering, Born-rule sampling, and the original *Channel Anatomy* scene. |
| **Analytics** | 10 analysis jobs: detection matrix, ROC, forgery bounds with Monte Carlo, interactive threshold designer, SPRT, fingerprint, CUSUM ARL, performance, repudiation, and Aer validation. |
| **Ledger / Incidents / Method** | 3D chain with verification sweep, Merkle trees and the tamper demo; the incident queue with responses; the science with live-parameter formulas. |

It has two themes: *Mist* (the original pastel) and *Noir* (dark). It also includes:
- the spring cursor, magnetic buttons and ripples from the original `fx.js`;
- a ⌘K command palette and WebSocket live updates;
- a reduced-motion mode and a mobile layout.

## Repository layout

```
src/sentinel/     quantum engine, TQDS protocol, QSentinel detection, adversary models, analysis, ledger
src/server/       FastAPI app: SQLite persistence, services, REST v1, /ws stream, background workers
web/              React 19 + TypeScript + Vite app (web/src/legacy = the original WebGL scenes, adapted)
config/           network topology and engine settings
tests/            engine, protocol, detection, analysis and API tests
docs/plan/        master, backend and frontend plans
dashboard/        the original v1 Streamlit dashboard (kept unchanged; `make legacy`)
docs/legacy_v1_README.md   the v1 README
```

## Audit

[`docs/AUDIT.md`](docs/AUDIT.md) lists judge-style cross-questions put to the running system, with verified answers and the defects they exposed and fixed. Examples: does quarantine really stop signing, does the drift monitor go quiet after an attack, and what happens when you replay, delay or forge a signature.

## Honest limits

- The quantum hardware is simulated **exactly** (channels, Bell sources, detectors). There is no physical device.
- Replay and impersonation can be physically invisible, because their quantum statistics are perfect. The protocol guard catches them, and the UI says so.
- The `demo` preset trades repudiation strength for speed and is labelled as such. `standard` and `high` meet all three security targets.
- Some channels are physically indistinguishable. The fingerprint reports equivalent explanations instead of guessing.
