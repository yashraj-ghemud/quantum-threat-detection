"""
sentinel/detection/fusion.py
============================
Deterministic decision lists that turn findings into an Assessment.

No weights are learned and no score is thresholded to decide: the first
matching rule wins, and the rule is reported with the decision.
"""

from __future__ import annotations

from sentinel.detection.findings import Assessment, Classification, SEVERITY_RANK, max_severity, threat_score

__all__ = ["fuse_distribution", "fuse_signature", "ACTIONS"]

ACTIONS = {
    "CHANNEL_MANIPULATION": ["quarantine_link", "recertify_link", "revoke_link_bundles"],
    "classical_frame": ["enable_mac", "quarantine_link"],
    "UNAUTHORIZED_VERIFICATION/key_harvest": ["quarantine_link", "revoke_link_bundles", "recertify_link"],
    "UNAUTHORIZED_VERIFICATION": ["deny_principal"],
    "REPUDIATION": ["suspend_signer", "escalate_dispute"],
    "FORGERY": ["flag_principal", "notify_recipients"],
    "IMPERSONATION": ["flag_principal", "notify_recipients"],
    "REPLAY": ["review_capture_source"],
    "DEGRADED": ["recertify_link", "use_larger_L"],
    "POLICY": [],
    "NONE": [],
}


def _fired(findings, prefix):
    return [f for f in findings if f.fired and f.id.startswith(prefix)]


def _actions(cat: str, sub: str | None) -> list:
    if sub == "classical_frame":
        return ACTIONS["classical_frame"]
    if cat == "UNAUTHORIZED_VERIFICATION" and sub == "key_harvest":
        return ACTIONS["UNAUTHORIZED_VERIFICATION/key_harvest"]
    return ACTIONS.get(cat, [])


def fuse_distribution(findings: list) -> Assessment:
    """Distribution decision list (backend plan section 6.5.2)."""
    frame = _fired(findings, "D6.")
    cert = _fired(findings, "D1.") + _fired(findings, "D3a.")
    chsh_drift = _fired(findings, "D2.")
    witness_drift = _fired(findings, "D3b.")
    qber = _fired(findings, "D4.")
    tomo = _fired(findings, "D5.")
    d7 = _fired(findings, "D7.")
    d7_excess = [f for f in d7 if f.data.get("direction") == "excess"]
    d7_deficit = [f for f in d7 if f.data.get("direction") == "deficit"]
    d8 = _fired(findings, "D8.")
    margin = _fired(findings, "D9.")
    cusum = _fired(findings, "D10.")

    def fp_of(link=None):
        cands = [f for f in findings if f.id.startswith("D5.") and (link is None or f.link_id == link)]
        cands.sort(key=lambda f: f.effect["value"] if f.effect else 0, reverse=True)
        return cands[0].data.get("fingerprint") if cands else None

    cls = Classification()
    ent_bad_links = {f.link_id for f in cert + chsh_drift + witness_drift + d7_deficit}
    if frame and any(f.link_id in ent_bad_links for f in frame):
        link = next(f.link_id for f in frame if f.link_id in ent_bad_links)
        rate = next(f.data.get("rate", 0) for f in frame if f.link_id == link)
        cls = Classification(
            "UNAUTHORIZED_VERIFICATION", "key_harvest", "conclusive", "D6 ∧ (D1 ∨ D3 ∨ D2 ∨ D7↓)",
            f"On {link} the correction bits the verifier received differ from those the signer sent "
            f"({100 * rate:.1f}% of sampled positions), and the link lost entanglement or its key states "
            f"bypassed the test pairs' path. Someone relayed the teleportation: a man-in-the-middle harvesting "
            f"public-key states to verify or forge without authorization.",
            ["entanglement-swapping relay that measures the key states"])
    elif frame:
        f0 = frame[0]
        fl = f0.data.get("flip_rates", {})
        which = "m0 (phase)" if fl.get("m0", 0) > fl.get("m1", 0) else "m1 (bit)"
        cls = Classification(
            "CHANNEL_MANIPULATION", "classical_frame", "conclusive", "D6",
            f"The classical half of teleportation was tampered with on {f0.link_id}: correction bits were flipped "
            f"in transit (mostly {which}), so the verifier applied the wrong Pauli correction. The quantum channel "
            f"itself tests clean.",
            ["man-in-the-middle on the classical channel", "a faulty correction-bit transmitter"])
    elif cert:
        link = cert[0].link_id
        fp = fp_of(link) or {}
        shape = fp.get("shape") or "entanglement_break"
        if shape in ("none", "general_pauli"):
            shape = "entanglement_break"
        cls = Classification(
            "CHANNEL_MANIPULATION", shape, "conclusive", "D1 ∨ D3a",
            f"Entanglement on {link} could not be certified (no Bell violation beyond confidence). "
            + (fp.get("summary", "") if fp else ""),
            (fp.get("alternatives", []) if fp else []) + ["intercept–resend (measuring the pairs breaks entanglement)"])
    elif d7_excess and not {f.link_id for f in d7_excess} & ent_bad_links:
        link = d7_excess[0].link_id
        if d8:
            cls = Classification(
                "REPUDIATION", "inconsistent_keys", "statistical", "D7↑ ∧ D8 ∧ channel clean",
                f"The link to {link} is certified clean by its Bell test, yet its key states carry excess errors, and "
                f"the two recipients' copies disagree. The signer did not send the states it claims: preparation "
                f"for a repudiation dispute. Symmetrization prevents the dispute; this evidence names the cause.",
                ["a faulty or dishonest source"])
        else:
            cls = Classification(
                "REPUDIATION", "source_fault", "statistical", "D7↑ ∧ channel clean",
                f"Key states on {link} carry more errors than its certified channel explains: the source is not "
                f"sending the states it claims.", ["a faulty source"])
    elif chsh_drift or witness_drift or qber or tomo or d7:
        links = [f.link_id for f in (tomo + qber + chsh_drift + witness_drift + d7) if f.link_id]
        link = links[0] if links else None
        fp = fp_of(link) or {}
        shape = fp.get("shape") or "unclassified_disturbance"
        if shape == "none":
            shape = "unclassified_disturbance"
        cls = Classification(
            "CHANNEL_MANIPULATION", shape, "statistical", "D2 ∨ D3b ∨ D4 ∨ D5",
            (f"The channel to {link} deviates from its calibrated baseline. " if link else "") + fp.get("summary", ""),
            fp.get("alternatives", []))
    elif margin:
        cls = Classification("DEGRADED", "insufficient_margin", "design", "D9", margin[0].evidence)
    elif cusum:
        cls = Classification(
            "CHANNEL_MANIPULATION", "low_intensity_persistent", "temporal", "D10", cusum[0].evidence,
            ["slow natural degradation of the link", "a low-and-slow attack campaign"])

    level = max_severity(findings)
    compromised = any(f.fired and SEVERITY_RANK[f.severity] >= SEVERITY_RANK["HIGH"] for f in findings) or bool(margin)
    verdict = "COMPROMISED" if compromised else "CERTIFIED"
    if cls.category == "NONE" and verdict == "CERTIFIED":
        cls.explanation = "Every link certified entanglement, matched its baseline, and passed frame and source checks."
    return Assessment(verdict=verdict, threat_level=level, threat_score=threat_score(findings),
                      classification=cls, findings=findings, recommended_actions=_actions(cls.category, cls.subtype))


def fuse_signature(findings: list, verdict_accept: bool, stage: str = "first") -> Assessment:
    """Signature decision list (backend plan section 6.5.3)."""
    by = {f.id: f for f in findings if f.fired}
    s9 = [f for f in findings if f.id == "S9.forensics"]
    cls = Classification()
    if any(f.id == "S1.authorization" and f.fired for f in findings):
        f = next(f for f in findings if f.id == "S1.authorization" and f.fired)
        cls = Classification("UNAUTHORIZED_VERIFICATION", "non_recipient", "conclusive", "S1", f.evidence)
    elif any(f.id == "S2.key_binding" and f.fired for f in findings):
        f = next(f for f in findings if f.id == "S2.key_binding" and f.fired)
        cls = Classification("IMPERSONATION", "identity_swap", "conclusive", "S2",
                             f.evidence + ". The quantum tests may pass: a valid key is not the right key.")
    else:
        s3 = next((f for f in findings if f.id == "S3.bundle_state" and f.fired), None)
        replay_ids = [f for f in findings if f.fired and f.id in ("S4.nonce", "S5.sequence", "S6.freshness")]
        if (s3 and not s3.data.get("policy_block")) or replay_ids:
            ids = {f.id for f in replay_ids}
            if s3 and not s3.data.get("policy_block"):
                ids.add("S3")
            if ids == {"S6.freshness"}:
                sub = "delay"
            elif stage == "forward_replay":
                sub = "forward_replay"
            else:
                sub = "resubmission"
            text = " ".join(f.evidence + "." for f in ([s3] if s3 else []) + replay_ids)
            cls = Classification("REPLAY", sub, "conclusive", "S3 ∨ S4 ∨ S5 ∨ S6",
                                 text + " Replayed quantum statistics are genuine by construction; the protocol layer is "
                                        "what catches a replay.")
        elif s3 and s3.data.get("policy_block"):
            cls = Classification("POLICY", "blocked_bundle", "conclusive", "S3", s3.evidence)
        elif s9:
            lab = s9[0].data.get("label")
            if lab == "KEYLESS":
                cls = Classification("IMPERSONATION", "keyless", "statistical", "S7 ∧ S9=KEYLESS", s9[0].evidence)
            elif lab == "INSIDER":
                cls = Classification("FORGERY", "insider", "statistical", "S7 ∧ S9=INSIDER", s9[0].evidence,
                                     attributed_to=s9[0].data.get("attributed_to"))
            else:
                nf = s9[0].data.get("n_failed", 0)
                sub = {"EXTERNAL_BLIND": "external_blind", "INFORMED": "informed"}.get(lab, "unattributed")
                if nf <= 8:
                    sub = "oracle_k_bits"
                cls = Classification("FORGERY", sub, s9[0].data.get("confidence", "statistical"), "S7 ∧ S9",
                                     s9[0].evidence + (" Only a few keys differ: the attacker needed a near-collision of the "
                                                       "message digest." if nf <= 8 else ""))
        elif "S10.transfer_consistency" in by:
            cls = Classification("REPUDIATION", "dispute", "statistical", "S10", by["S10.transfer_consistency"].evidence)

    verdict = "ACCEPTED" if verdict_accept and cls.category in ("NONE", "REPUDIATION") else "REJECTED"
    if verdict == "ACCEPTED" and cls.category == "NONE":
        cls.explanation = "All protocol checks passed and every key's mismatch rate was within its designed threshold."
    return Assessment(verdict=verdict, threat_level=max_severity(findings), threat_score=threat_score(findings),
                      classification=cls, findings=findings, recommended_actions=_actions(cls.category, cls.subtype))
