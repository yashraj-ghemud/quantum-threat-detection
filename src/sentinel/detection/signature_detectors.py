"""
sentinel/detection/signature_detectors.py
=========================================
Signature-time detectors (S7-S10). S1-S6 live in :mod:`sentinel.protocol.guard`.

S9 is forensic attribution. It reads the *pattern* of failures to say what
the forger knew:

- failures on nearly every key          -> no genuine key material (keyless impersonation)
- failures only where the digest differs, mismatch ~1/2 -> blind external forger
- mismatch ~1/3                          -> informed forger holding a measurement record
- own set fails while the set forwarded by the peer passes perfectly
                                         -> the forger knew the peer's records: insider (the peer)
"""

from __future__ import annotations

import numpy as np

from sentinel.detection.findings import Finding
from sentinel.protocol.verification import VerificationReport
from sentinel.stats import binom_sf, clopper_pearson, two_proportion_test

__all__ = ["key_tests", "sprt_finding", "forensics", "transfer_consistency"]


def key_tests(rep: VerificationReport, e_ucb: float) -> Finding:
    failed = rep.failed_keys
    fired = len(failed) > 0
    worst_p = 1.0
    if fired:
        for i in failed:
            for n, m in ((rep.n_own[i], rep.m_own[i]), (rep.n_recv[i], rep.m_recv[i])):
                if n > 0:
                    worst_p = min(worst_p, binom_sf(int(m), int(n), max(e_ucb, 1e-9)))
    inc = int(rep.inconclusive.sum())
    K = rep.passed.size
    return Finding(
        id="S7.key_tests", name=f"Key mismatch tests ({rep.verifier_id})", layer="signature", fired=fired,
        severity="CRITICAL" if fired else "NONE", conclusive=False,
        statistic={"name": "failed_keys", "value": len(failed)}, p_value=worst_p if fired else None,
        evidence=(f"{len(failed)} of {K} keys failed at {rep.verifier_id} (threshold {100 * rep.threshold:.2f}%"
                  + (f", {inc} inconclusive" if inc else "") + f"); overall mismatch {rep.mismatches}/{rep.tested}."
                  + (f" The worst set has probability {worst_p:.1e} under honest noise." if fired else ""))
        if fired else f"All {K} keys passed at {rep.verifier_id}: {rep.mismatches}/{rep.tested} mismatches "
                      f"({100 * rep.mismatches / max(rep.tested, 1):.2f}%) against threshold {100 * rep.threshold:.2f}%.",
        data={"verifier_id": rep.verifier_id, "failed_keys": failed[:64], "n_failed": len(failed), "keys": K,
              "rate": rep.mismatches / max(rep.tested, 1), "threshold": rep.threshold, "inconclusive": inc},
    )


def sprt_finding(rep: VerificationReport) -> Finding:
    s = rep.sprt or {}
    fired = bool(s.get("early_reject"))
    used, avail = s.get("observations_used", 0), s.get("observations_available", 0)
    return Finding(
        id="S8.sprt", name=f"Sequential early abort ({rep.verifier_id})", layer="signature", fired=fired,
        severity="CRITICAL" if fired else "NONE",
        statistic={"name": "fraction_read", "value": s.get("fraction_read", 1.0)},
        evidence=(f"Wald SPRT rejected key {s.get('reject_key')} after reading {used} of {avail} tested positions "
                  f"({100 * used / max(avail, 1):.1f}%).") if fired else
        (f"No early rejection; all {avail} tested positions read." if s.get("enabled") else "SPRT disabled."),
        data={k: v for k, v in s.items() if k != "traces"},
    )


def forensics(rep: VerificationReport, e_ucb: float, peer_id: str) -> Finding | None:
    """S9: who could have produced these failures?"""
    failed = rep.failed_keys
    if not failed:
        return None
    K = rep.passed.size
    frac = len(failed) / K
    fi = np.asarray(failed)
    n_own, m_own = int(rep.n_own[fi].sum()), int(rep.m_own[fi].sum())
    n_recv, m_recv = int(rep.n_recv[fi].sum()), int(rep.m_recv[fi].sum())
    n_all, m_all = n_own + n_recv, m_own + m_recv
    rate = m_all / n_all if n_all else 0.0
    lo, hi = clopper_pearson(m_all, n_all, 1e-3) if n_all else (0.0, 1.0)
    own_rate = m_own / n_own if n_own else 0.0
    recv_rate = m_recv / n_recv if n_recv else 0.0
    asym = two_proportion_test(m_own, n_own, m_recv, n_recv, "greater") if n_own and n_recv else {"p_value": 1.0}
    recv_hi = clopper_pearson(m_recv, n_recv, 1e-3)[1] if n_recv else 1.0

    attributed = None
    if (n_recv and asym["p_value"] < 1e-6 and recv_hi < e_ucb + 0.02 and own_rate > 0.2 and rep.mode == "symmetrized"):
        label, conf = "INSIDER", "statistical"
        attributed = peer_id
        text = (f"On the failed keys, the set {peer_id} forwarded matched the declared labels "
                f"({100 * recv_rate:.2f}% mismatch, honest level) while {rep.verifier_id}'s own set shows "
                f"{100 * own_rate:.1f}% (≈ 1/3). Only a holder of {peer_id}'s measurement records can do that: "
                f"the forgery is attributed to {peer_id}.")
    elif frac >= 0.9:
        label, conf = "KEYLESS", "statistical"
        text = (f"{len(failed)} of {K} keys failed ({100 * frac:.0f}%) with mismatch {100 * rate:.1f}%: the signature "
                f"carries no genuine key material. Consistent with an impersonator claiming the signer's bundle.")
    elif lo <= 0.5 <= hi and not (lo <= 1 / 3 <= hi):
        label, conf = "EXTERNAL_BLIND", "statistical"
        text = (f"{len(failed)} keys failed with mismatch {100 * rate:.1f}% [{100 * lo:.1f}, {100 * hi:.1f}] ≈ 1/2: "
                f"labels guessed without any measurement record (external forger modifying a genuine signature).")
    elif lo <= 1 / 3 <= hi:
        label, conf = "INFORMED", "statistical"
        text = (f"{len(failed)} keys failed with mismatch {100 * rate:.1f}% ≈ 1/3: the forger held a measurement "
                f"record of the key states (a recipient or an eavesdropper who measured them).")
    else:
        label, conf = "UNATTRIBUTED", "indicative"
        text = f"{len(failed)} keys failed with mismatch {100 * rate:.1f}% [{100 * lo:.1f}, {100 * hi:.1f}]."
    return Finding(
        id="S9.forensics", name=f"Forensic attribution ({rep.verifier_id})", layer="signature", fired=True,
        severity="HIGH", statistic={"name": "failed_mismatch_rate", "value": rate},
        evidence=text,
        data={"label": label, "confidence": conf, "attributed_to": attributed, "failed_fraction": frac,
              "n_failed": len(failed), "rate": rate, "rate_ci": [lo, hi], "own_rate": own_rate,
              "recv_rate": recv_rate, "asymmetry_p": asym["p_value"], "peer": peer_id},
    )


def transfer_consistency(first: VerificationReport | None, transfer: VerificationReport | None) -> Finding:
    dispute = bool(first and transfer and first.decision == "ACCEPT" and transfer.decision == "REJECT")
    return Finding(
        id="S10.transfer_consistency", name="Transferability", layer="signature", fired=dispute,
        severity="HIGH" if dispute else "NONE",
        evidence=(f"{first.verifier_id} accepted but {transfer.verifier_id} rejected the forwarded signature: a dispute, "
                  f"the outcome a repudiating signer wants.") if dispute else
        ("Both recipients reached the same decision." if first and transfer else "Transfer not performed."),
        data={"first": first.decision if first else None, "transfer": transfer.decision if transfer else None},
    )
