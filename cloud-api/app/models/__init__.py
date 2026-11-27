"""PostgreSQL tables for the cloud replica.

Every business row carries shop_id, and a business entity is unique per
(shop_id, public_id). A shop's id is the desktop pharmacy's public_id, the same
value the desktop puts in sync_outbox.shop_id.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now():
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ---------------------------------------------------------------- shops, devices, owners


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)  # = desktop pharmacy public_id
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = _now()
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShopDevice(Base):
    """A revocable credential for one shop computer. Only a hash of the secret is stored."""

    __tablename__ = "shop_devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(120))
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = _now()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Owner(Base):
    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64))  # enrollment in phase 08
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = _now()


class OwnerSession(Base):
    __tablename__ = "owner_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _now()


class OwnerChallenge(Base):
    """Short-lived password-ok step before TOTP. The raw challenge is not stored."""

    __tablename__ = "owner_challenges"
    __table_args__ = (CheckConstraint("purpose IN ('enroll', 'totp')", name="ck_owner_challenges_purpose"),)

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(10), nullable=False)
    # Present only until enrollment is confirmed. Not written to logs.
    pending_secret: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = _now()


# ---------------------------------------------------------------- business replica


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("shop_id", "public_id", name="uq_products_shop_public_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    salt: Mapped[str | None] = mapped_column(String(255))
    generic_name: Mapped[str | None] = mapped_column(String(255))
    manufacturer: Mapped[str | None] = mapped_column(String(255))
    form: Mapped[str | None] = mapped_column(String(50))
    strength: Mapped[str | None] = mapped_column(String(50))
    pack_size: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(100))
    barcode: Mapped[str | None] = mapped_column(String(64))
    rack_location: Mapped[str | None] = mapped_column(String(80))
    unit_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    reorder_level: Mapped[int | None] = mapped_column(Integer)
    requires_prescription: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = _now()


class StockBatch(Base):
    """Created and updated only by stock movements. quantity = sum of applied deltas."""

    __tablename__ = "stock_batches"
    __table_args__ = (UniqueConstraint("shop_id", "public_id", name="uq_stock_batches_shop_public_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    batch_number: Mapped[str] = mapped_column(String(64), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    selling_price: Mapped[float | None] = mapped_column(Numeric(10, 2))


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (UniqueConstraint("shop_id", "public_id", name="uq_stock_movements_shop_public_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("stock_batches.id"), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)  # as reported by the shop
    cloud_quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)  # batch quantity here after apply
    reason: Mapped[str | None] = mapped_column(String(255))
    source_type: Mapped[str | None] = mapped_column(String(20))
    source_ref: Mapped[str | None] = mapped_column(String(64))
    local_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = _now()


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("shop_id", "public_id", name="uq_patients_shop_public_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(String(500))
    allergies: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = _now()


class Prescription(Base):
    __tablename__ = "prescriptions"
    __table_args__ = (UniqueConstraint("shop_id", "public_id", name="uq_prescriptions_shop_public_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    doctor_name: Mapped[str | None] = mapped_column(String(255))
    complaint: Mapped[str | None] = mapped_column(String(500))
    diagnosis: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    prescribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispensed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = _now()


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"
    __table_args__ = (UniqueConstraint("shop_id", "public_id", name="uq_prescription_items_shop_public_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    medicine_name: Mapped[str | None] = mapped_column(String(255))
    medicine_salt: Mapped[str | None] = mapped_column(String(255))
    medicine_company: Mapped[str | None] = mapped_column(String(255))
    dosage: Mapped[str | None] = mapped_column(String(100))
    frequency: Mapped[str | None] = mapped_column(String(100))
    duration_days: Mapped[int | None] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str | None] = mapped_column(String(500))


# ---------------------------------------------------------------- bookkeeping


class AuditLog(Base):
    """Cloud-side actions (owner sign-in, shop and device changes). Ids only, no clinical text."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shops.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # owner | device | system
    actor_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _now()


class ProcessedSyncEvent(Base):
    """Idempotency: one row per applied event. A repeated event_id applies nothing."""

    __tablename__ = "processed_sync_events"
    __table_args__ = (UniqueConstraint("shop_id", "event_id", name="uq_processed_sync_events_shop_event"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id"), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    operation: Mapped[str] = mapped_column(String(10), nullable=False)
    entity_version: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    processed_at: Mapped[datetime] = _now()


class SynchronizationState(Base):
    """One row per shop. Also the per-shop lock that serializes event application."""

    __tablename__ = "synchronization_state"
    __table_args__ = (CheckConstraint("events_applied >= 0", name="ck_synchronization_state_applied"),)

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id"), primary_key=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_applied_sequence: Mapped[int | None] = mapped_column(BigInteger)
    events_applied: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    last_result: Mapped[str | None] = mapped_column(String(30))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # Reported by the shop's worker (phase 07 Part B); last-known values, not live.
    reported_pending: Mapped[int | None] = mapped_column(Integer)
    reported_failed: Mapped[int | None] = mapped_column(Integer)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
