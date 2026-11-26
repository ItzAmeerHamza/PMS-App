from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StockBatchCreate(BaseModel):
    batch_number: str
    expiry_date: date
    quantity: int = Field(ge=0)
    cost_price: Decimal = Decimal("0")
    selling_price: Decimal = Decimal("0")


class StockBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    medicine_id: int
    batch_number: str
    expiry_date: date
    quantity: int
    cost_price: Decimal
    selling_price: Decimal
    created_at: Optional[datetime] = None


class StockAdjust(BaseModel):
    quantity_delta: int = Field(description="Signed change; must not be zero")
    reason: str = Field(min_length=1, max_length=255, description="Why the stock changed, e.g. damaged, count correction")

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a reason for the adjustment")
        return value

    @field_validator("quantity_delta")
    @classmethod
    def _delta_not_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Quantity change must not be zero")
        return value


class StockMovementOut(BaseModel):
    id: int
    public_id: str
    medicine_id: int
    batch_id: int
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    movement_type: str
    quantity_delta: int
    quantity_after: int
    reason: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    staff_name: Optional[str] = None
    created_at: Optional[datetime] = None


class MedicineCreate(BaseModel):
    pharmacy_id: int
    sku: str
    name: str
    salt: Optional[str] = None
    generic_name: Optional[str] = None
    manufacturer: Optional[str] = None
    form: str = "tablet"
    strength: Optional[str] = None
    pack_size: Optional[str] = None
    category: Optional[str] = None
    barcode: Optional[str] = None
    rack_location: Optional[str] = None
    unit_price: Decimal = Decimal("0")
    reorder_level: int = 10
    requires_prescription: bool = False
    notes: Optional[str] = None
    is_active: bool = True
    initial_batch: Optional[StockBatchCreate] = None


class MedicineUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    salt: Optional[str] = None
    generic_name: Optional[str] = None
    manufacturer: Optional[str] = None
    form: Optional[str] = None
    strength: Optional[str] = None
    pack_size: Optional[str] = None
    category: Optional[str] = None
    barcode: Optional[str] = None
    rack_location: Optional[str] = None
    unit_price: Optional[Decimal] = None
    reorder_level: Optional[int] = None
    requires_prescription: Optional[bool] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class ImportRow(BaseModel):
    row: int
    sku: Optional[str] = None
    name: Optional[str] = None
    message: str


class MedicineImportResult(BaseModel):
    created: int
    skipped: list[ImportRow]
    errors: list[ImportRow]


class MedicineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pharmacy_id: int
    sku: str
    name: str
    salt: Optional[str] = None
    generic_name: Optional[str] = None
    manufacturer: Optional[str] = None
    form: Optional[str] = None
    strength: Optional[str] = None
    pack_size: Optional[str] = None
    category: Optional[str] = None
    barcode: Optional[str] = None
    rack_location: Optional[str] = None
    unit_price: Decimal
    reorder_level: int
    requires_prescription: bool = False
    notes: Optional[str] = None
    is_active: bool
    quantity_on_hand: int = 0
    sellable_quantity: int = 0
    is_low_stock: bool = False
    nearest_expiry: Optional[date] = None
    batches: list[StockBatchOut] = []
    created_at: Optional[datetime] = None
