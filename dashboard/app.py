"""
dashboard/app.py
================
Main entry point for the Quantum-Inspired Security Dashboard (Phase 8).
"""
import sys
from pathlib import Path
import streamlit as st

# Inject src into Python path to allow seamless imports of src/ modules
src_path = Path(__file__).parent.parent / "src"
root_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

from dashboard.components import _theme  # noqa: F401  (registers the pastel Plotly template)
from dashboard.components import metrics
from dashboard.components import charts
from dashboard.components import quantum_view
from dashboard.components import attack_panel
from dashboard.components import security_panel
from dashboard.components import intro_simulation
from dashboard.components import live_session

# ---------------------------------------------------------------------------
# Dashboard Initialization
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="QVeris Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Light pastel theme + motion styles (see docs/animation_storyboard.md).
from dashboard.components._web import read_web  # noqa: E402

st.markdown(f"<style>{read_web('theme.css')}</style>", unsafe_allow_html=True)


def _section(kicker: str, title: str) -> None:
    """Chapter-style section heading that continues the story's language."""
    st.markdown(
        f"<div class='qv-section'><span class='k'>{kicker}</span><h2>{title}</h2></div>",
        unsafe_allow_html=True,
    )


def main():
    # Cinematic intro that docks into a scroll-driven story hero.
    intro_simulation.render_intro()

    _section("After the story", "The live system")
    st.caption("Quantum-Inspired Threat Detection & Security Analytics. Everything below runs the real engine.")

    # Initialize basic session state vars for simulated logging
    if "event_logs" not in st.session_state:
        st.session_state.event_logs = []
        
    metrics.render_top_kpis()
    
    tab_live, tab_overview, tab_verify, tab_attacks, tab_analytics, tab_quantum = st.tabs([
        "Live Session",
        "Overview & Performance",
        "Live Verification",
        "Attack Simulation",
        "Threshold Analytics",
        "Quantum Noise"
    ])

    with tab_live:
        live_session.render_live_session()
    
    with tab_overview:
        charts.render_attack_comparison()
        st.divider()
        metrics.render_event_log()
        
    with tab_verify:
        security_panel.render_verification_panel()
        
    with tab_attacks:
        attack_panel.render_attack_panel()
        
    with tab_analytics:
        charts.render_threshold_analysis()
        st.divider()
        charts.render_performance_analytics()
        
    with tab_quantum:
        quantum_view.render_quantum_noise_panel()

if __name__ == "__main__":
    main()
