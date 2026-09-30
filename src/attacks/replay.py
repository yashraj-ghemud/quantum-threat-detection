"""
attacks/replay.py
=================
Replay attack simulation against the QDS protocol.

Phase 5 -- SIH26141 | Blockchain & Cybersecurity.

Simulates reuse of an old valid QDS signature/session against a new
verification context.  The attacker captures a valid signature and
replays it at a later time with a different sequence number.

Replay detection uses protocol/session consistency checks:
- Session ID mismatch between replayed and expected session
- Sequence number mismatch (old sequence number replayed in new context)
- Timestamp staleness beyond configurable window
- Message ID inconsistency

Detection does NOT simply label every repeated session as an attack;
it checks the context fields for consistency.

No AI/ML is used.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from attacks.base import AttackResult, BaseAttack, SessionMetadata
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = ["ReplayAttack", "ReplayCheckResult", "check_replay"]


# ---------------------------------------------------------------------------
# Replay detection check result
# ---------------------------------------------------------------------------

@dataclass
class ReplayCheckResult:
    """Result of a deterministic replay detection check.

    Attributes
    ----------
    is_replay : bool
        True if replay is detected through consistency checks.
    reasons : list[str]
        Human-readable reasons for the detection decision.
    session_id_match : bool
        Whether session IDs match the expected context.
    sequence_valid : bool
        Whether the sequence number is consistent.
    timestamp_valid : bool
        Whether the timestamp is within the acceptance window.
    message_consistent : bool
        Whether the message ID matches the expected context.
    """

    is_replay: bool = False
    reasons: list[str] = None  # type: ignore[assignment]
    session_id_match: bool = True
    sequence_valid: bool = True
    timestamp_valid: bool = True
    message_consistent: bool = True

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = []


def check_replay(
    received: SessionMetadata,
    expected: SessionMetadata,
    max_staleness_seconds: float = 60.0,
) -> ReplayCheckResult:
    """Deterministic replay detection using session consistency checks.

    Compares the received session metadata against the expected new-session
    context.  An attack is flagged when any consistency check fails.

    Parameters
    ----------
    received : SessionMetadata
        Metadata from the session being verified (possibly replayed).
    expected : SessionMetadata
        Expected metadata for a fresh, legitimate session.
    max_staleness_seconds : float
        Maximum acceptable age of the session timestamp.

    Returns
    -------
    ReplayCheckResult
    """
    reasons: list[str] = []

    # Check 1: Session ID must match expected context
    session_id_ok = (received.session_id == expected.session_id)
    if not session_id_ok:
        reasons.append(
            f"replay_session_mismatch: received session_id "
            f"{received.session_id[:8]}... != expected {expected.session_id[:8]}..."
        )

    # Check 2: Sequence number must be current (not reused)
    sequence_ok = (received.sequence_number == expected.sequence_number)
    if not sequence_ok:
        reasons.append(
            f"replay_sequence_mismatch: received seq={received.sequence_number} "
            f"!= expected seq={expected.sequence_number}"
        )

    # Check 3: Timestamp must be within acceptance window
    age = abs(expected.timestamp - received.timestamp)
    timestamp_ok = (age <= max_staleness_seconds)
    if not timestamp_ok:
        reasons.append(
            f"replay_timestamp_stale: session age={age:.1f}s "
            f"exceeds max={max_staleness_seconds:.1f}s"
        )

    # Check 4: Message ID consistency
    message_ok = (received.message_id == expected.message_id)
    if not message_ok:
        reasons.append(
            f"replay_message_mismatch: received msg={received.message_id!r} "
            f"!= expected msg={expected.message_id!r}"
        )

    is_replay = not (session_id_ok and sequence_ok and timestamp_ok and message_ok)

    return ReplayCheckResult(
        is_replay=is_replay,
        reasons=reasons,
        session_id_match=session_id_ok,
        sequence_valid=sequence_ok,
        timestamp_valid=timestamp_ok,
        message_consistent=message_ok,
    )


# ---------------------------------------------------------------------------
# Replay Attack
# ---------------------------------------------------------------------------

class ReplayAttack(BaseAttack):
    """Simulate replay of an old valid QDS session.

    The attacker captures an old valid session and replays it in a
    new context.  The session metadata is kept from the old session,
    creating detectable mismatches with the new expected context.

    At intensity 0.0, statevectors are unchanged and metadata is valid.
    At intensity 1.0, statevectors are unchanged but metadata is
    from an old session with mismatched sequence, timestamp, and IDs.

    Parameters
    ----------
    seed : int
        Random seed for reproducibility.
    staleness_seconds : float
        How old the replayed session appears (seconds in the past).
    """

    def __init__(
        self,
        seed: int = 42,
        staleness_seconds: float = 120.0,
    ) -> None:
        super().__init__(seed=seed)
        self._staleness = staleness_seconds

    def _execute_attack(
        self,
        statevectors: List[np.ndarray],
        metadata: SessionMetadata,
        intensity: float,
    ) -> AttackResult:
        """Replay an old session against a new verification context.

        Parameters
        ----------
        statevectors : list[np.ndarray]
            Legitimate statevectors (unchanged in replay).
        metadata : SessionMetadata
            Legitimate session metadata.
        intensity : float
            Controls the severity of replay manipulation.
            0.0 = no replay, 1.0 = full replay.

        Returns
        -------
        AttackResult
        """
        evidence: list[str] = []
        indicators: dict = {
            "replay_type": "session_replay",
            "staleness_seconds": 0.0,
            "sequence_offset": 0,
            "session_id_changed": False,
            "message_id_changed": False,
        }

        if intensity <= 0.0:
            evidence.append("intensity=0.0: no replay applied")
            return AttackResult(
                statevectors=statevectors,
                metadata=metadata,
                evidence=evidence,
                attack_indicators=indicators,
            )

        # Create the replayed (old) session metadata
        staleness = self._staleness * intensity
        old_seq_offset = max(1, int(10 * intensity))

        # Old session had a different session ID and older timestamp
        old_session_id = str(uuid.UUID(int=int(self._rng.integers(0, 2**63))))
        metadata.session_id = old_session_id
        metadata.timestamp = metadata.timestamp - staleness
        metadata.sequence_number = max(0, metadata.sequence_number - old_seq_offset)

        # At high intensity, also change the message_id (cross-message replay)
        if intensity >= 0.5:
            old_msg = f"old_msg_{int(self._rng.integers(0, 1000))}"
            metadata.message_id = old_msg
            indicators["message_id_changed"] = True
            evidence.append(
                f"replay_message_mismatch: replayed message_id={old_msg!r}"
            )

        indicators["staleness_seconds"] = staleness
        indicators["sequence_offset"] = old_seq_offset
        indicators["session_id_changed"] = True

        evidence.append(
            f"replay_session_mismatch: replayed old session_id={old_session_id[:8]}..."
        )
        evidence.append(
            f"replay_sequence_mismatch: sequence number reduced by {old_seq_offset}"
        )
        evidence.append(
            f"replay_timestamp_stale: session appears {staleness:.1f}s old"
        )

        return AttackResult(
            statevectors=statevectors,
            metadata=metadata,
            evidence=evidence,
            attack_indicators=indicators,
        )
