from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..core.schemas import User

class DoctorBase(BaseModel):
    license_number: str
    specialization: str
    qualifications: Optional[str] = None
    experience_years: Optional[int] = None
    bio: Optional[str] = None
    consultation_fee: Optional[int] = None
    is_available: bool = True

class DoctorCreate(DoctorBase):
    user_id: int

class DoctorUpdate(BaseModel):
    license_number: Optional[str] = None
    specialization: Optional[str] = None
    qualifications: Optional[str] = None
    experience_years: Optional[int] = None
    bio: Optional[str] = None
    consultation_fee: Optional[int] = None
    is_available: Optional[bool] = None

class Doctor(DoctorBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class DoctorWithUser(Doctor):
    user: User  # Will contain user information 