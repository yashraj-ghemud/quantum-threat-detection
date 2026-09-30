"""
server/context.py
=================
Wires every service together. One :class:`AppContext` per application.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from server.db.database import Database
from server.services.engine import EngineService
from server.services.hub import EventHub
from server.services.incidents import IncidentService
from server.services.jobs import JobManager
from server.services.ledger import LedgerService
from server.services.metrics import MetricsService
from server.services.selftest import SelfTest
from server.services.workers import CampaignRunner, TrafficController
from server.settings import Settings

__all__ = ["AppContext"]

log = logging.getLogger("qveris")


class AppContext:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.started_at = time.time()
        self.db = Database(settings.db_path)
        self.db.migrate()
        self.hub = EventHub()
        self.ledger = LedgerService(self.db, self.hub, settings.allow_tamper_demo)
        self.incidents = IncidentService(self.db, self.ledger, self.hub)
        self.engine = EngineService(settings, self.db, self.hub, self.ledger, self.incidents)
        self.executor = ThreadPoolExecutor(max_workers=max(1, settings.compute_workers), thread_name_prefix="qveris-compute")
        self.traffic = TrafficController(self.engine, self.hub, settings, self.executor)
        self.campaigns = CampaignRunner(self.engine, self.hub, self.executor)
        self.metrics = MetricsService(self.db, self.engine, self.incidents, self.ledger, self.traffic)
        self.jobs = JobManager(self.db, self.hub)
        self.selftest = SelfTest(self.hub, self.ledger, self.engine)
        self.hub.listeners.append(self.traffic.on_clients)

    def prune(self) -> dict:
        keep = self.settings.session_report_retention
        cutoff = self.db.scalar("SELECT created_at FROM sessions ORDER BY created_at DESC LIMIT 1 OFFSET ?", (keep,))
        stripped = 0
        if cutoff is not None:
            stripped = self.db.execute("UPDATE sessions SET report=NULL WHERE created_at <= ? AND report IS NOT NULL",
                                       (cutoff,)).rowcount
        self.db.execute("DELETE FROM nonces WHERE seen_at < ?", (time.time() - 86400,))
        self.db.execute("DELETE FROM link_monitor WHERE rowid IN (SELECT rowid FROM link_monitor ORDER BY t DESC LIMIT -1 OFFSET 20000)")
        files = self.engine.bundles.prune()
        return {"reports_stripped": stripped, "keystore_files_removed": files}

    def close(self) -> None:
        self.jobs.shutdown()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.db.close()
