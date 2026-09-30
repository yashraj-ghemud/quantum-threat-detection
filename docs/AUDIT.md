# Audit: cross-questions put to QVeris, with verified answers

This audit questioned the running system the way a judge would. Every answer below was checked against the live engine (`python -m server`, `standard` preset) or is pinned by a test. Where a question exposed a defect, the defect was fixed. The answer says what was wrong and names the test that now guards it.

Legend: **fixed** (a defect was found and fixed in this audit), **holds** (the behaviour was already correct and is now verified), **limit** (an honest limitation, stated in the UI).

---

## Operator responses: do the buttons really change the network?

### Q1. If I quarantine a link, can a signer still sign with bundles it already holds? (fixed)
- **Before:** Yes. Quarantine only stopped new distributions. ACTIVE bundles certified earlier on that link could still be used to sign.
- **Now:** `World.sign` refuses any group whose links include a quarantined link, and the API returns `409 LINK_QUARANTINED`.
- **Traffic:** the traffic worker pauses that group and publishes a `system.notice` ("traffic pauses g-alice: link alice-bob is quarantined").
- **UI:** the Command Center shows a blocked-traffic banner.
- **Release:** releasing the link resumes signing.
- **Test:** `tests/server/test_api.py::test_quarantine_blocks_signing_with_existing_bundles`.

### Q2. Can the operator stop a compromised signer, not just a link? (fixed)
- **Endpoints:** new `POST /network/nodes/{id}/suspend` and `/reinstate`.
- **While suspended:** signing is refused with `409 SIGNER_SUSPENDED`, and the reservoir reports `blocked_reason`.
- **Ledger:** both actions append `SIGNER_SUSPENDED` / `SIGNER_REINSTATED` transactions.
- **Incidents:** repudiation incidents recommend *Suspend signer*, and an incident can also *Reinstate* the signer.
- **Command Center:** select a signer node, then use *Suspend signer*.
- **Adversary nodes:** these cannot be suspended (404); they are not part of the network.
- **Test:** `test_suspend_and_reinstate_signer`.

### Q3. Does the MAC toggle on a link do anything? (holds, verified live)
The same `channel.pauli_frame` attack at intensity 0.5 was run on `g-alice`:

| MAC | What D6.frame_integrity reports |
|---|---|
| off | "58240 of 233472 sampled correction-bit pairs differ between signer and verifier (24.95 %)". The flips are caught statistically. |
| on | "Wegman–Carter MAC over the correction-bit stream failed: the classical teleportation channel was altered." The stream is rejected outright. |

### Q4. Does revoking a bundle actually remove it? (holds, verified live)
Revoking every ACTIVE bundle of a group empties its reservoir gauge. The next signature then triggers a fresh distribution, or is refused when auto-distribution is off.

### Q5. Do the detection settings and presets change behaviour, or are they cosmetic? (holds, verified live)
- Raising a detector's floor changes which detectors fire on the same attack.
- Switching the preset changes the key length that is actually used (L = 1024 for `demo`, 4096 for `standard`) and the resulting ε bounds.

## Detection honesty: does it cry wolf?

### Q6. After an attack ends, does the drift monitor go quiet again? (fixed, two defects)
The CUSUM (D10) exists for shifts too small for any single run. Two defects made it keep flagging honest traffic after an attack:

1. **A strong attack poisoned it.** The run added a huge excess, and honest bundles alarmed for a long time afterwards.
   - **Fix:** runs already flagged HIGH or above on that link by single-run detectors are excluded from the accumulator.
   - **Test:** `test_flagged_runs_do_not_poison_the_drift_monitor`.
2. **A moderate attack left it stuck above its limit.** Here single-run detectors rated the attacked link below HIGH, so the run correctly fed the CUSUM, which signalled. The statistic then drains by only about k per honest run, so every honest bundle kept alarming. On the live server this flagged **7 honest g-alice bundles over about 4 minutes** after a blitz campaign, and they showed up as "false rejections".
   - **Fix:** Page's restart rule. Once a CUSUM signals, the alarm is handed to the incident and the accumulator restarts from 0. A drift that persists re-alarms after its run length; one that stopped does not.
   - **Offline reproduction** (`channel.depolarize` at 0.12, seed 93): honest bundles flagged afterwards went from `[1, 1, 1, 0, 0, 0, 0, 0]` before the fix to all 0 after it.
   - **Live after the fix:** the same attack was run (the CUSUM signalled on the attack run itself), followed by 6 honest distributions. All 6 were CERTIFIED with no finding.
   - **Test:** `test_drift_alarm_restarts_instead_of_flagging_honest_traffic`.
   - **Low-and-slow attacks** are still caught: `test_low_and_slow_drift_still_accumulates`.

### Q7. Is the "false rejections" figure what it says? (fixed wording)
- **The problem:** the metric counts every honest run that was *flagged*. That includes distributions that stayed CERTIFIED but carried a MEDIUM drift finding, which are not rejections.
- **Fix:** the Command Center and Overview now label it **False alarms** ("honest runs flagged"). The exact Clopper–Pearson interval is kept.
- **Analytics:** the *false rejection* figure there still means rejected honest signatures, which is what that job measures.

### Q8. Does the threat level ever come back down? (fixed)
- **Before:** the pill showed the worst severity of incidents *updated in the last 30 minutes*. It dropped on its own even with critical incidents still open, and stayed red after everything was resolved until the window passed.
- **Now:** it is the worst severity among **OPEN** incidents. Resolve or dismiss them and it clears immediately. The tooltip says so.
- **Test:** `test_threat_level_follows_open_incidents`.

### Q9. Are the campaign results real? (holds, verified live)
- **Blitz campaign:** 8 attacks mixed, 30/min for 20 s on `g-alice`. It completed **7 runs, 7 detected, 7 correctly classified**.
- **Rows:** each run is a real session row with its injected attack recorded next to the engine's independent verdict.
- **Detection rate:** computed from those rows by SQL (`category = attack_category`).

## Signatures: try to break one

### Q10. What happens if I replay a valid signature, or deliver it late? (holds, now in the UI)
Live, on a freshly ACCEPTED signature:

| Action | Verdict | Findings that fired |
|---|---|---|
| Replay it as is | REJECTED · REPLAY/resubmission | S3.bundle_state, S4.nonce, S5.sequence |
| Deliver it 300 s late | REJECTED · REPLAY/resubmission | S3, S4, S5 and **S6.freshness** ("signature is 318.4 s old; window is 120 s") |
| Forge an altered copy (external blind forger, same message) | REJECTED · FORGERY/external blind | 124 of 256 keys failed at bob (threshold 5.86 %); mismatch ≈ 1/2, as guessing predicts |

- **UI:** these three attacks are now one click away, in the new **Try to break it** panel in the Signature Studio and on every accepted signature's report page. Each button calls the real endpoint (`/signatures/{id}/reverify`, `/attacks/run`) and shows the engine's own verdict and evidence.
- **Late delivery:** the panel shows the freshness evidence specifically.
- **Test:** `test_reverify_is_rejected_as_replay`.

### Q11. If someone edits the ledger database, does the inclusion proof still say "intact"? (fixed)
- **Before:** the Merkle proof started from the *stored* hash, so a rewritten row still proved "included".
- **Now:** `GET /ledger/tx/{id}` recomputes `sha256(canonical_json(payload))`, returns `computed_hash` and `valid`, and the proof starts from the recomputed hash. The drawer shows a mismatch banner.
- **Test:** `test_ledger_tamper_detect_revert`.

## Honest limits (stated in the UI)

- **Q12. Is the traffic real?** The *engine run* is real: every live signature is a full distribution, teleportation, verification and detector cascade. The *message text* of background traffic is synthetic (payment and memo templates), and the Command Center feed says so. Anything you type in the Studio is signed as typed.
- **Q13. Can QSentinel see a replay in the quantum data?** No. A replay's quantum statistics are perfect. The protocol guard catches it (S3–S6), and the UI names the layer that caught it.
- **Q14. Is there quantum hardware?** No. Channels, Bell sources and detectors are simulated exactly and agree with Qiskit Aer to 4.4 × 10⁻¹⁶.

---

## Interface defects found and fixed in the same audit

| Where | Defect | Fix |
|---|---|---|
| Overview · "Eight steps, measured" | 6 of 8 cards flickered to "not measured yet" under live traffic. Every event changed the latest-session id, and the new detail query started empty. | Keep the previous report while the next loads; bind only to honest runs (`attack=false`) |
| Legacy 3D scenes in Noir | Pastel sky and floor in the dark theme; dark ket labels (dark on dark); unreadable brand text | Scenes take the theme: dark world palette, light ket labels. The Noir CSS is injected last in `<head>` so it overrides template variables. Scenes rebuild on theme change. |
| Command Center | No way to act on a node or link from the map | Selecting a signer offers *Suspend / Reinstate*. Selecting a quantum link offers *Quarantine / Release* and *MAC on / off*, all against the live API. |
| Command Center | The detail card was translucent, so labels behind it showed through | Opaque surface |
| Command Center | Paused traffic was invisible | Banner naming each blocked group and the reason |
| Threat pill | Tooltip described the old 30-minute window | Describes the OPEN-incident rule |
| Incidents / Attack Lab | The new `reinstate_signer` response had no label | Labelled |

## How to reproduce

```bash
make test         # Python tests (engine, protocol, detection, API) plus web type-check and unit tests
make e2e          # Playwright, desktop and mobile
./scripts/dev.sh  # then try the Command Center actions and the Studio "Try to break it" panel
```
