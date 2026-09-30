"""
attacks/impersonation.py
========================
Signer impersonation attack simulation.

Phase 5 -- SIH26141 | Blockchain & Cybersecurity.

Simulates an unauthorized signer attempting to act as a legitimate
participant.  The impersonator generates their own signature using a
different seed (different key material), producing a mismatched state
sequence that is distinguishable through verification statistics.

The impersonator's identity context is explicitly tracked so that
detection can identify identity/context mismatch as the reason.

No AI/ML is used.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from attacks.base import AttackResult, BaseAttack, SessionMetadata
from qds.pauli_states import EIGENSTATE_LABELS, get_eigenstate
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = ["ImpersonationAttack", "IMPERSONATION_STRATEGIES"]

#: Supported impersonator models.
IMPERSONATION_STRATEGIES: Tuple[str, ...] = ("own_seed", "own_keypair")


class ImpersonationAttack(BaseAttack):
    """Simulate signer impersonation using unauthorized key material.

    Two impersonator models are provided:

    ``strategy='own_seed'`` (default, backward compatible)
        The impersonator derives a state sequence from its own arbitrary
        RNG seed.  This tests detection of *unrelated* key material.

    ``strategy='own_keypair'``
        The *realistic* model: the impersonator runs the real key-generation
        protocol, obtaining a perfectly valid QDS key pair of its own, and
        signs the victim's message with it.  Its signature is internally
        self-consistent -- it would verify against **its own** public key.
        It fails only because the verifier holds Alice's key, which is the
        property the scheme must guarantee.  This is a materially stronger
        adversary than an attacker emitting unrelated noise.

    Parameters
    ----------
    seed : int
        Random seed for reproducibility.
    impersonator_id : str
        Identity string for the impersonator.
    strategy : str
        One of :data:`IMPERSONATION_STRATEGIES`.
    message : bytes or str or None
        For ``strategy='own_keypair'``: the message the impersonator signs
        with its own key.  Defaults to a fixed placeholder.

    Raises
    ------
    ValueError
        If *strategy* is not recognised.
    """

    def __init__(
        self,
        seed: int = 42,
        impersonator_id: str = "attacker_eve",
        strategy: str = "own_seed",
        message: Optional[bytes] = None,
    ) -> None:
        super().__init__(seed=seed)
        if strategy not in IMPERSONATION_STRATEGIES:
            raise ValueError(
                f"Unknown impersonation strategy {strategy!r}. "
                f"Supported: {list(IMPERSONATION_STRATEGIES)}"
            )
        self._impersonator_id = impersonator_id
        self._strategy = strategy
        self._message = message if message is not None else b"impersonated-message"

    @property
    def strategy(self) -> str:
        """The impersonator model in use."""
        return self._strategy

    @property
    def variant(self) -> str:
        """Attack name qualified by strategy, e.g. ``'ImpersonationAttack[learned]'``.

        ``name`` deliberately stays the bare class name so existing result
        files and callers keep working; use *variant* when results from
        different adversary models must stay distinguishable.
        """
        return f"{self.__class__.__name__}[{self._strategy}]"

    def _impersonator_states(self, n: int) -> List["np.ndarray"]:
        """Build the impersonator's substitute statevector sequence."""
        if self._strategy == "own_keypair":
            # A genuine, valid key pair belonging to the attacker.
            from qds.keygen import generate_key_pair
            from qds.signer import sign_message

            priv, _ = generate_key_pair(signer_id=self._impersonator_id)
            forged = sign_message(self._message, priv, length=n)
            return [e.statevector.copy() for e in forged.elements]

        imp_rng = np.random.default_rng(self._seed + 9999)
        labels = list(EIGENSTATE_LABELS)
        return [
            get_eigenstate(labels[int(idx)]).statevector.copy()
            for idx in imp_rng.integers(0, len(labels), size=n)
        ]

    def _execute_attack(
        self,
        statevectors: List[np.ndarray],
        metadata: SessionMetadata,
        intensity: float,
    ) -> AttackResult:
        """Replace statevectors with impersonator's key material.

        Parameters
        ----------
        statevectors : list[np.ndarray]
            Deep copies of legitimate statevectors.
        metadata : SessionMetadata
            Session metadata (signer_id will be changed).
        intensity : float
            Fraction of elements to replace.  0.0 = none, 1.0 = all.

        Returns
        -------
        AttackResult
        """
        n = len(statevectors)
        n_impersonate = max(0, int(round(n * intensity)))
        evidence: list[str] = []
        indicators: dict = {
            "n_impersonated": n_impersonate,
            "n_total": n,
            "impersonator_id": self._impersonator_id,
            "legitimate_signer_id": metadata.signer_id,
            "impersonate_fraction": n_impersonate / n if n > 0 else 0.0,
            "impersonated_positions": [],
            "strategy": self._strategy,
        }

        if n_impersonate == 0:
            evidence.append("intensity=0.0: no impersonation applied")
            return AttackResult(
                statevectors=statevectors,
                metadata=metadata,
                evidence=evidence,
                attack_indicators=indicators,
            )

        # Build the impersonator's own state sequence per its strategy
        imp_states = self._impersonator_states(n)

        # Replace a fraction of positions with impersonator states
        positions = self._rng.choice(n, size=n_impersonate, replace=False)
        positions.sort()

        for pos in positions:
            statevectors[int(pos)] = imp_states[int(pos)]
            indicators["impersonated_positions"].append(int(pos))
            evidence.append(
                f"identity_mismatch: position {int(pos)} replaced "
                f"with impersonator ({self._impersonator_id}) state"
            )

        # Update metadata to reflect impersonation
        metadata.signer_id = self._impersonator_id
        evidence.append(
            f"identity_context_mismatch: signer_id changed from "
            f"'{indicators['legitimate_signer_id']}' to '{self._impersonator_id}'"
        )
        evidence.append(
            f"impersonation_summary: {n_impersonate}/{n} elements replaced "
            f"({100.0 * n_impersonate / n:.1f}%) via strategy={self._strategy}"
        )

        return AttackResult(
            statevectors=statevectors,
            metadata=metadata,
            evidence=evidence,
            attack_indicators=indicators,
        )
