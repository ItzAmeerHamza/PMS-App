import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .core.database import Base


def new_public_id() -> str:
    return str(uuid.uuid4())


def public_id_column():
    """Stable UUID used as the sync identity. Set once at insert, never regenerated."""
    return Column(String(36), nullable=False, unique=True, index=True, default=new_public_id)


def version_column():
    """Starts at 1 and increments on every UPDATE (SQLAlchemy version_id_col)."""
    return Column(Integer, nullable=False, default=1, server_default="1")


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id = Column(Integer, primary_key=True, index=True)
    public_id = public_id_column()
    name = Column(String(255), nullable=False)
    address = Column(String(500))
    phone = Column(String(20))
    license_number = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medicines = relationship("Medicine", back_populates="pharmacy")
    patients = relationship("Patient", back_populates="pharmacy")
    prescriptions = relationship("Prescription", back_populates="pharmacy")
    staff = relationship("Staff", back_populates="pharmacy")


class Staff(Base):
    __tablename__ = "staff"

    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    username = Column(String(64), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(40), nullable=False, default="store_manager")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pharmacy = relationship("Pharmacy", back_populates="staff")
    sessions = relationship("StaffSession", back_populates="staff", cascade="all, delete-orphan")


class StaffSession(Base):
    __tablename__ = "staff_sessions"

    token = Column(String(64), primary_key=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    staff = relationship("Staff", back_populates="sessions")


class Medicine(Base):
    __tablename__ = "medicines"
    __table_args__ = (UniqueConstraint("pharmacy_id", "sku", name="uq_medicine_sku_per_pharmacy"),)

    id = Column(Integer, primary_key=True, index=True)
    public_id = public_id_column()
    version = version_column()
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False, index=True)
    sku = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False, index=True)
    salt = Column(String(255))
    generic_name = Column(String(255))
    manufacturer = Column(String(255))
    form = Column(String(50), default="tablet")
    strength = Column(String(50))
    pack_size = Column(String(80))
    category = Column(String(100))
    barcode = Column(String(64))
    rack_location = Column(String(80))
    unit_price = Column(Numeric(10, 2), default=0)
    reorder_level = Column(Integer, default=10)
    requires_prescription = Column(Boolean, default=False)
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    pharmacy = relationship("Pharmacy", back_populates="medicines")
    batches = relationship("StockBatch", back_populates="medicine", cascade="all, delete-orphan")
    prescription_items = relationship("PrescriptionItem", back_populates="medicine")

    __mapper_args__ = {"version_id_col": version}


class StockBatch(Base):
    __tablename__ = "stock_batches"
    __table_args__ = (CheckConstraint("quantity >= 0", name="ck_stock_batches_quantity_not_negative"),)

    id = Column(Integer, primary_key=True, index=True)
    public_id = public_id_column()
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False, index=True)
    batch_number = Column(String(64), nullable=False)
    expiry_date = Column(Date, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    cost_price = Column(Numeric(10, 2), default=0)
    selling_price = Column(Numeric(10, 2), default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medicine = relationship("Medicine", back_populates="batches")
    movements = relationship("StockMovement", back_populates="batch", order_by="StockMovement.id")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    public_id = public_id_column()
    version = version_column()
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False, index=True)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False, index=True)
    date_of_birth = Column(Date)
    gender = Column(String(20))
    address = Column(String(500))
    allergies = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    # Tombstone (phase 04). Set instead of deleting the row; history stays readable.
    deleted_at = Column(DateTime(timezone=True), index=True)

    pharmacy = relationship("Pharmacy", back_populates="patients")
    prescriptions = relationship("Prescription", back_populates="patient")

    __mapper_args__ = {"version_id_col": version}


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    public_id = public_id_column()
    version = version_column()
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_name = Column(String(255))
    complaint = Column(String(500))
    diagnosis = Column(String(500))
    notes = Column(Text)
    status = Column(String(20), nullable=False, default="recorded")
    prescribed_at = Column(DateTime(timezone=True), server_default=func.now())
    dispensed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pharmacy = relationship("Pharmacy", back_populates="prescriptions")
    patient = relationship("Patient", back_populates="prescriptions")
    items = relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")
    sales = relationship("Sale", viewonly=True)

    __mapper_args__ = {"version_id_col": version}


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id = Column(Integer, primary_key=True, index=True)
    public_id = public_id_column()
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    medicine_name = Column(String(255))
    medicine_salt = Column(String(255))
    medicine_company = Column(String(255))
    dosage = Column(String(100))
    frequency = Column(String(100))
    duration_days = Column(Integer)
    quantity = Column(Integer, nullable=False)
    instructions = Column(String(500))

    prescription = relationship("Prescription", back_populates="items")
    medicine = relationship("Medicine", back_populates="prescription_items")


class Sale(Base):
    """A bill. Walk-in counter sales have no patient/prescription; prescription bills link both."""

    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False, index=True)
    invoice_number = Column(String(32), unique=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), index=True)
    staff_id = Column(Integer, ForeignKey("staff.id"))
    customer_name = Column(String(255))
    customer_phone = Column(String(20))
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    discount_percent = Column(Numeric(5, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(12, 2), nullable=False, default=0)
    tax_percent = Column(Numeric(5, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    payment_method = Column(String(20), nullable=False, default="cash")
    amount_paid = Column(Numeric(12, 2), nullable=False, default=0)
    change_due = Column(Numeric(12, 2), nullable=False, default=0)
    notes = Column(String(500))
    status = Column(String(20), nullable=False, default="paid")
    voided_at = Column(DateTime(timezone=True))
    void_reason = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    patient = relationship("Patient")
    prescription = relationship("Prescription")
    staff = relationship("Staff")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    medicine_name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    line_total = Column(Numeric(12, 2), nullable=False)

    sale = relationship("Sale", back_populates="items")
    medicine = relationship("Medicine")
    allocations = relationship("SaleAllocation", back_populates="item", cascade="all, delete-orphan")


class SaleAllocation(Base):
    """Which stock batch each sold unit came from, so a void can put it back exactly."""

    __tablename__ = "sale_allocations"

    id = Column(Integer, primary_key=True, index=True)
    sale_item_id = Column(Integer, ForeignKey("sale_items.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("stock_batches.id"), nullable=False)
    batch_number = Column(String(64))
    expiry_date = Column(Date)
    quantity = Column(Integer, nullable=False)

    item = relationship("SaleItem", back_populates="allocations")
    batch = relationship("StockBatch")


class AuditLog(Base):
    """Who did what. Never holds patient details or clinical text: only ids and action names."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    public_id = public_id_column()
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), index=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), index=True)
    action = Column(String(64), nullable=False)
    entity_type = Column(String(40))
    entity_public_id = Column(String(36))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


MOVEMENT_TYPES = ("opening_balance", "receipt", "adjustment", "dispense", "sale", "void")


class StockMovement(Base):
    """Append-only stock ledger. One row per change to a batch quantity.

    For every batch, SUM(quantity_delta) equals stock_batches.quantity.
    Rows are never updated or deleted by the app.
    """

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity_delta != 0", name="ck_stock_movements_delta_not_zero"),
        CheckConstraint("quantity_after >= 0", name="ck_stock_movements_after_not_negative"),
        CheckConstraint(
            "movement_type IN ('opening_balance', 'receipt', 'adjustment', 'dispense', 'sale', 'void')",
            name="ck_stock_movements_type",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = public_id_column()
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("stock_batches.id"), nullable=False, index=True)
    staff_id = Column(Integer, ForeignKey("staff.id"))
    movement_type = Column(String(20), nullable=False)
    quantity_delta = Column(Integer, nullable=False)
    quantity_after = Column(Integer, nullable=False)
    reason = Column(String(255))
    source_type = Column(String(20))
    source_id = Column(Integer)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    batch = relationship("StockBatch", back_populates="movements")
