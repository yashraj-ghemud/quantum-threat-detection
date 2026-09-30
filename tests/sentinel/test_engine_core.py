"""Engine core: states, linear algebra, channels, teleportation, Bell statistics, tomography."""

from __future__ import annotations

import math

import numpy as np
import pytest

from sentinel.bell import bell_state, estimate_bell, predicted, sample_bell_test, setting_probs
from sentinel.channels import CHANNEL_TYPES, ChannelSpecError, channel_from_spec, compose, spec_key
from sentinel.linalg import (
    X, Y, Z, H, S, is_cptp, kraus_to_ptm, polar, rodrigues, rotation_axis_angle, su2_rotation,
    unitary_ptm, partial_trace, bloch_to_rho, rho_to_bloch,
)
from sentinel.rng import RandomSource
from sentinel.states import BASIS_OF, BIT_OF, BLOCH, FRAME_PERM, FRAME_PTM, FRAME_SIGNS, label_from
from sentinel.teleport import get_model, sample_teleportations
from sentinel.tomography import aggregate_pe, detwirl, effective, frame_matrix, qber_counts

GRID = {
    "depolarizing": [{"p": p} for p in (0, 0.1, 0.5, 1.0)],
    "dephasing": [{"p": p, "axis": a} for p in (0, 0.3, 1.0) for a in "xyz"],
    "bit_flip": [{"p": 0.2}], "phase_flip": [{"p": 0.2}], "bit_phase_flip": [{"p": 0.2}],
    "amplitude_damping": [{"gamma": g} for g in (0, 0.25, 1.0)],
    "phase_damping": [{"lam": l} for l in (0, 0.5, 1.0)],
    "rotation": [{"axis": a, "theta": t} for a in ("x", [1, 1, 0], [0.2, -0.4, 1]) for t in (-1.0, 0.3, 3.0)],
    "pauli": [{"px": 0.1, "py": 0.2, "pz": 0.05}, {"px": 0.0, "py": 0.0, "pz": 1.0}],
    "measure_prepare": [{"basis": b} for b in "xyz"],
    "identity": [{}],
}


# --------------------------------------------------------------------------- states
class TestStates:
    def test_labels_and_bloch(self):
        for l in range(6):
            assert label_from(BASIS_OF[l], BIT_OF[l]) == l
            assert np.linalg.norm(BLOCH[l]) == pytest.approx(1.0)
            assert BLOCH[l][BASIS_OF[l]] == (1.0 if BIT_OF[l] == 0 else -1.0)

    def test_frame_perm_matches_signs(self):
        for k in range(4):
            for l in range(6):
                assert np.allclose(BLOCH[FRAME_PERM[k, l]], FRAME_SIGNS[k] * BLOCH[l])

    def test_frame_ptm_is_pauli_conjugation(self):
        paulis = [np.eye(2), X, Z, X @ Z]  # sigma_k = X^m1 Z^m0 with k = 2*m0 + m1
        order = [0, 1, 2, 3]
        for k, P in zip(order, paulis):
            assert np.allclose(unitary_ptm(P), FRAME_PTM[k])


# --------------------------------------------------------------------------- linalg
class TestLinalg:
    def test_rodrigues_matches_su2_conjugation(self):
        for axis, theta in (([0, 0, 1], 0.7), ([1, 2, -1], -1.3), ([1, 0, 0], math.pi)):
            R = unitary_ptm(su2_rotation(axis, theta))
            assert np.allclose(R[1:, 1:], rodrigues(axis, theta), atol=1e-12)

    def test_polar_and_axis_angle(self):
        U0 = rodrigues([1, 1, 1], 0.9)
        P0 = np.diag([0.9, 0.6, 0.3])
        U, P = polar(U0 @ P0)
        assert np.allclose(U, U0) and np.allclose(U @ P, U0 @ P0)
        axis, theta = rotation_axis_angle(U)
        assert theta == pytest.approx(0.9)
        assert np.allclose(axis, np.array([1, 1, 1]) / math.sqrt(3))

    def test_gates_on_bloch(self):
        assert np.allclose(unitary_ptm(H)[1:, 1:] @ [0, 0, 1], [1, 0, 0])
        assert np.allclose(unitary_ptm(S)[1:, 1:] @ [1, 0, 0], [0, 1, 0])

    def test_partial_trace_bell(self):
        phi = np.array([1, 0, 0, 1]) / math.sqrt(2)
        rho = np.outer(phi, phi)
        assert np.allclose(partial_trace(rho, [0], [2, 2]), np.eye(2) / 2)

    def test_bloch_roundtrip(self):
        r = np.array([0.3, -0.4, 0.5])
        assert np.allclose(rho_to_bloch(bloch_to_rho(r)), r)


# --------------------------------------------------------------------------- channels
class TestChannels:
    @pytest.mark.parametrize("name", list(GRID))
    def test_cptp_over_grid(self, name):
        for params in GRID[name]:
            ch = channel_from_spec({"type": name, **params})
            ok, info = is_cptp(ch.ptm)
            assert ok, (name, params, info)

    def test_closed_forms(self):
        p = 0.3
        M, c = channel_from_spec({"type": "depolarizing", "p": p}).affine
        assert np.allclose(M, (1 - p) * np.eye(3)) and np.allclose(c, 0)
        g = 0.4
        M, c = channel_from_spec({"type": "amplitude_damping", "gamma": g}).affine
        assert np.allclose(M, np.diag([math.sqrt(1 - g), math.sqrt(1 - g), 1 - g]))
        assert np.allclose(c, [0, 0, g])
        M, _ = channel_from_spec({"type": "dephasing", "p": 0.25, "axis": "x"}).affine
        assert np.allclose(M, np.diag([1, 0.5, 0.5]))
        M, _ = channel_from_spec({"type": "measure_prepare", "basis": "y"}).affine
        assert np.allclose(M, np.diag([0, 1, 0]))
        M, _ = channel_from_spec({"type": "pauli", "px": 0.1, "py": 0.2, "pz": 0.05}).affine
        assert np.allclose(M, np.diag([1 - 2 * 0.25, 1 - 2 * 0.15, 1 - 2 * 0.3]))

    def test_composition_order(self):
        a = {"type": "amplitude_damping", "gamma": 0.3}
        b = {"type": "rotation", "axis": "x", "theta": 1.0}
        ab = compose([a, b]).ptm
        assert np.allclose(ab, channel_from_spec(b).ptm @ channel_from_spec(a).ptm)
        assert not np.allclose(ab, compose([b, a]).ptm)

    def test_validation(self):
        with pytest.raises(ChannelSpecError):
            channel_from_spec({"type": "depolarizing", "p": 1.5})
        with pytest.raises(ChannelSpecError):
            channel_from_spec({"type": "warp_drive"})
        with pytest.raises(ChannelSpecError):
            channel_from_spec({"type": "pauli", "px": 0.6, "py": 0.6})
        with pytest.raises(ChannelSpecError):
            channel_from_spec({"type": "rotation", "axis": [0, 0, 0], "theta": 1})

    def test_spec_key_canonical(self):
        assert spec_key([{"p": 0.1, "type": "depolarizing"}]) == spec_key([{"type": "depolarizing", "p": 0.1}])
        assert set(CHANNEL_TYPES) >= set(GRID)


# --------------------------------------------------------------------------- teleport
class TestTeleport:
    def test_ideal_is_exact(self):
        m = get_model([])
        assert np.allclose(m.p_k, 0.25, atol=1e-12)
        for l in range(6):
            for k in range(4):
                assert np.allclose(m.bloch[l, k, k], BLOCH[l], atol=1e-12)
        assert np.allclose(m.averaged_ptm(), np.eye(4))

    @pytest.mark.parametrize("specs", [
        [{"type": "depolarizing", "p": 0.2}],
        [{"type": "amplitude_damping", "gamma": 0.35}],
        [{"type": "rotation", "axis": [1, 0, 1], "theta": 0.8}],
        [{"type": "phase_damping", "lam": 0.3}, {"type": "bit_flip", "p": 0.1}],
    ])
    def test_conditional_maps_are_frame_conjugations(self, specs):
        m, ch = get_model(specs), compose(specs)
        assert np.allclose(m.p_k, 0.25, atol=1e-12)
        for k in range(4):
            assert np.allclose(m.conditional_ptm(k), FRAME_PTM[k] @ ch.ptm @ FRAME_PTM[k], atol=1e-12)

    def test_pauli_channels_survive_averaging_but_ad_is_twirled(self):
        dep = [{"type": "depolarizing", "p": 0.2}]
        assert np.allclose(get_model(dep).averaged_ptm(), compose(dep).ptm)
        ad = [{"type": "amplitude_damping", "gamma": 0.3}]
        avg = get_model(ad).averaged_ptm()
        assert np.allclose(avg[1:, 0], 0)  # translation erased by the twirl
        assert not np.allclose(avg, compose(ad).ptm)

    def test_frame_tamper_is_extra_pauli(self):
        m = get_model([])
        # Received c = k XOR 1 (m1 flipped) applies an extra X.
        for l in range(6):
            for k in range(4):
                assert np.allclose(m.bloch[l, k, k ^ 1], FRAME_SIGNS[1] * BLOCH[l])

    def test_sampler_statistics(self):
        rs = RandomSource(3)
        n = 200_000
        m = get_model([{"type": "depolarizing", "p": 0.1}])
        labels, bases = rs.labels(n), rs.bases(n)
        k, c, o = sample_teleportations(m, labels, bases, rs.physics)
        assert np.array_equal(k, c)
        assert np.all(np.bincount(k, minlength=4) > 0.24 * n)
        pe = aggregate_pe(labels, k, c, bases, o)
        q = qber_counts(pe)["rate"]
        assert q == pytest.approx(0.05, abs=0.004)  # depolarizing error = p/2


# --------------------------------------------------------------------------- bell
class TestBell:
    def test_ideal_chsh(self):
        pred = predicted(bell_state(None))
        assert pred["S"] == pytest.approx(2 * math.sqrt(2), abs=1e-12)
        assert pred["F"] == pytest.approx(1.0)

    def test_depolarized_closed_forms(self):
        p = 0.2
        pred = predicted(bell_state(channel_from_spec({"type": "depolarizing", "p": p})))
        assert pred["S"] == pytest.approx(2 * math.sqrt(2) * (1 - p), abs=1e-12)
        assert pred["F"] == pytest.approx(1 - 3 * p / 4, abs=1e-12)
        assert pred["qber"] == pytest.approx(p / 2, abs=1e-12)

    def test_fidelity_is_entanglement_fidelity(self):
        ch = compose([{"type": "amplitude_damping", "gamma": 0.3}, {"type": "rotation", "axis": "y", "theta": 0.4}])
        M, _ = ch.affine
        assert predicted(bell_state(ch))["F"] == pytest.approx((1 + np.trace(M)) / 4, abs=1e-12)

    def test_measure_prepare_is_local(self):
        pred = predicted(bell_state(channel_from_spec({"type": "measure_prepare", "basis": "z"})))
        assert pred["S"] <= 2.0 + 1e-12

    def test_sampled_estimate_covers_truth(self):
        rs = RandomSource(5)
        ch = channel_from_spec({"type": "depolarizing", "p": 0.05})
        rho = bell_state(ch)
        est = estimate_bell(sample_bell_test(setting_probs(rho), 4000, rs.physics), delta=1e-5)
        truth = predicted(rho)
        assert est.S_lcb <= truth["S"] <= est.S + 5 * est.S_se
        assert abs(est.S - truth["S"]) < 5 * est.S_se
        assert est.S_lcb > 2.0
        assert abs(est.predicted_error["x"]["rate"] - truth["error"]["x"]) < 0.01


# --------------------------------------------------------------------------- tomography
class TestTomography:
    @pytest.mark.parametrize("specs", [
        [{"type": "amplitude_damping", "gamma": 0.3}],
        [{"type": "rotation", "axis": [0, 0, 1], "theta": 0.6}],
        [{"type": "dephasing", "p": 0.2, "axis": "y"}],
    ])
    def test_detwirl_recovers_channel(self, specs):
        rs = RandomSource(11)
        n = 300_000
        m, ch = get_model(specs), compose(specs)
        labels, bases = rs.labels(n), rs.bases(n)
        k, c, o = sample_teleportations(m, labels, bases, rs.physics)
        est = detwirl(aggregate_pe(labels, k, c, bases, o))
        M, cc = ch.affine
        assert np.all(np.abs(est.M - M) < 6 * est.M_se + 1e-3)
        assert np.all(np.abs(est.c - cc) < 6 * est.c_se + 1e-3)

    def test_effective_hides_translation(self):
        rs = RandomSource(12)
        n = 300_000
        m = get_model([{"type": "amplitude_damping", "gamma": 0.4}])
        labels, bases = rs.labels(n), rs.bases(n)
        k, c, o = sample_teleportations(m, labels, bases, rs.physics)
        pe = aggregate_pe(labels, k, c, bases, o)
        assert abs(effective(pe).c[2]) < 0.02
        assert detwirl(pe).c[2] == pytest.approx(0.4, abs=0.02)

    def test_frame_tamper_isolated(self):
        rs = RandomSource(13)
        n = 200_000
        m = get_model([])
        labels, bases = rs.labels(n), rs.bases(n)
        flip = rs.uniform(n) < 0.25
        k, c, o = sample_teleportations(m, labels, bases, rs.physics, flip_c0=flip)
        pe = aggregate_pe(labels, k, c, bases, o)
        fm = frame_matrix(pe)
        assert fm.sum() - np.trace(fm) == pytest.approx(0.25 * n, rel=0.03)
        assert np.allclose(detwirl(pe).M, np.eye(3), atol=0.02)          # quantum channel clean
        assert effective(pe).M[0, 0] == pytest.approx(0.5, abs=0.03)      # Z errors hit X states


# --------------------------------------------------------------------------- rng
class TestRandomSource:
    def test_labels_uniform(self):
        from scipy.stats import chisquare
        counts = np.bincount(RandomSource().labels(60_000), minlength=6)
        assert chisquare(counts).pvalue > 1e-6

    def test_seeded_reproducible(self):
        a, b = RandomSource(42), RandomSource(42)
        assert np.array_equal(a.labels(100), b.labels(100))
        assert np.array_equal(a.uniform(10), b.uniform(10))

    def test_choose_mask(self):
        mask = RandomSource(1).choose_mask(100, 37)
        assert mask.sum() == 37
