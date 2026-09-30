"""
sentinel/protocol/encoding.py
=============================
Signature envelopes and their encoding into the bits that get signed.

``sha256`` mode signs the first ``digest_bits`` bits of SHA-256 over the
canonical envelope, so the freshness metadata (sequence number, timestamp,
nonce) is covered by the signature: altering any of it requires forging keys.

``raw`` mode signs up to 31 message bytes directly (length byte + message +
zero padding = 256 bits): no hash, no computational assumption. Envelope
metadata is then *not* signed; replay protection rests on one-time bundles.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Sequence

import numpy as np

__all__ = [
    "PROTOCOL_ID",
    "RAW_MAX_BYTES",
    "MAX_MESSAGE_BYTES",
    "Envelope",
    "MessageTooLong",
    "envelope_bytes",
    "encode_bits",
    "digest_hex",
]

PROTOCOL_ID = "QVERIS-TQDS/1"
RAW_MAX_BYTES = 31
MAX_MESSAGE_BYTES = 4096
_SEP = b"\x1f"


class MessageTooLong(ValueError):
    """Message exceeds the limit for its encoding."""


@dataclass(frozen=True)
class Envelope:
    group_id: str
    signer_id: str
    recipients: tuple
    bundle_id: str
    seq: int
    timestamp: float
    nonce: str
    message: str
    encoding: str = "sha256"
    protocol: str = PROTOCOL_ID

    def as_dict(self) -> dict:
        d = asdict(self)
        d["recipients"] = list(self.recipients)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Envelope":
        return cls(
            group_id=d["group_id"], signer_id=d["signer_id"], recipients=tuple(d["recipients"]),
            bundle_id=d["bundle_id"], seq=int(d["seq"]), timestamp=float(d["timestamp"]),
            nonce=d["nonce"], message=d["message"], encoding=d.get("encoding", "sha256"),
            protocol=d.get("protocol", PROTOCOL_ID),
        )

    def with_(self, **kw) -> "Envelope":
        d = self.as_dict()
        d.update(kw)
        return Envelope.from_dict(d)


def _check(env: Envelope) -> bytes:
    msg = env.message.encode("utf-8")
    if len(msg) > MAX_MESSAGE_BYTES:
        raise MessageTooLong(f"message is {len(msg)} bytes; maximum is {MAX_MESSAGE_BYTES}")
    if env.encoding == "raw" and len(msg) > RAW_MAX_BYTES:
        raise MessageTooLong(f"raw encoding signs at most {RAW_MAX_BYTES} bytes; message is {len(msg)}")
    if env.encoding not in ("sha256", "raw"):
        raise ValueError(f"unknown encoding {env.encoding!r}")
    return msg


def envelope_bytes(env: Envelope) -> bytes:
    """Canonical byte string of the envelope (what sha256 mode hashes)."""
    msg = _check(env)
    parts: Sequence[bytes] = [
        env.group_id.encode(), env.signer_id.encode(),
        *(r.encode() for r in env.recipients),
        env.bundle_id.encode(), str(int(env.seq)).encode(), f"{env.timestamp:.6f}".encode(),
        env.nonce.encode(), env.encoding.encode(), msg,
    ]
    return env.protocol.encode() + _SEP + _SEP.join(parts)


def encode_bits(env: Envelope, digest_bits: int = 256) -> np.ndarray:
    """The ``digest_bits`` bits signed for this envelope (uint8, MSB first)."""
    msg = _check(env)
    if env.encoding == "raw":
        if digest_bits != 256:
            raise ValueError("raw encoding requires digest_bits = 256")
        block = bytes([len(msg)]) + msg + b"\x00" * (32 - 1 - len(msg))
        data = np.frombuffer(block, dtype=np.uint8)
    else:
        data = np.frombuffer(hashlib.sha256(envelope_bytes(env)).digest(), dtype=np.uint8)
    return np.unpackbits(data)[:digest_bits].astype(np.uint8)


def digest_hex(env: Envelope) -> str:
    """Hex of the signed block (SHA-256 digest, or the raw 32-byte block)."""
    msg = _check(env)
    if env.encoding == "raw":
        return (bytes([len(msg)]) + msg + b"\x00" * (32 - 1 - len(msg))).hex()
    return hashlib.sha256(envelope_bytes(env)).hexdigest()
