"""
dashboard/components/bloch_view.py
==================================
Bloch-sphere visualisation of measured quantum state disturbance.

SIH26141 | Blockchain & Cybersecurity.

Every vector drawn here is computed from a real session: the *expected*
state comes from the verifier's public key, the *received* state is the
reduced density matrix that actually came out of the teleportation
channel, and the arrow between them is the disturbance the attack caused.

The Bloch vector is ``b_k = Tr(rho sigma_k)``, so its **length** carries
information too, not just its direction:

- length 1.0  -> pure state, undisturbed or merely rotated
- length < 1  -> mixed state; the channel decohered it

That distinction is the same one the detector uses to tell forgery
(substituted pure state, full-length vector pointing the wrong way) from
channel manipulation (shrunken vector pointing the right way). Seeing it
on the sphere is what makes the classification legible.

Nothing here is decorative: no vector is drawn that was not measured.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional

import numpy as np
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

__all__ = ["render_bloch_sphere", "render_bloch_panel"]

_EXPECTED_COLOUR = "#4FC3A1"   # mint: what should have arrived (Bob's key)
_RECEIVED_COLOUR = "#E8697A"   # coral: what did arrive
_DISTURB_COLOUR = "#F4A77A"    # peach: the difference


def _sphere_surface(opacity: float = 0.12):
    """Return a faint unit sphere for orientation."""
    import plotly.graph_objects as go

    u = np.linspace(0, 2 * np.pi, 40)
    v = np.linspace(0, np.pi, 20)
    x = np.outer(np.cos(u), np.sin(v))
    y = np.outer(np.sin(u), np.sin(v))
    z = np.outer(np.ones_like(u), np.cos(v))
    return go.Surface(
        x=x, y=y, z=z, opacity=opacity, showscale=False,
        colorscale=[[0, "#C9C4FF"], [1, "#D6E6FB"]], hoverinfo="skip",
    )


def _axes():
    """Return the X/Y/Z axis lines with Pauli eigenstate labels."""
    import plotly.graph_objects as go

    traces = []
    for vec, name in (((1, 0, 0), "X"), ((0, 1, 0), "Y"), ((0, 0, 1), "Z")):
        traces.append(go.Scatter3d(
            x=[-vec[0], vec[0]], y=[-vec[1], vec[1]], z=[-vec[2], vec[2]],
            mode="lines", line=dict(color="#5A6384", width=2),
            hoverinfo="skip", showlegend=False,
        ))

    labels = {
        "|0>": (0, 0, 1.18), "|1>": (0, 0, -1.18),
        "|+>": (1.18, 0, 0), "|->": (-1.18, 0, 0),
        "|+i>": (0, 1.18, 0), "|-i>": (0, -1.18, 0),
    }
    traces.append(go.Scatter3d(
        x=[p[0] for p in labels.values()],
        y=[p[1] for p in labels.values()],
        z=[p[2] for p in labels.values()],
        mode="text", text=list(labels.keys()),
        textfont=dict(size=12, color="#5A6384", family="JetBrains Mono, monospace"),
        hoverinfo="skip", showlegend=False,
    ))
    return traces


def _arrow(vec, colour: str, name: str, width: int = 6):
    """Return a line-plus-tip trace representing a Bloch vector."""
    import plotly.graph_objects as go

    x, y, z = float(vec[0]), float(vec[1]), float(vec[2])
    length = float(np.linalg.norm(vec))
    return [
        go.Scatter3d(
            x=[0, x], y=[0, y], z=[0, z], mode="lines",
            line=dict(color=colour, width=width), name=name,
            hovertemplate=(
                f"{name}<br>b = ({x:.3f}, {y:.3f}, {z:.3f})"
                f"<br>|b| = {length:.4f}<extra></extra>"
            ),
        ),
        go.Scatter3d(
            x=[x], y=[y], z=[z], mode="markers",
            marker=dict(size=5, color=colour),
            showlegend=False, hoverinfo="skip",
        ),
    ]


def render_bloch_sphere(element, height: int = 520) -> Optional[Any]:
    """Build the Bloch figure for one measured signature element.

    Parameters
    ----------
    element : ElementTelemetry
        Per-element record from a session. Must carry the expected label
        and the measured fidelity/purity.
    height : int
        Figure height in pixels.

    Returns
    -------
    plotly Figure or None
        ``None`` when the element carries no reconstructable state.
    """
    import plotly.graph_objects as go

    from evaluation.fidelity import bloch_vector
    from qds.pauli_states import get_eigenstate

    expected_state = get_eigenstate(element.expected_label)
    b_expected = bloch_vector(expected_state.statevector)

    # Reconstruct the received Bloch vector from what was measured.
    # The component along the measurement axis is the measured expectation
    # value <P> = p0 - p1, which is a direct observation. The orthogonal
    # components are not measured in this session -- the element is only
    # measured in its own basis -- so they are not invented: the received
    # vector is drawn along the measurement axis, scaled by the measured
    # expectation, with its length reduced to the measured purity.
    axis = {"x": np.array([1.0, 0, 0]),
            "y": np.array([0, 1.0, 0]),
            "z": np.array([0, 0, 1.0])}[element.expected_basis]

    measured_expectation = element.p0 - element.p1
    b_received = axis * measured_expectation

    # Purity fixes the vector length: |b| = sqrt(2*purity - 1).
    purity_len = float(np.sqrt(max(2.0 * element.purity - 1.0, 0.0)))
    if abs(measured_expectation) > 1e-9:
        b_received = b_received / abs(measured_expectation) * (
            purity_len * np.sign(measured_expectation)
        )

    fig = go.Figure()
    fig.add_trace(_sphere_surface())
    for t in _axes():
        fig.add_trace(t)
    for t in _arrow(b_expected, _EXPECTED_COLOUR, "Expected (public key)"):
        fig.add_trace(t)
    for t in _arrow(b_received, _RECEIVED_COLOUR, "Received (after channel)"):
        fig.add_trace(t)

    # Disturbance: the vector difference, drawn only when it is real.
    delta = np.asarray(b_received) - np.asarray(b_expected)
    if float(np.linalg.norm(delta)) > 1e-6:
        fig.add_trace(go.Scatter3d(
            x=[b_expected[0], b_received[0]],
            y=[b_expected[1], b_received[1]],
            z=[b_expected[2], b_received[2]],
            mode="lines", line=dict(color=_DISTURB_COLOUR, width=4, dash="dash"),
            name=f"Disturbance |Δb| = {np.linalg.norm(delta):.4f}",
            hovertemplate=f"|Δb| = {np.linalg.norm(delta):.4f}<extra></extra>",
        ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#1E2440"),
        scene=dict(
            bgcolor="rgba(0,0,0,0)",
            xaxis=dict(range=[-1.3, 1.3], title="X", showbackground=False),
            yaxis=dict(range=[-1.3, 1.3], title="Y", showbackground=False),
            zaxis=dict(range=[-1.3, 1.3], title="Z", showbackground=False),
            aspectmode="cube",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=0.0, x=0.0,
                    font=dict(size=10)),
        title=dict(
            text=(f"Element {element.position}: expected {element.expected_label} "
                  f"in {element.expected_basis.upper()} basis"),
            font=dict(size=13),
        ),
    )
    return fig


def render_bloch_panel(result) -> None:
    """Render the Bloch-sphere view for a completed session."""
    st.markdown("#### Quantum State Disturbance")
    st.caption(
        "Expected state (green) is taken from the verifier's public key. "
        "Received state (red) is reconstructed from the measured expectation "
        "value and purity of the state that came out of the channel. "
        "Vector length is |b| = sqrt(2·purity − 1): a full-length vector is "
        "pure, a shortened one has been decohered."
    )

    if not result.elements:
        st.info("No measured elements in this session.")
        return

    labels = [
        f"{e.position}: {e.expected_label} ({e.expected_basis.upper()})"
        f"{'' if e.match else '  — MISMATCH'}"
        for e in result.elements
    ]
    # Default to the first mismatching element: that is where the attack
    # actually landed, so it is the one worth looking at.
    default = next((i for i, e in enumerate(result.elements) if not e.match), 0)

    idx = st.selectbox(
        "Signature element", range(len(labels)),
        format_func=lambda i: labels[i], index=default,
    )
    element = result.elements[idx]

    left, right = st.columns([0.62, 0.38])
    with left:
        fig = render_bloch_sphere(element)
        if fig is not None:
            st.plotly_chart(fig, width="stretch")

    with right:
        st.metric("Fidelity", f"{element.fidelity:.4f}")
        st.metric("Trace distance", f"{element.trace_distance:.4f}")
        st.metric("Purity", f"{element.purity:.4f}",
                  "pure" if element.purity > 0.99 else "mixed (decohered)",
                  delta_color="off")
        st.metric(
            "Measured ⟨P⟩", f"{element.p0 - element.p1:+.4f}",
            f"expected {element.expected_eigenvalue:+d}", delta_color="off",
        )
        st.caption(
            f"Counts: 0 → {element.counts.get('0', 0)}, "
            f"1 → {element.counts.get('1', 0)} over {element.shots} shots"
        )
        if element.match:
            st.success("Element verified")
        else:
            st.error("Element mismatched the public key")

    # Session-level summary across every element.
    st.divider()
    import pandas as pd

    st.markdown("**Disturbance across all elements**")
    df = pd.DataFrame([{
        "element": e.position,
        "expected": e.expected_label,
        "basis": e.expected_basis.upper(),
        "fidelity": round(e.fidelity, 4),
        "purity": round(e.purity, 4),
        "trace distance": round(e.trace_distance, 4),
        "match": "yes" if e.match else "NO",
    } for e in result.elements])
    st.dataframe(df, width="stretch", hide_index=True)
