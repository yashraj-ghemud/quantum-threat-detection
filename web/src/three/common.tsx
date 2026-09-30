import { Component, type ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { Canvas, type CanvasProps } from '@react-three/fiber';
import { qualityTier, reducedMotion, usePrefs } from '@/state/prefs';
import { webglAvailable } from '@/legacy/LegacyScene';

/** Canvas wrapper: quality-tier DPR, pause off-screen, reduced-motion demand loop, 2D fallback. */
export function SceneCanvas({ children, fallback, label, style, className, ...rest }: CanvasProps & { fallback: ReactNode; label: string; className?: string }) {
  const quality = usePrefs((s) => s.quality);
  const motion = usePrefs((s) => s.motion);
  const tier = qualityTier(quality);
  const reduce = reducedMotion(motion);
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { rootMargin: '80px' });
    io.observe(el); return () => io.disconnect();
  }, []);
  if (!webglAvailable()) return <div className={className} style={style}>{fallback}</div>;
  return (
    <div ref={ref} className={className} style={{ position: 'relative', ...style }} role="img" aria-label={label} data-cursor="">
      <GLBoundary fallback={fallback}>
        <Canvas dpr={tier === 'high' ? [1, 2] : tier === 'medium' ? [1, 1.5] : [1, 1.25]} frameloop={!visible ? 'never' : reduce ? 'demand' : 'always'}
          gl={{ antialias: tier !== 'low', alpha: true, powerPreference: 'high-performance' }} {...rest}>
          {children}
        </Canvas>
      </GLBoundary>
    </div>
  );
}

class GLBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

export function readVar(name: string, fallback = '#8C84F0') {
  try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback; } catch { return fallback; }
}
export const NODE_HEX: Record<string, string> = { alice: '--alice', diana: '--diana', bob: '--bob', charlie: '--charlie', erin: '--erin', eve: '--threat', mallory: '--mallory' };

/** A billboard label rendered to a canvas texture (no DOM overlay). */
export function LabelSprite({ title, sub, color, position = [0, 0, 0], scale = 1, dark = false }: { title: string; sub?: string; color: string; position?: [number, number, number]; scale?: number; dark?: boolean }) {
  const tex = useMemo(() => {
    const W = 512, H = sub ? 176 : 120;
    const c = document.createElement('canvas'); c.width = W; c.height = H;
    const ctx = c.getContext('2d')!;
    ctx.font = '700 58px "Space Grotesk", Inter, sans-serif';
    const tw = Math.min(W - 16, Math.max(ctx.measureText(title).width + 64, sub ? 230 : 0));
    const x = (W - tw) / 2, r = 40;
    ctx.beginPath(); ctx.moveTo(x + r, 8); ctx.arcTo(x + tw, 8, x + tw, H - 8, r); ctx.arcTo(x + tw, H - 8, x, H - 8, r); ctx.arcTo(x, H - 8, x, 8, r); ctx.arcTo(x, 8, x + tw, 8, r); ctx.closePath();
    ctx.fillStyle = dark ? 'rgba(43,39,66,.94)' : 'rgba(246,247,253,.9)'; ctx.fill();
    ctx.lineWidth = 4; ctx.strokeStyle = color; ctx.globalAlpha = 0.55; ctx.stroke(); ctx.globalAlpha = 1;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillStyle = dark ? '#ffffff' : '#1E2440'; ctx.fillText(title, W / 2, sub ? 64 : H / 2 + 2);
    if (sub) { ctx.font = '600 30px "JetBrains Mono", monospace'; ctx.fillStyle = color; ctx.fillText(sub.toUpperCase(), W / 2, 128); }
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
    return { t, aspect: W / H };
  }, [title, sub, color, dark]);
  useEffect(() => () => tex.t.dispose(), [tex]);
  const h = 0.62 * scale;
  return <sprite position={position} scale={[h * tex.aspect, h, 1]} renderOrder={20}><spriteMaterial map={tex.t} transparent depthWrite={false} depthTest={false} toneMapped={false} /></sprite>;
}
