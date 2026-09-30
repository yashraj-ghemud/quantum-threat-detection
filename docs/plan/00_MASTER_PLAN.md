# QVeris Sentinel — Master Plan

> **SIH26141 · Quantum-Inspired Cyber Threat Detection for Digital Signature Security**
> Organisation: Egreen Quanta · Theme: Blockchain & Cybersecurity · Category: Software

This is the top-level plan. The two companion documents carry the detail:

| Document | Scope |
|---|---|
| [`01_BACKEND_PLAN.md`](01_BACKEND_PLAN.md) | Protocol mathematics, quantum engine, adversary models, detection framework, security analysis, server, database, REST + WebSocket API, workers, jobs, tests. |
| [`02_FRONTEND_PLAN.md`](02_FRONTEND_PLAN.md) | Design system, motion language, every page and component, 3D scenes, data flow, mobile, accessibility, performance, tests. |

---

## 1. Where the project stands today (v1)

The uploaded project (`QVeris`, by the SIH team) already contains:

* A **Qiskit Aer teleportation channel** (`src/quantum/teleportation.py`) and noise models (`src/quantum/noise.py`).
* A **computational QDS**: an HMAC-SHA256-derived key table of Pauli eigenstates, SHA-256 message binding, and verification by measuring 256 "shots" per signature element (`src/qds/*`, `src/session.py`).
* A **threat engine**: a linear anomaly score over mismatch, fidelity, trace distance and entropy, plus protocol checks (`src/security/threat_engine.py`).
* Five **attack simulations** (`src/attacks/*`), an evaluation harness, and a Streamlit dashboard with embedded Three.js scenes.
* **1144 passing tests.** The engine is careful and honest about its own limits.

Its README lists its own limitations. Each one is a gap against the problem statement:

| # | v1 limitation (from its README) | Why it matters for PS 26141 |
|---|---|---|
| 1 | Not information-theoretically secure: unforgeability rests on HMAC as a PRF. | The PS asks to "preserve information-theoretic security guarantees". |
| 2 | Key reuse breaks unforgeability; a bound exists but nothing rotates keys automatically. | Signatures from a finite table leak the key over time. |
| 3 | Repudiation not defended (no multi-recipient / two-threshold rule). | A QDS needs non-repudiation and transferability, not only unforgeability. |
| 4 | FRR ≈ 1% at the calibrated operating point. | The PS asks for "deterministic acceptance of legitimate signatures". |
| 5 | One channel-attack model (depolarizing); low-intensity channel tampering is hard to catch (≈83%). | "Quantum channel manipulation" covers much more than depolarization. |
| 6 | "256 shots per element" measures one quantum state 256 times, which a single qubit cannot allow. | Physical fidelity of the model. |
| 7 | Teleportation correction bits are recorded as a modal count, not per qubit. | The classical half of teleportation is itself an attack surface. |
| 8 | Streamlit UI: not mobile-friendly, limited interactivity, no live stream. | The deliverable must be demonstrable and usable. |

## 2. The specific thing we build

**QVeris Sentinel.** It has two parts:

1. **A teleportation-based Quantum Digital Signature network (TQDS).** It follows the Gottesman–Chuang construction as made practical by Wallden–Dunjko–Kent–Andersson (2015) and Amiri et al. (2016): verifiers need no quantum memory, and symmetrization gives non-repudiation.
   * One-time, **truly random** private keys: CSPRNG-drawn Pauli-eigenstate labels. No PRF and no key table.
   * Public keys are **quantum**. Each label is **teleported** over a certified Bell pair to two verifiers, who measure immediately in random Pauli bases.
   * Lamport-style signing of a 256-bit message encoding. Signing reveals the labels of the key chosen by each bit.
   * **Two-threshold verification** (`s_a < s_v`) with **symmetrization**, giving unforgeability, transferability and non-repudiation. Each property has an explicit, computable error bound.
   * Every simulated qubit gets its own Bell-measurement outcome, its own correction bits and its own single-shot projective measurement.
2. **QSentinel, a quantum-inspired, ML-free threat-detection framework** with six layers of evidence:
   1. **Entanglement certification.** CHSH and a fidelity witness on sacrificial Bell pairs, with Hoeffding lower confidence bounds.
   2. **Channel forensics by Pauli-frame de-twirling tomography.** The teleported Pauli-eigenstate key samples reconstruct the channel's full Bloch map (M, c). Conditioning on each qubit's Bell outcome *undoes* the Pauli twirl that teleportation imposes, so non-unital and coherent attacks become visible. A deterministic rule set then classifies the shape of the disturbance.
   3. **Classical-frame integrity.** Correction bits are compared on a sample, and optionally checked with a Wegman–Carter MAC. This catches tampering with the classical half of teleportation.
   4. **Source-honesty test.** The QBER predicted from Bell-test correlators is compared with the QBER observed on key states. A certified channel with excess errors exposes a dishonest signer, which is how a repudiation attempt is set up. An error *deficit* exposes a man-in-the-middle relay.
   5. **Signature statistics.** Per-key mismatch tests at designed thresholds, an SPRT early abort, and forensic attribution: the pattern of failures points at who held what knowledge.
   6. **Protocol and temporal layers.** One-time-key consumption, nonce, sequence and freshness checks, authorization, and per-link CUSUM/EWMA change detection for slow, low-intensity campaigns.
   Every decision is a **named statistical test** with a p-value, an α corrected by Holm–Bonferroni, and an effect-size floor. It comes with a written explanation and the set of physically equivalent explanations the evidence cannot separate.

Around this core we build a **complete, running product**:

* A **FastAPI server** with a SQLite store. It exposes a REST API and a WebSocket event stream, and runs:
  * a live traffic generator and a key-reservoir maintainer;
  * attack campaigns;
  * background analytics jobs for forgery-probability analysis, detection matrices, ROC, threshold design, SPRT efficiency, CUSUM ARL, performance and engine validation;
  * incident management with response actions;
  * a **hash-chained, Merkle-rooted security ledger**, which ties the work to the blockchain theme.
* A **React + Three.js single-page app**: cinematic, highly interactive, animated, responsive down to phones, and bound entirely to the live backend.

### Non-negotiables

1. **No AI/ML anywhere.** Detection uses closed-form statistics only. Nothing is fitted or trained.
2. **No dummy data.** Every number on screen comes from the engine at run time. Empty states say "not measured yet" and offer the action that measures it. The only static data is configuration: the network topology and protocol presets.
3. **No stage is simulated by editing a later stage's number.** Attacks act on the physical layer (states, channels, correction bits) or on protocol messages. Every downstream consequence is computed, and a test enforces this.
4. **Honesty.** Where two attacks are physically indistinguishable, the UI says so. Where a bound is weak at a given key length, the UI shows the weak bound. Limitations are documented.

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  web/  React 19 · TypeScript · Vite · three.js (r3f) · motion · d3 · zustand │
│  Landing story · Command Center · Signature Studio · Attack Lab ·            │
│  Quantum Playground · Analytics · Ledger · Incidents · Method                │
└───────────────▲──────────────────────────────────────────────▲──────────────┘
                │ REST /api/v1/* (JSON)                         │ WebSocket /ws
┌───────────────┴──────────────────────────────────────────────┴──────────────┐
│  src/server/  FastAPI app                                                    │
│  routes → services (protocol, attacks, detection, incidents, ledger,        │
│            metrics, traffic, reservoir, jobs, selftest) → repositories      │
│  EventHub (pub/sub) · JobManager (thread pool) · SQLite (WAL) · keystore/   │
└───────────────▲─────────────────────────────────────────────────────────────┘
                │ pure-Python calls
┌───────────────┴─────────────────────────────────────────────────────────────┐
│  src/sentinel/  (NEW engine, NumPy/SciPy only)                               │
│   linalg · states · channels · teleport · bell · tomography · stats ·        │
│   sequential · protocol/{params,encoding,keys,distribution,symmetrization,   │
│   signing,verification,thresholds,guard} · adversary/* · detection/* ·      │
│   analysis/* · ledger                                                        │
└───────────────▲─────────────────────────────────────────────────────────────┘
                │ reuse + cross-validation
┌───────────────┴─────────────────────────────────────────────────────────────┐
│  src/quantum, src/qds, src/security, src/attacks, src/evaluation (v1)        │
│  Qiskit Aer teleportation circuit = reference implementation used to        │
│  validate the Sentinel superoperators; Pauli eigenstates; Clopper–Pearson.   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why a new engine next to v1 and not inside it:** v1's contract is one mutable key table with multi-shot elements, and its tests pin that behaviour. The Sentinel protocol differs at the root: one-time keys, single-shot qubits, two verifiers, symmetrization. Building it beside v1 keeps all 1144 v1 tests green. It also keeps v1 useful: its Aer circuit is the reference that the fast NumPy engine is validated against, at `max |Δρ| < 1e-9`.

**Why NumPy superoperators and not Aer in the loop:** a certified 256-bit signature bundle needs about 2.3 million teleported qubits. The teleportation map is linear. So we compute the four outcome-conditioned superoperators once per channel configuration, exactly from the 3-qubit circuit, and sample every qubit by table lookup. This is exact, not an approximation, and it runs millions of qubits per second.

## 4. Deliverables table (the PS "Delivery Table (Expected Deliverables)")

| # | Expected deliverable | Where it lives | How it is demonstrated |
|---|---|---|---|
| D1 | Quantum public-key distribution by Bell-state entanglement + teleportation | `sentinel/bell.py`, `sentinel/teleport.py`, `sentinel/protocol/distribution.py` | Studio stage 2, Command Center fibres, `/api/v1/keys/distribute` |
| D2 | Pauli correction + projective measurement for verification | `sentinel/teleport.py` (per-qubit frames), `protocol/verification.py` | Studio stage 5 qubit grid, Playground teleport mode |
| D3 | Detection of forgery, impersonation, replay, unauthorized verification, channel manipulation (+ Pauli-frame tampering, MITM key harvesting, repudiation) | `sentinel/adversary/*`, `sentinel/detection/*` | Attack Lab (17 variants), live campaigns, incidents |
| D4 | Statistical-threshold decision rules on Pauli-basis measurement statistics (no AI/ML) | `sentinel/stats.py`, `detection/*`, `protocol/thresholds.py` | Evidence cascade with p-values, α, effect floors |
| D5 | Forgery-probability analysis | `sentinel/analysis/forgery.py`, `/api/v1/theory/*` | Analytics: exact, Chernoff and Monte Carlo curves, insider-optimality search |
| D6 | Attack simulations | Attack Lab, campaigns, `analysis/detection_eval.py` | Detection matrix with Clopper–Pearson CIs |
| D7 | Security analysis (unforgeability, non-repudiation, robustness bounds) | `protocol/thresholds.py`, `analysis/design.py` | Interactive threshold designer |
| D8 | Performance evaluation (latency, throughput, complexity) | `analysis/performance.py` | Analytics performance section; live latency in every session |
| D9 | Deterministic acceptance of legitimate signatures | Threshold design on measured baseline QBER; ideal-channel preset | Live FRR counter; ε_rob shown per session |
| D10 | Mathematical modelling | `docs/sentinel/PROTOCOL.md`, `docs/sentinel/DETECTION.md`, Method page | KaTeX formulas bound to live parameters |
| D11 | Working software framework | `src/sentinel`, `src/server`, `web/` | `./scripts/start.sh` or `docker compose up` |

## 5. Milestones and acceptance criteria

| M | Name | Output | Accepted when |
|---|---|---|---|
| M0 | Plan | The three documents in `docs/plan/` | Committed and pushed |
| M1 | Engine core | `sentinel/{linalg,states,channels,teleport,bell,tomography,stats,sequential}` | All channels CPTP; ideal teleportation exact; superoperators equal Aer (`< 1e-9`) for 6 states × 6 channel families; ideal CHSH = 2√2; de-twirled tomography recovers AD/rotation maps within sampling error |
| M2 | Protocol | `sentinel/protocol/*` | Honest bundles certify; honest signatures accepted at both verifiers; one-time keys enforced; threshold designer reproduces exact tails |
| M3 | Attacks + detection | `sentinel/adversary/*`, `sentinel/detection/*` | Each of the 17 variants detected and **correctly classified** at its reference intensity; legitimate FAR = 0 in ≥ 200 honest runs at the default α; forensic attribution names the insider in insider forgery |
| M4 | Analysis | `sentinel/analysis/*` | Each job returns its schema; forgery Monte Carlo agrees with exact binomial within its CI; insider optimum = 1/3 ± 1e-3 |
| M5 | Server | `src/server/*` | All endpoints tested with `TestClient`; WebSocket receives `session.completed`; ledger verifies; tamper demo detected and reverted; restart-safe |
| M6 | Frontend foundation | `web/` shell | Builds with no type errors; shell renders at 1440×900 and 390×844 |
| M7 | Frontend pages | All routes | Every route renders live data with zero console errors in Playwright on desktop and mobile |
| M8 | Polish | Visual review pass | Screenshot review of every route; reduced-motion mode; Lighthouse-style budgets met |
| M9 | Packaging | Scripts, Docker, CI, README | A fresh clone runs with one command; full test suite green |

## 6. Repository layout (target)

```
config/            quantum_config.yaml (v1) · sentinel.yaml · network.yaml
src/
  quantum/ qds/ security/ attacks/ evaluation/ utils/   (v1, kept)
  sentinel/        NEW engine (see backend plan §19)
  server/          NEW FastAPI app (see backend plan §10)
web/               NEW frontend (see frontend plan §3)
tests/             v1 tests + tests/sentinel/ + tests/server/
experiments/       v1 experiments + sentinel_report.py (CLI over analytics jobs)
docs/
  plan/            this plan
  sentinel/        PROTOCOL.md · DETECTION.md · API.md · ATTACKS.md
scripts/           dev.sh · start.sh · selftest.sh
Dockerfile · docker-compose.yml · Makefile · .github/workflows/ci.yml
```

The Streamlit dashboard (`dashboard/`, `.streamlit/`, `tests/dashboard/`) is **replaced** by `web/`. Its storyboard ("The Journey of a Signature") and colour semantics carry forward into the new UI. The old code stays in git history (commit `0877e60`).

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Qubit counts (millions per bundle) cost CPU and memory | Exact table-driven sampling; int8 arrays; keystore files for active bundles only; presets (`demo` / `standard` / `high`) |
| Security bounds are weak at small L | The threshold designer reports achieved ε honestly; the `high` preset reaches negligible ε; the UI shows the numbers rather than a green tick |
| Physically equivalent attacks cannot be separated | The classifier reports the equivalence class and its alternatives ("isotropic contraction: depolarizing noise **or** random-basis intercept-resend on ~f pairs") |
| WebGL cost on phones | Adaptive quality tiers, a static fallback, `prefers-reduced-motion`, pausing off-screen canvases |
| Two long-running loops (traffic, reservoir) starve API requests | Bounded thread pool; a semaphore on heavy work; traffic pauses with no clients connected |
| Drift between frontend and backend types | TypeScript types generated from the server's OpenAPI schema (`npm run gen:api`) |

## 8. Definition of done

* `./scripts/start.sh` on a fresh clone installs, builds and serves the whole app at `http://localhost:8000`.
* Python tests (v1 + Sentinel + server) pass, the web type-check and build pass, and Playwright smoke passes on desktop and mobile viewports.
* Opening the app with an empty database shows empty states, never fabricated numbers. Starting traffic populates everything from real runs.
* Every attack in the catalog can be launched from the UI, is detected, is explained, raises an incident, and is anchored in the ledger.
* The README explains how to run, what is claimed, what is not, and where every number comes from.

## 9. References that shaped the protocol

* D. Gottesman, I. Chuang, *Quantum Digital Signatures* (2001).
* P. Wallden, V. Dunjko, A. Kent, E. Andersson, *Quantum digital signatures with quantum-key-distribution components*, PRA 91, 042304 (2015).
* R. Amiri, P. Wallden, A. Kent, E. Andersson, *Secure quantum signatures using insecure quantum channels*, PRA 93, 032325 (2016).
* J. F. Clauser, M. A. Horne, A. Shimony, R. A. Holt, *Proposed experiment to test local hidden-variable theories* (1969).
* A. Wald, *Sequential Tests of Statistical Hypotheses* (1945); E. S. Page, *Continuous inspection schemes* (1954).
* M. N. Wegman, J. L. Carter, *New hash functions and their use in authentication and set equality* (1981).

The PS's "Dataset Link" (a Google Drive folder) was not reachable from the build environment, which blocks drive.google.com. The protocol therefore follows the published constructions above. If the folder specifies a different teleportation-QDS variant, the engine is parametric enough to adopt it (see backend plan §3.11).
