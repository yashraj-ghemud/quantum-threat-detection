"""
attacks/forgery.py
==================
Quantum signature forgery attack simulation.

Phase 5 -- SIH26141 | Blockchain & Cybersecurity.

Simulates an attacker attempting to create/alter a valid QDS signature
without the signer's private key.  Three adversary models are provided:

``strategy='random'`` (default, backward compatible)
    A naive adversary substituting uniformly-random Pauli eigenstates.
    It knows nothing and learns nothing.

``strategy='key_ignorant'``
    A *realistic* adversary holding everything genuinely public: the
    published ``quantum_config.yaml`` (including ``random_seed: 42``), the
    signer's public key **fingerprint**, the message, and the public index
    derivation from :func:`qds.keygen.derive_signature_indices`.  It does
    **not** hold the private seed.  Because the key table is HMAC-derived,
    none of that public material narrows the search, so this adversary
    cannot beat uniform guessing -- precisely the property the security
    evaluation needs to demonstrate.

``strategy='learned'``
    The strongest realistic adversary: it has observed previous
    (message, signature) pairs from the same signer.  Signature positions
    are drawn from a finite key table, so indices recur across messages and
    every recurrence leaks that table entry.  The attacker replays learned
    states at known indices and guesses elsewhere.  This models the
    key-reuse weakness inherent to finite-table QDS and is the case that
    justifies bounding the number of signatures per key.

Controlled signature-state substitutions:
- intensity 0.0 → no modification (identity)
- intensity 1.0 → all elements replaced by the attacker's chosen states

The resulting measurements are processed by the Phase 4 detector,
which flags the statistical deviation from the legitimate baseline.

No AI/ML is used.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from attacks.base import AttackResult, BaseAttack, SessionMetadata
from qds.pauli_states import EIGENSTATE_LABELS, get_eigenstate
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = ["ForgeryAttack", "FORGERY_STRATEGIES"]

#: Supported adversary models, weakest to strongest.
FORGERY_STRATEGIES: Tuple[str, ...] = ("random", "key_ignorant", "learned")


class ForgeryAttack(BaseAttack):
    """Simulate signature forgery by substituting statevectors.

    The attacker replaces a fraction of the signature's statevectors with
    states chosen according to its *strategy* -- see the module docstring
    for the three adversary models.

    Parameters
    ----------
    seed : int
        Random seed for reproducibility.
    strategy : str
        One of :data:`FORGERY_STRATEGIES`.
    observed_table : dict[int, str] or None
        For ``strategy='learned'``: key-table entries the attacker already
        recovered from observed signatures, as
        ``{table_index: eigenstate_label}``.
    target_indices : sequence of int or None
        For ``strategy='learned'``: the key-table index used at each
        position of the signature under attack.  These are public (derived
        from the message digest), so the attacker legitimately knows them.

    Raises
    ------
    ValueError
        If *strategy* is not a recognised adversary model.
    """

    def __init__(
        self,
        seed: int = 42,
        strategy: str = "random",
        observed_table: Optional[Dict[int, str]] = None,
        target_indices: Optional[Sequence[int]] = None,
    ) -> None:
        super().__init__(seed=seed)
        if strategy not in FORGERY_STRATEGIES:
            raise ValueError(
                f"Unknown forgery strategy {strategy!r}. "
                f"Supported: {list(FORGERY_STRATEGIES)}"
            )
        self._strategy = strategy
        self._observed_table = dict(observed_table or {})
        self._target_indices = tuple(target_indices or ())

    @property
    def strategy(self) -> str:
        """The adversary model in use."""
        return self._strategy

    @property
    def variant(self) -> str:
        """Attack name qualified by strategy, e.g. ``'ForgeryAttack[learned]'``.

        ``name`` deliberately stays the bare class name so existing result
        files and callers keep working; use *variant* when results from
        different adversary models must stay distinguishable.
        """
        return f"{self.__class__.__name__}[{self._strategy}]"

    def _choose_state(self, position: int) -> Tuple[str, str]:
        """Pick the attacker's substitute label for *position*.

        Returns
        -------
        tuple[str, str]
            ``(label, provenance)`` where provenance is ``'learned'`` or
            ``'guessed'``.
        """
        labels = list(EIGENSTATE_LABELS)

        if self._strategy == "learned" and position < len(self._target_indices):
            table_index = self._target_indices[position]
            known = self._observed_table.get(table_index)
            if known is not None:
                # Recovered from a previously observed signature: exact.
                return known, "learned"

        # 'random' and 'key_ignorant' are operationally identical, and that
        # is the finding: public config plus fingerprint gives no advantage
        # over uniform guessing against an HMAC-derived key table.
        return labels[int(self._rng.integers(0, len(labels)))], "guessed"

    def _execute_attack(
        self,
        statevectors: List[np.ndarray],
        metadata: SessionMetadata,
        intensity: float,
    ) -> AttackResult:
        """Replace a controlled fraction of statevectors with random eigenstates.

        Parameters
        ----------
        statevectors : list[np.ndarray]
            Deep copies of legitimate statevectors.
        metadata : SessionMetadata
            Session metadata (not modified by forgery).
        intensity : float
            Fraction of elements to forge.  0.0 = none, 1.0 = all.

        Returns
        -------
        AttackResult
        """
        n = len(statevectors)
        n_forge = max(0, int(round(n * intensity)))
        evidence: list[str] = []
        indicators: dict = {
            "n_forged": n_forge,
            "n_total": n,
            "forge_fraction": n_forge / n if n > 0 else 0.0,
            "forged_positions": [],
            "strategy": self._strategy,
        }

        if n_forge == 0:
            evidence.append("intensity=0.0: no forgery applied")
            return AttackResult(
                statevectors=statevectors,
                metadata=metadata,
                evidence=evidence,
                attack_indicators=indicators,
            )

        # Randomly select which positions to forge
        positions = self._rng.choice(n, size=n_forge, replace=False)
        positions.sort()

        n_learned = 0
        for pos in positions:
            forged_label, provenance = self._choose_state(int(pos))
            forged_state = get_eigenstate(forged_label)
            statevectors[int(pos)] = forged_state.statevector.copy()
            indicators["forged_positions"].append(int(pos))
            if provenance == "learned":
                n_learned += 1
            evidence.append(
                f"signature_mismatch: position {int(pos)} forged with "
                f"{provenance} eigenstate {forged_label}"
            )

        indicators["n_learned"] = n_learned
        indicators["n_guessed"] = n_forge - n_learned
        indicators["key_knowledge"] = (
            len(self._observed_table) if self._strategy == "learned" else 0
        )

        evidence.append(
            f"forgery_summary: {n_forge}/{n} elements replaced "
            f"({100.0 * n_forge / n:.1f}%) via strategy={self._strategy} "
            f"[learned={n_learned}, guessed={n_forge - n_learned}]"
        )

        return AttackResult(
            statevectors=statevectors,
            metadata=metadata,
            evidence=evidence,
            attack_indicators=indicators,
        )
