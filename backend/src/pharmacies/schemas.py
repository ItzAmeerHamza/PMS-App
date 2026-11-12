from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PharmacyCreate(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    license_number: Optional[str] = None


class PharmacyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    license_number: Optional[str] = None


class PharmacyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    license_number: Optional[str] = None
    created_at: Optional[datetime] = None
