from sqlalchemy import Column, Integer, String, DateTime, Date, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

class Patient(Base):
    __tablename__ = "patients"
    
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    gender = Column(String(10), nullable=False)  # 'male', 'female', 'other'
    email = Column(String(255), unique=True, index=True)
    phone = Column(String(20))
    address = Column(Text)
    emergency_contact_name = Column(String(255))
    emergency_contact_phone = Column(String(20))
    blood_type = Column(String(5))  # 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'
    allergies = Column(Text)
    medical_history = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    appointments = relationship("Appointment", back_populates="patient")
    medical_records = relationship("MedicalRecord", back_populates="patient")
    prescriptions = relationship("Prescription", back_populates="patient") 