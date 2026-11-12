import csv
import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .. import models
from . import schemas


def _quantity_on_hand(medicine: models.Medicine) -> int:
    return sum(batch.quantity for batch in medicine.batches)


def _nearest_expiry(medicine: models.Medicine) -> date | None:
    dates = [batch.expiry_date for batch in medicine.batches if batch.quantity > 0]
    return min(dates) if dates else None


def serialize_batch(batch: models.StockBatch) -> dict:
    return {
        "id": batch.id,
        "medicine_id": batch.medicine_id,
        "batch_number": batch.batch_number,
        "expiry_date": batch.expiry_date,
        "quantity": batch.quantity,
        "cost_price": batch.cost_price,
        "selling_price": batch.selling_price,
        "created_at": batch.created_at,
    }


_TEXT_FIELDS = (
    "salt",
    "generic_name",
    "manufacturer",
    "form",
    "strength",
    "pack_size",
    "category",
    "barcode",
    "rack_location",
    "notes",
    "sku",
    "name",
)


def _clean(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _prepare_medicine_fields(data: dict) -> dict:
    prepared = {}
    for key, value in data.items():
        if key in _TEXT_FIELDS:
            value = _clean(value)
        if key in ("sku", "name") and not value:
            raise ValueError("Medicine name and SKU are required")
        prepared[key] = value
    if "salt" in data:
        prepared["generic_name"] = prepared.get("salt")
    elif prepared.get("generic_name"):
        prepared["salt"] = prepared["generic_name"]
    return prepared


def serialize_medicine(medicine: models.Medicine) -> dict:
    quantity = _quantity_on_hand(medicine)
    salt = medicine.salt or medicine.generic_name
    return {
        "id": medicine.id,
        "pharmacy_id": medicine.pharmacy_id,
        "sku": medicine.sku,
        "name": medicine.name,
        "salt": salt,
        "generic_name": medicine.generic_name or salt,
        "manufacturer": medicine.manufacturer,
        "form": medicine.form,
        "strength": medicine.strength,
        "pack_size": medicine.pack_size,
        "category": medicine.category,
        "barcode": medicine.barcode,
        "rack_location": medicine.rack_location,
        "unit_price": medicine.unit_price,
        "reorder_level": medicine.reorder_level,
        "requires_prescription": bool(medicine.requires_prescription),
        "notes": medicine.notes,
        "is_active": medicine.is_active,
        "quantity_on_hand": quantity,
        "is_low_stock": quantity <= medicine.reorder_level,
        "nearest_expiry": _nearest_expiry(medicine),
        "batches": [serialize_batch(batch) for batch in medicine.batches],
        "created_at": medicine.created_at,
    }


def _with_batches(db: Session):
    return db.query(models.Medicine).options(joinedload(models.Medicine.batches))


def list_medicines(db: Session, pharmacy_id: int, search: str | None = None, low_stock: bool = False) -> list[dict]:
    query = _with_batches(db).filter(models.Medicine.pharmacy_id == pharmacy_id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            models.Medicine.name.ilike(like)
            | models.Medicine.salt.ilike(like)
            | models.Medicine.generic_name.ilike(like)
            | models.Medicine.manufacturer.ilike(like)
            | models.Medicine.sku.ilike(like)
            | models.Medicine.barcode.ilike(like)
        )
    medicines = query.order_by(models.Medicine.name).all()
    serialized = [serialize_medicine(medicine) for medicine in medicines]
    if low_stock:
        return [item for item in serialized if item["is_low_stock"]]
    return serialized


def get_medicine(db: Session, medicine_id: int) -> models.Medicine | None:
    return _with_batches(db).filter(models.Medicine.id == medicine_id).first()


def create_medicine(db: Session, payload: schemas.MedicineCreate) -> models.Medicine:
    data = _prepare_medicine_fields(payload.model_dump(exclude={"initial_batch"}))
    medicine = models.Medicine(**data)
    db.add(medicine)
    db.flush()
    if payload.initial_batch:
        db.add(models.StockBatch(medicine_id=medicine.id, **payload.initial_batch.model_dump()))
    db.commit()
    return get_medicine(db, medicine.id)


def update_medicine(db: Session, medicine_id: int, payload: schemas.MedicineUpdate) -> models.Medicine | None:
    medicine = get_medicine(db, medicine_id)
    if not medicine:
        return None
    for field, value in _prepare_medicine_fields(payload.model_dump(exclude_unset=True)).items():
        setattr(medicine, field, value)
    db.commit()
    return get_medicine(db, medicine_id)


def delete_medicine(db: Session, medicine_id: int) -> bool:
    medicine = _with_batches(db).filter(models.Medicine.id == medicine_id).first()
    if not medicine:
        return False
    in_use = (
        db.query(models.PrescriptionItem)
        .filter(models.PrescriptionItem.medicine_id == medicine_id)
        .first()
    )
    if in_use:
        raise ValueError("This medicine is on a prescription. Mark it inactive instead of deleting it.")
    db.delete(medicine)
    db.commit()
    return True


def add_batch(db: Session, medicine_id: int, payload: schemas.StockBatchCreate) -> models.StockBatch | None:
    medicine = get_medicine(db, medicine_id)
    if not medicine:
        return None
    batch = models.StockBatch(medicine_id=medicine_id, **payload.model_dump())
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def adjust_batch(db: Session, batch_id: int, payload: schemas.StockAdjust) -> models.StockBatch | None:
    batch = db.query(models.StockBatch).filter(models.StockBatch.id == batch_id).first()
    if not batch:
        return None
    next_qty = batch.quantity + payload.quantity_delta
    if next_qty < 0:
        raise ValueError("Adjustment would make quantity negative")
    batch.quantity = next_qty
    db.commit()
    db.refresh(batch)
    return batch


def list_expiring(db: Session, pharmacy_id: int, days: int = 90) -> list[dict]:
    cutoff = date.today() + timedelta(days=days)
    batches = (
        db.query(models.StockBatch)
        .join(models.Medicine)
        .filter(
            models.Medicine.pharmacy_id == pharmacy_id,
            models.StockBatch.quantity > 0,
            models.StockBatch.expiry_date <= cutoff,
        )
        .order_by(models.StockBatch.expiry_date)
        .all()
    )
    return [
        {
            "id": batch.id,
            "medicine_id": batch.medicine_id,
            "medicine_name": batch.medicine.name,
            "batch_number": batch.batch_number,
            "expiry_date": batch.expiry_date,
            "quantity": batch.quantity,
        }
        for batch in batches
    ]


MAX_IMPORT_ROWS = 1000
_FORMS = {"tablet", "capsule", "syrup", "suspension", "injection", "ointment", "cream", "drops", "inhaler", "sachet", "gel"}
_COLUMN_ALIASES = {
    "name": "name",
    "medicine": "name",
    "medicine name": "name",
    "sku": "sku",
    "code": "sku",
    "item code": "sku",
    "salt": "salt",
    "generic": "generic_name",
    "generic name": "generic_name",
    "company": "manufacturer",
    "manufacturer": "manufacturer",
    "form": "form",
    "strength": "strength",
    "pack": "pack_size",
    "pack size": "pack_size",
    "category": "category",
    "barcode": "barcode",
    "rack": "rack_location",
    "rack location": "rack_location",
    "location": "rack_location",
    "price": "unit_price",
    "unit price": "unit_price",
    "selling price": "unit_price",
    "reorder": "reorder_level",
    "reorder level": "reorder_level",
    "rx": "requires_prescription",
    "prescription": "requires_prescription",
    "requires prescription": "requires_prescription",
    "notes": "notes",
    "active": "is_active",
    "quantity": "quantity",
    "qty": "quantity",
    "batch": "batch_number",
    "batch number": "batch_number",
    "expiry": "expiry_date",
    "expiry date": "expiry_date",
    "cost": "cost_price",
    "cost price": "cost_price",
}
_LENGTH_LIMITS = {
    "sku": 64,
    "name": 255,
    "salt": 255,
    "generic_name": 255,
    "manufacturer": 255,
    "strength": 50,
    "pack_size": 80,
    "category": 100,
    "barcode": 64,
    "rack_location": 80,
    "notes": 2000,
    "batch_number": 64,
}


def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not read this CSV file")


def _header_key(value: str) -> str:
    return " ".join((value or "").strip().casefold().replace("_", " ").replace("-", " ").split())


def _column_map(fieldnames: list[str | None]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in fieldnames:
        if not header:
            continue
        field = _COLUMN_ALIASES.get(_header_key(header))
        if field and field not in mapping:
            mapping[field] = header
    return mapping


def _cell(raw: dict, columns: dict[str, str], field: str) -> str:
    header = columns.get(field)
    if not header:
        return ""
    value = raw.get(header)
    return "" if value is None else str(value).strip()


def _parse_bool(value: str, default: bool, message: str) -> bool:
    if not value:
        return default
    token = value.casefold()
    if token in {"yes", "y", "true", "t", "1", "rx"}:
        return True
    if token in {"no", "n", "false", "f", "0"}:
        return False
    raise ValueError(message)


def _parse_money(value: str, message: str) -> Decimal | None:
    if not value:
        return None
    token = re.sub(r"(?i)\bpkr\b|rs\.?|[₹₨]", "", value.replace(",", "")).strip()
    try:
        amount = Decimal(token)
    except InvalidOperation:
        raise ValueError(message)
    if amount < 0 or amount > Decimal("99999999.99"):
        raise ValueError(message)
    return amount.quantize(Decimal("0.01"))


def _parse_int(value: str, message: str) -> int | None:
    if not value:
        return None
    token = value.replace(",", "").strip()
    if not re.fullmatch(r"-?\d+", token):
        raise ValueError(message)
    return int(token)


def _parse_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("Expiry date must be YYYY-MM-DD")


def _check_length(field: str, value: str | None):
    if value and len(value) > _LENGTH_LIMITS.get(field, 255):
        if field == "sku":
            raise ValueError("SKU is too long")
        if field == "name":
            raise ValueError("Medicine name is too long")
        raise ValueError("A column value is too long")


def _parse_import_row(raw: dict, columns: dict[str, str]) -> tuple[dict, dict | None]:
    name = _cell(raw, columns, "name")
    sku = _cell(raw, columns, "sku")
    salt = _cell(raw, columns, "salt") or _cell(raw, columns, "generic_name")
    form = _cell(raw, columns, "form").casefold() or "tablet"
    if form not in _FORMS:
        raise ValueError("Unknown medicine form")
    price = _parse_money(_cell(raw, columns, "unit_price"), "Price must be a number")
    reorder = _parse_int(_cell(raw, columns, "reorder_level"), "Reorder level must be a whole number")
    if reorder is not None and reorder < 0:
        raise ValueError("Reorder level must be a whole number")
    quantity = _parse_int(_cell(raw, columns, "quantity"), "Quantity must be a whole number")
    batch_number = _cell(raw, columns, "batch_number")
    expiry = _cell(raw, columns, "expiry_date")
    cost = _parse_money(_cell(raw, columns, "cost_price"), "Cost must be a number")
    stock_started = any([_cell(raw, columns, "quantity"), batch_number, expiry])
    batch = None
    if stock_started:
        if quantity is not None and quantity < 1:
            raise ValueError("Quantity must be at least 1")
        if quantity is None or not batch_number or not expiry:
            raise ValueError("Quantity needs a batch number and expiry date")
        batch = {
            "batch_number": batch_number,
            "expiry_date": _parse_date(expiry),
            "quantity": quantity,
            "cost_price": cost if cost is not None else Decimal("0"),
            "selling_price": price if price is not None else Decimal("0"),
        }
    fields = {
        "sku": sku,
        "name": name,
        "salt": salt or None,
        "generic_name": salt or None,
        "manufacturer": _cell(raw, columns, "manufacturer") or None,
        "form": form,
        "strength": _cell(raw, columns, "strength") or None,
        "pack_size": _cell(raw, columns, "pack_size") or None,
        "category": _cell(raw, columns, "category") or None,
        "barcode": _cell(raw, columns, "barcode") or None,
        "rack_location": _cell(raw, columns, "rack_location") or None,
        "unit_price": price if price is not None else Decimal("0"),
        "reorder_level": 10 if reorder is None else reorder,
        "requires_prescription": _parse_bool(
            _cell(raw, columns, "requires_prescription"),
            False,
            "Use yes or no for the prescription column",
        ),
        "notes": _cell(raw, columns, "notes") or None,
        "is_active": _parse_bool(_cell(raw, columns, "is_active"), True, "Use yes or no for the active column"),
    }
    for key, value in fields.items():
        _check_length(key, value if isinstance(value, str) else None)
    if batch:
        _check_length("batch_number", batch["batch_number"])
    prepared = _prepare_medicine_fields(fields)
    return prepared, batch


def import_medicines_csv(db: Session, pharmacy_id: int, raw: bytes) -> dict:
    if not db.query(models.Pharmacy.id).filter(models.Pharmacy.id == pharmacy_id).first():
        raise ValueError("Pharmacy not found")
    text = _decode_csv(raw)
    if not text.strip():
        raise ValueError("The CSV file is empty")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("The CSV needs name and sku columns")
    columns = _column_map(list(reader.fieldnames))
    if "name" not in columns or "sku" not in columns:
        raise ValueError("The CSV needs name and sku columns")

    seen = {sku.casefold() for (sku,) in db.query(models.Medicine.sku).filter(models.Medicine.pharmacy_id == pharmacy_id)}
    created = 0
    skipped = []
    errors = []
    data_rows = 0
    for index, raw_row in enumerate(reader, start=2):
        if not raw_row or not any((value or "").strip() for value in raw_row.values() if value is not None):
            continue
        data_rows += 1
        if data_rows > MAX_IMPORT_ROWS:
            errors.append({"row": index, "sku": None, "name": None, "message": "Only 1000 rows can be imported at once"})
            break
        sku = _cell(raw_row, columns, "sku") or None
        name = _cell(raw_row, columns, "name") or None
        try:
            fields, batch = _parse_import_row(raw_row, columns)
        except ValueError as exc:
            errors.append({"row": index, "sku": sku, "name": name, "message": str(exc)})
            continue
        key = fields["sku"].casefold()
        if key in seen:
            skipped.append({"row": index, "sku": fields["sku"], "name": fields["name"], "message": "SKU already exists for this pharmacy"})
            continue
        try:
            with db.begin_nested():
                medicine = models.Medicine(pharmacy_id=pharmacy_id, **fields)
                db.add(medicine)
                db.flush()
                if batch:
                    db.add(models.StockBatch(medicine_id=medicine.id, **batch))
                    db.flush()
        except IntegrityError:
            skipped.append({"row": index, "sku": fields["sku"], "name": fields["name"], "message": "SKU already exists for this pharmacy"})
            continue
        seen.add(key)
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}
