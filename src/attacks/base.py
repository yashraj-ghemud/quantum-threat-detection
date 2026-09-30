"""
attacks/base.py
================
Common attack abstraction for QDS attack simulation.

Phase 5 -- SIH26141 | Blockchain & Cybersecurity.

Every attack inherits from ``BaseAttack`` and must:
- receive legitimate QDS/session data
- modify or manipulate it according to the attack strategy
- return an ``AttackResult`` with the attacked session data
- preserve reproducibility using seeded randomness
- include attack name and metadata
- never modify the original legitimate session in-place

No AI/ML is used.
"""

from __future__ import annotations

import copy
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "SessionMetadata",
    "AttackResult",
    "BaseAttack",
]


# ---------------------------------------------------------------------------
# Session metadata for replay / context tracking
# ---------------------------------------------------------------------------

@dataclass
class SessionMetadata:
    """Metadata for a QDS verification session.

    Used for tracking session identity, timestamp, and authorization
    context.  The replay attack relies on these fields to detect
    session reuse.

    Attributes
    ----------
    session_id : str
        Unique identifier for this session (UUID4).
    message_id : str
        Message being signed/verified.
    sequence_number : int
        Monotonically increasing sequence counter.
    timestamp : float
        Session creation time (epoch seconds).
    signer_id : str
        Identity of the signer.
    verifier_id : str
        Identity of the intended verifier.
    authorized : bool
        Whether the verifier is authorized for this session.
    """

    session_id: str = ""
    message_id: str = ""
    sequence_number: int = 0
    timestamp: float = 0.0
    signer_id: str = "signer_alice"
    verifier_id: str = "verifier_bob"
    authorized: bool = True

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = str(uuid.uuid4())
        if self.timestamp <= 0:
            self.timestamp = time.time()


# ---------------------------------------------------------------------------
# Attack result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AttackResult:
    """Structured result of an attack simulation.

    Contains the attacked data and evidence explaining detection.

    Attributes
    ----------
    attack_name : str
        Human-readable name of the attack type.
    intensity : float
        Attack intensity in [0, 1].
    seed : int
        RNG seed used for reproducibility.
    statevectors : list[np.ndarray]
        Attacked statevectors to be passed to verify_signature.
    metadata : SessionMetadata
        Session metadata (potentially manipulated).
    original_metadata : SessionMetadata
        Original unmodified session metadata.
    evidence : list[str]
        Human-readable evidence explaining WHY the attack was/should be detected.
    attack_indicators : dict[str, Any]
        Machine-readable indicators for the attack.
    authorization_status : str
        'AUTHORIZED' or 'UNAUTHORIZED'.
    """

    attack_name: str = ""
    intensity: float = 0.0
    seed: int = 42
    statevectors: List[np.ndarray] = field(default_factory=list)
    metadata: SessionMetadata = field(default_factory=SessionMetadata)
    original_metadata: SessionMetadata = field(default_factory=SessionMetadata)
    evidence: List[str] = field(default_factory=list)
    attack_indicators: Dict[str, Any] = field(default_factory=dict)
    authorization_status: str = "AUTHORIZED"


# ---------------------------------------------------------------------------
# Base attack abstract class
# ---------------------------------------------------------------------------

class BaseAttack(ABC):
    """Abstract base class for all QDS attacks.

    Subclasses must implement ``execute()`` which receives the legitimate
    signature, statevectors, and session metadata, and returns an
    ``AttackResult`` with the manipulated data.

    The base class guarantees:
    - Deep copies are made of inputs (no in-place mutation).
    - A seeded RNG is provided for reproducibility.
    - Attack name is auto-populated from the subclass.

    Parameters
    ----------
    seed : int
        Random seed for reproducibility.
    """

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed
        self._rng = np.random.default_rng(seed)

    @property
    def name(self) -> str:
        """Human-readable name of this attack."""
        return self.__class__.__name__

    @property
    def seed(self) -> int:
        """RNG seed used by this attack."""
        return self._seed

    @abstractmethod
    def _execute_attack(
        self,
        statevectors: List[np.ndarray],
        metadata: SessionMetadata,
        intensity: float,
    ) -> AttackResult:
        """Implement the attack logic.

        Parameters
        ----------
        statevectors : list[np.ndarray]
            Deep copies of the legitimate statevectors.
        metadata : SessionMetadata
            Deep copy of the session metadata.
        intensity : float
            Attack intensity in [0.0, 1.0].

        Returns
        -------
        AttackResult
        """
        ...

    def execute(
        self,
        statevectors: List[np.ndarray],
        metadata: SessionMetadata,
        intensity: float = 1.0,
    ) -> AttackResult:
        """Execute the attack on a copy of the legitimate data.

        Parameters
        ----------
        statevectors : list[np.ndarray]
            Legitimate statevectors from signature.
        metadata : SessionMetadata
            Legitimate session metadata.
        intensity : float
            Attack intensity in [0.0, 1.0].  0.0 = no modification,
            1.0 = maximum modification.

        Returns
        -------
        AttackResult
            Result with attacked statevectors and evidence.
        """
        if not (0.0 <= intensity <= 1.0):
            raise ValueError(f"intensity must be in [0,1], got {intensity}.")

        # Deep copy to prevent in-place mutation
        sv_copy = [np.copy(sv) for sv in statevectors]
        meta_copy = copy.deepcopy(metadata)
        orig_meta = copy.deepcopy(metadata)

        # Reset RNG for determinism
        self._rng = np.random.default_rng(self._seed)

        result = self._execute_attack(sv_copy, meta_copy, intensity)
        result.attack_name = self.name
        result.intensity = intensity
        result.seed = self._seed
        result.original_metadata = orig_meta

        logger.info(
            "Attack %s executed: intensity=%.2f evidence=%d indicators=%d",
            self.name, intensity, len(result.evidence), len(result.attack_indicators),
        )
        return result
