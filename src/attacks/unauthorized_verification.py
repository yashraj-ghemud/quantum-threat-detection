"""
attacks/unauthorized_verification.py
=====================================
Unauthorized verification attack simulation.

Phase 5 -- SIH26141 | Blockchain & Cybersecurity.

Simulates a party verifying a signature without valid authorization.
The attack is caught by **two independent layers**:

1. **Quantum (intercept-resend)** -- the primary mechanism.  To read a
   signature element the unauthorized party must measure it, and it does
   not know the element's Pauli basis (that is key material).  Measuring
   in the wrong basis collapses the state onto an eigenstate of the
   *wrong* basis, and no-cloning means the original cannot be restored.
   When the legitimate verifier later measures in the correct basis it
   gets a coin flip on those elements.  With a uniformly-guessed basis the
   eavesdropper is wrong 2/3 of the time and corrupts half of those, so
   the expected mismatch rate is ``intensity / 3`` -- a large, purely
   statistical signal the Phase 4 detector sees exactly like any other
   attack.  This is the same physics BB84 uses to detect eavesdropping.

2. **Classical access control** -- a defence-in-depth layer.  The
   authorization flag is checked independently of the anomaly score, so a
   party that never touches the quantum channel is still rejected.

Earlier revisions used only layer 2, which is why this attack category
reported an anomaly score of exactly 0.0000 while every other category was
detected statistically.  Both layers now run; see ``docs/security_model.md``.

No AI/ML is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from attacks.base import AttackResult, BaseAttack, SessionMetadata
from qds.pauli_states import get_eigenstate, projective_measurement_probs
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "UnauthorizedVerificationAttack",
    "AuthorizationCheck",
    "check_authorization",
    "MEASUREMENT_BASES",
    "COLLAPSE_TARGETS",
]

#: Bases an unauthorized party can guess when intercepting an element.
MEASUREMENT_BASES: tuple = ("x", "y", "z")

#: (basis, eigenvalue) -> eigenstate label the state collapses onto.
COLLAPSE_TARGETS: dict = {
    ("z", +1): "|0>",
    ("z", -1): "|1>",
    ("x", +1): "|+>",
    ("x", -1): "|->",
    ("y", +1): "|+i>",
    ("y", -1): "|-i>",
}


# ---------------------------------------------------------------------------
# Authorization check
# ---------------------------------------------------------------------------

@dataclass
class AuthorizationCheck:
    """Result of an explicit authorization check.

    Attributes
    ----------
    status : str
        'AUTHORIZED' or 'UNAUTHORIZED'.
    verifier_id : str
        Identity of the verifier.
    authorized_verifiers : list[str]
        List of verifier IDs that are authorized for this session.
    reason : str
        Human-readable explanation of the decision.
    """

    status: str = "UNAUTHORIZED"
    verifier_id: str = ""
    authorized_verifiers: list[str] = None  # type: ignore[assignment]
    reason: str = ""

    def __post_init__(self) -> None:
        if self.authorized_verifiers is None:
            self.authorized_verifiers = []

    @property
    def is_authorized(self) -> bool:
        return self.status == "AUTHORIZED"


def check_authorization(
    verifier_id: str,
    metadata: SessionMetadata,
    authorized_verifiers: Optional[List[str]] = None,
) -> AuthorizationCheck:
    """Check if a verifier is authorized for a session.

    Authorization is determined by:
    1. The metadata.authorized flag.
    2. The verifier_id being in the authorized_verifiers list.

    Parameters
    ----------
    verifier_id : str
        Identity of the verifier attempting verification.
    metadata : SessionMetadata
        Session metadata with authorization context.
    authorized_verifiers : list[str] or None
        List of authorized verifier IDs.  If None, uses
        [metadata.verifier_id] as the only authorized verifier.

    Returns
    -------
    AuthorizationCheck
    """
    if authorized_verifiers is None:
        authorized_verifiers = [metadata.verifier_id]

    if not metadata.authorized:
        return AuthorizationCheck(
            status="UNAUTHORIZED",
            verifier_id=verifier_id,
            authorized_verifiers=authorized_verifiers,
            reason=f"authorization_failure: session metadata marks "
                   f"authorization=False",
        )

    if verifier_id not in authorized_verifiers:
        return AuthorizationCheck(
            status="UNAUTHORIZED",
            verifier_id=verifier_id,
            authorized_verifiers=authorized_verifiers,
            reason=f"authorization_failure: verifier '{verifier_id}' "
                   f"not in authorized list {authorized_verifiers}",
        )

    return AuthorizationCheck(
        status="AUTHORIZED",
        verifier_id=verifier_id,
        authorized_verifiers=authorized_verifiers,
        reason=f"verifier '{verifier_id}' is authorized",
    )


# ---------------------------------------------------------------------------
# Unauthorized Verification Attack
# ---------------------------------------------------------------------------

class UnauthorizedVerificationAttack(BaseAttack):
    """Simulate an unauthorized verifier attempting verification.

    The attacker uses an unauthorized identity to attempt verification.
    The authorization check rejects the attempt independently of any
    statistical anomaly score.

    At intensity 0.0, no modification is made (verifier is authorized).
    At intensity > 0.0, the verifier identity is changed to an
    unauthorized one and/or the authorization flag is revoked.

    Parameters
    ----------
    seed : int
        Random seed for reproducibility.
    attacker_verifier_id : str
        Identity of the unauthorized verifier.
    """

    def __init__(
        self,
        seed: int = 42,
        attacker_verifier_id: str = "unauthorized_charlie",
        intercept_resend: bool = True,
    ) -> None:
        super().__init__(seed=seed)
        self._attacker_id = attacker_verifier_id
        self._intercept_resend = intercept_resend

    @property
    def intercept_resend(self) -> bool:
        """Whether the attacker physically measures the intercepted states."""
        return self._intercept_resend

    def _intercept(
        self,
        statevectors: List[np.ndarray],
        intensity: float,
    ) -> tuple:
        """Measure intercepted elements in a guessed basis, collapsing them.

        The attacker does not know each element's Pauli basis, so it guesses
        uniformly from :data:`MEASUREMENT_BASES`.  The element collapses onto
        an eigenstate of the *guessed* basis -- irreversibly, by no-cloning.

        Parameters
        ----------
        statevectors : list[np.ndarray]
            States on the channel (already deep-copied by ``BaseAttack``).
        intensity : float
            Fraction of elements the attacker intercepts.

        Returns
        -------
        tuple
            ``(collapsed_statevectors, intercepted_positions, wrong_basis_count)``.
        """
        n = len(statevectors)
        n_intercept = max(0, int(round(n * intensity)))
        if n_intercept == 0:
            return statevectors, [], 0

        positions = sorted(
            int(x) for x in self._rng.choice(n, size=n_intercept, replace=False)
        )

        wrong_basis = 0
        for pos in positions:
            sv = statevectors[pos]
            guessed = MEASUREMENT_BASES[int(self._rng.integers(0, len(MEASUREMENT_BASES)))]

            p_plus, _ = projective_measurement_probs(sv, guessed)
            outcome = +1 if float(self._rng.random()) < p_plus else -1

            # Collapse: the post-measurement state is the eigenstate of the
            # guessed basis matching the observed outcome.
            collapsed = get_eigenstate(COLLAPSE_TARGETS[(guessed, outcome)])
            statevectors[pos] = collapsed.statevector.copy()

            # A guess that is not the element's own basis leaves the state
            # in a superposition w.r.t. the true basis -- the damage the
            # legitimate verifier will observe.
            if not np.isclose(p_plus, 1.0) and not np.isclose(p_plus, 0.0):
                wrong_basis += 1

        return statevectors, positions, wrong_basis

    def _execute_attack(
        self,
        statevectors: List[np.ndarray],
        metadata: SessionMetadata,
        intensity: float,
    ) -> AttackResult:
        """Set unauthorized verification context.

        Parameters
        ----------
        statevectors : list[np.ndarray]
            Legitimate statevectors (unchanged).
        metadata : SessionMetadata
            Session metadata to manipulate.
        intensity : float
            0.0 = no manipulation (authorized), > 0.0 = unauthorized.

        Returns
        -------
        AttackResult
        """
        evidence: list[str] = []
        indicators: dict = {
            "attacker_verifier_id": self._attacker_id,
            "legitimate_verifier_id": metadata.verifier_id,
            "authorization_revoked": False,
            "intercept_resend": self._intercept_resend,
            "intercepted_positions": [],
            "n_intercepted": 0,
            "n_wrong_basis": 0,
        }

        if intensity <= 0.0:
            evidence.append("intensity=0.0: no unauthorized verification applied")
            return AttackResult(
                statevectors=statevectors,
                metadata=metadata,
                evidence=evidence,
                attack_indicators=indicators,
                authorization_status="AUTHORIZED",
            )

        # --- Layer 1: quantum intercept-resend -------------------------
        # Reading the states requires measuring them, which collapses them.
        if self._intercept_resend:
            statevectors, positions, wrong_basis = self._intercept(
                statevectors, intensity
            )
            indicators["intercepted_positions"] = positions
            indicators["n_intercepted"] = len(positions)
            indicators["n_wrong_basis"] = wrong_basis
            indicators["intercept_resend"] = True
            if positions:
                evidence.append(
                    f"quantum_state_collapse: {len(positions)} element(s) "
                    f"measured by an unauthorized party; {wrong_basis} were "
                    f"measured in the wrong basis and are now corrupted "
                    f"(no-cloning prevents restoration)"
                )
        else:
            indicators["intercept_resend"] = False
            indicators["n_intercepted"] = 0
            indicators["n_wrong_basis"] = 0

        # --- Layer 2: classical access control -------------------------
        metadata.authorized = False
        metadata.verifier_id = self._attacker_id
        indicators["authorization_revoked"] = True

        auth_check = check_authorization(
            verifier_id=self._attacker_id,
            metadata=metadata,
        )

        evidence.append(
            f"authorization_failure: verifier '{self._attacker_id}' "
            f"is not authorized for session {metadata.session_id[:8]}..."
        )
        evidence.append(
            f"authorization_status: {auth_check.status} — {auth_check.reason}"
        )
        indicators["auth_check_result"] = auth_check.status

        return AttackResult(
            statevectors=statevectors,
            metadata=metadata,
            evidence=evidence,
            attack_indicators=indicators,
            authorization_status="UNAUTHORIZED",
        )
