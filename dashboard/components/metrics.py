"""
dashboard/components/metrics.py
===============================
KPI metrics and event log visualization.
"""
import pandas as pd
import streamlit as st
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent.parent / "experiments" / "results"

# Every KPI below is loaded from the canonical experiment output via the
# dashboard data contract. Nothing here computes a security metric, and
# nothing falls back to a plausible-looking placeholder: if a run has not
# been performed, the UI says so rather than showing a number that no
# measurement produced.
from dashboard.data_source import (  # noqa: E402
    load_attack_metrics,
    load_experiment_config,
    load_metrics,
    missing_results_message,
    pct,
    pct_ci,
    results_available,
)


def render_top_kpis():
    """Render the top dashboard KPIs from the canonical experiment run."""
    st.markdown("### System Security Posture")

    if not results_available():
        st.warning(missing_results_message())
        st.divider()
        return

    m = load_metrics() or {}
    cfg = load_experiment_config() or {}
    attacks = load_attack_metrics()

    # Animated posture header: rings sweep to the measured rates, per-attack
    # detection bars grow, numbers count up. Data comes only from the run.
    import json

    import streamlit.components.v1 as components

    from dashboard.components._web import read_web

    payload = {
        "metrics": m,
        "config": {k: cfg.get(k) for k in ("timestamp_utc", "trials_per_class", "seed")},
        "attacks": [] if attacks is None else [
            {"type": r.attack_type, "rate": float(r.detection_rate)} for r in attacks.itertuples()
        ],
    }
    html = read_web("posture.html").replace("/*QV_DATA*/null", json.dumps(payload, default=float).replace("</", "<\\/"))
    components.html(html, height=246, scrolling=False)

    st.divider()


def log_event(event_type: str, action: str, score: float, decision: str):
    """Log an interactive event to session state."""
    import datetime
    import uuid
    if "event_logs" not in st.session_state:
        st.session_state.event_logs = []

    st.session_state.event_logs.insert(0, {
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        "session_id": str(uuid.uuid4())[:8],
        "event_type": event_type,
        "action": action,
        "anomaly_score": round(score, 4),
        "decision": decision
    })


def render_event_log():
    """Render the chronological event log from dashboard interactions."""
    st.subheader("Live Event Log")
    col1, col2 = st.columns([0.8, 0.2])
    with col1:
        st.caption("Live interactions with the verification and attack engines.")
    with col2:
        if st.button("Clear Log"):
            st.session_state.event_logs = []

    if not st.session_state.get("event_logs"):
        st.info("No events logged yet. Perform verification or launch an attack to see live logs.")
    else:
        df = pd.DataFrame(st.session_state.event_logs)
        def color_decision(val):
            color = "#2E9E7F" if val in ("NORMAL", "ACCEPTED") else "#D04E61" if val in ("THREAT", "DENIED") else "#C0703F"
            return f'color: {color}; font-weight: 600'
        st.dataframe(df.style.map(color_decision, subset=['decision']), width="stretch", hide_index=True)
