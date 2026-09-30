"""
attacks — QDS Attack Simulation & Threat Validation.

Phase 5 -- SIH26141 | Blockchain & Cybersecurity.

Modules
-------
base                       : Common attack abstraction (BaseAttack, AttackResult)
forgery                    : Signature forgery via controlled state substitution
impersonation              : Signer impersonation with unauthorized key material
replay                     : Replay attack with session consistency checks
unauthorized_verification  : Unauthorized verifier access control
channel_manipulation       : Quantum channel depolarizing/dephasing disturbance
runner                     : Attack scenario orchestrator with Phase 4 integration

No AI/ML is used.
"""

from attacks.base import (
    SessionMetadata,
    AttackResult,
    BaseAttack,
)

from attacks.forgery import ForgeryAttack
from attacks.impersonation import ImpersonationAttack
from attacks.replay import ReplayAttack, ReplayCheckResult, check_replay
from attacks.unauthorized_verification import (
    UnauthorizedVerificationAttack,
    AuthorizationCheck,
    check_authorization,
)
from attacks.channel_manipulation import ChannelManipulationAttack
from attacks.runner import AttackScenarioResult, AttackRunner

__all__: list[str] = [
    # base
    "SessionMetadata",
    "AttackResult",
    "BaseAttack",
    # attacks
    "ForgeryAttack",
    "ImpersonationAttack",
    "ReplayAttack",
    "ReplayCheckResult",
    "check_replay",
    "UnauthorizedVerificationAttack",
    "AuthorizationCheck",
    "check_authorization",
    "ChannelManipulationAttack",
    # runner
    "AttackScenarioResult",
    "AttackRunner",
]
