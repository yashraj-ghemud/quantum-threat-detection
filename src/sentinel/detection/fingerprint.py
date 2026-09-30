"""
sentinel/detection/fingerprint.py
=================================
Channel-shape classifier on de-twirled Bloch maps.

Given the baseline map ``(M0, c0)`` and the current map ``(M, c)``, the
attack-induced map is ``M_A = M M0^-1``, ``c_A = c - M_A c0`` (attack after
baseline). Its shape is read off with a polar decomposition ``M_A = U P``:

1. translation ``|c_A|`` significant       -> non-unital (amplitude damping)
2. rotation angle of ``U`` significant     -> coherent rotation (axis, angle)
3. singular values of ``P``:
   - all ~1                                -> no channel-level anomaly
   - all equal and < 1                     -> isotropic (depolarizing class)
   - one ~preserved, two equal and smaller -> dephasing along that axis
   - otherwise                             -> general Pauli channel

Every threshold is ``max(absolute floor, k * sigma)`` where sigma is the
sampling noise of the estimates, so the rules adapt to sample size.

Physically equivalent explanations are reported as *alternatives*: a
depolarizing channel and random-basis intercept-resend on a fraction of pairs
are the same channel, and no measurement can tell them apart.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from sentinel.linalg import polar, rotation_axis_angle
from sentinel.tomography import ChannelEstimate

__all__ = ["Fingerprint", "classify_channel"]

_AXES = {"x": np.array([1.0, 0, 0]), "y": np.array([0, 1.0, 0]), "z": np.array([0, 0, 1.0])}


@dataclass
class Fingerprint:
    shape: str                   # none | isotropic | dephasing | amplitude_damping | non_unital | coherent_rotation | general_pauli
    summary: str
    params: dict = field(default_factory=dict)
    axis: list | None = None
    alternatives: list = field(default_factory=list)
    attack_map: dict = field(default_factory=dict)
    noise_sigma: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def _axis_name(v: np.ndarray) -> str:
    v = np.asarray(v, float)
    best = max(_AXES, key=lambda k: abs(float(np.dot(_AXES[k], v))))
    ang = math.degrees(math.acos(min(1.0, abs(float(np.dot(_AXES[best], v)) / (np.linalg.norm(v) or 1)))))
    return best if ang < 20 else "oblique"


def classify_channel(baseline: ChannelEstimate, current: ChannelEstimate) -> Fingerprint:
    M0, c0 = np.asarray(baseline.M), np.asarray(baseline.c)
    M, c = np.asarray(current.M), np.asarray(current.c)
    sigma = float(math.hypot(np.median(current.M_se), np.median(baseline.M_se)))
    try:
        M_A = M @ np.linalg.inv(M0)
    except np.linalg.LinAlgError:
        M_A = M.copy()
    c_A = c - M_A @ c0
    U, P = polar(M_A)
    axis, theta = rotation_axis_angle(U)
    evals, evecs = np.linalg.eigh((P + P.T) / 2)
    order = np.argsort(evals)[::-1]
    lam = evals[order]
    vecs = evecs[:, order]
    attack_map = {"M": M_A.tolist(), "c": c_A.tolist(), "singular_values": lam.tolist(),
                  "rotation_axis": axis.tolist(), "rotation_deg": math.degrees(theta)}

    t_norm = float(np.linalg.norm(c_A))
    t_thresh = max(0.03, 4 * sigma)
    # The rotation part of a polar decomposition is undefined along directions the map
    # crushes to ~0 (full dephasing, intercept-resend). Measure rotation only on
    # well-conditioned singular directions, with a threshold scaled by relative noise.
    W, sv, Vt = np.linalg.svd(M_A)
    good = sv > 0.3
    if good.all():
        rot_angle = theta
        rot_thresh = max(math.radians(4.0), 4 * sigma / max(float(sv.min()), 1e-6))
    elif good.any():
        dots = np.abs(np.einsum("ij,ji->i", W.T, Vt.T))  # |u_i . v_i| per singular direction
        rot_angle = float(max(math.acos(min(1.0, d)) for d, g in zip(dots, good) if g))
        rot_thresh = max(math.radians(6.0), 4 * sigma / max(float(sv[good].min()), 1e-6))
    else:
        rot_angle, rot_thresh = 0.0, math.inf
    unit_thresh = max(0.03, 4 * sigma)
    spread = max(0.05, 4 * sigma)

    # 1. Non-unital
    if t_norm > t_thresh:
        direction = c_A / t_norm
        gamma = abs(float(c_A[2]))
        cos_z = abs(float(direction[2]))
        pattern_ok = (abs(lam[2] - (1 - gamma)) < max(0.04, 5 * sigma)
                      and abs(lam[0] - math.sqrt(max(0.0, 1 - gamma))) < max(0.04, 5 * sigma))
        if cos_z > math.cos(math.radians(25)) and pattern_ok:
            toward = "|0>" if c_A[2] > 0 else "|1>"
            return Fingerprint(
                "amplitude_damping",
                f"Non-unital drift of {t_norm:.3f} toward {toward} with the matching contraction "
                f"(√(1−γ), √(1−γ), 1−γ): amplitude damping with γ ≈ {gamma:.3f}. Hidden by the Pauli twirl; "
                f"visible only after de-twirling.",
                {"gamma": gamma, "translation": t_norm}, direction.tolist(),
                ["energy-draining (lossy) tampering of the receiver's Bell half",
                 "a detector/memory relaxation fault at the receiver"], attack_map, sigma)
        return Fingerprint(
            "non_unital", f"Non-unital drift of {t_norm:.3f} along {np.round(direction, 2).tolist()}.",
            {"translation": t_norm}, direction.tolist(), ["state-dependent (non-unital) tampering"], attack_map, sigma)

    # 2. Coherent rotation
    if rot_angle > rot_thresh:
        name = _axis_name(axis)
        return Fingerprint(
            "coherent_rotation",
            f"Coherent rotation of {math.degrees(theta):.1f}° about the {name} axis with purity preserved "
            f"(singular values {np.round(lam, 3).tolist()}). A twirled view shows only dephasing; de-twirling "
            f"exposes the unitary.",
            {"theta_deg": math.degrees(theta), "theta_rad": theta, "axis_name": name}, axis.tolist(),
            ["a deliberate unitary on the receiver's half (e.g. a polarization rotator)",
             "an uncompensated reference-frame drift"], attack_map, sigma)

    # 3. Shrink pattern. The mean contraction has a smaller standard error (sigma / sqrt 3)
    # than any single singular value, so it is tested first.
    mean_shrink = float(1 - np.mean(lam))
    if mean_shrink < max(0.02, 3 * sigma / math.sqrt(3)) and lam[2] >= 1 - unit_thresh:
        return Fingerprint("none", "No channel-level deviation from the baseline beyond sampling noise.",
                           {}, None, [], attack_map, sigma)
    if lam[0] - lam[2] < spread:
        p = float(1 - np.mean(lam))
        f = min(1.0, 1.5 * p)
        return Fingerprint(
            "isotropic",
            f"Isotropic contraction λ ≈ {np.mean(lam):.3f}: depolarizing noise p ≈ {p:.3f} or random-basis "
            f"intercept–resend on ≈ {100 * f:.0f}% of pairs. These are the same channel; no measurement can "
            f"separate them.",
            {"p": p, "intercept_fraction": f, "lambda": float(np.mean(lam))}, None,
            [f"depolarizing noise p ≈ {p:.3f}", f"random-basis intercept–resend on ≈ {100 * f:.0f}% of pairs"],
            attack_map, sigma)
    if lam[0] - lam[1] > spread and lam[1] - lam[2] < spread:
        a = vecs[:, 0]
        name = _axis_name(a)
        p = float((1 - (lam[1] + lam[2]) / 2) / 2)
        f = min(1.0, 2 * p)
        return Fingerprint(
            "dephasing",
            f"Contraction onto the {name} axis (preserved λ = {lam[0]:.3f}, others ≈ {(lam[1] + lam[2]) / 2:.3f}): "
            f"dephasing along {name} with p ≈ {p:.3f}, equivalently {name}-basis intercept–resend on ≈ "
            f"{100 * f:.0f}% of pairs.",
            {"p": p, "axis_name": name, "intercept_fraction": f}, a.tolist(),
            [f"dephasing along {name} (p ≈ {p:.3f})", f"Pauli-σ_{name} errors with probability {p:.3f}",
             f"{name}-basis measure-and-resend on ≈ {100 * f:.0f}% of pairs"], attack_map, sigma)
    l1, l2, l3 = (float(x) for x in lam)
    probs = {"p_I": (1 + l1 + l2 + l3) / 4, "p_1": (1 + l1 - l2 - l3) / 4,
             "p_2": (1 - l1 + l2 - l3) / 4, "p_3": (1 - l1 - l2 + l3) / 4}
    return Fingerprint("general_pauli",
                       f"Anisotropic contraction {np.round(lam, 3).tolist()}: a general Pauli channel "
                       f"(principal-frame error probabilities {', '.join(f'{k}={v:.3f}' for k, v in probs.items())}).",
                       probs, None, ["a mixture of dephasing channels", "partial intercept–resend in several bases"],
                       attack_map, sigma)
