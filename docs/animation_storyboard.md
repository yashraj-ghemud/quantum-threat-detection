# QVeris — Animation Storyboard & Motion Script

> *"The Journey of a Signature."* One message, one quantum channel, one
> adversary, and the physics that catches her.

Every scene in the dashboard tells a part of the same story, and every step of
that story is a stage of the real pipeline in `src/session.py`. Nothing on
screen is decoration. If an object moves, it stands for something the engine
does.

---

## 1. Visual language

| Token | Hex | Meaning in the story |
|---|---|---|
| Mist (background) | `#EAEDF7` | the quantum vacuum: calm, light, never pure white |
| Surface | `#F3F4FB` | cards and panels |
| Ink | `#1E2440` | text |
| Lavender | `#8C84F0` | **Alice**, the signer, and her secret key |
| Mint | `#4FC3A1` | **Bob**, the verifier. Also "verified" and "secure" |
| Sky | `#6FA8F0` | the quantum channel, qubits, Bell pairs |
| Gold | `#E8B860` | classical bits (the 2 teleportation correction bits) |
| Peach | `#F4A77A` | SUSPICIOUS |
| Coral | `#E8697A` | **Eve**, the adversary. Also THREAT |

Materials follow the same logic:

* **Glass** (physically based, transmissive) for anything quantum: Bloch
  spheres, qubits, the fibre. A quantum state is fragile and see-through.
* **Matte ceramic** for classical infrastructure: stations and pedestals.
* **Obsidian** (dark, metallic, coral cracks) for Eve, the only dark object
  in a light world.

## 2. Motion principles

1. **Physics before keyframes.** Motion comes from springs, damping, gravity
   and inertia (critically damped springs for UI, ballistic arcs with
   restitution for debris). Nothing moves linearly.
2. **A camera with a person behind it.** Every shot has a subtle hand-held
   drift (layered low-frequency noise). Cuts are replaced by dollies, cranes
   and orbits. Impacts get a decaying camera shake. Entanglement uses a
   dolly-zoom (FOV and distance change together).
3. **Speed follows drama.** Calm chapters are slow (ease-in-out), reveals
   overshoot (back-out easing), and the attack is fast and jittery.
4. **Scrubbable.** The whole film is a pure function of story time `T`. The
   intro plays `T` on a clock. The landing page drives `T` from scroll. The
   same frame appears either way, so the landing page *is* the film.

## 3. The film: intro sequence (≈ 30 s, skippable)

| # | Time | Chapter | On screen | Camera | Pipeline stage |
|---|---|---|---|---|---|
| 0 | 0.0–3.5 | **PROLOGUE — A message is born** | Pastel dust drifts. A glass card condenses from particles; *"transfer 100 to bob"* types itself onto it. | Slow push-in from a wide, soft-focus drift | `MESSAGE` |
| I | 3.5–7.0 | **BIND** | The text lifts off as 64 hex glyphs, which orbit as a ring, then collapse into a single glowing digest core. | 90° orbit around the card | `SHA-256` message binding |
| II | 7.0–11.0 | **SIGN** | The core bursts into six Pauli-eigenstate qubits (mini Bloch spheres). Each arrow springs to ±X, ±Y, ±Z with overshoot. | Crane up to a top-down reveal | QDS signature → Pauli eigenstates |
| III | 11.0–15.0 | **ENTANGLE** | Alice's and Bob's stations rise from the floor. A Bell pair \|Φ+⟩ is born mid-channel and splits, joined by a double helix of light. | Wide pull-back with a dolly-zoom | Bell-state entanglement |
| IV | 15.0–19.5 | **TELEPORT** | Alice's qubit flashes (Bell measurement) and dissolves. Two gold classical bits arc overhead. X and Z gates flash at Bob and the state reappears there. | Chase cam flies along the fibre | Teleportation + Pauli correction |
| V | 19.5–23.0 | **INTRUSION** | The world tints coral. Eve rises beneath the channel and her tendrils grip the fibre. Pulses turn coral, the screen glitches, the camera shakes. | Handheld, fast, low angle | Attack injection |
| VI | 23.0–27.0 | **DETECT** | Bob measures: histogram bars rise, and the divergence gauge climbs past τ. A hexagonal shield snaps shut and Eve shatters into shards that fall, bounce and settle. | Locked-off, then a push-in on impact | Measurement statistics → threat detection |
| — | 27.0–31.0 | **EPILOGUE — QVERIS** | Pull back to the whole network. Particles form the **QVERIS** wordmark; real metrics from the canonical run fade in. The film docks into the landing page. | Crane back and up | System secured |

**Hand-off:** when the film ends, the full-screen frame animates down into the
hero stage of the page (FLIP transition). No cut, no reload. It is the same
WebGL scene, now driven by scroll.

## 4. The website: scroll story

The hero stage is sticky. Scrolling through it scrubs the film chapter by
chapter, with a text panel for each chapter explaining the real mechanism:

1. *Bind:* SHA-256 digest of the message bytes.
2. *Sign:* the digest indexes Alice's secret key table of Pauli eigenstates.
3. *Entangle and teleport:* the verifier's public key is the set of states it
   **received**, not a list it was handed.
4. *Intrusion:* forgery, impersonation, replay, interception, channel tampering.
5. *Detect:* Shannon entropy, Hellinger distance, KL divergence, and a
   percentile-calibrated threshold. No ML.

Interaction: the camera leans toward the cursor (parallax). Hovering an object
highlights it and names it. Clicking an object sends out a shockwave and a
spring pulse. "▶ Watch the film" replays the cinematic full-screen.

### Whole-site micro-interactions

* **Cursor:** a dot plus a spring-lagged ring. The ring grows over interactive
  elements, squashes in the direction of travel, and bursts into pastel
  "quantum" particles on click.
* **Magnetic buttons** lean toward the cursor. A ripple spreads from the click
  point.
* **3D tilt cards:** KPI metrics tilt toward the cursor, with a moving glare.
* **Scroll reveals:** blocks rise in with a slight 3D rotation as they enter.
  A gradient progress bar tracks the scroll.
* **Ambient background:** slow-drifting pastel aurora blobs.
* All motion respects `prefers-reduced-motion`.

## 5. Attack lab: one short film per attack (≈ 10 s, replayable)

Driven by the **real** `AttackScenarioResult` / `SessionResult`. The verdict
beat always shows what the detector actually decided: a missed attack is shown
as missed.

| Attack | Story beat | Physical meaning |
|---|---|---|
| FORGERY | Eve forges a counterfeit card. Her pulses carry **full-length arrows pointing the wrong way**. | substituted *pure* eigenstates |
| IMPERSONATION | Eve's station wears Alice's lavender skin, and the mask flickers. The signature is made with a different key. | wrong signing key vs public key |
| REPLAY | A ghost copy of an old packet trails the real one, stamped with a duplicate session nonce. | classical session-consistency check |
| UNAUTHORIZED_VERIFICATION | Eve taps the fibre, measures in the wrong basis and re-sends. The lock refuses her. | intercept-resend + access control |
| CHANNEL_MANIPULATION | The fibre shivers with amplitude ∝ intensity, and the pulses blur. Bob's arrows **shrink**. | depolarizing noise lowers purity |

Verdict: **THREAT** → the shield closes and Eve shatters. **SUSPICIOUS** →
an amber ring and Eve is pushed back. **NORMAL / LEGITIMATE** → a green seal
(and for an attack, "passed undetected", said honestly).

The HUD gauges show the real anomaly score against the real threshold, the
mismatch rate and the verification score. Drag to orbit, scroll to zoom, and
click ▶ to replay.

---

## 6. Remaster v2: live, data-driven scenes

Every panel gets its **own** scene, and every scene reacts to the widgets
**without reloading**. A tiny zero-height "data bus" component
(`_web.publish`) posts the current values to the page each run. The
long-lived WebGL scene polls the bus and *morphs* (springs) to the new state,
so dragging a slider visibly reshapes the world instead of restarting it.

Each scene has two layers:

* **Configured (theory).** As soon as a value changes, the scene shows what
  the attack or channel *does* according to the code, with the exact numbers
  the code uses. Nothing is presented as measured.
* **Measured (film).** When a run completes, a film replays the real result:
  per-element outcomes, shot counts, the anomaly score against the real
  thresholds, the real evidence lines and the real verdict.

### 6.1 Attack Lab (Attack Simulation and Live Session)

| Control | What changes on screen | Source of truth |
|---|---|---|
| attack type | Eve's tactic: substitution (forgery), Mallory's branch fibre (impersonation), ghost stream + nonce/age tags (replay), wrong-basis measurement (interception), fibre tremor + fog (channel) | `src/attacks/*.py` |
| intensity | how many of the n qubits are hit, `k = round(n·I)`; Eve's size, spikes, tendrils and speed; noise amplitude; replay staleness and `seq offset = max(1, int(10·I))`; cross-message replay when `I ≥ 0.5` | forgery / impersonation / interception / replay code |
| signature length | number of qubits in the stream and slots in Bob's measurement rack (shown up to 24; above that, each slot stands for several elements) | |
| shots | particle density of the measurement "rain" | |
| message | the card text and its real SHA-256 digest | `hashlib.sha256` |

**Measured film (about 14 s):** session start → the qubit stream carries the
real per-element results → shots rain into each slot's |0⟩/|1⟩ tubes with the
real counts → the anomaly gauge climbs to the real score, with the real
thresholds as notches → the evidence lines type out → verdict.

**Verdicts, and the endings they lead to:**

* **THREAT: the capture.** Every mismatched slot fires a beam at the
  adversary (the mismatches *are* the evidence) → a containment cage closes
  → cracks glow across her body in slow motion → implosion → detonation
  (flash, light pillar, floor shockwave, obsidian shards and embers) → time
  freezes with the shards hanging in the air → the shards are pulled in a
  spiral into Bob's orb ("evidence captured") → an **incident report** card
  materialises with the real numbers.
* **SUSPICIOUS:** beams tag Eve with an amber beacon, a repulse wave pushes
  her away, and a "flagged for review" card appears.
* **Missed attack:** Eve glitches out and escapes. The card says honestly
  that the attack passed and how many elements it affected.
* **Legitimate session:** the rack's streams converge on the message card and a
  mint **VERIFIED** seal slams onto it, followed by a certificate card.

### 6.2 Quantum Noise: "Channel Anatomy"

Alice's and Bob's Bloch spheres, with the input state and the **measured**
Bloch vector of Bob's real density matrix (`b = Tr(ρσ)`). Each noise model
has its own physics on the fibre: X-gate strikes (bit flip), Z-gate spins
(phase flip), fog and shrinkage (depolarizing), energy leaking out and the
vector sagging to |0⟩ (amplitude damping). A wireframe ellipsoid on Bob's
sphere shows where the channel maps *every* state, and it deforms live with p.
The panel recomputes on every change (cached), so the sliders drive it
directly.

### 6.3 Live Verification: "Signature Constellation"

The n signature elements orbit as a ring of qubits with their real
eigenstates. A scanner sweeps the ring, collapsing each element in its basis
and showing the real p(+1) and match. The central gauge fills to the real
verification score, and the threshold τ from the slider is a notch that
springs to its new value. Verification re-runs on every change, so the
gate visibly opens (accepted) or locks (rejected) as τ moves.

### 6.4 Story transitions

* **Film → page: "collapse and big bang".** The finished world implodes
  into a point of light, flashes, then expands out into the landing
  composition while the headline assembles letter by letter in 3D.
* **Epilogue:** the protected network blooms. Distant nodes across the
  world light up and are linked by new channels, around the wordmark.
* **Story → dashboard: "the dive".** The last stretch of scroll flies the
  camera into Bob's orb. Mint light fills the frame and fades into the
  dashboard, which begins exactly where the story ends.

### 6.5 v3: the QVERIS reveal and the way into the dashboard

The epilogue (T 27–34.5) is now a reveal sequence:

1. **Vortex (27.8–29.15).** All the world's dust spirals into a point above
   the network while three rings collapse inward. The camera orbits fast.
2. **Singularity (28.85–29.35, slow motion).** The camera rushes in on a wide
   lens, the light condenses, and bloom rises.
3. **Detonation (29.2).** A white blast ring, a floor shockwave, a camera
   shake, and the dust is blasted outward.
4. **The forge (29.25–30.55).** Six pearlescent, iridescent 3D letters are
   thrown out of the blast, then pulled back along curves. Each one *slams*
   into its mark (overshoot, squash, edge flash, its own shockwave, sparks
   and a camera kick), staggered 0.22 s apart.
5. **Light sweep and hero pose (31–34.5).** A moving light glints across the
   letters, an underline beam draws, the subtitle tracks in, the protected
   network lights up around the name, and the real metrics appear.

**Go to dashboard.** A button at the top of the landing page, and one at the
end of the film. It plays "the dive" (the camera flies into Bob's orb under
mint light) and lands the page on the dashboard. A floating "Back to the
story" pill returns to the top.

**Smoothness.** No per-frame geometry allocation anywhere: the fibre tremor
deforms the tube in place, and Eve's tendrils are instanced beads. The
attack film's slow motion eases in and out on a spring. The station orbs use
layered glass instead of the transmission pass, which saves a full extra
scene render every frame. Hovering a rack slot or a constellation element
shows its real measured values.
