"""
server/api/schemas.py
=====================
Request models (Pydantic v2). Responses are the engine's report dictionaries,
documented in ``docs/plan/01_BACKEND_PLAN.md`` section 12 and typed in
``web/src/api/types.ts``.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

Origin = Literal["STUDIO", "API", "LAB"]


class AttackSpecIn(BaseModel):
    attack_id: str = Field(..., examples=["channel.dephase"])
    intensity: float = Field(0.5, ge=0.0, le=1.0)
    params: dict[str, Any] = Field(default_factory=dict)
    target: Literal["first", "second", "both"] = "first"


class DistributeIn(BaseModel):
    group_id: str = "g-alice"
    preset: Optional[Literal["demo", "standard", "high"]] = None
    origin: Origin = "API"


class SignIn(BaseModel):
    group_id: str = "g-alice"
    message: str = Field(..., min_length=1, max_length=4096)
    encoding: Literal["sha256", "raw"] = "sha256"
    bundle_id: Optional[str] = None
    origin: Origin = "STUDIO"

    @field_validator("message")
    @classmethod
    def _utf8_len(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 4096:
            raise ValueError("message exceeds 4096 bytes")
        return v


class ReverifyIn(BaseModel):
    verifier_id: Optional[str] = None
    delay_s: float = Field(0.0, ge=0, le=3600)


class AttackRunIn(BaseModel):
    attack: AttackSpecIn
    group_id: str = "g-alice"
    message: Optional[str] = Field(None, max_length=4096)
    counterfactual: bool = True


class CampaignMixItem(BaseModel):
    attack: AttackSpecIn
    weight: float = Field(1.0, ge=0.0, le=100.0)


class CampaignIn(BaseModel):
    name: str = Field("Custom campaign", max_length=80)
    preset: Optional[str] = None
    mix: list[CampaignMixItem] = Field(default_factory=list)
    rate_per_min: float = Field(6, ge=1, le=60)
    duration_s: float = Field(120, ge=10, le=3600)
    group_ids: Optional[list[str]] = None


class TrafficIn(BaseModel):
    rate_per_min: Optional[int] = Field(None, ge=1, le=120)
    groups: Optional[list[str]] = None


class LinkPatch(BaseModel):
    baseline_channel: Optional[list[dict[str, Any]]] = None
    authenticated_classical: Optional[bool] = None
    length_km: Optional[float] = Field(None, ge=0, le=500)


class ReasonIn(BaseModel):
    reason: str = Field("", max_length=300)


class NoteIn(BaseModel):
    note: str = Field("", max_length=500)


class RespondIn(BaseModel):
    action: str


class PresetIn(BaseModel):
    preset: Literal["demo", "standard", "high"]


class DetectionPatch(BaseModel):
    alpha_family: Optional[float] = Field(None, ge=1e-12, le=1e-2)
    enforce: Optional[bool] = None
    floor_chsh_drop: Optional[float] = Field(None, gt=0, le=1)
    floor_fidelity_drop: Optional[float] = Field(None, gt=0, le=1)
    floor_qber_rise: Optional[float] = Field(None, gt=0, le=0.5)
    floor_tomography: Optional[float] = Field(None, gt=0, le=1)
    floor_consistency: Optional[float] = Field(None, gt=0, le=0.5)
    cusum_qber_k: Optional[float] = Field(None, gt=0, le=0.5)
    cusum_qber_h: Optional[float] = Field(None, gt=0, le=1)
    cusum_chsh_k: Optional[float] = Field(None, gt=0, le=1)
    cusum_chsh_h: Optional[float] = Field(None, gt=0, le=3)


class CalibrateIn(BaseModel):
    link_ids: Optional[list[str]] = None


class JobIn(BaseModel):
    kind: str
    preset: Literal["quick", "full"] = "quick"
    params: dict[str, Any] = Field(default_factory=dict)


class ChannelsIn(BaseModel):
    channels: list[dict[str, Any]] = Field(default_factory=list, max_length=8)


class TeleportIn(BaseModel):
    bloch: Optional[list[float]] = Field(None, min_length=3, max_length=3)
    label: Optional[int] = Field(None, ge=0, le=5)
    channels: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    frame_flip: dict[str, float] = Field(default_factory=dict)
    shots: int = Field(0, ge=0, le=20000)
    basis: Literal["x", "y", "z"] = "z"


class TamperIn(BaseModel):
    height: Optional[int] = Field(None, ge=1)
