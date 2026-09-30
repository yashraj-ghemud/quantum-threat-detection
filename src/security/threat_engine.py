"""
security/threat_engine.py
=========================
Deterministic, explainable threat detection.

SIH26141 | Blockchain & Cybersecurity.

No AI, no ML, no fitted model, no black box. Every number below is a
closed-form function of measured session telemetry, and every decision
comes with the evidence that produced it.

The anomaly score
-----------------
Four statistical indicators are normalised against a *measured* legitimate
baseline and combined linearly::

    anomaly_score = w_m * n_mismatch
                  + w_f * n_fidelity
                  + w_t * n_trace
                  + w_e * n_entropy

Each ``n_*`` is a one-sided normalised deviation from baseline, clipped to
[0, 1]:

    n_mismatch = clip( (mismatch - mu_mismatch) / NORM_MISMATCH , 0, 1)
    n_fidelity = clip( (mu_fidelity - fidelity) / NORM_FIDELITY , 0, 1)
    n_trace    = clip( (trace_dist - mu_trace)  / NORM_TRACE    , 0, 1)
    n_entropy  = clip( |entropy - mu_entropy|   / NORM_ENTROPY  , 0, 1)

One-sided because only one direction is suspicious: *more* mismatch, *less*
fidelity, *more* trace distance. Entropy is two-sided -- both an unusually
disordered and an unusually ordered outcome distribution are informative.

Why these weights
-----------------
The weights are not tuned to make results look good; they are fixed a
priori from how directly each indicator reflects a protocol violation:

============  ======  ==========================================================
indicator     weight  rationale
============  ======  ==========================================================
mismatch      0.40    The most direct evidence. A mismatch is a measured
                      disagreement between the received state and the
                      verifier's own key -- it *is* the signature failing.
fidelity      0.25    Physical distance of the received state from the sent
                      one. Catches channel damage that has not yet flipped
                      enough elements to move the mismatch rate.
trace dist.   0.25    Bounds single-shot distinguishability, so it is the
                      principled measure of "how detectable is this
                      disturbance". Weighted equally with fidelity because
                      the two are related but not redundant (a unitary
                      error moves fidelity while preserving purity).
entropy       0.10    Weakest and noisiest indicator at these shot counts,
                      so it contributes least; it is retained because it
                      responds to distribution-shape changes the other
                      three can miss.
============  ======  ==========================================================

The weights sum to 1.0, so the score stays in [0, 1] and is directly
comparable with a threshold on the same scale.

The normalisers (``NORM_*``) set what counts as a *fully* anomalous
deviation, and are documented at their definitions below.

Threshold
---------
The threshold is **not** hardcoded here. It is read from
``config/quantum_config.yaml`` if calibration has written one, and
otherwise falls back to a documented default. Calibration is performed by
``experiments/calibrate_threshold.py``, which sweeps candidate thresholds
over measured legitimate and attack sessions and selects an operating
point by a stated rule.

Attack classification
---------------------
Classification is a deterministic decision list over protocol facts and
telemetry signatures, evaluated in order of specificity. Protocol
violations (authorization, freshness, key binding) are checked first
because they are conclusive; statistical signatures are consulted only
afterwards. Each branch records why it fired.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "ThreatEngine",
    "WEIGHTS",
    "NORM_MISMATCH",
    "NORM_FIDELITY",
    "NORM_TRACE",
    "NORM_ENTROPY",
    "DEFAULT_WARNING_THRESHOLD",
    "DEFAULT_CRITICAL_THRESHOLD",
]

#: Indicator weights. Fixed a priori; see the module docstring for the
#: rationale behind each. They sum to 1.0.
WEIGHTS: Dict[str, float] = {
    "mismatch": 0.40,
    "fidelity": 0.25,
    "trace_distance": 0.25,
    "entropy": 0.10,
}

#: Deviation treated as fully anomalous (normalised indicator = 1.0).
#:
#: NORM_MISMATCH = 0.50: a blind forger matches ~1/2 of elements under
#: single-copy measurement, so a 50-point rise over baseline is total
#: failure of the signature.
NORM_MISMATCH: float = 0.50
#: NORM_FIDELITY = 0.50: fidelity 0.5 is the maximally-mixed floor for a
#: qubit -- a 0.5 drop means all state information is gone.
NORM_FIDELITY: float = 0.50
#: NORM_TRACE = 0.50: trace distance 0.5 already gives an adversary a
#: strong single-shot distinguishing advantage.
NORM_TRACE: float = 0.50
#: NORM_ENTROPY = 1.00: one full bit is the entire range of a binary
#: outcome distribution.
NORM_ENTROPY: float = 1.00

#: Fallback thresholds, used only when calibration has not written one.
DEFAULT_WARNING_THRESHOLD: float = 0.07
DEFAULT_CRITICAL_THRESHOLD: float = 0.20


class ThreatEngine:
    """Scores a session and classifies it, with explicit evidence.

    Parameters
    ----------
    baseline : dict
        Measured legitimate-session statistics from
        ``SessionRunner.calibrate_baseline``.
    warning_threshold, critical_threshold : float or None
        Operating points. ``None`` reads the calibrated values from config,
        falling back to the documented defaults.
    """

    def __init__(
        self,
        baseline: Dict[str, float],
        warning_threshold: Optional[float] = None,
        critical_threshold: Optional[float] = None,
    ) -> None:
        self.baseline = baseline
        warn, crit = self._load_thresholds()
        self.warning_threshold = (
            warn if warning_threshold is None else warning_threshold
        )
        self.critical_threshold = (
            crit if critical_threshold is None else critical_threshold
        )

    @staticmethod
    def _load_thresholds() -> Tuple[float, float]:
        """Read calibrated thresholds from config, else use defaults."""
        try:
            from utils.config import ConfigLoader

            cfg = ConfigLoader()
            warn = cfg.get_nested(
                "detection", "warning_threshold", default=DEFAULT_WARNING_THRESHOLD
            )
            crit = cfg.get_nested(
                "detection", "critical_threshold", default=DEFAULT_CRITICAL_THRESHOLD
            )
            return float(warn), float(crit)
        except Exception:  # pragma: no cover - config always present in repo
            return DEFAULT_WARNING_THRESHOLD, DEFAULT_CRITICAL_THRESHOLD

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def indicators(self, result) -> Dict[str, float]:
        """Compute the four normalised indicators for *result*.

        Returns
        -------
        dict[str, float]
            Each in [0, 1], keyed as in :data:`WEIGHTS`.
        """
        t = result.telemetry
        b = self.baseline

        n_mismatch = _clip01(
            (t.mismatch_rate - b.get("mismatch_mean", 0.0)) / NORM_MISMATCH
        )
        n_fidelity = _clip01(
            (b.get("fidelity_mean", 1.0) - t.mean_fidelity) / NORM_FIDELITY
        )
        n_trace = _clip01(
            (t.mean_trace_distance - b.get("trace_distance_mean", 0.0)) / NORM_TRACE
        )
        n_entropy = _clip01(
            abs(t.measurement_entropy - b.get("entropy_mean", 0.0)) / NORM_ENTROPY
        )

        return {
            "mismatch": n_mismatch,
            "fidelity": n_fidelity,
            "trace_distance": n_trace,
            "entropy": n_entropy,
        }

    def anomaly_score(self, result) -> Tuple[float, Dict[str, float]]:
        """Return ``(score, indicators)`` for *result*."""
        ind = self.indicators(result)
        score = sum(WEIGHTS[k] * v for k, v in ind.items())
        return float(np.clip(score, 0.0, 1.0)), ind

    #: Baseline spread below which a z-score is not meaningful.
    _MIN_STD_FOR_Z = 1e-4

    def z_score(self, result) -> Optional[float]:
        """Mismatch-rate z-score against the measured baseline.

        Returns ``None`` when the baseline has essentially no spread. With
        a clean channel every legitimate session mismatches exactly zero
        elements, so the standard deviation is 0 and a z-score would divide
        by the clamp floor -- yielding values like 5.6e5 that look like
        precision but carry no information.
        """
        b = self.baseline
        sd = b.get("mismatch_std", 0.0)
        if sd < self._MIN_STD_FOR_Z:
            return None
        return float((result.telemetry.mismatch_rate - b.get("mismatch_mean", 0.0)) / sd)

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def evaluate(self, result) -> Any:
        """Score, classify and explain *result*, mutating it in place.

        Sets ``anomaly_score``, ``threshold``, ``decision``,
        ``detected_attack`` and ``evidence``.
        """
        score, ind = self.anomaly_score(result)
        z = self.z_score(result)

        result.anomaly_score = score
        result.threshold = self.warning_threshold
        result.telemetry.entropy_deviation = ind["entropy"]

        evidence: List[str] = []

        # An indicator must clear this before it is cited as evidence.
        # Without it, ordinary shot-noise jitter is reported as a "drop" on
        # perfectly clean sessions, which trains the reader to ignore the
        # evidence list.
        MATERIAL = 0.01

        # --- Protocol violations: conclusive, checked first -------------
        protocol_attack: Optional[str] = None

        if not result.authorized:
            protocol_attack = "UNAUTHORIZED_VERIFICATION"
            evidence.append(
                f"authorization_failure: verifier {result.verifier_id!r} "
                "is not on the allow-list"
            )

        if not result.session_fresh:
            # Freshness failure on an otherwise quantum-valid signature is
            # the definitive replay signature.
            protocol_attack = protocol_attack or "REPLAY"
            for r in result.freshness_reasons:
                evidence.append(f"session_freshness: {r}")

        if not result.key_binding_valid:
            protocol_attack = protocol_attack or "IMPERSONATION"
            evidence.append(
                "key_binding_failure: signature key_id does not match the "
                "verifier's public key"
            )

        if not result.message_binding_valid:
            protocol_attack = protocol_attack or "FORGERY"
            evidence.append(
                "message_binding_failure: signature does not cover this message"
            )

        # --- Statistical evidence ---------------------------------------
        if ind["mismatch"] > MATERIAL:
            z_txt = f" (z={z:+.2f})" if z is not None else ""
            evidence.append(
                f"measurement_mismatch: rate {result.telemetry.mismatch_rate:.4f} "
                f"vs baseline {self.baseline.get('mismatch_mean', 0.0):.4f}{z_txt}"
            )
        if ind["fidelity"] > MATERIAL:
            evidence.append(
                f"fidelity_drop: {result.telemetry.mean_fidelity:.4f} "
                f"vs baseline {self.baseline.get('fidelity_mean', 1.0):.4f}"
            )
        if ind["trace_distance"] > MATERIAL:
            evidence.append(
                f"trace_distance_increase: {result.telemetry.mean_trace_distance:.4f} "
                f"vs baseline {self.baseline.get('trace_distance_mean', 0.0):.4f}"
            )
        if ind["entropy"] > max(MATERIAL, 0.05):
            evidence.append(
                f"entropy_deviation: {result.telemetry.measurement_entropy:.4f} "
                f"vs baseline {self.baseline.get('entropy_mean', 0.0):.4f}"
            )

        for b in ("x", "y", "z"):
            d = getattr(result.telemetry, f"{b}_deviation")
            if d is not None and d > 0.15:
                evidence.append(
                    f"{b}_basis_deviation: {d:.4f} of expected distribution"
                )

        # --- Decision ----------------------------------------------------
        statistical_threat = score >= self.critical_threshold
        statistical_warn = score >= self.warning_threshold

        if protocol_attack is not None:
            decision = "THREAT"
            attack = protocol_attack
        elif statistical_threat:
            decision = "THREAT"
            attack = self._classify_statistical(result, ind)
        elif statistical_warn:
            decision = "SUSPICIOUS"
            attack = self._classify_statistical(result, ind)
        else:
            decision = "LEGITIMATE"
            attack = "NONE"
            evidence.append(
                f"all indicators within calibrated tolerance "
                f"(score {score:.4f} < warning {self.warning_threshold:.4f})"
            )

        if decision != "LEGITIMATE":
            evidence.append(
                f"anomaly_score {score:.4f} "
                f"{'>=' if statistical_warn else '<'} "
                f"threshold {self.warning_threshold:.4f}"
            )

        result.decision = decision
        result.detected_attack = attack
        result.evidence = evidence
        return result

    def _classify_statistical(self, result, ind: Dict[str, float]) -> str:
        """Name the most likely attack from telemetry shape alone.

        A deterministic decision list, not a learned classifier. The
        discriminator is *how* the state was damaged:

        - Channel manipulation is decoherence: purity falls along with
          fidelity, because the state became mixed.
        - Forgery/impersonation substitute a different *pure* state:
          fidelity falls while purity stays near 1.
        """
        t = result.telemetry

        # Decoherence is measured as EXCESS mixedness beyond the channel's
        # own noise floor, not as distance from a hypothetical perfect
        # state. Every real channel is slightly lossy, so comparing against
        # 1.0 would label every session -- including legitimate ones -- as
        # channel manipulation.
        base_purity = self.baseline.get("purity_mean", 1.0)
        base_fidelity = self.baseline.get("fidelity_mean", 1.0)
        purity_std = max(self.baseline.get("purity_std", 1e-6), 1e-6)

        excess_purity_loss = base_purity - t.mean_purity
        fidelity_loss = max(0.0, base_fidelity - t.mean_fidelity)

        # Significant only if it clears the baseline's own spread.
        decohered = excess_purity_loss > max(5.0 * purity_std, 0.01)

        # Mixedness beyond the floor is the fingerprint of a noisy channel.
        if decohered and excess_purity_loss >= 0.3 * fidelity_loss:
            return "CHANNEL_MANIPULATION"

        # A substituted eigenstate is still pure: fidelity falls while
        # purity stays at the floor. That is forgery, not decoherence.
        if ind["mismatch"] > 0.0 and not decohered:
            return "FORGERY"

        if fidelity_loss > 0.0 and not decohered:
            return "FORGERY"

        if fidelity_loss > 0.0:
            return "CHANNEL_MANIPULATION"

        return "UNKNOWN"

    # ------------------------------------------------------------------
    # Explanation
    # ------------------------------------------------------------------

    def explain(self, result) -> str:
        """Render a human-readable verification explanation.

        Reports protocol status, per-basis mismatch counts, the physical
        metrics and the final decision -- the operator-facing view, with
        no internal implementation detail.
        """
        lines: List[str] = []
        verdict = "VERIFICATION PASSED" if result.decision == "LEGITIMATE" \
            else "VERIFICATION FAILED"
        lines.append(verdict)
        lines.append("")
        lines.append(f"Message binding   : {'VALID' if result.message_binding_valid else 'INVALID'}")
        lines.append(f"Signer key        : {'AUTHORIZED' if result.key_binding_valid else 'UNRECOGNISED'}")
        lines.append(f"Verifier          : {'AUTHORIZED' if result.authorized else 'UNAUTHORIZED'}")
        lines.append(f"Session freshness : {'FRESH' if result.session_fresh else 'STALE/REPLAYED'}")
        for r in result.freshness_reasons:
            lines.append(f"                    - {r}")
        lines.append("")

        per_basis: Dict[str, int] = {}
        for e in result.elements:
            if not e.match:
                per_basis[e.expected_basis] = per_basis.get(e.expected_basis, 0) + 1
        lines.append(f"Quantum state     : "
                     f"{'MATCH' if result.matches == result.total_elements else 'MISMATCH'} "
                     f"({result.matches}/{result.total_elements} elements)")
        for b in ("x", "y", "z"):
            n = per_basis.get(b, 0)
            if n:
                lines.append(f"  {b.upper()} basis         : {n} mismatch(es)")
        lines.append("")
        lines.append(f"Teleportation fidelity : {result.telemetry.mean_fidelity:.4f}")
        lines.append(f"Trace distance         : {result.telemetry.mean_trace_distance:.4f}")
        lines.append(f"Purity                 : {result.telemetry.mean_purity:.4f}")
        lines.append(f"Measurement entropy    : {result.telemetry.measurement_entropy:.4f}")
        lines.append("")
        lines.append(f"Anomaly score     : {result.anomaly_score:.4f}")
        lines.append(f"Threshold         : {result.threshold:.4f}")
        lines.append(f"Security decision : {result.decision}")
        if result.detected_attack != "NONE":
            lines.append(f"Attack classified : {result.detected_attack}")
        lines.append("")
        lines.append("Evidence:")
        for e in result.evidence:
            lines.append(f"  - {e}")
        return "\n".join(lines)

    def forensics(self, result, attack_id: str = "") -> str:
        """Render a post-incident attack report."""
        lines: List[str] = []
        lines.append(f"Attack ID        : {attack_id or result.session_id[:12].upper()}")
        lines.append(f"Declared attack  : {result.attack_type}")
        lines.append(f"Classified as    : {result.detected_attack}")
        lines.append(f"Intensity        : {result.attack_intensity:.2f}")
        lines.append(f"Session          : {result.session_id}")
        lines.append(f"Signature        : {result.signature_id}")
        lines.append("")

        affected = [e.position for e in result.elements if not e.match]
        lines.append(f"Affected elements: {len(affected)}/{result.total_elements} "
                     f"{affected if affected else ''}")
        lines.append(f"Mean fidelity    : {result.telemetry.mean_fidelity:.4f}")
        lines.append(f"Min fidelity     : {result.telemetry.min_fidelity:.4f}")
        lines.append(f"Trace distance   : {result.telemetry.mean_trace_distance:.4f}")
        lines.append(f"Purity           : {result.telemetry.mean_purity:.4f}")
        lines.append("")
        lines.append(f"Anomaly score    : {result.anomaly_score:.4f}")
        lines.append(f"Threshold        : {result.threshold:.4f}")
        detected = result.decision != "LEGITIMATE"
        lines.append(f"Detection        : {'DETECTED' if detected else 'MISSED'}")
        lines.append("")
        lines.append("Evidence:")
        for e in result.evidence:
            lines.append(f"  - {e}")
        lines.append("")
        lines.append("Timeline:")
        lines.append(result.timeline())
        return "\n".join(lines)


def _clip01(x: float) -> float:
    """Clip to [0, 1]."""
    return float(np.clip(x, 0.0, 1.0))
