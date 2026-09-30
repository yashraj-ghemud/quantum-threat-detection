# QVeris Dashboard

An interactive, real-time view of the Quantum-Inspired Cyber Threat Detection
system: a cinematic 3D story of how a signature is protected, followed by the
live engine (verification, attacks, threshold analytics, quantum noise).

## Setup
```bash
pip install streamlit plotly
```

## Running
From the project root (so `.streamlit/config.toml` applies the light theme):
```bash
streamlit run dashboard/app.py
```

A browser with WebGL 2 is required. Three.js is loaded from the jsDelivr CDN.

## The story
The motion design follows one storyboard, `docs/animation_storyboard.md`:
*"The Journey of a Signature"*: Bind, Sign, Entangle, Teleport, Intrusion,
Detect. Every beat is a real pipeline stage.

- **Intro film.** Plays full-screen on the first load of a browser session
  (skip with `Esc`). It uses a time-warped clock (slow motion on the Bell
  measurement and the shatter), a spline camera with hand-held drift and
  impact shake, and physically based glass, ceramic and obsidian materials.
- **Scroll hero.** When the film ends, the same WebGL scene docks into the
  page and scrolling scrubs the story, chapter by chapter. Hover objects to
  name them, click them for a spring pulse, or press "Watch the film" to
  replay the film.
- **Attack Lab.** Each attack or live session replays as a ~10 s film driven
  by the real result: anomaly score against the calibrated thresholds, the
  mismatch rate and per-element outcomes. The verdict shows the detector's
  actual decision, including a miss.
- **Live, data-driven scenes (v2).** Each panel has its own persistent
  scene that morphs when a widget changes, with no reload:
  *Attack Lab* (Attack Simulation and Live Session) shows the configured attack
  using the exact rules in `src/attacks/*.py`, then plays the measured film
  (per-element outcomes, shot rain, the real anomaly score against τ, the
  evidence, and the capture ending with an incident report).
  *Channel Anatomy* (Quantum Noise) shows Bob's real density matrix and the
  channel ellipsoid. *Signature Constellation* (Live Verification) scans the
  real element results against a live τ and a real `ForgeryAttack`.
- **Page motion.** Spring-physics cursor with click sparks, magnetic buttons,
  ripples, 3D tilt KPI cards, scroll reveals and a progress bar. All of it
  is disabled under `prefers-reduced-motion`.

## Architecture
- **`app.py`**: entry point. Loads `web/theme.css` and composes the page.
- **`components/`**: Streamlit sections.
    - **`intro_simulation.py`**: intro film and scroll hero (`web/story.*`).
    - **`attack_simulation_3d.py`**: Attack Lab scene (`web/attack_lab.*`).
    - **`live_session.py`**: real end-to-end session, plus its 3D replay.
    - **`metrics.py`**, **`charts.py`**, **`quantum_view.py`**,
      **`bloch_view.py`**, **`attack_panel.py`**, **`security_panel.py`**.
    - **`_web.py`**: inlines a scene (template, shared `core.js`, entry
      script and JSON data) into one `srcdoc` document.
      `publish()` is the data bus: a zero-height component that posts fresh
      values to `window.__qvBus`. Scenes stay static, so Streamlit never
      reloads their WebGL iframe.
- **`web/`**: front-end sources.
    - **`core.js`**: stage (PBR lighting, IBL, soft shadows, bloom, adaptive
      quality), models, particles, springs and camera helpers.
    - **`story.js` / `story.html`**: the film and the scroll hero.
    - **`attack_lab.js` / `attack_lab.html`**: the attack films.
    - **`noise_lab.js`**, **`verify_lab.js`** (with the shared `panel.html`): the Quantum Noise and Live Verification scenes.
    - **`fx.js`**: page interaction layer, injected once into the host page.
    - **`theme.css`**: the light pastel theme. Colours carry meaning:
      lavender = Alice, mint = Bob/verified, sky = channel, coral = Eve/threat.

## Limitations
- No quantum hardware is used; simulations run on `qiskit_aer`.
- The 3D scenes step down their quality automatically on slow GPUs.
- Real-time simulations may use a lot of memory at very high session depths.
