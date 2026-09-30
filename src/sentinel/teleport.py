"""
sentinel/teleport.py
====================
Exact teleportation superoperators and a batched per-qubit sampler.

The standard three-qubit circuit (identical to v1's
``quantum.teleportation.build_teleportation_circuit``)::

    q0  input (signer)      ──●── H ── M ──> m0
    q1  signer's Bell half  ──X─────── M ──> m1
    q2  verifier's half     ─[noise]──────── X^c1 ── Z^c0 ──> output

Teleportation is linear in the input state. So instead of simulating each
qubit with a circuit, we compute once per channel configuration the four
outcome-conditioned maps

    E_k(rho) = Tr_{q0 q1} [ Pi_k U (rho (x) rho_AB) U^dagger Pi_k ],   k = 2*m0 + m1

as 4x4 Pauli transfer matrices ``R_k`` (unnormalised; ``Tr E_k(rho)`` is the
probability of outcome k). The computation is exact linear algebra on 8x8
matrices, validated against Qiskit Aer in
:mod:`sentinel.analysis.validation`.

For the six-state alphabet everything the sampler needs collapses into
lookup tables:

    p_k[label, k]                  probability of Bell outcome k
    bloch[label, k, c]             receiver Bloch vector after correction c
    p_plus[label, k, c, basis]     probability of outcome +1 in ``basis``

so each teleported qubit costs a handful of vectorised table lookups.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Sequence

import numpy as np

from sentinel.channels import Channel, compose, spec_key
from sentinel.linalg import I2, H, PAULIS, X
from sentinel.states import FRAME_PTM, N_LABELS, V4

__all__ = [
    "TeleportationModel",
    "build_model",
    "get_model",
    "sample_teleportations",
    "PHI_PLUS",
]

#: |Phi+> as a density matrix on (q1, q2).
_phi = np.array([1, 0, 0, 1], dtype=complex) / np.sqrt(2.0)
PHI_PLUS: np.ndarray = np.outer(_phi, _phi.conj())

_P0 = np.array([[1, 0], [0, 0]], dtype=complex)
_P1 = np.array([[0, 0], [0, 1]], dtype=complex)


def _kron(*ops: np.ndarray) -> np.ndarray:
    out = ops[0]
    for op in ops[1:]:
        out = np.kron(out, op)
    return out


#: Alice's Bell-basis rotation: CX(q0 -> q1), then H(q0).
_CX01 = _kron(_P0, I2, I2) + _kron(_P1, X, I2)
_U = _kron(H, I2, I2) @ _CX01


def _noisy_bell_pair(channel_B: Channel, channel_A: Channel | None) -> np.ndarray:
    """rho_AB = (N_A (x) N_B)(|Phi+><Phi+|)."""
    rho = PHI_PLUS.copy()
    out = np.zeros((4, 4), dtype=complex)
    for K in channel_B.kraus:
        full = np.kron(I2, K)
        out += full @ rho @ full.conj().T
    rho = out
    if channel_A is not None:
        out = np.zeros((4, 4), dtype=complex)
        for K in channel_A.kraus:
            full = np.kron(K, I2)
            out += full @ rho @ full.conj().T
        rho = out
    return rho


@dataclass(frozen=True, eq=False)
class TeleportationModel:
    """Exact teleportation maps for one channel configuration.

    Attributes
    ----------
    R : ndarray, shape (4, 4, 4)
        ``R[k]`` is the unnormalised PTM of outcome ``k`` (before correction).
    p_k : ndarray, shape (6, 4)
        Outcome probabilities per input label.
    bloch : ndarray, shape (6, 4, 4, 3)
        Receiver Bloch vector for (label, sent k, received c).
    p_plus : ndarray, shape (6, 4, 4, 3)
        Probability of measuring +1 in basis 0/1/2 (X/Y/Z).
    rho_ab : ndarray, shape (4, 4)
        The shared (noisy) Bell pair.
    key : str
        Canonical cache key of the configuration.
    """

    R: np.ndarray
    p_k: np.ndarray
    bloch: np.ndarray
    p_plus: np.ndarray
    rho_ab: np.ndarray
    channel_B: Channel
    channel_A: Channel | None
    key: str

    # ------------------------------------------------------------------
    def teleport_bloch(self, r: Sequence[float]) -> list[dict]:
        """Per-outcome results for an arbitrary input Bloch vector (|r| <= 1)."""
        v = np.concatenate([[1.0], np.asarray(r, dtype=float)])
        out = []
        for k in range(4):
            raw = self.R[k] @ v
            p = float(raw[0])
            if p <= 1e-15:
                out.append({"k": k, "bits": [k >> 1, k & 1], "prob": 0.0, "bloch_pre": [0.0, 0.0, 0.0], "bloch_post": [0.0, 0.0, 0.0]})
                continue
            pre = raw[1:] / p
            post = (FRAME_PTM[k] @ raw)[1:] / p
            out.append({"k": k, "bits": [k >> 1, k & 1], "prob": p, "bloch_pre": pre.tolist(), "bloch_post": post.tolist()})
        return out

    def averaged_ptm(self) -> np.ndarray:
        """PTM of the full protocol averaged over outcomes (correct frames)."""
        return sum(FRAME_PTM[k] @ self.R[k] for k in range(4))

    def conditional_ptm(self, k: int, c: int | None = None) -> np.ndarray:
        """Normalised-per-outcome PTM for sent frame ``k`` and correction ``c``.

        Valid when ``Tr E_k(rho) = 1/4`` for every input (noise on the
        receiver only), which is the case for all link models used here.
        """
        c = k if c is None else c
        return 4.0 * (FRAME_PTM[c] @ self.R[k])


def build_model(channel_B: Channel, channel_A: Channel | None = None, key: str = "") -> TeleportationModel:
    """Compute the teleportation maps for the given channels (uncached)."""
    rho_ab = _noisy_bell_pair(channel_B, channel_A)
    R = np.zeros((4, 4, 4))
    for j in range(4):
        psi = _U @ np.kron(PAULIS[j], rho_ab) @ _U.conj().T
        t = psi.reshape(2, 2, 2, 2, 2, 2)  # (a0 a1 a2, b0 b1 b2)
        for m0 in range(2):
            for m1 in range(2):
                E = t[m0, m1, :, m0, m1, :]  # Tr_{01}(Pi_k psi Pi_k)
                k = 2 * m0 + m1
                R[k, :, j] = 0.5 * np.real(np.einsum("iab,ba->i", PAULIS, E))

    p_k = np.einsum("kij,lj->lk", R[:, :1, :], V4)  # (6,4): (R_k v_l)_0
    p_k = np.clip(p_k, 0.0, 1.0)

    bloch = np.zeros((N_LABELS, 4, 4, 3))
    for k in range(4):
        raw = V4 @ R[k].T  # (6,4) = R_k v_l
        for c in range(4):
            corr = raw @ FRAME_PTM[c].T  # P_c R_k v_l
            denom = np.where(p_k[:, k] > 1e-15, p_k[:, k], 1.0)
            bloch[:, k, c, :] = corr[:, 1:] / denom[:, None]
    p_plus = np.clip((1.0 + bloch) / 2.0, 0.0, 1.0)
    return TeleportationModel(R=R, p_k=p_k, bloch=bloch, p_plus=p_plus, rho_ab=rho_ab,
                              channel_B=channel_B, channel_A=channel_A, key=key)


@lru_cache(maxsize=256)
def _cached(key_b: str, key_a: str) -> TeleportationModel:
    import json

    specs_b = json.loads(key_b)
    specs_a = json.loads(key_a)
    ch_b = compose(specs_b)
    ch_a = compose(specs_a) if specs_a else None
    return build_model(ch_b, ch_a, key=f"{key_b}|{key_a}")


def get_model(channel_B_specs: Sequence[Mapping] | None = None,
              channel_A_specs: Sequence[Mapping] | None = None) -> TeleportationModel:
    """Cached model for channel spec lists on the receiver (B) and signer (A) halves."""
    return _cached(spec_key(channel_B_specs), spec_key(channel_A_specs))


_CHUNK = 1 << 20


def sample_teleportations(
    model: TeleportationModel,
    labels: np.ndarray,
    bases: np.ndarray,
    rng: np.random.Generator,
    flip_c0: np.ndarray | None = None,
    flip_c1: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Teleport ``len(labels)`` qubits and measure each once.

    Parameters
    ----------
    labels : uint8[N]
        Input six-state labels.
    bases : uint8[N]
        Receiver measurement basis per qubit (0=X, 1=Y, 2=Z).
    rng : numpy Generator
        Physics randomness (Bell outcomes and measurement outcomes).
    flip_c0, flip_c1 : bool[N] or None
        Classical tampering of the correction bits in transit.

    Returns
    -------
    (k, c, o) : uint8 arrays
        Sent Bell outcome, received correction bits, measurement outcome
        (0 = eigenvalue +1).
    """
    labels = np.asarray(labels, dtype=np.intp)
    bases = np.asarray(bases, dtype=np.intp)
    n = labels.shape[0]
    k_out = np.empty(n, dtype=np.uint8)
    c_out = np.empty(n, dtype=np.uint8)
    o_out = np.empty(n, dtype=np.uint8)
    cp = np.cumsum(model.p_k, axis=1)
    cp0, cp1, cp2 = cp[:, 0].copy(), cp[:, 1].copy(), cp[:, 2].copy()
    pp_flat = model.p_plus.ravel()
    for s in range(0, n, _CHUNK):
        e = min(n, s + _CHUNK)
        lab = labels[s:e]
        u = rng.random(e - s)
        k = (u > np.take(cp0, lab)).astype(np.intp)
        k += u > np.take(cp1, lab)
        k += u > np.take(cp2, lab)
        c = k.copy()
        if flip_c0 is not None:
            c ^= np.asarray(flip_c0[s:e], dtype=np.intp) << 1
        if flip_c1 is not None:
            c ^= np.asarray(flip_c1[s:e], dtype=np.intp)
        flat = ((lab * 4 + k) * 4 + c) * 3 + bases[s:e]
        pp = np.take(pp_flat, flat)
        o_out[s:e] = rng.random(e - s) >= pp
        k_out[s:e] = k
        c_out[s:e] = c
    return k_out, c_out, o_out
