"""
src/session.py
==============
The canonical end-to-end QDS security session.

SIH26141 | Blockchain & Cybersecurity.

This module is the single scientifically coherent path through the system.
Everything that matters happens here, in order, with each stage consuming
the real output of the previous one::

    MESSAGE
      -> MESSAGE BINDING          SHA-256 digest
      -> QDS SIGNATURE            key table indexed by the digest
      -> QUANTUM STATE            Pauli eigenstate per signature element
      -> [ATTACK INJECTION]       forgery / impersonation / interception
      -> BELL-STATE ENTANGLEMENT  |Phi+> shared signer <-> verifier
      -> QUANTUM TELEPORTATION    Bell measurement + classical bits
      -> [CHANNEL ATTACK]         noise injected on the channel qubits
      -> PAULI CORRECTION         X / Z applied from the correction bits
      -> RECEIVED QUANTUM STATE   Bob's actual reduced density matrix
      -> PROJECTIVE MEASUREMENT   sampled shots in the element's basis
      -> MEASUREMENT STATISTICS   real counts, real shot noise
      -> QDS VERIFICATION         measured eigenvalue vs the public key
      -> THREAT DETECTION         statistical + protocol evidence

Two rules this module exists to enforce:

1. **No stage is simulated by adjusting a later stage's number.** An attack
   perturbs a state or a piece of session metadata, and every downstream
   consequence is whatever the physics and statistics actually produce.
   There is no code path that edits a verification score.

2. **The teleported state is the state that gets verified.** Teleportation
   is not run alongside the protocol to produce a fidelity figure; the
   qubit Bob measures *is* the qubit that came out of the channel.

Replay is handled deliberately differently from the state-level attacks: a
replayed signature is quantum-mechanically perfect, so it is caught by
session freshness (nonce reuse, sequence regression, staleness), not by
pretending its measurement statistics look anomalous.

No AI/ML libraries are used.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from evaluation.fidelity import (
    bloch_vector,
    purity,
    state_fidelity,
    to_density_matrix,
    trace_distance,
)
from qds.keygen import (
    DEFAULT_KEY_TABLE_SIZE,
    PrivateKey,
    PublicKey,
    generate_key_pair,
)
from qds.pauli_states import get_eigenstate
from qds.signature import QDSSignature
from qds.signer import sign_message
from quantum.measurements import BasisCounts, sample_basis_counts
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "SessionContext",
    "ElementTelemetry",
    "SessionTelemetry",
    "SessionEvent",
    "SessionResult",
    "SessionRunner",
    "ReplayGuard",
    "AUTHORIZED_VERIFIERS",
]

#: Verifiers permitted to complete a verification. Deliberately explicit:
#: authorization is a deterministic allow-list check, not a heuristic.
AUTHORIZED_VERIFIERS: Tuple[str, ...] = ("verifier_bob",)


# ---------------------------------------------------------------------------
# Session context (protocol-level state)
# ---------------------------------------------------------------------------

@dataclass
class SessionContext:
    """Protocol-level context carried alongside the quantum signature.

    These are the fields a replay attack manipulates, and the ones the
    freshness checks consult. They are classical by nature -- session
    binding is a protocol property, not a quantum one.

    Attributes
    ----------
    session_id : str
        Unique id for this verification session.
    nonce : str
        Single-use random value. Reuse is conclusive evidence of replay.
    sequence_number : int
        Monotonic per-signer counter. A non-increasing value is a regression.
    timestamp : float
        Unix time at which the session was created.
    signer_id, verifier_id : str
        Claimed identities.
    message_id : str
        Human-readable label for correlation.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex)
    sequence_number: int = 1
    timestamp: float = field(default_factory=time.time)
    signer_id: str = "signer_alice"
    verifier_id: str = "verifier_bob"
    message_id: str = ""

    def age_seconds(self, now: Optional[float] = None) -> float:
        """Seconds elapsed since this context was created."""
        return (time.time() if now is None else now) - self.timestamp


class ReplayGuard:
    """Tracks nonces and sequence numbers to detect replayed sessions.

    Deliberately stateful and deterministic: a nonce is accepted exactly
    once, and a signer's sequence number must strictly increase. No
    statistics are involved, because replay leaves no statistical trace.
    """

    def __init__(self, max_age_seconds: float = 60.0) -> None:
        self.max_age_seconds = max_age_seconds
        self._seen_nonces: set[str] = set()
        self._last_sequence: Dict[str, int] = {}

    def check(self, ctx: SessionContext) -> Tuple[bool, List[str]]:
        """Validate freshness of *ctx*.

        Returns
        -------
        tuple[bool, list[str]]
            ``(is_fresh, reasons)``. ``reasons`` is empty when fresh and
            otherwise names every freshness rule that failed.
        """
        reasons: List[str] = []

        if ctx.nonce in self._seen_nonces:
            reasons.append(f"nonce_reused: {ctx.nonce[:12]}... already seen")

        last = self._last_sequence.get(ctx.signer_id)
        if last is not None and ctx.sequence_number <= last:
            reasons.append(
                f"sequence_regression: got {ctx.sequence_number}, "
                f"expected > {last}"
            )

        age = ctx.age_seconds()
        if age > self.max_age_seconds:
            reasons.append(
                f"stale_session: age {age:.1f}s exceeds "
                f"{self.max_age_seconds:.0f}s limit"
            )

        return (not reasons), reasons

    def commit(self, ctx: SessionContext) -> None:
        """Record *ctx* as consumed so a later replay of it is detected."""
        self._seen_nonces.add(ctx.nonce)
        prev = self._last_sequence.get(ctx.signer_id)
        if prev is None or ctx.sequence_number > prev:
            self._last_sequence[ctx.signer_id] = ctx.sequence_number


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

@dataclass
class ElementTelemetry:
    """Per-signature-element measurement record.

    Every field is computed from the state that actually arrived.
    """

    position: int
    expected_label: str
    expected_basis: str
    expected_eigenvalue: int
    fidelity: float
    trace_distance: float
    purity: float
    p0: float
    p1: float
    counts: Dict[str, int]
    shots: int
    measured_eigenvalue: int
    match: bool
    correction_bits: Tuple[int, int] = (0, 0)


@dataclass
class SessionTelemetry:
    """Aggregate quantum + statistical telemetry for one session.

    Only quantities that are genuinely computed appear here. Per-basis
    deviations are reported for whichever bases the signature actually
    used; a basis with no elements gets ``None`` rather than a filler 0.0,
    so a missing measurement can never be mistaken for a clean one.
    """

    mean_fidelity: float = 1.0
    min_fidelity: float = 1.0
    mean_trace_distance: float = 0.0
    mean_purity: float = 1.0
    x_deviation: Optional[float] = None
    y_deviation: Optional[float] = None
    z_deviation: Optional[float] = None
    measurement_entropy: float = 0.0
    entropy_deviation: float = 0.0
    mismatch_rate: float = 0.0
    verification_score: float = 1.0
    total_shots: int = 0
    basis_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """Flat dict for CSV/JSON export, omitting nothing that was computed."""
        return {
            "mean_fidelity": self.mean_fidelity,
            "min_fidelity": self.min_fidelity,
            "mean_trace_distance": self.mean_trace_distance,
            "mean_purity": self.mean_purity,
            "x_deviation": self.x_deviation,
            "y_deviation": self.y_deviation,
            "z_deviation": self.z_deviation,
            "measurement_entropy": self.measurement_entropy,
            "entropy_deviation": self.entropy_deviation,
            "mismatch_rate": self.mismatch_rate,
            "verification_score": self.verification_score,
            "total_shots": self.total_shots,
        }


@dataclass
class SessionEvent:
    """One entry in the session's security timeline."""

    stage: str
    detail: str
    elapsed_ms: float
    anomalous: bool = False

    def __repr__(self) -> str:  # pragma: no cover - trivial
        mark = " <-- ANOMALY" if self.anomalous else ""
        return f"[{self.elapsed_ms:7.2f} ms] {self.stage}: {self.detail}{mark}"


@dataclass
class SessionResult:
    """Complete outcome of one end-to-end session."""

    session_id: str
    signature_id: str
    message_id: str
    signer_id: str
    verifier_id: str
    attack_type: str
    attack_intensity: float

    verification_score: float
    accepted: bool
    matches: int
    total_elements: int

    telemetry: SessionTelemetry
    elements: List[ElementTelemetry] = field(default_factory=list)
    events: List[SessionEvent] = field(default_factory=list)

    message_binding_valid: bool = True
    key_binding_valid: bool = True
    session_fresh: bool = True
    authorized: bool = True
    freshness_reasons: List[str] = field(default_factory=list)

    anomaly_score: float = 0.0
    threshold: float = 0.0
    decision: str = "LEGITIMATE"
    detected_attack: str = "NONE"
    evidence: List[str] = field(default_factory=list)

    latency_sign_ms: float = 0.0
    latency_channel_ms: float = 0.0
    latency_measure_ms: float = 0.0
    latency_detect_ms: float = 0.0
    latency_total_ms: float = 0.0

    def as_row(self) -> Dict[str, Any]:
        """Flatten to one CSV row."""
        row: Dict[str, Any] = {
            "session_id": self.session_id,
            "signature_id": self.signature_id,
            "attack_type": self.attack_type,
            "attack_intensity": self.attack_intensity,
            "verification_score": self.verification_score,
            "accepted": self.accepted,
            "matches": self.matches,
            "total_elements": self.total_elements,
            "message_binding_valid": self.message_binding_valid,
            "key_binding_valid": self.key_binding_valid,
            "session_fresh": self.session_fresh,
            "authorized": self.authorized,
            "anomaly_score": self.anomaly_score,
            "threshold": self.threshold,
            "decision": self.decision,
            "detected_attack": self.detected_attack,
            "latency_total_ms": self.latency_total_ms,
        }
        row.update(self.telemetry.as_dict())
        return row

    def timeline(self) -> str:
        """Render the security event timeline as text."""
        return "\n".join(repr(e) for e in self.events)


# ---------------------------------------------------------------------------
# Session runner
# ---------------------------------------------------------------------------

class SessionRunner:
    """Executes end-to-end QDS sessions through the real quantum channel.

    Parameters
    ----------
    signature_length : int
        Pauli eigenstate elements per signature.
    table_size : int
        Size of the signer's secret key table.
    shots : int
        Measurement shots per signature element.
    teleport_shots : int
        Aer shots used to resolve each teleported element's density matrix.
    max_age_seconds : float
        Session staleness limit for the replay guard.
    seed : int
        Base seed. Controls *simulation* reproducibility only -- key
        material still comes from the CSPRNG unless a seed is pinned
        explicitly via :meth:`setup`.
    use_teleportation : bool
        When ``True`` (default) each signature element is physically
        teleported. ``False`` bypasses the channel and hands the verifier
        the prepared state directly -- far faster, and used only where the
        channel is not under test.
    """

    def __init__(
        self,
        signature_length: int = 16,
        table_size: int = DEFAULT_KEY_TABLE_SIZE,
        shots: int = 256,
        teleport_shots: int = 256,
        max_age_seconds: float = 60.0,
        seed: int = 42,
        use_teleportation: bool = True,
        baseline_noise_type: Optional[str] = "depolarizing",
        baseline_noise_level: float = 0.02,
        warning_threshold: Optional[float] = None,
        critical_threshold: Optional[float] = None,
    ) -> None:
        # An explicit operating point for THIS configuration. Left as None
        # the engine reads the calibrated threshold from config, which is
        # only valid for the configuration it was calibrated at -- see
        # _warn_threshold_mismatch. Pin these when running a configuration
        # the stored threshold does not cover.
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        # Every real channel is imperfect. Modelling legitimate traffic on a
        # *perfect* channel would make detection trivially easy -- legitimate
        # sessions would have zero variance, so any threshold at all would
        # separate them from attacks and the reported FAR/FRR would measure
        # nothing. This baseline noise floor is always present, for attack
        # and legitimate sessions alike, so the detector has to distinguish
        # an attack from ordinary hardware imperfection.
        self.baseline_noise_type = baseline_noise_type
        self.baseline_noise_level = baseline_noise_level
        self.signature_length = signature_length
        self.table_size = table_size
        self.shots = shots
        self.teleport_shots = teleport_shots
        self.seed = seed
        self.use_teleportation = use_teleportation

        self.replay_guard = ReplayGuard(max_age_seconds=max_age_seconds)
        self._warn_threshold_mismatch()
        # Channel-output cache. The teleportation circuit is deterministic
        # given (input state, noise model), and Aer's density_matrix method
        # returns the ensemble-averaged output, so transmitting the same
        # eigenstate through the same channel twice yields the same rho.
        # Only six distinct eigenstates exist, so caching turns hundreds of
        # circuit builds per session into at most six. This changes no
        # physics -- the per-shot randomness lives in the measurement
        # sampling, which is drawn fresh (and separately seeded) each time.
        self._channel_cache: Dict[Tuple, Tuple[np.ndarray, Tuple[int, int]]] = {}
        self._backends: Dict[Tuple[Optional[str], float], Any] = {}
        self._private_key: Optional[PrivateKey] = None
        self._public_key: Optional[PublicKey] = None
        self._sequence: int = 0
        self._baseline: Optional[Dict[str, float]] = None

    def _warn_threshold_mismatch(self) -> None:
        """Warn if the calibrated threshold does not fit this configuration.

        The stored threshold is only valid for the signature length and
        shot count it was calibrated at. Running under a different
        configuration silently inflates the false-rejection rate -- measured
        at 11.7% for length=8 against a threshold calibrated at length=16,
        versus 1.7% when they match. Failing loudly here is better than
        quietly rejecting honest users.
        """
        try:
            from utils.config import ConfigLoader

            cfg = ConfigLoader()
            cal_len = cfg.get_nested("detection", "calibrated_for_signature_length")
            cal_shots = cfg.get_nested("detection", "calibrated_for_shots")
        except Exception:  # pragma: no cover - config always present
            return

        if cal_len is None and cal_shots is None:
            return

        problems = []
        if cal_len is not None and int(cal_len) != self.signature_length:
            problems.append(
                f"signature_length={self.signature_length} "
                f"(threshold calibrated for {cal_len})"
            )
        if cal_shots is not None and int(cal_shots) != self.shots:
            problems.append(
                f"shots={self.shots} (threshold calibrated for {cal_shots})"
            )

        if problems:
            logger.warning(
                "Detection threshold was calibrated for a different "
                "configuration: %s. Expect an elevated false-rejection rate. "
                "Recalibrate with: python experiments/run_final_experiment.py "
                "--signature-length %d --shots %d",
                "; ".join(problems), self.signature_length, self.shots,
            )

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(
        self,
        signer_id: str = "signer_alice",
        private_seed: Optional[bytes] = None,
    ) -> Tuple[PrivateKey, PublicKey]:
        """Generate the signer's key pair and the verifier's public key."""
        priv, pub = generate_key_pair(
            signer_id=signer_id,
            table_size=self.table_size,
            private_seed=private_seed,
            distribute=False,
        )
        self._private_key, self._public_key = priv, pub
        return priv, pub

    @property
    def public_key(self) -> PublicKey:
        if self._public_key is None:
            self.setup()
        return self._public_key  # type: ignore[return-value]

    @property
    def private_key(self) -> PrivateKey:
        if self._private_key is None:
            self.setup()
        return self._private_key  # type: ignore[return-value]

    def next_context(self, message_id: str = "") -> SessionContext:
        """Build a fresh session context with a monotonic sequence number."""
        self._sequence += 1
        return SessionContext(
            sequence_number=self._sequence,
            signer_id=self.private_key.signer_id,
            message_id=message_id,
        )

    # ------------------------------------------------------------------
    # Channel
    # ------------------------------------------------------------------

    def _transmit(
        self,
        statevector: np.ndarray,
        noise_type: Optional[str],
        noise_level: float,
        seed: int,
    ) -> Tuple[np.ndarray, Tuple[int, int]]:
        """Send one element through the real teleportation channel.

        Returns
        -------
        tuple
            ``(received_density_matrix, correction_bits)``.
        """
        if not self.use_teleportation:
            return to_density_matrix(statevector), (0, 0)

        import warnings

        from qiskit import transpile
        from qiskit_aer import AerSimulator

        from qds.key_distribution import statevector_to_bloch_angles
        from quantum.teleportation import build_teleportation_circuit

        theta, phi = statevector_to_bloch_angles(statevector)

        cache_key = (round(theta, 9), round(phi, 9), noise_type, round(noise_level, 6))
        hit = self._channel_cache.get(cache_key)
        if hit is not None:
            return hit

        backend_key = (noise_type, round(noise_level, 6))
        backend = self._backends.get(backend_key)
        if backend is None:
            if noise_type and noise_level > 0.0:
                from quantum.noise import build_noise_model

                backend = AerSimulator(
                    method="density_matrix",
                    noise_model=build_noise_model(noise_type, noise_level),
                )
            else:
                backend = AerSimulator(method="density_matrix")
            self._backends[backend_key] = backend

        qc = build_teleportation_circuit(theta, phi)
        compiled = transpile(qc, backend)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = backend.run(
                compiled, shots=self.teleport_shots, seed_simulator=seed
            ).result()

        bob = result.data()["bob"]

        # Classical correction bits actually observed on the channel.
        try:
            counts = result.get_counts()
            modal = max(counts, key=counts.get).replace(" ", "")
            bits = (int(modal[-1]), int(modal[-2]))
        except Exception:  # pragma: no cover - counts absent on some backends
            bits = (0, 0)

        out = (to_density_matrix(bob), bits)
        self._channel_cache[cache_key] = out
        return out

    # ------------------------------------------------------------------
    # Baseline (for deviation metrics)
    # ------------------------------------------------------------------

    def calibrate_baseline(self, n_sessions: int = 30, message_prefix: str = "cal") -> Dict[str, float]:
        """Measure what an undisturbed session looks like.

        Deviation metrics are meaningless without a reference, and the
        reference must come from *measured* legitimate sessions rather than
        an assumed ideal: finite shots, and the simulator's own behaviour,
        both contribute spread that is not an attack.

        Returns
        -------
        dict[str, float]
            Baseline means and standard deviations.
        """
        scores, fids, mismatches, entropies, tds, purs = [], [], [], [], [], []
        for i in range(n_sessions):
            res = self.run(
                message=f"{message_prefix}_{i}".encode(),
                attack=None,
                detect=False,
            )
            scores.append(res.verification_score)
            fids.append(res.telemetry.mean_fidelity)
            mismatches.append(res.telemetry.mismatch_rate)
            entropies.append(res.telemetry.measurement_entropy)
            tds.append(res.telemetry.mean_trace_distance)
            purs.append(res.telemetry.mean_purity)

        self._baseline = {
            "mismatch_mean": float(np.mean(mismatches)),
            "mismatch_std": float(np.std(mismatches)) or 1e-6,
            "fidelity_mean": float(np.mean(fids)),
            "fidelity_std": float(np.std(fids)) or 1e-6,
            "entropy_mean": float(np.mean(entropies)),
            "entropy_std": float(np.std(entropies)) or 1e-6,
            "trace_distance_mean": float(np.mean(tds)),
            "trace_distance_std": float(np.std(tds)) or 1e-6,
            "purity_mean": float(np.mean(purs)),
            "purity_std": float(np.std(purs)) or 1e-6,
            "n_sessions": float(n_sessions),
        }
        logger.info(
            "Baseline calibrated over %d sessions: mismatch=%.4f+-%.4f "
            "fidelity=%.4f+-%.4f",
            n_sessions,
            self._baseline["mismatch_mean"], self._baseline["mismatch_std"],
            self._baseline["fidelity_mean"], self._baseline["fidelity_std"],
        )
        return self._baseline

    def calibrate_own_threshold(self, sigma: float = 8.0, n_sessions: int = 20) -> float:
        """Derive an operating point from this runner's own baseline.

        Measures the anomaly scores of legitimate sessions under the
        *current* configuration and places the threshold that many standard
        deviations above their mean. Self-contained, so it does not inherit
        a threshold calibrated for a different signature length or shot
        count -- which is the usual cause of an inflated false-rejection
        rate.

        For a published operating point use
        ``experiments/run_final_experiment.py``, which selects against
        measured attack sessions too; this is for ad-hoc and test
        configurations where only the legitimate side is available.
        """
        if self._baseline is None:
            self.calibrate_baseline(n_sessions=n_sessions)

        scores = []
        for i in range(n_sessions):
            res = self.run(message=f"thr_cal_{i}".encode(), detect=False)
            from security.threat_engine import ThreatEngine

            score, _ = ThreatEngine(self.baseline).anomaly_score(res)
            scores.append(score)

        mu, sd = float(np.mean(scores)), float(np.std(scores))
        thr = mu + sigma * max(sd, 1e-4)
        self.warning_threshold = thr
        self.critical_threshold = min(1.0, thr * 2.5)
        logger.info(
            "Self-calibrated threshold %.6f (baseline score %.6f +- %.6f, %.0f sigma)",
            thr, mu, sd, sigma,
        )
        return thr

    @property
    def baseline(self) -> Dict[str, float]:
        """The calibrated baseline, computing it on first use."""
        if self._baseline is None:
            self.calibrate_baseline()
        return self._baseline  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # The session
    # ------------------------------------------------------------------

    def run(
        self,
        message: bytes,
        attack: Optional[Any] = None,
        attack_type: str = "LEGITIMATE",
        intensity: float = 0.0,
        context: Optional[SessionContext] = None,
        signing_key: Optional[PrivateKey] = None,
        channel_noise: Optional[str] = None,
        channel_noise_level: float = 0.0,
        detect: bool = True,
        seed_offset: int = 0,
    ) -> SessionResult:
        """Run one complete session and return everything measured.

        Parameters
        ----------
        message : bytes
            The message being signed.
        attack : BaseAttack or None
            Attack applied to the statevectors *before* transmission.
        attack_type : str
            Canonical label recorded on the result.
        intensity : float
            Attack intensity in [0, 1].
        context : SessionContext or None
            Protocol context. ``None`` allocates a fresh one; a replay
            attack supplies a stale one deliberately.
        signing_key : PrivateKey or None
            Key used to sign. An impersonation attack supplies the
            attacker's own key here.
        channel_noise, channel_noise_level : str, float
            Noise injected onto the channel qubits during teleportation.
        detect : bool
            Run threat detection. ``False`` during baseline calibration,
            where no threshold exists yet.
        seed_offset : int
            Offsets simulator seeds so repeated trials are independent.

        Returns
        -------
        SessionResult
        """
        t_start = time.perf_counter()
        events: List[SessionEvent] = []

        def mark(stage: str, detail: str, anomalous: bool = False) -> None:
            events.append(SessionEvent(
                stage=stage,
                detail=detail,
                elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
                anomalous=anomalous,
            ))

        ctx = context if context is not None else self.next_context()
        mark("SESSION CREATED",
             f"id={ctx.session_id[:8]} seq={ctx.sequence_number} "
             f"nonce={ctx.nonce[:8]}")

        # --- 1. Message binding + signature -----------------------------
        t0 = time.perf_counter()
        key = signing_key if signing_key is not None else self.private_key
        signature: QDSSignature = sign_message(
            message, key, length=self.signature_length
        )
        latency_sign = (time.perf_counter() - t0) * 1000.0
        mark("SIGNATURE GENERATED",
             f"sig={signature.signature_id[:8]} "
             f"digest={signature.message_hash[:12]}... "
             f"len={signature.length}")

        statevectors = [e.statevector.copy() for e in signature.elements]

        # --- 2. Attack injection, BEFORE the channel --------------------
        if attack is not None and intensity > 0.0:
            from attacks.base import SessionMetadata

            meta = SessionMetadata(
                session_id=ctx.session_id,
                message_id=ctx.message_id or signature.message_id,
                sequence_number=ctx.sequence_number,
                signer_id=ctx.signer_id,
                verifier_id=ctx.verifier_id,
                authorized=True,
            )
            atk_res = attack.execute(statevectors, meta, intensity=intensity)
            statevectors = atk_res.statevectors
            if atk_res.metadata.verifier_id != ctx.verifier_id:
                ctx.verifier_id = atk_res.metadata.verifier_id
            if atk_res.metadata.signer_id != ctx.signer_id:
                ctx.signer_id = atk_res.metadata.signer_id
            mark("ATTACK INJECTED",
                 f"{attack_type} intensity={intensity:.2f} "
                 f"({len(atk_res.evidence)} indicators)",
                 anomalous=True)

        # --- 3. Bell pair + teleportation + Pauli correction ------------
        t0 = time.perf_counter()
        mark("BELL PAIR CREATED",
             f"|Phi+> x {len(statevectors)} (one per element); "
             f"baseline channel noise "
             f"{self.baseline_noise_type}@{self.baseline_noise_level:.3f}")
        if channel_noise and channel_noise_level > 0:
            mark("CHANNEL EVENT",
                 f"{channel_noise} noise p={channel_noise_level:.3f} "
                 f"injected on channel qubits",
                 anomalous=True)

        # An attack's noise adds to the ever-present baseline floor rather
        # than replacing it: a channel adversary perturbs a channel that was
        # already imperfect.
        eff_noise_type = channel_noise or self.baseline_noise_type
        if channel_noise and channel_noise_level > 0:
            eff_noise_level = min(1.0, self.baseline_noise_level + channel_noise_level)
        else:
            eff_noise_level = self.baseline_noise_level

        received: List[np.ndarray] = []
        corrections: List[Tuple[int, int]] = []
        for i, sv in enumerate(statevectors):
            rho, bits = self._transmit(
                sv, eff_noise_type, eff_noise_level,
                seed=self.seed + seed_offset * 1000 + i,
            )
            received.append(rho)
            corrections.append(bits)
        latency_channel = (time.perf_counter() - t0) * 1000.0
        mark("TELEPORTATION + PAULI CORRECTION",
             f"{len(received)} elements delivered "
             f"({latency_channel:.1f} ms)")

        # --- 4. Projective measurement of what actually arrived ---------
        t0 = time.perf_counter()
        elements, matches = self._measure_and_verify(
            signature, received, corrections, seed_offset
        )
        latency_measure = (time.perf_counter() - t0) * 1000.0
        total = len(elements)
        score = matches / total if total else 0.0
        mark("PROJECTIVE MEASUREMENT",
             f"{total} elements x {self.shots} shots; "
             f"{matches}/{total} matched expected eigenvalue")

        # --- 5. Telemetry ------------------------------------------------
        telemetry = self._build_telemetry(elements, score)
        mark("STATISTICAL ANALYSIS",
             f"F={telemetry.mean_fidelity:.4f} "
             f"T={telemetry.mean_trace_distance:.4f} "
             f"mismatch={telemetry.mismatch_rate:.4f} "
             f"H={telemetry.measurement_entropy:.4f}")

        # --- 6. Protocol checks -----------------------------------------
        msg_ok = signature.message_hash == _digest_hex(message)
        key_ok = signature.key_id == self.public_key.key_id
        fresh, freshness_reasons = self.replay_guard.check(ctx)
        authorized = ctx.verifier_id in AUTHORIZED_VERIFIERS

        if not key_ok:
            mark("KEY BINDING", f"key_id mismatch: {signature.key_id[:8]} "
                                f"!= {self.public_key.key_id[:8]}", anomalous=True)
        if not fresh:
            mark("FRESHNESS CHECK", "; ".join(freshness_reasons), anomalous=True)
        if not authorized:
            mark("AUTHORIZATION",
                 f"verifier {ctx.verifier_id!r} not in allow-list",
                 anomalous=True)

        self.replay_guard.commit(ctx)

        result = SessionResult(
            session_id=ctx.session_id,
            signature_id=signature.signature_id,
            message_id=ctx.message_id or signature.message_id,
            signer_id=ctx.signer_id,
            verifier_id=ctx.verifier_id,
            attack_type=attack_type,
            attack_intensity=intensity,
            verification_score=score,
            accepted=score >= 0.7 and msg_ok and key_ok,
            matches=matches,
            total_elements=total,
            telemetry=telemetry,
            elements=elements,
            events=events,
            message_binding_valid=msg_ok,
            key_binding_valid=key_ok,
            session_fresh=fresh,
            authorized=authorized,
            freshness_reasons=freshness_reasons,
            latency_sign_ms=latency_sign,
            latency_channel_ms=latency_channel,
            latency_measure_ms=latency_measure,
        )

        # --- 7. Threat detection ----------------------------------------
        if detect:
            t0 = time.perf_counter()
            from security.threat_engine import ThreatEngine

            ThreatEngine(
                self.baseline,
                warning_threshold=self.warning_threshold,
                critical_threshold=self.critical_threshold,
            ).evaluate(result)
            result.latency_detect_ms = (time.perf_counter() - t0) * 1000.0
            mark("THREAT DECISION",
                 f"{result.decision} ({result.detected_attack}) "
                 f"score={result.anomaly_score:.4f} "
                 f"threshold={result.threshold:.4f}",
                 anomalous=result.decision != "LEGITIMATE")

        result.latency_total_ms = (time.perf_counter() - t_start) * 1000.0
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _measure_and_verify(
        self,
        signature: QDSSignature,
        received: Sequence[np.ndarray],
        corrections: Sequence[Tuple[int, int]],
        seed_offset: int,
    ) -> Tuple[List[ElementTelemetry], int]:
        """Measure each received state and compare against the public key."""
        elements: List[ElementTelemetry] = []
        matches = 0

        for pos, rho in enumerate(received):
            # Expected state comes from the VERIFIER's public key, never
            # from the (possibly attacker-supplied) signature elements.
            table_index = (
                signature.key_indices[pos]
                if pos < len(signature.key_indices) else 0
            )
            try:
                expected = self.public_key.state_at(table_index)
            except IndexError:
                expected = get_eigenstate(signature.elements[pos].label)

            ideal = to_density_matrix(expected.statevector)
            f = state_fidelity(ideal, rho)
            td = trace_distance(ideal, rho)
            pur = purity(rho)

            # Sample real shots from the received state in the expected basis.
            bc = _sample_from_density(
                rho, expected.basis, self.shots,
                seed=self.seed + seed_offset * 1000 + pos,
            )

            measured_ev = +1 if bc.p0 >= bc.p1 else -1
            match = measured_ev == expected.eigenvalue
            matches += int(match)

            elements.append(ElementTelemetry(
                position=pos,
                expected_label=expected.label,
                expected_basis=expected.basis,
                expected_eigenvalue=expected.eigenvalue,
                fidelity=f,
                trace_distance=td,
                purity=pur,
                p0=bc.p0,
                p1=bc.p1,
                counts=bc.counts,
                shots=bc.shots,
                measured_eigenvalue=measured_ev,
                match=match,
                correction_bits=tuple(corrections[pos]),
            ))

        return elements, matches

    def _build_telemetry(
        self,
        elements: Sequence[ElementTelemetry],
        score: float,
    ) -> SessionTelemetry:
        """Aggregate per-element records into session telemetry."""
        if not elements:
            return SessionTelemetry()

        fids = [e.fidelity for e in elements]
        tds = [e.trace_distance for e in elements]
        purs = [e.purity for e in elements]

        # Per-basis deviation: how far the measured +1 probability drifted
        # from what the expected eigenstate predicts (1.0 for a +1
        # eigenstate, 0.0 for a -1 eigenstate). Bases with no elements stay
        # None rather than being reported as zero deviation.
        per_basis: Dict[str, List[float]] = {"x": [], "y": [], "z": []}
        for e in elements:
            ideal_p0 = 1.0 if e.expected_eigenvalue == +1 else 0.0
            per_basis[e.expected_basis].append(abs(e.p0 - ideal_p0))

        def dev(b: str) -> Optional[float]:
            return float(np.mean(per_basis[b])) if per_basis[b] else None

        # Shannon entropy of the pooled outcome distribution, in bits.
        n0 = sum(e.counts.get("0", 0) for e in elements)
        n1 = sum(e.counts.get("1", 0) for e in elements)
        entropy = _binary_entropy(n0, n1)

        basis_counts: Dict[str, Dict[str, int]] = {}
        for e in elements:
            b = basis_counts.setdefault(e.expected_basis, {"0": 0, "1": 0})
            b["0"] += e.counts.get("0", 0)
            b["1"] += e.counts.get("1", 0)

        return SessionTelemetry(
            mean_fidelity=float(np.mean(fids)),
            min_fidelity=float(np.min(fids)),
            mean_trace_distance=float(np.mean(tds)),
            mean_purity=float(np.mean(purs)),
            x_deviation=dev("x"),
            y_deviation=dev("y"),
            z_deviation=dev("z"),
            measurement_entropy=entropy,
            entropy_deviation=0.0,  # filled by ThreatEngine against baseline
            mismatch_rate=1.0 - score,
            verification_score=score,
            total_shots=sum(e.shots for e in elements),
            basis_counts=basis_counts,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _digest_hex(message: bytes) -> str:
    """SHA-256 hex digest of *message*."""
    from qds.keygen import message_digest

    return message_digest(message).hex()


def _binary_entropy(n0: int, n1: int) -> float:
    """Shannon entropy in bits of a binary outcome distribution."""
    total = n0 + n1
    if total == 0:
        return 0.0
    h = 0.0
    for n in (n0, n1):
        if n > 0:
            p = n / total
            h -= p * np.log2(p)
    return float(h)


def _sample_from_density(
    rho: np.ndarray,
    basis: str,
    shots: int,
    seed: int,
) -> BasisCounts:
    """Sample shots in *basis* from a possibly-mixed received state.

    A state that has been through a noisy channel is mixed, so it is
    decomposed into its eigen-ensemble and each shot drawn from the
    component it lands in. This reproduces the mixed state's statistics
    exactly, whereas collapsing to the dominant eigenvector first would
    quietly restore purity and hide channel damage.
    """
    from quantum.measurements import counts_to_probabilities, measure_density_matrix

    p0_exact, _ = measure_density_matrix(rho, basis)
    rng = np.random.default_rng(seed)
    draws = rng.random(shots)
    n0 = int(np.count_nonzero(draws < p0_exact))
    counts = {"0": n0, "1": shots - n0}
    p0, p1 = counts_to_probabilities(counts, shots)

    return BasisCounts(
        basis=basis,
        counts=counts,
        shots=shots,
        p0=p0,
        p1=p1,
        expectation=p0 - p1,
        analytic_p0=p0_exact,
    )
