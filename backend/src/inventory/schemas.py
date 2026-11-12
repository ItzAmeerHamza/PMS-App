from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
    quantity_delta: int
    reason: Optional[str] = None


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
    is_low_stock: bool = False
    nearest_expiry: Optional[date] = None
    batches: list[StockBatchOut] = []
    created_at: Optional[datetime] = None
