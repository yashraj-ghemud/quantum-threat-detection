# Cyber Attack Model

The framework evaluates protocol integrity against five attack vectors. For
each we state the adversary's *knowledge*, what the attack actually does to
the data, and how it is detected — with the mechanism that genuinely fires,
not the one that sounds most quantum.

Detection rates below come from `experiments/results/security_summary.csv`
(300 legitimate + 1500 attack sessions, swept across intensities 0.1–1.0).

## Adversary knowledge model

Unless stated otherwise the adversary holds everything genuinely public: the
published `config/quantum_config.yaml` (including `random_seed: 42`), the
signer's public-key **fingerprint**, the message, and the public index
derivation. It does **not** hold the private seed. Because the key table is
HMAC-derived, none of that public material narrows the search — which is the
property the evaluation exists to demonstrate.

## 1. Forgery Attack

**Vector**: An adversary without the private key attempts to produce states
that will verify.

**Mechanics** — three models, in increasing strength:

| Strategy | Adversary knowledge | Result |
|---|---|---|
| `random` | none | verification score ≈ 0.197, 0/60 accepted |
| `key_ignorant` | full public config + fingerprint | ≈ 0.207, 0/60 accepted |
| `learned` | has observed previous signatures | **succeeds** — see below |

**Detection**: Guessed states mismatch the verifier's key table, producing a
large statistical deviation. Detection rate **88.7%** across the intensity
sweep; at full intensity it is 100%.

**The `learned` case is the real threat.** Signature positions are drawn from
a finite key table, so indices recur across messages and every recurrence
leaks that table entry. With `table_size=64`, `signature_length=16`:

| Observed signatures | Table recovered | Forgeries accepted |
|---|---|---|
| 5 | 48/64 | 60/60 |
| 25 | 64/64 | 60/60 |

Five observed signatures are enough to forge at will. Mitigation is to bound
signatures per key; see `docs/security_model.md`.

## 2. Session Impersonation

**Vector**: An adversary signs as somebody else.

**Mechanics** — two models:
- `own_seed`: derives a state sequence from an unrelated RNG seed.
- `own_keypair`: runs the real key-generation protocol and signs the victim's
  message with a **perfectly valid key pair of its own**. The signature is
  internally self-consistent and would verify against the attacker's own
  public key.

**Detection**: The `key_id` carried by the signature does not match the public
key the verifier holds, and the states come from a different table, so the
measured match rate collapses. Detection rate **89.3%** across the sweep.
The `own_keypair` model is the meaningful test: it confirms that holding *a*
valid key confers no ability to impersonate *another* signer.

## 3. Replay Attack

**Vector**: A valid signature is captured and retransmitted to authorise a
second time.

**Mechanics**: Re-sends genuine, previously-valid states with stale session
metadata.

**Detection**: **Classical session-consistency checking** — sequence number
and staleness — not quantum statistics. Detection rate **100%**.

A replayed signature carries authentic, undisturbed quantum states, so its
measurement statistics are *indistinguishable from a legitimate session by
construction*: measured anomaly score ≈ 0.03 with a mismatch rate of 0.0.
Earlier documentation claimed replay produced "a sudden and definitive
statistical anomaly" because its deviation was near zero; that is backwards.
Near-zero deviation is exactly what a *legitimate* session looks like, which
is why replay must be caught on metadata.

## 4. Unauthorized Verification

**Vector**: A party without authorization attempts to read and verify a
signature.

**Mechanics**: To read an element the attacker must **measure** it, and it
does not know that element's Pauli basis — the basis is key material.
Measuring in a guessed basis collapses the state onto an eigenstate of the
*wrong* basis, and no-cloning means the original cannot be restored.

**Detection** — two independent layers:

1. **Quantum (primary)**: when the legitimate verifier later measures in the
   correct basis, the corrupted elements return coin flips. A uniformly
   guessed basis is wrong 2/3 of the time and corrupts half of those, giving
   an expected mismatch rate of `intensity / 3`. Measured: 0.0852 / 0.1750 /
   0.2383 / 0.3312 at intensities 0.25 / 0.50 / 0.75 / 1.00 against theory of
   0.0833 / 0.1667 / 0.2500 / 0.3333. This is the BB84 eavesdropper-detection
   mechanism, and it yields a mean anomaly score of ≈ 0.27 (classified
   `THREAT`).
2. **Classical access control (defence in depth)**: the authorization flag is
   checked independently, so an attacker that never touches the quantum
   channel is still rejected.

Detection rate **100%**. Note that an earlier revision implemented layer 2
only, which is why this category previously reported an anomaly score of
exactly `0.0000` — detected, but not by the quantum mechanism the project
claims. Both layers now run.

## 5. Channel Manipulation (Eavesdropping / MITM)

**Vector**: An adversary interferes with the quantum channel between signer
and verifier.

**Mechanics**: In `mode='quantum_channel'` the states are transmitted through
the **real** 3-qubit teleportation circuit on Aer while the adversary injects
a Qiskit noise model onto the channel qubits. The verifier receives whatever
genuinely came out the far end — a mixed state, sampled from its eigen-ensemble
so the degradation is preserved rather than idealised away. The analytic
`depolarizing` / `dephasing` / `both` modes remain available for fast sweeps.

**Detection**: Channel noise shrinks the Bloch vector, which shows up as
elevated mismatch and a fidelity drop. Measured on the live channel:

| Injected noise `p` | Mean fidelity | Verification score | Accepted |
|---|---|---|---|
| 0.00 | 1.0000 | 1.0000 | 12/12 |
| 0.05 | 0.9362 | 0.9531 | 12/12 |
| 0.15 | 0.8264 | 0.7812 | 9/12 |
| 0.35 | 0.6677 | 0.6562 | 5/12 |
| 0.60 | 0.5567 | 0.5521 | 1/12 |

Detection rate **83.0%** across the sweep — the weakest of the five, because
low-intensity channel tampering is genuinely hard to separate from background
hardware noise. Phase 6.5 finds detection becomes reliable (≥90%) at
intensity ≥ 0.50. This is a limitation, not a solved problem.
