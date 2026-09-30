"""
qds/key_distribution.py
=======================
Quantum public-key distribution by Bell-state entanglement and teleportation.

Phase 3 -- SIH26141 | Blockchain & Cybersecurity.

This module is the functional bridge between :mod:`quantum` and :mod:`qds`.
The signer does **not** hand the verifier a classical list of eigenstate
labels; it teleports each key-table eigenstate across a quantum channel:

1. Signer and verifier share a ``|Φ+⟩`` Bell pair
   (:mod:`quantum.bell_states`, realised inside the teleportation circuit).
2. The signer performs a Bell-basis measurement on (key qubit, its half of
   the pair), yielding two classical correction bits.
3. The verifier applies the corresponding Pauli correction (``X`` / ``Z``)
   to its half -- standard teleportation, implemented in
   :mod:`quantum.teleportation`.
4. The verifier tomographically reconstructs the received qubit's Bloch
   vector and identifies which of the six Pauli eigenstates it holds.

Because the channel is a real simulated quantum channel, the noise models
in :mod:`quantum.noise` apply here, and a channel-manipulation adversary
(:mod:`attacks.channel_manipulation`) perturbs an actual transmitted state
rather than an abstract statevector.

No AI/ML libraries are used.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from qds.keygen import PrivateKey, PublicKey
from qds.pauli_states import (
    EIGENSTATE_LABELS,
    PAULI_MATRICES,
    PauliEigenstate,
    get_eigenstate,
)
from utils.config import ConfigLoader
from utils.logger import get_logger

logger = get_logger(__name__)

__all__: list[str] = [
    "KeyDistributionResult",
    "teleport_eigenstate",
    "teleport_statevector",
    "statevector_to_bloch_angles",
    "dominant_pure_state",
    "sample_pure_state",
    "reconstruct_label",
    "bloch_vector_from_density_matrix",
    "distribute_public_key",
]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class KeyDistributionResult:
    """Outcome of teleporting one signer key table to a verifier.

    Attributes
    ----------
    key_id : str
        Identifier of the key pair being distributed.
    table_size : int
        Number of eigenstates teleported.
    sent_labels : tuple[str, ...]
        The signer's true key-table labels.
    received_labels : tuple[str, ...]
        Labels the verifier reconstructed from the teleported states.
    fidelities : list[float]
        Per-eigenstate teleportation fidelity.
    mean_fidelity : float
        Mean of *fidelities*.
    correction_bits : list[tuple[int, int]]
        Classical Bell-measurement correction bits per teleported state.
    reconstruction_errors : int
        Count of positions where the verifier's label differs from the
        signer's -- non-zero only under strong channel noise.
    noise_type : str or None
        Noise channel applied during distribution.
    noise_level : float
        Noise probability used.
    """

    key_id: str
    table_size: int
    sent_labels: Tuple[str, ...]
    received_labels: Tuple[str, ...]
    fidelities: List[float] = field(default_factory=list)
    mean_fidelity: float = 1.0
    correction_bits: List[Tuple[int, int]] = field(default_factory=list)
    reconstruction_errors: int = 0
    noise_type: Optional[str] = None
    noise_level: float = 0.0

    @property
    def reconstruction_accuracy(self) -> float:
        """Fraction of key-table positions recovered correctly."""
        if self.table_size == 0:
            return 0.0
        return 1.0 - (self.reconstruction_errors / self.table_size)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"KeyDistributionResult(key_id={self.key_id[:8]}..., "
            f"n={self.table_size}, mean_F={self.mean_fidelity:.4f}, "
            f"accuracy={self.reconstruction_accuracy:.4f}, "
            f"noise={self.noise_type}@{self.noise_level:.3f})"
        )


# ---------------------------------------------------------------------------
# Bloch reconstruction
# ---------------------------------------------------------------------------

def bloch_vector_from_density_matrix(rho) -> np.ndarray:
    """Return the Bloch vector (bx, by, bz) of a single-qubit density matrix.

    Uses ``b_k = Tr(rho * sigma_k)``.

    Parameters
    ----------
    rho : DensityMatrix or array-like, shape (2, 2)
        Single-qubit density matrix.

    Returns
    -------
    np.ndarray, shape (3,)
        Real Bloch-vector components in x, y, z order.
    """
    mat = np.asarray(getattr(rho, "data", rho), dtype=complex)
    return np.array(
        [float(np.real(np.trace(mat @ PAULI_MATRICES[b]))) for b in ("x", "y", "z")],
        dtype=float,
    )


def reconstruct_label(rho) -> Tuple[str, float]:
    """Identify which Pauli eigenstate a received qubit is closest to.

    The verifier measures the teleported qubit's Bloch vector and picks the
    eigenstate with maximum overlap.  Under a noiseless channel this is
    exact; under noise the Bloch vector shrinks toward the origin but its
    *direction* -- and therefore the identified label -- stays correct until
    the noise is severe.

    Parameters
    ----------
    rho : DensityMatrix or array-like, shape (2, 2)
        Bob's reduced density matrix after teleportation corrections.

    Returns
    -------
    tuple[str, float]
        ``(label, overlap)`` -- the identified eigenstate label and its
        Bloch-vector overlap (dot product) with the received state.
    """
    received = bloch_vector_from_density_matrix(rho)

    best_label = EIGENSTATE_LABELS[0]
    best_overlap = -np.inf
    for label in EIGENSTATE_LABELS:
        overlap = float(np.dot(received, get_eigenstate(label).bloch_vector))
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = label
    return best_label, best_overlap


# ---------------------------------------------------------------------------
# Single-eigenstate teleportation
# ---------------------------------------------------------------------------

def teleport_eigenstate(
    state: PauliEigenstate,
    noise_type: Optional[str] = None,
    noise_level: float = 0.0,
    shots: int = 1024,
    seed: Optional[int] = None,
) -> Tuple[str, float, Tuple[int, int]]:
    """Teleport one Pauli eigenstate from signer to verifier.

    Parameters
    ----------
    state : PauliEigenstate
        Eigenstate to transmit.  Its Bloch angles drive the teleportation
        circuit's input preparation.
    noise_type : str or None
        Channel noise model (``'bit_flip'``, ``'phase_flip'``,
        ``'depolarizing'``, ``'amplitude_damping'``).  ``None`` or a
        *noise_level* of 0 gives a noiseless channel.
    noise_level : float
        Noise probability in [0, 1].
    shots : int
        Aer shots used to average Bob's density matrix.
    seed : int or None
        Simulator seed.  Defaults to the project ``random_seed``.

    Returns
    -------
    tuple[str, float, tuple[int, int]]
        ``(received_label, fidelity, correction_bits)``.
    """
    # Imported here so that `import qds` does not drag in Aer.
    from qiskit import transpile
    from qiskit_aer import AerSimulator
    from qiskit.quantum_info import state_fidelity

    from quantum.teleportation import (
        build_teleportation_circuit,
        ideal_density_matrix,
    )

    if seed is None:
        seed = ConfigLoader().random_seed

    if noise_type and noise_level > 0.0:
        from quantum.noise import build_noise_model

        backend = AerSimulator(
            method="density_matrix",
            noise_model=build_noise_model(noise_type, noise_level),
        )
    else:
        backend = AerSimulator(method="density_matrix")

    qc = build_teleportation_circuit(state.theta, state.phi)
    compiled = transpile(qc, backend)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = backend.run(compiled, shots=shots, seed_simulator=seed).result()

    bob_dm = result.data()["bob"]
    fidelity = float(
        state_fidelity(bob_dm, ideal_density_matrix(state.theta, state.phi)).real
    )

    # Classical correction bits actually observed on the channel.  Aer
    # returns the Bell-measurement counts; the modal outcome is recorded so
    # the protocol's classical side-channel is represented explicitly.
    try:
        counts: Dict[str, int] = result.get_counts()
        modal = max(counts, key=counts.get)
        bits = modal.replace(" ", "")[-2:]
        correction = (int(bits[-1]), int(bits[-2]))
    except Exception:  # pragma: no cover - counts absent on some backends
        correction = (0, 0)

    label, _ = reconstruct_label(bob_dm)
    return label, fidelity, correction


# ---------------------------------------------------------------------------
# Statevector-level channel transport
# ---------------------------------------------------------------------------

def statevector_to_bloch_angles(statevector: np.ndarray) -> Tuple[float, float]:
    """Convert a single-qubit statevector to Bloch angles ``(theta, phi)``.

    For ``|psi> = a|0> + b|1>``::

        theta = 2 * arccos(|a|)
        phi   = arg(b) - arg(a)

    Parameters
    ----------
    statevector : np.ndarray, shape (2,)
        Normalised single-qubit statevector.

    Returns
    -------
    tuple[float, float]
        ``(theta, phi)`` in radians, with ``phi`` wrapped to [0, 2*pi).
    """
    sv = np.asarray(statevector, dtype=complex).reshape(2)
    norm = float(np.linalg.norm(sv))
    if norm > 0:
        sv = sv / norm

    a, b = sv[0], sv[1]
    theta = 2.0 * float(np.arccos(np.clip(abs(a), 0.0, 1.0)))
    phi = float(np.angle(b) - np.angle(a)) % (2.0 * np.pi)
    return theta, phi


def dominant_pure_state(rho) -> np.ndarray:
    """Return the dominant pure component of a single-qubit density matrix.

    A noisy channel delivers a *mixed* state, but the rest of the QDS
    pipeline is expressed over statevectors.  The eigenvector with the
    largest eigenvalue is the pure state the verifier is most likely to
    collapse onto, so it is the faithful statevector-level stand-in for
    what actually arrived.

    Parameters
    ----------
    rho : DensityMatrix or array-like, shape (2, 2)
        Received density matrix.

    Returns
    -------
    np.ndarray, shape (2,)
        Normalised statevector of the dominant eigenvector.
    """
    mat = np.asarray(getattr(rho, "data", rho), dtype=complex)
    eigvals, eigvecs = np.linalg.eigh(mat)
    principal = eigvecs[:, int(np.argmax(eigvals.real))]
    nrm = float(np.linalg.norm(principal))
    return principal / nrm if nrm > 0 else principal


def sample_pure_state(rho, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """Draw a pure state from the eigen-ensemble of a density matrix.

    A noisy channel delivers a *mixed* state ``rho``, but the QDS pipeline
    is expressed over statevectors.  Writing ``rho`` in its eigenbasis::

        rho = sum_i  lambda_i |e_i><e_i|

    and sampling ``|e_i>`` with probability ``lambda_i`` reproduces every
    measurement statistic of ``rho`` exactly, in expectation.

    This must **not** be replaced by :func:`dominant_pure_state`.  For a
    depolarizing channel the Bloch vector shrinks without rotating, so
    always taking the dominant eigenvector renormalises the state back to
    perfect purity -- silently undoing the channel noise and making channel
    attacks undetectable.  Sampling keeps the degradation observable: as
    fidelity falls, the ensemble increasingly returns the *opposite*
    eigenvector, exactly as a real verifier would see.

    Parameters
    ----------
    rho : DensityMatrix or array-like, shape (2, 2)
        Received density matrix.
    rng : numpy.random.Generator or None
        Generator for the draw.  ``None`` draws fresh randomness.

    Returns
    -------
    np.ndarray, shape (2,)
        A normalised statevector sampled from the ensemble.
    """
    gen = np.random.default_rng() if rng is None else rng
    mat = np.asarray(getattr(rho, "data", rho), dtype=complex)

    eigvals, eigvecs = np.linalg.eigh(mat)
    probs = np.clip(eigvals.real, 0.0, None)
    total = probs.sum()
    probs = probs / total if total > 0 else np.full(len(probs), 1.0 / len(probs))

    chosen = eigvecs[:, int(gen.choice(len(probs), p=probs))]
    nrm = float(np.linalg.norm(chosen))
    return chosen / nrm if nrm > 0 else chosen


def teleport_statevector(
    statevector: np.ndarray,
    noise_type: Optional[str] = None,
    noise_level: float = 0.0,
    shots: int = 512,
    seed: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[np.ndarray, float]:
    """Transport an arbitrary statevector across the real quantum channel.

    Runs the full 3-qubit teleportation circuit on Aer -- Bell pair, Bell
    measurement, classical Pauli correction -- optionally under a noise
    model.  This is what gives a channel-manipulation adversary a genuine
    quantum channel to interfere with, rather than an abstract vector.

    Parameters
    ----------
    statevector : np.ndarray, shape (2,)
        State to transmit.
    noise_type : str or None
        Channel noise model applied to the channel qubits.
    noise_level : float
        Noise probability in [0, 1].
    shots : int
        Aer shots used to average the received density matrix.
    seed : int or None
        Simulator seed.
    rng : numpy.random.Generator or None
        Generator used to sample the received pure state from the mixed
        output (see :func:`sample_pure_state`).

    Returns
    -------
    tuple[np.ndarray, float]
        ``(received_statevector, fidelity)`` where fidelity is measured
        against the ideal transmitted state.
    """
    from qiskit import transpile
    from qiskit_aer import AerSimulator
    from qiskit.quantum_info import state_fidelity

    from quantum.teleportation import (
        build_teleportation_circuit,
        ideal_density_matrix,
    )

    if seed is None:
        seed = ConfigLoader().random_seed

    theta, phi = statevector_to_bloch_angles(statevector)

    if noise_type and noise_level > 0.0:
        from quantum.noise import build_noise_model

        backend = AerSimulator(
            method="density_matrix",
            noise_model=build_noise_model(noise_type, noise_level),
        )
    else:
        backend = AerSimulator(method="density_matrix")

    compiled = transpile(build_teleportation_circuit(theta, phi), backend)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = backend.run(compiled, shots=shots, seed_simulator=seed).result()

    bob_dm = result.data()["bob"]
    fidelity = float(state_fidelity(bob_dm, ideal_density_matrix(theta, phi)).real)
    return sample_pure_state(bob_dm, rng), fidelity


# ---------------------------------------------------------------------------
# Full key-table distribution
# ---------------------------------------------------------------------------

def distribute_public_key(
    private_key: PrivateKey,
    noise_type: Optional[str] = None,
    noise_level: float = 0.0,
    shots: int = 1024,
    seed: Optional[int] = None,
    max_states: Optional[int] = None,
) -> PublicKey:
    """Distribute a signer's public key to the verifier by teleportation.

    Every entry of the signer's secret key table is teleported across the
    quantum channel and reconstructed by the verifier.  The resulting
    :class:`~qds.keygen.PublicKey` therefore holds states the verifier
    *received*, not states it was told about.

    Parameters
    ----------
    private_key : PrivateKey
        The signer's key material.
    noise_type : str or None
        Channel noise model applied during transmission.
    noise_level : float
        Noise probability in [0, 1].
    shots : int
        Aer shots per teleported eigenstate.
    seed : int or None
        Base simulator seed.
    max_states : int or None
        Teleport only the first *max_states* table entries and take the
        remainder directly.  Teleportation is the dominant cost of key
        generation, so experiments that need many key pairs can bound it
        here; ``None`` (default) teleports the whole table.

    Returns
    -------
    PublicKey
        The verifier's reconstructed public key, carrying the measured
        mean channel fidelity in ``distribution_fidelity``.
    """
    result = distribute_public_key_verbose(
        private_key,
        noise_type=noise_type,
        noise_level=noise_level,
        shots=shots,
        seed=seed,
        max_states=max_states,
    )
    return PublicKey(
        key_id=private_key.key_id,
        signer_id=private_key.signer_id,
        fingerprint=private_key.fingerprint(),
        table_size=private_key.table_size,
        distribution_fidelity=result.mean_fidelity,
        _labels=result.received_labels,
    )


def distribute_public_key_verbose(
    private_key: PrivateKey,
    noise_type: Optional[str] = None,
    noise_level: float = 0.0,
    shots: int = 1024,
    seed: Optional[int] = None,
    max_states: Optional[int] = None,
) -> KeyDistributionResult:
    """Distribute a public key and return the full per-state audit trail.

    Same protocol as :func:`distribute_public_key`, but returns a
    :class:`KeyDistributionResult` with per-eigenstate fidelities and
    correction bits -- used by
    ``experiments/phase3_qds_validation.py`` to validate the teleportation
    step that the live scheme actually runs.
    """
    if seed is None:
        seed = ConfigLoader().random_seed

    sent = private_key.key_table()
    limit = len(sent) if max_states is None else min(max_states, len(sent))

    received: List[str] = []
    fidelities: List[float] = []
    corrections: List[Tuple[int, int]] = []

    for i, label in enumerate(sent):
        if i >= limit:
            # Beyond the teleportation budget: the remaining table entries
            # are taken over a noiseless ideal channel.
            received.append(label)
            fidelities.append(1.0)
            corrections.append((0, 0))
            continue

        got, fid, bits = teleport_eigenstate(
            get_eigenstate(label),
            noise_type=noise_type,
            noise_level=noise_level,
            shots=shots,
            seed=seed + i,
        )
        received.append(got)
        fidelities.append(fid)
        corrections.append(bits)

    errors = sum(1 for a, b in zip(sent, received) if a != b)
    mean_fid = float(np.mean(fidelities)) if fidelities else 1.0

    logger.info(
        "Distributed public key %s...: n=%d teleported=%d mean_F=%.6f "
        "errors=%d noise=%s@%.3f",
        private_key.key_id[:8], len(sent), limit, mean_fid,
        errors, noise_type, noise_level,
    )

    return KeyDistributionResult(
        key_id=private_key.key_id,
        table_size=len(sent),
        sent_labels=tuple(sent),
        received_labels=tuple(received),
        fidelities=fidelities,
        mean_fidelity=mean_fid,
        correction_bits=corrections,
        reconstruction_errors=errors,
        noise_type=noise_type,
        noise_level=noise_level,
    )
