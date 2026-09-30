"""
dashboard/components/_web.py
============================
Builds the self-contained HTML documents for the WebGL scenes.

Streamlit renders ``components.html`` as a ``srcdoc`` iframe, which cannot
load sibling files, so each scene is inlined: the page template, the shared
3D core (``web/core.js``) and the scene entry file are concatenated into a
single ES module, and the scene's input data is embedded as JSON.

Three.js and its addons come from a pinned CDN build through an import map.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
THREE_VERSION = "0.165.0"

_IMPORT_MAP = (
    '<script type="importmap">{"imports": {'
    f'"three": "https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/build/three.module.js", '
    f'"three/addons/": "https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/examples/jsm/"'
    "}}</script>"
)

_MODULE_IMPORTS = """
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { FontLoader } from 'three/addons/loaders/FontLoader.js';
import { TextGeometry } from 'three/addons/geometries/TextGeometry.js';
"""


def read_web(name: str) -> str:
    """Return the text of a file in ``dashboard/web``."""
    return (WEB_DIR / name).read_text(encoding="utf-8")


def _json_for_script(data: Dict[str, Any]) -> str:
    # "</" would end the <script> element early; escaping it keeps JSON valid.
    return json.dumps(data, default=float).replace("</", "<\\/")


def build_scene(template: str, scripts: Iterable[str], data: Dict[str, Any]) -> str:
    """Assemble one scene into a standalone HTML document.

    Parameters
    ----------
    template : str
        HTML file in ``dashboard/web`` with ``<!--QV_HEAD-->`` and
        ``<!--QV_SCRIPT-->`` placeholders.
    scripts : iterable of str
        JS files concatenated, in order, into one module after the imports.
    data : dict
        JSON-serialisable scene input, exposed as ``window.QV_DATA``.
    """
    body = "\n".join(read_web(s) for s in scripts)
    script = (
        f"<script>window.QV_DATA = {_json_for_script(dict(data, three_version=THREE_VERSION))};</script>\n"
        f'<script type="module">{_MODULE_IMPORTS}\n{body}\n</script>'
    )
    return (
        read_web(template)
        .replace("<!--QV_HEAD-->", _IMPORT_MAP)
        .replace("<!--QV_SCRIPT-->", script)
    )


def publish(channel: str, payload: Dict[str, Any]) -> None:
    """Post ``payload`` to a long-lived scene without reloading it.

    Scenes are rendered with a static ``srcdoc`` so Streamlit keeps their
    iframe (and WebGL context) across reruns. Fresh values travel through
    this zero-height component instead: it stores them on the parent page
    under ``window.__qvBus[channel]`` with a content hash, and the scene
    polls for a new hash every frame and morphs to the new state.
    """
    import hashlib

    import streamlit.components.v1 as components

    body = _json_for_script(payload)
    version = hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]
    components.html(
        "<script>(function(){try{var P=window.parent;P.__qvBus=P.__qvBus||{};"
        f"P.__qvBus[{json.dumps(channel)}]={{v:'{version}',d:{body}}};}}catch(e){{}}}})();</script>",
        height=0,
    )
