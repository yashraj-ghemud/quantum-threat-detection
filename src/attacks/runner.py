"""
attacks/runner.py
=================
Attack simulation runner for QDS attack evaluation.

Phase 5 -- SIH26141 | Blockchain & Cybersecurity.

Generates legitimate baseline/session data using Phase 3 QDS,
applies one attack at a time, sends attacked measurements through
Phase 4 detector, and records structured results.

The runner:
- Keeps legitimate baseline data unchanged
- Generates fresh legitimate sessions for each attack test
- Feeds attacked statevectors into the QDS verification pipeline
- Passes verification results through the ThreatDetector
- Collects all results in a structured format

No AI/ML is used.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from attacks.base import AttackResult, BaseAttack, SessionMetadata
from attacks.replay import ReplayAttack, check_replay
from attacks.unauthorized_verification import (
    UnauthorizedVerificationAttack,
    check_authorization,
)
from qds.signature import QDSSignature, generate_signature
from qds.verification import verify_signature
from security.detector import DetectionResult, ThreatDetector
from utils.logger import get_logger
from utils.reproducibility import get_rng

logger = get_logger(__name__)

__all__: list[str] = [
    "AttackScenarioResult",
    "AttackRunner",
]


# ---------------------------------------------------------------------------
# Scenario result
# ---------------------------------------------------------------------------

@dataclass
class AttackScenarioResult:
    """Structured result for one attack scenario evaluation.

    Attributes
    ----------
    attack_type : str
        Name of the attack (e.g. 'FORGERY', 'LEGITIMATE').
    intensity : float
        Attack intensity used.
    sample_count : int
        Number of signature elements in the session.
    mismatch_rate : float
        Observed mismatch rate from verification.
    anomaly_score : float
        Anomaly score from the Phase 4 detector.
    classification : str
        NORMAL / SUSPICIOUS / THREAT from the detector.
    detection_status : str
        DETECTED / MISSED / NOT_APPLICABLE.
    reason : str
        Human-readable explanation of why the attack was/wasn't detected.
    verification_score : float
        QDS verification score.
    authorization_status : str
        AUTHORIZED / UNAUTHORIZED.
    replay_detected : bool
        Whether replay was detected.
    evidence : list[str]
        Evidence from the attack result.
    detection_result : DetectionResult or None
        Full detection result from Phase 4.
    """

    attack_type: str = ""
    intensity: float = 0.0
    sample_count: int = 0
    mismatch_rate: float = 0.0
    anomaly_score: float = 0.0
    classification: str = "NORMAL"
    detection_status: str = "NOT_APPLICABLE"
    reason: str = ""
    verification_score: float = 1.0
    authorization_status: str = "AUTHORIZED"
    replay_detected: bool = False
    evidence: List[str] = field(default_factory=list)
    detection_result: Optional[DetectionResult] = None


# ---------------------------------------------------------------------------
# Attack Runner
# ---------------------------------------------------------------------------

class AttackRunner:
    """Execute attack scenarios against the QDS + detector pipeline.

    Parameters
    ----------
    sig_length : int
        Number of elements per QDS signature.
    n_baseline : int
        Number of legitimate sessions for detector calibration.
    seed : int
        Base random seed for reproducibility.
    warn_percentile : float
        Percentile for warning threshold calibration.
    crit_percentile : float
        Percentile for critical threshold calibration.
    """

    def __init__(
        self,
        sig_length: int = 32,
        n_baseline: int = 12,
        seed: int = 42,
        warn_percentile: float = 75.0,
        crit_percentile: float = 95.0,
    ) -> None:
        self._sig_length = sig_length
        self._n_baseline = n_baseline
        self._seed = seed
        self._detector: Optional[ThreatDetector] = None
        self._baseline_built = False
        self._warn_pct = warn_percentile
        self._crit_pct = crit_percentile

    def _build_detector(self) -> ThreatDetector:
        """Build and calibrate the Phase 4 ThreatDetector from baseline."""
        detector = ThreatDetector(
            calibration_method="percentile",
            warn_percentile=self._warn_pct,
            crit_percentile=self._crit_pct,
        )

        # Generate legitimate baseline sessions
        for i in range(self._n_baseline):
            sig = generate_signature(
                f"baseline_{i}",
                length=self._sig_length,
                seed=self._seed + i,
            )
            vr = verify_signature(sig)
            detector.add_baseline_session(vr)

        detector.calibrate()
        return detector

    @property
    def detector(self) -> ThreatDetector:
        """Lazily build and return the calibrated detector."""
        if self._detector is None:
            self._detector = self._build_detector()
        return self._detector

    def _generate_legitimate_session(
        self,
        seed_offset: int = 0,
        message_id: str = "test_msg",
    ) -> tuple:
        """Generate a legitimate QDS signature and session metadata.

        Returns
        -------
        tuple of (QDSSignature, list[np.ndarray], SessionMetadata)
        """
        sig = generate_signature(
            message_id,
            length=self._sig_length,
            seed=self._seed + 500 + seed_offset,
        )
        statevectors = [e.statevector.copy() for e in sig.elements]
        metadata = SessionMetadata(
            message_id=message_id,
            sequence_number=seed_offset + 1,
            signer_id="signer_alice",
            verifier_id="verifier_bob",
            authorized=True,
        )
        return sig, statevectors, metadata

    def run_legitimate(
        self,
        seed_offset: int = 0,
    ) -> AttackScenarioResult:
        """Run a legitimate session (no attack) as baseline comparison.

        Returns
        -------
        AttackScenarioResult
        """
        sig, statevectors, metadata = self._generate_legitimate_session(seed_offset)
        vr = verify_signature(sig)
        dr = self.detector.detect(vr, session_id=f"legitimate_{seed_offset}")

        return AttackScenarioResult(
            attack_type="LEGITIMATE",
            intensity=0.0,
            sample_count=sig.length,
            mismatch_rate=dr.mismatch_rate,
            anomaly_score=dr.anomaly_score,
            classification=dr.classification,
            detection_status="NOT_APPLICABLE",
            reason="legitimate baseline session — no attack applied",
            verification_score=vr.verification_score,
            authorization_status="AUTHORIZED",
            replay_detected=False,
            evidence=[],
            detection_result=dr,
        )

    def run_attack(
        self,
        attack: BaseAttack,
        attack_type: str,
        intensity: float = 1.0,
        seed_offset: int = 100,
    ) -> AttackScenarioResult:
        """Run a single attack scenario and evaluate with Phase 4 detector.

        Parameters
        ----------
        attack : BaseAttack
            Attack instance to execute.
        attack_type : str
            Label for the attack type (e.g. 'FORGERY').
        intensity : float
            Attack intensity in [0, 1].
        seed_offset : int
            Offset for seed to generate a unique legitimate session.

        Returns
        -------
        AttackScenarioResult
        """
        sig, statevectors, metadata = self._generate_legitimate_session(
            seed_offset, message_id=f"msg_{attack_type.lower()}"
        )

        # Execute the attack
        attack_result: AttackResult = attack.execute(
            statevectors=statevectors,
            metadata=metadata,
            intensity=intensity,
        )

        # --- Authorization check (classical layer) ---
        # This runs *alongside* the quantum-statistical detector, not
        # instead of it.  An earlier revision returned here immediately with
        # anomaly_score=0.0, which is why this attack category reported a
        # score of exactly 0.0000 in every results file while every other
        # category was scored statistically.  The unauthorized party has to
        # measure the states to read them, and that collapse is a real,
        # measurable perturbation -- so we now fall through to full
        # verification and detection, and merge the authorization verdict in
        # at the end.
        auth_failed = False
        auth_reason = ""
        if isinstance(attack, UnauthorizedVerificationAttack) and intensity > 0:
            auth_check = check_authorization(
                verifier_id=attack_result.metadata.verifier_id,
                metadata=attack_result.metadata,
            )
            auth_failed = not auth_check.is_authorized
            auth_reason = auth_check.reason

        # --- Replay check ---
        replay_detected = False
        if isinstance(attack, ReplayAttack) and intensity > 0:
            # Create expected new-session metadata
            _, _, expected_meta = self._generate_legitimate_session(
                seed_offset, message_id=f"msg_{attack_type.lower()}"
            )
            replay_check = check_replay(
                received=attack_result.metadata,
                expected=expected_meta,
                max_staleness_seconds=60.0,
            )
            replay_detected = replay_check.is_replay
            if replay_detected:
                attack_result.evidence.extend(replay_check.reasons)

        # --- QDS Verification with attacked statevectors ---
        vr = verify_signature(
            sig,
            received_statevectors=attack_result.statevectors,
        )

        # --- Phase 4 detection ---
        session_id = f"{attack_type}_{intensity:.2f}_{seed_offset}"
        dr = self.detector.detect(vr, session_id=session_id)

        # --- Determine detection status ---
        detected = False
        reasons: list[str] = []

        # Statistical detection
        if dr.classification in ("SUSPICIOUS", "THREAT"):
            detected = True
            reasons.append(
                f"measurement_distribution_deviation: "
                f"classification={dr.classification} "
                f"anomaly_score={dr.anomaly_score:.4f}"
            )

        # Replay detection
        if replay_detected:
            detected = True
            reasons.append("replay_session_mismatch: replay consistency check failed")

        # Classical authorization detection (defence in depth)
        if auth_failed:
            detected = True
            reasons.append(f"authorization_failure: {auth_reason}")

        # Build reason string
        if detected:
            detection_status = "DETECTED"
            reason = " | ".join(reasons)
        else:
            detection_status = "MISSED"
            reason = (
                f"attack not detected: classification={dr.classification} "
                f"anomaly_score={dr.anomaly_score:.4f}"
            )

        return AttackScenarioResult(
            attack_type=attack_type,
            intensity=intensity,
            sample_count=sig.length,
            mismatch_rate=dr.mismatch_rate,
            anomaly_score=dr.anomaly_score,
            classification=dr.classification,
            detection_status=detection_status,
            reason=reason,
            verification_score=vr.verification_score,
            authorization_status=(
                "UNAUTHORIZED" if auth_failed
                else attack_result.authorization_status
            ),
            replay_detected=replay_detected,
            evidence=attack_result.evidence,
            detection_result=dr,
        )
