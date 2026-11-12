from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .core.database import Base


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id = Column(Integer, primary_key=True, index=True)
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


class StockBatch(Base):
    __tablename__ = "stock_batches"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False, index=True)
    batch_number = Column(String(64), nullable=False)
    expiry_date = Column(Date, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    cost_price = Column(Numeric(10, 2), default=0)
    selling_price = Column(Numeric(10, 2), default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medicine = relationship("Medicine", back_populates="batches")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
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

    pharmacy = relationship("Pharmacy", back_populates="patients")
    prescriptions = relationship("Prescription", back_populates="patient")


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
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


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id = Column(Integer, primary_key=True, index=True)
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
