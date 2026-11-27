from collections import OrderedDict
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session, joinedload

from .. import models
from ..core.audit import record_audit
from ..core.transaction import business_transaction
from ..inventory.service import allocate_stock, change_batch_quantity
from ..prescriptions.service import emit_prescription
from . import schemas

CENT = Decimal("0.01")
ZERO = Decimal("0")


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def _blank(value: str | None) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; they are stored in UTC, so label them as such."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def serialize_sale(sale: models.Sale, with_items: bool = True) -> dict:
    return {
        "id": sale.id,
        "pharmacy_id": sale.pharmacy_id,
        "invoice_number": sale.invoice_number,
        "patient_id": sale.patient_id,
        "prescription_id": sale.prescription_id,
        "customer_name": sale.customer_name,
        "customer_phone": sale.customer_phone,
        "staff_name": sale.staff.full_name if sale.staff else None,
        "subtotal": sale.subtotal,
        "discount_percent": sale.discount_percent,
        "discount_amount": sale.discount_amount,
        "tax_percent": sale.tax_percent,
        "tax_amount": sale.tax_amount,
        "total": sale.total,
        "payment_method": sale.payment_method,
        "amount_paid": sale.amount_paid,
        "change_due": sale.change_due,
        "notes": sale.notes,
        "status": sale.status,
        "voided_at": as_utc(sale.voided_at),
        "void_reason": sale.void_reason,
        "created_at": as_utc(sale.created_at),
        "item_count": sum(item.quantity for item in sale.items),
        "items": [
            {
                "id": item.id,
                "medicine_id": item.medicine_id,
                "medicine_name": item.medicine_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "line_total": item.line_total,
                "allocations": [
                    {
                        "batch_id": alloc.batch_id,
                        "batch_number": alloc.batch_number,
                        "expiry_date": alloc.expiry_date,
                        "quantity": alloc.quantity,
                    }
                    for alloc in item.allocations
                ],
            }
            for item in sale.items
        ]
        if with_items
        else [],
    }


def _query(db: Session):
    return db.query(models.Sale).options(
        joinedload(models.Sale.staff),
        joinedload(models.Sale.items).joinedload(models.SaleItem.allocations),
    )


def get_sale(db: Session, sale_id: int) -> models.Sale | None:
    return _query(db).filter(models.Sale.id == sale_id).first()


def list_sales(
    db: Session,
    pharmacy_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    search: str | None = None,
    status: str | None = None,
) -> dict:
    query = _query(db).filter(models.Sale.pharmacy_id == pharmacy_id)
    if start:
        query = query.filter(models.Sale.created_at >= _naive_utc(start))
    if end:
        query = query.filter(models.Sale.created_at < _naive_utc(end))
    if status:
        query = query.filter(models.Sale.status == status)
    if search and search.strip():
        like = f"%{search.strip()}%"
        query = query.filter(
            models.Sale.invoice_number.ilike(like)
            | models.Sale.customer_name.ilike(like)
            | models.Sale.customer_phone.ilike(like)
        )
    sales = query.order_by(models.Sale.created_at.desc(), models.Sale.id.desc()).all()
    return {"sales": [serialize_sale(sale, with_items=False) for sale in sales], "summary": summarize(sales)}


def summarize(sales: list[models.Sale]) -> dict:
    paid = [sale for sale in sales if sale.status == "paid"]
    by_method: dict[str, Decimal] = {}
    for sale in paid:
        by_method[sale.payment_method] = _money(by_method.get(sale.payment_method, ZERO) + sale.total)
    return {
        "count": len(paid),
        "total": _money(sum((sale.total for sale in paid), ZERO)),
        "discount": _money(sum((sale.discount_amount for sale in paid), ZERO)),
        "tax": _money(sum((sale.tax_amount for sale in paid), ZERO)),
        "by_method": by_method,
        "voided_count": len(sales) - len(paid),
    }


def sales_between(db: Session, pharmacy_id: int, start: datetime, end: datetime) -> dict:
    sales = (
        db.query(models.Sale)
        .filter(
            models.Sale.pharmacy_id == pharmacy_id,
            models.Sale.created_at >= _naive_utc(start),
            models.Sale.created_at < _naive_utc(end),
        )
        .all()
    )
    return summarize(sales)


def _merge_lines(items: list[schemas.SaleItemCreate]) -> "OrderedDict[int, int]":
    merged: OrderedDict[int, int] = OrderedDict()
    for item in items:
        merged[item.medicine_id] = merged.get(item.medicine_id, 0) + item.quantity
    return merged


def create_sale(db: Session, payload: schemas.SaleCreate) -> models.Sale:
    with business_transaction(db):
        sale = _create_sale(db, payload)
    return get_sale(db, sale.id)


def _create_sale(db: Session, payload: schemas.SaleCreate) -> models.Sale:
    if not payload.items:
        raise ValueError("Add at least one medicine to the bill")

    patient = None
    prescription = None
    if payload.prescription_id:
        prescription = (
            db.query(models.Prescription).filter(models.Prescription.id == payload.prescription_id).first()
        )
        if not prescription or prescription.pharmacy_id != payload.pharmacy_id:
            raise ValueError("Prescription not found")
        if prescription.status != "recorded":
            raise ValueError("This prescription is already billed or cancelled")
        patient = prescription.patient
    elif payload.patient_id:
        patient = db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first()
        if not patient or patient.pharmacy_id != payload.pharmacy_id or patient.deleted_at is not None:
            raise ValueError("Patient not found")

    customer_name = _blank(payload.customer_name)
    customer_phone = _blank(payload.customer_phone)
    if patient:
        customer_name = customer_name or f"{patient.first_name} {patient.last_name}".strip()
        customer_phone = customer_phone or patient.phone

    sale = models.Sale(
        pharmacy_id=payload.pharmacy_id,
        patient_id=patient.id if patient else None,
        prescription_id=prescription.id if prescription else None,
        staff_id=db.info.get("staff_id"),
        customer_name=customer_name,
        customer_phone=customer_phone,
        payment_method=payload.payment_method,
        notes=_blank(payload.notes),
        status="paid",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(sale)
    db.flush()
    # Set now so the sale's stock movement events can reference the bill.
    sale.invoice_number = f"INV-{sale.id:06d}"

    subtotal = ZERO
    for medicine_id, quantity in _merge_lines(payload.items).items():
        medicine = db.query(models.Medicine).filter(models.Medicine.id == medicine_id).first()
        if not medicine or medicine.pharmacy_id != payload.pharmacy_id:
            raise ValueError("Select a medicine from this store")
        if not medicine.is_active:
            raise ValueError(f"{medicine.name} is inactive")
        unit_price = _money(medicine.unit_price)
        line_total = _money(unit_price * quantity)
        item = models.SaleItem(
            sale_id=sale.id,
            medicine_id=medicine.id,
            medicine_name=medicine.name,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        )
        for batch, taken in allocate_stock(db, medicine, quantity, "sale", source_type="sale", source_id=sale.id):
            item.allocations.append(
                models.SaleAllocation(
                    batch_id=batch.id,
                    batch_number=batch.batch_number,
                    expiry_date=batch.expiry_date,
                    quantity=taken,
                )
            )
        db.add(item)
        subtotal += line_total

    subtotal = _money(subtotal)
    discount_percent = _money(payload.discount_percent)
    tax_percent = _money(payload.tax_percent)
    discount_amount = _money(subtotal * discount_percent / 100)
    taxable = subtotal - discount_amount
    tax_amount = _money(taxable * tax_percent / 100)
    total = _money(taxable + tax_amount)

    if payload.payment_method == "cash" and payload.amount_paid is not None:
        amount_paid = _money(payload.amount_paid)
        if amount_paid < total:
            raise ValueError("Amount received is less than the bill total")
    else:
        amount_paid = total

    sale.subtotal = subtotal
    sale.discount_percent = discount_percent
    sale.discount_amount = discount_amount
    sale.tax_percent = tax_percent
    sale.tax_amount = tax_amount
    sale.total = total
    sale.amount_paid = amount_paid
    sale.change_due = _money(amount_paid - total)
    if prescription:
        prescription.status = "dispensed"
        prescription.dispensed_at = datetime.now(timezone.utc)
        emit_prescription(db, prescription, "updated")
        record_audit(db, "prescription.dispensed", pharmacy_id=sale.pharmacy_id, entity_type="prescription", entity_public_id=prescription.public_id)

    record_audit(db, "sale.created", pharmacy_id=sale.pharmacy_id, entity_type="sale")
    return sale


def void_sale(db: Session, sale_id: int, reason: str | None) -> models.Sale | None:
    sale = get_sale(db, sale_id)
    if not sale:
        return None
    if sale.status != "paid":
        raise ValueError("This bill is already void")
    with business_transaction(db):
        for item in sale.items:
            for alloc in item.allocations:
                batch = db.query(models.StockBatch).filter(models.StockBatch.id == alloc.batch_id).first()
                if batch:
                    # Same batch the sale took from, recorded as a void movement.
                    change_batch_quantity(db, batch, alloc.quantity, "void", source_type="sale", source_id=sale.id)
        if sale.prescription and sale.prescription.status == "dispensed":
            sale.prescription.status = "recorded"
            sale.prescription.dispensed_at = None
            emit_prescription(db, sale.prescription, "updated")
        sale.status = "void"
        sale.voided_at = datetime.now(timezone.utc).replace(tzinfo=None)
        sale.void_reason = _blank(reason)
        record_audit(db, "sale.voided", pharmacy_id=sale.pharmacy_id, entity_type="sale")
    return get_sale(db, sale_id)
