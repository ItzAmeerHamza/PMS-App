"""Schema version 1 for sync events (docs/SYNC_PROTOCOL.md).

Field names match the desktop outbox (backend/src/core/outbox.py). The cloud keeps
its own copy instead of importing the desktop package, so either app runs alone.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SCHEMA_VERSION = 1

EVENT_NAMES = {
    ("product", "created"): "product.created",
    ("product", "updated"): "product.updated",
    ("product", "deleted"): "product.deleted",
    ("stock_movement", "created"): "stock.movement_created",
    ("patient", "created"): "patient.created",
    ("patient", "updated"): "patient.updated",
    ("patient", "deleted"): "patient.deleted",
    ("prescription", "created"): "prescription.created",
    ("prescription", "updated"): "prescription.updated",
    ("prescription", "deleted"): "prescription.deleted",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Envelope(_Strict):
    event_id: uuid.UUID
    sequence: int = Field(ge=1)
    shop_id: uuid.UUID
    entity_type: Literal["product", "stock_movement", "patient", "prescription"]
    entity_id: uuid.UUID
    operation: Literal["created", "updated", "deleted"]
    entity_version: int = Field(ge=1)
    schema_version: int
    payload: dict
    created_at: datetime

    @field_validator("schema_version")
    @classmethod
    def _supported(cls, value: int) -> int:
        if value != SCHEMA_VERSION:
            raise ValueError("unsupported schema_version")
        return value


class Tombstone(_Strict):
    public_id: uuid.UUID
    version: int = Field(ge=1)
    deleted_at: datetime


class ProductPayload(_Strict):
    public_id: uuid.UUID
    version: int = Field(ge=1)
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    salt: str | None = Field(default=None, max_length=255)
    generic_name: str | None = Field(default=None, max_length=255)
    manufacturer: str | None = Field(default=None, max_length=255)
    form: str | None = Field(default=None, max_length=50)
    strength: str | None = Field(default=None, max_length=50)
    pack_size: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, max_length=100)
    barcode: str | None = Field(default=None, max_length=64)
    rack_location: str | None = Field(default=None, max_length=80)
    unit_price: Decimal | None = None
    reorder_level: int | None = None
    requires_prescription: bool = False
    notes: str | None = None
    is_active: bool = True
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MovementBatch(_Strict):
    public_id: uuid.UUID
    batch_number: str = Field(min_length=1, max_length=64)
    expiry_date: date
    cost_price: Decimal | None = None
    selling_price: Decimal | None = None


class MovementPayload(_Strict):
    public_id: uuid.UUID
    movement_type: Literal["opening_balance", "receipt", "adjustment", "dispense", "sale", "void"]
    quantity_delta: int
    quantity_after: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=255)
    source_type: str | None = Field(default=None, max_length=20)
    source_ref: str | None = Field(default=None, max_length=64)
    medicine_public_id: uuid.UUID
    batch: MovementBatch
    created_at: datetime | None = None

    @field_validator("quantity_delta")
    @classmethod
    def _non_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("quantity_delta must not be zero")
        return value


class PatientPayload(_Strict):
    public_id: uuid.UUID
    version: int = Field(ge=1)
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=20)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=500)
    allergies: str | None = None
    notes: str | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PrescriptionItemPayload(_Strict):
    public_id: uuid.UUID
    medicine_public_id: uuid.UUID
    medicine_name: str | None = Field(default=None, max_length=255)
    medicine_salt: str | None = Field(default=None, max_length=255)
    medicine_company: str | None = Field(default=None, max_length=255)
    dosage: str | None = Field(default=None, max_length=100)
    frequency: str | None = Field(default=None, max_length=100)
    duration_days: int | None = None
    quantity: int = Field(gt=0)
    instructions: str | None = Field(default=None, max_length=500)


class PrescriptionPayload(_Strict):
    public_id: uuid.UUID
    version: int = Field(ge=1)
    patient_public_id: uuid.UUID
    doctor_name: str | None = Field(default=None, max_length=255)
    complaint: str | None = Field(default=None, max_length=500)
    diagnosis: str | None = Field(default=None, max_length=500)
    notes: str | None = None
    status: Literal["recorded", "dispensed", "cancelled"]
    prescribed_at: datetime | None = None
    dispensed_at: datetime | None = None
    created_at: datetime | None = None
    items: list[PrescriptionItemPayload] = Field(min_length=1)


PAYLOADS = {
    ("product", "created"): ProductPayload,
    ("product", "updated"): ProductPayload,
    ("product", "deleted"): Tombstone,
    ("stock_movement", "created"): MovementPayload,
    ("patient", "created"): PatientPayload,
    ("patient", "updated"): PatientPayload,
    ("patient", "deleted"): Tombstone,
    ("prescription", "created"): PrescriptionPayload,
    ("prescription", "updated"): PrescriptionPayload,
    ("prescription", "deleted"): Tombstone,
}


class InvalidEvent(Exception):
    """Carries a short diagnostic code: field names only, never payload values."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code[:64]


def _code(prefix: str, exc: ValidationError) -> str:
    first = exc.errors()[0]
    field = ".".join(str(part) for part in first.get("loc", ())) or "body"
    return f"{prefix}:{field}"


def parse_envelope(raw: dict) -> Envelope:
    if not isinstance(raw, dict):
        raise InvalidEvent("schema:event")
    try:
        return Envelope.model_validate(raw)
    except ValidationError as exc:
        raise InvalidEvent(_code("schema", exc)) from None


def parse_payload(event: Envelope):
    key = (event.entity_type, event.operation)
    model = PAYLOADS.get(key)
    if model is None:
        raise InvalidEvent("schema:entity_type/operation")
    name = event.payload.get("event")
    if name is not None and name != EVENT_NAMES[key]:
        raise InvalidEvent("schema:payload.event")
    try:
        payload = model.model_validate(event.payload)
    except ValidationError as exc:
        raise InvalidEvent(_code("payload", exc)) from None
    if payload.public_id != event.entity_id:
        raise InvalidEvent("payload:public_id_mismatch")
    if hasattr(payload, "version") and payload.version != event.entity_version:
        raise InvalidEvent("payload:version_mismatch")
    if event.entity_type == "stock_movement" and event.entity_version != 1:
        raise InvalidEvent("payload:movement_version_must_be_1")
    return payload
