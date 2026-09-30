"""
server/services/ledger.py
=========================
The hash-chained, Merkle-rooted security ledger.

Every verdict, incident and response action is appended as a transaction;
the block producer seals pending transactions into blocks.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from sentinel.ledger import (
    GENESIS_PREV, block_hash, block_header, canonical_json, inclusion_proof, merkle_levels, merkle_root, sha256_hex,
    verify_chain,
)
from server.db.database import Database, dumps, loads

__all__ = ["LedgerService"]


class LedgerService:
    def __init__(self, db: Database, hub=None, allow_tamper: bool = True) -> None:
        self.db = db
        self.hub = hub
        self.allow_tamper = allow_tamper
        self.last_verification: Optional[dict] = None
        self._ensure_genesis()

    def _ensure_genesis(self) -> None:
        if self.db.scalar("SELECT COUNT(*) FROM ledger_blocks"):
            return
        header = block_header(0, GENESIS_PREV, merkle_root([]), time.time(), 0)
        self.db.execute("INSERT INTO ledger_blocks(height, hash, prev_hash, merkle_root, timestamp, tx_count) VALUES (?,?,?,?,?,?)",
                        (0, block_hash(header), GENESIS_PREV, header["merkle_root"], header["timestamp"], 0))

    # -- writing ------------------------------------------------------------------
    def append(self, kind: str, payload: dict, ref_id: str | None = None) -> str:
        tx_id = str(uuid.uuid4())
        body = canonical_json({"kind": kind, **payload})
        self.db.execute("INSERT INTO ledger_txs(id, kind, payload, payload_hash, ref_id, created_at) VALUES (?,?,?,?,?,?)",
                        (tx_id, kind, body, sha256_hex(body), ref_id, time.time()))
        return tx_id

    def pending(self) -> list:
        return self.db.query("SELECT id, created_at FROM ledger_txs WHERE block_height IS NULL ORDER BY created_at, id")

    def maybe_seal(self, max_txs: int = 16, max_age_s: float = 8.0, force: bool = False) -> Optional[dict]:
        pend = self.pending()
        if not pend:
            return None
        oldest = pend[0]["created_at"]
        if not force and len(pend) < max_txs and time.time() - oldest < max_age_s:
            return None
        return self.seal([p["id"] for p in pend[:256]])

    def seal(self, tx_ids: list) -> dict:
        with self.db.tx():
            head = self.db.one("SELECT * FROM ledger_blocks ORDER BY height DESC LIMIT 1")
            rows = [self.db.one("SELECT id, payload_hash FROM ledger_txs WHERE id=?", (t,)) for t in tx_ids]
            leaves = [r["payload_hash"] for r in rows]
            height = head["height"] + 1
            header = block_header(height, head["hash"], merkle_root(leaves), time.time(), len(leaves))
            h = block_hash(header)
            self.db.execute("INSERT INTO ledger_blocks(height, hash, prev_hash, merkle_root, timestamp, tx_count) VALUES (?,?,?,?,?,?)",
                            (height, h, head["hash"], header["merkle_root"], header["timestamp"], len(leaves)))
            for i, t in enumerate(tx_ids):
                self.db.execute("UPDATE ledger_txs SET block_height=?, idx=? WHERE id=?", (height, i, t))
        block = {**header, "hash": h}
        if self.hub:
            self.hub.publish("ledger", "ledger.block", {**block, "tx_ids": tx_ids})
        return block

    # -- reading ------------------------------------------------------------------
    def summary(self) -> dict:
        head = self.db.one("SELECT * FROM ledger_blocks ORDER BY height DESC LIMIT 1")
        tampered = [r["tx_id"] for r in self.db.query("SELECT tx_id FROM ledger_tamper_log WHERE reverted_at IS NULL")]
        return {"height": head["height"], "head_hash": head["hash"],
                "tx_total": self.db.scalar("SELECT COUNT(*) FROM ledger_txs"),
                "pending": self.db.scalar("SELECT COUNT(*) FROM ledger_txs WHERE block_height IS NULL"),
                "last_verification": self.last_verification, "tamper_demo_enabled": self.allow_tamper,
                "tampered": tampered}

    def blocks(self, before: Optional[int] = None, limit: int = 30) -> list:
        if before is None:
            return self.db.query("SELECT * FROM ledger_blocks ORDER BY height DESC LIMIT ?", (limit,))
        return self.db.query("SELECT * FROM ledger_blocks WHERE height < ? ORDER BY height DESC LIMIT ?", (before, limit))

    def block(self, height: int) -> Optional[dict]:
        b = self.db.one("SELECT * FROM ledger_blocks WHERE height=?", (height,))
        if not b:
            return None
        txs = self.db.query("SELECT id, idx, kind, payload, payload_hash, ref_id, created_at FROM ledger_txs "
                            "WHERE block_height=? ORDER BY idx", (height,))
        for t in txs:
            t["payload"] = loads(t["payload"])
            t["valid"] = sha256_hex(canonical_json(t["payload"])) == t["payload_hash"]
        levels = merkle_levels([t["payload_hash"] for t in txs])
        return {"block": b, "txs": txs, "merkle_levels": levels}

    def tx(self, tx_id: str) -> Optional[dict]:
        t = self.db.one("SELECT * FROM ledger_txs WHERE id=?", (tx_id,))
        if not t:
            return None
        t["payload"] = loads(t["payload"])
        # Recompute the leaf from the payload as stored now: a rewritten row no longer matches.
        t["computed_hash"] = sha256_hex(canonical_json(t["payload"]))
        t["valid"] = t["computed_hash"] == t["payload_hash"]
        if t["block_height"] is not None:
            leaves = [r["payload_hash"] for r in self.db.query(
                "SELECT payload_hash FROM ledger_txs WHERE block_height=? ORDER BY idx", (t["block_height"],))]
            t["proof"] = inclusion_proof(leaves, t["idx"])
            t["merkle_root"] = merkle_root(leaves)
        return t

    def tx_for_ref(self, ref_id: str) -> Optional[dict]:
        return self.db.one("SELECT id, block_height FROM ledger_txs WHERE ref_id=? ORDER BY created_at DESC LIMIT 1", (ref_id,))

    # -- integrity ------------------------------------------------------------------
    def verify(self) -> dict:
        t0 = time.perf_counter()
        blocks = self.db.query("SELECT * FROM ledger_blocks ORDER BY height")
        txs: dict = {}
        for t in self.db.query("SELECT id, block_height, idx, payload, payload_hash FROM ledger_txs "
                               "WHERE block_height IS NOT NULL ORDER BY block_height, idx"):
            txs.setdefault(t["block_height"], []).append(t)
        res = verify_chain(blocks, txs)
        res["duration_ms"] = (time.perf_counter() - t0) * 1000
        res["at"] = time.time()
        self.last_verification = {"at": res["at"], "valid": res["valid"], "first_invalid_height": res["first_invalid_height"]}
        if self.hub:
            self.hub.publish("ledger", "ledger.verified", {k: v for k, v in res.items() if k != "issues"} |
                             {"issues": res["issues"][:20]})
        return res

    def tamper(self, height: Optional[int] = None) -> dict:
        if not self.allow_tamper:
            raise PermissionError("tamper demo disabled")
        if height is None:
            row = self.db.one("SELECT t.* FROM ledger_txs t WHERE t.block_height IS NOT NULL ORDER BY t.block_height DESC, t.idx LIMIT 1")
        else:
            row = self.db.one("SELECT * FROM ledger_txs WHERE block_height=? ORDER BY idx LIMIT 1", (height,))
        if not row:
            raise LookupError("no sealed transaction to tamper with")
        payload = loads(row["payload"])
        field = next((k for k in ("message_sha256", "verdict", "severity", "category", "kind") if k in payload), "kind")
        original = payload.get(field)
        payload[field] = ("0" * 64) if field == "message_sha256" else ("ACCEPTED" if field == "verdict" else f"{original}*")
        # Rewrite the stored payload directly, leaving every hash untouched.
        self.db.execute("INSERT INTO ledger_tamper_log(tx_id, original_payload, tampered_at) VALUES (?,?,?)",
                        (row["id"], row["payload"], time.time()))
        self.db.execute("UPDATE ledger_txs SET payload=? WHERE id=?", (canonical_json(payload), row["id"]))
        info = {"tx_id": row["id"], "height": row["block_height"], "field": field, "before": original,
                "after": payload[field], "note": "The stored payload was rewritten directly in SQLite; no hash was updated."}
        if self.hub:
            self.hub.publish("ledger", "ledger.tampered", info)
        return info

    def revert(self) -> dict:
        rows = self.db.query("SELECT id, tx_id, original_payload FROM ledger_tamper_log WHERE reverted_at IS NULL ORDER BY id DESC")
        for r in rows:
            self.db.execute("UPDATE ledger_txs SET payload=? WHERE id=?", (r["original_payload"], r["tx_id"]))
            self.db.execute("UPDATE ledger_tamper_log SET reverted_at=? WHERE id=?", (time.time(), r["id"]))
        return {"reverted": [r["tx_id"] for r in rows]}
