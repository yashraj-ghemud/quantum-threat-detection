"""
server/services/stores.py
=========================
Persistent implementations of the engine's storage protocols.

- :class:`DbGuardStore`     nonces, sequence numbers and bundle consumption in SQLite
- :class:`DbBundleStore`    bundle rows in SQLite, material in ``data/keystore/*.npz``
- :func:`seed_topology`     first-start seeding of nodes, groups and links from YAML
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from sentinel.protocol.encoding import Envelope
from sentinel.protocol.keys import KeyBundle
from server.db.database import Database, dumps, loads

__all__ = ["DbGuardStore", "DbBundleStore", "seed_topology", "next_seq_factory"]


class DbGuardStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def nonce_seen(self, verifier_id: str, nonce: str) -> bool:
        return self.db.scalar("SELECT 1 FROM nonces WHERE verifier_id=? AND nonce=?", (verifier_id, nonce)) is not None

    def last_seq(self, signer_id: str, verifier_id: str) -> Optional[int]:
        return self.db.scalar("SELECT last_seq FROM signer_sequences WHERE signer_id=? AND verifier_id=?",
                              (signer_id, verifier_id))

    def consumed(self, bundle_id: str, verifier_id: str) -> bool:
        return self.db.scalar("SELECT 1 FROM bundle_consumption WHERE bundle_id=? AND verifier_id=?",
                              (bundle_id, verifier_id)) is not None

    def commit(self, verifier_id: str, envelope: Envelope, session_id: str, accepted: bool) -> None:
        now = time.time()
        with self.db.tx():
            self.db.execute("INSERT OR IGNORE INTO nonces(verifier_id, nonce, session_id, seen_at) VALUES (?,?,?,?)",
                            (verifier_id, envelope.nonce, session_id, now))
            self.db.execute("INSERT OR IGNORE INTO bundle_consumption(bundle_id, verifier_id, session_id, consumed_at) "
                            "VALUES (?,?,?,?)", (envelope.bundle_id, verifier_id, session_id, now))
            if accepted:
                self.db.execute(
                    "INSERT INTO signer_sequences(signer_id, verifier_id, last_seq) VALUES (?,?,?) "
                    "ON CONFLICT(signer_id, verifier_id) DO UPDATE SET last_seq=MAX(last_seq, excluded.last_seq)",
                    (envelope.signer_id, verifier_id, int(envelope.seq)))


class DbBundleStore:
    """Bundle rows in SQLite; material files in the keystore; a small LRU of loaded bundles."""

    def __init__(self, db: Database, keystore: Path, cache_size: int = 10) -> None:
        self.db = db
        self.keystore = Path(keystore)
        self.keystore.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.keystore, 0o700)
        except OSError:  # pragma: no cover
            pass
        self._cache: OrderedDict = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.RLock()
        self.on_status = None   # callback(bundle_id, status)

    def _path(self, bundle_id: str) -> Path:
        return self.keystore / f"{bundle_id}.npz"

    def _remember(self, b: KeyBundle) -> None:
        with self._lock:
            self._cache[b.bundle_id] = b
            self._cache.move_to_end(b.bundle_id)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    # -- protocol ----------------------------------------------------------------
    def put(self, bundle: KeyBundle, origin: str = "API", session_id: str | None = None,
            summary: dict | None = None, injected_attack: dict | None = None) -> None:
        path = self._path(bundle.bundle_id)
        bundle.save(path)
        now = time.time()
        self.db.execute(
            "INSERT INTO bundles(id, group_id, signer_id, recipients, preset, params, status, origin, design, summary, "
            "session_id, injected_attack, material_path, created_at, updated_at, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, design=excluded.design, updated_at=excluded.updated_at",
            (bundle.bundle_id, bundle.group_id, bundle.signer_id, dumps(list(bundle.recipients)), bundle.params.preset,
             dumps(bundle.params.as_dict()), bundle.status, origin, dumps(bundle.design), dumps(summary or {}),
             session_id, dumps(injected_attack) if injected_attack else None, str(path), bundle.created_at, now,
             bundle.created_at + 86400))
        self._remember(bundle)

    def annotate(self, bundle_id: str, origin: str, session_id: str, summary: dict, injected_attack: dict | None) -> None:
        self.db.execute("UPDATE bundles SET origin=?, session_id=?, summary=?, injected_attack=? WHERE id=?",
                        (origin, session_id, dumps(summary), dumps(injected_attack) if injected_attack else None, bundle_id))

    def get(self, bundle_id: str) -> Optional[KeyBundle]:
        with self._lock:
            b = self._cache.get(bundle_id)
            if b is not None:
                self._cache.move_to_end(bundle_id)
                return b
        path = self._path(bundle_id)
        if not path.exists():
            return None
        b = KeyBundle.load(path)
        row = self.meta(bundle_id)
        if row:
            b.status = row["status"]
            b.signed = row["status"] in ("SIGNED", "CONSUMED")
        self._remember(b)
        return b

    def meta(self, bundle_id: str) -> Optional[dict]:
        row = self.db.one("SELECT id, group_id, signer_id, recipients, status, created_at, design FROM bundles WHERE id=?",
                          (bundle_id,))
        if not row:
            return None
        return {"bundle_id": row["id"], "group_id": row["group_id"], "signer_id": row["signer_id"],
                "recipients": loads(row["recipients"]), "status": row["status"], "created_at": row["created_at"],
                "design": loads(row["design"])}

    def set_status(self, bundle_id: str, status: str) -> None:
        self.db.execute("UPDATE bundles SET status=?, updated_at=? WHERE id=?", (status, time.time(), bundle_id))
        with self._lock:
            b = self._cache.get(bundle_id)
            if b is not None:
                b.status = status
                if status in ("SIGNED", "CONSUMED"):
                    b.signed = True
        if self.on_status:
            self.on_status(bundle_id, status)

    def active_ids(self, group_id: str) -> list:
        rows = self.db.query("SELECT id FROM bundles WHERE group_id=? AND status='ACTIVE' AND expires_at > ? "
                             "ORDER BY created_at", (group_id, time.time()))
        return [r["id"] for r in rows]

    def shred(self, bundle_id: str, labels_only: bool = False) -> None:
        path = self._path(bundle_id)
        with self._lock:
            b = self._cache.get(bundle_id)
        if labels_only:
            if b is None and path.exists():
                b = KeyBundle.load(path)
            if b is not None:
                b.shred_labels()
                if path.exists():
                    b.save(path)
        else:
            with self._lock:
                self._cache.pop(bundle_id, None)
            if path.exists():
                path.unlink()

    # -- maintenance -------------------------------------------------------------
    def prune(self, keep_spent: int = 40) -> int:
        """Delete material of old spent bundles (records are kept for the most recent ones)."""
        rows = self.db.query("SELECT id FROM bundles WHERE status IN ('CONSUMED','COMPROMISED','REVOKED','EXPIRED','BURNED') "
                             "ORDER BY updated_at DESC LIMIT -1 OFFSET ?", (keep_spent,))
        n = 0
        for r in rows:
            p = self._path(r["id"])
            if p.exists():
                p.unlink()
                n += 1
            with self._lock:
                self._cache.pop(r["id"], None)
        self.db.execute("UPDATE bundles SET status='EXPIRED' WHERE status='ACTIVE' AND expires_at <= ?", (time.time(),))
        return n


def next_seq_factory(db: Database):
    def next_seq(group_id: str) -> int:
        with db.tx():
            db.execute("INSERT INTO signer_counters(group_id, next_seq) VALUES (?, 1) "
                       "ON CONFLICT(group_id) DO UPDATE SET next_seq = next_seq + 1", (group_id,))
            return int(db.scalar("SELECT next_seq FROM signer_counters WHERE group_id=?", (group_id,)))
    return next_seq


def seed_topology(db: Database, network: dict, reservoir_target: int) -> bool:
    """Insert nodes, groups and links on first start. Returns True if seeded."""
    if db.scalar("SELECT COUNT(*) FROM nodes"):
        return False
    now = time.time()
    with db.tx():
        for n in network["nodes"]:
            pos = n.get("pos", [0, 0, 0])
            db.execute("INSERT INTO nodes(id, name, role, label, color, pos_x, pos_y, pos_z, hidden, meta, created_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (n["id"], n.get("name", n["id"]), n["role"], n.get("label"), n.get("color"), pos[0], pos[1], pos[2],
                        int(bool(n.get("hidden"))), dumps({}), now))
        for g in network["groups"]:
            db.execute("INSERT INTO groups(id, signer_id, recipients, hidden, reservoir_target, created_at) VALUES (?,?,?,?,?,?)",
                       (g["id"], g["signer"], dumps(g["recipients"]), int(bool(g.get("hidden"))),
                        int(g.get("reservoir_target", reservoir_target)), now))
        for l in network["links"]:
            db.execute("INSERT INTO links(id, kind, a, b, length_km, baseline_channel, authenticated_classical, hidden, "
                       "updated_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (l["id"], l["kind"], l["a"], l["b"], float(l.get("length_km", 0)),
                        dumps(l.get("baseline_channel", [])), int(bool(l.get("authenticated_classical"))),
                        int(bool(l.get("hidden"))), now, now))
            if l["kind"] == "quantum":
                db.execute("INSERT INTO link_secrets(link_id, mac_key) VALUES (?,?)", (l["id"], secrets.token_bytes(32)))
    return True
