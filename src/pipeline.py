"""
src/pipeline.py
===============
End-to-end pipeline for the Quantum-Inspired Cyber Threat Detection Framework.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
import time
import numpy as np

from qds.signature import generate_signature
from qds.verification import verify_signature
from security.detector import ThreatDetector
from attacks.base import BaseAttack, SessionMetadata
from attacks.replay import check_replay
from attacks.unauthorized_verification import check_authorization, UnauthorizedVerificationAttack
from quantum.noise import run_noisy_teleportation

@dataclass
class PipelineResult:
    session_id: str
    signature_length: int
    quantum_state_basis: str
    teleportation_fidelity: float
    measurement_statistics: Dict[str, float]
    verification_score: float
    mismatch_rate: float
    anomaly_score: float
    classification: str
    authorization_status: str
    attack_type: str
    detection_status: str
    decision_reasons: List[str]
    latency: float

class EndToEndPipeline:
    def __init__(self, detector: ThreatDetector, noise_level: float = 0.0):
        self.detector = detector
        self.noise_level = noise_level
        self._rng = np.random.default_rng(42)

    def run_scenario(
        self,
        session_label: str,
        signature_length: int = 16,
        attack: Optional[BaseAttack] = None,
        intensity: float = 1.0,
        seed: int = 42,
        attack_label: Optional[str] = None,
    ) -> PipelineResult:
        """Run one full scenario and return its measured result.

        Parameters
        ----------
        session_label : str
            Identifier for this session.
        signature_length : int
            Number of signature elements.
        attack : BaseAttack or None
            Attack to apply.  ``None`` runs a legitimate session.
        intensity : float
            Attack intensity in [0, 1].
        seed : int
            Seed for signature generation.
        attack_label : str or None
            Canonical attack label recorded on the result (e.g.
            ``'FORGERY'``).  Defaults to ``attack.name``
            (``'ForgeryAttack'``).  Callers that group results by attack
            category should pass this explicitly -- a mismatched label
            silently produces empty groups and zero rates.
        """
        t0 = time.perf_counter()
        reasons = []

        # 1. QDS generation -- a legitimate signature and its true states
        sig = generate_signature(session_label, length=signature_length, seed=seed)
        statevectors = [el.statevector.copy() for el in sig.elements]

        metadata = SessionMetadata(
            session_id=sig.signature_id,
            message_id=session_label
        )

        attack_type = "LEGITIMATE"
        received = statevectors
        effective_noise = self.noise_level

        # 2. Attack simulation -- mutates the REAL statevectors
        if attack:
            attack_type = attack_label if attack_label else attack.name

            attack_res = attack.execute(statevectors, metadata, intensity=intensity)
            received = attack_res.statevectors
            metadata = attack_res.metadata
            reasons.extend(attack_res.evidence)

            # Channel noise applies to THIS scenario only.  Mutating
            # self.noise_level here would leak the attack into every later
            # session and make results depend on scenario ordering.
            if "ChannelManipulation" in attack.name:
                effective_noise = min(1.0, effective_noise + intensity)

        # 3. Channel fidelity, measured on the real teleportation channel
        fidelity_avg = 1.0
        if effective_noise > 0:
            fids = []
            for el in sig.elements:
                res = run_noisy_teleportation(
                    noise_type="depolarizing",
                    p=effective_noise,
                    theta=el.eigenstate.theta,
                    phi=el.eigenstate.phi
                )
                fids.append(res.fidelity)
            fidelity_avg = float(np.mean(fids))

        # 4. QDS verification of whatever actually arrived
        v_res = verify_signature(sig, received_statevectors=received)

        # 5. Statistical detection from the real measurement statistics
        det_res = self.detector.detect(v_res, session_id=sig.signature_id)

        # 6. Authorization -- a classical access-control layer running
        #    alongside the quantum-statistical detector, not instead of it
        #    (see docs/security_model.md)
        auth_status = "AUTHORIZED"
        if attack and "Unauthorized" in attack.name and intensity > 0:
            auth_check = check_authorization(metadata.verifier_id, metadata)
            if not auth_check.is_authorized:
                auth_status = "UNAUTHORIZED"
                det_res.classification = "REJECTED"
                reasons.append(f"authorization_failure: {auth_check.reason}")

        # 7. Replay -- detected by session-consistency checking
        if attack and "Replay" in attack.name and intensity > 0:
            expected_meta = SessionMetadata(
                session_id=sig.signature_id,
                message_id=session_label,
            )
            replay_check = check_replay(
                received=metadata,
                expected=expected_meta,
                max_staleness_seconds=60.0,
            )
            if replay_check.is_replay:
                det_res.classification = "REJECTED"
                reasons.extend(replay_check.reasons)
            
        t1 = time.perf_counter()
        
        detection_status = "NOT_APPLICABLE"
        if attack_type != "LEGITIMATE":
            if det_res.classification in ["SUSPICIOUS", "THREAT", "REJECTED"]:
                detection_status = "DETECTED"
            else:
                detection_status = "MISSED"
                
        return PipelineResult(
            session_id=sig.signature_id,
            signature_length=sig.length,
            quantum_state_basis="Mixed Pauli",
            teleportation_fidelity=fidelity_avg,
            measurement_statistics={"matches": v_res.matches, "total": sig.length},
            verification_score=v_res.verification_score,
            mismatch_rate=1.0 - v_res.verification_score,
            anomaly_score=det_res.anomaly_score,
            classification=det_res.classification,
            authorization_status=auth_status,
            attack_type=attack_type,
            detection_status=detection_status,
            decision_reasons=reasons,
            latency=t1 - t0
        )
