"""
dashboard/components/quantum_view.py
====================================
Quantum noise panel: "Channel Anatomy".

Every widget change re-runs the real noisy teleportation (cached per
setting) and publishes Bob's measured density matrix to the persistent 3D
scene (``dashboard/web/noise_lab.js``), which morphs to the new state: the
measured Bloch vector, and the channel's action on the whole Bloch ball.
"""
import numpy as np
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from qds.pauli_states import get_eigenstate
from quantum.noise import NOISE_TYPES, ideal_density_matrix, run_noisy_teleportation

from dashboard.components._web import build_scene, publish

_PAULI = (
    np.array([[0, 1], [1, 0]], dtype=complex),
    np.array([[0, -1j], [1j, 0]], dtype=complex),
    np.array([[1, 0], [0, -1]], dtype=complex),
)


def _bloch(rho: np.ndarray) -> list:
    """Bloch vector b_k = Tr(rho sigma_k)."""
    return [float(np.real(np.trace(rho @ s))) for s in _PAULI]


@st.cache_data(show_spinner="Simulating the open quantum channel...")
def _teleport(noise_type: str, p: float, state_label: str):
    """Run (and cache) one noisy teleportation for this setting."""
    state = get_eigenstate(state_label)
    res = run_noisy_teleportation(noise_type, p, state.theta, state.phi)
    rho = np.asarray(res.bob_density_matrix.data)
    ideal = np.asarray(ideal_density_matrix(res.theta, res.phi).data)
    return float(res.fidelity), rho, ideal


def render_quantum_noise_panel():
    """Render interactive quantum telemetry and noise analysis."""
    st.subheader("Quantum Teleportation & Noise Injection")

    col_ctrl, col_viz = st.columns([0.3, 0.7])

    with col_ctrl:
        st.markdown("**Channel Configuration**")
        noise_type = st.selectbox("Noise Model", NOISE_TYPES, index=2)  # default to depolarizing
        noise_p = st.slider("Noise Strength (p)", min_value=0.0, max_value=1.0, value=0.1, step=0.05)
        state_label = st.selectbox("Transmit Eigenstate", ["|0>", "|1>", "|+>", "|->", "|+i>", "|-i>"], index=2)
        st.caption("Every change re-runs the real teleportation circuit on Aer and updates the scene.")

    fidelity, rho, ideal = _teleport(noise_type, float(noise_p), state_label)

    with col_viz:
        html = build_scene("panel.html", ["core.js", "noise_lab.js"], {"channel": "noise", "title": "CHANNEL ANATOMY"})
        components.html(html, height=500, scrolling=False)
        publish("noise", {
            "noise_type": noise_type, "p": float(noise_p), "state": state_label,
            "fidelity": fidelity, "purity": float(np.real(np.trace(rho @ rho))),
            "ideal": _bloch(ideal), "received": _bloch(rho),
        })

        st.metric("Teleportation Fidelity", f"{fidelity:.4%}")
        if fidelity >= 0.80:
            st.success("Transmission successful. Fidelity meets the minimum threshold (>= 80%).")
        else:
            st.error("Transmission failed. Fidelity dropped below the threshold because of channel noise.")

        # Ideal vs received density-matrix populations.
        fig = go.Figure()
        fig.add_trace(go.Bar(x=['|0⟩', '|1⟩'], y=np.diag(ideal).real, name='Ideal State', marker_color='#8C84F0'))
        fig.add_trace(go.Bar(x=['|0⟩', '|1⟩'], y=np.diag(rho).real, name='Received State', marker_color='#6FA8F0'))
        fig.update_layout(
            template="plotly_white", barmode='group', title="Density Matrix Projection Probabilities", yaxis_range=[0, 1],
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(236,239,249,0.6)",
            font=dict(family="Inter, sans-serif", color="#1E2440"),
            bargap=0.35, bargroupgap=0.12,
        )
        fig.update_traces(marker_line_width=0, marker_cornerradius=8)
        st.plotly_chart(fig, width="stretch")
