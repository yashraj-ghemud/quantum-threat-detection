# QVeris Sentinel — Frontend Plan (design · motion · pages · data · mobile)

> Companion to [`00_MASTER_PLAN.md`](00_MASTER_PLAN.md) and [`01_BACKEND_PLAN.md`](01_BACKEND_PLAN.md).
> Every number the UI shows comes from the backend API or WebSocket. The frontend computes presentation
> only (layout, animation, formatting). The one exception is Playground gate rotations, which are exact 2×2 algebra.

---

## Table of contents

0. [Vision and principles](#0-vision-and-principles)
1. [Technology stack](#1-technology-stack)
2. [Information architecture](#2-information-architecture)
3. [Project structure](#3-project-structure)
4. [Design system](#4-design-system)
5. [Motion system](#5-motion-system)
6. [Global experiences](#6-global-experiences)
7. [App shell](#7-app-shell)
8. [Component library](#8-component-library)
9. [Data-visualisation kit](#9-data-visualisation-kit)
10. [3D scene kit](#10-3d-scene-kit)
11. [Pages](#11-pages)
12. [Data layer](#12-data-layer)
13. [Mobile strategy](#13-mobile-strategy)
14. [Accessibility](#14-accessibility)
15. [Performance](#15-performance)
16. [Resilience and error handling](#16-resilience-and-error-handling)
17. [Testing and visual review](#17-testing-and-visual-review)
18. [Build and backend integration](#18-build-and-backend-integration)
19. [Implementation order and acceptance](#19-implementation-order-and-acceptance)
20. [Copy and tone](#20-copy-and-tone)

---

## 0. Vision and principles

**"A mission-control room for quantum signatures."** The UI should feel like standing inside the physics: entangled pairs flowing along fibres, qubits collapsing into outcomes, an adversary's disturbance bending the Bloch sphere, and the detector's evidence cascading into a verdict. The spectacle is always **bound to real data**: an animation that moves always stands for something the engine did.

| # | Principle | Rule |
|---|---|---|
| F1 | **Truthful motion** | Every animated quantity is driven by an API/WS value. No decorative counters, and no numbers invented for placeholder. |
| F2 | **Empty is honest** | With no data, show an empty state that names what is missing and offers the action that creates it ("Start live traffic", "Run evaluation"). |
| F3 | **Explain everything** | Every metric has an ⓘ that opens the Explain drawer (what, how computed, why it matters, formula). |
| F4 | **Delight at 60 fps, degrade gracefully** | Quality tiers, reduced motion, WebGL fallback, pause when off-screen. |
| F5 | **Mobile is first-class** | Every page is fully usable at 360 px wide with touch. No hover-only information. |
| F6 | **Semantic colour** | Hue means identity or state, consistently (§4.1). A colour is never the *only* carrier of meaning. |

---

## 1. Technology stack

| Concern | Choice (version at plan time) | Why |
|---|---|---|
| Framework | **React 19.x** + **TypeScript** (5.9 line; 7.x if the toolchain is stable) | Ecosystem; r3f; concurrent rendering |
| Build | **Vite 8** + `@vitejs/plugin-react` 6 | Fast HMR, code-splitting, proxy |
| Routing | **react-router-dom 7** (data router, lazy routes) | Nested layouts, lazy chunks |
| Server state | **@tanstack/react-query 5** | Caching, dedupe, invalidation from WS |
| Client state | **zustand 5** | Tiny, selector-based, usable outside React (WS) |
| Animation | **motion 13** (`motion/react`) | Springs, layout animations, gestures, AnimatePresence |
| 3D | **three 0.186**, **@react-three/fiber 9**, **@react-three/drei 10**, **@react-three/postprocessing 3** | Declarative scenes, helpers, bloom |
| Charts | **d3-scale, d3-shape, d3-array, d3-format, d3-interpolate** (modular) + custom SVG | Full creative control, small bundle |
| Math | **KaTeX 0.18** (lazy) | Formulas on the Method page and in the Explain drawer |
| Icons | **lucide-react** + custom SVG glyphs (qubit, Bloch, entangle, teleport, ledger) | Tree-shakable |
| Fonts | `@fontsource-variable/inter`, `@fontsource/space-grotesk`, `@fontsource/jetbrains-mono` | Self-hosted; no external font CDN at run time |
| Types from backend | **openapi-typescript 7** | Generated from the server's OpenAPI; no drift |
| Tests | **vitest 5**, **@playwright/test** (pre-installed Chromium) | Unit + E2E + screenshots |
| Lint/format | eslint (typescript-eslint, react-hooks) + prettier | Consistency |

No CSS framework. Hand-written CSS with custom properties (`src/styles/`) gives total control of the look and a small footprint. CSS Modules are used for component-scoped styles.

---

## 2. Information architecture

| Route | Page | Nav label | Icon | Purpose |
|---|---|---|---|---|
| `/` | Overview | Overview | orbit | Cinematic story + live proof |
| `/command` | Command Center | Command | radar | Live SOC: network, feed, threat level, controls |
| `/studio` | Signature Studio | Studio | pen-tool | Sign & verify a message, watch every stage |
| `/attack-lab` | Attack Lab | Attack Lab | zap / skull | Launch any of 17 attacks, see the physics and the evidence |
| `/playground` | Quantum Playground | Playground | atom | Bloch sphere, gates, channels, teleportation, measurement |
| `/analytics` | Analytics | Analytics | line-chart | Evaluation jobs and interactive theory |
| `/ledger` | Ledger | Ledger | blocks | Hash-chained audit ledger, Merkle trees, integrity |
| `/incidents` | Incidents | Incidents | shield-alert | Incident queue |
| `/incidents/:id` | Incident detail | — | — | Forensics + response |
| `/sessions/:id` | Session detail | — | — | Full report of one distribution or signature |
| `/method` | Method | Method | book-open | The science, formulas bound to live parameters |
| `*` | Not found | — | — | "State collapsed" 404 |

Deep links carry state via query parameters:
* `/attack-lab?attack=channel.dephase&intensity=0.4`
* `/studio?group=g-alice&preset=high`
* `/analytics#forgery`

---

## 3. Project structure

```
web/
  index.html                  meta, theme-color, preload fonts, #root, <noscript>
  vite.config.ts              proxy /api,/ws → :8000; manualChunks (three, charts, math)
  tsconfig.json · eslint.config.js · .prettierrc
  playwright.config.ts · vitest.config.ts
  public/  favicon.svg · manifest.webmanifest · og.png (generated at build from SVG)
  src/
    main.tsx                  providers (QueryClient, Router), fonts, styles
    app/
      App.tsx                 layout route: Shell + Outlet + global overlays
      routes.tsx              route table (lazy)
      Shell.tsx               TopBar, NavRail, BottomNav, content frame
      Boot.tsx                boot sequence overlay
      Backdrop.tsx            quantum field (WebGL) or CSS fallback
      Cursor.tsx              custom cursor (pointer: fine)
      PageTransition.tsx      clip-path tunnelling transitions
      CommandPalette.tsx
      Toasts.tsx
      ExplainDrawer.tsx
      SettingsSheet.tsx
      ErrorBoundary.tsx
    api/
      client.ts               fetch wrapper, ApiError, timeouts, retries
      openapi.json            dumped from server (checked in)
      schema.d.ts             generated types (checked in)
      models.ts               friendly aliases over schema.d.ts
      endpoints.ts            typed calls per route
      queryKeys.ts
    stream/
      socket.ts               WS manager (backoff, heartbeat, subscribe)
      router.ts               event → store/cache updates
    state/
      connection.ts live.ts prefs.ts ui.ts jobs.ts sceneEvents.ts
    lib/
      quantum.ts              Bloch math, gate rotations, affine maps (exact)
      format.ts               numbers, sci-notation, durations, percentages + CIs, relative time
      fuzzy.ts                command palette scoring
      color.ts                semantic colour lookups, severity, basis colours
      audio.ts                WebAudio synth
      haptics.ts
      explanations.tsx        Explain-drawer content registry (static educational text)
      useMeasure.ts useInView.ts useReducedMotion.ts useQuality.ts useInterval.ts useHotkeys.ts
    components/               primitives (§8)
    charts/                   visual kit (§9)
    three/                    scene kit (§10)
    features/
      overview/ command/ studio/ attack-lab/ playground/ analytics/ ledger/ incidents/ sessions/ method/
    styles/
      tokens.css              design tokens (dark + light)
      base.css                reset, typography, focus, scrollbars, selection
      utilities.css           layout helpers (stack, cluster, grid)
      glass.css               glass/panel materials, noise overlay
  e2e/
    smoke.spec.ts flows.spec.ts mobile.spec.ts
    global-setup.ts           starts backend on a temp data dir
```

---

## 4. Design system

### 4.1 Colour: "Quantum Noir" (dark, default) and "Daylight Lab" (light)

The semantics carry over from the v1 storyboard: lavender = signer, mint = verified, sky = quantum channel, gold = classical bits, coral = adversary/threat.

| Token | Dark | Light | Meaning |
|---|---|---|---|
| `--bg-void` | `#03040A` | `#E6EAF6` | Deepest background |
| `--bg-0` | `#060816` | `#EEF1FA` | Page |
| `--bg-1` | `#0A0E20` | `#F5F7FD` | Raised areas |
| `--bg-2` | `#10152C` | `#FFFFFF` | Panels (opaque fallback) |
| `--bg-3` | `#171D3A` | `#F0F3FB` | Inputs, wells |
| `--glass-1` | `rgba(16,21,44,.55)` | `rgba(255,255,255,.62)` | Glass panels |
| `--glass-2` | `rgba(22,28,58,.78)` | `rgba(255,255,255,.82)` | Popovers, drawers |
| `--line` | `rgba(148,163,255,.10)` | `rgba(30,40,90,.10)` | Hairlines |
| `--line-strong` | `rgba(148,163,255,.22)` | `rgba(30,40,90,.20)` | Borders |
| `--text-0` | `#F2F4FF` | `#121833` | Primary text |
| `--text-1` | `#C3CAEB` | `#394266` | Secondary |
| `--text-2` | `#8A93BD` | `#5E678F` | Tertiary / labels |
| `--text-3` | `#5B6390` | `#8C94B8` | Disabled / ticks |
| `--alice` | `#A48CFF` | `#6A4DF0` | Signer Alice, private key |
| `--diana` | `#FF8AD8` | `#C23A9A` | Signer Diana |
| `--bob` | `#2EF2C0` | `#00997A` | Verifier Bob |
| `--charlie` | `#8CF26A` | `#3F8F1F` | Verifier Charlie |
| `--erin` | `#6FD6FF` | `#0B7DB3` | Verifier Erin |
| `--quantum` | `#57A9FF` | `#1F6FD6` | Qubits, fibres, Bell pairs |
| `--classical` | `#FFC75A` | `#B07A10` | Classical bits, packets, ledger |
| `--ok` | `#2EF2C0` | `#00997A` | ACCEPTED / CERTIFIED |
| `--warn` | `#FF9F5A` | `#C4621A` | SUSPICIOUS / degraded |
| `--threat` | `#FF4D6D` | `#D52B4C` | REJECTED / COMPROMISED / Eve |
| `--mallory` | `#FF7A3D` | `#C4501A` | Rogue insider signer |
| `--basis-x` | `#36C5F0` | `#0E86B0` | X basis |
| `--basis-y` | `#F15BB5` | `#B8237E` | Y basis |
| `--basis-z` | `#FEE440` | `#9C8500` | Z basis |
| `--sev-none` | `#8A93BD` | `#5E678F` | |
| `--sev-low` | `#7AA2FF` | `#2D5BD1` | |
| `--sev-medium` | `#FFC75A` | `#B07A10` | |
| `--sev-high` | `#FF9F5A` | `#C4621A` | |
| `--sev-critical` | `#FF4D6D` | `#D52B4C` | |

Each semantic colour has `-soft` (14% alpha fill), `-glow` (box-shadow `0 0 24px color / .35`) and `-ink` (text on the colour, AA-checked) variants, generated in `tokens.css`.

Theme selection: `data-theme="dark|light"` on `<html>`, defaulting to `prefers-color-scheme`. `body` always has an explicit background.

### 4.2 Typography

| Style | Font | Size (desktop / mobile) | Line height | Weight | Tracking |
|---|---|---|---|---|---|
| `display-xl` | Space Grotesk | clamp(52px, 7.2vw, 112px) | 0.94 | 700 | −0.035em |
| `display` | Space Grotesk | clamp(36px, 4.6vw, 64px) | 1.0 | 700 | −0.03em |
| `h1` | Space Grotesk | 36 / 28 | 1.1 | 650 | −0.02em |
| `h2` | Space Grotesk | 28 / 22 | 1.15 | 600 | −0.015em |
| `h3` | Space Grotesk | 22 / 19 | 1.2 | 600 | −0.01em |
| `h4` | Inter | 17 / 16 | 1.3 | 600 | 0 |
| `body` | Inter | 15 / 16 | 1.55 | 400 | 0 |
| `body-sm` | Inter | 13 / 14 | 1.5 | 400 | 0 |
| `kicker` | Inter | 11 / 11 | 1.2 | 600 | 0.14em, uppercase |
| `num` | JetBrains Mono | inherits | — | 500 | tabular-nums |
| `mono` | JetBrains Mono | 13 / 12 | 1.5 | 400 | 0 |

Numbers always use `font-variant-numeric: tabular-nums` so count-ups do not jitter.

### 4.3 Space, radius, elevation, layout

* Spacing (4-pt): `--s-1`…`--s-12` = 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96.
* Radius: `--r-xs 6`, `--r-sm 10`, `--r-md 14`, `--r-lg 20`, `--r-xl 28`, `--r-pill 999`.
* **Glass panel**:
  * background `--glass-1`, `backdrop-filter: blur(18px) saturate(140%)`;
  * a 1 px gradient border (`linear-gradient(135deg, var(--line-strong), transparent 40%, var(--line))` via a mask trick);
  * inner top highlight `inset 0 1px 0 rgba(255,255,255,.05)`;
  * noise overlay (SVG turbulence, 3.5% opacity).
  Browsers without `backdrop-filter` fall back to `--bg-2`.
* **Glow elevation**: `--glow-1` (subtle), `--glow-2` (focus), `--glow-3` (hero), tinted by a context colour through `--glow-color`.
* Breakpoints: `xs <480`, `sm ≥480`, `md ≥768`, `lg ≥1024`, `xl ≥1280`, `2xl ≥1600`.
* Content max width 1680 px. Gutters: 16 (mobile), 24 (md), 32 (xl).
* Z-index scale: backdrop 0, content 10, sticky 20, nav 30, drawer 40, modal 50, toast 60, cursor 70, boot 80.

### 4.4 Iconography and imagery

* lucide at 1.6 px stroke, 20/24 px.
* Custom glyphs share the grid: `QubitLogo` (sphere + orbit + shield notch), `BlochGlyph`, `EntangleGlyph` (two linked loops), `TeleportGlyph`, `LedgerGlyph`, `EveGlyph` (cracked diamond), `KeyPairGlyph` (Lamport twin keys).
* No stock imagery. All illustration is generative (SVG or WebGL).

---

## 5. Motion system

### 5.1 Tokens

| Token | Value | Use |
|---|---|---|
| `--dur-instant` | 80 ms | Press feedback |
| `--dur-fast` | 160 ms | Hovers, small fades |
| `--dur-base` | 260 ms | Most UI transitions |
| `--dur-slow` | 420 ms | Panels, drawers |
| `--dur-slower` | 700 ms | Page reveal |
| `--dur-cinematic` | 1200 ms | Hero moments |
| `--ease-out` | `cubic-bezier(.22,1,.36,1)` | Entrances |
| `--ease-in-out` | `cubic-bezier(.65,0,.35,1)` | Morphs |
| `--ease-in` | `cubic-bezier(.55,0,1,.45)` | Exits |
| spring `snappy` | stiffness 520, damping 34, mass .8 | Toggles, buttons |
| spring `smooth` | 260 / 30 | Panels, layout |
| spring `gentle` | 140 / 22 | Numbers, needles |
| spring `wobbly` | 180 / 12 | Playful reveals (stamps) |

### 5.2 Choreography rules

1. **Enter**: from `y: 12px`, `opacity: 0`, `filter: blur(6px)` → rest, `--dur-base`, `--ease-out`.
2. **Stagger**: 40 ms between siblings, capped at 12 items (total ≤ 480 ms); later items appear together.
3. **Exit**: faster than enter (160 ms), no blur, `y: −6px`.
4. **Numbers** spring (`gentle`) from the previous value, never from 0, after first render.
5. **Causality**: an effect never starts before its cause. For example, a verdict stamp waits for the last verification cell.
6. **One hero at a time**: while a cinematic moment plays (stamp, shockwave), other animations dim to 60%.
7. **Physics over tweening** for anything that "has mass": needles, sphere arrows, falling blocks.
8. **No infinite attention-grabbers**. Looping ambient motion stays under 8% luminance variance and pauses after 30 s of inactivity.

### 5.3 Reduced motion and quality tiers

* `motion` pref: `system` (default, follows `prefers-reduced-motion`), `full`, `reduced`.
* Reduced: no parallax, no camera moves, no particles, no glitches or shakes; crossfades of 120 ms; counters jump; 3D scenes render static frames and re-render on data change only (`frameloop="demand"`).
* `quality` pref: `auto` | `high` | `medium` | `low`. `auto` uses `navigator.hardwareConcurrency`, `deviceMemory`, DPR, coarse pointer and drei `PerformanceMonitor` to pick and adjust.

| Tier | DPR cap | Postprocessing | Particles | Glass (transmission) | Backdrop |
|---|---|---|---|---|---|
| high | 2 | Bloom + vignette | 100% | yes | WebGL |
| medium | 1.5 | Bloom only | 50% | no (standard + opacity) | WebGL (½ res) |
| low | 1.25 | none | 20% | no | CSS gradient |

### 5.4 Signature moments (named, reusable)

| Name | Where | Description |
|---|---|---|
| `EntanglementFlash` | Boot end, Studio stage 2 | Two points connect with a helix of light, then a radial flash |
| `CollapseRipple` | Measurements | A ring shrinks onto the outcome, and the cell flips colour |
| `VerdictStamp` | Studio, Attack Lab | A stamp scales from 1.6 with `wobbly`, an ink-bleed mask spreads, and particles burst in the verdict colour |
| `Shockwave` | Incidents, COMPROMISED | An expanding ring in the scene plus a 2 px screen-edge vignette pulse |
| `Glitch` | Attack running | Per-letter offset and RGB split on headers for ≤ 400 ms bursts, capped at 2 bursts per second |
| `ScanBeam` | Ledger verify, qubit grids | A soft light band sweeps across items, each one resolving as the beam passes |
| `Unseal` | Studio key reveal | The lock shackle opens, the key glows, and the twin key shatters |
| `Tunnel` | Route change | A clip-path circle grows from the nav item that was clicked |

---

## 6. Global experiences

### 6.1 Boot sequence (`Boot.tsx`)
* Shown on the first visit in a browser session (`sessionStorage`), full-screen over the app. Skip with `Esc`, a click on "Skip", or immediately under reduced motion.
* Content is a terminal-style log fed by **real** calls:
  1. `QVERIS SENTINEL · cold start`
  2. `GET /api/v1/health … 200 (12 ms) · engine 2.0.0 · preset standard`
  3. One line per selftest check as `selftest.check` events arrive (or from polling `/system/selftest`): `[ OK ] teleport.aer  max|Δρ| = 3.1e-16`, `[SKIP] …`, `[FAIL] …`
  4. `event stream … ws open (rtt 8 ms)`
  5. `entangling interface …` → **EntanglementFlash** → reveal.
* Visuals:
  * text types at 12 ms per character, with a caret;
  * status tags are coloured;
  * a thin progress line fills with the checks;
  * a small rotating Bloch glyph animates.
* Minimum on-screen time is 1.6 s (for readability). There is no maximum: if the checks are slow, the app reveals after 6 s and the remaining checks continue in the background.
* **Backend unreachable**: the boot log shows `engine unreachable — retrying in 3 s` with a countdown and a "Continue offline" button. The app then shows the degraded banner (§16).

### 6.2 Quantum backdrop (`Backdrop.tsx`)
* A fixed full-viewport canvas behind all content, rendering one fragment shader:
  * a domain-warped fBm "probability fog" in deep indigo;
  * faint interference fringes from up to 6 **ripple sources**. Sources come from the cursor (desktop) and from WS events: a completed session spawns a ripple at a random edge position in the event's colour;
  * hue drifting toward coral with the global threat level (`u_threat`, springed);
  * film grain and a vignette.
* Renders at ½ DPR, capped at 30 fps, and pauses when the tab is hidden.
* On low quality or reduced motion it is replaced by static layered radial gradients (CSS).

### 6.3 Custom cursor (`Cursor.tsx`)
* Rendered only when `(pointer: fine)`, motion is not reduced, and the pref allows it.
* An 8 px dot follows instantly; a 36 px ring follows with spring `smooth`.
* States:
  * `interactive` (ring 52 px, tinted by `data-cursor-color`);
  * `text`;
  * `drag` (squashed ring with a "drag" micro-label);
  * `orbit` (in 3D canvases, "drag to orbit");
  * `busy` (dashed rotating ring while a request runs).
* **Magnetic** targets (`data-magnetic`): the element translates up to 6 px toward the pointer and the ring snaps to its bounds.
* The native cursor is hidden (`cursor: none`) on `body.has-custom-cursor` only; text inputs keep the native I-beam.

### 6.4 Page transitions (`PageTransition.tsx`)
* `AnimatePresence mode="wait"` keyed by pathname.
* **Exit**: opacity 0, scale .985, blur 8 px, 200 ms.
* **Enter**: `clip-path: circle(0 at X Y)` → `circle(150% at X Y)` over 650 ms `--ease-out`, where (X, Y) is the centre of the clicked nav item (stored in `ui.transitionOrigin`) or the viewport centre by default. A 1 px sky scan-line sweeps with the reveal edge. Children stagger in.
* Reduced motion: a 120 ms crossfade.

### 6.5 Command palette (`CommandPalette.tsx`)
* Opens with ⌘K / Ctrl-K / `/`, or the top-bar button. It is a modal with an input and result groups:
  * **Navigate**: all routes.
  * **Actions**:
    * Start/Stop traffic; set the rate;
    * Launch *attack* (all 17);
    * Run analytics *kind* (quick);
    * Verify ledger; Certify link *id*;
    * Toggle theme, motion, sound; Open settings.
  * **Recent**: the last 5 sessions and incidents from the live store.
* Fuzzy scoring (`lib/fuzzy.ts`): subsequence match plus bonuses for word starts, consecutive runs and recent use.
* Keyboard: ↑ ↓, Enter, Esc, and Tab to switch group. It enters with scale .96 → 1 and a blur.

### 6.6 Toasts (`Toasts.tsx`)
* Sources: `incident.opened` (severity-coloured, with an **Investigate** action), job completion, API errors, traffic/campaign state changes.
* At most 4 visible, the rest queued. Auto-dismiss after 6 s; CRITICAL stays until dismissed.
* A progress bar shows time remaining, hover pauses it, and swiping dismisses on touch.
* An ARIA live region announces the title.

### 6.7 Sound and haptics
* `lib/audio.ts` is a WebAudio synth: no audio files, master gain 0.15, **off by default**, and enabled only after a user gesture.

| Event | Sound |
|---|---|
| Accepted signature | Soft pluck; pitch rises as QBER falls |
| Rejected signature | Detuned minor second |
| Critical incident | 60 Hz pulse + filtered noise swell |
| Block sealed | Three-note shimmer |
| UI toggles | 4 ms tick at −30 dB |

* Haptics: `navigator.vibrate([30, 40, 30])` on CRITICAL incidents when enabled (mobile).

### 6.8 Explain drawer (`ExplainDrawer.tsx`)
* `explain(topicId)` opens a right-side drawer (a bottom sheet on mobile) with content from `lib/explanations.tsx`. Each entry has:
  * **What it is**, **How we compute it** (with KaTeX), **Why it matters for security**, and **Limits**;
  * a "Go deeper" link to the matching Method section.
* Topics include: `chsh`, `witness`, `qber`, `detwirl`, `frame`, `source_consistency`, `copy_consistency`, `margin`, `cusum`, `key_tests`, `sprt`, `forensics`, `protocol_guard`, `symmetrization`, `thresholds`, `eps_rob`, `eps_forge`, `eps_rep`, `holm`, `clopper_pearson`, `teleportation`, `six_state`, `lamport`, `ledger`, `merkle`.

### 6.9 Settings sheet
* Controls:
  * Theme (system/dark/light);
  * Motion (system/full/reduced);
  * Quality (auto/high/medium/low);
  * Sound, Haptics, Custom cursor;
  * Show hints (first-visit coach marks);
  * API base (advanced, for pointing at a remote server).
* Persisted to `localStorage` under `qveris.prefs.v1`. Every access is wrapped in try/catch and the app works with storage unavailable.

---

## 7. App shell

### 7.1 Desktop (≥ 1024 px)

```
┌──────┬──────────────────────────────────────────────────────────────────┐
│      │ TopBar: [route title (scramble)]   ·live· [THREAT: HIGH] [⏵12/m] [⌘K] [⚙] │
│ Nav  ├──────────────────────────────────────────────────────────────────┤
│ Rail │                                                                  │
│ 76px │                         <Outlet/>                                │
│ (hover│                                                                  │
│ →232)│                                                                  │
└──────┴──────────────────────────────────────────────────────────────────┘
```

* **NavRail**: logo (animated `QubitLogo`) at the top, 9 items, settings at the bottom. It expands on hover or when pinned. The active item is a glowing capsule (`layoutId="nav-active"`) that springs between items and emits 6 tiny particles on change. Items carry a count badge (open incidents, running jobs).
* **TopBar**:
  * page title with `ScrambleText` on route change;
  * `ConnectionPill` (live / reconnecting n / offline, with RTT tooltip);
  * `ThreatLevelPill` (colour + label, pulsing at HIGH+, links to /incidents);
  * `TrafficControl` (a play/pause toggle + rate segmented control 6/12/30 per min; the tooltip shows generated count);
  * the ⌘K button; a settings button.

### 7.2 Tablet (768–1023 px)
NavRail is collapsed (icons only, no expansion); the TopBar is the same; content uses two columns where the desktop has three.

### 7.3 Mobile (< 768 px)
* **TopBar** (52 px): logo, route title, threat dot and connection dot, a ⌘ button (palette as a full sheet).
* **BottomNav** (64 px + `env(safe-area-inset-bottom)`): Command, Studio, Attack, Analytics, More. **More** opens a sheet with Overview, Playground, Ledger, Incidents, Method and Settings. The active tab has an animated pill and an icon bounce.
* The traffic control moves into Command Center's floating action button.

---

## 8. Component library

All components are typed, accessible (roles and labels), themable through tokens, and motion-aware (they respect reduced motion).

| Component | Props (key) | Behaviour and motion |
|---|---|---|
| `Button` | `variant: primary\|secondary\|ghost\|danger`, `size`, `icon`, `loading`, `magnetic` | Press scale .97 (snappy); ripple from the click point; primary has an animated gradient border; `loading` shows a mini orbit spinner |
| `HoldButton` | `holdMs=650`, `onConfirm` | A ring fills while held and releases with a burst. Used to launch attacks; keyboard: hold Space/Enter |
| `IconButton` | `label` (required for a11y) | Tooltip on hover/focus |
| `Toggle` | `checked`, `onChange`, `label` | Spring knob; the track glows in the context colour |
| `Segmented` | `options`, `value` | Sliding highlight (`layoutId`) |
| `Slider` | `min,max,step,value,format,marks,log?` | The thumb grows while dragging; a floating value bubble; arrow keys step; PageUp/Down ×10; optional log scale |
| `Select` | native `<select>` styled + custom popover on desktop | Keyboard accessible |
| `Tabs` | `items`, `value` | Underline morph |
| `Badge` / `Chip` | `tone` (semantic) | Pulse variant for live states |
| `SeverityPill` | `level` | Colour + icon + label; CRITICAL shimmers |
| `VerdictBadge` | `verdict` | ACCEPTED ✓ mint, REJECTED ✕ coral, CERTIFIED ◆ mint, COMPROMISED ▲ coral |
| `Tooltip` / `Popover` | — | Smart placement, 120 ms delay, touch = tap |
| `Modal` / `Sheet` / `Drawer` | `open`, `onClose`, `title` | Focus trap, Esc, scrim blur; sheets are draggable with snap points on mobile |
| `GlassPanel` | `title?`, `kicker?`, `actions?`, `explain?` | The panel material (§4.3), with an optional ⓘ opening Explain |
| `Stat` | `label, value, format, delta?, spark?, ci?, explain?` | A `CountUp` value; the CI in small mono; a sparkline under it |
| `CountUp` | `value, format, spring` | Springs from the previous value |
| `ScrambleText` | `text, duration` | Characters resolve left→right from random glyphs (`0-9a-f` for hashes) |
| `TypeText` | `text, speed` | Typed reveal with a caret (boot) |
| `HashChip` | `hash, head=10` | Mono chip; a click copies it (toast "Copied") with a scramble |
| `ProgressRing` | `value 0..1, indeterminate` | Springed arc |
| `Meter` / `LiquidGauge` | `value, max, tone` | A liquid fill with a sine surface (reservoir) |
| `ThreatRing` | `level, counts` | Concentric severity arcs rotating slowly; a jolt on new incidents |
| `ConnectionPill` | — | Reads `state/connection` |
| `Timeline` | `items` | A vertical line draws in; nodes pop |
| `Stepper` | `steps, active, progress` | A connector fills with light |
| `JsonViewer` | `data, collapsedDepth` | Syntax colouring; collapse/expand; copy path |
| `Formula` | `tex, display?` | Lazy KaTeX |
| `Skeleton` | `shape` | An interference-fringe shimmer |
| `EmptyState` | `title, body, action` | A floating Bloch glyph illustration |
| `ErrorState` | `error, retry` | Shows the API error code/message and a retry |
| `NodeAvatar` | `nodeId` | A coloured orb with an initial; a signer shows a key notch, a verifier a check notch |
| `VirtualList` | `items, rowHeight, render` | Windowed rendering for feeds (≥ 200 rows) |
| `KeyValue` | `rows` | Mono-aligned definition list |

---

## 9. Data-visualisation kit

All charts are SVG unless noted. They are responsive via `useMeasure` (ResizeObserver) and themed through tokens. Accessibility: `role="img"`, an `aria-label` summary, and a "View data" toggle that renders an accessible table.

| Chart | Data | Encodings and motion |
|---|---|---|
| `LineChart` | `series[{id,label,color,points[{x,y,lo?,hi?}]}]`, `xScale/yScale: linear\|log` | Paths draw in (dash-offset, 900 ms); CI bands at 16% opacity; reference lines with labels (α, thresholds, bounds); hover crosshair snapping to the nearest x, with a tooltip listing all series; legend toggles series (fade) |
| `BarChart` | grouped/stacked | Bars grow from the baseline with spring `smooth`; value labels count up |
| `Heatmap` | `rows, cols, values, scale: sequential\|diverging` | Cells fade in along a diagonal wave; hover highlights the row/column; optional cell text |
| `ConfusionMatrix` | labels × labels | Heatmap + row-normalised percentages + diagonal emphasis |
| `Radar` | axes (pₓ, p_y, p_z, p_I) | Baseline polygon (ghost) vs current (filled), springed vertices |
| `ChshGauge` | `S, S_lcb, S0` | A semicircle from 0 to 3. The classical zone (0–2) is hatched coral, the quantum zone (2–2√2) a mint gradient, and the region beyond 2√2 is greyed "impossible". Ticks at 2 (local bound) and 2√2 (Tsirelson). The needle springs (`gentle`); the LCB is a translucent arc; the baseline S₀ is a small diamond |
| `Sparkline` | `points, baseline?` | Last-value dot with a glow; a baseline band |
| `PmfChart` | two PMFs + thresholds | Bars for Bin(n, e) (mint) and Bin(n, ⅓) (coral) with **shaded tail areas** labelled ε_rob and ε_forge; threshold markers s_a and s_v are draggable in the Threshold Designer |
| `SprtChart` | `trace[[n, llr]…]`, `A`, `B` | A step path that draws itself in sync with the Studio playback; boundary lines; the crossing point bursts |
| `BitGrid` | 256 cells: `state: pass\|fail\|inconclusive\|pending`, `value bit` | A 16×16 grid; a wave reveal from the top-left; failures pulse coral; a hover tooltip shows n and m for the own/recv sets |
| `KeyPairGrid` | 256 × {key0, key1} | Twin micro-cells; `Unseal` motion on the chosen key |
| `QubitGrid` (**canvas**) | `cells[keys][positions]{b, o, set, t (tested), x (mismatch)}` | Fill by basis colour; untested cells at 25% alpha; mismatches get a coral ring with a pulse; a separator between the own and recv sets; a scan beam sweeps during playback. Canvas keeps 768+ cells cheap |
| `MatrixView` | 3×3 or 4×4 numbers | Diverging colour per cell; numbers morph (CountUp); used for M, PTM and the frame matrix |
| `LatencyWaterfall` | stages with start/duration | Horizontal bars offset in time; total marker |
| `HistogramChart` | bins | For measurement counts vs the Born prediction line |
| `SphereMap` | lat/long grid values (insider optimality) | Equirectangular heatmap with minimum markers at the six axis points |
| `LinkSeriesChart` | monitor points | QBER and S on twin axes, CUSUM as a filled area, alarm markers, incident markers |

Number formatting (`lib/format.ts`):
* rates as percentages with 2 decimals and a CI `[a, b]`;
* tiny probabilities in scientific notation `3.1 × 10⁻¹⁰` (true superscripts);
* durations adaptive (`41 ms`, `2.3 s`);
* counts with thin-space grouping (`2 330 624`);
* hashes shortened `9f3a…c21e`.

---

## 10. 3D scene kit

`<SceneCanvas quality fallback={<Svg2D/>}>` wraps every scene. It provides:
* the DPR from the quality tier, plus drei `PerformanceMonitor` (it steps down on sustained low fps);
* `frameloop` `always` while in view and animating, `demand` under reduced motion, `never` while off-screen (IntersectionObserver);
* a WebGL availability check with the 2D fallback;
* disposal of geometries and materials on unmount;
* a transparent background (the backdrop shows through).

### 10.1 `HeroScene` (Overview)
* **Objects**:
  * **Alice sphere** (left) and **Bob sphere** (right): glass Bloch spheres (MeshPhysicalMaterial transmission 1, roughness .15, thickness .6, iridescence .3; the medium tier uses a standard material at opacity .35) with latitude rings, axes in basis colours, and a state arrow;
  * a **Bell helix** between them: 2 × 90 instanced spheres on a double helix along a Catmull-Rom arc, colours alternating alice/bob, joined by 90 thin "bond" lines, flowing at 0.15 units/s;
  * **qubit pulses**: 40 instanced sky orbs streaming;
  * a **dust field**: 3 000 points (high) with slow curl-noise drift and cursor parallax;
  * **Eve**: a dark faceted crystal (octahedron, metalness .8, coral emissive crack texture), hidden until chapter 6;
  * **Shield cage**: a hexagonal cage (instanced hex frames) around Bob, hidden until chapter 7;
  * **Ledger stack**: 6 rounded boxes in chapter 8.
* **Scroll timeline**: a sticky canvas, and `useScroll` progress `T ∈ [0, 8]` across chapters. Per chapter there is a keyframe (camera pos/target/fov and object states), interpolated with smoothstep. The camera adds pointer parallax (±0.25).
* **Chapter states**:
  1. Entangle: the helix forms from scattered particles; the CHSH ring counter appears as a 3D text billboard.
  2. Teleport: Alice's arrow flashes and dissolves; two gold bits arc over; Bob's arrow materialises (X/Z gates flash).
  3. Estimate: a sampled subset of pulses peels off into a small cloud, which becomes an ellipsoid ghost.
  4. Symmetrize: a Charlie sphere slides in; half the records (small cubes) swap between Bob and Charlie.
  5. Sign: Lamport twin keys over Alice; one of each pair glows.
  6. Intrude: the world tints coral, Eve rises, tendrils grip the helix, and the pulses jitter.
  7. Detect: the cage snaps shut (spring), a shockwave fires, Eve shatters into 60 shards (simple ballistic integration, floor bounce).
  8. Anchor: blocks drop and chain; the camera cranes up.
* **Interactions**: hovering a sphere shows a label; clicking spins it (angular impulse, damped).

### 10.2 `NetworkScene` (Command Center)
* **Layout**: node positions come from the backend (`pos_x/y/z`). Ground: a hex-grid shader plane with radial fade and slow scanning rings.
* **Node**:
  * signer: an octahedron core + 2 tilted orbit rings;
  * verifier: an icosahedron core + 1 ring.
  Emissive in the node colour, with a billboard glow sprite and a drei `Html` label (name, role, mini stats). Suspended nodes get a coral outline and a slow blink.
* **Quantum link**: a `TubeGeometry` along a lifted arc with a custom shader (flowing stripes `fract(uv.x*8 - t*speed)`, soft edges, fresnel). The colour follows status (sky / peach DEGRADED / coral QUARANTINED). On `distribution.completed` the stripe speed bursts and brightness pulses.
* **Classical links** (verifier↔verifier and signature delivery paths): dashed gold lines (`Line2`) with animated dash offset.
* **Pulses**: an instanced mesh pool (max 400).
  * `distribution.completed` spawns N = clamp(round(log10(qubits)·3), 6, 24) sky pulses per link, staggered by 40 ms.
  * `session.completed` spawns a gold packet along signer→V₁ (0.9 s), then V₁→V₂ (0.7 s). On arrival V₁ flashes the verdict colour.
* **Threat effects**:
  * COMPROMISED distribution: a coral lightning arc (a jagged polyline regenerated each frame for 600 ms) along the link, a shockwave ring at the verifier, and **Eve** materialising beside the link for 3 s;
  * `incident.opened`: a camera micro-shake (amplitude .03, 350 ms) when motion is full.
* **Controls**:
  * OrbitControls (damping .08, polar limits, zoom limits); auto-rotate at 0.3 after 10 s idle;
  * click a node/link to select (outline pass on high, emissive boost otherwise), which opens the details panel;
  * double-click to focus (camera tween 700 ms).
* **2D fallback**: an SVG graph with the same layout (x/z projection), animated dashes and pulses (SMIL-free, rAF-driven).

### 10.3 `BlochScene` (Attack Lab, Playground)
* **Sphere**: glass (tiered) + a lat/long wire (12 × 24) + three axis lines in basis colours with end labels (`|+⟩ |−⟩ |+i⟩ |−i⟩ |0⟩ |1⟩`) as billboard text. The six eigenstate markers are small spheres.
* **Ellipsoid** (`ChannelEllipsoid`): a unit sphere mesh transformed by `Matrix4` from (M, c):
  * rows of M go into the basis columns; the translation is c;
  * material: iridescent translucent (the current map) vs a mint wireframe ghost (the baseline);
  * **morph**: the 12 numbers spring independently (`smooth`), which produces an organic deformation.
  A **rotation-axis arrow** and angle arc appear for coherent rotation; a **translation arrow** appears for non-unital maps.
* **State vector**: a cylinder + cone. The direction springs; a fading trail line (64 points) shows the geodesic history.
* **Frame-resolved minis**: 4 small ellipsoids in a row (HTML overlay labels k = 00, 01, 10, 11), toggled on.
* **Interaction** (Playground):
  * drag on the sphere surface (raycast → Bloch vector, clamped to the unit sphere or its interior with a mixedness slider);
  * orbit with right-drag or two fingers;
  * gate application animates a rotation about the gate axis (quaternion slerp, 500 ms).

### 10.4 `ChainScene` (Ledger)
* Blocks: drei `RoundedBox` (instanced when > 60), laid out along a gentle S-curve receding in z. The newest block sits at the front-right.
  * Material: dark glass with an emissive edge (valid mint, pending sky, tampered coral), plus a height label as an `Html` chip.
  * Chain links between blocks: a torus pair.
* **New block**: spawns 3 units above, drops with spring `wobbly`, the chain link "clicks", and a gold dust burst plays.
* **Verify**: a plane of light sweeps from genesis to head. Each block flips its edge to mint (valid) or coral (tampered) as the plane passes. Tampered blocks crack: a vertex-shader noise displacement plus coral fissures. Downstream blocks dim to show the broken link.
* Click selects a block (details panel). Scroll/drag pans along the chain.
* **Mobile**: a 2D horizontal chain of cards with snap scrolling.

### 10.5 `QuantumFieldBackdrop` (global)
The single fragment shader of §6.2. Uniforms: `u_time`, `u_res`, `u_mouse`, `u_threat`, `u_theme`, `u_ripples[6]` (xy, t0, colour).

### 10.6 Shared 3D helpers
`useSpringVector`, `GlowSprite`, `PulsePool`, `ShockwaveRing`, `LightningArc`, `BillboardLabel`, `makeGlassMaterial(tier)`, and `basisColor(β)`. Colours are read from CSS tokens at mount so both themes stay in sync.

---

## 11. Pages

Each page spec lists: layout (desktop / mobile), data sources, sections, interactions, and states (loading/empty/error).

### 11.1 Overview `/`

**Data**:
* `GET /metrics/summary` (plus live `metrics.tick`);
* `GET /sessions?kind=distribution&limit=1`;
* `GET /sessions?kind=signature&limit=1` (latest reports for the chapter chips);
* `GET /analytics/latest/{detection_matrix,forgery_analysis,performance}` (optional);
* `GET /ledger/summary`.

**Sections**:
1. **Hero** (100dvh): `HeroScene` fills it.
   * Overlay (bottom-left): kicker `SIH26141 · QUANTUM-INSPIRED THREAT DETECTION`, headline *"Signatures that physics can defend."* The letters assemble from scattered positions (per-letter springs, random offset ±40 px, stagger 18 ms). Then a 2-line subhead and CTAs: **Enter Command Center** (primary, magnetic) and **Sign a message** (secondary).
   * **Live proof card** (glass, top-right on desktop, below the headline on mobile), with 4 `Stat`s:
     * Signatures verified;
     * Attacks detected ("62/62" with CI);
     * Mean CHSH S over the last 20 certified links;
     * Ledger height.
     Each has a sparkline from `/metrics/timeseries`. With zero sessions it shows an empty state: "Engine idle — no sessions measured yet" with a **Start live traffic** button (`POST /traffic/start`).
   * A scroll cue: an animated line with a travelling dot.
2. **The Journey** (8 chapters × 100vh, a sticky canvas, text panels scroll).
   * A left progress rail with chapter dots (clickable, scroll-to).
   * Each chapter: a kicker (`01 · ENTANGLE`), a title, 2–3 sentences, and a **live proof chip** bound to the latest real report:

| # | Chapter | Proof chip (real value) |
|---|---|---|
| 1 | Entangle | `alice→bob  S = 2.78  (LCB 2.64 > 2)` |
| 2 | Teleport | `2 330 624 qubits · 0 frame errors` |
| 3 | Estimate | `QBER 1.02 % [0.96, 1.08]` |
| 4 | Symmetrize | `1 024 records swapped per key` |
| 5 | Sign | `digest 9f3a…c21e · 256 keys revealed` |
| 6 | Verify | `mismatch 1.03 % ≤ s_a 8.62 %` |
| 7 | Intrude → Detect | `detection 62/62 · FRR 0/1041` |
| 8 | Anchor | `block #42 · 7c1d…0b9a` |

   If a chip's source does not exist yet, it reads "not measured yet" in `--text-3`.
3. **Threat catalog**: six category cards (a 3 × 2 grid on desktop, a horizontal snap-scroll carousel on mobile).
   * Each card: glyph, name, a one-line physics summary, "caught by" layer chips, and a live count (per-category detection from metrics).
   * Hover: 3D tilt (±6°) and a looping micro-animation (SVG) of the attack. Click goes to `/attack-lab?category=…`.
4. **Evidence strip**: three mini charts from the latest analytics results (detection heat strip, forgery-bound curve, throughput bars), each linking to its Analytics section. With no results: "No evaluation run yet — Run the quick suite" (queues 3 jobs).
5. **Footer**: stack, PS reference, the "No AI/ML · no fabricated data" statement, links to the Method page and API docs (`/docs`).

### 11.2 Command Center `/command`

**Data**:
* `GET /network`, `/metrics/summary`, `/keys/reservoir`, `/incidents?status=OPEN&limit=20`, `/sessions?limit=50`, `/traffic`;
* WS: all topics.

**Desktop layout** (12-col grid, `gap 16`):

```
┌───────────────────────────── header: title · status sentence · [Traffic ▶ 12/min] [Campaign] ─┐
│ NetworkScene (cols 1–8, rows 1–2, min-h 560)          │ ThreatRing + level      (cols 9–12)  │
│   overlays: legend · 2D/3D · reset view               │ KPI tiles 2×2 (spark)                │
│   selected link/node panel slides up from bottom      │ Key reservoir (liquid gauges/group)  │
├───────────────────────────────────────────────────────┼──────────────────────────────────────┤
│ Link health cards (row scroll: 4 cards)               │ Live feed (virtual list)             │
└───────────────────────────────────────────────────────┴──────────────────────────────────────┘
```

* **Status sentence** (live): "Live · 11.8 signatures/min · threat level **HIGH** · 3 open incidents · ledger #42".
* **KPI tiles**:
  * Throughput (per min);
  * Acceptance (accepted/total, last 15 min);
  * Detections (attacks detected / injected, with CI);
  * False rejections (FRR with CI).
* **Link health card** (per quantum link):
  * name `alice → bob`, status chip, length;
  * `Sparkline` of QBER (baseline band), mini `ChshGauge`, a CUSUM bar vs h;
  * last update relative time;
  * actions: **Certify** (POST; the card shows a scanning animation until the report arrives, then flashes), **Quarantine/Release**, **Attack** (→ Attack Lab preset targeting this link), **Details** (→ drawer with `LinkSeriesChart`).
* **Live feed**:
  * rows for signatures and distributions interleaved, newest on top, slide-in from the top (spring). Each row: icon (signature/distribution), group, message preview or qubits, verdict badge, threat pill if any, latency, relative time. Rows from attacks show an **injected** tag (ground truth) next to the detected classification. Clicking opens `SessionDrawer`.
  * Filter chips: All / Signatures / Distributions / Threats.
* **Campaign sheet**: preset mixes (**Low & slow** channel drift, **Blitz**, **Insider threat**, **Replay storm**, **Custom**), rate, duration and target groups. Start → `POST /attacks/campaigns`. A running campaign shows a coral banner with progress and a Stop button.
* **Choreography**: see §10.2 (pulses, packets, lightning, Eve, shockwaves) plus ThreatRing jolts and toasts.

**Mobile**:
* a compact header;
* ThreatRing + KPIs as horizontal snap cards;
* the NetworkScene at 55vh (low tier, or the 2D fallback with a toggle);
* the feed and link cards stacked;
* traffic and campaign controls in a FAB (bottom-right, above the BottomNav) that opens a sheet.

**States**:
* no nodes: error (the backend should always seed);
* no sessions: the feed empty state with **Start live traffic**;
* WS offline: the scene dims, with an overlay "stream offline — showing last known state".

### 11.3 Signature Studio `/studio`

**Data**:
* `GET /network` (groups), `/keys/reservoir`, `/system/config` (presets), `/theory/design` (preview);
* `POST /signatures/sign-and-verify`;
* WS `ledger.block` (to resolve the tx).

**Layout**: the composer on the left (380 px) and the Pipeline Theater on the right. On mobile the composer comes first, collapsing into a summary bar once running.

**Composer**:
* **Message** textarea: a live UTF-8 byte counter, and a colour change when raw mode is over its limit.
* Example buttons: `Pay 250 QVC to Bob`, `Rotate HSM key #7`, `Grid dispatch 42 MW`. These are text inputs only.
* **Encoding** segmented: SHA-256 (any length) | Raw (≤ 31 B, fully IT). Raw is disabled with an explanation when the message is too long.
* **Group** picker: cards (`alice → bob, charlie`, `diana → charlie, erin`) with avatars and a reservoir count.
* **Preset** segmented (demo / standard / high), with the qubit estimate and **design preview**: s_a, s_v, ε_rob, ε_forge, ε_rep from `/theory/design` using the link's baseline QBER, each with ⓘ.
* **Sign & verify** primary button. It shows the busy cursor and an inline quantum loader while the request is in flight (typically < 1 s).

**Pipeline Theater**: a `Stepper` of 8 stages. Playback is driven by a local timeline over the received report. Controls: ▶/❚❚, speed ×0.5/×1/×2, a scrub bar, and **Skip to verdict**. Stage durations (at ×1): 1.2, 1.6, 1.8, 1.0, 3.4, 1.8, 2.2, 1.4 s.

| # | Stage | Visual (bound to report fields) |
|---|---|---|
| 1 | Envelope → digest | Envelope fields as chips (`signer, recipients, seq, timestamp, nonce, message`) flow into a funnel (SVG path morph). The digest hex resolves with `ScrambleText` (real `digest.hex`); the `BitGrid` fills bit by bit (1 = lavender, 0 = dim) |
| 2 | One-time key bundle | A bundle card flips in (id, created, L, qubits, certification S / QBER per link, design ε's) → CERTIFIED stamp with `EntanglementFlash` |
| 3 | Reveal keys | `KeyPairGrid`: each bit's chosen key **unseals**; the twin dims (the first 32 shatter into particles). Caption: "Revealed 256 of 512 one-time keys · L = 2048 labels each" |
| 4 | Transmit | A gold packet travels Alice → Bob along a bezier, labelled with the signature size (`signature.size_bytes`) |
| 5 | Bob verifies | `QubitGrid` (from `grid_sample`) with a scan beam; own/recv counters (n, m) count up; `BitGrid` cells flip pass/fail in scan order (from `keys.pass`); `SprtChart` draws key 0's LLR; a bar compares the observed rate with s_a |
| 6 | Forward to Charlie | A packet Bob → Charlie; Charlie's `BitGrid` and threshold s_v |
| 7 | Sentinel assessment | `FindingsCascade` (cards stagger in: ✓ / ⚠ / ✕, statistic, p-value log bar vs α, effect vs floor, ⓘ). Then the **VerdictStamp** (ACCEPTED / REJECTED) with a shockwave and particles, and the classification sentence |
| 8 | Anchor | A tx card flies into the "pending pool". When a `ledger.block` containing the tx arrives, it shows block height and hash (scramble) with a link to the Ledger; otherwise "sealing in ≤ 8 s" with a countdown |

After playback there are tabs: **Summary**, **Findings** (full list), **Latency** (`LatencyWaterfall`), **Raw report** (`JsonViewer`), **ε bounds** (the design numbers with formulas).

**Errors**:
* 409 `BUNDLE_UNAVAILABLE`: an inline card "Reservoir empty for g-alice" with **Distribute now** (`POST /keys/distribute`), animated as a mini distribution.
* 409 `LINK_QUARANTINED`: a card linking to the incident.

### 11.4 Attack Lab `/attack-lab`

**Data**:
* `GET /attacks/catalog`, `/network`, `/detection/baselines`;
* `POST /theory/link` (the predicted effect preview for channel attacks);
* `POST /attacks/run`; `POST /incidents/{id}/respond`.

**Layout** (desktop): catalog (320 px) | configuration (360 px) | Theater (flex). Once a run completes the configuration column collapses into a chip bar, giving the Theater more room. On mobile the three are steps in a flow: catalog → configure (sheet) → theater.

**Catalog**:
* Category tabs: All, Forgery, Impersonation, Replay, Unauthorized, Channel, Repudiation.
* Cards: glyph, name, phase badge (`distribution` sky / `signing` gold), a one-line summary.
* Search field; keyboard navigation (↑↓, Enter).

**Configure panel**:
* **Description**, **physics** (expandable, with KaTeX) and **adversary knowledge** (a bullet list), all from the catalog.
* **Parameters** rendered from the schema: sliders with unit-labelled marks, selects, toggles.
  * The **intensity** slider shows the mapped physical parameter live (e.g. `I = 0.40 → p = 0.20`).
  * **Target**: group, plus link side (first / second / both) for distribution attacks.
  * **Counterfactual** toggle (default on).
* **Predicted effect** (channel attacks only): `POST /theory/link` with baseline + attack gives the predicted S, F and QBER per basis vs baseline. It updates live (debounced 150 ms) while sliding, and says "prediction from exact channel algebra; the run will sample it".
* **Launch**: a `HoldButton` (650 ms) that arms with a charging ring, then fires.

**Theater** while running: the header glitches (`Glitch`), a coral edge vignette pulses, Eve's avatar floats in, and there is a progress shimmer.

**Theater — distribution attacks**:
* **Timeline strip**: Distribute → Bell test → PE → De-twirl → Fingerprint → Decision (→ Counterfactual).
* **BlochScene** (large): the baseline ghost and the measured de-twirled ellipsoid (per selected link).
  * A toggle **Effective ⇄ De-twirled**, with an explanation pill: "The effective view is what verification experiences — the Pauli twirl hides non-unital and coherent components".
  * A toggle for the frame-resolved minis.
* **Instrument panel** (grid):
  * `ChshGauge` per link (S, LCB, S₀);
  * a QBER per-basis bar chart with baseline + CI;
  * `MatrixView` of the frame matrix (4×4);
  * a Pauli `Radar`;
  * `MatrixView` of M (current vs baseline diff toggle).
* **Fingerprint card**: shape, estimated parameters, axis, and the alternatives list ("physically equivalent explanations").

**Theater — signing attacks**:
* **Guard checklist**: authorization, key binding, bundle state, nonce, sequence, freshness, each ✓/✕ with detail.
* `BitGrid` for V₁ and V₂ (failures in coral).
* A mismatch histogram of failed keys with model lines at ⅓ and ½.
* **Forensic attribution card** (for example: "Recv-set matched Bob's forwarded records on 100% of tested positions → **INSIDER: bob**").
* For replay: "Quantum statistics: clean (mismatch 1.0%) — replay is physically invisible; caught by protocol layer".

**Right rail** (both kinds):
* the **Evidence cascade**: all findings, fired first, with Holm-adjusted α shown;
* the **Classification card**: category / subtype / confidence / rule / explanation;
* ground-truth badges: **Detected ✓** and **Correctly classified ✓/✕**;
* incident link;
* **recommended actions** as buttons (execute via `/incidents/{id}/respond`, each with a confirmation popover).

**Counterfactual panel**: a split card, "With Sentinel" vs "Without <defence>", each with verdict badges, key numbers and the outcome sentence from the report. It animates a coral "breach" line when the counterfactual succeeds.

**Run history**: a horizontal list of this session's runs (stored in memory) that can be clicked back into the Theater.

### 11.5 Quantum Playground `/playground`

**Data**:
* `GET /system/config` (channel types + param ranges);
* `POST /playground/channel` (debounced), `POST /playground/teleport`.
* Local exact math (`lib/quantum.ts`) for gate rotations and dragging.

**Layout**: a large `BlochScene` on the left (60%) and an accordion of tools on the right. On mobile the scene sits on top (50vh) with tools as tabs below.

**Tools**:
1. **State**:
   * the six eigenstate buttons (with ket labels);
   * θ/φ sliders plus a purity slider r ∈ [0, 1];
   * readouts: Bloch vector, amplitudes α, β (complex, formatted), and a density-matrix `MatrixView` (2×2 complex as re/im).
2. **Gates**:
   * X, Y, Z, H, S, S†, T, and Rx/Ry/Rz(θ) with an angle slider;
   * each application animates a rotation about the gate axis (slerp) and records a **gate history** chip trail (undo/redo).
3. **Channel designer**:
   * a reorderable stack of channel blocks (drag handle, motion `Reorder`), each with type-specific sliders; "+ Add channel" opens a menu of types;
   * on change: `POST /playground/channel` → the ellipsoid morphs;
   * `MatrixView` PTM (4×4);
   * a Choi eigenvalues bar (with a CPTP badge);
   * predicted S, F and QBER per basis;
   * **twirled vs de-twirled** toggle (the twirled map is the one returned by the API).
4. **Teleport**:
   * an SVG 3-wire circuit (q₀ input, q₁, q₂) with gates H, CX, measurement dials and the classically-controlled X/Z;
   * frame-flip sliders (m₀, m₁ tamper probabilities);
   * **Run** → `POST /playground/teleport` → the animation:
     1. the Bell pair forms (wires glow);
     2. CX and H pulse;
     3. the measurement dials spin to the outcome sampled for display (from `samples.frames` if shots > 0, else the most probable);
     4. gold bits travel to Bob;
     5. the correction gate flashes;
     6. Bob's mini sphere shows the post-correction state.
   * Four outcome cards (k = 00…11): probability bar, and pre/post Bloch mini-spheres (static renders).
5. **Measure**:
   * a basis segmented control (X/Y/Z) and a shots slider (1 … 20 000);
   * **Run** → `POST /playground/teleport` with shots (with channels) or local exact sampling (no channel);
   * `HistogramChart` of counts vs the Born-rule line, with the expectation value and binomial CI.

### 11.6 Analytics `/analytics`

**Data**:
* `GET /analytics/kinds`, `/analytics/latest/{kind}` for each kind, `/analytics/jobs?limit=20`;
* `POST /analytics/jobs`, `DELETE /analytics/jobs/{id}`;
* `GET /theory/design`, `/theory/forgery` (interactive sections);
* WS `jobs`.

**Layout**:
* A header with a sticky section nav (chips): Detection · ROC · Forgery · Thresholds · SPRT · Fingerprint · CUSUM · Performance · Repudiation · Validation.
* **Job launcher grid**: 10 cards, each with:
  * title, "what it measures", params summary, estimated time (quick/full);
  * last run (relative time, duration), status;
  * **Run quick** / **Run full** buttons, and a `ProgressRing` + message + Cancel while running.
  * On completion: a glow flash, the section scrolls into view (if the user did not scroll away), and a toast.
* A **Run quick suite** button queues the quick jobs sequentially (the server runs one at a time).

**Sections** (each: title, a "What this shows" paragraph, the chart(s), params used, generated time, **Download JSON / CSV**; empty state with Run):

| Section | Charts |
|---|---|
| Detection | `Heatmap` attack × intensity (detection rate, CI in tooltip); `LineChart` rate vs intensity per category with CI bands; `ConfusionMatrix`; KPI chips: FRR with CI (legit), overall detection with CI, classification accuracy |
| ROC | `LineChart` (FPR log-x vs TPR), one curve per detector + fused, AUC chips, α markers |
| Forgery | Log-y `LineChart` ε_forge(key) vs L (exact and Chernoff, external and insider) with **MC points and CI whiskers**; a message-level k table; `SphereMap` insider-optimality with min markers and the text "min = 0.3333 at ±x̂, ±ŷ, ±ẑ" |
| Threshold designer (interactive) | L (log slider 64…16384), e (0…0.1), ε_rob / ε_forge targets (log sliders) → `GET /theory/design` (debounced 120 ms) → `PmfChart` with shaded tails; a number line with s_a and s_v; readouts ε_rob, ε_forge, ε_rep (key/msg) in sci-notation; a feasibility banner (with L_min). Also the `threshold_design` job table |
| SPRT | ASN vs p (MC points + Wald line) with fixed n reference; reject rate (OC curve); an animated sample-path demo |
| Fingerprint | `ConfusionMatrix` of true family vs predicted shape; per-family accuracy bars |
| CUSUM | ARL vs shift (log-y), with the false-alarm ARL₀ highlighted |
| Performance | Stacked `BarChart` of latency per stage vs L; a qubits/s line; the NumPy vs Aer speedup bar (log) |
| Repudiation | Dispute rate vs inconsistency r, with vs without symmetrization (CI bands); the bound overlay |
| Validation | A table of channel × max\|Δρ\| with pass badges |

### 11.7 Ledger `/ledger`

**Data**:
* `GET /ledger/summary`, `/ledger/blocks?limit=30` (plus paging), `/ledger/blocks/{h}`, `/ledger/tx/{id}`;
* `POST /ledger/verify`, `/ledger/tamper`, `/ledger/tamper/revert`;
* WS `ledger`.

**Layout**:
* Header stats: height, head hash (`HashChip`), tx total, pending, integrity badge (last verification result + time).
* **ChainScene** (a mobile card chain).
* A details panel (right on desktop, a sheet on mobile) for the selected block:
  * header fields (`KeyValue`);
  * the **Merkle tree** SVG, built bottom-up with lines drawing (leaves = tx hashes);
  * the tx list (kind icon, time, payload preview). Clicking a tx opens its payload `JsonViewer` + inclusion proof path, highlighted in the tree.
* **Actions**:
  * **Verify integrity**: the `ScanBeam` sweep and results. On failure, a banner shows the first invalid height, the issues, and the downstream count.
  * **Tamper demo** (visible only if enabled): a confirmation modal "This rewrites one stored transaction directly in the database to demonstrate detection." Then run Verify automatically.
  * **Revert tamper**.

### 11.8 Incidents `/incidents`, `/incidents/:id`

**List**:
* Filter chips (status, severity, category) and a search (title/link).
* Cards: a severity stripe, title, category/subtype, link/group, occurrences ×n, relative time (live ticking), status pill.
* Desktop is a split view (list 420 px | detail); mobile navigates to the detail route.
* New incidents slide in with a coral flash.

**Detail**:
* Header: severity, title, status, first/last seen, occurrences.
* Actions: **Acknowledge**, **Resolve** (with an optional note), and the recommended response actions.
* **Explanation** paragraph and classification.
* The evidence cascade (reuse).
* **Related session**: a mini report (distribution or signature) linking to `/sessions/:id`.
* **Link monitor** `LinkSeriesChart` (±30 min around the incident, with a marker).
* **Action history** `Timeline`.
* **Ledger anchor**: tx id and block (link).

### 11.9 Session detail `/sessions/:id`

* Fetches the stored report and renders `DistributionReportView` or `SignatureReportView`. These are the same components as the Attack Lab and Studio theaters in **static mode** (no playback; everything visible).
* Header: kind, verdict, time, origin, injected-attack tag (ground truth), copy link.

### 11.10 Method `/method`

* Long-form, with a sticky table of contents (and a scroll-spy highlight).
* Sections: the problem; system overview (an animated SVG architecture diagram); the TQDS protocol (a phase diagram with step highlights on scroll); six-state encoding and teleportation (formulas); Bell certification; frame de-twirling tomography; detection layers (table); security bounds; threat model and assumptions; limitations; references.
* Security bounds use formulas with **live parameters**: KaTeX expressions interpolated with values from `/system/config` and `/theory/design`, for example "with L = 2048, n_min = 290, e = 1.5 %: ε_forge = 9.6 × 10⁻⁷".
* The page is fully readable without JS-heavy scenes (text-first; diagrams are SVG).

### 11.11 Not found
A Bloch arrow collapses to the south pole with the heading "State collapsed — this page does not exist", and buttons to Overview and Command.

---

## 12. Data layer

### 12.1 API client (`api/client.ts`)

* `apiBase = prefs.apiBase || import.meta.env.VITE_API_BASE || ""` (same origin by default).
* `request<T>(method, path, {body, query, timeoutMs, signal})`:
  * JSON encode/decode;
  * `AbortController` timeouts (default 20 s; heavy POSTs 120 s);
  * GET retries twice on network errors with 300/900 ms backoff;
  * errors are parsed into `ApiError {code, status, message, detail, requestId}` from the backend error shape (§17.1 of the backend plan).
* `endpoints.ts` exposes typed functions (`getNetwork()`, `signAndVerify(req)`, `runAttack(req)`, …) using the generated types.

### 12.2 Query keys and cache policy

| Key | staleTime | Invalidated by |
|---|---|---|
| `['network']` | 10 s | `link.updated` (patched in place) |
| `['metrics', window]` | 5 s | `metrics.tick` (merged), `session.completed` (debounced invalidate 1 s) |
| `['reservoir']` | 5 s | `reservoir.updated` (setQueryData) |
| `['sessions', filters]` | 5 s | `session.completed` / `distribution.completed` (prepend) |
| `['session', id]` | ∞ | — |
| `['incidents', filters]` | 5 s | `incident.*` |
| `['incident', id]` | 10 s | `incident.updated` |
| `['catalog']`, `['config']`, `['detectors']`, `['analyticsKinds']` | ∞ | — |
| `['job', id]`, `['latest', kind]` | 30 s | `job.completed` |
| `['ledger','summary']`, `['ledger','blocks']` | 10 s | `ledger.block`, `ledger.verified`, `ledger.tampered` |
| `['theory', …params]` | 60 s | — |

### 12.3 WebSocket (`stream/socket.ts`, `stream/router.ts`)

* Connects to `${wsBase}/ws` (from `location` or the API base) and sends `subscribe` for all topics.
* **Heartbeat**: a ping every 10 s updates the RTT in `state/connection`. After 30 s of silence it reconnects.
* **Backoff**: 0.5, 1, 2, 4, 8 s (with ±20% jitter), capped at 8. State: `connecting | live | reconnecting(n) | offline`.
* **Batching**: incoming events are queued and flushed once per animation frame (`requestAnimationFrame`) into the stores and caches, which prevents render storms during campaigns.
* Routing (`router.ts`):
  * `session.completed` → `live.feed.prepend`, `sceneEvents.push({kind:'packet', …})`, sound;
  * `distribution.completed` → feed + `sceneEvents.push({kind:'pulses', …})` + (if COMPROMISED) `sceneEvents.push({kind:'lightning'})`;
  * `incident.opened` → toast, `live.threat` update, ThreatRing jolt, haptics;
  * `link.updated` → patch the `['network']` cache;
  * `job.*` → `jobs` store + invalidate on completion;
  * `ledger.*` → invalidate the ledger + `sceneEvents` (block drop);
  * `metrics.tick` → `live.metrics`;
  * `traffic.state` / `campaign.state` → `live.traffic`;
  * `selftest.*` → the boot log.

### 12.4 Stores (zustand)

| Store | State | Notes |
|---|---|---|
| `connection` | `status, attempts, rttMs, lastEventAt, serverVersion` | Read by ConnectionPill and banners |
| `live` | `feed (ring buffer 300)`, `metricsTick`, `threatLevel`, `openIncidents`, `traffic`, `campaigns`, `reservoir` | Written by the router |
| `sceneEvents` | a queue of `{id, kind, payload, t}` | Scenes consume in `useFrame` (pop-by-kind) |
| `prefs` | theme, motion, quality, sound, haptics, cursor, hints, apiBase | Persisted (try/catch) |
| `ui` | paletteOpen, explainTopic, transitionOrigin, selected {nodeId, linkId}, settingsOpen | |
| `jobs` | `byId {status, progress, message}` | |

---

## 13. Mobile strategy

* **Breakpoint-driven layouts** (§7.3) plus **container queries** for panels that move between sidebars and full width.
* **Touch**:
  * targets ≥ 44 × 44 px;
  * sliders with a larger thumb (28 px) and haptic ticks at marks (when enabled);
  * sheets with drag-to-dismiss and snap points (25/60/92%).
* **No hover dependence**: tooltips open on tap, and "hover" reveals become explicit expanders.
* **Viewport**: `100dvh`; `env(safe-area-inset-*)` padding; no fixed element covers the keyboard (inputs scroll into view).
* **3D**:
  * the low tier by default on coarse pointers + DPR > 2;
  * a 2D fallback toggle in the Command Center;
  * OrbitControls touch (one finger rotates, two pan/zoom);
  * scenes pause when scrolled away.
* **Charts**: fewer ticks (`ticks(4)`), legends stacked below, wide charts inside horizontally scrollable wells with snap, and tooltips pinned to the top of the chart.
* **Performance**: the particle budget is cut to 20%; WS-driven effects are throttled (max 4 pulses per second).
* **Tested viewports**: 360×740, 390×844, 412×915, 768×1024 (tablet), 1440×900, 1920×1080.

---

## 14. Accessibility

* Landmarks: `header`, `nav`, `main`, `aside`, `footer`; a "Skip to content" link; one `h1` per page.
* **Keyboard**: every control is reachable. There are visible focus rings (`outline: 2px solid var(--quantum)` + glow), and a logical tab order. Shortcuts: ⌘K palette, `g` then a letter for navigation (`g c` Command, `g s` Studio, `g a` Attack Lab, `g l` Ledger …), `?` for the shortcut sheet.
* **Screen readers**:
  * an `aria-live="polite"` region for verdicts ("Signature accepted by Bob and Charlie") and new incidents;
  * charts have summaries plus a data-table toggle;
  * the 3D canvases have `aria-label` descriptions and are not focus traps; everything they show is also available as text in adjacent panels.
* **Colour**: text contrast ≥ 4.5:1 (checked for both themes in `tokens.css` comments); icons + text accompany every colour-coded state.
* **Motion**: §5.3. No flashing above 3 Hz. The glitch effect is capped and disabled under reduced motion.
* `prefers-contrast: more` raises line opacity and removes glass transparency.

---

## 15. Performance

| Budget | Target |
|---|---|
| Shell + Overview JS (gz) | ≤ 430 KB (three is the bulk; split into its own chunk) |
| Other route chunks (gz) | ≤ 150 KB each (charts chunk shared; KaTeX lazy) |
| LCP (desktop, local) | ≤ 2.0 s; mobile mid-tier ≤ 3.0 s |
| Frame rate | 60 fps desktop (high), ≥ 45 medium, ≥ 30 low/mobile |
| Main-thread long tasks during interaction | < 50 ms |
| Memory | Stable over 10 min of live traffic (no growth > 30 MB) |

Techniques:
* route-level `lazy()`; `manualChunks` (`three`, `charts`, `math`);
* instancing and object pools (pulses, shards);
* `useFrame` work kept O(active objects);
* ring buffers for feeds and virtualised lists;
* rAF-batched WS updates; `memo` / selector-based zustand subscriptions;
* canvas for dense grids; SVG for charts at ≤ 2 000 elements (above that, downsample);
* fonts self-hosted with `font-display: swap` and preloaded woff2 for the two display weights;
* images: none (generative only).

---

## 16. Resilience and error handling

* **ErrorBoundary per route**: a "decoherence" error view (the error message, request id if present, **Retry**, **Report** (copy details)).
* **Degraded banner** (top, dismissible, persistent while applicable):
  * "Event stream reconnecting (attempt 3)";
  * "Engine unreachable — showing cached data";
  * "Tamper detected in ledger (height 17) — Verify for details".
* API errors: inline `ErrorState` for query failures; toasts for mutation failures, with the backend's `code` mapped to friendly copy (e.g. `BUNDLE_UNAVAILABLE` → "No certified key bundle ready — distribute one now?").
* **Optimistic UI only for pure UI state**. Server outcomes are never assumed. A verdict appears only from the response.
* **Stale-data labelling**: when showing cached data while offline, timestamps show "as of 12:04:31".

---

## 17. Testing and visual review

* **Unit (vitest)**:
  * `lib/quantum.ts`: rotations preserve norm; H maps ẑ→x̂; S maps x̂→ŷ; affine-map application; eigenstate table;
  * `lib/format.ts`: sci-notation, CI formatting, durations;
  * `lib/fuzzy.ts` ranking;
  * `stream/router.ts`: event → store effects, with mocked stores.
* **Type-check**: `tsc --noEmit` is part of `npm run check`.
* **E2E (Playwright)**. `global-setup.ts` starts the backend with a temp data dir, `QVERIS_PRESET=demo` and `QVERIS_AUTOSTART_TRAFFIC=0`, and serves the built app through the backend.
  * `smoke.spec.ts`: every route renders its `h1` and key test-ids, with **no console errors** (captured and asserted empty).
  * `flows.spec.ts`:
    1. Studio: sign & verify → ACCEPTED shown;
    2. Attack Lab: `forgery.blind` → REJECTED + FORGERY; `channel.dephase` → COMPROMISED + fingerprint `dephasing`;
    3. Playground: teleport → 4 outcome cards;
    4. Ledger: verify valid → tamper → invalid → revert → valid;
    5. Command: start traffic → a feed row appears within 15 s;
    6. Analytics: run `threshold_design` quick → table rendered.
  * `mobile.spec.ts`: the same smoke at 390×844 (touch emulation), plus the BottomNav navigation and sheet open/close.
  * Screenshots for every route at 1440×900 and 390×844 go to `web/e2e/artifacts/` (gitignored) for **visual review passes**: check alignment, overflow, contrast and empty states; fix, re-run, repeat.
* **Chromium**: Playwright uses the pre-installed browser (`executablePath` from `/opt/pw-browsers` when versions differ).

---

## 18. Build and backend integration

* `npm run dev`: Vite on :5173 with the proxy `/api` → `http://localhost:8000` and `/ws` → `ws://localhost:8000` (ws: true).
* `npm run build`: `web/dist`, served by FastAPI (backend plan §10.4) at `/`, with SPA fallback.
* `npm run gen:api`: `python -m server.dump_openapi > src/api/openapi.json && openapi-typescript src/api/openapi.json -o src/api/schema.d.ts`. Both files are committed; CI checks that they are up to date.
* `npm run check`: tsc + eslint + vitest.
* `npm run e2e`: Playwright (needs Python deps installed).
* Environment: `VITE_API_BASE` (optional, for split hosting).

---

## 19. Implementation order and acceptance

1. Scaffold (Vite, TS, lint), tokens, base styles, fonts, the shell (NavRail / TopBar / BottomNav), routing with lazy pages, providers.
2. API client + generated types; WS manager + router + stores; ConnectionPill; toasts; ErrorBoundary; degraded banner.
3. Primitives (§8) and the charts kit (§9) with a hidden `/__kit` route for development review (excluded from the nav, kept for QA).
4. Backdrop, cursor, page transitions, boot sequence, command palette, Explain drawer, settings.
5. Scene kit (§10) with the 2D fallbacks.
6. Pages in order: Command Center → Studio → Attack Lab → Overview → Playground → Analytics → Ledger → Incidents + Session → Method → 404.
7. Mobile pass, then the accessibility pass, then the performance pass.
8. Playwright suites + screenshot review iterations (at least two full passes).

**Accepted when**:
* all routes render live data at desktop and mobile sizes with zero console errors;
* the flows in §17 pass;
* budgets are met or deviations documented;
* reduced-motion mode is fully usable;
* no hard-coded metric values exist in the source (`grep` check for numeric literals in feature components outside tokens/animation constants is part of the review).

---

## 20. Copy and tone

* **Voice**: precise, calm, confident. Physics terms are used correctly and always link to Explain.
* **Numbers** carry units and uncertainty ("1.02 % [0.96, 1.08]", "ε_forge ≤ 9.6 × 10⁻⁷").
* **Never** "unhackable", "100% secure" or "AI-powered". **Always** "detected", "certified", "bounded by".
* **Honesty statements** appear where they apply, e.g. on replay: "Replay is physically invisible — the protocol layer catches it"; on equivalent channels: "These explanations describe the same channel; no measurement can separate them".
* **Empty states** say what is missing and how to create it, in one sentence plus one action.
