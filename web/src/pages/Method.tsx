import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ep, qk } from '@/api/endpoints';
import { Formula } from '@/components/Formula';
import { Chip, Panel } from '@/components/ui';
import { int, sci } from '@/lib/format';

const TOC = [['problem', 'The problem'], ['overview', 'System overview'], ['protocol', 'The TQDS protocol'], ['teleport', 'Six-state keys & teleportation'], ['bell', 'Bell certification'],
  ['tomography', 'De-twirled tomography'], ['detection', 'Detection layers'], ['bounds', 'Security bounds'], ['ledger', 'Audit ledger'], ['threats', 'Threat model'], ['limits', 'Assumptions & limits'], ['refs', 'References']] as const;

export default function Method() {
  const cfg = useQuery({ queryKey: qk.config, queryFn: ep.config, staleTime: 60_000 });
  const dets = useQuery({ queryKey: qk.detectors, queryFn: ep.detectors, staleTime: Infinity });
  const preset = cfg.data?.presets?.[cfg.data.active_preset];
  const d = useQuery({ queryKey: ['theory', 'design', 'method', preset?.L], enabled: !!preset, staleTime: 60_000,
    queryFn: () => ep.design({ L: preset!.L, e: 0.0125, eps_rob: preset!.eps_rob_target, eps_forge: preset!.eps_forge_target, eps_rep: preset!.eps_rep_target }) });
  const [active, setActive] = useState('problem');
  useEffect(() => {
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) setActive(e.target.id); }), { rootMargin: '-30% 0px -60% 0px' });
    TOC.forEach(([id]) => { const el = document.getElementById(id); if (el) io.observe(el); });
    return () => io.disconnect();
  }, []);
  const D = d.data;
  return (
    <div className="method">
      <nav className="method-toc" aria-label="Contents">{TOC.map(([id, t]) => <a key={id} href={`#${id}`} className={active === id ? 'on' : ''}>{t}</a>)}</nav>
      <article className="method-body">
        <span className="kicker">Method</span><h1>How QVeris defends a signature with physics</h1>
        <p className="lead">QVeris implements a <b>teleportation-based quantum digital signature</b> (QDS) and a physics-grounded threat detector, <b>QSentinel</b>. Security comes from exact statistics over measured quantum data, not from a trained model: there is no AI/ML anywhere in the decision path.</p>

        <section id="problem"><h2>The problem</h2>
          <p>Classical signatures rest on computational assumptions that large quantum computers undermine. Quantum digital signatures instead give <i>information-theoretic</i> unforgeability and non-repudiation, but only if the quantum channel is honest. SIH problem 26141 asks for quantum-inspired detection of threats to signature security. QVeris answers with a QDS protocol whose every quantum step is measured and audited, and a detector that names the attack: forgery, impersonation, replay, unauthorized verification, channel manipulation or repudiation.</p></section>

        <section id="overview"><h2>System overview</h2>
          <svg viewBox="0 0 760 210" width="100%" className="arch" role="img" aria-label="Architecture: engine, detection, server, ledger, web">
            {[['Sentinel engine', 'exact superoperators · Bell · teleport', 20, 'var(--sky)'], ['TQDS protocol', 'distribute · sign · verify · transfer', 200, 'var(--lav)'], ['QSentinel', 'D1–D10 · S1–S10 · fusion', 380, 'var(--coral)'], ['Ledger', 'hash chain · Merkle', 560, 'var(--gold)']].map(([t, s, x, c]) => (
              <g key={t as string} transform={`translate(${x},30)`}><rect width={170} height={70} rx={16} fill="var(--bg-2)" stroke={c as string} strokeWidth={2} /><text x={85} y={32} textAnchor="middle" fontWeight={700} fontSize={14} fill="var(--text-0)">{t}</text><text x={85} y={52} textAnchor="middle" fontSize={10.5} fill="var(--text-2)">{s}</text></g>))}
            {[190, 370, 550].map((x) => <path key={x} d={`M${x},65 l10,0`} stroke="var(--text-2)" strokeWidth={2} markerEnd="url(#ar)" />)}
            <defs><marker id="ar" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="var(--text-2)" /></marker></defs>
            <g transform="translate(200,140)"><rect width={350} height={50} rx={14} fill="var(--lav-l)" /><text x={175} y={30} textAnchor="middle" fontSize={13} fontWeight={600} fill="var(--text-0)">FastAPI · SQLite · WebSocket → this web app</text></g>
            <path d="M375,100 L375,140" stroke="var(--text-2)" strokeWidth={2} strokeDasharray="4 4" />
          </svg></section>

        <section id="protocol"><h2>The TQDS protocol</h2>
          <ol>
            <li><b>Distribution.</b> For each digest bit the signer holds two one-time keys, each of <Formula tex={`L = ${int(preset?.L ?? 4096)}`} /> random six-state qubits. Every qubit is <i>teleported</i> to each recipient over a Bell pair certified by CHSH; the recipient measures in a random basis and keeps its records.</li>
            <li><b>Parameter estimation.</b> A fraction of positions is revealed to estimate the per-basis error and fingerprint the channel; the honest error bound <Formula tex="e_{ucb}" /> sets the thresholds.</li>
            <li><b>Symmetrization.</b> Recipients swap a random half of their records over an authenticated channel, so a signer cannot target one of them.</li>
            <li><b>Signing.</b> The SHA-256 digest of the envelope (message, signer, recipients, sequence, timestamp, nonce) selects one key per bit; the signer reveals its labels.</li>
            <li><b>Verification.</b> The first recipient accepts if every key has <Formula tex="m \le s_a\,n" /> mismatches on the positions measured in the revealed basis; a transferee uses the looser <Formula tex="s_v" />, which is what makes transfer safe.</li>
          </ol></section>

        <section id="teleport"><h2>Six-state keys & teleportation</h2>
          <p>Key labels are uniform over <Formula tex="\{|0\rangle,|1\rangle,|+\rangle,|-\rangle,|{+i}\rangle,|{-i}\rangle\}" />. Teleportation turns a Bell pair and two classical bits into a quantum channel:</p>
          <Formula display tex="|\psi\rangle_A |\Phi^+\rangle_{A'B} = \tfrac12 \sum_{k} |\beta_k\rangle_{AA'} \otimes \sigma_k |\psi\rangle_B,\qquad \rho_B = \sigma_c\,\mathcal N\!\big(\sigma_k \rho\, \sigma_k\big)\,\sigma_c" />
          <p>The engine computes the exact outcome-conditioned superoperators <Formula tex="R_k" /> of the three-qubit circuit and samples from them; it agrees with Qiskit Aer to machine precision (see Analytics → validation) while running hundreds of times faster.</p></section>

        <section id="bell"><h2>Bell certification</h2>
          <Formula display tex="S = E(A_0,B_0)+E(A_0,B_1)+E(A_1,B_0)-E(A_1,B_1),\qquad S_{local}\le 2 < S_{quantum}\le 2\sqrt2" />
          <p>Sacrificial pairs are measured in randomly chosen CHSH settings and in the X/Y/Z bases for the fidelity witness <Formula tex="F = \tfrac14(1+\langle XX\rangle-\langle YY\rangle+\langle ZZ\rangle)" />. Exact Clopper–Pearson bounds give <Formula tex="S_{lcb}" /> and <Formula tex="F_{lcb}" />; a link whose <Formula tex="S_{lcb}\le 2" /> is refused. At the active preset each setting uses {int(preset?.bell_pairs_per_setting as number)} pairs.</p></section>

        <section id="tomography"><h2>De-twirled tomography</h2>
          <p>Averaged over the random frame <Formula tex="k" />, teleportation <i>twirls</i> any channel into a Pauli channel, hiding amplitude damping and coherent rotations. But the signer knows <Formula tex="k" /> and the verifier knows the correction <Formula tex="c" />, so each estimation outcome is an unbiased sample of the channel at a known input:</p>
          <Formula display tex="\mathcal N\big(r_{\pi_k(\ell)}\big) = P_c\, r_{\mathrm{fin}}" />
          <p>From these the engine reconstructs the Bloch map <Formula tex="r \mapsto Mr + c" /> and a fingerprint names its shape (isotropic, dephasing, amplitude damping, coherent rotation, classical frame) with physically equivalent alternatives.</p></section>

        <section id="detection"><h2>Detection layers</h2>
          <p>Twenty detectors run on every distribution and signature; statistical ones share a Holm–Bonferroni family-wise α of <b>{sci((cfg.data?.detection?.alpha_family as number) ?? null)}</b> with effect-size floors. A deterministic decision list fuses them into a verdict and a classification.</p>
          <div className="table-wrap"><table className="table"><thead><tr><th>id</th><th>detector</th><th>layer</th><th>statistic</th><th /></tr></thead><tbody>
            {(dets.data || []).map((x) => <tr key={x.id}><td className="mono xs">{x.id}</td><td><b className="small">{x.name}</b><div className="xs muted">{x.description}</div></td><td className="xs">{x.layer}</td><td className="xs">{x.statistic}</td><td>{x.conclusive ? <Chip tone="lav">conclusive</Chip> : <Chip>statistical</Chip>}</td></tr>)}
          </tbody></table></div></section>

        <section id="bounds"><h2>Security bounds (live, preset {cfg.data?.active_preset})</h2>
          <p>With <Formula tex={`L=${int(preset?.L ?? 0)}`} />, a tested count of at least <Formula tex={`n_{min}=${D?.n_min ?? '\\cdot'}`} /> positions and an honest error bound <Formula tex={`e=${D ? (D.e_ucb * 100).toFixed(2) : '\\cdot'}\\%`} />, the designer chooses <Formula tex={`s_a=${D ? (D.s_a * 100).toFixed(2) : '\\cdot'}\\%`} /> and <Formula tex={`s_v=${D ? (D.s_v * 100).toFixed(2) : '\\cdot'}\\%`} /> from exact tails:</p>
          <Formula display tex={`\\varepsilon_{rob} \\le \\sum_{keys} \\Pr[\\mathrm{Bin}(n,e) > s_a n] = ${D ? D.eps_rob_msg.toExponential(2).replace('e', '\\times 10^{') + '}' : '\\cdot'}`} />
          <Formula display tex={`\\varepsilon_{forge} = \\Pr[\\mathrm{Bin}(n,\\tfrac13) \\le s_v n] = ${D ? D.eps_forge_key.toExponential(2).replace('e', '\\times 10^{') + '}' : '\\cdot'}`} />
          <Formula display tex={`\\varepsilon_{rep} \\le \\text{hypergeometric split tail} = ${D ? D.eps_rep_msg.toExponential(2).replace('e', '\\times 10^{') + '}' : '\\cdot'}`} />
          <p className="small muted">1/3 is the optimal insider mismatch over all measurement directions for six-state keys (Analytics → forgery shows the full sphere). Targets for this preset: ε_rob ≤ {sci(preset?.eps_rob_target)}, ε_forge ≤ {sci(preset?.eps_forge_target)}, ε_rep ≤ {sci(preset?.eps_rep_target)}.</p></section>

        <section id="ledger"><h2>Audit ledger</h2><p>Every session, incident, response and configuration change becomes a transaction; blocks commit to the previous block hash and to a Merkle root over canonical-JSON transaction hashes. Verification recomputes every leaf, root and link; a single rewritten row is pinpointed to its block, and inclusion proofs can be re-checked in the browser.</p></section>

        <section id="threats"><h2>Threat model</h2>
          <div className="grid g2">{[['Forgery', 'external (blind), insider (holds a recipient’s records), hash near-collision oracle'], ['Impersonation', 'identity swap, keyless'], ['Replay', 'resubmission, forward replay, delayed delivery'],
            ['Unauthorized verification', 'non-recipient verifier, man-in-the-middle key harvesting'], ['Channel manipulation', 'depolarizing, dephasing, amplitude damping, coherent rotation, intercept–resend, Pauli-frame tampering, low-and-slow drift'], ['Repudiation', 'signer sends inconsistent copies to force a dispute']].map(([t, s]) => <Panel key={t} tight><b>{t}</b><p className="small muted" style={{ margin: '6px 0 0' }}>{s}</p></Panel>)}</div></section>

        <section id="limits"><h2>Assumptions & limits</h2>
          <ul>
            <li>The quantum hardware is simulated exactly (noise models, Bell sources, detectors as channels); loss is modelled as post-selected heralding time, not as signal.</li>
            <li>Recipients’ symmetrization channel and the classical frame bits are assumed authenticated where the preset says so (a Wegman–Carter MAC is available per link).</li>
            <li>The <i>demo</i> preset trades repudiation strength for speed and is labelled as such; <i>standard</i> and <i>high</i> meet all targets.</li>
            <li>Some channels are physically indistinguishable (e.g. z-dephasing and z-basis intercept-resend on a fraction of pairs); the classifier reports them as alternatives rather than guessing.</li>
          </ul></section>

        <section id="refs"><h2>References</h2>
          <ol className="small">
            <li>D. Gottesman, I. Chuang, “Quantum digital signatures”, arXiv:quant-ph/0105032 (2001).</li>
            <li>P. Wallden, V. Dunjko, A. Kent, E. Andersson, “Quantum digital signatures with quantum-key-distribution components”, Phys. Rev. A 91, 042304 (2015).</li>
            <li>R. Amiri, P. Wallden, A. Kent, E. Andersson, “Secure quantum signatures using insecure quantum channels”, Phys. Rev. A 93, 032325 (2016).</li>
            <li>J. F. Clauser, M. A. Horne, A. Shimony, R. A. Holt, “Proposed experiment to test local hidden-variable theories”, PRL 23, 880 (1969).</li>
            <li>A. Wald, “Sequential tests of statistical hypotheses”, Ann. Math. Stat. 16, 117 (1945). E. S. Page, “Continuous inspection schemes”, Biometrika 41, 100 (1954).</li>
            <li>S. Holm, “A simple sequentially rejective multiple test procedure”, Scand. J. Stat. 6, 65 (1979).</li>
          </ol></section>
      </article>
    </div>
  );
}
