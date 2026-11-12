from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PrescriptionItemCreate(BaseModel):
    medicine_id: int
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration_days: Optional[int] = None
    quantity: int = Field(gt=0)
    instructions: Optional[str] = None


class PrescriptionCreate(BaseModel):
    pharmacy_id: int
    patient_id: int
    doctor_name: Optional[str] = None
    complaint: Optional[str] = None
    diagnosis: Optional[str] = None
    notes: Optional[str] = None
    items: list[PrescriptionItemCreate]


class PrescriptionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    medicine_salt: Optional[str] = None
    medicine_company: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration_days: Optional[int] = None
    quantity: int
    instructions: Optional[str] = None


class PrescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pharmacy_id: int
    patient_id: int
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    complaint: Optional[str] = None
    diagnosis: Optional[str] = None
    notes: Optional[str] = None
    status: str
    prescribed_at: Optional[datetime] = None
    dispensed_at: Optional[datetime] = None
    items: list[PrescriptionItemOut] = []
    created_at: Optional[datetime] = None
