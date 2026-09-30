# QVeris Sentinel — Backend Plan (engine · protocol · detection · server)

> Companion to [`00_MASTER_PLAN.md`](00_MASTER_PLAN.md). This document specifies **every** backend piece
> precisely enough to implement it without further design decisions: the mathematics, the algorithms,
> the constants and why they were chosen, the data structures, the API, the database, the workers, and
> the tests. When implementation discovers a better choice, this document is updated in the same commit.

---

## Table of contents

0. [Principles](#0-principles)
1. [Notation and glossary](#1-notation-and-glossary)
2. [System context and threat model](#2-system-context-and-threat-model)
3. [Protocol specification — TQDS](#3-protocol-specification--tqds)
4. [Quantum simulation engine](#4-quantum-simulation-engine)
5. [Adversary models (17 variants)](#5-adversary-models-17-variants)
6. [QSentinel detection framework](#6-qsentinel-detection-framework)
7. [Security analysis and forgery probability](#7-security-analysis-and-forgery-probability)
8. [Performance model and complexity](#8-performance-model-and-complexity)
9. [Security ledger](#9-security-ledger)
10. [Server architecture](#10-server-architecture)
11. [Persistence](#11-persistence)
12. [REST API reference](#12-rest-api-reference)
13. [WebSocket protocol](#13-websocket-protocol)
14. [Background workers](#14-background-workers)
15. [Analytics jobs](#15-analytics-jobs)
16. [Configuration](#16-configuration)
17. [Errors, validation, limits, logging, hardening](#17-errors-validation-limits-logging-hardening)
18. [Testing strategy](#18-testing-strategy)
19. [Module map and signatures](#19-module-map-and-signatures)
20. [Build, run, deploy](#20-build-run-deploy)
21. [Implementation order](#21-implementation-order)
22. [Known limitations (stated up front)](#22-known-limitations-stated-up-front)

---

## 0. Principles

| # | Principle | Consequence in code |
|---|---|---|
| P1 | **No AI/ML.** | Only closed-form statistics: exact binomial/hypergeometric tails, Clopper–Pearson, Hoeffding, Chernoff–KL, χ², two-proportion z, Holm–Bonferroni, SPRT, CUSUM, EWMA. No fitted parameters except *measured baselines* (sample means/counts). |
| P2 | **No fabricated numbers.** | Everything the API returns is computed by the engine at run time or loaded from rows the engine wrote. No seed data other than configuration (topology, presets). |
| P3 | **Attacks act on physics or on protocol messages, never on results.** | Adversaries receive states/channels/correction bits/envelopes and return modified ones; they have no handle on `VerificationReport` or `Assessment`. A test greps for result mutation inside `sentinel/adversary/`. |
| P4 | **Information boundaries are enforced in code.** | Verifiers act through a `VerifierView` holding only what that party legitimately holds; forgers receive an `AdversaryKnowledge` object built from explicit sources (public data, captured classical traffic, insider records). The private key (`KeyBundle.labels`) is never passed to adversary code. |
| P5 | **Every decision is explainable.** | A `Finding` carries statistic, null hypothesis, p-value, α, effect size, effect floor, and a human sentence. A fused `Assessment` carries the decision list branch that fired and the alternatives the evidence cannot exclude. |
| P6 | **Exact where possible, sampled where physical.** | Superoperators, channel maps, predicted statistics are exact linear algebra. Measurement outcomes, Bell outcomes and key material are sampled per qubit. |
| P7 | **Honest limits.** | Weak bounds are reported as weak. Physically indistinguishable attacks are reported as an equivalence class. |

---

## 1. Notation and glossary

| Symbol | Meaning |
|---|---|
| X, Y, Z | Pauli matrices σₓ, σᵧ, σ_z; I is the identity |
| ℓ ∈ {0..5} | Six-state label. **Order is fixed**: 0=`|+⟩`(X,+1), 1=`|−⟩`(X,−1), 2=`|+i⟩`(Y,+1), 3=`|−i⟩`(Y,−1), 4=`|0⟩`(Z,+1), 5=`|1⟩`(Z,−1). basis(ℓ)=ℓ//2 (0=X,1=Y,2=Z), bit(ℓ)=ℓ%2 (0 ↔ eigenvalue +1). This order makes basis index = Bloch component index. |
| r ∈ ℝ³ | Bloch vector, ρ = ½(I + r·σ) |
| v = (1, r) | Homogeneous Bloch 4-vector |
| R | Pauli transfer matrix (PTM), 4×4 real, R_ij = ½ Tr(σ_i 𝓔(σ_j)), σ₀ = I. 𝓔(ρ) ↔ v ↦ R v |
| (M, c) | Affine Bloch map of a CPTP channel: R = [[1,0],[c, M]], r ↦ M r + c |
| \|Φ⁺⟩ | (\|00⟩+\|11⟩)/√2 |
| k = (m₀, m₁) | Alice's Bell-measurement outcome for one teleportation (**sent frame**); index k = 2·m₀ + m₁ |
| c = (c₀, c₁) | Correction bits **received** by the verifier (c = k unless tampered) |
| C_c | Correction unitary Z^{c₀} X^{c₁} (X applied first, then Z) |
| P_k | PTM of conjugation by the Pauli σ_k = X^{m₁} Z^{m₀}; diagonal ±1 |
| β ∈ {0,1,2} | A verifier's measurement basis (X, Y, Z) |
| o ∈ {0,1} | Measurement outcome, 0 ↔ eigenvalue +1 |
| K | Number of keys in a bundle = 2 × `digest_bits` (a 0-key and a 1-key per bit) |
| L | Positions per key **kept for signing** (after parameter estimation removes a sample) |
| L_dist | Positions per key distributed = ⌈L / (1 − f_pe)⌉ |
| n | Tested positions in one verification set (verifier basis = revealed label basis) |
| s_a, s_v | Mismatch-rate thresholds: s_a for acceptance by the first recipient, s_v for transfer (s_a < s_v) |
| e | Honest mismatch rate (QBER) on tested positions |
| p_f | Minimal mismatch rate achievable by a forger (external ½, insider ⅓) |
| ε_rob, ε_forge, ε_rep | Robustness (honest rejected), forgery, repudiation failure probabilities |
| QBER | Quantum bit error rate: mismatch fraction on basis-matched positions |
| PE | Parameter estimation (the sampled positions whose labels Alice reveals after distribution) |
| FAR / FRR | **False Acceptance Rate** = fraction of attack runs not detected; **False Rejection Rate** = fraction of legitimate runs flagged/rejected. (Same convention as v1.) |

---

## 2. System context and threat model

### 2.1 Parties

| Id | Role | Trust | Notes |
|---|---|---|---|
| `alice` | Signer (group `g-alice`) | Honest by default; **dishonest** in the repudiation scenario | Holds private one-time keys (labels) |
| `diana` | Signer (group `g-diana`) | Honest | Second signer so the network has more than one group |
| `bob` | Verifier, first recipient of `g-alice` | Honest by default; **dishonest insider** in insider forgery | No quantum memory: measures on arrival |
| `charlie` | Verifier, second recipient of `g-alice`, first recipient of `g-diana` | Honest | |
| `erin` | Verifier, second recipient of `g-diana` | Honest; used as a *non-recipient* in unauthorized verification of `g-alice` | |
| `eve` | External adversary | Malicious | Controls quantum fibres and classical channels (read/modify), not labs |
| `mallory` | Rogue signer (group `g-mallory`, hidden) | Malicious | Holds valid keys *of her own*; used for identity-swap impersonation |

### 2.2 Channels

* **Quantum links** `signer↔verifier`: carry one half of each Bell pair from the entanglement source (at the signer) to the verifier. The baseline noise channel 𝒩₀ (configured, *unknown to the detector*) acts on the verifier's half. Eve may add a channel 𝒜, measure-and-resend, or substitute the half entirely.
* **Classical teleportation channel** `signer→verifier`: carries the correction bits k. Eve can read everything. She can modify the bits unless the link runs with `authenticated_classical=true`, in which case a Wegman–Carter MAC protects them (§3.4.4).
* **Classical verifier channel** `bob↔charlie` (and `charlie↔erin`): authenticated and private. It carries symmetrization records and forwarded signatures. This is the standard assumption of the no-memory QDS literature.
* **Signature delivery** `signer→first recipient`: classical, public. Eve can capture, delay or replay it.

### 2.3 Adversary goals mapped to the PS

| PS threat | Our categories |
|---|---|
| Forgery | `FORGERY` (external blind, insider, oracle-assisted k-bit) |
| Impersonation | `IMPERSONATION` (identity swap with own keys, keyless claim) |
| Replay | `REPLAY` (resubmission, forward-replay, delay) |
| Unauthorized verification | `UNAUTHORIZED_VERIFICATION` (non-recipient attempt, MITM key harvesting) |
| Quantum channel manipulation | `CHANNEL_MANIPULATION` (depolarize, dephase, amplitude-damp, coherent rotation, intercept–resend, classical Pauli-frame tampering) |
| (extension) | `REPUDIATION` (dishonest signer distributing inconsistent keys) |

### 2.4 Assumptions (explicit)

A1 Attacks are i.i.d. across positions within a run (collective attacks). Coherent attacks across positions are out of scope (§22).
A2 Verifiers have no quantum memory and measure each received qubit immediately in a basis drawn from the CSPRNG.
A3 The verifier↔verifier classical channel is authenticated and private.
A4 Classical channels have no natural bit errors after link-layer checks. Any correction-bit mismatch is therefore adversarial.
A5 The detector does not know 𝒩₀. It **measures** a baseline during a trusted calibration window (§6.8).
A6 Message compression uses SHA-256 in `sha256` mode (computational collision resistance, the only computational assumption). `raw` mode signs up to 31 message bytes bit-by-bit, with no computational assumption.

---

## 3. Protocol specification — TQDS

### 3.1 Parameters

`ProtocolParams` (immutable dataclass, validated):

| Field | Type | Default (`standard`) | Range | Meaning |
|---|---|---|---|---|
| `digest_bits` | int | 256 | {32, 64, 128, 256} | Bits signed. Values below 256 are **analysis-only** (flag `analysis_only=True`). |
| `L` | int | 4096 | 64 … 16384 | Positions per key kept for signing |
| `f_pe` | float | 0.10 | 0.02 … 0.5 | Fraction of distributed positions sacrificed for PE |
| `bell_pairs_per_setting` | int | 2000 | 200 … 20000 | Test pairs per Bell setting per verifier link (7 settings) |
| `eps_rob_target` | float | 1e-9 | 1e-15 … 1e-2 | Target message-level robustness failure |
| `eps_forge_target` | float | 1e-6 | 1e-15 … 1e-1 | Target **per-key** forgery probability |
| `eps_rep_target` | float | 1e-6 | — | Target per-key repudiation probability. Reported; a shortfall warns but does not abort. |
| `delta_pe` | float | 1e-6 | — | Confidence parameter of the QBER upper bound used for design |
| `delta_bell` | float | 1e-5 | — | Confidence parameter of the CHSH / witness lower bounds |
| `p_forge_insider` | float | 1/3 | fixed | §7.2 |
| (derived) `n_min` | int | from design | — | A set needs n ≥ n_min tested positions, else INCONCLUSIVE. n_min is the exact Bin(⌊L/2⌋, ⅓) quantile at a small share of ε_rob (§7.4), **not** a fixed fraction: with L = 2048 a fixed 85% floor would make ~15% of honest signatures fail somewhere among 512 sets. |
| `freshness_window_s` | float | 120 | 5 … 3600 | Maximum signature age |
| `encoding` | enum | `sha256` | `sha256` \| `raw` | §3.7 |

Presets (`config/sentinel.yaml → presets`):

| Preset | L | bell_pairs_per_setting | Qubits per bundle (256-bit) | Intended use |
|---|---|---|---|---|
| `demo` | 1024 | 1000 | 256·2·1138·2 ≈ 1.17 M | Tests, quick lab runs (relaxed targets: ε_rob 1e-6, ε_forge 1e-4) |
| `standard` | 4096 | 2000 | 256·2·4552·2 ≈ 4.66 M | Live traffic, Studio (meets ε_rob 1e-9, ε_forge 1e-6, ε_rep 1e-6) |
| `high` | 8192 | 4000 | 256·2·9103·2 ≈ 9.32 M | Negligible bounds (all targets 1e-12) |
| `analysis` | 1024, digest_bits=32 | 1000 | 32·2·1138·2 ≈ 0.15 M | Analytics jobs (thousands of runs; relaxed targets) |

Measured on the build container (4 vCPU): `demo` 150 ms, `standard` 460 ms, `high` 930 ms per bundle (≈ 10 M qubits/s). `standard` was first planned at L = 2048, but at that length the repudiation bound is only ≈ 0.9 at message level; L = 4096 meets all three targets, so it is the default. Each preset also sets δ_pe and α_SPRT small enough that they fit inside its robustness budget (demo 1e-8/1e-11, standard 1e-10/1e-13, high 1e-14/1e-17).

### 3.2 Key generation (one-time, CSPRNG)

For a group G = (signer S, recipients (V₁, V₂)) a **bundle** B has:

* `bundle_id` (uuid4), `group_id`, `signer_id`, `recipients`, `params`, `created_at`.
* Private labels `λ[i, b, j] ∈ {0..5}` for bit i ∈ [0, digest_bits), value b ∈ {0,1}, position j ∈ [0, L_dist).

**Label sampling (unbiased, vectorised).** Draw ⌈1.03·N⌉ + 64 bytes from `secrets.token_bytes`. Keep bytes < 252 (252 = 42·6). Take `byte % 6`. Repeat if short. The rejection rate is 4/256, and the result is exactly uniform over 6. Selftest check `rng.labels_uniform` runs a χ² test on 60 000 draws (df = 5) and requires p > 1e-6.

In **seeded mode** (tests and reproducible analytics only), labels come from `PCG64DXSM(seed)`. The seeded mode is refused when `QVERIS_ENV=production`.

### 3.3 Distribution phase (per bundle)

For each recipient V ∈ {V₁, V₂} over link (S, V):

1. **Entanglement distribution.** The source prepares |Φ⁺⟩ pairs and sends one half to V over the quantum link. The state shared by S and V is ρ_SV = (𝟙 ⊗ 𝒩)(|Φ⁺⟩⟨Φ⁺|), where 𝒩 = 𝒜 ∘ 𝒩₀ (attack after baseline). Some attacks make pairs heterogeneous: a fraction f of pairs is substituted by Eve (§5).
2. **Bell test (certification).** S and V choose a random subset of pairs as test pairs. That is 7 × `bell_pairs_per_setting` per link, disjoint from key pairs. The subset is announced *after* distribution, so Eve cannot tell test pairs from key pairs. Settings, as unit vectors (α for S, β for V):
   * CHSH: A₀ = ẑ, A₁ = x̂; B₀ = (ẑ + x̂)/√2, B₁ = (ẑ − x̂)/√2; pairs (A₀B₀), (A₀B₁), (A₁B₀), (A₁B₁).
   * Witness: (x̂, x̂), (ŷ, ŷ), (ẑ, ẑ).
   Outcomes a, b ∈ {±1} are sampled from P(a, b | α, β) = Tr[(Π_a^α ⊗ Π_b^β) ρ_SV], with Π_±^n = (I ± n·σ)/2.
3. **Public-key teleportation.** For each key position (i, b, j), S teleports the eigenstate with label λ[i,b,j] to V through one key pair. Each teleportation gives:
   * the sent frame k ~ P(k | ℓ), as the Bell outcome;
   * the classical transmission of k, which may be tampered into c;
   * V's immediate measurement in a CSPRNG basis β, giving outcome o. V stores (β, o, c) and nothing else.
   Both recipients receive a copy for **every** position: the same label, independent qubits.
4. **Parameter estimation (PE).** S draws the PE positions from the CSPRNG: exactly `n_pe = L_dist − L` per key. For those positions S reveals (ℓ, k) and V reveals (β, o, c). The positions are then discarded from the key. PE produces the statistics in §6: per-basis QBER, de-twirled tomography, frame integrity, source consistency.
5. **Design check.** From the PE QBER upper bound e_ucb (Clopper–Pearson, 1 − δ_pe, max over both copies), the threshold designer (§7.4) computes (s_a, s_v) and the achieved ε's. If no feasible s_a < s_v exists, finding D9 fires and the bundle is marked COMPROMISED with reason "insufficient security margin".
6. **Symmetrization.** For each key, V₁ picks a CSPRNG subset S₁ of exactly ⌊L/2⌋ of its L kept positions and sends (j, β, o) for j ∈ S₁ to V₂. V₂ does the same with S₂ towards V₁. Afterwards:
   * V₁ holds `own₁` = records at positions ∉ S₁ (own copy) and `recv₁` = V₂'s records at positions ∈ S₂.
   * V₂ holds `own₂` = own records at positions ∉ S₂ and `recv₂` = V₁'s records at positions ∈ S₁.
7. **Assessment.** The detection framework (§6) fuses all findings. If the verdict is CERTIFIED, the bundle becomes `ACTIVE`. Otherwise it becomes `COMPROMISED`: private labels are deleted, the verifier records are kept for forensics, and the bundle can never sign (unless a lab counterfactual run explicitly bypasses the policy, §5.4).

### 3.4 Teleportation details

#### 3.4.1 Circuit (reference; identical to v1's `build_teleportation_circuit`)

q₀ = input (signer), q₁ = signer's half of the Bell pair, q₂ = verifier's half.
|Φ⁺⟩ on (q₁, q₂) → noise on q₂ → CX(q₀→q₁) → H(q₀) → measure q₀ → m₀, q₁ → m₁ → verifier applies X^{c₁} then Z^{c₀}.

#### 3.4.2 Per-qubit semantics

* P(k | ℓ) = (R_k v_ℓ)₀. It equals ¼ for any channel acting on q₂ alone, because the signer's reduced state stays I/2. It is computed anyway, not assumed.
* The verifier's Bloch vector for (ℓ, k, c) is `(P_{C_c} R_k v_ℓ)_{1:3} / P(k|ℓ)`, where `P_{C_c}` is the PTM of the correction unitary.
* P(o = 0 | ℓ, k, c, β) = (1 + r_β)/2.

#### 3.4.3 Correction-bit tampering

Eve flips c₀ with probability q₀ and c₁ with probability q₁, independently per qubit (`channel.pauli_frame`). The verifier applies C_c ≠ C_k. The resulting state is an extra Pauli (Z for c₀, X for c₁) on the teleported state.

#### 3.4.4 Optional authenticated classical channel (Wegman–Carter)

When `link.authenticated_classical = true`, the signer computes a tag over the k-stream of each (bundle, verifier):

* The k-stream is packed into 61-bit words w₁ … w_m.
* The tag is t = (Σ_{i=1}^{m} w_i · r^{m−i+1} + s) mod p, with p = 2⁶¹ − 1.
* (r, s) is drawn once per bundle from the link's pre-shared key pool: the CSPRNG, stored in the server-side link secret table, never in API output.

The verifier recomputes the tag over the *received* c-stream. A mismatch makes D6 fire conclusively over **all** positions, not just the PE sample. The forgery probability for a single tampered stream is ≤ m/p ≈ 2⁻⁴⁰ for m ≤ 2²¹ words.

### 3.5 Signing

1. Build the **envelope** `{protocol:"QVERIS-TQDS/1", group_id, signer_id, recipients:[V₁,V₂], bundle_id, seq, timestamp, nonce, encoding, message}`:
   * `seq` is the signer's monotonic counter per group;
   * `nonce` is 128-bit CSPRNG hex;
   * `timestamp` is float Unix seconds.
2. **Encode** it to `digest_bits` bits (§3.7).
3. For each bit i with value d_i, reveal `λ[i, d_i, j]` for all kept positions j. Positions are in the canonical kept order: ascending distributed index with PE positions removed.
4. The signature is `(envelope, revealed: uint8[digest_bits, L])`. Its wire size is digest_bits·L bytes, 512 KiB at `standard`. It is kept server-side; the API returns a digest of it plus a display sample.
5. The signer marks the bundle `SIGNED` (one-time: a second signing attempt raises `KeyReuseError`).

### 3.6 Verification and transfer

**Verifier V with view (own, recv) and threshold s** (V₁ uses s_a; V₂ as transferee uses s_v):

For each bit i (key (i, d_i)) and each set X ∈ {own, recv}:
* T = {j ∈ X : β_j = basis(revealed_ij)} (the tested positions); n = |T|;
* m = |{j ∈ T : o_j ≠ bit(revealed_ij)}| (mismatches);
* the set is INCONCLUSIVE if n < n_min, otherwise PASS if m ≤ ⌊s·n⌋, otherwise FAIL.

The key passes iff both sets PASS. The signature is **accepted by V** iff every key passes and every protocol check (§3.9) passes.

**SPRT early abort** (efficiency, §6.4). Before the fixed test, V streams the tested positions of each key in a CSPRNG order through Wald's SPRT:
* hypotheses H₀: rate = e_ucb, H₁: rate = p_f,insider = ⅓;
* error rates α_s = 1e-9 (probability of rejecting an honest key) and β_s = 1e-6;
* per-observation LLR: a mismatch adds ln(p₁/p₀), a match adds ln((1−p₁)/(1−p₀));
* reject when LLR ≥ A = ln((1−β_s)/α_s).

The SPRT is used **only to reject early**. Acceptance always requires the fixed test, so the fixed-test forgery bound (§7) is unchanged. α_s adds to ε_rob, and the designer accounts for it. The report includes the observations used vs. available (the ASN saving).

**Transfer.** If V₁ accepts, V₁ forwards (signature, `forwarded_by=V₁`) to V₂ over the authenticated verifier channel. V₂ runs the same procedure with s_v. The session records both decisions. The case **V₁ accept ∧ V₂ reject** is a *dispute* (finding S10).

### 3.7 Message encoding

* **`sha256`:**
  * bytes = `b"QVERIS-TQDS/1"` ‖ 0x1F ‖ join(0x1F, [group_id, signer_id, V₁, V₂, bundle_id, str(seq), f"{timestamp:.6f}", nonce, encoding, message_utf8]);
  * bits = the first `digest_bits` bits of SHA-256(bytes), MSB-first per byte.
  The freshness metadata is therefore **signed**: altering a nonce or seq changes the digest and requires forging keys.
* **`raw`:**
  * requires len(message_utf8) ≤ 31;
  * bytes = [len] ‖ message ‖ 0x00 padding to 32 bytes; bits = 256 bits MSB-first;
  * only the message is signed. Envelope metadata is checked (§3.9) but unauthenticated, so replay protection rests on one-time bundle consumption, which is still conclusive.

### 3.8 Why this is information-theoretic (and where it is not)

Unforgeability of a key the forger has not seen rests only on the forger's inability to predict single-shot measurement outcomes of states from the six-state alphabet that it holds at most one copy of (§7.2). There is no computational assumption: labels come from an entropy source, and tests are exact tail bounds. The computational element is `sha256` compression; `raw` mode removes it. Assumptions A1–A4 bound the claim.

### 3.9 Protocol guard (per verifier, checked before the quantum tests)

| Order | Check | Failure → | Conclusive |
|---|---|---|---|
| 1 | `verifier_id ∈ bundle.recipients` | S1 → `UNAUTHORIZED_VERIFICATION` | yes |
| 2 | `bundle.signer_id == envelope.signer_id` and `bundle.group_id == envelope.group_id` | S2 → `IMPERSONATION` | yes |
| 3 | bundle status ∈ {ACTIVE, SIGNED} and not consumed by this verifier | CONSUMED → S3 `REPLAY`; COMPROMISED/REVOKED/EXPIRED → S3 `POLICY` | yes |
| 4 | `nonce` never seen by this verifier | S4 → `REPLAY` | yes |
| 5 | `seq` > last accepted seq from this signer at this verifier | S5 → `REPLAY` | yes |
| 6 | now − timestamp ≤ `freshness_window_s` and timestamp ≤ now + 5 s (clock skew) | S6 → `REPLAY` (delay) | yes |

The quantum tests run **even when a guard check fails**, and their result is reported. For a replay they show clean statistics, which is the honest evidence that replay is invisible to physics. Any verification attempt, pass or fail, marks the bundle consumed for that verifier, because the labels are now public.

State is stored in the tables `nonces`, `signer_sequences` and `bundle_consumption` (§11).

### 3.10 Bundle lifecycle

```
DISTRIBUTING ──assessment CERTIFIED──▶ ACTIVE ──sign──▶ SIGNED ──V₁ verifies──▶ CONSUMED(V₁) ──V₂──▶ CONSUMED
      │                                  │  └──TTL 24h──▶ EXPIRED
      └──assessment COMPROMISED──▶ COMPROMISED (quarantined; labels shredded)
ACTIVE ──operator revoke / link quarantine──▶ REVOKED (labels shredded)
```
Transitions are atomic in the DB (`UPDATE … WHERE status = ?`). Each emits a `bundle.*` ledger transaction.

### 3.11 Extension points

* `n_recipients > 2`: symmetrization generalises (each recipient forwards a random 1/N share to each peer). Out of scope for this version; the data model stores `recipients` as a list.
* Alternative bases (BB84 X/Z only): `states.ALPHABET` can switch; then p_f,insider = ¼ + … and the designer uses the alphabet's constant. This is where a Drive-specified variant would slot in.

---

## 4. Quantum simulation engine

### 4.1 Representations and conventions

* Tensor order **(q₀, q₁, q₂)**, big-endian kron: `kron(a, kron(b, c))`.
* States enter as density matrices ρ; single-qubit maps are carried as **PTM R** (4×4 real) plus the Kraus list they came from.
* Conversions in `linalg.py`:
  * `kraus_to_ptm(K)`: R_ij = ½ Σ_m Tr(σ_i K_m σ_j K_m†)
  * `ptm_to_choi(R)`: J = Σ_{a,b} |a⟩⟨b| ⊗ 𝓔(|a⟩⟨b|), where 𝓔 comes from R via the Pauli expansion of |a⟩⟨b|
  * `is_cptp(R, tol=1e-10)`: eig(J) ≥ −tol and Tr_out J = I
  * `ptm_affine(R)` → (M, c); `bloch_to_rho(r)`, `rho_to_bloch(ρ)`
  * `partial_trace(ρ, keep, dims)`
  * `polar(M)` → (U, P) via SVD, with det-sign fix
  * `rotation_axis_angle(U)`
  * `pauli_ptm(k)`: diagonal signs, P_I = diag(1,1,1,1), P_X = diag(1,1,−1,−1), P_Y = diag(1,−1,1,−1), P_Z = diag(1,−1,−1,1).

### 4.2 Channel library (`channels.py`)

`Channel` is a frozen dataclass: `name`, `params`, `kraus: tuple[np.ndarray,...]`, cached `ptm`, `affine`. A factory `channel_from_spec(spec: dict)` accepts `{"type": ..., **params}`.

| type | params (range) | Kraus | PTM / affine |
|---|---|---|---|
| `identity` | — | {I} | I₄ |
| `depolarizing` | p ∈ [0,1] | √(1−3p/4) I, √(p/4) X, √(p/4) Y, √(p/4) Z | M = (1−p) I, c = 0 |
| `dephasing` | p ∈ [0,1], axis ∈ {x,y,z} | √(1−p) I, √p σ_axis | M = diag with the two ⊥ components × (1−2p) |
| `bit_flip` | p | = dephasing(axis=x) | |
| `phase_flip` | p | = dephasing(axis=z) | |
| `bit_phase_flip` | p | = dephasing(axis=y) | |
| `amplitude_damping` | γ ∈ [0,1] | [[1,0],[0,√(1−γ)]], [[0,√γ],[0,0]] | M = diag(√(1−γ), √(1−γ), 1−γ), c = (0,0,γ) |
| `phase_damping` | λ ∈ [0,1] | [[1,0],[0,√(1−λ)]], [[0,0],[0,√λ]] | M = diag(√(1−λ), √(1−λ), 1) |
| `rotation` | axis n ∈ S², θ ∈ [−π, π] | U = exp(−iθ n·σ/2) | M = Rodrigues(n, θ), c = 0 |
| `pauli` | pₓ, p_y, p_z ≥ 0, Σ ≤ 1 | √p₀ I, √pₓ X, √p_y Y, √p_z Z | M = diag(1−2(p_y+p_z), 1−2(pₓ+p_z), 1−2(pₓ+p_y)) |
| `measure_prepare` | basis ∈ {x,y,z} | \|±_b⟩⟨±_b\| | M = e_b e_bᵀ, c = 0 (entanglement-breaking) |
| `composite` | `channels: [spec…]` (applied in order) | all products K⁽²⁾K⁽¹⁾ (pruned where ‖K‖_F < 1e-14) | R = R_n ⋯ R_1 |

A link's baseline and an attack are both lists of specs, composed as `composite(baseline + attack)`. Validation: every constructed channel passes `is_cptp` (tested over a parameter grid).

### 4.3 Teleportation superoperators (`teleport.py`)

`TeleportationModel(channel_B: Channel, channel_A: Channel = identity)`:

1. ρ_AB = (𝒩_A ⊗ 𝒩_B)(|Φ⁺⟩⟨Φ⁺|), computed with Kraus on a 4×4.
2. U = (H ⊗ I ⊗ I) · (CX₀₁ ⊗ I).
3. For each Pauli basis operator σ_j (j = 0..3) as the "input" (by linearity): Ψ_j = U (σ_j ⊗ ρ_AB) U†.
4. For each k = (m₀, m₁) with projector Π_k = |m₀⟩⟨m₀| ⊗ |m₁⟩⟨m₁| ⊗ I: E_k(σ_j) = Tr₀₁(Π_k Ψ_j Π_k), a 2×2 matrix on q₂.
5. R_k[i, j] = ½ Tr(σ_i E_k(σ_j)), giving four 4×4 real matrices, **unnormalised** (trace-decreasing).
6. Correction PTMs: `P_C[c] = PTM(Z^{c₀}) · PTM(X^{c₁})`.
7. **Tables** for the six labels, all 4 sent frames and all 4 received frames:
   * `p_k[ℓ, k] = (R_k v_ℓ)₀` → shape (6, 4)
   * `bloch[ℓ, k, c] = (P_C[c] R_k v_ℓ)_{1:3} / p_k[ℓ,k]` → shape (6, 4, 4, 3)
   * `p_plus[ℓ, k, c, β] = (1 + bloch[ℓ,k,c,β]) / 2` → shape (6, 4, 4, 3)
8. General input (Playground): `teleport_bloch(r) → {k: (p_k, bloch_pre, bloch_post)}`.

Properties asserted in tests:
* noiseless: `p_k ≡ ¼`, `bloch[ℓ,k,k] = r_ℓ` exactly;
* Σ_k P_C[k] R_k equals the averaged (twirled) channel;
* for a Pauli channel 𝒩, Σ_k P_C[k] R_k = PTM(𝒩).

**Cache.** Models are memoised by the canonical JSON of (channel_B spec, channel_A spec), with an LRU of 256 entries.

### 4.4 Batched trajectory sampler

`sample_teleportations(model, labels: uint8[N], rng, bases: uint8[N], flip_c0: bool[N] | None, flip_c1: bool[N] | None) → (k: uint8[N], c: uint8[N], o: uint8[N])`:

```
u1 = rng.random(N);  cp = cumsum(p_k, axis=1)[labels]          # (N,4)
k  = (u1 > cp[:,0]) + (u1 > cp[:,1]) + (u1 > cp[:,2])          # inverse CDF
c  = k ^ (flip_c0 << 1) ^ flip_c1                              # tamper (k index = 2*m0 + m1)
pp = p_plus[labels, k, c, bases]
o  = (rng.random(N) >= pp).astype(uint8)                       # 0 ↔ +1
```

All operations are O(N) and memory-bound. N = 2.3 M uses roughly 60 MB peak for float64 temporaries, so the sampler processes chunks of 2²⁰. Heterogeneous positions (Eve substitutes a fraction) use a boolean mask and a second model; §5 defines each.

### 4.5 Bell-pair statistics (`bell.py`)

* `correlation_tensor(ρ_AB)`: T_ij = Tr[ρ (σ_i ⊗ σ_j)], with local vectors a, b.
* `joint_probs(ρ_AB, α, β)`: P(±,±) = ¼(1 ± a·α ± b·β ± αᵀTβ) (signs by outcome).
* **Closed forms** (tested): for ρ = (𝟙⊗𝒩)(Φ⁺), T = T₀ Mᵀ with T₀ = diag(1, −1, 1). Hence:
  * F := ⟨Φ⁺|ρ|Φ⁺⟩ = (1 + T_xx − T_yy + T_zz)/4 = (1 + tr M)/4;
  * S = E(A₀,B₀) + E(A₀,B₁) + E(A₁,B₀) − E(A₁,B₁) with E = αᵀTβ;
  * for depolarizing(p): S = 2√2 (1−p) and F = 1 − 3p/4.
* `sample_bell_test(ρ_eff, n_per_setting, rng)` → counts for 7 settings × 4 outcomes (multinomial). For a substituted fraction f, ρ_eff = (1−f)ρ + f·I/4 per pair. This is exact, because pairs are independent and the counts depend only on the per-pair mixture.
* `estimate_bell(counts, delta)` returns:
  * `E_hat` per setting, with a Clopper–Pearson interval on q = P(ab = +1) at δ/7, mapped through E = 2q − 1;
  * `S_hat`, `S_lcb` (sum of the per-term worst-case bounds: lower for the three + terms, upper for the − term), and `S_se` (√Σ(1−E²)/n);
  * `F_hat`, `F_lcb`;
  * per-basis **Bell-predicted error rates**: e_x = (1 − T_xx)/2, e_y = (1 + T_yy)/2, e_z = (1 − T_zz)/2, with their counts. These are the fractions of witness pairs whose product disagrees with the ideal Φ⁺ correlation.

### 4.6 Pauli-frame de-twirling tomography (`tomography.py`)

**Why it is needed.** The verifier's corrected state for sent frame k is P_k 𝒩(P_k ρ) (conjugations), with P(k) = ¼. Averaging over k gives the *Pauli twirl* of 𝒩. The twirl erases the translation c (non-unital, for example amplitude damping) and the off-diagonal part of M (coherent rotations). A detector that looks only at averaged statistics is blind to both.

**De-twirling identity.** The Bell outcome k leaves the verifier's qubit, before correction, in 𝒩(σ_k ρ_ℓ σ_k): the noise acts on the verifier's half, and it commutes with the signer's measurement. After the correction C_c the Bloch vector is therefore

  r_fin = P_c 𝒩(P_k r_ℓ)   (for an untampered frame c = k; noiseless 𝒩 gives P_k P_k r_ℓ = r_ℓ).

Because P_c is its own inverse,

  𝒩(r_{π_k(ℓ)}) = P_c r_fin,  where π_k(ℓ) is the label whose Bloch vector is P_k r_ℓ.

Every PE observation is therefore an unbiased single-shot sample of 𝒩's output component β for the input π_k(ℓ), with sign s = (P_c)_{ββ} applied to the ±1 outcome. Using the *true* k for the input and the *received* c for the sign recovers the quantum channel 𝒩 even under classical frame tampering. The tampering then shows up separately in the frame matrix.

**Estimator.**

* Accumulate the counts `n[ℓ', β]` and signed sums `z[ℓ', β]` (ℓ' ∈ 6 inputs, β ∈ 3 bases): r̂_β(ℓ') = z/n.
* Invert linearly:
  * M̂[:, j] = (r̂(+j) − r̂(−j))/2
  * ĉ = ⅓ Σ_j (r̂(+j) + r̂(−j))/2
* The standard error of each component is √((1 − r̂²)/n).

Two further maps come from the same PE data:

* **Effective map** (what verification experiences): r̂^eff_β(ℓ) from raw outcomes, without sign correction, pooled over k and c. It includes the twirl and any frame tampering.
* **Frame matrix** F[k, c]: counts of sent vs received frames (4×4). It is diagonal when the channel is clean.

Output is a `ChannelEstimate` with fields `M, c, M_se, c_se, n_cells, effective_M, effective_c, frame_matrix, counts`.

### 4.7 Validation against Qiskit Aer (`analysis/validation.py`)

The build uses v1's circuit layout, with a `qiskit.quantum_info.Kraus` instruction appended on q₂ right after the Bell pair's CX. Then:

1. For the six eigenstates and the channels {identity, depolarizing 0.1, dephasing-z 0.2, amplitude_damping 0.3, rotation(ẑ, 0.4), measure_prepare-z}, run Aer `density_matrix` with `save_density_matrix([2], conditional=True)` after the corrections.
2. Compare per-outcome normalised ρ with the Sentinel `bloch[ℓ,k,k]`, and the averaged ρ with Σ_k p_k ρ_k.
3. Pass criterion: max |Δρ| < 1e-9.

This runs in selftest (§14.6) and in `tests/sentinel/test_aer_validation.py`. It is skipped with reason if qiskit is not importable.

---

## 5. Adversary models (17 variants)

### 5.1 Common structure

```python
@dataclass(frozen=True)
class AttackSpec:            # what the API receives
    attack_id: str           # e.g. "channel.dephase"
    intensity: float = 0.5   # ∈ [0,1], mapped per attack
    params: dict = {}        # attack-specific, validated against the catalog schema
    target: str = "first"    # "first" | "second" | "both" recipient link(s) (distribution attacks)
```

The **catalog** (`adversary/catalog.py`) is data: id, category, subtype, phase (`distribution` | `signing`), name, one-line summary, physics paragraph, adversary knowledge, parameter schema (name, type, min, max, step, default, options, unit, description), intensity mapping (a formula string plus a function), expected detection layer(s), counterfactual description, icon key. `GET /api/v1/attacks/catalog` serves it verbatim.

A distribution attack implements the hook
`DistributionAttack.plan(link_ctx) -> LinkPlan`. A `LinkPlan` contains:
* the extra channel 𝒜, if any;
* `substitute_fraction` f and Eve's handling of substituted pairs;
* frame-flip probabilities (q₀, q₁);
* source label perturbations: which positions of which copy get which alternative label (repudiation only; applied by the *signer's* code path, because the signer is the dishonest party).

A signing attack implements the hook
`SigningAttack.execute(ctx: SigningAttackContext) -> AttackOutcome`. It receives only an `AdversaryKnowledge` object (P4) and can call the public verification entry points as a network participant would.

### 5.2 Distribution-phase attacks

| id | Category / subtype | Intensity mapping | What physically happens | Primary detection |
|---|---|---|---|---|
| `channel.depolarize` | CHANNEL_MANIPULATION / depolarizing | p = 0.5·I | 𝒜 = depolarizing(p) on the verifier half | D2, D4, D5 (isotropic) |
| `channel.dephase` | CHANNEL_MANIPULATION / dephasing | p = 0.5·I; param `axis` ∈ {x,y,z} (default z) | 𝒜 = dephasing(p, axis) | D4 (two bases), D5 (dephasing, axis) |
| `channel.amplitude_damp` | CHANNEL_MANIPULATION / amplitude_damping | γ = 0.6·I | 𝒜 = amplitude_damping(γ) | D5 **de-twirled** translation. Averaged statistics hide c; this attack showcases §4.6 |
| `channel.coherent_rotation` | CHANNEL_MANIPULATION / coherent_rotation | θ = (π/2)·I; param `axis` (default ẑ) | 𝒜 = rotation(axis, θ) | D5 de-twirled rotation (a twirled view looks like dephasing) |
| `channel.intercept_resend` | CHANNEL_MANIPULATION / intercept_resend | f = I; param `basis` ∈ {random,x,y,z} | On a fraction f of pairs Eve measures the verifier half in a basis and resends the eigenstate. Per pair: 𝒜 = measure_prepare(basis) for fixed basis; for `random` the basis is drawn per pair (mixture of the 3) | D1 (S → 2√2(1−f) + f·S_mp), D3, D4, D5 (dephasing or isotropic) |
| `channel.pauli_frame` | CHANNEL_MANIPULATION / classical_frame | q = 0.5·I; param `bits` ∈ {m0, m1, both} | Flip correction bits in transit | **D6 conclusive**; D4/D5 show a Pauli-X or Z channel on the effective map, **not** on the de-twirled one |
| `unauthorized.key_harvest_mitm` | UNAUTHORIZED_VERIFICATION / key_harvest | f = I | Eve substitutes a fraction f of the verifier's halves with halves of her own pairs. She receives the teleported key state in her lab (she reads k on the classical channel and corrects), measures it in a random basis (recording (β_E, o_E) = harvested knowledge), then re-teleports the eigenstate (β_E, o_E) to the verifier through her own pair over the same fibre (baseline channel). She sends the verifier her **own** Bell outcome k_E as the correction bits | D1/D3 (substituted pairs uncorrelated with the signer → S, F drop), **D6** (≈¾ of substituted positions show k ≠ c), **D7 deficit** (key QBER ≈ f/3 below the Bell-predicted f/2) |
| `repudiation.inconsistent_keys` | REPUDIATION / inconsistent_keys | r = 0.5·I; param `victim` ∈ {first, second} (default second) | The dishonest signer teleports, to the victim recipient, the **orthogonal** eigenstate (same basis, flipped bit) on a fraction r of positions, while claiming the original labels | **D7 excess** on the victim link while D1–D3 are clean; **D8** copy inconsistency; symmetrization defeats the goal (§7.3) |

Heterogeneous-position handling in `distribution.py`:

* **intercept_resend** and **key_harvest_mitm** draw a per-pair Bernoulli(f) mask with CSPRNG → `sub`.
  * Test pairs: ρ_eff mixture as in §4.5. For intercept-resend this uses the measure-prepare state; for MITM, I/4.
  * Key positions in `sub`, **key_harvest_mitm**:
    1. Eve's received state is (baseline Alice–Eve) ℓ.
    2. She measures in a random basis, using the sampler with an identity-channel model and her basis.
    3. She re-prepares label ℓ_E = 2·β_E + o_E.
    4. She teleports it to the verifier through the baseline model; k_E comes from that sampler.
    5. The verifier records c = k_E, while the signer's PE records k. Harvested knowledge `(positions, β_E, o_E)` is stored in the `AttackOutcome` for the counterfactual.
  * Key positions in `sub`, **intercept_resend**: use the model with 𝒜 = measure_prepare, the correct k, and no frame change.

### 5.3 Signing-phase attacks

| id | Category / subtype | Knowledge (P4) | Action | Detection |
|---|---|---|---|---|
| `forgery.blind` | FORGERY / external_blind | A captured genuine signature (envelope + revealed labels) for message m | Builds an envelope for m' (param `mode`: `modified_message` alters the text → ~half the digest bits differ; `oracle_k_bits` assumes a hash near-collision oracle and differs in exactly k = max(1, round(256·I)) bits). Reuses revealed labels for equal bits; draws **uniform** labels for differing bits | S7 fails on the differing keys (mismatch ≈ ½); S9 → partial failure + rate ½ → `external_blind` |
| `forgery.insider` | FORGERY / insider | V₁'s own records (all positions) + V₂'s symmetrization records S₂ + the captured genuine signature | V₁ forges to V₂. For each differing key and position j: declare V₂'s record where V₁ knows it (j ∈ S₂), otherwise V₁'s own record (β, o) as the label 2β + o | V₂: the own-set fails (≈ ⅓); **the recv-set passes perfectly** → S9 **set-asymmetry** → attribution to V₁ |
| `forgery.bit_flip_oracle` | FORGERY / oracle_k_bits | As `forgery.blind` + oracle | Forges exactly k bits (param `k`, default 1) with uniform guesses | S7 on those k keys; per-key forgery probability measured vs §7 |
| `impersonation.identity_swap` | IMPERSONATION / identity_swap | Mallory's own ACTIVE bundle for group `g-mallory` (same recipients), distributed on demand | Signs a message with **her** bundle and **her** labels but sets `signer_id="alice"`, `group_id="g-alice"` | S2 conclusive (the bundle belongs to Mallory). Quantum statistics pass, the honest evidence that a valid key ≠ the right key |
| `impersonation.keyless` | IMPERSONATION / keyless | Alice's public bundle id only | Claims Alice's bundle and emits uniform labels for **all** keys | S7: ~all keys fail at ≈ ½ → S9 `keyless` → IMPERSONATION |
| `replay.resubmit` | REPLAY / resubmission | A captured accepted signature | Resends it unchanged to V₁ | S3 consumed, S4 nonce, S5 seq; quantum clean |
| `replay.forward_replay` | REPLAY / forward_replay | A captured forwarded signature | Presents it to V₂ as a fresh first delivery | S3 (consumed by V₂ at forwarding), S4 |
| `replay.delayed` | REPLAY / delay | A signature intercepted **before** delivery | Holds it for `delay_s` (param, default 300; the API simulates the delay by back-dating the check time, `now = ts + delay_s`, with no sleeping) then delivers | S6 stale; the bundle is otherwise fresh |
| `unauthorized.non_recipient` | UNAUTHORIZED_VERIFICATION / non_recipient | A captured signature | Party `verifier` (param: `erin` default, or `eve`) requests verification | S1 conclusive; `eve` also fails authentication (unknown principal) |

`signing` attacks that need a captured signature take one from the **CaptureBuffer**: the last 16 accepted signatures seen on public classical channels, held in memory. If it is empty, the runner first performs a legitimate session (origin `LAB`) to capture one. The report states this.

### 5.4 Counterfactuals (Sentinel OFF)

`AttackRunRequest.counterfactual = true` (default in the Lab) asks the runner to *also* compute what would have happened without the defence. This is computed by running the real code paths with the specific defence disabled:

| Attack family | Counterfactual computed |
|---|---|
| Distribution attacks (except MITM, repudiation) | Use the COMPROMISED bundle anyway: honest signing + both verifications → shows **denial of service** (honest signature rejected) or a silent acceptance at reduced margin |
| `unauthorized.key_harvest_mitm` | Use the bundle anyway. Eve forges a message to V₁ using harvested labels (declare (β_E, o_E) on harvested positions, uniform elsewhere) → shows V₁ **accepting a forgery** when f is high enough |
| `repudiation.inconsistent_keys` | Re-run verification with **symmetrization disabled** (each verifier tests its own copy only) → shows V₁ accept ∧ V₂ reject (the dispute Alice wanted) vs. with symmetrization (decisions agree) |
| `replay.*` | Re-run verification with the **protocol guard disabled** → quantum tests alone ACCEPT the replay |
| `forgery.insider` | Re-run V₂'s verification with a **single pooled set** (no own/recv split) → the insider's pooled mismatch drops below s_v at high recv share, showing why sets are tested separately |
| `impersonation.identity_swap` | Guard disabled → quantum tests ACCEPT (Mallory's keys are valid for her bundle) |
| others | none (the report says "no weaker configuration is meaningful") |

Counterfactual results are clearly marked `counterfactual: true`. They never change stored bundle state (they run on copies) and are excluded from live KPIs.

---

## 6. QSentinel detection framework

### 6.1 Architecture

```
distribution run ─▶ per-link evidence (Bell counts, PE aggregates, frame matrix, MAC)
                    ├─ D1 CHSH certificate        ├─ D5 tomography deviation → fingerprint
                    ├─ D2 CHSH drift              ├─ D6 frame integrity (+MAC)
                    ├─ D3 witness cert. + drift   ├─ D7 Bell-vs-key consistency
                    ├─ D4 QBER excess (per basis) └─ D9 security margin
                  group-level: D8 copy consistency · temporal: D10 CUSUM/EWMA (per link)
                  ─▶ Holm correction over the statistical family ─▶ fusion (decision list §6.5)
                  ─▶ Assessment(verdict, threat level, classification, explanation, alternatives)

signature run ─▶ S1..S6 protocol guard · S7 key tests · S8 SPRT · S9 forensics · S10 dispute
                  ─▶ fusion (§6.5) ─▶ Assessment
```

### 6.2 Statistical toolkit (`stats.py`)

All functions are vectorised where it matters, with scipy as the numeric backend:

| Function | Definition |
|---|---|
| `binom_sf(m, n, p)` | P(Bin(n,p) ≥ m) = `scipy.stats.binom.sf(m−1, n, p)` |
| `binom_cdf(m, n, p)` | P(Bin(n,p) ≤ m) |
| `clopper_pearson(x, n, delta)` | Two-sided exact interval via the beta quantiles `beta.ppf(δ/2, x, n−x+1)`, `beta.ppf(1−δ/2, x+1, n−x)`. Reuses v1 `evaluation.far_frr.clopper_pearson_interval` where the signature matches |
| `cp_upper(x, n, delta)`, `cp_lower` | One-sided bounds |
| `hoeffding_halfwidth(n, delta, range=1)` | √(range²·ln(2/δ)/(2n)) |
| `kl_bernoulli(q, p)` | q ln(q/p) + (1−q) ln((1−q)/(1−p)) |
| `chernoff_upper_tail(n, p, q)` | exp(−n·KL(q‖p)) for q > p (and the lower tail for q < p) |
| `two_proportion_z(x1, n1, x2, n2, alternative)` | Pooled z; exact **Fisher** fallback when any expected count < 10 |
| `chi2_homogeneity(counts_a, counts_b)` | Σ over cells of the 2×2 Pearson statistic, df = #cells with both n > 0. Returns (X², df, p) |
| `holm(pvalues, alpha)` | Step-down: sort ascending, reject p₍ᵢ₎ ≤ α/(m−i+1) until the first failure |
| `hypergeom_split_tail(N, K, n1, a, b)` | P(X ≤ a ∧ K − X > b), X ~ Hypergeom(N, K, n1) |

Numerical guards: p-values are clipped to [1e-300, 1]; `log10p` is reported for the UI.

### 6.3 Detectors (definitions)

Every detector returns:

`Finding(id, name, layer, fired, conclusive, severity, statistic{name,value}, p_value|None, alpha|None, effect{name,value,floor}|None, evidence: str, data: dict)`

Configured defaults are in `config/sentinel.yaml → detection`.

**D1 `entanglement.chsh_certificate`** (layer `entanglement`)
- Input: the link's CHSH counts.
- Statistic: S_lcb at δ_bell.
- Fires iff S_lcb ≤ 2: no certified Bell violation, so the pairs are consistent with a local-realistic (classical) source.
- Severity CRITICAL. Not p-value based. Conclusive at confidence 1 − δ_bell.
- Evidence: "CHSH S = 2.12 (LCB 1.87 at δ=1e-5) does not exceed the local bound 2 — entanglement not certified."

**D2 `entanglement.chsh_drift`**
- Statistic: z = (S₀ − Ŝ)/√(se₀² + ŝe²), one-sided.
- Fires iff p = Φ(−z) < α (after Holm) **and** S₀ − Ŝ ≥ 0.10.
- Severity HIGH if ΔS ≥ 0.25, else MEDIUM.

**D3 `entanglement.witness`**
- Certificate part: F_lcb ≤ ½ → fires CRITICAL (not entangled).
- Drift part: two-proportion tests of the per-setting disagreement fractions vs baseline, combined by Holm. Fires if significant **and** F₀ − F̂ ≥ 0.02.
- Severity HIGH / MEDIUM.

**D4 `channel.qber_excess`**
- Per basis β and overall: two-proportion one-sided test of the current PE mismatch fraction (basis-matched PE positions) vs the baseline calibration counts.
- Effect: Δe ≥ 0.01 absolute.
- `data.per_basis` holds (e, CI, e₀, p).
- Severity: HIGH if Δe ≥ 0.05, MEDIUM if ≥ 0.02, else LOW.

**D5 `channel.tomography_deviation`**
- χ² homogeneity between current and baseline **de-twirled** cells (6 inputs × 3 bases, each a 2-outcome cell).
- Effect: max |r̂ − r̂₀| over cells ≥ 0.04.
- On firing, runs the **fingerprint classifier** (§6.5.1) and attaches `data.fingerprint`.
- Severity HIGH if effect ≥ 0.1 else MEDIUM.
- Also reports the *effective* (twirled) χ² for comparison, which lets the UI show "hidden by the twirl".

**D6 `classical.frame_integrity`**
- With MAC: fires if the tag fails (conclusive, all positions).
- Without MAC: fires iff Σ_{k≠c} F[k,c] > 0 on the PE sample (conclusive by A4).
- Statistic: tamper rate with a Clopper–Pearson CI; `data.flip_pattern` gives flip rates of m₀ and m₁.
- Severity CRITICAL.

**D7 `source.bell_consistency`** (two-sided)
- Per basis β: compare the key-state PE mismatch fraction e_key,β with the Bell-predicted e_bell,β (witness disagreements for setting ββ).
- Test: two-proportion two-sided test, pooled over β with Holm.
- Effect: |Δ| ≥ 0.01.
- Direction: Δ > 0 is **excess**: the key states are worse than the channel explains, so the source is inconsistent. Δ < 0 is **deficit**: the key states did not travel the path the test pairs did, a relay/MITM signature.
- Only meaningful when the frame is clean; if D6 fired, D7's excess direction is annotated "frame-induced".
- Severity HIGH.

**D8 `source.copy_consistency`** (group-level)
- Two-proportion two-sided test between the V₁-copy and V₂-copy PE mismatch rates.
- Effect ≥ 0.01.
- Interpreted as signer inconsistency only if both links' D1–D3 are clean; otherwise annotated "explained by channel findings".
- Severity HIGH.

**D9 `security.margin`**
- The designer cannot find s_a < s_v at the measured e_ucb.
- Severity MEDIUM (degradation, not necessarily an attack). Causes abort.
- Evidence includes the minimum L that would restore feasibility.

**D10 `temporal.cusum`** (per link, updated after each certified or compromised bundle)
- QBER CUSUM: C_t = max(0, C_{t−1} + (ê_t − e₀) − k), k = 0.0025; alarm when C_t > h = 0.015.
- CHSH CUSUM (downward): C_t = max(0, C_{t−1} + (S₀ − Ŝ_t) − k_S), k_S = 0.02; alarm when C_t > h_S = 0.12.
- EWMA (λ = 0.2) of QBER, for display.
- An alarm fires MEDIUM "persistent low-level drift". The monitor resets after an operator re-certification.
- Rationale: a single bundle's effect floor (0.01) deliberately ignores small shifts; CUSUM accumulates them. An attack adding Δe = 0.005 alarms after ≈ 6 bundles; the honest ARL₀ is measured by the `cusum_arl` job.

**S1–S6** (protocol guard, §3.9): conclusive; each yields a Finding with `layer="protocol"`.

**S7 `signature.key_tests`**
- Fires iff any set FAILs or is INCONCLUSIVE.
- `data`:
  * `per_key` arrays (for the UI 16×16 strips): `n_own, m_own, n_recv, m_recv, pass`;
  * `failed_keys`;
  * `worst_p`: min over failed sets of P(Bin(n, e_ucb) ≥ m).
- Severity CRITICAL.

**S8 `signature.sprt`**
- Reports `observations_used`, `observations_available`, `early_reject: bool` and a per-key LLR trace (first 8 keys, for the UI chart).
- Fires iff early reject. Severity follows S7.

**S9 `signature.forensics`** (runs when S7 fired). Features:
- ρ_fail = failed keys / K.
- Pooled mismatch rate over failed sets, with a Clopper–Pearson CI.
- Set asymmetry at the transferee: two-proportion test of own vs recv mismatch on failed keys.

Rules, first match wins:
1. Set asymmetry significant with recv ≈ 0 (recv CI upper < e_ucb + 0.02) and own ≈ ⅓ → **INSIDER** (attribution: the peer recipient whose forwarded records match).
2. ρ_fail ≥ 0.9 → **KEYLESS** (no genuine key material) → category IMPERSONATION.
3. The pooled rate CI contains ½ and excludes ⅓ → **EXTERNAL_BLIND**.
4. The CI contains ⅓ → **INFORMED** (a holder of a measurement record).
5. Otherwise **UNATTRIBUTED**.

**S10 `signature.transfer_consistency`**
- V₁ accept ∧ V₂ reject → fires HIGH "dispute".
- Carries both sets' statistics.

### 6.4 Multiple testing and severity

* **Family**: all p-value findings of one distribution (D2, D3-drift, D4 per basis, D5, D7 per basis, D8) share one Holm correction at `alpha_family` (default **1e-6**). Conclusive findings (D1, D3-cert, D6, S1–S6) sit outside the family.
* A finding **fires** only if it is significant **and** its effect clears its floor. The floor keeps huge samples from flagging trivial drifts.
* **Threat score** (UI only; decisions never use it):
  * E_d = min(1, log₁₀(1/p_d) / log₁₀(1/α_d)) for statistical findings, 1 for fired conclusive findings;
  * `threat_score` = 1 − Π_d (1 − w_sev(d)·E_d), with w = {LOW 0.15, MEDIUM 0.35, HIGH 0.7, CRITICAL 1.0}.
  It is deterministic and documented.
* **Threat level** of an assessment is the max severity among fired findings (NONE if none).

### 6.5 Fusion

#### 6.5.1 Fingerprint classifier (on the de-twirled physical channel)

Inputs: baseline (M₀, c₀) and current (M, c), both de-twirled, with standard errors.
Attack map: M_A = M M₀⁻¹, c_A = c − M_A c₀.
Noise scale: σ = median(M_se) ⊕ median(M₀_se) (root-sum-square).

1. **Non-unital:** if ‖c_A‖ > max(0.03, 4σ) → `amplitude_damping` when c_A points within 25° of ±ẑ and the λ-pattern matches (λ_z ≈ 1−γ̂, λ_{x,y} ≈ √(1−γ̂) within 3σ, with γ̂ = |c_A,z|); otherwise `non_unital`. Report γ̂ and direction.
2. **Polar decomposition** M_A = U P, with θ = arccos((tr U − 1)/2). If θ > max(4°, 4σ rad) → `coherent_rotation`. Report the axis (eigenvector of U for eigenvalue 1) and θ̂.
3. Singular values λ₁ ≥ λ₂ ≥ λ₃ of P.
4. If λ₃ ≥ 1 − max(0.03, 4σ) → `none` (no channel-level anomaly; other findings may still fire).
5. If λ₁ − λ₃ < max(0.05, 6σ) → `isotropic` with p̂ = 1 − mean(λ).
   *Equivalence class*: depolarizing(p̂) ≡ random-basis intercept–resend on f̂ = 3p̂/2 of pairs.
6. If λ₁ − λ₂ > max(0.05, 6σ) and λ₂ − λ₃ < max(0.05, 6σ) → `dephasing` along the P-eigenvector a of λ₁, with p̂ = (1 − (λ₂+λ₃)/2)/2.
   *Equivalence class*: dephasing(a, p̂) ≡ Pauli-σ_a errors with prob p̂ ≡ intercept–resend in basis a on f̂ = 2p̂ of pairs.
7. Otherwise `general_pauli` with (p_I, pₓ, p_y, p_z) from λ in the principal frame:
   * p_I = (1+λ₁+λ₂+λ₃)/4
   * pₓ = (1+λ₁−λ₂−λ₃)/4
   * p_y = (1−λ₁+λ₂−λ₃)/4
   * p_z = (1−λ₁−λ₂+λ₃)/4

The output `Fingerprint(shape, params, axis, confidence_note, alternatives: [str])` states the physics honestly. For example: "Isotropic contraction λ ≈ 0.62: consistent with depolarizing noise p ≈ 0.38 **or** random-basis intercept–resend on ≈ 57% of pairs; these are the same channel and no measurement can separate them."

#### 6.5.2 Distribution decision list (first match wins)

| # | Condition | Category / subtype | Confidence |
|---|---|---|---|
| 1 | D6 fired **and** (D1 or D3-cert or D2 fired or D7 deficit) | UNAUTHORIZED_VERIFICATION / key_harvest (MITM) | conclusive (frame) + statistical (entanglement) |
| 2 | D6 fired | CHANNEL_MANIPULATION / classical_frame | conclusive |
| 3 | D1 or D3-cert fired | CHANNEL_MANIPULATION / fingerprint.shape (typically intercept_resend / entanglement_break) | certification failure |
| 4 | D7 excess fired **and** D1, D2, D3 clean on that link | if D8 fired → REPUDIATION / inconsistent_keys; else REPUDIATION / source_fault | statistical |
| 5 | Any of D2, D3-drift, D4, D5 fired | CHANNEL_MANIPULATION / fingerprint.shape (`none` → `unclassified_disturbance`) | statistical |
| 6 | D9 fired | DEGRADED / insufficient_margin | design |
| 7 | D10 alarm | CHANNEL_MANIPULATION / low_intensity_persistent | temporal |
| 8 | — | NONE | — |

Verdict: **COMPROMISED** if any HIGH/CRITICAL finding fired or D9 fired. Otherwise **CERTIFIED**, with warnings for LOW/MEDIUM.

#### 6.5.3 Signature decision list

| # | Condition | Category / subtype |
|---|---|---|
| 1 | S1 | UNAUTHORIZED_VERIFICATION / non_recipient |
| 2 | S2 | IMPERSONATION / identity_swap |
| 3 | S3-consumed, S4, S5 or S6 | REPLAY / (resubmission \| forward_replay \| delay), chosen by which checks fired (S6 alone → delay; at V₂ as first delivery → forward_replay) |
| 4 | S3-policy (compromised / revoked / expired) | POLICY / blocked_bundle (not an attack classification) |
| 5 | S7 with S9 = KEYLESS | IMPERSONATION / keyless |
| 6 | S7 with S9 = INSIDER | FORGERY / insider (attributed_to = peer) |
| 7 | S7 (other S9) | FORGERY / (external_blind \| informed \| oracle_k_bits when failures ≤ 8 keys \| unattributed) |
| 8 | S10 | REPUDIATION / dispute |
| 9 | — | NONE → ACCEPTED |

Verdict: **ACCEPTED** iff V₁ accepted and no protocol check failed. The V₂ transfer result is reported, and disputes raise S10. **REJECTED** otherwise.

#### 6.5.4 Recommended actions (deterministic mapping)

| Category | Actions offered |
|---|---|
| CHANNEL_MANIPULATION (quantum) | `quarantine_link`, `recertify_link`, `revoke_link_bundles` |
| classical_frame | `enable_mac`, `quarantine_link` |
| key_harvest | `quarantine_link`, `revoke_link_bundles`, `recertify_link` |
| REPUDIATION | `suspend_signer`, `escalate_dispute` |
| FORGERY / IMPERSONATION | `flag_principal` (attribution if any), `notify_recipients` |
| REPLAY | `none_required` (blocked by protocol), `review_capture_source` |
| UNAUTHORIZED | `deny_principal` |
| DEGRADED | `recertify_link`, `use_larger_L` |

Actions that change state (`quarantine_link`, `recertify_link`, `revoke_link_bundles`, `enable_mac`, `suspend_signer`) are implemented. Informational ones (`flag_principal`, `notify_recipients`, `escalate_dispute`, `review_capture_source`, `deny_principal`, `use_larger_L`) are recorded on the incident as audit entries and as ledger transactions.

### 6.6 Temporal monitoring (`sequential.py`)

* `Cusum(k, h, direction)` with `update(x) -> (C, alarm)` and serialisable state.
* `Ewma(lam)`.
* `Sprt(p0, p1, alpha, beta)` with `run(stream) -> (decision, n_used, trace)` and `asn(p)` (Wald approximation).
* Link monitors persist their state in `link_monitor_state` so it survives restarts, and append each update to `link_monitor` (time series for the UI).

### 6.7 Assessment object

```jsonc
{
  "verdict": "COMPROMISED",               // or CERTIFIED | ACCEPTED | REJECTED
  "threat_level": "CRITICAL",             // NONE|LOW|MEDIUM|HIGH|CRITICAL
  "threat_score": 0.97,
  "classification": {
    "category": "UNAUTHORIZED_VERIFICATION",
    "subtype": "key_harvest",
    "confidence": "conclusive",            // conclusive | statistical | temporal | indicative
    "rule": "D6 ∧ (D1 ∨ D3 ∨ D2 ∨ D7↓)",
    "explanation": "Correction bits were altered on 24.8% of sampled positions …",
    "alternatives": [],
    "attributed_to": null                  // e.g. "bob" for insider forgery
  },
  "findings": [ /* Finding… */ ],
  "recommended_actions": ["quarantine_link", "revoke_link_bundles", "recertify_link"]
}
```

### 6.8 Baseline calibration (`detection/baseline.py`)

* **When:** at first start for every link without a baseline; after a link's baseline channel changes (PATCH); on operator request (`/detection/baselines/calibrate`); after re-certification.
* **How:** model-level sampling with no attack. No bundle is created: this is a trusted maintenance window.
  * N_pe_cal = 400 000 positions through the full per-qubit pipeline, drawing labels, frames, bases and outcomes exactly like PE.
  * 20 000 pairs per Bell setting.
* **Stored:**
  * PE counts per basis (mismatch, total);
  * de-twirled cell counts (6×3×(n, plus)) and effective counts;
  * Bell counts (7×4);
  * derived (S₀, se₀, F₀, M₀, c₀, e₀ per basis);
  * `calibrated_at`, `samples`, and the channel spec hash. The hash is used only to detect config changes; the **detector never reads the spec**.
* Cost ≈ 0.2 s per link.

---

## 7. Security analysis and forgery probability

### 7.1 Robustness (honest acceptance)

Honest mismatches on a set are Bin(n, e). With the design using n_min and e_ucb:

  ε_rob(message) ≤ 2·digest_bits·P(Bin(n_min, e_ucb) > ⌊s_a·n_min⌋) + 2·digest_bits·α_s + δ_pe.

(The terms are: sets, SPRT early rejects, and PE bound failure.) On an ideal channel e = 0: every honest set has m = 0 ≤ ⌊s_a n⌋, so **acceptance is deterministic**. The `ideal` link preset demonstrates this.

### 7.2 Forgery

*External blind forger* (uniform label for an unseen key): a position is tested w.p. ⅓ (verifier basis = declared basis). Given tested, the true basis equals the declared basis w.p. ⅓ (then mismatch iff the bit is wrong, w.p. ½); otherwise the verifier's outcome is uniform (mismatch ½). So p_f = ⅓·½ + ⅔·½ = **½**.

*Insider forger* (V₁ forging to V₂, single copy, no memory, optimal): V₁ declares its own measured (β₁, o₁). A position is tested iff β₂ = β₁. Then:
* if the true basis = β₁ (prob ⅓), both outcomes are exact → match;
* otherwise V₂'s outcome is uniform → mismatch ½.
So p_f = ⅔·½ = **⅓**.

`analysis/forgery.py → insider_optimum()` verifies numerically that no projective strategy does better. It searches measurement directions n on a 4 000-point Fibonacci sphere × all 36 outcome→label maps, computes the exact expected tested-mismatch averaged over the 6 true labels (with a copy of the same state at V₂), and returns min = ⅓ at n ∈ {±x̂, ±ŷ, ±ẑ}.

Per-key forgery probability (the forger must pass V₂'s own set, the set it lacks knowledge of):

  ε_forge(key) = P(Bin(n_min, p_f) ≤ ⌊s_v·n_min⌋).

The Chernoff form exp(−n·KL(s_v‖p_f)) is reported alongside.

*Message level.* In `sha256` mode, forging m' requires forging every key where the digests differ. With k differing bits, ε = ε_forge(key)^k (independent keys). A random m' has k ~ Bin(256, ½). The oracle model reports ε_forge(key)^k for k = 1..8.

### 7.3 Repudiation

Alice's goal: V₁ accepts and V₂ rejects. After symmetrization, V₂'s sets are the *complementary halves* of the two copies whose other halves V₁ tested. Take one copy with N tested positions containing K errors, split into halves of n₁ = N/2. Then

  P_rep(copy) = max_K P(X ≤ ⌊s_a n₁⌋ ∧ K − X > ⌊s_v n₁⌋),  X ~ Hypergeom(N, K, n₁),

and ε_rep(key) ≤ 2·P_rep, message level ≤ digest_bits·ε_rep(key). `analysis/forgery.py → repudiation_bound()` computes this exactly with scipy's hypergeometric distribution. Without symmetrization, Alice succeeds with probability ≈ 1 by corrupting only V₂'s copy; the `repudiation_analysis` job shows both.

### 7.4 Threshold designer (`protocol/thresholds.py`)

`design(L, e_ucb, digest_bits, targets) -> ThresholdDesign`:

1. n_nom = ⌊L/6⌋. n_min = the largest n with 4·digest_bits·P(Bin(⌊L/2⌋, ⅓) < n) ≤ 0.1·eps_rob_target (sets that fall short are INCONCLUSIVE, and this probability is charged to ε_rob).
2. c_a = min c such that 2·digest_bits·binom_sf(c+1, n_min, e_ucb) ≤ eps_rob_target − 2·digest_bits·α_s − δ_pe; s_a = c_a / n_min.
3. c_v = max c such that binom_cdf(c, n_min, p_f,insider) ≤ eps_forge_target; s_v = c_v / n_min.
4. Feasible iff c_a < c_v. Compute ε_rep by §7.3 at (s_a, s_v).
5. If infeasible, bisect L upward to the minimum feasible L_min (≤ 65 536) and report it.
6. Return `{s_a, s_v, c_a, c_v, n_nom, n_min, eps_rob, eps_forge_key, eps_forge_chernoff, eps_rep_key, eps_rep_msg, feasible, L_min, e_ucb, sprt:{alpha, beta, A}}`.

Thresholds are **rates** applied to each set's actual n (m ≤ ⌊s·n⌋). The reported ε's are the **maximum over every n from n_min to ⌊L/2⌋** of the exact tail, so the floor on the rounding cannot hide a bad n.

Measured designs (e_ucb ≈ 0.013): L = 2048 gives s_a = 0.094, s_v = 0.188, ε_rob = 4e-10, ε_forge = 6e-7 but ε_rep(msg) ≈ 0.9, so it is **not** used as the default. L = 4096 (`standard`) gives n_min = 529, s_a ≈ 0.06, s_v ≈ 0.236, ε_rob ≈ 8e-10, ε_forge ≈ 7e-7, ε_rep(msg) ≈ 1.5e-14. L = 8192 (`high`) gives ε_rob ≈ 5e-13, ε_forge ≈ 9e-13, ε_rep ≈ 1e-37. `demo` and `analysis` (L = 1024) meet their relaxed robustness and forgery targets but **not** repudiation; the UI says so.

---

## 8. Performance model and complexity

| Operation | Complexity | Notes |
|---|---|---|
| Model build (superoperators) | O(1): 16 × (8×8) products | Cached per channel spec |
| Distribution sampling | O(K·L_dist) per recipient | ~6 vector ops of length N; chunked at 2²⁰ |
| PE aggregation | O(n_pe_total) with `np.bincount` on packed cell indices | 288 cells |
| Symmetrization | O(K·L) | CSPRNG permutations per key via argsort of random keys |
| Signing | O(digest_bits·L) | Gather from label array |
| Verification | O(digest_bits·L) per verifier | Boolean masks + `sum(axis=1)` |
| Fusion | O(#findings) | |
| Tomography inversion, fingerprint | O(1) | 3×3 algebra |

Targets on a 4-vCPU container: `standard` distribution ≤ 400 ms, sign + two verifications ≤ 150 ms, `analysis` distribution ≤ 40 ms.

**Modelled hardware time.** This is labelled as modelled, never as measured. t_hw = N_pairs / (R_src·η·η_det), with R_src = 10 MHz, η = 10^(−0.02·length_km) (0.2 dB/km), and η_det = 0.9. It is reported in the distribution report.

---

## 9. Security ledger

* **Transactions** (`ledger_txs`), each with `kind`, `payload` (canonical JSON: sorted keys, `separators=(',',':')`, UTF-8) and `payload_hash` = SHA-256(payload). Kinds:
  * `SIGNATURE_ACCEPTED`: session id, group, signer, message SHA-256, bundle id, both verifier decisions + mismatch summary.
  * `SIGNATURE_REJECTED`: the same + classification.
  * `BUNDLE_CERTIFIED` / `BUNDLE_COMPROMISED`: bundle id, links, S, QBER, classification.
  * `INCIDENT`: incident id, severity, category, evidence digest.
  * `RESPONSE_ACTION`: action, target, incident id.
  * `LINK_STATE`: quarantine / release / recertify.
* **Blocks** (`ledger_blocks`):
  * `height`, `prev_hash`, `merkle_root`, `timestamp`, `tx_count`;
  * `hash` = SHA-256(canonical JSON of `{height, prev_hash, merkle_root, timestamp, tx_count}`).
* **Merkle tree:** leaves are the tx hashes (bytes); each parent = SHA-256(left ‖ right); an odd level duplicates its last node; the empty tree root is SHA-256(b"").
* **Genesis:** height 0, prev = "0"×64, no txs. Created by the DB migration.
* **Block producer** (worker, §14.4): seals pending txs when ≥ 16 are pending or the oldest is ≥ 8 s old.
* **Verification** (`POST /ledger/verify`) recomputes every payload hash, Merkle root, header hash and prev link. It returns the first invalid height, the issues found (`payload_hash_mismatch`, `merkle_mismatch`, `header_mismatch`, `broken_link`) and the count of blocks downstream of the break.
* **Tamper demo** (enabled by `QVERIS_ALLOW_TAMPER_DEMO`, default `true` in dev, `false` in production):
  * `POST /ledger/tamper {height?}` rewrites one stored tx payload field (e.g. `message_sha256` → a different hash) **directly in SQLite**, without touching hashes. The original is saved in `ledger_tamper_log`.
  * `POST /ledger/tamper/revert` restores it.
  * Both actions are logged.

---

## 10. Server architecture

### 10.1 Package layout (`src/server`)

```
server/
  __init__.py            version
  __main__.py            `python -m server` → uvicorn with settings
  app.py                 create_app(settings) → FastAPI; lifespan; routers; static SPA
  settings.py            Settings dataclass from env + config/sentinel.yaml
  context.py             AppContext (db, repos, services, hub, executors, stop events)
  db/
    database.py          Database: sqlite3 conn, RLock, WAL, migrations, helpers
    migrations/001_init.sql
    repos.py             NodeRepo, LinkRepo, GroupRepo, BundleRepo, SessionRepo, IncidentRepo,
                         LedgerRepo, JobRepo, MonitorRepo, GuardRepo, SettingsRepo, BaselineRepo
  services/
    network.py           topology seeding, link status, quarantine/release, secrets (MAC keys)
    keystore.py          bundle material files (npz) save/load/shred
    protocol.py          distribute(), sign_and_verify(), reverify() (orchestrates sentinel)
    attacks.py           catalog, run_attack(), campaigns
    detection.py         baselines, calibrate, monitors, detection config
    incidents.py         open/aggregate/ack/resolve/respond
    ledger.py            append tx, produce blocks, verify, tamper demo
    metrics.py           summary + time series queries
    traffic.py           TrafficGenerator, ReservoirMaintainer, CampaignRunner
    jobs.py              JobManager + registry of analytics jobs
    hub.py               EventHub (thread-safe publish → asyncio queues)
    selftest.py          startup/self checks
    capture.py           CaptureBuffer (last 16 accepted signatures)
  api/
    errors.py            ApiError + handlers (problem JSON)
    schemas.py           Pydantic v2 models (requests/responses)
    ratelimit.py         token buckets
    routes/{system,network,keys,signatures,sessions,attacks,traffic,detection,
            incidents,analytics,theory,playground,ledger,metrics}.py
    ws.py                /ws endpoint
```

### 10.2 Concurrency model

* The ASGI event loop serves requests and WebSockets.
* **Compute executor:** `ThreadPoolExecutor(max_workers=settings.compute_workers)` (default 2) for distributions and sessions. NumPy releases the GIL in its heavy kernels.
* **Job executor:** `ThreadPoolExecutor(max_workers=1)` for analytics jobs, with cooperative cancellation (`threading.Event`, checked between trials).
* An `asyncio.Semaphore(compute_workers)` guards compute submissions from background loops. User requests take priority: background loops `acquire` with `wait_for(timeout=0)` semantics and skip a tick when busy.
* **DB:** one `sqlite3.Connection(check_same_thread=False)` behind an `RLock`; WAL; `synchronous=NORMAL`; `foreign_keys=ON`. All repos take the lock. Transactions go through `with db.tx():`.
* **EventHub:** `publish(topic, type, data)` is callable from any thread (`loop.call_soon_threadsafe`). Each WS client has a bounded `asyncio.Queue(maxsize=512)`. On overflow the oldest event is dropped and a `lag` counter is sent.

### 10.3 Lifespan

1. Load `Settings`; create the data dir (`QVERIS_DATA_DIR`, default `./data`).
2. Open the DB and run migrations. If `nodes` is empty, **seed the topology** from `config/network.yaml`. Create the ledger genesis.
3. Build services and the `AppContext`; attach it to `app.state.ctx`.
4. Start background tasks:
   * selftest (thread);
   * baseline calibration for uncalibrated links;
   * reservoir maintainer;
   * block producer;
   * metrics ticker;
   * idle guard for traffic;
   * campaign runner.
5. Serve.
6. Shutdown: set stop events, cancel tasks, wait for executors (timeout 10 s), close the DB.

### 10.4 Static frontend

If `web/dist/index.html` exists:
* mount `/assets` as StaticFiles;
* add a catch-all `GET /{path:path}` that returns `index.html` for any path not starting with `api/` or `ws`, and serves real files (favicon, manifest) when present.
Otherwise `/` returns a JSON pointer to the docs (`/docs`) and a hint to build the web app.

---

## 11. Persistence

### 11.1 SQLite schema (`migrations/001_init.sql`)

```sql
CREATE TABLE schema_version (version INTEGER NOT NULL);

CREATE TABLE nodes (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('signer','verifier','adversary')),
  label TEXT, color TEXT, pos_x REAL, pos_y REAL, pos_z REAL, hidden INTEGER NOT NULL DEFAULT 0,
  suspended INTEGER NOT NULL DEFAULT 0, meta TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL);

CREATE TABLE groups (
  id TEXT PRIMARY KEY, signer_id TEXT NOT NULL REFERENCES nodes(id), recipients TEXT NOT NULL,  -- JSON [v1,v2]
  hidden INTEGER NOT NULL DEFAULT 0, reservoir_target INTEGER NOT NULL DEFAULT 3, created_at REAL NOT NULL);

CREATE TABLE links (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('quantum','classical')),
  a TEXT NOT NULL REFERENCES nodes(id), b TEXT NOT NULL REFERENCES nodes(id),
  length_km REAL NOT NULL DEFAULT 0, baseline_channel TEXT NOT NULL DEFAULT '[]',  -- JSON spec list
  authenticated_classical INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','QUARANTINED','DEGRADED')),
  hidden INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL, created_at REAL NOT NULL);

CREATE TABLE link_secrets (link_id TEXT PRIMARY KEY REFERENCES links(id), mac_key BLOB NOT NULL);

CREATE TABLE baselines (
  link_id TEXT PRIMARY KEY REFERENCES links(id), calibrated_at REAL NOT NULL, samples INTEGER NOT NULL,
  spec_hash TEXT NOT NULL, stats TEXT NOT NULL);   -- JSON (counts + derived)

CREATE TABLE bundles (
  id TEXT PRIMARY KEY, group_id TEXT NOT NULL REFERENCES groups(id), signer_id TEXT NOT NULL,
  recipients TEXT NOT NULL, preset TEXT NOT NULL, params TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('DISTRIBUTING','ACTIVE','SIGNED','CONSUMED','COMPROMISED','REVOKED','EXPIRED')),
  origin TEXT NOT NULL, design TEXT, report TEXT,          -- JSON ThresholdDesign, DistributionReport(summary)
  injected_attack TEXT, counterfactual INTEGER NOT NULL DEFAULT 0,
  material_path TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, expires_at REAL);
CREATE INDEX ix_bundles_group_status ON bundles(group_id, status);

CREATE TABLE bundle_consumption (
  bundle_id TEXT NOT NULL REFERENCES bundles(id), verifier_id TEXT NOT NULL, session_id TEXT NOT NULL,
  consumed_at REAL NOT NULL, PRIMARY KEY (bundle_id, verifier_id));

CREATE TABLE nonces (verifier_id TEXT NOT NULL, nonce TEXT NOT NULL, session_id TEXT, seen_at REAL NOT NULL,
  PRIMARY KEY (verifier_id, nonce));
CREATE TABLE signer_sequences (signer_id TEXT NOT NULL, verifier_id TEXT NOT NULL, last_seq INTEGER NOT NULL,
  PRIMARY KEY (signer_id, verifier_id));
CREATE TABLE signer_counters (group_id TEXT PRIMARY KEY, next_seq INTEGER NOT NULL);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('distribution','signature')),
  origin TEXT NOT NULL CHECK(origin IN ('TRAFFIC','RESERVOIR','STUDIO','LAB','CAMPAIGN','API','CALIBRATION')),
  group_id TEXT, bundle_id TEXT, signer_id TEXT, recipients TEXT,
  message_preview TEXT, message_sha256 TEXT, encoding TEXT,
  injected_attack TEXT,                                      -- JSON AttackSpec or NULL (ground truth)
  verdict TEXT NOT NULL, threat_level TEXT NOT NULL, category TEXT, subtype TEXT,
  threat_score REAL NOT NULL DEFAULT 0, counterfactual INTEGER NOT NULL DEFAULT 0,
  latency_ms REAL, report TEXT NOT NULL,                     -- JSON full report (trace)
  created_at REAL NOT NULL);
CREATE INDEX ix_sessions_created ON sessions(created_at DESC);
CREATE INDEX ix_sessions_kind ON sessions(kind, created_at DESC);

CREATE TABLE incidents (
  id TEXT PRIMARY KEY, created_at REAL NOT NULL, updated_at REAL NOT NULL,
  severity TEXT NOT NULL, category TEXT NOT NULL, subtype TEXT, title TEXT NOT NULL, summary TEXT NOT NULL,
  link_id TEXT, group_id TEXT, session_id TEXT, bundle_id TEXT, occurrences INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
  assessment TEXT NOT NULL, actions TEXT NOT NULL DEFAULT '[]', ledger_tx_id TEXT);
CREATE INDEX ix_incidents_status ON incidents(status, created_at DESC);

CREATE TABLE link_monitor (
  link_id TEXT NOT NULL, t REAL NOT NULL, bundle_id TEXT, qber REAL, chsh REAL, fidelity REAL,
  cusum_qber REAL, cusum_chsh REAL, ewma_qber REAL, alarm INTEGER NOT NULL DEFAULT 0);
CREATE INDEX ix_link_monitor ON link_monitor(link_id, t DESC);
CREATE TABLE link_monitor_state (link_id TEXT PRIMARY KEY, state TEXT NOT NULL);

CREATE TABLE ledger_blocks (height INTEGER PRIMARY KEY, hash TEXT NOT NULL, prev_hash TEXT NOT NULL,
  merkle_root TEXT NOT NULL, timestamp REAL NOT NULL, tx_count INTEGER NOT NULL);
CREATE TABLE ledger_txs (id TEXT PRIMARY KEY, block_height INTEGER REFERENCES ledger_blocks(height),
  idx INTEGER, kind TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX ix_ledger_pending ON ledger_txs(block_height) WHERE block_height IS NULL;
CREATE TABLE ledger_tamper_log (id INTEGER PRIMARY KEY AUTOINCREMENT, tx_id TEXT NOT NULL,
  original_payload TEXT NOT NULL, tampered_at REAL NOT NULL, reverted_at REAL);

CREATE TABLE jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, params TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
  progress REAL NOT NULL DEFAULT 0, message TEXT, result TEXT, error TEXT,
  created_at REAL NOT NULL, started_at REAL, finished_at REAL);
CREATE INDEX ix_jobs_kind ON jobs(kind, created_at DESC);

CREATE TABLE kv_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
```

### 11.2 Keystore (`data/keystore/`)

* One file `{bundle_id}.npz` per ACTIVE or SIGNED bundle:
  * `labels` uint8 (digest_bits, 2, L), kept positions only;
  * `rec_{v}` uint8 (digest_bits, 2, L) per recipient v, packed `basis | o<<2 | fwd<<3` (fwd = forwarded to the peer);
  * `order_{v}` uint32 permutation seeds for SPRT ordering (optional);
  * `meta` JSON bytes.
* It is written atomically (temp file + `os.replace`) and **shredded** (unlinked) when the bundle reaches CONSUMED (both recipients), COMPROMISED (labels only; records kept inside the report summary), REVOKED or EXPIRED.
* The `VerifierView` loader reads only `rec_{self}` (own + fwd mask) and the peer's fwd positions. Code review rule: `labels` is loaded only by `SignerService`.

### 11.3 Retention

* `sessions` keeps the latest 5 000 rows. Older rows lose their full `report` (set to a summary) by a nightly-style pruning pass that runs every 10 min.
* `link_monitor` keeps 10 000 rows per link.
* `jobs` results are kept.
* `nonces` older than 24 h are pruned. That is safe: freshness already rejects signatures older than the window.

---

## 12. REST API reference

Base: `/api/v1`. JSON in and out. Timestamps are float Unix seconds, plus ISO strings where noted. Errors use the shape in §17.1. OpenAPI is served at `/openapi.json` and the Swagger UI at `/docs`.

### 12.1 System

| Method & path | Request | Response |
|---|---|---|
| `GET /health` | — | `{status:"ok", version, engine_version, uptime_s, db:"ok", ws_clients, preset, time}` |
| `GET /system/selftest` | — | `{state:"idle\|running\|done", started_at, finished_at, checks:[{id, name, status:"pass\|fail\|skip\|running\|pending", duration_ms, detail, metrics:{…}}]}` |
| `POST /system/selftest/run` | — | 202 + the same object (running) |
| `GET /system/config` | — | `{presets:{…}, active_preset, detection:{alpha_family, floors…, cusum…}, features:{tamper_demo, mac}, limits:{…}}` |
| `PUT /system/preset` | `{preset}` | new config (applies to future bundles) |

### 12.2 Network

| Method & path | Request | Response |
|---|---|---|
| `GET /network` | — | `{nodes:[Node], links:[LinkStatus], groups:[Group]}` (hidden entries excluded unless `?include_hidden=true`) |
| `GET /network/links/{id}` | — | `LinkDetail` = LinkStatus + baseline summary + monitor tail (100) + recent bundles |
| `PATCH /network/links/{id}` | `{baseline_channel?: [ChannelSpec], authenticated_classical?: bool, length_km?: number}` | `LinkDetail` (triggers recalibration if the channel changed) |
| `POST /network/links/{id}/certify` | — | `CertificationReport` (fresh calibration-size Bell test + PE vs baseline; lifts quarantine if CERTIFIED) |
| `POST /network/links/{id}/quarantine` | `{reason}` | `LinkStatus` |
| `POST /network/links/{id}/release` | — | `LinkStatus` (requires a passing certification within 10 min) |
| `GET /network/links/{id}/monitor?limit=200` | — | `[{t, qber, chsh, fidelity, cusum_qber, cusum_chsh, ewma_qber, alarm}]` |

`LinkStatus = {id, kind, a, b, length_km, status, authenticated_classical, baseline_channel, last:{t, qber, chsh, fidelity, cusum_qber, cusum_chsh, alarm}|null, baseline:{calibrated_at, qber, chsh, fidelity}|null}`

### 12.3 Keys

| Method & path | Request | Response |
|---|---|---|
| `GET /keys/reservoir` | — | `[{group_id, signer_id, recipients, active, target, signed, consumed_total, compromised_total, last_distribution_at}]` |
| `GET /keys/bundles?status&group_id&limit=50&before` | — | `[BundleSummary]` |
| `GET /keys/bundles/{id}` | — | `BundleDetail` (design, distribution report summary, lifecycle, consumption). **Never private material.** |
| `POST /keys/distribute` | `{group_id, preset?, attack?: AttackSpec, origin?: "STUDIO"\|"API"}` | `DistributionReport` |
| `POST /keys/bundles/{id}/revoke` | `{reason}` | `BundleSummary` |

`DistributionReport`:
```jsonc
{ "session_id": "...", "bundle_id": "...", "group_id": "g-alice", "preset": "standard",
  "params": {...}, "qubits_teleported": 2330624, "bell_pairs": 28000,
  "links": [ { "link_id": "alice-bob", "verifier_id": "bob",
      "bell": {"S": 2.781, "S_lcb": 2.64, "S_se": 0.021, "F": 0.987, "F_lcb": 0.981,
               "E": {"A0B0":0.70,...}, "counts": {...}, "predicted_error": {"x":..,"y":..,"z":..}},
      "pe": {"n": 116736, "qber": 0.0102, "qber_ci": [..], "per_basis": {"x": {...}, ...}},
      "tomography": {"M": [[..]], "c": [..], "M_se": [[..]], "effective_M": [[..]], "effective_c": [..],
                     "frame_matrix": [[..4x4..]], "fingerprint": {...}|null},
      "frame": {"compared": 116736, "mismatched": 0, "mac": "absent|ok|fail", "flip_rates": {"m0":0,"m1":0}},
      "hardware_time_ms_modelled": 2611.0,
      "sample": { "positions": [ {"label":4,"k":2,"c":2,"basis":2,"outcome":0,"pe":false}, ... 64 ] } } ],
  "symmetrization": {"forwarded_per_key": 1024},
  "design": { ThresholdDesign },
  "assessment": { Assessment },
  "status": "ACTIVE|COMPROMISED", "latency_ms": {"distribution": 212.4, "pe": 9.1, "detection": 3.2, "total": 231.0},
  "injected_attack": AttackSpec|null, "counterfactual": false, "incident_id": null }
```

### 12.4 Signatures and sessions

| Method & path | Request | Response |
|---|---|---|
| `POST /signatures/sign-and-verify` | `{group_id, message (≤4096 B; ≤31 B for raw), encoding?: "sha256"\|"raw", preset?, bundle_id?, origin?: "STUDIO"\|"API", include_trace?: true}` | `SignatureReport` |
| `POST /signatures/{session_id}/reverify` | `{verifier_id, delay_s?: number}` | `SignatureReport` (replays the stored captured signature; used by replay demos) |
| `GET /sessions?kind&origin&verdict&category&attack&limit=50&before` | — | `[SessionSummary]` |
| `GET /sessions/{id}` | — | full stored report (`DistributionReport` or `SignatureReport`) |

`SignatureReport`:
```jsonc
{ "session_id": "...", "group_id": "g-alice", "bundle_id": "...", "encoding": "sha256",
  "envelope": {"protocol":"QVERIS-TQDS/1","signer_id":"alice","recipients":["bob","charlie"],
               "seq": 41, "timestamp": 1758790000.12, "nonce": "9f…", "message": "…"},
  "digest": {"hex": "…", "bits": "0110…"},
  "signature": {"sha256": "…", "size_bytes": 524288, "revealed_sample": [[…16 keys × 48 labels…]]},
  "verifications": [
    { "verifier_id": "bob", "role": "first", "threshold": 0.0862, "decision": "ACCEPT",
      "guard": [Finding…], "keys": {"n_own":[256], "m_own":[256], "n_recv":[256], "m_recv":[256], "pass":[256]},
      "totals": {"tested": 174208, "mismatches": 1789, "rate": 0.0103},
      "sprt": {"used": 5210, "available": 174208, "early_reject": false, "trace": [[…8 keys…]]},
      "grid_sample": {"keys": 16, "positions": 48, "cells": [[{"b":1,"o":0,"set":"own","t":true,"x":false}…]]},
      "latency_ms": 18.2 },
    { "verifier_id": "charlie", "role": "transfer", "threshold": 0.2, "decision": "ACCEPT", … } ],
  "assessment": {Assessment}, "verdict": "ACCEPTED",
  "ledger": {"tx_id": "…", "status": "pending"},
  "latency_ms": {"encode":0.1,"sign":6.3,"verify_first":18.2,"verify_transfer":17.9,"detect":0.8,"total":44.9},
  "eps": {"rob_msg": 2.1e-10, "forge_key": 9.6e-7, "rep_msg": 1.2e-2},
  "injected_attack": null, "counterfactual": false, "incident_id": null }
```

### 12.5 Attacks, campaigns, traffic

| Method & path | Request | Response |
|---|---|---|
| `GET /attacks/catalog` | — | `[AttackCatalogEntry]` |
| `POST /attacks/run` | `{attack: AttackSpec, group_id?: "g-alice", message?, counterfactual?: true, preset?}` | `AttackRunReport = {attack, catalog_entry, distribution?: DistributionReport, signature?: SignatureReport, counterfactual?: {description, distribution?, signature?, outcome_sentence}, detected: bool, correctly_classified: bool, incident_id?, notes:[str]}` |
| `GET /attacks/campaigns` | — | `[Campaign]` |
| `POST /attacks/campaigns` | `{name, mix:[{attack: AttackSpec, weight}], rate_per_min (1..60), duration_s (10..3600), group_ids?}` | `Campaign` |
| `DELETE /attacks/campaigns/{id}` | — | `Campaign` (stopped) |
| `GET /traffic` | — | `{running, paused_idle, rate_per_min, generated, started_at, groups, last_session_at}` |
| `POST /traffic/start` | `{rate_per_min?: 1..120 (default 12), groups?}` | traffic state |
| `POST /traffic/stop` | — | traffic state |

Traffic messages are real transaction strings built at run time: `"TX {seq:06d} | {signer}→{recipient} | {amount:.2f} QVC | ref {nonce[:8]}"`, where amount and reference come from the CSPRNG.

### 12.6 Detection and incidents

| Method & path | Request | Response |
|---|---|---|
| `GET /detection/config` | — | `DetectionConfig` |
| `PUT /detection/config` | partial `DetectionConfig` (alpha_family ∈ [1e-12, 1e-2], floors ∈ sane ranges, cusum k/h > 0, enforce: bool) | `DetectionConfig` |
| `GET /detection/detectors` | — | `[{id, name, layer, description, statistic, null_hypothesis, severity_rule, conclusive}]` |
| `GET /detection/baselines` | — | `[{link_id, calibrated_at, samples, qber, qber_per_basis, S, S_se, F, M, c}]` |
| `POST /detection/baselines/calibrate` | `{link_ids?}` | `Job` |
| `GET /incidents?status&severity&category&limit=50&before` | — | `[IncidentSummary]` |
| `GET /incidents/{id}` | — | `IncidentDetail` (assessment, related session summary, link monitor window, actions, ledger tx) |
| `POST /incidents/{id}/acknowledge` | `{note?}` | detail |
| `POST /incidents/{id}/resolve` | `{note?}` | detail |
| `POST /incidents/{id}/respond` | `{action}` | `{incident, result}` |

### 12.7 Analytics, theory, playground

| Method & path | Request | Response |
|---|---|---|
| `GET /analytics/kinds` | — | `[{kind, title, description, params_schema, presets:{quick:{…}, full:{…}}, est_seconds:{quick, full}}]` |
| `POST /analytics/jobs` | `{kind, params?, preset?: "quick"\|"full"}` | `Job` |
| `GET /analytics/jobs?kind&limit` | — | `[Job]` (without large results) |
| `GET /analytics/jobs/{id}` | — | `Job` with `result` |
| `DELETE /analytics/jobs/{id}` | — | `Job` (cancelled) |
| `GET /analytics/latest/{kind}` | — | the latest SUCCEEDED `Job` with result, or 404 |
| `GET /theory/design?L&e&digest_bits&eps_rob&eps_forge` | — | `ThresholdDesign` (+ PMFs for plotting: honest Bin(n_min, e) and forger Bin(n_min, ⅓), trimmed to mass ≥ 1e-12) |
| `GET /theory/forgery?L_min&L_max&points&s_v&strategy` | — | `{L:[…], exact:[…], chernoff:[…]}` |
| `POST /theory/link` | `{channels:[ChannelSpec]}` | predicted `{S, F, qber_per_basis, qber, M, c, twirled_M}` |
| `POST /playground/channel` | `{channels:[ChannelSpec]}` | `{kraus:[{re:[[..]], im:[[..]]}], ptm:[[..]], M, c, choi_eigenvalues, cptp, twirled:{M,c}, predicted:{S,F,qber_per_basis}}` |
| `POST /playground/teleport` | `{bloch?:[x,y,z] \| label?: 0..5, channels?:[…], frame_flip?:{m0:0..1, m1:0..1}, shots?: 0..20000, basis?: "x"\|"y"\|"z"}` | `{input_bloch, outcomes:[{k, bits:[m0,m1], prob, bloch_pre, bloch_post}], average_bloch, fidelity, samples?:{basis, shots, counts:{"0":…,"1":…}, frames:{"00":…}}}` |

### 12.8 Ledger and metrics

| Method & path | Request | Response |
|---|---|---|
| `GET /ledger/summary` | — | `{height, head_hash, tx_total, pending, last_verification:{at, valid, first_invalid_height}\|null, tamper_demo_enabled, tampered:[tx_id]}` |
| `GET /ledger/blocks?before&limit=30` | — | `[BlockSummary]` |
| `GET /ledger/blocks/{height}` | — | `{block, txs:[Tx], merkle_levels:[[hash…]…]}` |
| `GET /ledger/tx/{id}` | — | `Tx` + inclusion proof `[{hash, side}]` |
| `POST /ledger/verify` | — | `{valid, checked_blocks, checked_txs, first_invalid_height, issues:[{height, tx_id?, kind, detail}], duration_ms}` |
| `POST /ledger/tamper` | `{height?}` | `{tx_id, height, field, before_hash, note}` (403 if disabled) |
| `POST /ledger/tamper/revert` | — | `{reverted:[tx_id]}` |
| `GET /metrics/summary?window=all\|1h\|15m` | — | `MetricsSummary` (below) |
| `GET /metrics/timeseries?series=sessions\|detections\|latency\|qber&window=1h&bucket_s=60&link_id?` | — | `{series, bucket_s, points:[{t, …}]}` |
| `GET /metrics/prometheus` | — | text exposition |

`MetricsSummary`:
```jsonc
{ "window": "all", "generated_at": 1758790000.0,
  "sessions": {"signature_total": 812, "accepted": 790, "rejected": 22, "by_origin": {"TRAFFIC": 760, ...}},
  "distributions": {"total": 301, "certified": 280, "compromised": 21},
  "detection": {
     "legit_runs": 1041, "false_rejections": 0, "frr": 0.0, "frr_ci": [0, 0.0035],
     "attack_runs": 62, "detected": 62, "far": 0.0, "far_ci": [0, 0.057],
     "correctly_classified": 60, "classification_accuracy": 0.968,
     "per_category": [{"category":"FORGERY","runs":10,"detected":10,"correct":10,"ci":[..]}, ...] },
  "throughput_per_min": 11.8, "latency_ms": {"p50": 41.2, "p95": 66.0},
  "links": [LinkStatus…], "reservoir": [...],
  "ledger": {"height": 42, "tx_total": 1320, "pending": 3},
  "incidents": {"open": 3, "by_severity": {"CRITICAL":1,"HIGH":2}}, "threat_level": "HIGH",
  "traffic": {TrafficState} }
```

Detection metrics use the ground truth stored in `sessions.injected_attack`. Counterfactual rows are excluded. A legitimate run is any row with `injected_attack IS NULL`.

---

## 13. WebSocket protocol

Endpoint `GET /ws` (upgrade). Envelope in both directions:

```jsonc
{ "v": 1, "type": "session.completed", "topic": "sessions", "ts": 1758790000.123, "id": 1834, "data": { ... } }
```

* **Client → server:**
  * `{"op":"subscribe","topics":["sessions","incidents",…]}` (the default after connect is **all topics**);
  * `{"op":"unsubscribe","topics":[…]}`;
  * `{"op":"ping","t":<client ms>}`.
* **Server → client:**
  * `hello` `{server_version, server_time, topics, traffic, preset}`;
  * `pong` `{t, server_time}`;
  * `lag` `{dropped}`;
  * the topic events below.

| topic | type | data |
|---|---|---|
| `sessions` | `session.completed` | `SessionSummary` (signature) |
| `distributions` | `distribution.completed` | `DistributionSummary` |
| `incidents` | `incident.opened` / `incident.updated` | `IncidentSummary` |
| `links` | `link.updated` | `LinkStatus` |
| `reservoir` | `reservoir.updated` | reservoir array |
| `traffic` | `traffic.state` / `campaign.state` | state objects |
| `metrics` | `metrics.tick` (1 Hz, only while clients are connected) | `{sessions_per_min, accepted_last_min, rejected_last_min, threat_level, open_incidents, ledger_height, reservoir_total}` |
| `jobs` | `job.progress` / `job.completed` | `{job_id, kind, status, progress, message}` |
| `ledger` | `ledger.block` / `ledger.verified` / `ledger.tampered` | block summary / verification result / tamper info |
| `system` | `selftest.check` / `selftest.done` / `system.notice` | check / summary / `{level, message}` |

Heartbeat: the server sends `pong`-style `{"type":"heartbeat"}` every 15 s. The client reconnects with exponential backoff (0.5 s → 8 s, jitter) after 30 s of silence.

`SessionSummary = {id, kind:"signature", created_at, origin, group_id, signer_id, recipients, message_preview, bundle_id, verdict, threat_level, category, subtype, threat_score, injected_attack:{attack_id, category}|null, latency_ms, decisions:{first:"ACCEPT|REJECT", transfer:"ACCEPT|REJECT|SKIPPED"}}`
`DistributionSummary = {id, kind:"distribution", created_at, origin, group_id, bundle_id, verdict, threat_level, category, subtype, threat_score, injected_attack|null, qubits, latency_ms, links:[{link_id, verifier_id, S, qber, frame_mismatch}]}`

---

## 14. Background workers

### 14.1 Reservoir maintainer
* Every 2 s, for each visible group with `reservoir_target > 0`: if its ACTIVE count is below target **and** the traffic is running or the reservoir was never filled, distribute one bundle (origin `RESERVOIR`) through the compute semaphore.
* COMPROMISED results raise incidents like any other.
* Bundles are skipped for groups whose links are QUARANTINED; the reservoir entry shows `blocked_reason`.

### 14.2 Traffic generator
* While running: every `60/rate` seconds (± 20% jitter), pick the next visible group round-robin and run `sign_and_verify(origin=TRAFFIC)` with a fresh transaction message.
* If no ACTIVE bundle exists, the tick is skipped with a `system.notice` "reservoir empty". It never blocks the loop.
* **Idle guard:** with `QVERIS_AUTOSTART_TRAFFIC=1`, traffic starts when the first WS client connects. It pauses (`paused_idle=true`) 120 s after the last client disconnects, and resumes on reconnect.

### 14.3 Campaign runner
* Each campaign ticks at its rate and draws an attack from the weighted mix with the CSPRNG. It calls `run_attack(origin=CAMPAIGN, counterfactual=False)`.
* It stops at `duration_s` or on DELETE, and emits `campaign.state`.

### 14.4 Block producer
* Every 1 s: seal when pending ≥ 16 or the oldest pending is ≥ 8 s old. Emits `ledger.block`.

### 14.5 Metrics ticker
* 1 Hz while any WS client is connected: cheap aggregate queries over the last 60 s. Emits `metrics.tick`.

### 14.6 Selftest (startup + on demand)

| id | Check | Pass criterion |
|---|---|---|
| `channels.cptp` | Every channel family × 5 parameter points | Choi eig ≥ −1e-10, TP error < 1e-12 |
| `teleport.ideal` | Noiseless model | p_k = ¼ ± 1e-12, output = input ± 1e-12 for 6 labels |
| `teleport.aer` | §4.7 | max \|Δρ\| < 1e-9 (skip if qiskit missing) |
| `bell.ideal` | ρ = Φ⁺ | S = 2√2 ± 1e-12, F = 1 |
| `bell.depolarizing` | p = 0.2 | S = 2√2·0.8 ± 1e-12 |
| `tomography.roundtrip` | AD(0.3) and rotation(ẑ, 0.5) with 2·10⁵ samples | de-twirled M, c within 5σ; the effective map shows c ≈ 0 (twirl) |
| `stats.tails` | binom/hypergeom vs brute force for small n | exact equality |
| `rng.labels_uniform` | 60 000 CSPRNG labels | χ² p > 1e-6 |
| `ledger.chain` | Verify the current chain | valid (reports first invalid otherwise) |
| `protocol.honest_roundtrip` | A `demo`-preset bundle over an ideal link, sign + verify | ACCEPTED at both verifiers, CERTIFIED |

Results stream over the `system` topic, which is the source of the frontend boot sequence.

---

## 15. Analytics jobs

Every job is `run(params, progress_cb, cancel_event) -> result_dict`. Results are JSON-serialisable, contain their `params` and `seed`, and include `generated_at` and `duration_s`. Default presets:

| kind | Quick params | Full params | Result schema (keys) |
|---|---|---|---|
| `engine_validation` | 6 channels | + 12 channels × 3 strengths | `{checks:[{channel, max_dev, per_label:[…]}], aer_version, pass}` |
| `detection_matrix` | analysis preset; attacks = all 17; intensities [0.25, 0.5, 1.0]; trials 6; legit 60 | intensities [0.1, 0.25, 0.5, 0.75, 1.0]; trials 20; legit 200 | `{attacks:[{attack_id, category, points:[{intensity, runs, detected, rate, ci, correct, classification_rate}]}], legit:{runs, false_rejections, frr, frr_ci}, confusion:{labels:[…], matrix:[[…]]}, far:{…}}` |
| `roc` | attack `channel.depolarize` at intensity 0.05, 150 legit + 150 attack runs | 400 + 400, 3 attacks | `{curves:[{detector, points:[{alpha, tpr, fpr}], auc}]}`. Sweeps α over logspace(−12, −0.3, 40) using stored p-values, with no re-simulation per α |
| `forgery_analysis` | L ∈ {32..2048} (8 pts); MC 2 000 key trials per L for L ≤ 128 | 12 pts; MC 20 000 | `{curves:{external:{exact,chernoff}, insider:{exact,chernoff}}, mc:[{L, strategy, trials, passes, rate, ci}], message_level:[{k, eps}], insider_optimum:{min, argmin, grid_points}}` |
| `threshold_design` | e ∈ {0.005, 0.01, 0.02, 0.04}; L ∈ {256..16384} | finer grid | `{rows:[{e, L, s_a, s_v, eps_rob, eps_forge, eps_rep_key, eps_rep_msg, feasible}]}` |
| `sprt_efficiency` | p ∈ [0, 0.5] (26 pts), n = 400, 500 paths each | 2 000 paths | `{points:[{p, asn_mc, asn_wald, reject_rate}], fixed_n}` |
| `channel_fingerprint` | families × 3 strengths × 10 trials (analysis preset) | × 5 strengths × 30 | `{labels, matrix, per_family:[{family, strength, predicted_shape, accuracy}]}` |
| `cusum_arl` | shifts Δe ∈ {0, .0025, .005, .01, .02}, 200 runs | 1 000 runs | `{points:[{shift, arl_mean, arl_ci, false_alarm}]}`. Per-bundle QBER sampled from the exact binomial of the link model at the analysis preset |
| `performance` | L ∈ {256, 512, 1024, 2048}, 5 reps | + {4096, 8192}, 10 reps | `{rows:[{L, qubits, distribution_ms, sign_ms, verify_ms, detect_ms, qubits_per_s}], aer_vs_numpy:{aer_ms_per_qubit, numpy_ms_per_qubit, speedup}}` |
| `repudiation_analysis` | r ∈ [0, 0.5] (11 pts), 200 runs, demo preset | 1 000 runs | `{points:[{r, dispute_rate_with_sym, dispute_rate_without_sym, ci…}], bound:{…}}` |

Jobs publish `job.progress` at ≥ 1% increments (at most 5 Hz). Cancellation is checked between trials, and a cancelled job stores the partial result with `partial: true`.

---

## 16. Configuration

### 16.1 `config/sentinel.yaml`

```yaml
engine:
  chunk_size: 1048576
  model_cache: 256
presets:
  demo:      { L: 1024, bell_pairs_per_setting: 1000, eps_rob_target: 1.0e-6, eps_forge_target: 1.0e-4, eps_rep_target: 1.0e-3, delta_pe: 1.0e-8, sprt_alpha: 1.0e-11 }
  standard:  { L: 4096, bell_pairs_per_setting: 2000, eps_rob_target: 1.0e-9, eps_forge_target: 1.0e-6, eps_rep_target: 1.0e-6, delta_pe: 1.0e-10, sprt_alpha: 1.0e-13 }
  high:      { L: 8192, bell_pairs_per_setting: 4000, eps_rob_target: 1.0e-12, eps_forge_target: 1.0e-12, eps_rep_target: 1.0e-12, delta_pe: 1.0e-14, sprt_alpha: 1.0e-17 }
  analysis:  { L: 1024, bell_pairs_per_setting: 1000, digest_bits: 32, analysis_only: true, eps_rob_target: 1.0e-6, eps_forge_target: 1.0e-4, eps_rep_target: 1.0e-3, delta_pe: 1.0e-8, sprt_alpha: 1.0e-10 }
protocol:
  digest_bits: 256
  f_pe: 0.10
  eps_rob_target: 1.0e-9
  eps_forge_target: 1.0e-6
  eps_rep_target: 1.0e-6
  delta_pe: 1.0e-6
  delta_bell: 1.0e-5
  freshness_window_s: 120
  sprt: { alpha: 1.0e-9, beta: 1.0e-6 }
  bundle_ttl_s: 86400
detection:
  alpha_family: 1.0e-6
  enforce: true
  floors: { chsh_drop: 0.10, fidelity_drop: 0.02, qber_rise: 0.01, tomography_max_dev: 0.04, consistency: 0.01 }
  cusum: { qber_k: 0.0025, qber_h: 0.015, chsh_k: 0.02, chsh_h: 0.12, ewma_lambda: 0.2 }
  calibration: { pe_samples: 400000, bell_pairs_per_setting: 20000 }
server:
  active_preset: standard
  compute_workers: 2
  traffic_rate_per_min: 12
  reservoir_target: 3
  block_max_txs: 16
  block_max_age_s: 8
hardware_model: { source_rate_hz: 1.0e7, fibre_loss_db_per_km: 0.2, detector_efficiency: 0.9 }
```

### 16.2 `config/network.yaml`

This is the seeded topology described in §2.1: node positions for the 3D layout, colours, labels, groups, and links with `length_km` and `baseline_channel` spec lists. The defaults:

| Link | length_km | baseline_channel |
|---|---|---|
| alice-bob | 22 | depolarizing 0.012 → amplitude_damping 0.004 |
| alice-charlie | 35 | depolarizing 0.016 → amplitude_damping 0.006 |
| diana-charlie | 18 | depolarizing 0.010 → phase_damping 0.010 |
| diana-erin | 41 | depolarizing 0.018 → amplitude_damping 0.008 |
| mallory-bob, mallory-charlie (hidden) | 25 | depolarizing 0.012 |

Classical links: bob-charlie and charlie-erin (verifier channels).

An `ideal` link preset (`baseline_channel: []`) can be applied through PATCH for the deterministic-acceptance demo.

### 16.3 Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `QVERIS_HOST` / `QVERIS_PORT` | 0.0.0.0 / 8000 | Bind address |
| `QVERIS_DATA_DIR` | `./data` | DB + keystore |
| `QVERIS_ENV` | `development` | `production` disables the seeded RNG + tamper demo by default |
| `QVERIS_PRESET` | from yaml | Override the active preset |
| `QVERIS_AUTOSTART_TRAFFIC` | `1` | Start traffic on the first WS client |
| `QVERIS_ALLOW_TAMPER_DEMO` | `1` (dev) | Enable `/ledger/tamper` |
| `QVERIS_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated |
| `QVERIS_SEED` | unset | Seeded physics RNG for reproducible runs (tests) |
| `QVERIS_SKIP_CALIBRATION` | `0` | Tests only |
| `QVERIS_API_KEY` | unset | If set, mutating endpoints require `X-API-Key` |
| `QVERIS_LOG_LEVEL` | `INFO` | |

---

## 17. Errors, validation, limits, logging, hardening

### 17.1 Error shape

```json
{ "error": { "code": "BUNDLE_UNAVAILABLE", "message": "No ACTIVE bundle for group g-alice", "status": 409,
             "detail": {"group_id": "g-alice", "reservoir": 0}, "request_id": "4c1e…" } }
```

| code | status | when |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Pydantic validation (field errors in detail) |
| `NOT_FOUND` | 404 | Unknown id |
| `BUNDLE_UNAVAILABLE` | 409 | No ACTIVE bundle and on-demand distribution failed or was refused |
| `BUNDLE_COMPROMISED` | 409 | Signing with a COMPROMISED bundle outside a counterfactual |
| `LINK_QUARANTINED` | 409 | Distribution over a quarantined link |
| `KEY_REUSE` | 409 | A second signature from a bundle |
| `MESSAGE_TOO_LONG` | 413 | > 4096 B, or > 31 B in raw |
| `RATE_LIMITED` | 429 | Token bucket empty (`Retry-After` header) |
| `FEATURE_DISABLED` | 403 | Tamper demo off |
| `UNAUTHORIZED` | 401 | API key required/invalid |
| `JOB_CONFLICT` | 409 | Same kind already running |
| `INTERNAL` | 500 | Unexpected; logged with the request id, message sanitised |

### 17.2 Limits and rate limiting

* Token buckets per client IP:
  * heavy POSTs (`distribute`, `sign-and-verify`, `attacks/run`, `certify`, jobs): capacity 12, refill 1 per second;
  * light endpoints: 60 per second.
* Request body ≤ 64 KiB.
* WebSocket clients ≤ 32.

### 17.3 Logging and observability

* Standard `logging` with the format `ts level logger request_id message`. The request-id middleware sets the `X-Request-ID` header.
* Access logs from uvicorn.
* Engine timings are logged at DEBUG.
* `/metrics/prometheus` exposes counters (sessions by verdict, detections by category), histograms (latency) and gauges (reservoir, open incidents, ws clients).

### 17.4 Hardening

* No private material ever serialised to the API (tests assert that no response contains the key `labels`).
* Keystore files are created with mode 0600.
* The seeded RNG is refused in production.
* CORS is an allow-list.
* The tamper demo is off in production.
* Mutating endpoints are optionally API-key protected.
* SQL is fully parameterised.
* Hostile input is validated: message size and encoding, channel params ranges, attack params against the catalog schema, enum checks.

---

## 18. Testing strategy

All tests use pytest (`pythonpath = ["src", "."]`). Statistical tests use fixed seeds (seeded mode) and **wide, justified tolerances** (≥ 5σ), so they are deterministic and not flaky.

| Suite | File | Key assertions |
|---|---|---|
| linalg | `tests/sentinel/test_linalg.py` | PTM ↔ Kraus ↔ Choi round-trips; polar decomposition; Rodrigues matches the U-conjugation PTM |
| channels | `test_channels.py` | CPTP across grids; closed-form M, c match the Kraus-derived ones; composition order |
| teleport | `test_teleport.py` | Ideal exactness; p_k = ¼; per-k conditional forms; Pauli-channel averaged map = channel; tampering produces the expected Pauli |
| aer | `test_aer_validation.py` | §4.7 for 6 channels (skip if no qiskit) |
| bell | `test_bell.py` | T = T₀Mᵀ; S, F closed forms; sampling estimates within 5σ; CP bounds cover the truth |
| tomography | `test_tomography.py` | De-twirl recovers AD and rotation; the effective map loses c; frame matrix diagonal when clean |
| stats | `test_stats.py` | Tails vs brute force; Holm vs a hand example; two-proportion/Fisher switch |
| sequential | `test_sequential.py` | SPRT decisions on crafted streams; ASN(Wald) vs MC within 10%; CUSUM alarm times on crafted inputs |
| protocol | `test_protocol.py` | Honest bundle CERTIFIED + ACTIVE; honest signature ACCEPTED by both; one-time signing; symmetrization sets sizes; raw encoding bounds; envelope binding |
| thresholds | `test_thresholds.py` | Designer tails; monotonicity in n; infeasible → L_min |
| attacks | `test_attacks_detection.py` | **Each of the 17 variants at its reference intensity** → detected + correct category/subtype; insider attribution; MITM counterfactual accepts Eve's forgery at f = 1; repudiation counterfactual disputes without symmetrization |
| FAR | `test_false_alarms.py` | 200 honest bundles (analysis preset) + 200 honest signatures → 0 COMPROMISED, 0 REJECTED |
| boundaries | `test_information_boundaries.py` | Adversary modules never import keystore label loaders; grep for result mutation (P3); no `labels` in API JSON |
| ledger | `test_ledger.py` | Merkle vectors, verification, tamper detection + revert |
| server | `tests/server/test_api_*.py` | Every endpoint (TestClient); WS `hello` + `session.completed`; reservoir fill; traffic tick; incidents from attacks; jobs lifecycle (quick presets with tiny params); restart persistence (new app on the same data dir) |
| analysis | `tests/sentinel/test_analysis.py` | Insider optimum = ⅓ ± 1e-3; forgery MC within CI of exact; job result schemas |

Reference intensities for the attack tests (analysis preset unless stated):

| Attack | Intensity / params |
|---|---|
| depolarize | 0.5 |
| dephase | 0.5 |
| amplitude_damp | 0.5 |
| coherent_rotation | 0.5 |
| intercept_resend | 0.5 |
| pauli_frame | 0.3 |
| key_harvest_mitm | 0.5 |
| repudiation | 0.5 |
| forgery.* | mode `modified_message` |
| bit_flip_oracle | k = 1 |
| impersonation.*, replay.*, non_recipient | defaults |

CI budget: the full Python suite should run in under 4 minutes on the container, including v1's ~36 s.

---

## 19. Module map and signatures

```python
# sentinel/states.py
LABELS: tuple[str, ...] = ("+", "-", "+i", "-i", "0", "1")
BASIS_OF: np.ndarray  # uint8[6]  = [0,0,1,1,2,2]
BIT_OF: np.ndarray    # uint8[6]  = [0,1,0,1,0,1]
BLOCH: np.ndarray     # float[6,3]
V4: np.ndarray        # float[6,4] homogeneous
FRAME_PERM: np.ndarray  # uint8[4,6]  π_k(ℓ)
def label_from(basis: int, bit: int) -> int

# sentinel/linalg.py
PAULIS: np.ndarray  # complex[4,2,2]
def kraus_to_ptm(kraus) -> np.ndarray
def ptm_to_choi(R) -> np.ndarray
def is_cptp(R, tol=1e-10) -> tuple[bool, dict]
def ptm_affine(R) -> tuple[np.ndarray, np.ndarray]
def unitary_ptm(U) -> np.ndarray
def pauli_ptm(index: int) -> np.ndarray
def polar(M) -> tuple[np.ndarray, np.ndarray]
def rotation_axis_angle(U) -> tuple[np.ndarray, float]
def partial_trace(rho, keep: Sequence[int], dims: Sequence[int]) -> np.ndarray
def bloch_to_rho(r) -> np.ndarray ; def rho_to_bloch(rho) -> np.ndarray

# sentinel/channels.py
@dataclass(frozen=True) class Channel: name: str; params: dict; kraus: tuple; ptm: np.ndarray
def channel_from_spec(spec: Mapping) -> Channel
def compose(specs: Sequence[Mapping]) -> Channel
def spec_key(specs) -> str       # canonical JSON for caching
CHANNEL_TYPES: dict[str, ChannelTypeInfo]   # for API schema

# sentinel/teleport.py
class TeleportationModel:
    R: np.ndarray            # float[4,4,4] (k,i,j)
    p_k: np.ndarray          # float[6,4]
    bloch: np.ndarray        # float[6,4,4,3]
    p_plus: np.ndarray       # float[6,4,4,3]
    def teleport_bloch(self, r) -> list[dict]
    def averaged_ptm(self) -> np.ndarray
def get_model(channel_B_specs, channel_A_specs=()) -> TeleportationModel   # cached
def sample_teleportations(model, labels, bases, rng, flip_c0=None, flip_c1=None) -> tuple[np.ndarray, np.ndarray, np.ndarray]

# sentinel/bell.py
def bell_state(channel_B: Channel, channel_A: Channel | None = None) -> np.ndarray       # 4x4
def correlation_tensor(rho) -> tuple[np.ndarray, np.ndarray, np.ndarray]                 # T, a, b
SETTINGS: tuple[BellSetting, ...]   # 7 (name, alpha, beta)
def setting_probs(rho) -> np.ndarray                                                      # [7,4]
def sample_bell_test(probs, n_per_setting, rng) -> np.ndarray                             # counts [7,4]
def estimate_bell(counts, delta) -> BellEstimate
def predicted(rho) -> dict   # exact S, F, predicted errors

# sentinel/tomography.py
def aggregate_pe(labels, k, c, bases, outcomes) -> PECounts     # 288-cell counts + qber counts
def detwirl(pe: PECounts) -> ChannelEstimate
def effective(pe: PECounts) -> ChannelEstimate
def frame_matrix(pe: PECounts) -> np.ndarray

# sentinel/stats.py        (see §6.2)
# sentinel/sequential.py   Sprt, Cusum, Ewma
# sentinel/rng.py
class RandomSource: def labels(n); def bases(n); def bits(n, p=0.5); def uniform(n); def permutation_keys(shape); def token_hex(nbytes); physics: np.random.Generator

# sentinel/protocol/params.py     ProtocolParams, PRESETS, load_presets(yaml)
# sentinel/protocol/encoding.py   Envelope, encode_bits(envelope, digest_bits) -> np.ndarray[uint8]
# sentinel/protocol/keys.py       KeyBundle (labels + records), VerifierView, pack/unpack
# sentinel/protocol/link.py       LinkPhysics(baseline specs, attack plan) -> models & masks
# sentinel/protocol/distribution.py
def distribute(group: GroupSpec, links: dict[str, LinkPhysics], params, rng, attack_plans=None) -> DistributionOutcome
# sentinel/protocol/symmetrization.py   symmetrize(bundle, rng) -> None (sets fwd masks)
# sentinel/protocol/signing.py          sign(bundle, envelope) -> Signature
# sentinel/protocol/verification.py     verify(view: VerifierView, signature, threshold, design, sprt=True, pooled=False) -> VerificationReport
# sentinel/protocol/thresholds.py       design(...) -> ThresholdDesign ; repudiation_bound(...)
# sentinel/protocol/guard.py            GuardState protocol (nonce/seq/consumption), check(envelope, bundle_meta, verifier_id, now) -> list[Finding]

# sentinel/adversary/catalog.py         CATALOG: list[AttackCatalogEntry]; get(id)
# sentinel/adversary/distribution_attacks.py  plan_for(spec, link_ctx) -> LinkPlan
# sentinel/adversary/signing_attacks.py       execute(spec, ctx: SigningAttackContext) -> AttackOutcome
# sentinel/adversary/knowledge.py             AdversaryKnowledge builders

# sentinel/detection/findings.py        Finding, Severity, Assessment, Classification
# sentinel/detection/baseline.py        LinkBaseline, calibrate_link(physics, samples, rng)
# sentinel/detection/distribution_detectors.py  run_link_detectors(link_evidence, baseline, cfg) -> list[Finding]; copy_consistency(...)
# sentinel/detection/signature_detectors.py     key_tests(...), sprt_finding(...), forensics(...), transfer_consistency(...)
# sentinel/detection/fingerprint.py     classify(baseline_est, current_est) -> Fingerprint
# sentinel/detection/fusion.py          fuse_distribution(findings_by_link, group_findings, cfg) -> Assessment ; fuse_signature(...)
# sentinel/detection/monitor.py         LinkMonitor(state).update(evidence) -> (Finding|None, point)

# sentinel/analysis/{forgery,design,detection_eval,performance,validation,cusum,sprt,repudiation,fingerprint_eval}.py
# sentinel/ledger.py  canonical_json, sha256_hex, merkle_root(levels), merkle_levels, inclusion_proof, block_hash
```

---

## 20. Build, run, deploy

* Python ≥ 3.10 (container: 3.11). Dependencies are added to `requirements.txt` and `pyproject.toml`: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `httpx` (tests); qiskit and qiskit-aer stay (v1 + validation).
* Run the server:
  * `python -m server`, or
  * `uvicorn server.app:create_app --factory --app-dir src --port 8000`.
* `scripts/dev.sh` runs the backend with reload, plus `npm run dev` in `web/` (Vite proxy `/api` and `/ws` → 8000).
* `scripts/start.sh`:
  1. create a venv if missing;
  2. `pip install -r requirements.txt`;
  3. `npm ci && npm run build` in `web/`;
  4. `python -m server`.
* **Dockerfile** (multi-stage):
  * `node:22-alpine` builds `web/dist`;
  * `python:3.11-slim` installs the requirements, copies `src`, `config` and `web/dist`;
  * `EXPOSE 8000`; `HEALTHCHECK` on `/api/v1/health`.
  `docker-compose.yml` mounts a `./data` volume.
* **CI** (`.github/workflows/ci.yml`): job `python` (pip install, pytest), job `web` (npm ci, type-check, vitest, build).

---

## 21. Implementation order

1. `states`, `linalg`, `channels` + tests.
2. `teleport` (+ Aer validation), `bell`, `tomography` + tests.
3. `stats`, `sequential` + tests.
4. Protocol: `params`, `encoding`, `keys`, `link`, `distribution`, `symmetrization`, `signing`, `verification`, `thresholds`, `guard` + honest end-to-end tests.
5. Detection: `findings`, `baseline`, detectors, `fingerprint`, `fusion`, `monitor` + FAR tests.
6. Adversaries (catalog + both phases) + attack-detection tests + counterfactuals.
7. `ledger` + analysis modules + tests.
8. Server: DB, repos, services, routes, WS, workers, jobs + API tests.
9. Frontend (see frontend plan), bound to the real API.
10. Performance pass (§8 targets) and a doc update with the measured numbers.

---

## 22. Known limitations (stated up front)

1. **Simulation, not hardware.** Physics is exact linear algebra plus sampling. There is no photonic hardware, and loss appears only in the modelled hardware time.
2. **Collective (i.i.d.) attacks only.** Coherent attacks across many positions and finite-key effects beyond the stated tail bounds are out of scope.
3. **Repudiation bound is weak at `standard` L** (≈ 1e-2 at message level). This is reported honestly; `high` fixes it at a higher qubit cost.
4. **Equivalent channels are indistinguishable.** The fingerprint names an equivalence class, not an intent.
5. **SHA-256 in `sha256` mode** is a computational assumption (post-quantum collision security ≈ 2⁸⁵ under BHT). `raw` mode avoids it for ≤ 31-byte messages.
6. **Two recipients per group.** N-party symmetrization is designed (§3.11) but not implemented.
7. **Replay is caught by the protocol layer, not by physics.** A replayed signature is quantum-mechanically perfect. We say so on screen.
