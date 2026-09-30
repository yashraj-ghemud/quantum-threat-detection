"""
dashboard/components/attack_panel.py
====================================
Interactive Premium Attack simulation panel with 3D Quantum Networking visual.
"""
import streamlit as st
import time
import pandas as pd

from attacks.runner import AttackRunner
from attacks.forgery import ForgeryAttack
from attacks.impersonation import ImpersonationAttack
from attacks.replay import ReplayAttack
from attacks.unauthorized_verification import UnauthorizedVerificationAttack
from attacks.channel_manipulation import ChannelManipulationAttack

from security.detector import ThreatDetector
from dashboard.components.attack_simulation_3d import lab_config, num, render_lab

ATTACKS = {
    "FORGERY": ForgeryAttack,
    "IMPERSONATION": ImpersonationAttack,
    "REPLAY": ReplayAttack,
    "UNAUTHORIZED_VERIFICATION": UnauthorizedVerificationAttack,
    "CHANNEL_MANIPULATION": ChannelManipulationAttack,
}

def _match_counts(res) -> tuple[int, int]:
    """Return ``(matches, total)`` for a scenario result.

    The full Phase 4 ``DetectionResult`` carries exact counts, but it is
    ``None`` on the authorization-failure path, so fall back to the
    ``sample_count`` / ``mismatch_rate`` fields that are always present.
    """
    dr = getattr(res, "detection_result", None)
    stats = getattr(dr, "stats", None)
    if stats is not None:
        return round(stats.match_rate * stats.total), stats.total
    total = res.sample_count
    return round((1.0 - res.mismatch_rate) * total), total


def _lab_result(res, config: dict) -> dict:
    """Everything the Attack Lab film shows, taken from the real result."""
    import uuid

    dr = getattr(res, "detection_result", None)
    return {
        "id": uuid.uuid4().hex,
        "config": config,
        "classification": res.classification,
        "detection": res.detection_status,
        "authorization": res.authorization_status,
        "anomaly": num(res.anomaly_score),
        "threshold": num(getattr(dr, "warning_threshold", None)),
        "critical": num(getattr(dr, "critical_threshold", None)),
        "mismatch_rate": num(res.mismatch_rate),
        "verification": num(res.verification_score),
        "reason": res.reason,
        "evidence": [str(e) for e in (res.evidence or [])[:3]],
    }


def render_attack_panel():
    st.subheader("Interactive Quantum-Cyber Attack Simulation")
    st.write("Visually inject and analyze quantum interception, forgery, or replay threats against QVERIS.")

    if "attack_history" not in st.session_state:
        st.session_state.attack_history = []
    
    col_ctrl, col_sim = st.columns([0.3, 0.7])
    
    with col_ctrl:
        st.markdown("**Attack Vector Matrix**")
        att_type = st.selectbox("Attack Type", list(ATTACKS.keys()))
        intensity = st.slider("Attack Intensity", min_value=0.0, max_value=1.0, value=0.5, step=0.05)
        sig_len = st.number_input("Signature Length", min_value=4, max_value=256, value=16, step=4)
        seed = st.number_input("Random Seed", min_value=0, max_value=9999, value=42)
        
        c1, c2 = st.columns(2)
        launch = c1.button("LAUNCH ATTACK", type="primary")
        reset = c2.button("RESET SIMULATION")

        if reset:
            st.session_state.current_attack_res = None
            st.session_state.attack_lab_result = None
            st.session_state.attack_history = []
            st.rerun()

        config = lab_config(att_type, intensity, sig_len, seed=int(seed))

        # The run happens in this column so the 3D scene's position in the
        # layout never changes; Streamlit then keeps its WebGL iframe alive.
        if launch:
            start_t = time.perf_counter()
            with st.spinner(f"Running {att_type} through the real pipeline..."):
                runner = AttackRunner(sig_length=sig_len, n_baseline=2, seed=seed)
                try:
                    runner._build_detector()
                except Exception:
                    pass

                AttClass = ATTACKS[att_type]
                attack_inst = AttClass(seed=seed)

                res = runner.run_attack(
                    attack=attack_inst,
                    attack_type=att_type,
                    intensity=intensity
                )
                res.latency = time.perf_counter() - start_t

                st.session_state.current_attack_res = res
                st.session_state.attack_lab_result = _lab_result(res, config)
                st.session_state.attack_history.append({
                    "Attack": att_type,
                    "Intensity": intensity,
                    "Anomaly Score": round(res.anomaly_score, 4),
                    "Classification": res.classification,
                    "Verification": round(res.verification_score, 4),
                    "Authorization": res.authorization_status,
                    "Detection": res.detection_status,
                    "Latency (s)": round(res.latency, 3)
                })

    with col_sim:
        # Live scene: morphs as the controls change, replays each measured run.
        render_lab("lab-attack", "ATTACK LAB", config, st.session_state.get("attack_lab_result"))

    current_res = st.session_state.get("current_attack_res")

    # Results Panel
    if current_res:
        st.divider()
        st.markdown("### Threat Detection Telemetry")
        dr = getattr(current_res, "detection_result", None)
        warn_t = getattr(dr, "warning_threshold", None)
        matches, total = _match_counts(current_res)

        c = st.columns(5)
        tone = {"THREAT": "bad", "SUSPICIOUS": "warn"}.get(current_res.classification, "ok")
        c[0].markdown(f"**VERDICT**<br><span class='qv-verdict {tone}'>{current_res.classification}</span>"
                      f"<br><small>{current_res.detection_status.lower()} · {current_res.authorization_status.lower()}</small>",
                      unsafe_allow_html=True)
        c[1].metric("Anomaly score", f"{current_res.anomaly_score:.4f}",
                    f"τ {warn_t:.4f}" if warn_t is not None else None, delta_color="off")
        c[2].metric("Matches", f"{matches}/{total}", f"mismatch {current_res.mismatch_rate:.3f}", delta_color="off")
        c[3].metric("Verification", f"{current_res.verification_score:.4f}")
        c[4].metric("Pipeline time", f"{getattr(current_res, 'latency', 0.0):.3f} s",
                    f"{current_res.attack_type.lower()} · I {current_res.intensity:.2f}", delta_color="off")
        st.info(f"**Detector reason:** {current_res.reason}")

    # Every launch in this session, against the threshold it had to beat.
    if st.session_state.attack_history:
        st.divider()
        cA, cB = st.columns([0.85, 0.15])
        cA.markdown("### Attack Comparison History")
        if cB.button("Clear Results"):
            st.session_state.attack_history = []
            st.session_state.current_attack_res = None
            st.session_state.attack_lab_result = None
            st.rerun()

        df = pd.DataFrame(st.session_state.attack_history)
        df.insert(0, "Run", range(1, len(df) + 1))
        import plotly.graph_objects as go

        from dashboard.components._theme import ATTACK_COLORS, CHART_CONFIG, INK2, pretty

        fig = go.Figure()
        for name, sub in df.groupby("Attack"):
            fig.add_trace(go.Scatter(
                x=sub["Run"], y=sub["Anomaly Score"], mode="markers", name=pretty(name),
                marker=dict(size=10 + 26 * sub["Intensity"], color=ATTACK_COLORS.get(name, "#8C84F0"),
                            line=dict(color="white", width=2), opacity=0.9),
                customdata=sub[["Intensity", "Classification", "Detection"]].values,
                hovertemplate="run %{x}<br>anomaly %{y:.4f}<br>I = %{customdata[0]:.2f}"
                              "<br>%{customdata[1]} · %{customdata[2]}<extra>" + pretty(name) + "</extra>",
            ))
        dr = getattr(current_res, "detection_result", None) if current_res else None
        if dr is not None and getattr(dr, "warning_threshold", None):
            fig.add_hline(y=dr.warning_threshold, line=dict(color=INK2, dash="dash"), annotation_text="τ")
        fig.update_layout(title="Anomaly score per launch (marker size = intensity)", height=340,
                          xaxis=dict(title="launch", dtick=1), yaxis=dict(title="anomaly score"))
        st.plotly_chart(fig, width="stretch", config=CHART_CONFIG, key="attack_history_chart")
        with st.expander("History table"):
            st.dataframe(df, width="stretch", hide_index=True)
