// Copies three@0.165 (the version the original QVeris scenes were authored
// against) plus exactly the addon modules they import, with their relative
// dependencies, into public/vendor/three. The scenes then run fully offline.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, '../node_modules/three-legacy');
const out = path.resolve(here, '../public/vendor/three');
const ENTRY = [
  'build/three.module.js',
  'examples/jsm/environments/RoomEnvironment.js',
  'examples/jsm/postprocessing/EffectComposer.js',
  'examples/jsm/postprocessing/RenderPass.js',
  'examples/jsm/postprocessing/UnrealBloomPass.js',
  'examples/jsm/postprocessing/OutputPass.js',
  'examples/jsm/controls/OrbitControls.js',
  'examples/jsm/geometries/RoundedBoxGeometry.js',
  'examples/jsm/loaders/FontLoader.js',
  'examples/jsm/geometries/TextGeometry.js',
  'examples/fonts/helvetiker_bold.typeface.json',
];
const seen = new Set();
function copy(rel) {
  if (seen.has(rel)) return;
  seen.add(rel);
  const from = path.join(src, rel), to = path.join(out, rel);
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
  if (!rel.endsWith('.js')) return;
  const text = fs.readFileSync(from, 'utf8');
  for (const m of text.matchAll(/(?:from|import)\s*['"](\.{1,2}\/[^'"]+)['"]/g)) {
    copy(path.posix.normalize(path.posix.join(path.posix.dirname(rel), m[1])));
  }
}
if (!fs.existsSync(src)) { console.error('three-legacy is not installed'); process.exit(1); }
ENTRY.forEach(copy);
// three.module.js imports three.core.js in newer builds; copy siblings if referenced.
console.log(`vendored ${seen.size} three@0.165 files into public/vendor/three`);
