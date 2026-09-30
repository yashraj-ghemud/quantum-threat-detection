"""
dashboard/components/security_panel.py
======================================
Live signature generation and verification.

Verification is cheap, so it re-runs on every widget change and the
"Signature Constellation" scene (``dashboard/web/verify_lab.js``) morphs
live: the ring re-scans when the signature changes, and the threshold notch
moves (and the gate opens or locks) when only τ changes.

The optional tampering control passes the signature through the real
``ForgeryAttack`` before verification, so the score/threshold interplay is
shown on genuinely forged states rather than an invented score.
"""
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from attacks.base import SessionMetadata
from attacks.forgery import ForgeryAttack
from qds.signature import generate_signature
from qds.verification import verify_signature
from security.detector import ThreatDetector

from dashboard.components._web import build_scene, publish


def _verify(message: str, sig_len: int, seed: int, threshold: float, forged: float):
    """Generate, optionally forge, and verify one signature."""
    sig = generate_signature(message, length=sig_len, seed=seed)
    received = None
    if forged > 0:
        attack = ForgeryAttack(seed=seed)
        received = attack.execute(sig.statevectors(), SessionMetadata(), intensity=forged).statevectors
    res = verify_signature(sig, received_statevectors=received, threshold=threshold)
    det = ThreatDetector().detect(res, session_id=sig.signature_id)
    return sig, res, det


def render_verification_panel():
    """Render the live signature verification UI."""
    st.subheader("Live Verification Control")
    st.write("Generate a QDS signature, optionally forge part of it, and verify it against the measurement apparatus. "
             "Every change re-verifies; the constellation shows each element being measured.")

    col_opt, col_res = st.columns([0.3, 0.7])

    with col_opt:
        st.markdown("**Signature Parameters**")
        message = st.text_input("Message", "dashboard_test", key="ver_msg")
        sig_len = st.number_input("Signature Length (Qubits)", min_value=4, max_value=256, value=16, step=4, key="ver_sig_len")
        t_thresh = st.slider("Acceptance Threshold τ", min_value=0.0, max_value=1.0, value=0.7, step=0.05)
        forged = st.slider("Forged fraction (real ForgeryAttack)", min_value=0.0, max_value=1.0, value=0.0, step=0.05,
                           help="Passes the signature through attacks.forgery.ForgeryAttack at this intensity before verifying.")
        seed = st.number_input("Random Seed", min_value=0, max_value=9999, value=42, key="ver_seed")
        log = st.button("Log this verification", type="primary")

    sig, res, det_res = _verify(message, int(sig_len), int(seed), float(t_thresh), float(forged))
    if log:
        from dashboard.components.metrics import log_event
        log_event(
            event_type="Forged Verification" if forged > 0 else "Legitimate Verification",
            action="verify_signature",
            score=det_res.anomaly_score,
            decision=det_res.classification,
        )

    with col_res:
        html = build_scene("panel.html", ["core.js", "verify_lab.js"], {"channel": "verify", "title": "SIGNATURE CONSTELLATION"})
        components.html(html, height=500, scrolling=False)
        publish("verify", {
            "n": int(sig_len), "threshold": float(t_thresh), "score": float(res.verification_score),
            "matches": int(res.matches), "accepted": bool(res.accepted), "seed": int(seed),
            "message": f"{message}|{forged:.2f}",
            "elements": [{
                "label": e.expected_label, "basis": e.expected_basis, "expected": int(e.expected_eigenvalue),
                "measured": int(e.measured_eigenvalue), "match": bool(e.match), "p_plus": float(e.p_plus),
            } for e in res.element_results],
        })

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Verification Score", f"{res.verification_score:.4f}")
        c2.metric("Anomaly Score", f"{det_res.anomaly_score:.4f}")
        c3.metric("Match Count", f"{res.matches}/{sig_len}")
        status = "ACCEPTED" if res.accepted else "REJECTED"
        tone = "ok" if res.accepted else "bad"
        c4.markdown(f"**Outcome**<br><span class='qv-verdict {tone}'>{status}</span>", unsafe_allow_html=True)

        with st.expander("Signature Structure & Measurements", expanded=False):
            df = pd.DataFrame([{
                "Position": e.position,
                "Eigenstate": e.expected_label,
                "Basis": e.expected_basis.upper(),
                "Expected": "+1" if e.expected_eigenvalue == 1 else "-1",
                "Measured": "+1" if e.measured_eigenvalue == 1 else "-1",
                "p(+1)": round(e.p_plus, 4),
                "Match": "yes" if e.match else "NO",
            } for e in res.element_results])
            st.dataframe(df, width="stretch", hide_index=True)
