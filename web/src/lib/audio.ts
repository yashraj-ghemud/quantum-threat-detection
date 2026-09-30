/* A tiny WebAudio synth. No audio files; off by default; enabled only after a gesture. */
import { getPrefs } from '@/state/prefs';

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let lastAt = 0;
function ac(): AudioContext | null {
  if (!getPrefs().sound) return null;
  try {
    if (!ctx) {
      ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      master = ctx.createGain(); master.gain.value = 0.15; master.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  } catch { return null; }
}
function tone(freq: number, dur: number, type: OscillatorType = 'sine', gain = 0.5, delay = 0) {
  const c = ac(); if (!c || !master) return;
  const now = c.currentTime + delay;
  const o = c.createOscillator(), g = c.createGain();
  o.type = type; o.frequency.setValueAtTime(freq, now);
  g.gain.setValueAtTime(0, now); g.gain.linearRampToValueAtTime(gain, now + 0.008); g.gain.exponentialRampToValueAtTime(0.0001, now + dur);
  o.connect(g); g.connect(master); o.start(now); o.stop(now + dur + 0.02);
}
function throttle(ms: number) { const n = performance.now(); if (n - lastAt < ms) return false; lastAt = n; return true; }
export const sfx = {
  accept() { if (throttle(120)) { tone(880, 0.25, 'sine', 0.35); tone(1320, 0.3, 'sine', 0.2, 0.05); } },
  reject() { if (throttle(120)) { tone(311, 0.4, 'triangle', 0.35); tone(330, 0.4, 'triangle', 0.3); } },
  alarm() { tone(60, 0.9, 'sawtooth', 0.25); tone(90, 0.7, 'square', 0.08, 0.05); },
  block() { if (throttle(200)) { tone(1046, 0.18, 'sine', 0.2); tone(1318, 0.18, 'sine', 0.18, 0.07); tone(1568, 0.3, 'sine', 0.16, 0.14); } },
  tick() { tone(2400, 0.02, 'square', 0.03); },
};
