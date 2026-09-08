import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.domain import DELIVERY_PRIORITIES, DELIVERY_STATUSES

Status = Literal["planned", "in_transit", "delayed", "completed", "cancelled"]

class DeliveryCreate(BaseModel):
    """Create a delivery from an owned route analysis.

    Source/destination/cargo always come from the analysis; only operationally
    sensible overrides are accepted here.
    """
    analysis_id: uuid.UUID
    vehicle: str | None = Field(None, max_length=80)
    priority: str | None = Field(None, max_length=20)
    planned_departure: datetime | None = None
    notes: str | None = Field(None, max_length=1000)

    @field_validator("priority")
    @classmethod
    def priority_allowed(cls, value):
        if value is not None and value not in DELIVERY_PRIORITIES:
            raise ValueError(f"priority must be one of {DELIVERY_PRIORITIES}")
        return value

class DeliveryUpdate(BaseModel):
    status: Status | None = None
    status_note: str | None = Field(None, max_length=500)
    planned_departure: datetime | None = None
    actual_arrival: datetime | None = None
    notes: str | None = Field(None, max_length=1000)

class DeliveryResponse(BaseModel):
    id: uuid.UUID
    identifier: str
    analysis_id: uuid.UUID | None
    source: str
    destination: str
    cargo_type: str
    vehicle: str
    priority: str
    status: str
    planned_departure: datetime | None
    estimated_arrival: datetime | None
    actual_arrival: datetime | None
    notes: str | None
    accessibility: int | None = None
    risk_level: str | None = None
    allowed_transitions: list[str] = []
    created_at: datetime

class DeliveryStatusEvent(BaseModel):
    from_status: str | None
    to_status: str
    note: str | None = None
    at: datetime

class DeliveryDetailResponse(DeliveryResponse):
    """Full logistics detail: route, intelligence, timing, hazards, provenance."""
    updated_at: datetime
    status_history: list[DeliveryStatusEvent] = []
    sensitive_transitions: list[str] = []
    route: dict[str, Any] | None = None
    accessibility_detail: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    weather: dict[str, Any] | None = None
    terrain: dict[str, Any] | None = None
    hazards: dict[str, Any] | None = None
    geometry: list[dict[str, float]] = []
    source_coordinate: dict[str, float] | None = None
    destination_coordinate: dict[str, float] | None = None
    data_quality: dict[str, Any] = {}
    analysis: dict[str, Any] | None = None

class TransitionRules(BaseModel):
    statuses: list[str] = DELIVERY_STATUSES
    transitions: dict[str, list[str]]
    sensitive: list[str]
    priorities: list[str] = DELIVERY_PRIORITIES
