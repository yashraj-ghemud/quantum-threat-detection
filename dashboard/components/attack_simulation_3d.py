"""
dashboard/components/attack_simulation_3d.py
============================================
Attack Lab: a persistent 3D scene that reacts to the widgets and replays
real results (``dashboard/web/attack_lab.js``).

The scene is rendered once per channel with static HTML, so Streamlit keeps
its iframe across reruns. Each rerun publishes two things on the data bus:

* ``config``: the current widget values. The scene shows the configured
  attack using the rules in ``src/attacks/*.py``, labelled as theory.
* ``result``: the last measured run and the config it ran with. A new
  result plays the measured film: real per-element outcomes, the anomaly
  score against the real thresholds, the evidence and the verdict.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit.components.v1 as components

from dashboard.components._web import build_scene, publish


def num(v: Any) -> Optional[float]:
    """Float or ``None``; results can carry numpy scalars or missing values."""
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def lab_config(attack: str, intensity: float, n: int, *, shots: Optional[int] = None,
               seed: Optional[int] = None, message: str = "", digest: str = "") -> Dict[str, Any]:
    """The widget state in the form the scene expects."""
    attack = (attack or "NONE").upper()
    return {
        "type": attack,
        "intensity": 0.0 if attack == "NONE" else round(float(intensity), 2),
        "n": int(n),
        "shots": shots,
        "seed": seed,
        "message": message,
        "digest": digest,
    }


def render_lab(channel: str, title: str, config: Dict[str, Any],
               result: Optional[Dict[str, Any]] = None, height: int = 560) -> None:
    """Render the Attack Lab scene and publish its current state.

    Parameters
    ----------
    channel : str
        Bus channel; one per panel, so two labs never share state.
    title : str
        Panel title drawn in the scene.
    config : dict
        From :func:`lab_config`, describing the widgets right now.
    result : dict, optional
        Last measured run: ``id``, ``config`` (as it was at run time),
        ``classification``, ``anomaly``, ``threshold``, ``critical``,
        ``mismatch_rate``, ``verification``, ``authorization``, ``reason``,
        ``evidence`` and optionally ``elements``.
    """
    html = build_scene("attack_lab.html", ["core.js", "attack_lab.js"], {"channel": channel, "title": title})
    components.html(html, height=height, scrolling=False)
    publish(channel, {"config": config, "result": result})


def render_3d_simulation(attack_event: Optional[Dict[str, Any]] = None, height: int = 560) -> None:
    """Backwards-compatible wrapper: idle Attack Lab with no result."""
    ev = attack_event or {}
    render_lab("lab-legacy", ev.get("title", "ATTACK LAB"),
               lab_config(ev.get("type") or "NONE", ev.get("intensity") or 0, ev.get("samples") or 8), None, height)
