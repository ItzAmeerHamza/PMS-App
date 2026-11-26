from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

PaymentMethod = Literal["cash", "card", "bank_transfer", "other"]


class SaleItemCreate(BaseModel):
    medicine_id: int
    quantity: int = Field(gt=0)


class SaleCreate(BaseModel):
    pharmacy_id: int
    prescription_id: Optional[int] = None
    patient_id: Optional[int] = None
    customer_name: Optional[str] = Field(default=None, max_length=255)
    customer_phone: Optional[str] = Field(default=None, max_length=20)
    items: list[SaleItemCreate]
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    tax_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    payment_method: PaymentMethod = "cash"
    amount_paid: Optional[Decimal] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=500)


class SaleVoid(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=255)


class SaleAllocationOut(BaseModel):
    batch_id: int
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    quantity: int


class SaleItemOut(BaseModel):
    id: int
    medicine_id: int
    medicine_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    allocations: list[SaleAllocationOut] = []


class SaleOut(BaseModel):
    id: int
    pharmacy_id: int
    invoice_number: str
    patient_id: Optional[int] = None
    prescription_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    staff_name: Optional[str] = None
    subtotal: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    tax_percent: Decimal
    tax_amount: Decimal
    total: Decimal
    payment_method: str
    amount_paid: Decimal
    change_due: Decimal
    notes: Optional[str] = None
    status: str
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    item_count: int = 0
    items: list[SaleItemOut] = []


class SalesSummary(BaseModel):
    count: int
    total: Decimal
    discount: Decimal
    tax: Decimal
    by_method: dict[str, Decimal]
    voided_count: int


class SaleList(BaseModel):
    sales: list[SaleOut]
    summary: SalesSummary
