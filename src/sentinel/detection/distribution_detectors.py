"""
sentinel/detection/distribution_detectors.py
============================================
Detectors D1-D9 on the evidence of one distribution.

Each detector returns a :class:`Finding`. Statistical findings are first
marked ``candidate`` (their raw p-value and effect); :func:`apply_holm`
then applies the Holm-Bonferroni correction across the whole distribution
and sets ``fired`` only for findings that are significant **and** clear their
effect-size floor.

====  ================================  ======================================
 id    name                              statistic
====  ================================  ======================================
 D1    entanglement.chsh_certificate     CHSH lower confidence bound vs 2
 D2    entanglement.chsh_drift           z-test of S vs baseline S0
 D3a   entanglement.witness_certificate  fidelity lower bound vs 1/2
 D3b   entanglement.witness_drift        witness disagreements vs baseline
 D4    channel.qber_excess               per-basis QBER vs baseline
 D5    channel.tomography_deviation      chi-square on de-twirled cells
 D6    classical.frame_integrity         correction-bit mismatches / MAC
 D7    source.bell_consistency           key QBER vs Bell-predicted QBER
 D8    source.copy_consistency           recipient copies against each other
 D9    security.margin                   threshold design feasibility
====  ================================  ======================================
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats as _st

from sentinel.detection.baseline import LinkBaseline
from sentinel.detection.config import DetectionConfig
from sentinel.detection.findings import Finding
from sentinel.detection.fingerprint import classify_channel
from sentinel.protocol.distribution import LinkEvidence
from sentinel.protocol.thresholds import ThresholdDesign
from sentinel.stats import P_FLOOR, chi2_homogeneity, clopper_pearson, holm, holm_thresholds, two_proportion_test

__all__ = ["link_detectors", "copy_consistency", "margin_finding", "apply_holm", "STATISTICAL_IDS"]

STATISTICAL_IDS = {"D2.chsh_drift", "D3b.witness_drift", "D4.qber_excess", "D5.tomography_deviation",
                   "D7.bell_consistency", "D8.copy_consistency"}


def _bonf(p: float, m: int) -> float:
    return float(min(1.0, max(P_FLOOR, p * m)))


def link_detectors(ev: LinkEvidence, base: LinkBaseline, cfg: DetectionConfig) -> list:
    """Run D1-D7 for one link."""
    out = []
    b, b0 = ev.bell, base.bell
    lid = ev.link_id

    # D1 CHSH certificate
    fired = b.S_lcb <= 2.0
    out.append(Finding(
        id="D1.chsh_certificate", name="CHSH entanglement certificate", layer="entanglement", link_id=lid,
        fired=fired, severity="CRITICAL" if fired else "NONE", conclusive=True,
        statistic={"name": "S_lcb", "value": b.S_lcb},
        evidence=(f"CHSH S = {b.S:.3f} (lower bound {b.S_lcb:.3f}) does not exceed the local bound 2: the pairs are "
                  f"consistent with a classical source, so entanglement is not certified.") if fired else
        f"CHSH S = {b.S:.3f}, lower bound {b.S_lcb:.3f} > 2: Bell violation certified.",
        data={"S": b.S, "S_lcb": b.S_lcb, "S_se": b.S_se, "tsirelson": 2 * math.sqrt(2), "E": b.E},
    ))

    # D2 CHSH drift
    se = math.hypot(b.S_se, b0.S_se) or 1e-12
    z = (b0.S - b.S) / se
    p = float(_st.norm.sf(z))
    eff = b0.S - b.S
    out.append(Finding(
        id="D2.chsh_drift", name="CHSH drift vs baseline", layer="entanglement", link_id=lid, fired=False,
        severity="HIGH" if eff >= 0.25 else "MEDIUM", statistic={"name": "z", "value": z}, p_value=max(p, P_FLOOR),
        effect={"name": "ΔS", "value": eff, "floor": cfg.floor_chsh_drop},
        evidence=f"S = {b.S:.3f} vs baseline {b0.S:.3f} (ΔS = {eff:+.3f}, z = {z:.1f})",
        data={"S": b.S, "S0": b0.S, "S_se": b.S_se, "S0_se": b0.S_se},
    ))

    # D3a witness certificate
    fired = b.F_lcb <= 0.5
    out.append(Finding(
        id="D3a.witness_certificate", name="Entanglement witness certificate", layer="entanglement", link_id=lid,
        fired=fired, severity="CRITICAL" if fired else "NONE", conclusive=True,
        statistic={"name": "F_lcb", "value": b.F_lcb},
        evidence=(f"Fidelity with |Φ+⟩ F = {b.F:.3f} (lower bound {b.F_lcb:.3f}) ≤ 1/2: no entanglement certified.")
        if fired else f"Fidelity F = {b.F:.3f} (lower bound {b.F_lcb:.3f}) > 1/2.",
        data={"F": b.F, "F_lcb": b.F_lcb},
    ))

    # D3b witness drift: per-basis disagreement fractions vs baseline
    pmin, parts = 1.0, {}
    for basis in ("x", "y", "z"):
        cur, ref = b.predicted_error[basis], b0.predicted_error[basis]
        t = two_proportion_test(cur["errors"], cur["n"], ref["errors"], ref["n"], "greater")
        parts[basis] = {"rate": cur["rate"], "baseline": ref["rate"], "p": t["p_value"]}
        pmin = min(pmin, t["p_value"])
    effF = b0.F - b.F
    out.append(Finding(
        id="D3b.witness_drift", name="Witness drift vs baseline", layer="entanglement", link_id=lid, fired=False,
        severity="HIGH" if effF >= 0.05 else "MEDIUM", statistic={"name": "min_p_basis", "value": pmin},
        p_value=_bonf(pmin, 3), effect={"name": "ΔF", "value": effF, "floor": cfg.floor_fidelity_drop},
        evidence=f"F = {b.F:.3f} vs baseline {b0.F:.3f} (ΔF = {effF:+.3f})", data={"per_basis": parts},
    ))

    # D4 QBER excess (per basis + overall, Bonferroni within)
    q, q0 = ev.qber, base.qber
    parts, pmin, max_delta = {}, 1.0, -1.0
    for key in ("x", "y", "z", "overall"):
        cur = q["per_basis"][key] if key != "overall" else {"errors": q["errors"], "n": q["n"], "rate": q["rate"]}
        ref = q0["per_basis"][key] if key != "overall" else {"errors": q0["errors"], "n": q0["n"], "rate": q0["rate"]}
        t = two_proportion_test(cur["errors"], cur["n"], ref["errors"], ref["n"], "greater")
        parts[key] = {"rate": cur["rate"], "ci": list(clopper_pearson(cur["errors"], cur["n"], 0.05)),
                      "baseline": ref["rate"], "n": cur["n"], "p": t["p_value"]}
        pmin = min(pmin, t["p_value"])
        max_delta = max(max_delta, cur["rate"] - ref["rate"])
    sev = "HIGH" if max_delta >= 0.05 else "MEDIUM" if max_delta >= 0.02 else "LOW"
    out.append(Finding(
        id="D4.qber_excess", name="QBER excess vs baseline", layer="channel", link_id=lid, fired=False, severity=sev,
        statistic={"name": "qber", "value": q["rate"]}, p_value=_bonf(pmin, 4),
        effect={"name": "Δe", "value": max_delta, "floor": cfg.floor_qber_rise},
        evidence=f"QBER {100 * q['rate']:.2f}% vs baseline {100 * q0['rate']:.2f}% (largest per-basis rise "
                 f"{100 * max_delta:+.2f} points)",
        data={"per_basis": parts},
    ))

    # D5 tomography deviation (de-twirled)
    cur, ref = ev.detwirled, base.detwirled
    chi = chi2_homogeneity(cur.plus, cur.n, ref.plus, ref.n)
    eff_chi = chi2_homogeneity(ev.effective.plus, ev.effective.n, base.effective.plus, base.effective.n)
    dev = float(np.max(np.abs(cur.r - ref.r)))
    fp = classify_channel(ref, cur)
    sev = "HIGH" if dev >= 0.1 else "MEDIUM"
    out.append(Finding(
        id="D5.tomography_deviation", name="De-twirled channel tomography", layer="channel", link_id=lid, fired=False,
        severity=sev, statistic={"name": "chi2", "value": chi["statistic"]}, p_value=chi["p_value"],
        effect={"name": "max|Δr|", "value": dev, "floor": cfg.floor_tomography},
        evidence=f"χ² = {chi['statistic']:.1f} on {chi['df']} cells (twirled view χ² = {eff_chi['statistic']:.1f}); "
                 f"largest Bloch deviation {dev:.3f}. {fp.summary}",
        data={"chi2": chi, "effective_chi2": eff_chi, "fingerprint": fp.as_dict(),
              "M": cur.M.tolist(), "c": cur.c.tolist(), "M0": ref.M.tolist(), "c0": ref.c.tolist(),
              "effective_M": ev.effective.M.tolist(), "effective_c": ev.effective.c.tolist()},
    ))

    # D6 classical frame integrity
    fr = ev.frame
    mac_fail = fr.get("mac") == "fail"
    fired = mac_fail or fr["mismatched"] > 0
    if mac_fail:
        evid = "Wegman–Carter MAC over the correction-bit stream failed: the classical teleportation channel was altered."
    elif fired:
        evid = (f"{fr['mismatched']} of {fr['compared']} sampled correction-bit pairs differ between signer and "
                f"verifier ({100 * fr['rate']:.2f}%; m0 flips {100 * fr['flip_rates']['m0']:.2f}%, "
                f"m1 flips {100 * fr['flip_rates']['m1']:.2f}%). Classical channels carry no natural bit errors.")
    else:
        evid = f"All {fr['compared']} sampled correction-bit pairs agree" + (" and the MAC verified." if fr.get("mac") == "ok" else ".")
    out.append(Finding(
        id="D6.frame_integrity", name="Classical frame integrity", layer="classical", link_id=lid, fired=fired,
        severity="CRITICAL" if fired else "NONE", conclusive=True,
        statistic={"name": "tamper_rate", "value": fr["rate"]}, evidence=evid, data=fr,
    ))

    # D7 Bell-predicted vs observed key QBER (two-sided)
    parts, pmin = {}, 1.0
    ke = kn = be = bn = 0
    for basis in ("x", "y", "z"):
        kq = q["per_basis"][basis]
        bp = b.predicted_error[basis]
        t = two_proportion_test(kq["errors"], kq["n"], bp["errors"], bp["n"], "two-sided")
        parts[basis] = {"key_rate": kq["rate"], "bell_rate": bp["rate"], "p": t["p_value"]}
        pmin = min(pmin, t["p_value"])
        ke += kq["errors"]; kn += kq["n"]; be += bp["errors"]; bn += bp["n"]
    key_rate = ke / kn if kn else 0.0
    bell_rate = be / bn if bn else 0.0
    delta = key_rate - bell_rate
    direction = "excess" if delta > 0 else "deficit"
    out.append(Finding(
        id="D7.bell_consistency", name="Source honesty (Bell-predicted vs key QBER)", layer="source", link_id=lid,
        fired=False, severity="HIGH", statistic={"name": "Δ", "value": delta}, p_value=_bonf(pmin, 3),
        effect={"name": "|Δ|", "value": abs(delta), "floor": cfg.floor_consistency},
        evidence=(f"Key-state QBER {100 * key_rate:.2f}% vs {100 * bell_rate:.2f}% predicted by the Bell test on the same "
                  f"link ({direction} {100 * abs(delta):.2f} points). "
                  + ("Excess: the key states are worse than the channel explains, so the source did not send what it claims."
                     if delta > 0 else "Deficit: the key states did not travel the path the test pairs did (relay / man-in-the-middle).")),
        data={"per_basis": parts, "key_rate": key_rate, "bell_rate": bell_rate, "direction": direction},
    ))
    return out


def copy_consistency(ev_a: LinkEvidence, ev_b: LinkEvidence, cfg: DetectionConfig) -> Finding:
    """D8: the two recipients' copies against each other."""
    qa, qb = ev_a.qber, ev_b.qber
    t = two_proportion_test(qa["errors"], qa["n"], qb["errors"], qb["n"], "two-sided")
    delta = qa["rate"] - qb["rate"]
    worse = ev_a.verifier_id if delta > 0 else ev_b.verifier_id
    return Finding(
        id="D8.copy_consistency", name="Recipient copy consistency", layer="source", fired=False, severity="HIGH",
        statistic={"name": "Δ", "value": delta}, p_value=t["p_value"],
        effect={"name": "|Δ|", "value": abs(delta), "floor": cfg.floor_consistency},
        evidence=f"{ev_a.verifier_id}'s copy QBER {100 * qa['rate']:.2f}% vs {ev_b.verifier_id}'s {100 * qb['rate']:.2f}% "
                 f"(|Δ| = {100 * abs(delta):.2f} points; {worse}'s copy is worse).",
        data={"rates": {ev_a.verifier_id: qa["rate"], ev_b.verifier_id: qb["rate"]}, "worse_copy": worse},
    )


def margin_finding(design: ThresholdDesign) -> Finding:
    """D9: can thresholds be designed at the measured error rate?"""
    fired = not design.feasible
    return Finding(
        id="D9.security_margin", name="Security margin", layer="security", fired=fired,
        severity="MEDIUM" if fired else "NONE", conclusive=True,
        statistic={"name": "e_ucb", "value": design.e_ucb},
        evidence=(f"At the measured error bound {100 * design.e_ucb:.2f}% no thresholds s_a < s_v meet the targets for "
                  f"L = {design.L}" + (f"; L ≥ {design.L_min} would." if design.L_min else ".")) if fired else
        f"Thresholds s_a = {design.s_a:.4f} < s_v = {design.s_v:.4f} at error bound {100 * design.e_ucb:.2f}%.",
        data={"design": design.as_dict()},
    )


def apply_holm(findings: list, alpha: float) -> None:
    """Holm correction across statistical findings; sets ``fired`` and ``candidate`` in place."""
    stat = [f for f in findings if f.id in STATISTICAL_IDS and f.p_value is not None]
    if not stat:
        return
    pvals = [f.p_value for f in stat]
    rej = holm(pvals, alpha)
    thr = holm_thresholds(pvals, alpha)
    for f, r, a in zip(stat, rej, thr):
        f.alpha = a
        f.candidate = bool(r)
        eff_ok = f.effect is None or f.effect["value"] >= f.effect["floor"]
        f.fired = bool(r and eff_ok)
        if not f.fired:
            f.severity = "NONE" if not r else f.severity
            if r and not eff_ok:
                f.evidence += f" — statistically significant but below the effect floor {f.effect['floor']}."
                f.severity = "NONE"
