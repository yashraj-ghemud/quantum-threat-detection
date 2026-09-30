"""
sentinel/ledger.py
==================
Hash-chain and Merkle-tree primitives for the security ledger.

- Transaction payloads are canonical JSON (sorted keys, compact separators,
  UTF-8); ``payload_hash = SHA-256(payload)``.
- Merkle tree over transaction hashes: parent = SHA-256(left || right) on raw
  bytes; an odd level duplicates its last node; the empty root is SHA-256(b"").
- Block hash = SHA-256 of the canonical JSON header
  ``{height, prev_hash, merkle_root, timestamp, tx_count}``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Sequence

__all__ = [
    "GENESIS_PREV",
    "canonical_json",
    "sha256_hex",
    "merkle_levels",
    "merkle_root",
    "inclusion_proof",
    "verify_proof",
    "block_header",
    "block_hash",
    "verify_chain",
]

GENESIS_PREV = "0" * 64


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def merkle_levels(leaves: Sequence[str]) -> list:
    """All levels from leaves (hex) up to the root."""
    if not leaves:
        return [[sha256_hex(b"")]]
    level = list(leaves)
    levels = [level]
    while len(level) > 1:
        if len(level) % 2:
            level = level + [level[-1]]
        level = [sha256_hex(bytes.fromhex(level[i]) + bytes.fromhex(level[i + 1])) for i in range(0, len(level), 2)]
        levels.append(level)
    return levels


def merkle_root(leaves: Sequence[str]) -> str:
    return merkle_levels(leaves)[-1][0]


def inclusion_proof(leaves: Sequence[str], index: int) -> list:
    """Sibling path for leaf ``index``: [{"hash": h, "side": "left"|"right"}] from bottom to top."""
    proof = []
    level = list(leaves)
    i = index
    while len(level) > 1:
        if len(level) % 2:
            level = level + [level[-1]]
        sib = i ^ 1
        proof.append({"hash": level[sib], "side": "left" if sib < i else "right"})
        level = [sha256_hex(bytes.fromhex(level[j]) + bytes.fromhex(level[j + 1])) for j in range(0, len(level), 2)]
        i //= 2
    return proof


def verify_proof(leaf: str, proof: Iterable[dict], root: str) -> bool:
    h = leaf
    for step in proof:
        if step["side"] == "left":
            h = sha256_hex(bytes.fromhex(step["hash"]) + bytes.fromhex(h))
        else:
            h = sha256_hex(bytes.fromhex(h) + bytes.fromhex(step["hash"]))
    return h == root


def block_header(height: int, prev_hash: str, merkle: str, timestamp: float, tx_count: int) -> dict:
    return {"height": int(height), "prev_hash": prev_hash, "merkle_root": merkle,
            "timestamp": round(float(timestamp), 6), "tx_count": int(tx_count)}


def block_hash(header: dict) -> str:
    return sha256_hex(canonical_json(header))


def verify_chain(blocks: Sequence[dict], txs_by_height: dict) -> dict:
    """Recompute every hash. ``blocks`` sorted by height; each has the stored fields.

    ``txs_by_height[h]`` is the ordered list of {"id", "payload", "payload_hash"}.
    """
    issues = []
    prev = None
    first_bad = None
    n_tx = 0
    for b in blocks:
        h = int(b["height"])
        txs = txs_by_height.get(h, [])
        n_tx += len(txs)
        leaves = []
        for t in txs:
            recomputed = sha256_hex(t["payload"])
            if recomputed != t["payload_hash"]:
                issues.append({"height": h, "tx_id": t["id"], "kind": "payload_hash_mismatch",
                               "detail": "stored transaction payload no longer matches its hash"})
            leaves.append(recomputed)
        root = merkle_root(leaves)
        if root != b["merkle_root"]:
            issues.append({"height": h, "kind": "merkle_mismatch",
                           "detail": f"Merkle root recomputes to {root[:16]}… but the block records {b['merkle_root'][:16]}…"})
        header = block_header(h, b["prev_hash"], b["merkle_root"], b["timestamp"], b["tx_count"])
        if block_hash(header) != b["hash"]:
            issues.append({"height": h, "kind": "header_mismatch", "detail": "block header hash does not match"})
        expected_prev = GENESIS_PREV if prev is None else prev["hash"]
        if b["prev_hash"] != expected_prev:
            issues.append({"height": h, "kind": "broken_link", "detail": "prev_hash does not match the previous block"})
        if issues and first_bad is None:
            first_bad = h
        prev = b
    downstream = sum(1 for b in blocks if first_bad is not None and int(b["height"]) > first_bad)
    return {"valid": not issues, "checked_blocks": len(blocks), "checked_txs": n_tx,
            "first_invalid_height": first_bad, "issues": issues, "downstream_blocks": downstream}
