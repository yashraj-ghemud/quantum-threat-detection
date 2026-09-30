"""
attacks/channel_manipulation.py
================================
Quantum channel manipulation attack simulation.

Phase 5 -- SIH26141 | Blockchain & Cybersecurity.

Simulates channel-level manipulation between signer and verifier.
Models physically meaningful quantum channel disturbances:

1. **State corruption (depolarizing)**: Applies a depolarizing-like
   disturbance to statevectors, mixing the pure state with the
   maximally mixed state.  Parameterised by probability p.

2. **Measurement disturbance (dephasing)**: Applies random phase
   rotations to statevectors, simulating an eavesdropper's
   measurement back-action on the quantum channel.

3. **Configurable disturbance probability**: Each element is
   independently disturbed with probability proportional to intensity.

4. **Real quantum channel** (``mode='quantum_channel'``): rather than
   applying an analytic map to an abstract vector, each state is actually
   transmitted through the 3-qubit teleportation circuit on Aer -- Bell
   pair, Bell measurement, classical Pauli correction -- with the
   adversary injecting a Qiskit noise model onto the channel qubits.  The
   verifier then receives whatever genuinely came out the far end.  This is
   the mode that exercises the same transport path the live QDS scheme
   uses for key distribution (:mod:`qds.key_distribution`).

The disturbances are quantum-mechanically motivated:
- Depolarizing channel:  ρ → (1-p)ρ + p·I/2
- Dephasing channel:     |ψ⟩ → Rz(θ)|ψ⟩  with random θ

No random corruption of classical metadata is performed.
No AI/ML is used.
"""

from __future__ import annotations

from typing import List

import numpy as np

from attacks.base import AttackResult, BaseAttack, SessionMetadata
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = ["ChannelManipulationAttack"]


def _apply_depolarizing(
    statevector: np.ndarray,
    p: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply a depolarizing-like disturbance to a pure statevector.

    With probability p, replace the statevector with a uniformly
    random pure state on the Bloch sphere.  With probability (1-p),
    keep the original statevector.

    This simulates the depolarizing channel ρ → (1-p)ρ + p·I/2
    at the state level.

    Parameters
    ----------
    statevector : np.ndarray
        Input pure state (2,).
    p : float
        Disturbance probability in [0, 1].
    rng : np.random.Generator

    Returns
    -------
    np.ndarray
        Disturbed statevector (normalized).
    """
    if rng.random() >= p:
        return statevector

    # Generate a random Bloch sphere direction using Haar measure
    theta = np.arccos(1 - 2 * rng.random())
    phi = 2 * np.pi * rng.random()
    new_sv = np.array([
        np.cos(theta / 2),
        np.exp(1j * phi) * np.sin(theta / 2),
    ], dtype=complex)
    return new_sv


def _apply_dephasing(
    statevector: np.ndarray,
    p: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply a dephasing-like disturbance to a pure statevector.

    Applies a random Z-rotation Rz(θ) with θ drawn from [-π·p, π·p].
    This simulates the measurement back-action of an eavesdropper.

    Parameters
    ----------
    statevector : np.ndarray
        Input pure state (2,).
    p : float
        Disturbance strength — controls the range of the random phase.
    rng : np.random.Generator

    Returns
    -------
    np.ndarray
        Dephased statevector (normalized).
    """
    if p <= 0.0:
        return statevector

    # Random phase rotation angle
    angle = rng.uniform(-np.pi * p, np.pi * p)
    rz = np.array([
        [np.exp(-1j * angle / 2), 0],
        [0, np.exp(1j * angle / 2)],
    ], dtype=complex)
    new_sv = rz @ statevector
    # Renormalize (should already be unit norm, but for safety)
    norm = np.linalg.norm(new_sv)
    if norm > 1e-15:
        new_sv = new_sv / norm
    return new_sv


class ChannelManipulationAttack(BaseAttack):
    """Simulate quantum channel manipulation between signer and verifier.

    Applies physically motivated quantum disturbances to the statevectors
    in transit.  Supports depolarizing and dephasing disturbance modes.

    Parameters
    ----------
    seed : int
        Random seed for reproducibility.
    mode : str
        Disturbance mode: 'depolarizing', 'dephasing', or 'both'.
    """

    def __init__(
        self,
        seed: int = 42,
        mode: str = "both",
        channel_noise: str = "depolarizing",
        shots: int = 256,
    ) -> None:
        super().__init__(seed=seed)
        valid = ("depolarizing", "dephasing", "both", "quantum_channel")
        if mode not in valid:
            raise ValueError(f"mode must be one of {valid}, got {mode!r}")
        self._mode = mode
        self._channel_noise = channel_noise
        self._shots = shots

    @property
    def mode(self) -> str:
        """Disturbance model in use."""
        return self._mode

    def _run_quantum_channel(
        self,
        statevectors: List[np.ndarray],
        intensity: float,
    ) -> tuple[List[np.ndarray], List[float]]:
        """Transmit every state through the real noisy teleportation channel.

        Returns
        -------
        tuple
            ``(received_statevectors, per_element_fidelities)``.
        """
        from qds.key_distribution import teleport_statevector

        received: List[np.ndarray] = []
        fidelities: List[float] = []
        for i, sv in enumerate(statevectors):
            got, fid = teleport_statevector(
                sv,
                noise_type=self._channel_noise,
                noise_level=intensity,
                shots=self._shots,
                seed=self._seed + i,
            )
            received.append(got)
            fidelities.append(fid)
        return received, fidelities

    def _execute_attack(
        self,
        statevectors: List[np.ndarray],
        metadata: SessionMetadata,
        intensity: float,
    ) -> AttackResult:
        """Apply quantum channel disturbances to statevectors.

        Parameters
        ----------
        statevectors : list[np.ndarray]
            Deep copies of legitimate statevectors.
        metadata : SessionMetadata
            Session metadata (not modified by channel manipulation).
        intensity : float
            Probability of disturbance per element.
            0.0 = no disturbance, 1.0 = maximum disturbance.

        Returns
        -------
        AttackResult
        """
        n = len(statevectors)
        evidence: list[str] = []
        disturbed_count = 0
        indicators: dict = {
            "mode": self._mode,
            "n_total": n,
            "n_disturbed": 0,
            "disturbed_positions": [],
            "disturbance_probability": intensity,
        }

        if intensity <= 0.0:
            evidence.append("intensity=0.0: no channel manipulation applied")
            return AttackResult(
                statevectors=statevectors,
                metadata=metadata,
                evidence=evidence,
                attack_indicators=indicators,
            )

        if self._mode == "quantum_channel":
            received, fidelities = self._run_quantum_channel(statevectors, intensity)
            mean_fid = float(np.mean(fidelities)) if fidelities else 1.0
            n_degraded = sum(1 for f in fidelities if f < 0.999)

            indicators["n_disturbed"] = n_degraded
            indicators["disturbed_positions"] = [
                i for i, f in enumerate(fidelities) if f < 0.999
            ]
            indicators["channel_noise"] = self._channel_noise
            indicators["mean_channel_fidelity"] = mean_fid
            indicators["element_fidelities"] = fidelities

            evidence.append(
                f"quantum_channel_interference: {n_degraded}/{n} teleported "
                f"states degraded by injected {self._channel_noise} noise "
                f"(p={intensity:.2f}), mean channel fidelity={mean_fid:.4f}"
            )
            return AttackResult(
                statevectors=received,
                metadata=metadata,
                evidence=evidence,
                attack_indicators=indicators,
            )

        for i in range(n):
            sv = statevectors[i]
            original_sv = sv.copy()
            modified = False

            if self._mode in ("depolarizing", "both"):
                sv = _apply_depolarizing(sv, intensity, self._rng)
                if not np.allclose(sv, original_sv, atol=1e-12):
                    modified = True

            if self._mode in ("dephasing", "both"):
                sv = _apply_dephasing(sv, intensity, self._rng)
                if not np.allclose(sv, original_sv, atol=1e-12):
                    modified = True

            statevectors[i] = sv

            if modified:
                disturbed_count += 1
                indicators["disturbed_positions"].append(i)
                evidence.append(
                    f"channel_disturbance: position {i} disturbed "
                    f"via {self._mode} channel (intensity={intensity:.2f})"
                )

        indicators["n_disturbed"] = disturbed_count

        evidence.append(
            f"channel_manipulation_summary: {disturbed_count}/{n} elements "
            f"disturbed ({100.0 * disturbed_count / n:.1f}%) via {self._mode}"
        )

        return AttackResult(
            statevectors=statevectors,
            metadata=metadata,
            evidence=evidence,
            attack_indicators=indicators,
        )
