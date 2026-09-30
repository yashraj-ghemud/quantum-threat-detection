"""
sentinel/protocol/keys.py
=========================
Key bundles and the per-verifier views that enforce information boundaries.

A :class:`KeyBundle` is the *world state* of one distributed one-time key
set: the signer's private labels and each recipient's measurement records.
In the simulation all of it lives in one object, so access is mediated:

- the **signer** reads ``labels`` (and only the signing code does);
- a **verifier** acts only through :meth:`KeyBundle.view_for`, which returns a
  :class:`VerifierView` holding its own records plus the records its peer
  forwarded to it during symmetrization, and nothing else;
- **adversaries** never receive a ``KeyBundle``; they get an explicit
  knowledge object built from what they could legitimately observe.

Records are packed one byte per position in storage:
``basis | outcome << 2 | forwarded << 3``.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from sentinel.protocol.params import ProtocolParams

__all__ = ["VerifierRecords", "VerifierView", "KeyBundle", "KeyReuseError", "BundleShredded"]

_UNKNOWN = np.uint8(255)


class KeyReuseError(RuntimeError):
    """A one-time bundle was asked to sign a second message."""


class BundleShredded(RuntimeError):
    """The private labels of this bundle have been destroyed."""


@dataclass
class VerifierRecords:
    basis: np.ndarray    # uint8 (B, 2, L)
    outcome: np.ndarray  # uint8 (B, 2, L)
    fwd: np.ndarray      # bool  (B, 2, L)  positions forwarded to the peer

    def pack(self) -> np.ndarray:
        return (self.basis | (self.outcome << 2) | (self.fwd.astype(np.uint8) << 3)).astype(np.uint8)

    @classmethod
    def unpack(cls, packed: np.ndarray) -> "VerifierRecords":
        return cls(basis=(packed & 3).astype(np.uint8), outcome=((packed >> 2) & 1).astype(np.uint8),
                   fwd=((packed >> 3) & 1).astype(bool))


@dataclass
class VerifierView:
    """What one recipient legitimately holds for one bundle."""

    verifier_id: str
    peer_id: str
    bundle_id: str
    own_basis: np.ndarray      # (B, 2, L) own measurement records (all positions)
    own_outcome: np.ndarray
    own_kept: np.ndarray       # (B, 2, L) bool: own positions NOT forwarded (the "own" set)
    recv_basis: np.ndarray     # (B, 2, L) peer records, 255 where not received
    recv_outcome: np.ndarray
    recv_mask: np.ndarray      # (B, 2, L) bool: positions the peer forwarded (the "recv" set)


@dataclass
class KeyBundle:
    bundle_id: str
    group_id: str
    signer_id: str
    recipients: tuple
    params: ProtocolParams
    labels: Optional[np.ndarray]           # uint8 (B, 2, L), private
    records: dict                          # verifier_id -> VerifierRecords
    created_at: float = field(default_factory=time.time)
    design: Optional[dict] = None
    status: str = "DISTRIBUTING"
    signed: bool = False

    # -- structure -----------------------------------------------------------
    @property
    def shape(self) -> tuple:
        return (self.params.digest_bits, 2, self.params.L)

    def peer_of(self, verifier_id: str) -> str:
        a, b = self.recipients
        if verifier_id == a:
            return b
        if verifier_id == b:
            return a
        raise KeyError(f"{verifier_id!r} is not a recipient of bundle {self.bundle_id}")

    def view_for(self, verifier_id: str) -> VerifierView:
        peer = self.peer_of(verifier_id)
        own = self.records[verifier_id]
        other = self.records[peer]
        recv_mask = other.fwd.copy()
        return VerifierView(
            verifier_id=verifier_id, peer_id=peer, bundle_id=self.bundle_id,
            own_basis=own.basis, own_outcome=own.outcome, own_kept=~own.fwd,
            recv_basis=np.where(recv_mask, other.basis, _UNKNOWN).astype(np.uint8),
            recv_outcome=np.where(recv_mask, other.outcome, _UNKNOWN).astype(np.uint8),
            recv_mask=recv_mask,
        )

    def private_labels(self) -> np.ndarray:
        """Signer-only access to the private labels."""
        if self.labels is None:
            raise BundleShredded(f"bundle {self.bundle_id} labels were shredded")
        return self.labels

    def shred_labels(self) -> None:
        if self.labels is not None:
            self.labels[...] = 0
        self.labels = None

    def meta(self) -> dict:
        """Public, non-secret description."""
        return {
            "bundle_id": self.bundle_id, "group_id": self.group_id, "signer_id": self.signer_id,
            "recipients": list(self.recipients), "status": self.status, "signed": self.signed,
            "created_at": self.created_at, "params": self.params.as_dict(), "design": self.design,
        }

    # -- persistence ---------------------------------------------------------
    def save(self, path: str | os.PathLike) -> None:
        """Atomic write of the bundle material (npz, mode 0600)."""
        path = Path(path)
        arrays = {f"rec_{v}": self.records[v].pack() for v in self.recipients}
        if self.labels is not None:
            arrays["labels"] = self.labels
        meta = {
            "bundle_id": self.bundle_id, "group_id": self.group_id, "signer_id": self.signer_id,
            "recipients": list(self.recipients), "params": {k: v for k, v in self.params.__dict__.items()},
            "created_at": self.created_at, "design": self.design, "status": self.status, "signed": self.signed,
        }
        arrays["meta"] = np.frombuffer(json.dumps(meta).encode("utf-8"), dtype=np.uint8)
        buf = io.BytesIO()
        np.savez_compressed(buf, **arrays)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".npz")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(buf.getvalue())
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @classmethod
    def load(cls, path: str | os.PathLike) -> "KeyBundle":
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(bytes(data["meta"]).decode("utf-8"))
            labels = data["labels"].copy() if "labels" in data.files else None
            records = {v: VerifierRecords.unpack(data[f"rec_{v}"]) for v in meta["recipients"]}
        return cls(
            bundle_id=meta["bundle_id"], group_id=meta["group_id"], signer_id=meta["signer_id"],
            recipients=tuple(meta["recipients"]), params=ProtocolParams.from_dict(meta["params"]),
            labels=labels, records=records, created_at=meta["created_at"], design=meta.get("design"),
            status=meta.get("status", "ACTIVE"), signed=meta.get("signed", False),
        )
