"""End-to-end API tests: every route group through FastAPI's TestClient, with the real engine."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from server.app import create_app

from .conftest import make_settings

API = "/api/v1"


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


# ------------------------------------------------------------------ system
def test_health_and_config(client):
    h = ok(client.get(f"{API}/health"))
    assert h["status"] == "ok" and h["preset"] == "demo"
    cfg = ok(client.get(f"{API}/system/config"))
    assert {"demo", "standard", "high"} <= set(cfg["presets"])
    assert cfg["features"]["tamper_demo"] is True
    assert "X-Request-ID" in client.get(f"{API}/health").headers


def test_root_without_frontend(client):
    assert ok(client.get("/"))["docs"] == "/docs"
    assert client.get("/openapi.json").status_code == 200


def test_selftest_runs_and_passes(client):
    ok(client.post(f"{API}/system/selftest/run"), 202)
    for _ in range(600):
        snap = ok(client.get(f"{API}/system/selftest"))
        if snap["state"] == "done":
            break
        time.sleep(0.1)
    assert snap["state"] == "done"
    bad = [c for c in snap["checks"] if c["status"] == "fail"]
    assert not bad, bad


# ------------------------------------------------------------------ network
def test_network_hides_adversaries_by_default(client):
    net = ok(client.get(f"{API}/network"))
    ids = {n["id"] for n in net["nodes"]}
    assert {"alice", "bob", "charlie", "diana", "erin"} <= ids
    assert "eve" not in ids and "mallory" not in ids
    full = ok(client.get(f"{API}/network", params={"include_hidden": True}))
    assert "eve" in {n["id"] for n in full["nodes"]}


def test_link_lifecycle(client):
    ok(client.post(f"{API}/network/links/alice-charlie/quarantine", json={"reason": "test"}))
    r = client.post(f"{API}/signatures/sign-and-verify", json={"message": "blocked?"})
    assert r.status_code in (409, 200)
    ok(client.post(f"{API}/network/links/alice-charlie/release"))
    cert = ok(client.post(f"{API}/network/links/alice-charlie/certify"))
    assert cert["certified"] is True
    assert ok(client.get(f"{API}/network/links/alice-charlie"))["status"] == "ACTIVE"
    assert client.get(f"{API}/network/links/nope").status_code == 404


# ------------------------------------------------------------------ keys + signatures
def test_distribute_sign_verify_roundtrip(client):
    d = ok(client.post(f"{API}/keys/distribute", json={"group_id": "g-alice"}))
    assert d["kind"] == "distribution" and d["assessment"]["verdict"] == "CERTIFIED"
    bundle = ok(client.get(f"{API}/keys/bundles/{d['bundle_id']}"))
    assert bundle["status"] == "ACTIVE"

    s = ok(client.post(f"{API}/signatures/sign-and-verify",
                       json={"message": "Transfer 5,000 INR to account 42", "bundle_id": d["bundle_id"]}))
    assert s["assessment"]["verdict"] == "ACCEPTED"
    assert s["bundle_id"] == d["bundle_id"]
    assert ok(client.get(f"{API}/keys/bundles/{d['bundle_id']}"))["status"] != "ACTIVE"

    sess = ok(client.get(f"{API}/sessions/{s['session_id']}"))
    assert sess["session_id"] == s["session_id"]
    listed = ok(client.get(f"{API}/sessions", params={"kind": "signature"}))
    assert any(x["id"] == s["session_id"] for x in listed)
    assert any(c["session_id"] == s["session_id"] for c in ok(client.get(f"{API}/signatures/captured")))


def test_auto_distribution_and_raw_encoding(client):
    s = ok(client.post(f"{API}/signatures/sign-and-verify",
                       json={"group_id": "g-diana", "message": "short", "encoding": "raw"}))
    assert s["assessment"]["verdict"] == "ACCEPTED"
    r = client.post(f"{API}/signatures/sign-and-verify", json={"message": "x" * 40, "encoding": "raw"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "MESSAGE_TOO_LONG"


def test_reverify_is_rejected_as_replay(client):
    s = ok(client.post(f"{API}/signatures/sign-and-verify", json={"message": "once only"}))
    again = ok(client.post(f"{API}/signatures/{s['session_id']}/reverify", json={}))
    assert again["assessment"]["verdict"] == "REJECTED"


def test_validation_errors(client):
    r = client.post(f"{API}/signatures/sign-and-verify", json={"message": ""})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    r = client.post(f"{API}/signatures/sign-and-verify", json={"message": "hi", "group_id": "g-nope"})
    assert r.status_code in (404, 409, 422)
    assert client.get(f"{API}/sessions/missing").status_code == 404
    assert client.get(f"{API}/does-not-exist").json()["error"]["code"] == "NOT_FOUND"


def test_reservoir(client):
    res = ok(client.get(f"{API}/keys/reservoir"))
    assert {r["group_id"] for r in res} >= {"g-alice", "g-diana"}
    assert "g-mallory" not in {r["group_id"] for r in res}


# ------------------------------------------------------------------ attacks
def test_attack_catalog(client):
    cat = ok(client.get(f"{API}/attacks/catalog"))
    assert len(cat) == 17


@pytest.mark.parametrize("attack_id", [
    "channel.dephase", "channel.pauli_frame", "unauthorized.key_harvest_mitm", "unauthorized.non_recipient",
    "forgery.blind", "forgery.insider", "impersonation.identity_swap", "replay.resubmit",
    "repudiation.inconsistent_keys",
])
def test_attacks_detected_and_classified(client, attack_id):
    run = ok(client.post(f"{API}/attacks/run", json={"attack": {"attack_id": attack_id, "intensity": 0.6}}))
    assert run["detected"] is True, run["verdict"]
    assert run["correctly_classified"] is True, (run["detected_category"], run["detected_subtype"])
    assert run["detected_category"] == run["expected_category"]


def test_attack_runs_and_incidents(client):
    runs = ok(client.get(f"{API}/attacks/runs"))
    assert runs
    detail = ok(client.get(f"{API}/attacks/runs/{runs[0]['id']}"))
    assert "attack" in detail
    incidents = ok(client.get(f"{API}/incidents"))
    assert incidents, "attacks must open incidents"
    inc = incidents[0]
    ok(client.post(f"{API}/incidents/{inc['id']}/acknowledge", json={"note": "on it"}))
    resp = client.post(f"{API}/incidents/{inc['id']}/respond", json={"action": "notify_recipients"})
    assert ok(resp)["result"]["recorded"] is True
    assert client.post(f"{API}/incidents/{inc['id']}/respond", json={"action": "bogus"}).status_code == 422
    done = ok(client.post(f"{API}/incidents/{inc['id']}/resolve", json={"note": "closed"}))
    assert done["status"] == "RESOLVED"


def test_unknown_attack(client):
    r = client.post(f"{API}/attacks/run", json={"attack": {"attack_id": "nope"}})
    assert r.status_code == 422


# ------------------------------------------------------------------ detection
def test_detection_config_and_catalog(client):
    dets = ok(client.get(f"{API}/detection/detectors"))
    assert {d["id"].split(".")[0] for d in dets} >= {f"D{i}" for i in (1, 2, 4, 5, 6, 7, 8, 9, 10)}
    before = ok(client.get(f"{API}/detection/config"))
    after = ok(client.put(f"{API}/detection/config", json={"alpha_family": 1e-5}))
    assert after["alpha_family"] == 1e-5
    ok(client.put(f"{API}/detection/config", json={"alpha_family": before["alpha_family"]}))
    base = ok(client.get(f"{API}/detection/baselines"))
    assert {b["link_id"] for b in base} >= {"alice-bob", "alice-charlie"}


# ------------------------------------------------------------------ theory + playground
def test_theory(client):
    d = ok(client.get(f"{API}/theory/design", params={"L": 4096, "e": 0.013}))
    assert d["feasible"] and d["s_a"] < d["s_v"]
    tight = ok(client.get(f"{API}/theory/design", params={"L": 256, "e": 0.02}))
    assert tight["feasible"] is False  # L=256 cannot meet the 1e-9 / 1e-6 targets
    f = ok(client.get(f"{API}/theory/forgery", params={"L_min": 32, "L_max": 1024, "points": 5}))
    assert len(f["L"]) == 5
    link = ok(client.post(f"{API}/theory/link", json={"channels": [{"type": "depolarizing", "p": 0.05}]}))
    assert 2 < link["S"] < 2.83 and abs(link["qber"] - 0.025) < 1e-9


def test_playground(client):
    ch = ok(client.post(f"{API}/playground/channel", json={"channels": [{"type": "amplitude_damping", "gamma": 0.3}]}))
    assert len(ch["ptm"]) == 4
    tp = ok(client.post(f"{API}/playground/teleport", json={"label": 0, "shots": 400, "basis": "x"}))
    assert len(tp["outcomes"]) == 4
    assert abs(sum(o["prob"] for o in tp["outcomes"]) - 1) < 1e-9
    r = client.post(f"{API}/playground/channel", json={"channels": [{"type": "nope"}]})
    assert r.status_code == 422


# ------------------------------------------------------------------ ledger
def test_ledger_tamper_detect_revert(client):
    ok(client.post(f"{API}/signatures/sign-and-verify", json={"message": "ledger entry"}))
    ok(client.post(f"{API}/ledger/seal"))
    summary = ok(client.get(f"{API}/ledger/summary"))
    assert summary["height"] >= 1
    assert ok(client.post(f"{API}/ledger/verify"))["valid"] is True
    blk = ok(client.get(f"{API}/ledger/blocks/1"))
    assert blk["block"]["height"] == 1
    info = ok(client.post(f"{API}/ledger/tamper", json={}))
    assert ok(client.get(f"{API}/ledger/tx/{info['tx_id']}"))["valid"] is False
    bad = ok(client.post(f"{API}/ledger/verify"))
    assert bad["valid"] is False and bad["first_invalid_height"] is not None
    ok(client.post(f"{API}/ledger/tamper/revert"))
    assert ok(client.post(f"{API}/ledger/verify"))["valid"] is True


# ------------------------------------------------------------------ metrics
def test_metrics(client):
    m = ok(client.get(f"{API}/metrics/summary"))
    assert m["sessions"]["signature_total"] >= 1
    assert m["detection"]["frr"] == 0
    ts = ok(client.get(f"{API}/metrics/timeseries"))
    assert ts["points"]
    q = ok(client.get(f"{API}/metrics/timeseries", params={"series": "qber"}))
    assert q["points"]
    prom = client.get(f"{API}/metrics/prometheus")
    assert prom.status_code == 200 and "qveris_signatures_total" in prom.text


# ------------------------------------------------------------------ jobs
def test_analytics_job_lifecycle(client):
    kinds = {k["kind"] for k in ok(client.get(f"{API}/analytics/kinds"))}
    assert "threshold_design" in kinds
    job = ok(client.post(f"{API}/analytics/jobs", json={"kind": "threshold_design", "preset": "quick"}))
    for _ in range(600):
        j = ok(client.get(f"{API}/analytics/jobs/{job['id']}"))
        if j["status"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.1)
    assert j["status"] == "SUCCEEDED", j
    assert j["result"]["rows"]
    assert ok(client.get(f"{API}/analytics/latest/threshold_design"))["id"] == job["id"]
    assert client.post(f"{API}/analytics/jobs", json={"kind": "nope"}).status_code in (404, 422)


# ------------------------------------------------------------------ traffic + campaigns
def test_traffic_and_campaign_controls(client):
    assert ok(client.post(f"{API}/traffic/start", json={"rate_per_min": 30}))["running"] is True
    assert ok(client.post(f"{API}/traffic/stop"))["running"] is False
    camp = ok(client.post(f"{API}/attacks/campaigns", json={"preset": "replay_storm", "duration_s": 10}))
    assert any(c["id"] == camp["id"] for c in ok(client.get(f"{API}/attacks/campaigns"))["campaigns"])
    ok(client.delete(f"{API}/attacks/campaigns/{camp['id']}"))


# ------------------------------------------------------------------ websocket
def test_websocket_stream(client):
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and "sessions" in hello["data"]["topics"]
        ws.send_json({"op": "ping", "t": 7})
        assert ws.receive_json()["data"]["t"] == 7
        ws.send_json({"op": "unsubscribe", "topics": ["metrics", "system", "jobs", "traffic"]})
        assert ws.receive_json()["type"] == "subscribed"
        sid = ok(client.post(f"{API}/signatures/sign-and-verify", json={"message": "stream me"}))["session_id"]
        for _ in range(200):
            m = ws.receive_json()
            if m["type"] == "session.completed" and m["data"]["id"] == sid:
                assert m["data"]["verdict"] == "ACCEPTED"
                assert m["data"]["injected_attack"] is None
                break
        else:
            pytest.fail("session.completed for our signature never arrived")


# ------------------------------------------------------------------ persistence + auth
def test_restart_persistence(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, skip_calibration=True))) as c:
        ok(c.post(f"{API}/detection/baselines/calibrate", json={}))
        s = ok(c.post(f"{API}/signatures/sign-and-verify", json={"message": "persist"}))
        ok(c.post(f"{API}/ledger/seal"))
    with TestClient(create_app(make_settings(tmp_path, skip_calibration=True))) as c:
        assert ok(c.get(f"{API}/sessions/{s['session_id']}"))["session_id"] == s["session_id"]
        assert ok(c.post(f"{API}/ledger/verify"))["valid"] is True
        assert ok(c.get(f"{API}/detection/baselines"))


def test_api_key_protects_mutations(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, api_key="s3cret", skip_calibration=True))) as c:
        assert c.get(f"{API}/health").status_code == 200
        assert c.post(f"{API}/ledger/seal").status_code == 401
        assert c.post(f"{API}/ledger/seal", headers={"X-API-Key": "s3cret"}).status_code == 200


def test_rate_limit(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, heavy_rate_capacity=2, heavy_rate_refill=0.01,
                                             skip_calibration=True))) as c:
        codes = [c.post(f"{API}/theory/link", json={}).status_code for _ in range(3)]  # not heavy
        assert codes == [200, 200, 200]
        codes = [c.post(f"{API}/detection/baselines/calibrate", json={"link_ids": ["alice-bob"]}).status_code
                 for _ in range(3)]
        assert codes[:2] == [200, 200] and codes[2] == 429


def test_background_workers_fill_reservoir(tmp_path):
    s = make_settings(tmp_path, background=True, autostart_traffic=False)
    with TestClient(create_app(s)) as c:
        deadline = time.time() + 90
        while time.time() < deadline:
            res = {r["group_id"]: r for r in ok(c.get(f"{API}/keys/reservoir"))}
            if all(r["active"] >= r["target"] for r in res.values()):
                break
            time.sleep(0.5)
        assert all(r["active"] >= r["target"] for r in res.values()), res
        assert ok(c.get(f"{API}/detection/baselines"))


def test_serves_built_frontend_with_spa_fallback(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>QVeris</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    with TestClient(create_app(make_settings(tmp_path, web_dist=dist, skip_calibration=True))) as c:
        assert "QVeris" in c.get("/").text
        assert "QVeris" in c.get("/attack-lab").text          # client-side route
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert c.get("/api/v1/nope").status_code == 404        # API 404s stay JSON
        assert c.get("/api/v1/analytics/latest/roc").json() is None


def test_quarantine_blocks_signing_with_existing_bundles(client):
    ok(client.post(f"{API}/keys/distribute", json={"group_id": "g-alice"}))
    ok(client.post(f"{API}/network/links/alice-bob/quarantine", json={"reason": "test"}))
    try:
        r = client.post(f"{API}/signatures/sign-and-verify", json={"message": "must not sign"})
        assert r.status_code == 409 and r.json()["error"]["code"] == "LINK_QUARANTINED"
        res = {x["group_id"]: x for x in ok(client.get(f"{API}/keys/reservoir"))}
        assert "quarantined" in res["g-alice"]["blocked_reason"]
    finally:
        ok(client.post(f"{API}/network/links/alice-bob/release"))
    assert ok(client.post(f"{API}/signatures/sign-and-verify", json={"message": "after release"}))["verdict"] == "ACCEPTED"


def test_suspend_and_reinstate_signer(client):
    ok(client.post(f"{API}/network/nodes/diana/suspend"))
    r = client.post(f"{API}/signatures/sign-and-verify", json={"group_id": "g-diana", "message": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SIGNER_SUSPENDED"
    ok(client.post(f"{API}/network/nodes/diana/reinstate"))
    assert ok(client.post(f"{API}/signatures/sign-and-verify", json={"group_id": "g-diana", "message": "y"}))["verdict"] == "ACCEPTED"
    assert client.post(f"{API}/network/nodes/eve/suspend").status_code == 404


def test_threat_level_follows_open_incidents(client):
    run = ok(client.post(f"{API}/attacks/run", json={"attack": {"attack_id": "forgery.blind"}, "counterfactual": False}))
    level = lambda: ok(client.get(f"{API}/metrics/summary"))["threat_level"]
    assert level() in ("HIGH", "CRITICAL")
    for inc in ok(client.get(f"{API}/incidents", params={"status": "OPEN", "limit": 500})):
        ok(client.post(f"{API}/incidents/{inc['id']}/resolve", json={"note": "test"}))
    assert level() == "NONE"
    assert run["incident_id"]
