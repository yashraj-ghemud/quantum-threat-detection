"""Ledger primitives."""

from __future__ import annotations

from sentinel.ledger import (
    GENESIS_PREV, block_hash, block_header, canonical_json, inclusion_proof, merkle_levels, merkle_root, sha256_hex,
    verify_chain, verify_proof,
)


def test_canonical_json_stable():
    assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'


def test_merkle_and_proofs():
    leaves = [sha256_hex(str(i)) for i in range(5)]
    root = merkle_root(leaves)
    assert len(merkle_levels(leaves)) == 4
    for i, leaf in enumerate(leaves):
        assert verify_proof(leaf, inclusion_proof(leaves, i), root)
    assert not verify_proof(sha256_hex("x"), inclusion_proof(leaves, 0), root)
    assert merkle_root([]) == sha256_hex(b"")


def _chain(n=3):
    blocks, txs = [], {}
    prev = GENESIS_PREV
    for h in range(n):
        items = [{"id": f"t{h}{j}", "payload": canonical_json({"h": h, "j": j})} for j in range(h)]
        for t in items:
            t["payload_hash"] = sha256_hex(t["payload"])
        root = merkle_root([t["payload_hash"] for t in items])
        header = block_header(h, prev, root, 1000.0 + h, len(items))
        b = {**header, "hash": block_hash(header)}
        blocks.append(b)
        txs[h] = items
        prev = b["hash"]
    return blocks, txs


def test_verify_chain_and_tamper():
    blocks, txs = _chain(4)
    assert verify_chain(blocks, txs)["valid"]
    txs[2][0]["payload"] = canonical_json({"h": 2, "j": 0, "evil": True})
    res = verify_chain(blocks, txs)
    assert not res["valid"] and res["first_invalid_height"] == 2
    assert {i["kind"] for i in res["issues"]} >= {"payload_hash_mismatch", "merkle_mismatch"}
    assert res["downstream_blocks"] == 1
