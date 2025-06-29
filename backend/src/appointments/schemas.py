from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from .models import AppointmentStatus, AppointmentType

class AppointmentBase(BaseModel):
    patient_id: int
    doctor_id: int
    scheduled_at: datetime
    duration_minutes: int = 30
    appointment_type: AppointmentType
    reason: Optional[str] = None
    notes: Optional[str] = None
    is_urgent: bool = False

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    appointment_type: Optional[AppointmentType] = None
    status: Optional[AppointmentStatus] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    is_urgent: Optional[bool] = None

class Appointment(AppointmentBase):
    id: int
    status: AppointmentStatus
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AppointmentWithDetails(Appointment):
    patient: dict  # Will contain patient information
    doctor: dict   # Will contain doctor information 