/* Hosts an original QVeris WebGL scene (dashboard/web/*) inside the app.
   Like dashboard/components/_web.py, the page template, the shared core.js and
   the scene entry are assembled into one ES module in a same-origin srcdoc
   iframe. three@0.165 is self-hosted under /vendor/three. Fresh data goes
   through window.__qvBus[channel], the bus the scenes already poll. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { usePrefs, resolvedTheme, reducedMotion } from '@/state/prefs';

declare global { interface Window { __qvBus?: Record<string, { v: string; d: unknown }> } }

export type SceneName = 'story' | 'attack_lab' | 'noise' | 'verify';
const SOURCES: Record<SceneName, () => Promise<[string, string]>> = {
  story: () => Promise.all([import('./story.html?raw'), import('./story.js?raw')]).then(([a, b]) => [a.default, b.default]),
  attack_lab: () => Promise.all([import('./attack_lab.html?raw'), import('./attack_lab.js?raw')]).then(([a, b]) => [a.default, b.default]),
  noise: () => Promise.all([import('./panel.html?raw'), import('./noise_lab.js?raw')]).then(([a, b]) => [a.default, b.default]),
  verify: () => Promise.all([import('./panel.html?raw'), import('./verify_lab.js?raw')]).then(([a, b]) => [a.default, b.default]),
};
const loadCore = () => import('./core.js?raw').then((m) => m.default);

const MODULE_IMPORTS = `
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
`;

const jsonForScript = (d: unknown) => JSON.stringify(d).replace(/</g, '\\u003c');

async function buildDoc(scene: SceneName, data: Record<string, any>): Promise<string> {
  const [[template, entry], core] = await Promise.all([SOURCES[scene](), loadCore()]);
  const vendor = `${location.origin}/vendor/three`;
  const importMap = `<script type="importmap">${JSON.stringify({ imports: { three: `${vendor}/build/three.module.js`, 'three/addons/': `${vendor}/examples/jsm/` } })}</script>`;
  const script = `<script>window.QV_DATA = ${jsonForScript({ ...data, three_version: '0.165.0', vendor })};</script>\n` +
    `<script type="module">${MODULE_IMPORTS}\n${core}\n${entry}\n</script>`;
  // Self-hosted fonts: copy the app's @font-face rules (absolute URLs) instead of Google Fonts.
  const faces: string[] = [];
  for (const sheet of Array.from(document.styleSheets)) {
    let rules: CSSRuleList | null = null;
    try { rules = sheet.cssRules; } catch { continue; }
    for (const r of Array.from(rules || [])) {
      if (r instanceof CSSFontFaceRule) faces.push(r.cssText.replace(/url\((['"]?)(\/[^)'"]+)\1\)/g, (_m, _q, u) => `url("${location.origin}${u}")`));
    }
  }
  const dark = data.theme === 'noir' ? `<style>
    :root { --ink: #F2F4FF; --ink2: #A7AED6; --surface: rgba(16,21,44,.78); --line: rgba(148,163,255,.16); --bg: #060816; }
    html, body { background: #060816 !important; color: #F2F4FF; }
    .glass, .panel, .chip, #skip, #tip, #fg-story { background: rgba(16,21,44,.78) !important; border-color: rgba(148,163,255,.18) !important; color: #F2F4FF !important; }
    #landing p, .panel p, #cap-line, .row span, .meter .row, #th-lines .note, #evidence, #reason, #hint, #note { color: #A7AED6 !important; }
    #th-lines div, .meter b, .row b, #sub, #tip b, .verdict b, #brand b, h1, h2, h3 { color: #F2F4FF; }
    #brand .mark::after { background: #060816 !important; }
    .bar { background: #0A0E20 !important; }
    #vignette { background: radial-gradient(120% 90% at 50% 45%, transparent 55%, rgba(3,4,10,.55) 100%) !important; }
    #dive { background: radial-gradient(120% 80% at 50% 60%, rgba(46,242,192,.18), #060816 70%) !important; }
    #flash { background: radial-gradient(circle at 50% 50%, #FFFFFF 0%, #A48CFF 28%, rgba(87,169,255,.4) 52%, rgba(6,8,22,0) 72%) !important; }
    .track { background: rgba(148,163,255,.14) !important; }
  </style>` : '';
  const fontCss = `<style>${faces.join('\n')}</style>`;
  return template.replace(/<link rel="preconnect"[^>]*>\s*<link href="https:\/\/fonts\.googleapis\.com[^>]*>/, fontCss).replace('<!--QV_HEAD-->', importMap).replace('<!--QV_SCRIPT-->', script).replace('</head>', `${dark}</head>`);
}

let busSeq = 0;
export function publish(channel: string, payload: unknown) {
  window.__qvBus = window.__qvBus || {};
  window.__qvBus[channel] = { v: `v${++busSeq}`, d: payload };
}

interface Props {
  scene: SceneName; channel?: string; title?: string; data?: Record<string, unknown>; payload?: unknown;
  className?: string; style?: React.CSSProperties; label: string; onReady?: () => void;
}

export function LegacyScene({ scene, channel, title, data, payload, className, style, label, onReady }: Props) {
  const [doc, setDoc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const ch = channel || scene;
  // The document is built once per mount: data that changes goes through the bus.
  const theme = usePrefs((st) => st.theme);
  const motion = usePrefs((st) => st.motion);
  const resolved = resolvedTheme(theme);
  // Rebuilt when the theme or motion preference changes; live data still goes through the bus.
  const init = useMemo(() => ({ channel: ch, title, theme: resolved, reducedMotion: reducedMotion(motion), ...(data || {}) }), [ch, resolved, motion]); // eslint-disable-line react-hooks/exhaustive-deps
  const ref = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    let alive = true;
    buildDoc(scene, init).then((d) => alive && setDoc(d)).catch(() => alive && setFailed(true));
    return () => { alive = false; };
  }, [scene, init]);

  useEffect(() => { if (payload !== undefined) publish(ch, payload); }, [ch, payload, doc]);
  useEffect(() => () => { if (window.__qvBus) delete window.__qvBus[ch]; }, [ch]);

  if (failed || !webglAvailable()) {
    return <div className={`legacy-fallback ${className || ''}`} style={style} role="img" aria-label={label}>
      <div className="empty"><div className="orb" /><h4>3D scene unavailable</h4><p>This browser has no WebGL. All numbers remain available in the panels.</p></div>
    </div>;
  }
  return (
    <iframe
      ref={ref}
      className={`legacy-scene ${className || ''}`}
      style={style}
      title={label}
      aria-label={label}
      srcDoc={doc || `<!doctype html><html><body style="margin:0;background:${resolved === 'noir' ? '#060816' : '#EAEDF7'}"></body></html>`}
      onLoad={() => doc && onReady?.()}
      allow="fullscreen"
    />
  );
}

let _webgl: boolean | null = null;
export function webglAvailable(): boolean {
  if (_webgl != null) return _webgl;
  try {
    const c = document.createElement('canvas');
    _webgl = !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch { _webgl = false; }
  return _webgl;
}
