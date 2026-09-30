"""
dashboard/components/intro_simulation.py
========================================
The cinematic intro and the scroll-driven landing hero.

One WebGL scene (``dashboard/web/story.js``) tells "The Journey of a
Signature" (see ``docs/animation_storyboard.md``). On the first load of a
browser session it plays full-screen as a film, then docks into the page,
where the same story is scrubbed by scrolling.

The page never reloads this iframe on Streamlit reruns: the HTML is
identical across runs, and whether the film has already played is tracked
in the browser, not in ``st.session_state``. A changing ``srcdoc`` would
make Streamlit rebuild the iframe and restart WebGL on every widget change.
"""

from __future__ import annotations

import hashlib

import streamlit.components.v1 as components

from dashboard.components._web import build_scene, read_web
from dashboard.data_source import load_metrics, results_available

STORY_MESSAGE = "transfer 100 to bob"


def _headline_metrics() -> dict | None:
    """Real headline figures for the epilogue, or ``None`` without a run."""
    if not results_available():
        return None
    m = load_metrics() or {}
    keys = ("detection_rate", "far", "frr", "threshold")
    return {k: m.get(k) for k in keys}


def render_intro() -> None:
    """Render the story scene: intro film first, then the landing hero."""
    data = {
        "message": STORY_MESSAGE,
        # The digest drawn on screen is the real SHA-256 of the message.
        "digest": hashlib.sha256(STORY_MESSAGE.encode()).hexdigest(),
        "metrics": _headline_metrics(),
        # Page-wide interaction layer, injected once into the parent page.
        "fx": read_web("fx.js"),
        "intro": True,
    }
    html = build_scene("story.html", ["core.js", "story.js"], data)
    # The scene sets its own height (several viewports tall, sticky inside).
    components.html(html, height=820, scrolling=False)
