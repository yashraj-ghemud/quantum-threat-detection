"""
dashboard/components/charts.py
==============================
Threat-analytics charts, read from the canonical experiment output.

SIH26141 | Blockchain & Cybersecurity.

Every chart here is backed by `experiments/results/final/`, which only
`experiments/run_final_experiment.py` writes. This module loads and
renders; it computes no security metric of its own. The one interactive
exception, the operating-point explorer, only *looks up* rows of the
threshold sweep the experiment already measured.

A missing input says so explicitly: a blank panel is better than a number
nobody can trace to a run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dashboard.components._theme import (  # noqa: E402
    ATTACK_COLORS, CHART_CONFIG, CORAL, GOLD, INK2, LAV, MINT, PEACH, SKY, pretty, rgba,
)
from dashboard.data_source import (  # noqa: E402
    load_attack_metrics,
    load_comparison,
    load_confusion_matrix,
    load_intensity,
    load_metrics,
    load_threshold_analysis,
    missing_results_message,
    plot_path,
    results_available,
)

RESULTS_DIR = _ROOT / "experiments" / "results" / "final"


def _require_results() -> bool:
    """Show the regeneration instruction when no canonical run exists."""
    if results_available():
        return True
    st.warning(missing_results_message())
    return False


def _chart(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, width="stretch", config=CHART_CONFIG, key=key)


def _static_figures(names: list[str]) -> None:
    """The matplotlib figures the run exported, tucked away for reports."""
    have = [n for n in names if plot_path(n)]
    if not have:
        return
    with st.expander("Static figures exported by the run (for reports)"):
        cols = st.columns(min(2, len(have)))
        for i, n in enumerate(have):
            cols[i % len(cols)].image(plot_path(n), caption=n, width="stretch")


# ---------------------------------------------------------------------------
# Attack comparison
# ---------------------------------------------------------------------------

def render_attack_comparison() -> None:
    """Per-attack detection with intervals, and each class's telemetry fingerprint."""
    st.subheader("Attack Detection Performance")
    if not _require_results():
        return

    df = load_attack_metrics()
    comp = load_comparison()
    m = load_metrics() or {}
    if df is None or df.empty:
        st.info("No attack metrics in the canonical results.")
        return

    left, right = st.columns(2)
    with left:
        # Detection rate with its 95% Clopper-Pearson interval.
        names = [pretty(a) for a in df["attack_type"]]
        fig = go.Figure(go.Bar(
            x=names, y=df["detection_rate"] * 100,
            marker=dict(color=[ATTACK_COLORS.get(a, LAV) for a in df["attack_type"]], cornerradius=10),
            error_y=dict(type="data", symmetric=False, color=INK2, thickness=1.4, width=6,
                         array=(df["ci_upper"] - df["detection_rate"]) * 100,
                         arrayminus=(df["detection_rate"] - df["ci_lower"]) * 100),
            text=[f"{v * 100:.1f}%" for v in df["detection_rate"]], textposition="inside",
            customdata=np.stack([df["detected"], df["trials"], df["ci_lower"] * 100, df["ci_upper"] * 100,
                                 df["classification_accuracy"] * 100], axis=1),
            hovertemplate="<b>%{x}</b><br>detected %{customdata[0]:.0f} / %{customdata[1]:.0f}"
                          "<br>95% CI [%{customdata[2]:.2f}, %{customdata[3]:.2f}]"
                          "<br>correctly named %{customdata[4]:.1f}%<extra></extra>",
        ))
        lo = max(0.0, float((df["ci_lower"].min()) * 100) - 5)
        fig.update_layout(title="Detection rate per attack (95% CI)", yaxis=dict(title="detected %", range=[lo, 101]), height=380, showlegend=False)
        _chart(fig, "det_rate")

    with right:
        # How far above τ each class lands: the margin the detector has.
        if comp is not None and not comp.empty:
            th = m.get("threshold")
            c = comp.sort_values("anomaly_score")
            fig = go.Figure(go.Bar(
                y=[pretty(x) for x in c["condition"]], x=c["anomaly_score"], orientation="h",
                marker=dict(color=[ATTACK_COLORS.get(x, LAV) for x in c["condition"]], cornerradius=8),
                text=[f"{v:.4f}" for v in c["anomaly_score"]], textposition="outside",
                hovertemplate="<b>%{y}</b><br>mean anomaly score %{x:.5f}<extra></extra>",
            ))
            if th:
                fig.add_vline(x=th, line=dict(color=INK2, width=2, dash="dash"),
                              annotation_text=f"τ = {th:.4f}", annotation_position="top")
            vals = c["anomaly_score"].clip(lower=1e-6)
            span = [np.log10(min(vals.min(), th or vals.min()) * 0.5), np.log10(vals.max() * 4)]
            fig.update_traces(cliponaxis=False)
            fig.update_layout(title="Mean anomaly score vs the calibrated threshold", height=380,
                              xaxis=dict(title="anomaly score (log)", type="log", range=span), showlegend=False)
            _chart(fig, "anom_margin")
    below = []
    if comp is not None and not comp.empty and m.get("threshold"):
        below = [pretty(c) for c, v in zip(comp["condition"], comp["anomaly_score"])
                 if c != "NORMAL" and v < m["threshold"]]
    st.caption(
        "Detection rate is the fraction flagged SUSPICIOUS or THREAT; bars carry 95% Clopper-Pearson intervals. "
        "The right chart is the statistical margin: how far each class's mean anomaly score lands from τ."
        + (f" {', '.join(below)} sits below τ on purpose: its quantum statistics are identical to a legitimate "
           "session by construction, so the engine catches it with the classical session-consistency check "
           "(nonce, sequence, freshness) instead." if below else "")
    )

    if comp is not None and not comp.empty:
        st.markdown("#### Telemetry fingerprint: normal vs each attack")
        st.caption("Each axis is one measured statistic, scaled across classes to [0, 1]. Hover for the real value. "
                   "Purity separates forgery (still pure) from channel noise (decohered).")
        metrics_cols = [("fidelity", "fidelity"), ("purity", "purity"), ("trace_distance", "trace distance"),
                        ("entropy", "entropy"), ("mismatch_rate", "mismatch rate"), ("anomaly_score", "anomaly score")]
        metrics_cols = [mc for mc in metrics_cols if mc[0] in comp.columns]
        options = list(comp["condition"])
        chosen = st.multiselect("Classes", options, default=options, format_func=pretty, key="fp_classes")
        fig = go.Figure()
        for _, row in comp.iterrows():
            if row["condition"] not in chosen:
                continue
            r, real = [], []
            for col, _ in metrics_cols:
                lo, hi = comp[col].min(), comp[col].max()
                r.append(0.5 if hi - lo < 1e-12 else (row[col] - lo) / (hi - lo))
                real.append(row[col])
            colour = ATTACK_COLORS.get(row["condition"], LAV)
            fig.add_trace(go.Scatterpolar(
                r=r + r[:1], theta=[lbl for _, lbl in metrics_cols] + [metrics_cols[0][1]],
                customdata=real + real[:1], name=pretty(row["condition"]), fill="toself",
                line=dict(color=colour, width=2.5), fillcolor=rgba(colour, 0.12),
                hovertemplate="<b>" + pretty(row["condition"]) + "</b><br>%{theta}: %{customdata:.5f}<extra></extra>",
            ))
        fig.update_layout(height=470, polar=dict(radialaxis=dict(range=[0, 1.05], showticklabels=False)), title="")
        _chart(fig, "fingerprint")

    with st.expander("Data tables"):
        show = df.copy()
        show["detection_rate"] = (show["detection_rate"] * 100).round(2)
        show["95% CI"] = [f"[{lo * 100:.2f}, {hi * 100:.2f}]" for lo, hi in zip(show["ci_lower"], show["ci_upper"])]
        show["classified"] = (show["classification_accuracy"] * 100).round(1)
        st.dataframe(show[["attack_type", "trials", "detected", "missed", "detection_rate", "95% CI", "classified",
                           "mean_anomaly_score", "mean_fidelity", "mean_purity"]], width="stretch", hide_index=True)
        if comp is not None:
            cols = ["condition", "fidelity", "purity", "trace_distance", "entropy", "mismatch_rate", "anomaly_score"]
            st.dataframe(comp[[c for c in cols if c in comp.columns]].round(4), width="stretch", hide_index=True)
    _static_figures(["attack_comparison.png", "normal_vs_attack.png"])


# ---------------------------------------------------------------------------
# Threshold analysis
# ---------------------------------------------------------------------------

def _confusion_fig(tp, tn, fp, fn, title: str) -> go.Figure:
    z = [[tn, fp], [fn, tp]]
    labels = [[f"TN<br><b>{tn}</b>", f"FP<br><b>{fp}</b>"], [f"FN<br><b>{fn}</b>", f"TP<br><b>{tp}</b>"]]
    fig = go.Figure(go.Heatmap(
        z=z, x=["Predicted legitimate", "Predicted attack"], y=["Actual legitimate", "Actual attack"],
        colorscale=[[0, "#EEF0F9"], [0.5, rgba(LAV, 0.55)], [1, LAV]], showscale=False,
        text=labels, texttemplate="%{text}", textfont=dict(size=16, family="Space Grotesk"),
        hovertemplate="%{y} · %{x}: %{z}<extra></extra>", xgap=6, ygap=6,
    ))
    fig.update_layout(title=title, height=330, yaxis=dict(autorange="reversed"))
    return fig


def render_threshold_analysis() -> None:
    """Operating-point explorer over the measured sweep, plus intensity analyses."""
    st.subheader("Threshold & Error-Rate Analysis")
    if not _require_results():
        return

    m = load_metrics() or {}
    df = load_threshold_analysis()
    calibrated = m.get("threshold")

    if df is not None and not df.empty:
        st.markdown("#### Operating-point explorer")
        st.caption("Slide along the thresholds the experiment actually evaluated. Every number below is a row of "
                   "threshold_analysis.csv; the star is the operating point the run selected (lowest FAR with FRR ≤ 5%).")
        st.info(
            f"This sweep scores the **statistical layer alone**. Its FAR counts replayed sessions, which are "
            f"statistically invisible by design. The full engine adds protocol checks (replay freshness, access "
            f"control), which is why its measured FAR at τ* is **{m.get('far', 0) * 100:.2f}%** "
            f"(95% CI {m.get('far_ci', [0, 0])[0] * 100:.2f}–{m.get('far_ci', [0, 0])[1] * 100:.2f}%, n = {m.get('far_n', '?')})."
        )
        df = df.sort_values("threshold").reset_index(drop=True)
        options = list(range(len(df)))
        default = int((df["threshold"] - (calibrated or 0)).abs().idxmin()) if calibrated else len(df) // 2
        idx = st.select_slider("Threshold τ", options=options, value=default,
                               format_func=lambda i: f"{df.loc[i, 'threshold']:.5f}", key="op_point")
        row = df.loc[idx]
        ref = df.loc[default]

        c = st.columns(5)

        def _d(v: float, unit: str = " pts vs τ*"):
            return None if abs(v) < 1e-9 else f"{v:+.2f}{unit}"

        c[0].metric("FAR · statistical", f"{row['far'] * 100:.2f}%", _d((row['far'] - ref['far']) * 100), delta_color="inverse")
        c[1].metric("FRR", f"{row['frr'] * 100:.2f}%", _d((row['frr'] - ref['frr']) * 100), delta_color="inverse")
        c[2].metric("Accuracy", f"{row['accuracy'] * 100:.2f}%", _d((row['accuracy'] - ref['accuracy']) * 100, " pts"))
        if "f1" in row:
            c[3].metric("F1", f"{row['f1'] * 100:.2f}%", _d((row['f1'] - ref['f1']) * 100, " pts"))
        c[4].metric("Threshold", f"{row['threshold']:.5f}", "selected τ*" if idx == default else "exploring", delta_color="off")

        left, right = st.columns([0.62, 0.38])
        with left:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["threshold"], y=df["far"] * 100, name="FAR · attacks passed", mode="lines",
                                     line=dict(color=CORAL, width=3, shape="spline"), fill="tozeroy", fillcolor=rgba(CORAL, 0.08)))
            fig.add_trace(go.Scatter(x=df["threshold"], y=df["frr"] * 100, name="FRR · legitimate denied", mode="lines",
                                     line=dict(color=SKY, width=3, shape="spline"), fill="tozeroy", fillcolor=rgba(SKY, 0.08)))
            fig.add_trace(go.Scatter(x=df["threshold"], y=df["accuracy"] * 100, name="accuracy", mode="lines",
                                     line=dict(color=MINT, width=2, dash="dot")))
            fig.add_vline(x=row["threshold"], line=dict(color=LAV, width=2))
            fig.add_trace(go.Scatter(x=[row["threshold"]] * 2, y=[row["far"] * 100, row["frr"] * 100], mode="markers",
                                     marker=dict(size=13, color=[CORAL, SKY], line=dict(color="white", width=2)),
                                     showlegend=False, hoverinfo="skip"))
            if calibrated:
                fig.add_trace(go.Scatter(x=[ref["threshold"]], y=[ref["far"] * 100], mode="markers", name="selected τ*",
                                         marker=dict(symbol="star", size=18, color=GOLD, line=dict(color="white", width=1.5))))
            fig.update_layout(title="FAR / FRR across the measured sweep", height=400,
                              xaxis=dict(title="threshold τ (log)", type="log"), yaxis=dict(title="%", range=[-2, 102]))
            _chart(fig, "farfrr")
        with right:
            _chart(_confusion_fig(int(row["tp"]), int(row["tn"]), int(row["fp"]), int(row["fn"]),
                                  f"Confusion at τ = {row['threshold']:.5f}"), "cm_live")
            cm = load_confusion_matrix()
            if cm is not None:
                st.caption(f"The canonical run at τ* recorded {int(cm.iloc[0, 0])} TN · {int(cm.iloc[0, 1])} FP · "
                           f"{int(cm.iloc[1, 0])} FN · {int(cm.iloc[1, 1])} TP.")

    st.divider()
    inten = load_intensity()
    if inten is not None and not inten.empty:
        st.markdown("#### Attack intensity")
        left, right = st.columns(2)
        with left:
            fig = go.Figure()
            for name, sub in inten.groupby("attack_type"):
                fig.add_trace(go.Scatter(x=sub["intensity"], y=sub["mean_anomaly_score"], name=pretty(name),
                                         mode="lines+markers", line=dict(color=ATTACK_COLORS.get(name, LAV), width=2.5, shape="spline"),
                                         customdata=sub["detection_rate"] * 100,
                                         hovertemplate="%{x:.2f} → score %{y:.4f}<br>detected %{customdata:.1f}%<extra>" + pretty(name) + "</extra>"))
            if calibrated:
                fig.add_hline(y=calibrated, line=dict(color=INK2, dash="dash"), annotation_text="τ*")
            fig.update_layout(title="Anomaly score grows with attack intensity", height=400,
                              xaxis=dict(title="intensity"), yaxis=dict(title="mean anomaly score (log)", type="log"))
            _chart(fig, "int_score")
        with right:
            fig = go.Figure()
            for name, sub in inten.groupby("attack_type"):
                fig.add_trace(go.Scatter(x=sub["intensity"], y=sub["detection_rate"] * 100, name=pretty(name),
                                         mode="lines+markers", line=dict(color=ATTACK_COLORS.get(name, LAV), width=2.5)))
            fig.update_layout(title="Detection rate vs intensity", height=400, yaxis=dict(title="detected %", range=[0, 105]),
                              xaxis=dict(title="intensity"))
            _chart(fig, "int_det")
        chan = inten[inten["attack_type"] == "CHANNEL_MANIPULATION"]
        if not chan.empty and "mean_fidelity" in chan:
            fig = go.Figure(go.Scatter(x=chan["intensity"], y=chan["mean_fidelity"], mode="lines+markers",
                                       line=dict(color=PEACH, width=3, shape="spline"), fill="tozeroy", fillcolor=rgba(PEACH, 0.12),
                                       hovertemplate="p = %{x:.2f}<br>fidelity %{y:.4f}<extra></extra>"))
            fig.update_layout(title="Teleportation fidelity vs injected channel noise", height=320,
                              xaxis=dict(title="depolarizing strength injected"), yaxis=dict(title="mean fidelity"))
            _chart(fig, "fid_noise")
            st.caption("Measured on the live teleportation channel: injected noise degrades the state the verifier receives.")
    _static_figures(["far_frr_vs_threshold.png", "confusion_matrix.png", "detection_vs_intensity.png", "fidelity_vs_noise.png"])


# ---------------------------------------------------------------------------
# Performance / scalability
# ---------------------------------------------------------------------------

def render_performance_analytics() -> None:
    """Latency, throughput and scaling behaviour."""
    st.subheader("Performance & Scalability")
    if not _require_results():
        return

    m = load_metrics() or {}
    lat = m.get("latency_ms", {})

    cols = st.columns(5)
    cols[0].metric("Signature gen", f"{lat.get('signature_generation_mean', 0):.2f} ms")
    cols[1].metric("Quantum channel", f"{lat.get('quantum_channel_mean', 0):.2f} ms")
    cols[2].metric("Verification", f"{lat.get('verification_mean', 0):.2f} ms")
    cols[3].metric("Detection", f"{lat.get('detection_mean', 0):.2f} ms")
    cols[4].metric("Throughput", f"{m.get('throughput_sessions_per_sec', 0):.1f}/s")
    st.caption(f"End-to-end mean {lat.get('end_to_end_mean', 0):.2f} ms, median {lat.get('end_to_end_median', 0):.2f} ms.")

    left, right = st.columns(2)
    path = RESULTS_DIR / "scalability_length.csv"
    if path.exists():
        ldf = pd.read_csv(path)
        with left:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            for col, label, colour in (("sign_ms", "signing", LAV), ("channel_ms", "quantum channel", SKY),
                                       ("measure_ms", "measure + verify", MINT), ("detect_ms", "detection", CORAL)):
                if col in ldf:
                    fig.add_trace(go.Bar(x=ldf["signature_length"].astype(str), y=ldf[col], name=label,
                                         marker=dict(color=colour, cornerradius=4)), secondary_y=False)
            fig.add_trace(go.Scatter(x=ldf["signature_length"].astype(str), y=ldf["throughput_per_sec"], name="throughput",
                                     mode="lines+markers", line=dict(color=GOLD, width=3)), secondary_y=True)
            fig.update_layout(barmode="stack", title="Latency by stage vs signature length", height=400)
            fig.update_yaxes(title_text="ms per session", secondary_y=False)
            fig.update_yaxes(title_text="sessions / s", secondary_y=True, showgrid=False)
            fig.update_xaxes(title_text="signature length (elements)")
            _chart(fig, "lat_len")
    path = RESULTS_DIR / "scalability_shots.csv"
    if path.exists():
        sdf = pd.read_csv(path)
        with right:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=sdf["shots_per_element"].astype(str), y=sdf["total_ms"], name="cost (ms)",
                                 marker=dict(color=rgba(SKY, 0.8), cornerradius=6)), secondary_y=False)
            if "baseline_score_std" in sdf:
                fig.add_trace(go.Scatter(x=sdf["shots_per_element"].astype(str), y=sdf["baseline_score_std"],
                                         name="baseline score spread", mode="lines+markers",
                                         line=dict(color=CORAL, width=3)), secondary_y=True)
            fig.update_layout(title="Shots: cost vs statistical precision", height=400)
            fig.update_yaxes(title_text="ms per session", secondary_y=False)
            fig.update_yaxes(title_text="std of legitimate scores", secondary_y=True, showgrid=False)
            fig.update_xaxes(title_text="shots per element")
            _chart(fig, "shots")
    st.caption("More shots cost time but tighten the spread of legitimate scores, which lets the detector run a tighter threshold.")
    _static_figures(["latency_vs_length.png", "throughput_vs_length.png", "scalability_vs_shots.png"])
