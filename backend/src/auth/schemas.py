from typing import Optional

from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


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
