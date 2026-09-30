"""
server/api/routes/v1.py
=======================
REST API v1 (backend plan section 12).

Handlers that run engine work are plain ``def`` so FastAPI executes them in
its worker thread pool; handlers that touch asyncio objects are ``async``.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Optional

import numpy as np
from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from sentinel import __version__ as ENGINE_VERSION
from sentinel.adversary.catalog import CATALOG, CATEGORIES
from sentinel.analysis.forgery import exact_curves
from sentinel.analysis.jobs import kinds_public
from sentinel.bell import bell_state, predicted
from sentinel.channels import CHANNEL_TYPES, compose
from sentinel.detection.catalog import DETECTORS
from sentinel.linalg import ptm_affine, ptm_to_choi, is_cptp
from sentinel.protocol.thresholds import design, pmf_series
from sentinel.states import FRAME_PTM
from sentinel.teleport import get_model
from server.api import schemas as S
from server.db.database import loads
from server.services.engine import ApiConflict, ApiNotFound
from server.services.workers import CAMPAIGN_PRESETS

router = APIRouter(prefix="/api/v1")


def ctx(request: Request):
    return request.app.state.ctx


# ======================================================================= system
@router.get("/health", tags=["system"])
def health(request: Request):
    c = ctx(request)
    return {"status": "ok", "version": ENGINE_VERSION, "engine_version": ENGINE_VERSION,
            "uptime_s": time.time() - c.started_at, "db": "ok", "ws_clients": c.hub.client_count,
            "preset": c.engine.preset, "time": time.time(), "env": c.settings.env}


@router.get("/system/selftest", tags=["system"])
def selftest(request: Request):
    return ctx(request).selftest.snapshot()


@router.post("/system/selftest/run", tags=["system"], status_code=202)
def selftest_run(request: Request):
    st = ctx(request).selftest
    if st.state != "running":
        threading.Thread(target=st.run, daemon=True, name="selftest").start()
        time.sleep(0.05)
    return st.snapshot()


@router.get("/system/config", tags=["system"])
def system_config(request: Request):
    c = ctx(request)
    return {"presets": c.engine.presets(), "active_preset": c.engine.preset, "detection": c.engine.detection.as_dict(),
            "features": {"tamper_demo": c.settings.allow_tamper_demo, "mac": True, "api_key_required": bool(c.settings.api_key)},
            "channel_types": CHANNEL_TYPES, "categories": CATEGORIES,
            "limits": {"message_bytes": 4096, "raw_message_bytes": 31, "traffic_rate_per_min": [1, 120],
                       "campaign_duration_s": [10, 3600]},
            "hardware_model": {"source_rate_hz": c.engine.world.hardware.source_rate_hz,
                               "fibre_loss_db_per_km": c.engine.world.hardware.loss_db_per_km,
                               "detector_efficiency": c.engine.world.hardware.detector_efficiency}}


@router.put("/system/preset", tags=["system"])
def set_preset(body: S.PresetIn, request: Request):
    return {"active_preset": body.preset, "params": ctx(request).engine.set_preset(body.preset)}


# ======================================================================= network
@router.get("/network", tags=["network"])
def network(request: Request, include_hidden: bool = False):
    return ctx(request).engine.network_view(include_hidden)


@router.get("/network/links/{link_id}", tags=["network"])
def link_detail(link_id: str, request: Request):
    c = ctx(request)
    st = c.engine.link_status(link_id)
    b = c.engine.world.baselines.get(link_id)
    mon = c.db.query("SELECT * FROM link_monitor WHERE link_id=? ORDER BY t DESC LIMIT 100", (link_id,))
    groups = c.engine.groups_on_link(link_id)
    bundles = []
    if groups:
        marks = ",".join("?" * len(groups))
        bundles = c.db.query(f"SELECT id, group_id, status, origin, created_at, session_id FROM bundles WHERE group_id IN ({marks}) "
                             "ORDER BY created_at DESC LIMIT 20", groups)
    return {**st, "baseline_detail": b.summary() if b else None, "monitor": list(reversed(mon)), "groups": groups,
            "recent_bundles": bundles}


@router.patch("/network/links/{link_id}", tags=["network"])
def link_patch(link_id: str, body: S.LinkPatch, request: Request):
    return ctx(request).engine.patch_link(link_id, body.baseline_channel, body.authenticated_classical, body.length_km)


@router.post("/network/links/{link_id}/certify", tags=["network"])
def link_certify(link_id: str, request: Request):
    return ctx(request).engine.certify_link(link_id)


@router.post("/network/links/{link_id}/quarantine", tags=["network"])
def link_quarantine(link_id: str, body: S.ReasonIn, request: Request):
    return ctx(request).engine.set_link_status(link_id, "QUARANTINED", body.reason or "operator")


@router.post("/network/links/{link_id}/release", tags=["network"])
def link_release(link_id: str, request: Request):
    return ctx(request).engine.set_link_status(link_id, "ACTIVE", "released by operator")


@router.post("/network/nodes/{node_id}/suspend", tags=["network"])
def node_suspend(node_id: str, request: Request):
    return ctx(request).engine.suspend_signer(node_id, True)


@router.post("/network/nodes/{node_id}/reinstate", tags=["network"])
def node_reinstate(node_id: str, request: Request):
    return ctx(request).engine.suspend_signer(node_id, False)


@router.get("/network/links/{link_id}/monitor", tags=["network"])
def link_monitor(link_id: str, request: Request, limit: int = Query(200, ge=1, le=5000)):
    rows = ctx(request).db.query("SELECT * FROM link_monitor WHERE link_id=? ORDER BY t DESC LIMIT ?", (link_id, limit))
    return list(reversed(rows))


# ======================================================================= keys
@router.get("/keys/reservoir", tags=["keys"])
def reservoir(request: Request):
    return ctx(request).engine.reservoir()


def _bundle_row(r: dict) -> dict:
    r["recipients"] = loads(r["recipients"])
    for k in ("params", "design", "summary", "injected_attack"):
        if k in r:
            r[k] = loads(r[k])
    r.pop("material_path", None)
    return r


@router.get("/keys/bundles", tags=["keys"])
def bundles(request: Request, status: Optional[str] = None, group_id: Optional[str] = None,
            limit: int = Query(50, ge=1, le=500), before: Optional[float] = None):
    sql = "SELECT id, group_id, signer_id, recipients, preset, status, origin, session_id, injected_attack, created_at, updated_at FROM bundles WHERE 1=1"
    args: list = []
    if status:
        sql += " AND status=?"
        args.append(status)
    if group_id:
        sql += " AND group_id=?"
        args.append(group_id)
    if before:
        sql += " AND created_at < ?"
        args.append(before)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    return [_bundle_row(r) for r in ctx(request).db.query(sql, args)]


@router.get("/keys/bundles/{bundle_id}", tags=["keys"])
def bundle(bundle_id: str, request: Request):
    c = ctx(request)
    r = c.db.one("SELECT * FROM bundles WHERE id=?", (bundle_id,))
    if not r:
        raise ApiNotFound(bundle_id)
    out = _bundle_row(r)
    out["consumption"] = c.db.query("SELECT verifier_id, session_id, consumed_at FROM bundle_consumption WHERE bundle_id=?", (bundle_id,))
    return out


@router.post("/keys/distribute", tags=["keys"])
def distribute(body: S.DistributeIn, request: Request):
    return ctx(request).engine.distribute(body.group_id, body.origin, body.preset)


@router.post("/keys/bundles/{bundle_id}/revoke", tags=["keys"])
def revoke(bundle_id: str, body: S.ReasonIn, request: Request):
    c = ctx(request)
    m = c.engine.bundles.meta(bundle_id)
    if not m:
        raise ApiNotFound(bundle_id)
    if m["status"] != "ACTIVE":
        raise ApiConflict("BUNDLE_NOT_ACTIVE", f"bundle is {m['status']}")
    c.engine.bundles.set_status(bundle_id, "REVOKED")
    c.engine.bundles.shred(bundle_id, labels_only=True)
    c.ledger.append("BUNDLE_REVOKED", {"bundle_id": bundle_id, "reason": body.reason}, ref_id=bundle_id)
    c.hub.publish("reservoir", "reservoir.updated", c.engine.reservoir())
    return bundle(bundle_id, request)


# ======================================================================= signatures and sessions
@router.post("/signatures/sign-and-verify", tags=["signatures"])
def sign_and_verify(body: S.SignIn, request: Request):
    return ctx(request).engine.sign_and_verify(body.group_id, body.message, body.encoding, body.bundle_id, body.origin)


@router.get("/signatures/captured", tags=["signatures"])
def captured(request: Request):
    return ctx(request).engine.captured()


@router.post("/signatures/{session_id}/reverify", tags=["signatures"])
def reverify(session_id: str, body: S.ReverifyIn, request: Request):
    return ctx(request).engine.reverify(session_id, body.verifier_id, body.delay_s)


@router.get("/sessions", tags=["sessions"])
def sessions(request: Request, kind: Optional[str] = None, origin: Optional[str] = None, verdict: Optional[str] = None,
             category: Optional[str] = None, attack: Optional[bool] = None, limit: int = Query(50, ge=1, le=500),
             before: Optional[float] = None):
    sql = "SELECT summary FROM sessions WHERE counterfactual=0"
    args: list = []
    for col, val in (("kind", kind), ("origin", origin), ("verdict", verdict), ("category", category)):
        if val:
            sql += f" AND {col}=?"
            args.append(val)
    if attack is not None:
        sql += " AND injected_attack IS " + ("NOT NULL" if attack else "NULL")
    if before:
        sql += " AND created_at < ?"
        args.append(before)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    return [loads(r["summary"]) for r in ctx(request).db.query(sql, args)]


@router.get("/sessions/{session_id}", tags=["sessions"])
def session(session_id: str, request: Request):
    r = ctx(request).db.one("SELECT summary, report FROM sessions WHERE id=?", (session_id,))
    if not r:
        raise ApiNotFound(session_id)
    if r["report"] is None:
        return {**loads(r["summary"]), "report_pruned": True}
    return loads(r["report"])


# ======================================================================= attacks, campaigns, traffic
@router.get("/attacks/catalog", tags=["attacks"])
def attack_catalog():
    return CATALOG


@router.post("/attacks/run", tags=["attacks"])
def attack_run(body: S.AttackRunIn, request: Request):
    return ctx(request).engine.run_attack(body.attack.model_dump(), body.group_id, body.message, body.counterfactual)


@router.get("/attacks/runs", tags=["attacks"])
def attack_runs(request: Request, limit: int = Query(30, ge=1, le=200)):
    rows = ctx(request).db.query("SELECT id, attack_id, category, group_id, origin, detected, correct, created_at "
                                 "FROM attack_runs ORDER BY created_at DESC LIMIT ?", (limit,))
    for r in rows:
        r["detected"], r["correct"] = bool(r["detected"]), bool(r["correct"])
    return rows


@router.get("/attacks/runs/{run_id}", tags=["attacks"])
def attack_run_get(run_id: str, request: Request):
    r = ctx(request).db.one("SELECT report FROM attack_runs WHERE id=?", (run_id,))
    if not r:
        raise ApiNotFound(run_id)
    return loads(r["report"])


@router.get("/attacks/campaigns", tags=["attacks"])
async def campaigns(request: Request):
    return {"campaigns": ctx(request).campaigns.list(), "presets": CAMPAIGN_PRESETS}


@router.post("/attacks/campaigns", tags=["attacks"])
async def campaign_start(body: S.CampaignIn, request: Request):
    mix = [m.model_dump() for m in body.mix]
    name = body.name
    if body.preset:
        p = CAMPAIGN_PRESETS.get(body.preset)
        if not p:
            raise ApiConflict("VALIDATION_ERROR", f"unknown campaign preset {body.preset!r}")
        mix = mix or p["mix"]
        name = p["name"] if body.name == "Custom campaign" else body.name
    if not mix:
        raise ApiConflict("VALIDATION_ERROR", "a campaign needs at least one attack")
    return ctx(request).campaigns.start(name, mix, body.rate_per_min, body.duration_s, body.group_ids, body.preset)


@router.delete("/attacks/campaigns/{campaign_id}", tags=["attacks"])
async def campaign_stop(campaign_id: str, request: Request):
    c = ctx(request).campaigns.stop(campaign_id)
    if c is None:
        raise ApiNotFound(campaign_id)
    return c


@router.get("/traffic", tags=["traffic"])
async def traffic(request: Request):
    return ctx(request).traffic.state()


@router.post("/traffic/start", tags=["traffic"])
async def traffic_start(body: S.TrafficIn, request: Request):
    return ctx(request).traffic.start(body.rate_per_min, body.groups)


@router.post("/traffic/stop", tags=["traffic"])
async def traffic_stop(request: Request):
    return ctx(request).traffic.stop()


# ======================================================================= detection and incidents
@router.get("/detection/config", tags=["detection"])
def detection_config(request: Request):
    return ctx(request).engine.detection.as_dict()


@router.put("/detection/config", tags=["detection"])
def detection_put(body: S.DetectionPatch, request: Request):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return ctx(request).engine.set_detection(patch)


@router.get("/detection/detectors", tags=["detection"])
def detectors():
    return DETECTORS


@router.get("/detection/baselines", tags=["detection"])
def baselines(request: Request):
    return [b.summary() for b in ctx(request).engine.world.baselines.values()]


@router.post("/detection/baselines/calibrate", tags=["detection"])
def calibrate(body: S.CalibrateIn, request: Request):
    return ctx(request).engine.calibrate(body.link_ids)


@router.get("/incidents", tags=["incidents"])
def incidents(request: Request, status: Optional[str] = None, severity: Optional[str] = None,
              category: Optional[str] = None, limit: int = Query(50, ge=1, le=500), before: Optional[float] = None):
    return ctx(request).incidents.list(status, severity, category, limit, before)


@router.get("/incidents/{incident_id}", tags=["incidents"])
def incident(incident_id: str, request: Request):
    c = ctx(request)
    inc = c.incidents.get(incident_id)
    if not inc:
        raise ApiNotFound(incident_id)
    sess = c.db.one("SELECT summary FROM sessions WHERE id=?", (inc["session_id"],)) if inc["session_id"] else None
    mon = []
    if inc["link_id"]:
        mon = c.db.query("SELECT * FROM link_monitor WHERE link_id=? AND t BETWEEN ? AND ? ORDER BY t",
                         (inc["link_id"], inc["created_at"] - 1800, inc["updated_at"] + 1800))
    tx = c.ledger.tx_for_ref(incident_id)
    return {**inc, "session": loads(sess["summary"]) if sess else None, "link_monitor": mon, "ledger_tx": tx,
            "link": c.engine.link_status(inc["link_id"]) if inc["link_id"] else None}


@router.post("/incidents/{incident_id}/acknowledge", tags=["incidents"])
def incident_ack(incident_id: str, body: S.NoteIn, request: Request):
    if not ctx(request).incidents.get(incident_id):
        raise ApiNotFound(incident_id)
    return ctx(request).incidents.set_status(incident_id, "ACKNOWLEDGED", body.note)


@router.post("/incidents/{incident_id}/resolve", tags=["incidents"])
def incident_resolve(incident_id: str, body: S.NoteIn, request: Request):
    if not ctx(request).incidents.get(incident_id):
        raise ApiNotFound(incident_id)
    return ctx(request).incidents.set_status(incident_id, "RESOLVED", body.note)


@router.post("/incidents/{incident_id}/respond", tags=["incidents"])
def incident_respond(incident_id: str, body: S.RespondIn, request: Request):
    return ctx(request).engine.respond(incident_id, body.action)


# ======================================================================= analytics
@router.get("/analytics/kinds", tags=["analytics"])
def analytics_kinds():
    return kinds_public()


@router.post("/analytics/jobs", tags=["analytics"])
def job_submit(body: S.JobIn, request: Request):
    try:
        return ctx(request).jobs.submit(body.kind, body.params, body.preset)
    except KeyError:
        raise ApiNotFound(f"job kind {body.kind}") from None


@router.get("/analytics/jobs", tags=["analytics"])
def jobs(request: Request, kind: Optional[str] = None, limit: int = Query(20, ge=1, le=200)):
    return ctx(request).jobs.list(kind, limit)


@router.get("/analytics/jobs/{job_id}", tags=["analytics"])
def job(job_id: str, request: Request):
    j = ctx(request).jobs.get(job_id)
    if not j:
        raise ApiNotFound(job_id)
    return j


@router.delete("/analytics/jobs/{job_id}", tags=["analytics"])
def job_cancel(job_id: str, request: Request):
    j = ctx(request).jobs.cancel(job_id)
    if not j:
        raise ApiNotFound(job_id)
    return j


@router.get("/analytics/latest/{kind}", tags=["analytics"])
def job_latest(kind: str, request: Request):
    # null (not 404) when the analysis has never been run: that is a normal state.
    return ctx(request).jobs.latest(kind)


# ======================================================================= theory and playground
@router.get("/theory/design", tags=["theory"])
def theory_design(L: int = Query(4096, ge=16, le=65536), e: float = Query(0.013, ge=0.0, le=0.3),
                  digest_bits: int = Query(256), eps_rob: float = Query(1e-9, gt=0, lt=1),
                  eps_forge: float = Query(1e-6, gt=0, lt=1), eps_rep: float = Query(1e-6, gt=0, lt=1)):
    if digest_bits not in (32, 64, 128, 256):
        raise ApiConflict("VALIDATION_ERROR", "digest_bits must be 32, 64, 128 or 256")
    d = design(L, max(e, 1e-6), digest_bits=digest_bits, eps_rob_target=eps_rob, eps_forge_target=eps_forge,
               eps_rep_target=eps_rep)
    return {**d.as_dict(), "pmf_honest": pmf_series(d.n_min, max(e, 1e-6)), "pmf_forger": pmf_series(d.n_min, d.p_forge)}


@router.get("/theory/forgery", tags=["theory"])
def theory_forgery(L_min: int = Query(32, ge=16), L_max: int = Query(8192, le=65536), points: int = Query(24, ge=2, le=80),
                   s_v: float = Query(0.2, gt=0, lt=0.5), e: float = Query(0.01, ge=0, lt=0.2)):
    Ls = sorted(set(int(x) for x in np.geomspace(L_min, L_max, points)))
    return exact_curves(Ls, s_v, e)


def _mc(M) -> dict:
    return {"M": np.asarray(M).tolist()}


@router.post("/theory/link", tags=["theory"])
def theory_link(body: S.ChannelsIn):
    ch = compose(body.channels)
    M, c = ch.affine
    pred = predicted(bell_state(ch))
    twirled = get_model(body.channels).averaged_ptm()
    tM, tc = ptm_affine(twirled)
    return {"S": pred["S"], "F": pred["F"], "qber_per_basis": pred["error"], "qber": pred["qber"], "E": pred["E"],
            "M": M.tolist(), "c": c.tolist(), "twirled_M": tM.tolist(), "twirled_c": tc.tolist()}


@router.post("/playground/channel", tags=["playground"])
def playground_channel(body: S.ChannelsIn):
    ch = compose(body.channels)
    M, c = ch.affine
    ok, info = is_cptp(ch.ptm)
    twirled = get_model(body.channels).averaged_ptm()
    tM, tc = ptm_affine(twirled)
    pred = predicted(bell_state(ch))
    return {"kraus": [{"re": np.real(K).tolist(), "im": np.imag(K).tolist()} for K in ch.kraus],
            "ptm": ch.ptm.tolist(), "M": M.tolist(), "c": c.tolist(), "choi_eigenvalues": info["choi_eigenvalues"],
            "cptp": ok, "twirled": {"M": tM.tolist(), "c": tc.tolist()},
            "predicted": {"S": pred["S"], "F": pred["F"], "qber_per_basis": pred["error"], "qber": pred["qber"]}}


@router.post("/playground/teleport", tags=["playground"])
def playground_teleport(body: S.TeleportIn):
    from sentinel.states import BLOCH

    if body.label is not None:
        r = BLOCH[body.label].copy()
    elif body.bloch is not None:
        r = np.asarray(body.bloch, dtype=float)
        n = float(np.linalg.norm(r))
        if n > 1:
            r = r / n
    else:
        raise ApiConflict("VALIDATION_ERROR", "give a label or a Bloch vector")
    q0 = float(min(max(body.frame_flip.get("m0", 0.0), 0.0), 1.0))
    q1 = float(min(max(body.frame_flip.get("m1", 0.0), 0.0), 1.0))
    model = get_model(body.channels)
    v = np.concatenate([[1.0], r])
    outcomes = []
    avg = np.zeros(3)
    fl = {0: (1 - q0) * (1 - q1), 1: (1 - q0) * q1, 2: q0 * (1 - q1), 3: q0 * q1}
    for k in range(4):
        raw = model.R[k] @ v
        p = float(raw[0])
        pre = (raw[1:] / p).tolist() if p > 1e-15 else [0, 0, 0]
        post = ((FRAME_PTM[k] @ raw)[1:] / p) if p > 1e-15 else np.zeros(3)
        received = {}
        for f, pf in fl.items():
            if pf <= 0:
                continue
            cbits = k ^ f
            b = (FRAME_PTM[cbits] @ raw)[1:] / p if p > 1e-15 else np.zeros(3)
            avg += p * pf * b
            received[str(cbits)] = {"prob": pf, "bloch": b.tolist()}
        outcomes.append({"k": k, "bits": [k >> 1, k & 1], "prob": p, "bloch_pre": pre, "bloch_post": post.tolist(),
                         "received": received})
    nr = float(np.linalg.norm(r))
    fidelity = float((1 + r @ avg) / 2) if nr > 0.999 else None
    out = {"input_bloch": r.tolist(), "outcomes": outcomes, "average_bloch": avg.tolist(), "fidelity": fidelity}
    if body.shots:
        rng = np.random.default_rng()
        bidx = "xyz".index(body.basis)
        ks = rng.choice(4, size=body.shots, p=np.clip([o["prob"] for o in outcomes], 0, None) / sum(o["prob"] for o in outcomes))
        flips = (rng.random(body.shots) < q0).astype(int) * 2 + (rng.random(body.shots) < q1).astype(int)
        cs = ks ^ flips
        zeros = 0
        for k in range(4):
            for c_ in range(4):
                sel = (ks == k) & (cs == c_)
                n = int(sel.sum())
                if not n:
                    continue
                raw = model.R[k] @ v
                b = (FRAME_PTM[c_] @ raw)[1:] / raw[0]
                zeros += int(rng.binomial(n, float(np.clip((1 + b[bidx]) / 2, 0, 1))))
        out["samples"] = {"basis": body.basis, "shots": body.shots, "counts": {"0": zeros, "1": body.shots - zeros},
                          "born_p0": float((1 + avg[bidx]) / 2),
                          "frames": {f"{k >> 1}{k & 1}": int((ks == k).sum()) for k in range(4)}}
    return out


# ======================================================================= ledger and metrics
@router.get("/ledger/summary", tags=["ledger"])
def ledger_summary(request: Request):
    return ctx(request).ledger.summary()


@router.get("/ledger/blocks", tags=["ledger"])
def ledger_blocks(request: Request, before: Optional[int] = None, limit: int = Query(30, ge=1, le=200)):
    return ctx(request).ledger.blocks(before, limit)


@router.get("/ledger/blocks/{height}", tags=["ledger"])
def ledger_block(height: int, request: Request):
    b = ctx(request).ledger.block(height)
    if not b:
        raise ApiNotFound(f"block {height}")
    return b


@router.get("/ledger/tx/{tx_id}", tags=["ledger"])
def ledger_tx(tx_id: str, request: Request):
    t = ctx(request).ledger.tx(tx_id)
    if not t:
        raise ApiNotFound(tx_id)
    return t


@router.post("/ledger/verify", tags=["ledger"])
def ledger_verify(request: Request):
    return ctx(request).ledger.verify()


@router.post("/ledger/tamper", tags=["ledger"])
def ledger_tamper(body: S.TamperIn, request: Request):
    try:
        return ctx(request).ledger.tamper(body.height)
    except LookupError as exc:
        raise ApiConflict("NOTHING_SEALED", str(exc)) from None


@router.post("/ledger/tamper/revert", tags=["ledger"])
def ledger_revert(request: Request):
    return ctx(request).ledger.revert()


@router.post("/ledger/seal", tags=["ledger"])
def ledger_seal(request: Request):
    return ctx(request).ledger.maybe_seal(force=True) or {"sealed": False, "reason": "no pending transactions"}


@router.get("/metrics/summary", tags=["metrics"])
def metrics_summary(request: Request, window: str = Query("all", pattern="^(all|24h|1h|15m)$")):
    return ctx(request).metrics.summary(window)


@router.get("/metrics/timeseries", tags=["metrics"])
def metrics_timeseries(request: Request, series: str = Query("sessions", pattern="^(sessions|qber)$"),
                       window: str = Query("1h", pattern="^(all|24h|1h|15m)$"), bucket_s: int = Query(60, ge=5, le=3600),
                       link_id: Optional[str] = None):
    return ctx(request).metrics.timeseries(series, window, bucket_s, link_id)


@router.get("/metrics/prometheus", tags=["metrics"], response_class=PlainTextResponse)
def metrics_prom(request: Request):
    return ctx(request).metrics.prometheus()
