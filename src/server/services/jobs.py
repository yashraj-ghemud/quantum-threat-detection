"""
server/services/jobs.py
=======================
Background analytics jobs: one worker thread, cooperative cancellation,
progress events over the WebSocket, results persisted in SQLite.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from sentinel.analysis.jobs import JOB_KINDS, run_job
from server.db.database import Database, dumps, loads

__all__ = ["JobManager", "JobConflict"]


class JobConflict(Exception):
    pass


class JobManager:
    def __init__(self, db: Database, hub) -> None:
        self.db = db
        self.hub = hub
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qveris-job")
        self.cancels: dict = {}
        # Jobs interrupted by a restart are marked failed.
        self.db.execute("UPDATE jobs SET status='FAILED', error='interrupted by server restart', finished_at=? "
                        "WHERE status IN ('QUEUED','RUNNING')", (time.time(),))

    def submit(self, kind: str, params: dict | None = None, preset: str = "quick") -> dict:
        if kind not in JOB_KINDS:
            raise KeyError(kind)
        if preset not in ("quick", "full"):
            raise ValueError("preset must be quick or full")
        running = self.db.scalar("SELECT id FROM jobs WHERE kind=? AND status IN ('QUEUED','RUNNING')", (kind,))
        if running:
            raise JobConflict(running)
        jid = str(uuid.uuid4())
        now = time.time()
        self.db.execute("INSERT INTO jobs(id, kind, preset, params, status, created_at) VALUES (?,?,?,?,?,?)",
                        (jid, kind, preset, dumps(params or {}), "QUEUED", now))
        ev = threading.Event()
        self.cancels[jid] = ev
        self.pool.submit(self._run, jid, kind, params or {}, preset, ev)
        job = self.get(jid)
        self.hub.publish("jobs", "job.progress", self._brief(job))
        return job

    def _brief(self, job: dict) -> dict:
        return {k: job.get(k) for k in ("id", "kind", "preset", "status", "progress", "message", "created_at",
                                        "started_at", "finished_at", "error")}

    def _run(self, jid: str, kind: str, params: dict, preset: str, cancel: threading.Event) -> None:
        self.db.execute("UPDATE jobs SET status='RUNNING', started_at=? WHERE id=?", (time.time(), jid))
        last = {"t": 0.0, "p": -1.0}

        def progress(frac: float, message: str) -> None:
            now = time.time()
            if frac - last["p"] < 0.01 and now - last["t"] < 0.25:
                return
            last.update(t=now, p=frac)
            self.db.execute("UPDATE jobs SET progress=?, message=? WHERE id=?", (float(frac), message[:200], jid))
            self.hub.publish("jobs", "job.progress", {"id": jid, "kind": kind, "status": "RUNNING",
                                                      "progress": float(frac), "message": message})

        try:
            result = run_job(kind, params, preset, progress, cancel)
            status = "CANCELLED" if cancel.is_set() else "SUCCEEDED"
            self.db.execute("UPDATE jobs SET status=?, progress=1, result=?, finished_at=?, message=? WHERE id=?",
                            (status, dumps(result), time.time(), "done", jid))
        except Exception as exc:  # pragma: no cover - reported to the user
            self.db.execute("UPDATE jobs SET status='FAILED', error=?, finished_at=? WHERE id=?",
                            (f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}"[:4000], time.time(), jid))
        finally:
            self.cancels.pop(jid, None)
            job = self.get(jid, with_result=False)
            self.hub.publish("jobs", "job.completed", self._brief(job))

    def get(self, jid: str, with_result: bool = True) -> Optional[dict]:
        r = self.db.one("SELECT * FROM jobs WHERE id=?", (jid,))
        if not r:
            return None
        r["params"] = loads(r["params"])
        r["result"] = loads(r["result"]) if with_result else None
        return r

    def list(self, kind: str | None = None, limit: int = 20) -> list:
        if kind:
            rows = self.db.query("SELECT id, kind, preset, params, status, progress, message, error, created_at, started_at, "
                                 "finished_at FROM jobs WHERE kind=? ORDER BY created_at DESC LIMIT ?", (kind, limit))
        else:
            rows = self.db.query("SELECT id, kind, preset, params, status, progress, message, error, created_at, started_at, "
                                 "finished_at FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
        for r in rows:
            r["params"] = loads(r["params"])
        return rows

    def latest(self, kind: str) -> Optional[dict]:
        r = self.db.one("SELECT id FROM jobs WHERE kind=? AND status='SUCCEEDED' ORDER BY finished_at DESC LIMIT 1", (kind,))
        return self.get(r["id"]) if r else None

    def cancel(self, jid: str) -> Optional[dict]:
        ev = self.cancels.get(jid)
        if ev:
            ev.set()
        return self.get(jid, with_result=False)

    def shutdown(self) -> None:
        for ev in self.cancels.values():
            ev.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
