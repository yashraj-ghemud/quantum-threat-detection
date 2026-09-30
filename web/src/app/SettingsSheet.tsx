import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Drawer } from '@/components/overlays';
import { Segmented, Toggle, Button } from '@/components/ui';
import { usePrefs } from '@/state/prefs';
import { useUi, toast } from '@/state/ui';
import { ep, qk } from '@/api/endpoints';
import { friendly } from '@/api/client';
import { reconnectNow, disconnect } from '@/stream/socket';
import { int } from '@/lib/format';

export function SettingsSheet() {
  const open = useUi((s) => s.settingsOpen);
  const set = useUi((s) => s.set);
  const p = usePrefs();
  const qc = useQueryClient();
  const cfg = useQuery({ queryKey: qk.config, queryFn: ep.config, enabled: open });
  const presets = cfg.data ? Object.values(cfg.data.presets).filter((x) => ['demo', 'standard', 'high'].includes(x.preset)) : [];
  return (
    <Drawer open={open} onClose={() => set({ settingsOpen: false })} title="Settings">
      <div className="stack" style={{ ['--gap' as string]: '22px' }}>
        <div className="field"><span className="label">Theme</span>
          <Segmented label="Theme" value={p.theme} onChange={(v) => p.set({ theme: v })} options={[{ value: 'mist', label: 'Mist (original)' }, { value: 'noir', label: 'Noir' }, { value: 'system', label: 'System' }]} /></div>
        <div className="field"><span className="label">Motion</span>
          <Segmented label="Motion" value={p.motion} onChange={(v) => p.set({ motion: v })} options={[{ value: 'system', label: 'System' }, { value: 'full', label: 'Full' }, { value: 'reduced', label: 'Reduced' }]} /></div>
        <div className="field"><span className="label">3D quality</span>
          <Segmented label="Quality" value={p.quality} onChange={(v) => p.set({ quality: v })} options={[{ value: 'auto', label: 'Auto' }, { value: 'high', label: 'High' }, { value: 'medium', label: 'Medium' }, { value: 'low', label: 'Low' }]} /></div>
        <div className="stack" style={{ ['--gap' as string]: '12px' }}>
          <Toggle checked={p.cursor} onChange={(v) => p.set({ cursor: v })} label="Spring cursor with sparks (mouse only)" />
          <Toggle checked={p.sound} onChange={(v) => p.set({ sound: v })} label="Sound (WebAudio synth, no files)" />
          <Toggle checked={p.haptics} onChange={(v) => p.set({ haptics: v })} label="Haptics on critical incidents (mobile)" />
          <Toggle checked={p.introSeen} onChange={(v) => p.set({ introSeen: v })} label="Skip the intro film on Overview" />
        </div>
        <hr style={{ margin: 0 }} />
        <div className="field">
          <span className="label">Security preset (server-wide)</span>
          {cfg.data ? (
            <>
              <Segmented label="Preset" value={cfg.data.active_preset} onChange={async (v) => {
                try { await ep.setPreset(v); await qc.invalidateQueries(); toast({ tone: 'ok', title: `Preset set to ${v}`, body: 'New distributions use it; existing bundles keep theirs.' }); }
                catch (e) { toast({ tone: 'warn', title: friendly(e) }); }
              }} options={presets.map((x) => ({ value: x.preset, label: x.preset }))} />
              <div className="xs muted">{presets.map((x) => `${x.preset}: L = ${int(x.L)}, targets ε_rob ${x.eps_rob_target}, ε_forge ${x.eps_forge_target}, ε_rep ${x.eps_rep_target}`).join(' · ')}</div>
            </>
          ) : <div className="skeleton" style={{ height: 36 }} />}
        </div>
        <details>
          <summary className="label" style={{ cursor: 'pointer' }}>Advanced</summary>
          <div className="stack" style={{ marginTop: 12 }}>
            <div className="field"><label className="label" htmlFor="apibase">API base (empty = same origin)</label>
              <input id="apibase" className="input" placeholder="http://localhost:8000" defaultValue={p.apiBase} onBlur={(e) => { p.set({ apiBase: e.target.value.trim() }); disconnect(); reconnectNow(); qc.invalidateQueries(); }} /></div>
            <div className="field"><label className="label" htmlFor="apikey">API key (only if the server sets QVERIS_API_KEY)</label>
              <input id="apikey" className="input" type="password" defaultValue={p.apiKey} onBlur={(e) => p.set({ apiKey: e.target.value.trim() })} /></div>
            <Button size="sm" onClick={() => { try { sessionStorage.removeItem('qveris.booted'); } catch { /* ignore */ } location.reload(); }}>Replay boot sequence</Button>
          </div>
        </details>
        <p className="xs faint">Preferences are stored in this browser only. Keyboard: ⌘K palette · g then c/s/a/p/n/l/i/m to navigate · , settings.</p>
      </div>
    </Drawer>
  );
}
