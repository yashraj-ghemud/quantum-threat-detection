# Security Model

The security model of our Quantum-Inspired Digital Signature (QDS) Framework defines the security assumptions, trust boundaries, and threat capabilities modeled and defended against by our anomaly detection layers.

## Fundamental Security Posture

Security here rests on two independent foundations:

1. **A computational secret.** The signer holds a 256-bit private seed drawn from the OS CSPRNG (`secrets.token_bytes`), from which the key table of Pauli eigenstates is derived by HMAC-SHA256. Without that seed, the table is unpredictable.
2. **Physical bounds.** The **No-Cloning Theorem** and the **Observer Effect** mean the quantum public key cannot be copied off the wire, and an eavesdropper cannot read a signature element without disturbing it.

Both matter. The physics alone does not prevent forgery if the state sequence is publicly derivable — which is precisely the flaw an earlier revision had, where signatures were generated from the message id plus the **public** `random_seed: 42` in `config/quantum_config.yaml`. Anyone who read the config could reproduce a signature byte-for-byte. Key material is now the root of unforgeability, and the physics protects its distribution.

### Key lifecycle

```
generate_key_pair()          secrets.token_bytes(32)  -> PrivateKey
  |                          HMAC-SHA256              -> key table (secret)
  v
distribute_public_key()      Bell pair -> teleport -> Pauli correction
  |                          verifier reconstructs the table as QUANTUM states
  v
sign_message(msg, priv)      indices = f(SHA-256(msg))      [public]
  |                          states  = key_table[indices]   [secret]
  v
verify_signature(sig, pub)   measure received states against the verifier's
                             own teleported copy, under the Born rule
```

The index derivation is deliberately public so the verifier needs no secret. Unforgeability comes from the *contents* of the table, exactly as in Gottesman-Chuang QDS.

### Verification Paradigms

1. **Classical Hardening**: The QDS state acts as a one-time pad (OTP). When the threshold drops below the hard limit (e.g. `0.70`), standard authentication instantly triggers a REJECT.
2. **Statistical Hardening**: Because true quantum states suffer from decoherence, we cannot strictly reject every mismatch. Thus, the real evaluation analyzes the **pattern** of mismatches vs expected system hardware noise levels. An anomaly score > `warning` limit throws `SUSPICIOUS`; crossing `critical` throws `THREAT`.

### Measurement model and why it matters

Each key element is distributed as multiple copies and measured under the Born rule (`copies_per_element`, default 16). This is not a detail. A single-copy verifier that resolves ties deterministically — taking `p(+1) >= p(-1)` as `+1` — gives a forger who guesses a *conjugate*-basis state a free 50% match rate per element, because such a state yields exactly `p(+1) = p(-1) = 0.5`. Measured, that flaw let **4.5%** of blind forgeries through. Sampling the Born distribution across copies and requiring the mean eigenvalue to clear a decision margin reduces blind-forgery acceptance to **0 in 2000 trials**, with honest verification unaffected (200/200).

### Trust Boundaries

* **Sender (Alice)**: Trusted for *this* version — see "Out of scope" below. Holds the private seed; the seed never leaves the signer and is redacted from `repr` so it cannot leak into logs or experiment output.
* **Quantum Channel**: Fully UNTRUSTED. Open to MITM, eavesdropping, and hardware noise. Modeled with the Qiskit Aer noise models in `quantum/noise.py` applied to the real teleportation circuit.
* **Receiver (Bob)**: Trusted to perform faithful projective measurements, and to hold the teleported public key privately.

### Out of scope for this version: signer repudiation

A dishonest **signer** who later denies a valid signature is **not** defended against here. Alice is trusted, so the model covers forgery, impersonation, replay, unauthorized verification, and channel manipulation — but not a signer repudiating their own signature.

This is a real gap relative to the QDS literature. Gottesman-Chuang QDS defends against repudiation by having the signer distribute key copies to *multiple* recipients and accepting a signature only if it passes at a stricter threshold than the one used for transfer; the gap between the two thresholds is what makes a signature transferable and repudiation detectable. Implementing that requires multi-recipient key distribution and a two-threshold accept/transfer rule, which this version does not have. It is scoped out deliberately, not overlooked.

## Detection layers by attack category

| Attack | Primary detection | Mechanism |
|---|---|---|
| Forgery | Quantum-statistical | Guessed states mismatch the key table |
| Impersonation | Quantum-statistical + key binding | `key_id` mismatch, and states from a different table |
| Channel manipulation | Quantum-statistical | Channel noise degrades fidelity and perturbs measurement statistics |
| Unauthorized verification | **Quantum-statistical**, plus classical access control | Intercept-resend collapse (below) |
| Replay | Classical session consistency | A replayed signature is quantum-mechanically *perfect*; only metadata reveals it |

**Unauthorized verification** deserves a note, because an earlier revision detected it *only* via the classical authorization flag and therefore reported an anomaly score of exactly `0.0000` for the whole category — contradicting the project's claim that all categories are detected by quantum measurement statistics. It is now caught primarily by physics: to read an element, the unauthorized party must measure it, and it does not know the element's Pauli basis. Measuring in the wrong basis collapses the state irreversibly. With a uniformly guessed basis the attacker is wrong 2/3 of the time and corrupts half of those, giving an expected mismatch rate of `intensity / 3`. Measured across 40 sessions per point:

| Intensity | Observed mismatch | Theory (`i/3`) |
|---|---|---|
| 0.25 | 0.0852 | 0.0833 |
| 0.50 | 0.1750 | 0.1667 |
| 0.75 | 0.2383 | 0.2500 |
| 1.00 | 0.3312 | 0.3333 |

This is the same physics BB84 uses to detect eavesdropping. The classical authorization check is retained as defence in depth, so a party that never touches the quantum channel is still rejected.

**Replay** is the honest exception: a replayed signature carries genuine, undisturbed states, so its quantum statistics are indistinguishable from a legitimate session by construction (measured anomaly score ~0.03, mismatch rate 0.0). It is detected by session-consistency checking on metadata. We state this plainly rather than claiming quantum detection for it.

## Known limitation: key-table reuse

Signature positions are drawn from a finite key table, so indices recur across messages and **every recurrence leaks that table entry** to an eavesdropper who can observe signatures. This is a property of finite-table QDS, and it is severe. Measured with `table_size=64`, `signature_length=16`:

| Observed signatures | Table entries recovered | Forgeries accepted |
|---|---|---|
| 0 (blind) | 0 / 64 | 0 / 60 |
| 5 | 48 / 64 | **60 / 60** |
| 25 | 64 / 64 | **60 / 60** |

**An attacker needs only five observed signatures to forge at will.** The mitigation is to bound the number of signatures per key — treat the key table as one-time material and rotate it well before `table_size / signature_length` messages, or size the table so that the expected index coverage stays negligible over the key's lifetime. This version does not enforce that bound automatically; it is the most important item for a follow-up.

## FAR / FRR: what we measure and what we claim

FAR and FRR are binomial rates estimated from a finite sample, so every figure below is reported with a confidence interval and its sample size. A bare point estimate is not a defensible claim: observing **zero** false accepts in 25 sessions is consistent with a true rate as high as **13.7%** (95% Clopper-Pearson). Reporting "FAR = 0.00%" from such a sample overstates the result by an order of magnitude.

Definitions, as implemented in `evaluation/metrics.py`:

* **FAR = FN / (FN + TP)** — attack sessions that slipped through. Denominator: attack sessions.
* **FRR = FP / (FP + TN)** — legitimate sessions wrongly denied. Denominator: legitimate sessions.

An earlier revision had these two swapped, which inverted every headline number: the figure published as "FAR — risk of an attack passing" was in fact the rate of turning away legitimate users. The swap also inverted the threshold optimiser's objective, causing it to select an operating point that let an attack through in order to avoid inconveniencing users, while claiming to minimise attack pass-through.

Current measured results (300 legitimate sessions, 1500 attack sessions, 95% Clopper-Pearson intervals):

| Metric | Default thresholds | Calibrated (Phase 6.5) |
|---|---|---|
| Detection rate | 92.20% (CI [90.73%, 93.51%]) | 88.80% |
| FAR — attack passes | 7.80% (CI [6.49%, 9.27%]) | 11.20% |
| FRR — legitimate denied | 17.00% (CI [12.93%, 21.74%]) | 7.33% |

We **do not** claim the False Acceptance Rate is contained or eliminated. Calibration trades the two error types against each other — tightening thresholds to bring FRR from 17.0% down to 7.3% raises FAR from 7.8% to 11.2%. Which operating point is correct depends on the deployment's relative cost of a missed attack versus a rejected honest user; `evaluation/threshold_optimization.py` selects one by minimising FAR subject to an FRR ceiling.

Sample sizes are set in the `evaluation` block of `config/quantum_config.yaml` and drive the width of every interval above.
