from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PatientCreate(BaseModel):
    pharmacy_id: int
    first_name: str
    last_name: str
    phone: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    allergies: Optional[str] = None
    notes: Optional[str] = None


class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    allergies: Optional[str] = None
    notes: Optional[str] = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: Optional[str] = None
    pharmacy_id: int
    first_name: str
    last_name: str
    phone: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    allergies: Optional[str] = None
    notes: Optional[str] = None
    prescription_count: int = 0
    is_repeat_visitor: bool = False
    last_visit: Optional[datetime] = None
    deleted: bool = False
    deleted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class PatientDetailOut(PatientOut):
    pass


class PatientPage(BaseModel):
    items: list[PatientOut]
    total: int
    page: int
    page_size: int
