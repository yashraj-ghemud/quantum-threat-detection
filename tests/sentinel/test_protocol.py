"""TQDS protocol: params, encoding, distribution, symmetrization, signing, verification, design, guard."""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from sentinel.protocol.distribution import distribute
from sentinel.protocol.encoding import Envelope, MessageTooLong, digest_hex, encode_bits
from sentinel.protocol.guard import MemoryGuardStore, check_guard
from sentinel.protocol.keys import KeyBundle, KeyReuseError
from sentinel.protocol.link import LinkPlan, wc_keys, wc_tag
from sentinel.protocol.params import ParamsError, params_for
from sentinel.protocol.signing import sign
from sentinel.protocol.thresholds import design, repudiation_bound
from sentinel.protocol.verification import verify
from sentinel.rng import RandomSource
from sentinel.sequential import Sprt
from sentinel.stats import hypergeom_split_tail


def _env(bundle_id, msg="Pay 250 QVC to Bob", seq=1, enc="sha256", ts=None, nonce="ab" * 16):
    return Envelope("g-alice", "alice", ("bob", "charlie"), bundle_id, seq, ts or time.time(), nonce, msg, enc)


def _sprt(d):
    return Sprt(d.sprt["p0"], d.sprt["p1"], d.sprt["alpha"], d.sprt["beta"])


@pytest.fixture(scope="module")
def honest(request):
    from tests.sentinel.conftest import BASE_BOB, BASE_CHARLIE
    from sentinel.protocol.link import LinkSpec
    links = {"bob": LinkSpec("alice-bob", "alice", "bob", BASE_BOB, 22),
             "charlie": LinkSpec("alice-charlie", "alice", "charlie", BASE_CHARLIE, 35)}
    p = params_for("analysis")
    return distribute("g-alice", "alice", ("bob", "charlie"), links, p, RandomSource(101)), links


class TestParams:
    def test_presets_valid(self):
        for name in ("demo", "standard", "high", "analysis"):
            p = params_for(name)
            assert p.L_dist >= p.L and p.n_pe == p.L_dist - p.L
        assert params_for("standard").qubits() == 256 * 2 * params_for("standard").L_dist * 2

    def test_rejects_bad(self):
        with pytest.raises(ParamsError):
            params_for("standard", digest_bits=32)
        with pytest.raises(ParamsError):
            params_for("standard", L=10)
        with pytest.raises(ParamsError):
            params_for("nope")


class TestEncoding:
    def test_sha256_binds_metadata(self):
        a = encode_bits(_env("b1"), 256)
        assert a.shape == (256,) and set(np.unique(a)) <= {0, 1}
        assert not np.array_equal(a, encode_bits(_env("b1", nonce="cd" * 16), 256))
        assert not np.array_equal(a, encode_bits(_env("b1", seq=2), 256))

    def test_raw_mode(self):
        e = _env("b1", msg="hi", enc="raw")
        bits = encode_bits(e, 256)
        raw = np.packbits(bits).tobytes()
        assert raw[0] == 2 and raw[1:3] == b"hi"
        assert digest_hex(e) == raw.hex()
        with pytest.raises(MessageTooLong):
            encode_bits(_env("b1", msg="x" * 32, enc="raw"))
        with pytest.raises(MessageTooLong):
            encode_bits(_env("b1", msg="x" * 5000))


class TestDistribution:
    def test_structure(self, honest):
        out, _ = honest
        p = out.bundle.params
        b = out.bundle
        assert b.labels.shape == (p.digest_bits, 2, p.L)
        for v in ("bob", "charlie"):
            r = b.records[v]
            assert r.basis.shape == b.labels.shape
            assert np.all(r.fwd.sum(axis=2) == p.L // 2)
            ev = out.evidence[v]
            assert ev.pe.total == p.digest_bits * 2 * p.n_pe
            assert ev.bell.S_lcb > 2.0
            assert ev.frame["mismatched"] == 0
            assert 0 < ev.qber["rate"] < 0.03
        assert out.design.feasible

    def test_view_boundaries(self, honest):
        out, _ = honest
        view = out.bundle.view_for("bob")
        assert np.array_equal(view.recv_mask, out.bundle.records["charlie"].fwd)
        assert np.all(view.recv_basis[~view.recv_mask] == 255)
        with pytest.raises(KeyError):
            out.bundle.view_for("erin")

    def test_save_load_roundtrip(self, honest, tmp_path):
        out, _ = honest
        path = tmp_path / "b.npz"
        out.bundle.save(path)
        again = KeyBundle.load(path)
        assert np.array_equal(again.labels, out.bundle.labels)
        for v in ("bob", "charlie"):
            assert np.array_equal(again.records[v].fwd, out.bundle.records[v].fwd)
            assert np.array_equal(again.records[v].outcome, out.bundle.records[v].outcome)
        again.shred_labels()
        assert again.labels is None


class TestSignVerify:
    def test_honest_accepted_by_both(self, links):
        p = params_for("analysis")
        out = distribute("g-alice", "alice", ("bob", "charlie"), links, p, RandomSource(7))
        d = out.design
        sig = sign(out.bundle, _env(out.bundle.bundle_id))
        r1 = verify(out.bundle.view_for("bob"), sig, d.s_a, d.n_min, "first", _sprt(d))
        r2 = verify(out.bundle.view_for("charlie"), sig, d.s_v, d.n_min, "transfer", _sprt(d))
        assert r1.decision == "ACCEPT" and r2.decision == "ACCEPT"
        assert not r1.sprt["early_reject"]
        assert r1.grid["keys"] == 16
        with pytest.raises(KeyReuseError):
            sign(out.bundle, _env(out.bundle.bundle_id, msg="second"))

    def test_ideal_channel_deterministic(self):
        from sentinel.protocol.link import LinkSpec
        links = {v: LinkSpec(f"alice-{v}", "alice", v, [], 1) for v in ("bob", "charlie")}
        out = distribute("g-alice", "alice", ("bob", "charlie"), links, params_for("analysis"), RandomSource(9))
        sig = sign(out.bundle, _env(out.bundle.bundle_id))
        r = verify(out.bundle.view_for("bob"), sig, out.design.s_a, out.design.n_min)
        assert r.mismatches == 0 and r.decision == "ACCEPT"

    def test_random_labels_rejected_fast(self, links):
        p = params_for("analysis")
        out = distribute("g-alice", "alice", ("bob", "charlie"), links, p, RandomSource(8))
        d = out.design
        sig = sign(out.bundle, _env(out.bundle.bundle_id))
        forged = sig.copy()
        forged.revealed = RandomSource(1).labels(forged.revealed.size).reshape(forged.revealed.shape)
        r = verify(out.bundle.view_for("bob"), forged, d.s_a, d.n_min, "first", _sprt(d))
        assert r.decision == "REJECT" and r.sprt["early_reject"]
        assert r.sprt["fraction_read"] < 0.05
        assert r.mismatches / r.tested == pytest.approx(0.5, abs=0.05)

    def test_counterfactual_modes(self, honest):
        out, _ = honest
        d = out.design
        env = _env(out.bundle.bundle_id)
        from sentinel.protocol.signing import signature_from_labels
        sig = signature_from_labels(env, out.bundle.labels[np.arange(32), encode_bits(env, 32), :], 32)
        for mode in ("pooled", "own_only"):
            r = verify(out.bundle.view_for("charlie"), sig, d.s_v, d.n_min, "transfer", mode=mode)
            assert r.decision == "ACCEPT" and r.mode == mode


class TestDesign:
    def test_tails_hold_for_every_n(self):
        d = design(4096, 0.013)
        assert d.feasible and d.s_a < d.s_v
        from scipy.stats import binom
        for n in range(d.n_min, 4096 // 2 + 1, 37):
            assert binom.sf(math.floor(d.s_a * n + 1e-9), n, 0.013) <= d.eps_rob_set * (1 + 1e-9)
            assert binom.cdf(math.floor(d.s_v * n + 1e-9), n, 1 / 3) <= d.eps_forge_key * (1 + 1e-9)
        assert d.meets_targets == {"robustness": True, "forgery": True, "repudiation": True}

    def test_infeasible_reports_L_min(self):
        d = design(512, 0.05, eps_rob_target=1e-9, eps_forge_target=1e-6)
        assert d.L_min is not None and d.L_min > 512
        assert design(d.L_min, 0.05).feasible

    def test_repudiation_bound_brute(self):
        n, sa, sv = 60, 0.1, 0.25
        a, b = math.floor(sa * n), math.floor(sv * n)
        brute = max(hypergeom_split_tail(2 * n, K, n, a, b) for K in range(0, 2 * n + 1))
        assert repudiation_bound(n, sa, sv) == pytest.approx(brute)


class TestGuard:
    def test_all_checks(self):
        store = MemoryGuardStore()
        meta = {"bundle_id": "b1", "group_id": "g-alice", "signer_id": "alice",
                "recipients": ["bob", "charlie"], "status": "SIGNED"}
        env = _env("b1", seq=5)
        f = {x.id: x for x in check_guard(env, meta, "bob", store)}
        assert not any(x.fired for x in f.values())
        store.commit("bob", env, "s1", accepted=True)
        f = {x.id: x for x in check_guard(env, meta, "bob", store)}
        assert f["S3.bundle_state"].fired and f["S4.nonce"].fired and f["S5.sequence"].fired
        f = {x.id: x for x in check_guard(env, meta, "erin", store)}
        assert f["S1.authorization"].fired
        f = {x.id: x for x in check_guard(env.with_(signer_id="mallory"), meta, "charlie", store)}
        assert f["S2.key_binding"].fired
        f = {x.id: x for x in check_guard(env, meta, "charlie", store, now=env.timestamp + 500)}
        assert f["S6.freshness"].fired
        f = {x.id: x for x in check_guard(env, dict(meta, status="COMPROMISED"), "charlie", store)}
        assert f["S3.bundle_state"].fired and f["S3.bundle_state"].data["policy_block"]


def test_wegman_carter_mac():
    rng = np.random.default_rng(0)
    k = rng.integers(0, 4, 10_000).astype(np.uint8)
    r, s = wc_keys(b"k" * 32, "b1|bob")
    assert wc_tag(k, r, s) == wc_tag(k.copy(), r, s)
    k2 = k.copy()
    k2[1234] ^= 1
    assert wc_tag(k, r, s) != wc_tag(k2, r, s)
    assert wc_keys(b"k" * 32, "b2|bob") != (r, s)


def test_mac_detects_frame_tamper(links):
    links["bob"].authenticated = True
    links["bob"].mac_key = b"s" * 32
    out = distribute("g-alice", "alice", ("bob", "charlie"), links, params_for("analysis"), RandomSource(4),
                     plans={"bob": LinkPlan(flip_c1=0.001)})
    assert out.evidence["bob"].frame["mac"] == "fail"
    assert out.evidence["charlie"].frame["mac"] == "absent"
