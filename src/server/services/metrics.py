"""
server/services/metrics.py
==========================
Aggregates over stored sessions. Detection figures use the ground truth
recorded with every session (``injected_attack``); counterfactual runs are
excluded, and so is analytics traffic (it never reaches the database).
"""

from __future__ import annotations

import math
import time

from sentinel.stats import clopper_pearson
from server.db.database import Database, loads

__all__ = ["MetricsService", "WINDOWS"]

WINDOWS = {"all": None, "24h": 86400, "1h": 3600, "15m": 900}
CATS = ["FORGERY", "IMPERSONATION", "REPLAY", "UNAUTHORIZED_VERIFICATION", "CHANNEL_MANIPULATION", "REPUDIATION"]


def _flagged_sql() -> str:
    return "(verdict IN ('COMPROMISED','REJECTED') OR (category IS NOT NULL AND category NOT IN ('NONE','POLICY')))"


class MetricsService:
    def __init__(self, db: Database, engine, incidents, ledger, traffic=None) -> None:
        self.db = db
        self.engine = engine
        self.incidents = incidents
        self.ledger = ledger
        self.traffic = traffic

    def _since(self, window: str) -> float:
        w = WINDOWS.get(window)
        return 0.0 if w is None else time.time() - w

    def summary(self, window: str = "all") -> dict:
        since = self._since(window)
        base = "FROM sessions WHERE counterfactual=0 AND created_at >= ?"
        sig = self.db.one(f"SELECT COUNT(*) AS n, SUM(verdict='ACCEPTED') AS acc, SUM(verdict='REJECTED') AS rej {base} AND kind='signature'", (since,))
        dist = self.db.one(f"SELECT COUNT(*) AS n, SUM(verdict='CERTIFIED') AS cert, SUM(verdict='COMPROMISED') AS comp {base} AND kind='distribution'", (since,))
        by_origin = {r["origin"]: r["n"] for r in self.db.query(f"SELECT origin, COUNT(*) AS n {base} AND kind='signature' GROUP BY origin", (since,))}
        legit = self.db.one(f"SELECT COUNT(*) AS n, SUM({_flagged_sql()}) AS bad {base} AND injected_attack IS NULL", (since,))
        att = self.db.one(f"SELECT COUNT(*) AS n, SUM({_flagged_sql()}) AS det, SUM(category = attack_category) AS correct "
                          f"{base} AND injected_attack IS NOT NULL", (since,))
        ln, lb = legit["n"] or 0, legit["bad"] or 0
        an, ad, ac = att["n"] or 0, att["det"] or 0, att["correct"] or 0
        per_cat = []
        for c in CATS:
            r = self.db.one(f"SELECT COUNT(*) AS n, SUM({_flagged_sql()}) AS det, SUM(category = attack_category) AS correct "
                            f"{base} AND attack_category=?", (since, c))
            n = r["n"] or 0
            lo, hi = clopper_pearson(r["det"] or 0, n, 0.05) if n else (None, None)
            per_cat.append({"category": c, "runs": n, "detected": r["det"] or 0, "correct": r["correct"] or 0,
                            "rate": (r["det"] or 0) / n if n else None, "ci": [lo, hi] if n else None})
        frr_ci = list(clopper_pearson(lb, ln, 0.05)) if ln else None
        far_ci = list(clopper_pearson(an - ad, an, 0.05)) if an else None
        lat = [r["latency_ms"] for r in self.db.query(
            "SELECT latency_ms FROM sessions WHERE kind='signature' AND counterfactual=0 AND latency_ms IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 200")]
        lat.sort()

        def pct(p):
            if not lat:
                return None
            return lat[min(len(lat) - 1, int(math.ceil(p * len(lat))) - 1)]

        per_min = self.db.scalar("SELECT COUNT(*) FROM sessions WHERE kind='signature' AND counterfactual=0 AND created_at >= ?",
                                 (time.time() - 60,))
        lsum = self.ledger.summary()
        chsh = self.db.query("SELECT chsh FROM link_monitor ORDER BY t DESC LIMIT 20")
        return {
            "window": window, "generated_at": time.time(),
            "sessions": {"signature_total": sig["n"] or 0, "accepted": sig["acc"] or 0, "rejected": sig["rej"] or 0,
                         "by_origin": by_origin},
            "distributions": {"total": dist["n"] or 0, "certified": dist["cert"] or 0, "compromised": dist["comp"] or 0},
            "detection": {
                "legit_runs": ln, "false_rejections": lb, "frr": lb / ln if ln else None, "frr_ci": frr_ci,
                "attack_runs": an, "detected": ad, "far": (an - ad) / an if an else None, "far_ci": far_ci,
                "detection_rate": ad / an if an else None,
                "correctly_classified": ac, "classification_accuracy": ac / an if an else None,
                "per_category": per_cat},
            "throughput_per_min": per_min or 0,
            "latency_ms": {"p50": pct(0.5), "p95": pct(0.95)},
            "mean_chsh_recent": (sum(r["chsh"] for r in chsh) / len(chsh)) if chsh else None,
            "links": [self.engine.link_status(r["id"]) for r in self.db.query("SELECT id FROM links WHERE kind='quantum' AND hidden=0")],
            "reservoir": self.engine.reservoir(),
            "ledger": {"height": lsum["height"], "tx_total": lsum["tx_total"], "pending": lsum["pending"], "head_hash": lsum["head_hash"]},
            "incidents": {"open": sum(self.incidents.open_counts().values()), "by_severity": self.incidents.open_counts()},
            "threat_level": self.incidents.threat_level(),
            "traffic": self.traffic.state() if self.traffic else None,
        }

    def tick(self) -> dict:
        now = time.time()
        r = self.db.one("SELECT COUNT(*) AS n, SUM(verdict='ACCEPTED') AS acc, SUM(verdict='REJECTED') AS rej FROM sessions "
                        "WHERE kind='signature' AND counterfactual=0 AND created_at >= ?", (now - 60,))
        return {"sessions_per_min": r["n"] or 0, "accepted_last_min": r["acc"] or 0, "rejected_last_min": r["rej"] or 0,
                "threat_level": self.incidents.threat_level(), "open_incidents": sum(self.incidents.open_counts().values()),
                "ledger_height": self.ledger.summary()["height"],
                "reservoir_total": sum(x["active"] for x in self.engine.reservoir()), "time": now}

    def timeseries(self, series: str, window: str = "1h", bucket_s: int = 60, link_id: str | None = None) -> dict:
        since = self._since(window) or (time.time() - 3600)
        bucket_s = max(5, int(bucket_s))
        if series == "qber":
            args = [since]
            sql = "SELECT link_id, t, qber, chsh, fidelity, cusum_qber, cusum_chsh, ewma_qber, h_qber, h_chsh, alarm FROM link_monitor WHERE t >= ?"
            if link_id:
                sql += " AND link_id=?"
                args.append(link_id)
            sql += " ORDER BY t"
            return {"series": series, "points": self.db.query(sql, args)}
        rows = self.db.query("SELECT kind, verdict, category, latency_ms, created_at, injected_attack IS NOT NULL AS attack "
                             "FROM sessions WHERE counterfactual=0 AND created_at >= ? ORDER BY created_at", (since,))
        buckets: dict = {}
        for r in rows:
            b = int(r["created_at"] // bucket_s) * bucket_s
            d = buckets.setdefault(b, {"t": b, "signatures": 0, "accepted": 0, "rejected": 0, "distributions": 0,
                                       "compromised": 0, "attacks": 0, "latency_sum": 0.0, "latency_n": 0})
            if r["kind"] == "signature":
                d["signatures"] += 1
                d["accepted"] += int(r["verdict"] == "ACCEPTED")
                d["rejected"] += int(r["verdict"] == "REJECTED")
                if r["latency_ms"]:
                    d["latency_sum"] += r["latency_ms"]
                    d["latency_n"] += 1
            else:
                d["distributions"] += 1
                d["compromised"] += int(r["verdict"] == "COMPROMISED")
            d["attacks"] += int(r["attack"])
        pts = []
        for b in sorted(buckets):
            d = buckets[b]
            d["latency_ms"] = d["latency_sum"] / d["latency_n"] if d["latency_n"] else None
            del d["latency_sum"], d["latency_n"]
            pts.append(d)
        return {"series": series, "bucket_s": bucket_s, "points": pts}

    def prometheus(self) -> str:
        s = self.summary("all")
        lines = [
            "# HELP qveris_signatures_total Signature sessions by verdict",
            "# TYPE qveris_signatures_total counter",
            f'qveris_signatures_total{{verdict="accepted"}} {s["sessions"]["accepted"]}',
            f'qveris_signatures_total{{verdict="rejected"}} {s["sessions"]["rejected"]}',
            "# TYPE qveris_distributions_total counter",
            f'qveris_distributions_total{{verdict="certified"}} {s["distributions"]["certified"]}',
            f'qveris_distributions_total{{verdict="compromised"}} {s["distributions"]["compromised"]}',
            "# TYPE qveris_open_incidents gauge",
            f"qveris_open_incidents {s['incidents']['open']}",
            "# TYPE qveris_ledger_height gauge",
            f"qveris_ledger_height {s['ledger']['height']}",
        ]
        for c in s["detection"]["per_category"]:
            lines.append(f'qveris_attack_runs_total{{category="{c["category"]}"}} {c["runs"]}')
            lines.append(f'qveris_attacks_detected_total{{category="{c["category"]}"}} {c["detected"]}')
        for r in s["reservoir"]:
            lines.append(f'qveris_reservoir_active{{group="{r["group_id"]}"}} {r["active"]}')
        return "\n".join(lines) + "\n"
