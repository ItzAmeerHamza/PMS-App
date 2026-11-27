from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PrescriptionItemCreate(BaseModel):
    medicine_id: int
    dosage: Optional[str] = Field(default=None, max_length=100)
    frequency: Optional[str] = Field(default=None, max_length=100)
    duration_days: Optional[int] = Field(default=None, ge=1, le=365)
    quantity: int = Field(gt=0, le=100_000)
    instructions: Optional[str] = Field(default=None, max_length=500)


class PrescriptionCreate(BaseModel):
    pharmacy_id: int
    patient_id: int
    doctor_name: Optional[str] = Field(default=None, max_length=255)
    complaint: Optional[str] = Field(default=None, max_length=500)
    diagnosis: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=5000)
    items: list[PrescriptionItemCreate] = Field(max_length=100)


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
    sale_id: Optional[int] = None
    items: list[PrescriptionItemOut] = []
    created_at: Optional[datetime] = None


class PrescriptionPage(BaseModel):
    items: list[PrescriptionOut]
    total: int
    page: int
    page_size: int
