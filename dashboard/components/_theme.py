"""
dashboard/components/_theme.py
==============================
One Plotly look for every chart, matching the story's palette.

Colours carry the same meaning as in the 3D scenes: lavender = Alice and the
signer, mint = Bob and "verified", sky = the channel, coral = Eve and
"threat", peach = suspicious, gold = classical information.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

INK, INK2 = "#1E2440", "#5A6384"
LAV, MINT, SKY, CORAL, PEACH, GOLD = "#8C84F0", "#4FC3A1", "#6FA8F0", "#E8697A", "#F4A77A", "#E8B860"
GRID = "rgba(30,36,64,0.07)"

# One colour per attack class, used consistently across all charts.
ATTACK_COLORS = {
    "NORMAL": MINT,
    "LEGITIMATE": MINT,
    "FORGERY": CORAL,
    "IMPERSONATION": LAV,
    "REPLAY": GOLD,
    "UNAUTHORIZED_VERIFICATION": SKY,
    "CHANNEL_MANIPULATION": PEACH,
}


def pretty(name: str) -> str:
    """FORGERY -> Forgery, UNAUTHORIZED_VERIFICATION -> Unauthorized verification."""
    return str(name).replace("_", " ").capitalize()


def rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


pio.templates["qveris"] = go.layout.Template(
    layout=dict(
        font=dict(family="Inter, system-ui, sans-serif", color=INK, size=13),
        title=dict(font=dict(family="Space Grotesk, Inter, sans-serif", size=17, color=INK), x=0.01, xanchor="left"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(236,239,249,0.55)",
        colorway=[LAV, SKY, MINT, CORAL, PEACH, GOLD],
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, ticks="", title_font=dict(color=INK2)),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, ticks="", title_font=dict(color=INK2)),
        legend=dict(bgcolor="rgba(243,244,251,0.7)", bordercolor="rgba(255,255,255,0.6)", borderwidth=1,
                    font=dict(size=12), orientation="h", yanchor="bottom", y=1.02, x=0),
        hoverlabel=dict(bgcolor="#F6F7FD", bordercolor=LAV, font=dict(family="JetBrains Mono, monospace", size=12, color=INK)),
        margin=dict(l=10, r=10, t=56, b=10),
        # Values glide to their new positions when a figure updates.
        transition=dict(duration=650, easing="cubic-in-out"),
        polar=dict(bgcolor="rgba(236,239,249,0.55)",
                   radialaxis=dict(gridcolor=GRID, linecolor=GRID), angularaxis=dict(gridcolor=GRID, linecolor=GRID)),
    )
)
pio.templates.default = "plotly_white+qveris"

CHART_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}
