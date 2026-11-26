from typing import Optional

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class SetupStatus(BaseModel):
    needs_setup: bool
    has_pharmacy: bool
    pharmacy_name: Optional[str] = None


class SetupIn(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(max_length=256)
    pharmacy_name: Optional[str] = Field(default=None, max_length=255)
    pharmacy_address: Optional[str] = Field(default=None, max_length=500)
    pharmacy_phone: Optional[str] = Field(default=None, max_length=20)
    license_number: Optional[str] = Field(default=None, max_length=100)


class PharmacyBrief(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    license_number: Optional[str] = None


class StaffOut(BaseModel):
    id: int
    full_name: str
    username: str
    role: str
    pharmacy: PharmacyBrief


class LoginOut(StaffOut):
    token: str
