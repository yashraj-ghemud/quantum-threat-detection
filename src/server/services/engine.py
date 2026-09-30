"""
server/services/engine.py
=========================
The server's engine service: a :class:`sentinel.world.World` backed by
SQLite and the keystore, plus persistence of every run, incidents, ledger
transactions and live events.

All World operations run under one lock: the World is not thread-safe, and
its operations are CPU-bound NumPy work (they release the GIL internally).
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Optional

from sentinel import __version__ as ENGINE_VERSION
from sentinel.adversary.catalog import AttackSpec, catalog_entry
from sentinel.channels import normalise_specs
from sentinel.detection.baseline import LinkBaseline, spec_hash
from sentinel.detection.config import DetectionConfig
from sentinel.detection.findings import SEVERITY_RANK
from sentinel.network import load_network, params_from_settings
from sentinel.protocol.link import HardwareModel, LinkSpec
from sentinel.protocol.params import ProtocolParams
from sentinel.world import GroupSpec, World
from server.db.database import Database, dumps, loads
from server.services.incidents import IncidentService
from server.services.ledger import LedgerService
from server.services.stores import DbBundleStore, DbGuardStore, next_seq_factory, seed_topology

__all__ = ["EngineService", "ApiConflict", "ApiNotFound"]


class ApiConflict(Exception):
    def __init__(self, code: str, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.detail = code, message, detail or {}


class ApiNotFound(Exception):
    pass


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class EngineService:
    def __init__(self, settings, db: Database, hub, ledger: LedgerService, incidents: IncidentService) -> None:
        self.settings = settings
        self.db = db
        self.hub = hub
        self.ledger = ledger
        self.incidents = incidents
        self.lock = threading.RLock()
        self.network = load_network(settings.config_dir / "network.yaml")
        seed_topology(db, self.network, settings.reservoir_target)
        yaml = settings.yaml
        self.detection = DetectionConfig.from_dict(yaml.get("detection"))
        stored = self.db.one("SELECT value FROM kv_settings WHERE key='detection'")
        if stored:
            self.detection = DetectionConfig(**{**self.detection.as_dict(), **loads(stored["value"])})
        preset_row = self.db.one("SELECT value FROM kv_settings WHERE key='preset'")
        self.preset = loads(preset_row["value"]) if preset_row else settings.preset
        self.bundles = DbBundleStore(db, settings.keystore_dir)
        self.bundles.on_status = self._on_bundle_status
        self.guard = DbGuardStore(db)
        hw = yaml.get("hardware_model", {})
        self.world = World(
            groups=self._load_groups(), links=self._load_links(), params=self._params(self.preset),
            detection=self.detection, guard=self.guard, bundles=self.bundles,
            baselines=self._load_baselines(), monitor_states=self._load_monitor_states(),
            hardware=HardwareModel(float(hw.get("source_rate_hz", 1e7)), float(hw.get("fibre_loss_db_per_km", 0.2)),
                                   float(hw.get("detector_efficiency", 0.9))),
            seed=settings.seed, principals={r["id"] for r in db.query("SELECT id FROM nodes WHERE role != 'adversary'")},
            next_seq=next_seq_factory(db),
        )
        self.world.quarantined = {r["id"] for r in db.query("SELECT id FROM links WHERE status='QUARANTINED'")}
        self.started_at = time.time()

    # ------------------------------------------------------------------ loading
    def _params(self, preset: str) -> ProtocolParams:
        return params_from_settings(self.settings.yaml, preset)

    def _load_groups(self) -> dict:
        return {g["id"]: GroupSpec(g["id"], g["signer_id"], tuple(loads(g["recipients"])), bool(g["hidden"]))
                for g in self.db.query("SELECT * FROM groups")}

    def _load_links(self) -> dict:
        out = {}
        secrets_ = {r["link_id"]: bytes(r["mac_key"]) for r in self.db.query("SELECT * FROM link_secrets")}
        for l in self.db.query("SELECT * FROM links WHERE kind='quantum'"):
            out[l["id"]] = LinkSpec(l["id"], l["a"], l["b"], loads(l["baseline_channel"]), l["length_km"],
                                    bool(l["authenticated_classical"]), secrets_.get(l["id"]))
        return out

    def _load_baselines(self) -> dict:
        out = {}
        for r in self.db.query("SELECT * FROM baselines"):
            try:
                out[r["link_id"]] = LinkBaseline.from_dict(loads(r["stats"]))
            except Exception:
                continue
        return out

    def _load_monitor_states(self) -> dict:
        return {r["link_id"]: loads(r["state"]) for r in self.db.query("SELECT * FROM link_monitor_state")}

    # ------------------------------------------------------------------ baselines
    def stale_links(self) -> list:
        out = []
        for lid, spec in self.world.links.items():
            b = self.world.baselines.get(lid)
            if b is None or b.spec_hash != spec_hash(list(spec.baseline)):
                out.append(lid)
        return out

    def calibrate(self, link_ids: list | None = None) -> list:
        ids = link_ids or list(self.world.links)
        with self.lock:
            res = self.world.calibrate(ids)
            for lid, b in res.items():
                self.db.execute("INSERT INTO baselines(link_id, calibrated_at, samples, spec_hash, stats) VALUES (?,?,?,?,?) "
                                "ON CONFLICT(link_id) DO UPDATE SET calibrated_at=excluded.calibrated_at, samples=excluded.samples, "
                                "spec_hash=excluded.spec_hash, stats=excluded.stats",
                                (lid, b.calibrated_at, b.samples, b.spec_hash, dumps(b.to_dict())))
                self.db.execute("DELETE FROM link_monitor_state WHERE link_id=?", (lid,))
        for lid in ids:
            self.hub.publish("links", "link.updated", self.link_status(lid))
        return [self.world.baselines[l].summary() for l in ids]

    # ------------------------------------------------------------------ status
    def link_status(self, link_id: str) -> dict:
        l = self.db.one("SELECT * FROM links WHERE id=?", (link_id,))
        if not l:
            raise ApiNotFound(link_id)
        last = self.db.one("SELECT * FROM link_monitor WHERE link_id=? ORDER BY t DESC LIMIT 1", (link_id,))
        b = self.world.baselines.get(link_id)
        return {
            "id": l["id"], "kind": l["kind"], "a": l["a"], "b": l["b"], "length_km": l["length_km"], "status": l["status"],
            "status_reason": l["status_reason"], "authenticated_classical": bool(l["authenticated_classical"]),
            "baseline_channel": loads(l["baseline_channel"]), "hidden": bool(l["hidden"]),
            "transmittance": self.world.hardware.transmittance(l["length_km"]) if l["kind"] == "quantum" else None,
            "last": ({k: last[k] for k in ("t", "qber", "chsh", "fidelity", "cusum_qber", "cusum_chsh", "ewma_qber",
                                           "h_qber", "h_chsh")} | {"alarm": bool(last["alarm"])}) if last else None,
            "baseline": ({"calibrated_at": b.calibrated_at, "qber": b.qber["rate"], "chsh": b.bell.S, "fidelity": b.bell.F,
                          "samples": b.samples} if b else None),
        }

    def network_view(self, include_hidden: bool = False) -> dict:
        hid = "" if include_hidden else " WHERE hidden=0"
        nodes = self.db.query(f"SELECT * FROM nodes{hid}")
        for n in nodes:
            n["pos"] = [n.pop("pos_x"), n.pop("pos_y"), n.pop("pos_z")]
            n["meta"] = loads(n["meta"])
            n["hidden"] = bool(n["hidden"])
            n["suspended"] = bool(n["suspended"])
        links = [self.link_status(l["id"]) for l in self.db.query(f"SELECT id FROM links{hid}")]
        groups = self.db.query(f"SELECT * FROM groups{hid}")
        for g in groups:
            g["recipients"] = loads(g["recipients"])
            g["hidden"] = bool(g["hidden"])
        return {"nodes": nodes, "links": links, "groups": groups}

    def reservoir(self) -> list:
        out = []
        for g in self.db.query("SELECT * FROM groups WHERE hidden=0"):
            counts = {r["status"]: r["n"] for r in self.db.query(
                "SELECT status, COUNT(*) AS n FROM bundles WHERE group_id=? GROUP BY status", (g["id"],))}
            last = self.db.scalar("SELECT MAX(created_at) FROM bundles WHERE group_id=?", (g["id"],))
            links = [self.world.link_between(g["signer_id"], v).link_id for v in loads(g["recipients"])]
            blocked = [l for l in links if l in self.world.quarantined]
            suspended = bool(self.db.scalar("SELECT suspended FROM nodes WHERE id=?", (g["signer_id"],)))
            out.append({"group_id": g["id"], "signer_id": g["signer_id"], "recipients": loads(g["recipients"]),
                        "active": counts.get("ACTIVE", 0), "target": g["reservoir_target"], "signed": counts.get("SIGNED", 0),
                        "consumed_total": counts.get("CONSUMED", 0), "compromised_total": counts.get("COMPROMISED", 0),
                        "revoked_total": counts.get("REVOKED", 0), "burned_total": counts.get("BURNED", 0),
                        "last_distribution_at": last,
                        "blocked_reason": (f"link {', '.join(blocked)} quarantined" if blocked else
                                           "signer suspended" if suspended else None)})
        return out

    def reservoir_active(self, group_id: str) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM bundles WHERE group_id=? AND status='ACTIVE'", (group_id,)) or 0)

    def _on_bundle_status(self, bundle_id: str, status: str) -> None:
        pass

    # ------------------------------------------------------------------ persistence helpers
    def _save_session(self, run, kind: str, origin: str, counterfactual: bool = False) -> dict:
        summary = run.summary()
        summary["origin"] = origin
        report = run.report()
        report["origin"] = origin
        inj = run.injected_attack
        if kind == "signature":
            env = run.envelope
            msg_preview, msg_sha, enc = env.message[:120], _sha(env.message), env.encoding
            signer, recips, bundle_id = env.signer_id, env.recipients, env.bundle_id
        else:
            msg_preview = msg_sha = enc = None
            signer, recips, bundle_id = run.group.signer_id, run.group.recipients, run.bundle_id
        a = run.assessment
        self.db.execute(
            "INSERT INTO sessions(id, kind, origin, group_id, bundle_id, signer_id, recipients, message_preview, message_sha256, "
            "encoding, injected_attack, attack_category, verdict, threat_level, category, subtype, threat_score, counterfactual, "
            "latency_ms, summary, report, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run.session_id, kind, origin, summary["group_id"], bundle_id, signer, dumps(list(recips)), msg_preview, msg_sha,
             enc, dumps(inj) if inj else None, (inj or {}).get("category"), a.verdict, a.threat_level,
             a.classification.category, a.classification.subtype, a.threat_score, int(counterfactual),
             summary.get("latency_ms"), dumps(summary), dumps(report), run.created_at))
        return summary

    def _worst_link(self, run) -> Optional[str]:
        best, link = -1, None
        for f in run.findings:
            if f.fired and f.link_id and SEVERITY_RANK[f.severity] > best:
                best, link = SEVERITY_RANK[f.severity], f.link_id
        return link

    def _after_distribution(self, run, origin: str) -> dict:
        summary = self._save_session(run, "distribution", origin)
        self.bundles.annotate(run.bundle_id, origin, run.session_id, summary, run.injected_attack)
        for lid, p in run.monitor_points.items():
            self.db.execute("INSERT INTO link_monitor(link_id, t, bundle_id, qber, chsh, fidelity, cusum_qber, cusum_chsh, "
                            "ewma_qber, h_qber, h_chsh, alarm) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (lid, run.created_at, run.bundle_id, p["qber"], p["chsh"], p["fidelity"], p["cusum_qber"],
                             p["cusum_chsh"], p["ewma_qber"], p.get("h_qber"), p.get("h_chsh"), int(bool(p["alarm"]))))
            self.db.execute("INSERT INTO link_monitor_state(link_id, state) VALUES (?,?) "
                            "ON CONFLICT(link_id) DO UPDATE SET state=excluded.state",
                            (lid, dumps(self.world.monitor_states.get(lid, {}))))
        a = run.assessment
        tx = self.ledger.append("BUNDLE_CERTIFIED" if a.verdict == "CERTIFIED" else "BUNDLE_COMPROMISED", {
            "session_id": run.session_id, "bundle_id": run.bundle_id, "group_id": run.group.group_id,
            "verdict": a.verdict, "category": a.classification.category, "subtype": a.classification.subtype,
            "links": summary["links"], "qubits": summary["qubits"]}, ref_id=run.session_id)
        inc = self.incidents.from_assessment(a.as_dict(), "distribution", run.session_id, run.group.group_id,
                                             run.bundle_id, self._worst_link(run))
        self.hub.publish("distributions", "distribution.completed", summary)
        for lid in {run.outcome.evidence[v].link_id for v in run.group.recipients}:
            self.hub.publish("links", "link.updated", self.link_status(lid))
        self.hub.publish("reservoir", "reservoir.updated", self.reservoir())
        return {"summary": summary, "incident_id": inc["id"] if inc else None, "ledger_tx": tx}

    def _after_signature(self, run, origin: str) -> dict:
        summary = self._save_session(run, "signature", origin)
        a = run.assessment
        tx = self.ledger.append("SIGNATURE_ACCEPTED" if a.verdict == "ACCEPTED" else "SIGNATURE_REJECTED", {
            "session_id": run.session_id, "group_id": run.group_id, "signer_id": run.envelope.signer_id,
            "bundle_id": run.envelope.bundle_id, "message_sha256": _sha(run.envelope.message), "verdict": a.verdict,
            "decisions": summary["decisions"], "category": a.classification.category, "subtype": a.classification.subtype},
            ref_id=run.session_id)
        inc = self.incidents.from_assessment(a.as_dict(), "signature", run.session_id, run.group_id,
                                             run.envelope.bundle_id, None)
        self.hub.publish("sessions", "session.completed", summary)
        self.hub.publish("reservoir", "reservoir.updated", self.reservoir())
        return {"summary": summary, "incident_id": inc["id"] if inc else None, "ledger_tx": tx}

    # ------------------------------------------------------------------ operations
    def _check_signer(self, group_id: str) -> GroupSpec:
        try:
            g = self.world.group(group_id)
        except KeyError:
            raise ApiNotFound(f"group {group_id}") from None
        if self.db.scalar("SELECT suspended FROM nodes WHERE id=?", (g.signer_id,)):
            raise ApiConflict("SIGNER_SUSPENDED", f"signer {g.signer_id} is suspended", {"signer_id": g.signer_id})
        return g

    def distribute(self, group_id: str, origin: str = "API", preset: str | None = None) -> dict:
        self._check_signer(group_id)
        from sentinel.world import LinkQuarantined

        with self.lock:
            try:
                run = self.world.distribute(group_id, params=self._params(preset) if preset else None, origin=origin)
            except LinkQuarantined as exc:
                raise ApiConflict("LINK_QUARANTINED", str(exc), {"group_id": group_id}) from None
            post = self._after_distribution(run, origin)
        report = run.report()
        report["incident_id"] = post["incident_id"]
        report["ledger"] = {"tx_id": post["ledger_tx"], "status": "pending"}
        return report

    def sign_and_verify(self, group_id: str, message: str, encoding: str = "sha256", bundle_id: str | None = None,
                        origin: str = "API", auto_distribute: bool = True) -> dict:
        self._check_signer(group_id)
        from sentinel.protocol.encoding import MAX_MESSAGE_BYTES, RAW_MAX_BYTES, MessageTooLong
        from sentinel.world import BundleCompromised, BundleUnavailable, LinkQuarantined

        size = len(message.encode("utf-8"))
        limit = RAW_MAX_BYTES if encoding == "raw" else MAX_MESSAGE_BYTES
        if size > limit:  # checked before any key material is spent
            raise ApiConflict("MESSAGE_TOO_LONG", f"{encoding} encoding signs at most {limit} bytes; message is {size}")

        with self.lock:
            try:
                if bundle_id is None and not self.world.bundles.active_ids(group_id):
                    if not auto_distribute:
                        raise BundleUnavailable(f"no ACTIVE bundle for group {group_id}")
                    self.distribute(group_id, origin="RESERVOIR")
                    if not self.world.bundles.active_ids(group_id):
                        raise BundleUnavailable(f"a fresh distribution for {group_id} was not certified")
                run = self.world.sign_and_verify(group_id, message, encoding, bundle_id=bundle_id, origin=origin)
            except BundleUnavailable as exc:
                raise ApiConflict("BUNDLE_UNAVAILABLE", str(exc), {"group_id": group_id}) from None
            except BundleCompromised as exc:
                raise ApiConflict("BUNDLE_COMPROMISED", str(exc), {"group_id": group_id}) from None
            except LinkQuarantined as exc:
                raise ApiConflict("LINK_QUARANTINED", str(exc), {"group_id": group_id}) from None
            except MessageTooLong as exc:
                raise ApiConflict("MESSAGE_TOO_LONG", str(exc), {}) from None
            post = self._after_signature(run, origin)
        report = run.report()
        report["incident_id"] = post["incident_id"]
        report["ledger"] = {"tx_id": post["ledger_tx"], "status": "pending"}
        return report

    def run_attack(self, spec: dict, group_id: str = "g-alice", message: str | None = None,
                   counterfactual: bool = True, origin: str = "LAB") -> dict:
        from sentinel.adversary.catalog import AttackSpecError
        from sentinel.world import BundleUnavailable, LinkQuarantined

        attack = AttackSpec.from_dict(spec)
        entry = catalog_entry(attack.attack_id)
        self._check_signer(group_id)
        with self.lock:
            try:
                run = self.world.run_attack(attack, group_id=group_id, message=message, counterfactual=counterfactual,
                                            origin=origin)
            except AttackSpecError as exc:
                raise ApiConflict("VALIDATION_ERROR", str(exc), {}) from None
            except LinkQuarantined as exc:
                raise ApiConflict("LINK_QUARANTINED", str(exc), {"group_id": group_id}) from None
            except BundleUnavailable as exc:
                raise ApiConflict("BUNDLE_UNAVAILABLE", str(exc), {"group_id": group_id}) from None
            incident = None
            for s in run.setup:
                self._after_signature(s, origin)
            if run.distribution is not None:
                incident = self._after_distribution(run.distribution, origin)["incident_id"]
            if run.signature is not None:
                incident = self._after_signature(run.signature, origin)["incident_id"] or incident
            report = run.report()
            report["incident_id"] = incident
            report["id"] = (run.distribution or run.signature).session_id
            self.db.execute("INSERT INTO attack_runs(id, attack_id, category, group_id, origin, detected, correct, report, created_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (report["id"], attack.attack_id, entry["category"], group_id, origin, int(run.detected),
                             int(run.correctly_classified), dumps(report), run.created_at))
        return report

    def reverify(self, session_id: str, verifier_id: str | None = None, delay_s: float = 0.0) -> dict:
        with self.lock:
            cap = next((c for c in self.world.capture if c.session_id == session_id), None)
            if cap is None:
                raise ApiNotFound("signature not in the capture buffer (only the last 16 accepted signatures are kept)")
            now = time.time() + delay_s
            run = self.world.deliver(cap.signature.copy(), to=verifier_id, now=now, origin="API",
                                     injected_attack={"attack_id": "replay.resubmit", "category": "REPLAY",
                                                      "subtype": "resubmission"})
            post = self._after_signature(run, "API")
        rep = run.report()
        rep["incident_id"] = post["incident_id"]
        return rep

    def captured(self) -> list:
        return [{"session_id": c.session_id, "group_id": c.group_id, "at": c.at, "message": c.signature.envelope.message[:80]}
                for c in reversed(self.world.capture)]

    # ------------------------------------------------------------------ links and responses
    def set_link_status(self, link_id: str, status: str, reason: str = "") -> dict:
        if not self.db.one("SELECT 1 FROM links WHERE id=?", (link_id,)):
            raise ApiNotFound(link_id)
        self.db.execute("UPDATE links SET status=?, status_reason=?, updated_at=? WHERE id=?",
                        (status, reason or None, time.time(), link_id))
        with self.lock:
            if status == "QUARANTINED":
                self.world.quarantined.add(link_id)
            else:
                self.world.quarantined.discard(link_id)
        self.ledger.append("LINK_STATE", {"link_id": link_id, "status": status, "reason": reason[:300]}, ref_id=link_id)
        st = self.link_status(link_id)
        self.hub.publish("links", "link.updated", st)
        self.hub.publish("reservoir", "reservoir.updated", self.reservoir())
        return st

    def groups_on_link(self, link_id: str) -> list:
        spec = self.world.links.get(link_id)
        if spec is None:
            return []
        return [g.group_id for g in self.world.groups.values()
                if g.signer_id == spec.signer_id and spec.verifier_id in g.recipients]

    def revoke_link_bundles(self, link_id: str) -> dict:
        n = 0
        with self.lock:
            for gid in self.groups_on_link(link_id):
                for bid in self.world.bundles.active_ids(gid):
                    self.bundles.set_status(bid, "REVOKED")
                    self.bundles.shred(bid, labels_only=True)
                    n += 1
        self.hub.publish("reservoir", "reservoir.updated", self.reservoir())
        return {"revoked": n}

    def certify_link(self, link_id: str) -> dict:
        """Fresh certification run over the link (demo-size, not stored). Releases quarantine if clean."""
        groups = self.groups_on_link(link_id)
        if not groups:
            raise ApiNotFound(f"no group uses link {link_id}")
        with self.lock:
            q = link_id in self.world.quarantined
            self.world.quarantined.discard(link_id)
            try:
                run = self.world.distribute(groups[0], params=self._params("demo"), store=False, update_monitors=False,
                                            origin="CALIBRATION")
            finally:
                if q:
                    self.world.quarantined.add(link_id)
        bad = [f.as_dict() for f in run.findings if f.fired and f.link_id == link_id
               and SEVERITY_RANK[f.severity] >= SEVERITY_RANK["HIGH"]]
        certified = not bad
        if certified:
            with self.lock:
                self.world.monitor_states.pop(link_id, None)
            self.db.execute("DELETE FROM link_monitor_state WHERE link_id=?", (link_id,))
            if q:
                self.set_link_status(link_id, "ACTIVE", "re-certified")
        ev = next(run.outcome.evidence[v] for v in run.group.recipients if run.outcome.evidence[v].link_id == link_id)
        return {"link_id": link_id, "certified": certified, "was_quarantined": q, "findings": bad,
                "bell": ev.bell.as_dict(), "qber": ev.qber["rate"], "frame": ev.frame,
                "fingerprint": next((f.data.get("fingerprint") for f in run.findings
                                     if f.id.startswith("D5.") and f.link_id == link_id), None),
                "at": time.time(), "status": self.link_status(link_id)}

    def patch_link(self, link_id: str, baseline_channel=None, authenticated_classical=None, length_km=None) -> dict:
        l = self.db.one("SELECT * FROM links WHERE id=?", (link_id,))
        if not l:
            raise ApiNotFound(link_id)
        recal = False
        if baseline_channel is not None:
            specs = normalise_specs(baseline_channel)
            self.db.execute("UPDATE links SET baseline_channel=?, updated_at=? WHERE id=?", (dumps(specs), time.time(), link_id))
            recal = True
        if authenticated_classical is not None:
            self.db.execute("UPDATE links SET authenticated_classical=?, updated_at=? WHERE id=?",
                            (int(bool(authenticated_classical)), time.time(), link_id))
        if length_km is not None:
            self.db.execute("UPDATE links SET length_km=?, updated_at=? WHERE id=?", (float(length_km), time.time(), link_id))
        with self.lock:
            self.world.links = self._load_links()
        if recal and l["kind"] == "quantum":
            self.calibrate([link_id])
        self.ledger.append("LINK_STATE", {"link_id": link_id, "change": {"baseline_channel": baseline_channel is not None,
                                                                         "authenticated_classical": authenticated_classical,
                                                                         "length_km": length_km}}, ref_id=link_id)
        st = self.link_status(link_id)
        self.hub.publish("links", "link.updated", st)
        return st

    def suspend_signer(self, signer_id: str, suspended: bool = True) -> dict:
        if not self.db.one("SELECT id FROM nodes WHERE id=? AND role != 'adversary'", (signer_id,)):
            raise ApiNotFound(f"node {signer_id}")
        self.db.execute("UPDATE nodes SET suspended=? WHERE id=?", (int(suspended), signer_id))
        self.ledger.append("SIGNER_SUSPENDED" if suspended else "SIGNER_REINSTATED", {"signer_id": signer_id}, ref_id=signer_id)
        self.hub.publish("links", "node.updated", {"id": signer_id, "suspended": suspended})
        self.hub.publish("reservoir", "reservoir.updated", self.reservoir())
        return {"signer_id": signer_id, "suspended": suspended}

    def respond(self, incident_id: str, action: str) -> dict:
        inc = self.incidents.get(incident_id)
        if not inc:
            raise ApiNotFound(incident_id)
        link = inc.get("link_id")
        group = inc.get("group_id")
        if action == "quarantine_link":
            if not link:
                raise ApiConflict("NO_LINK", "this incident is not tied to a link")
            result = {"link": self.set_link_status(link, "QUARANTINED", f"incident {incident_id[:8]}")}
        elif action == "release_link":
            if not link:
                raise ApiConflict("NO_LINK", "this incident is not tied to a link")
            result = {"link": self.set_link_status(link, "ACTIVE", f"released after incident {incident_id[:8]}")}
        elif action == "recertify_link":
            if not link:
                raise ApiConflict("NO_LINK", "this incident is not tied to a link")
            result = self.certify_link(link)
        elif action == "revoke_link_bundles":
            if not link:
                raise ApiConflict("NO_LINK", "this incident is not tied to a link")
            result = self.revoke_link_bundles(link)
        elif action == "enable_mac":
            if not link:
                raise ApiConflict("NO_LINK", "this incident is not tied to a link")
            result = {"link": self.patch_link(link, authenticated_classical=True)}
        elif action in ("suspend_signer", "reinstate_signer"):
            signer = self.world.groups[group].signer_id if group in self.world.groups else None
            if not signer:
                raise ApiConflict("NO_SIGNER", "no signer for this incident")
            result = self.suspend_signer(signer, action == "suspend_signer")
        elif action in ("flag_principal", "notify_recipients", "escalate_dispute", "review_capture_source",
                        "deny_principal", "use_larger_L"):
            result = {"recorded": True, "note": "Informational action recorded on the incident and in the ledger."}
        else:
            raise ApiConflict("VALIDATION_ERROR", f"unknown action {action!r}")
        inc = self.incidents.record(incident_id, action, result)
        return {"incident": inc, "result": result}

    # ------------------------------------------------------------------ settings
    def set_preset(self, preset: str) -> dict:
        params = self._params(preset)
        with self.lock:
            self.world.params = params
            self.preset = preset
        self.db.execute("INSERT INTO kv_settings(key, value) VALUES ('preset', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (dumps(preset),))
        return params.as_dict()

    def set_detection(self, patch: dict) -> dict:
        cfg = DetectionConfig(**{**self.detection.as_dict(), **patch}).validate()
        with self.lock:
            self.detection = cfg
            self.world.detection = cfg
        self.db.execute("INSERT INTO kv_settings(key, value) VALUES ('detection', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (dumps(cfg.as_dict()),))
        return cfg.as_dict()

    def presets(self) -> dict:
        out = {}
        for name in ("demo", "standard", "high", "analysis"):
            p = self._params(name)
            out[name] = p.as_dict()
        return out

    def engine_info(self) -> dict:
        return {"engine_version": ENGINE_VERSION, "preset": self.preset, "uptime_s": time.time() - self.started_at}
