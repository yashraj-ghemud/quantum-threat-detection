"""
server/services/incidents.py
============================
Incidents: opened from assessments, aggregated when repeated, acknowledged,
resolved, and answered with response actions.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from sentinel.detection.findings import SEVERITY_RANK
from server.db.database import Database, dumps, loads

__all__ = ["IncidentService", "PRETTY"]

PRETTY = {
    "FORGERY": "Forgery", "IMPERSONATION": "Impersonation", "REPLAY": "Replay",
    "UNAUTHORIZED_VERIFICATION": "Unauthorized verification", "CHANNEL_MANIPULATION": "Channel manipulation",
    "REPUDIATION": "Repudiation", "DEGRADED": "Degraded link", "POLICY": "Policy block",
}
DEDUP_WINDOW_S = 60.0


def _pretty_sub(s: Optional[str]) -> str:
    return (s or "").replace("_", " ")


class IncidentService:
    def __init__(self, db: Database, ledger, hub=None) -> None:
        self.db = db
        self.ledger = ledger
        self.hub = hub

    def from_assessment(self, assessment: dict, kind: str, session_id: str, group_id: str | None,
                        bundle_id: str | None, link_id: str | None) -> Optional[dict]:
        level = assessment["threat_level"]
        cls = assessment["classification"]
        cat = cls["category"]
        if SEVERITY_RANK.get(level, 0) < SEVERITY_RANK["MEDIUM"] or cat == "NONE":
            return None
        sub = cls.get("subtype")
        now = time.time()
        existing = self.db.one(
            "SELECT * FROM incidents WHERE status='OPEN' AND category=? AND COALESCE(subtype,'')=? "
            "AND COALESCE(link_id,'')=? AND COALESCE(group_id,'')=? AND updated_at > ? ORDER BY updated_at DESC LIMIT 1",
            (cat, sub or "", link_id or "", group_id or "", now - DEDUP_WINDOW_S))
        if existing:
            sev = existing["severity"] if SEVERITY_RANK[existing["severity"]] >= SEVERITY_RANK[level] else level
            self.db.execute("UPDATE incidents SET occurrences=occurrences+1, updated_at=?, severity=?, session_id=?, "
                            "assessment=? WHERE id=?", (now, sev, session_id, dumps(assessment), existing["id"]))
            inc = self.get(existing["id"])
            if self.hub:
                self.hub.publish("incidents", "incident.updated", self.summary_of(inc))
            return inc
        where = link_id or group_id or "network"
        title = f"{PRETTY.get(cat, cat.title())}: {_pretty_sub(sub)} on {where}" if sub else f"{PRETTY.get(cat, cat)} on {where}"
        iid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO incidents(id, created_at, updated_at, severity, category, subtype, title, summary, link_id, group_id, "
            "session_id, bundle_id, status, assessment, actions, recommended, attributed_to) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (iid, now, now, level, cat, sub, title, cls.get("explanation", "")[:2000], link_id, group_id, session_id,
             bundle_id, "OPEN", dumps(assessment), "[]", dumps(assessment.get("recommended_actions", [])),
             cls.get("attributed_to")))
        tx = self.ledger.append("INCIDENT", {"incident_id": iid, "severity": level, "category": cat, "subtype": sub,
                                              "session_id": session_id, "kind": kind, "link_id": link_id,
                                              "evidence_sha256": _digest(assessment)}, ref_id=iid)
        self.db.execute("UPDATE incidents SET ledger_tx_id=? WHERE id=?", (tx, iid))
        inc = self.get(iid)
        if self.hub:
            self.hub.publish("incidents", "incident.opened", self.summary_of(inc))
        return inc

    # -- reading ------------------------------------------------------------------
    def get(self, iid: str) -> Optional[dict]:
        r = self.db.one("SELECT * FROM incidents WHERE id=?", (iid,))
        if not r:
            return None
        r["assessment"] = loads(r["assessment"])
        r["actions"] = loads(r["actions"])
        r["recommended"] = loads(r["recommended"])
        return r

    @staticmethod
    def summary_of(r: dict) -> dict:
        return {k: r.get(k) for k in ("id", "created_at", "updated_at", "severity", "category", "subtype", "title",
                                      "summary", "link_id", "group_id", "session_id", "bundle_id", "occurrences",
                                      "status", "attributed_to", "ledger_tx_id")} | {"recommended": r.get("recommended")}

    def list(self, status=None, severity=None, category=None, limit=50, before=None) -> list:
        sql = "SELECT * FROM incidents WHERE 1=1"
        args: list = []
        if status:
            sql += " AND status=?"
            args.append(status)
        if severity:
            sql += " AND severity=?"
            args.append(severity)
        if category:
            sql += " AND category=?"
            args.append(category)
        if before:
            sql += " AND updated_at < ?"
            args.append(float(before))
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(int(limit))
        out = []
        for r in self.db.query(sql, args):
            r["recommended"] = loads(r["recommended"])
            out.append(self.summary_of(r))
        return out

    def open_counts(self) -> dict:
        rows = self.db.query("SELECT severity, COUNT(*) AS n FROM incidents WHERE status='OPEN' GROUP BY severity")
        return {r["severity"]: r["n"] for r in rows}

    def threat_level(self) -> str:
        """Worst severity among OPEN incidents (acknowledged ones are being handled)."""
        rows = self.db.query("SELECT severity FROM incidents WHERE status='OPEN'")
        best = "NONE"
        for r in rows:
            if SEVERITY_RANK[r["severity"]] > SEVERITY_RANK[best]:
                best = r["severity"]
        return best

    # -- workflow -----------------------------------------------------------------
    def _log(self, iid: str, action: str, note: str = "", result: dict | None = None) -> dict:
        inc = self.get(iid)
        entry = {"at": time.time(), "action": action, "note": note, "result": result or {}}
        actions = inc["actions"] + [entry]
        self.db.execute("UPDATE incidents SET actions=?, updated_at=? WHERE id=?", (dumps(actions), time.time(), iid))
        self.ledger.append("RESPONSE_ACTION", {"incident_id": iid, "action": action, "note": note[:500]}, ref_id=iid)
        inc = self.get(iid)
        if self.hub:
            self.hub.publish("incidents", "incident.updated", self.summary_of(inc))
        return inc

    def set_status(self, iid: str, status: str, note: str = "") -> dict:
        self.db.execute("UPDATE incidents SET status=?, updated_at=? WHERE id=?", (status, time.time(), iid))
        return self._log(iid, status.lower(), note)

    def record(self, iid: str, action: str, result: dict, note: str = "") -> dict:
        return self._log(iid, action, note, result)


def _digest(obj) -> str:
    from sentinel.ledger import canonical_json, sha256_hex

    return sha256_hex(canonical_json(obj))
