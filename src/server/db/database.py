"""
server/db/database.py
=====================
SQLite access: one connection (WAL) guarded by a re-entrant lock.

Every statement goes through :meth:`Database.execute` / :meth:`query`, so
access is serialised; writes inside ``with db.tx():`` are atomic.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

__all__ = ["Database", "dumps", "loads", "clean"]

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def clean(obj: Any) -> Any:
    """Recursively convert to strict JSON types: numpy → Python, NaN/±inf → None, sets/tuples → lists."""
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [clean(v) for v in obj]
    try:
        import numpy as np

        if isinstance(obj, np.ndarray):
            return clean(obj.tolist())
        if isinstance(obj, np.generic):
            return clean(obj.item())
    except Exception:  # pragma: no cover
        pass
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


def dumps(obj: Any) -> str:
    return json.dumps(clean(obj), separators=(",", ":"), allow_nan=False)


def loads(s: Optional[str]) -> Any:
    return None if s is None else json.loads(s)


def _default(o):
    try:
        import numpy as np

        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:  # pragma: no cover
        pass
    return str(o)


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
        self._depth = 0

    # -- migrations ------------------------------------------------------------
    def migrate(self) -> int:
        with self.lock:
            self.conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self.conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            current = row["v"] or 0
            for path in sorted(MIGRATIONS.glob("*.sql")):
                version = int(path.name.split("_", 1)[0])
                if version <= current:
                    continue
                sql = path.read_text(encoding="utf-8").replace("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);", "")
                self.conn.execute("BEGIN")
                try:
                    for stmt in _split(sql):
                        self.conn.execute(stmt)
                    self.conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
                    self.conn.execute("COMMIT")
                except Exception:
                    self.conn.execute("ROLLBACK")
                    raise
                current = version
            return current

    # -- access --------------------------------------------------------------------
    @contextmanager
    def tx(self):
        with self.lock:
            outer = self._depth == 0
            if outer:
                self.conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield self
                self._depth -= 1
                if outer:
                    self.conn.execute("COMMIT")
            except Exception:
                self._depth -= 1
                if outer:
                    self.conn.execute("ROLLBACK")
                raise

    def execute(self, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, tuple(params))

    def executemany(self, sql: str, rows: Iterable[Iterable]) -> None:
        with self.lock:
            self.conn.executemany(sql, [tuple(r) for r in rows])

    def query(self, sql: str, params: Iterable = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: Iterable = ()) -> Optional[dict]:
        with self.lock:
            r = self.conn.execute(sql, tuple(params)).fetchone()
            return dict(r) if r else None

    def scalar(self, sql: str, params: Iterable = ()) -> Any:
        with self.lock:
            r = self.conn.execute(sql, tuple(params)).fetchone()
            return r[0] if r else None

    def close(self) -> None:
        with self.lock:
            self.conn.close()


def _split(sql: str) -> list[str]:
    """Split a migration file into statements (no semicolons inside our DDL strings)."""
    out, buf = [], []
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("--") or not s:
            continue
        buf.append(line)
        if s.endswith(";"):
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return out
