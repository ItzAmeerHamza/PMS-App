"""Read-only owner queries. Paginated, optionally filtered by shop. No writes to business rows."""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models


def _page(db: Session, query, count_query, limit: int, offset: int, serialize) -> dict:
    total = db.scalar(count_query) or 0
    rows = db.execute(query.limit(limit).offset(offset)).all()
    return {"items": [serialize(*row) for row in rows], "total": total, "limit": limit, "offset": offset}


def _shop_filter(query, column, shop_id):
    return query.where(column == shop_id) if shop_id else query


def _sync_fields(state: models.SynchronizationState | None) -> dict:
    """Last-known sync. reported_pending stays null until the shop reports it."""
    if state is None:
        return {"last_sync_at": None, "last_applied_sequence": None, "events_applied": None,
                "last_result": None, "last_error_code": None, "reported_pending": None,
                "reported_failed": None, "reported_at": None}
    return {
        "last_sync_at": state.last_sync_at, "last_applied_sequence": state.last_applied_sequence,
        "events_applied": state.events_applied, "last_result": state.last_result,
        "last_error_code": state.last_error_code, "reported_pending": state.reported_pending,
        "reported_failed": state.reported_failed, "reported_at": state.reported_at,
    }


def shops(db: Session, limit: int, offset: int) -> dict:
    query = (
        select(models.Shop, models.SynchronizationState)
        .outerjoin(models.SynchronizationState, models.SynchronizationState.shop_id == models.Shop.id)
        .order_by(models.Shop.name, models.Shop.id)
    )
    return _page(db, query, select(func.count()).select_from(models.Shop), limit, offset, lambda s, state: {
        "id": str(s.id), "name": s.name, "created_at": s.created_at, "disabled": s.disabled_at is not None,
        **_sync_fields(state),
    })


def overview(db: Session, shop_id: uuid.UUID | None) -> dict:
    def count(model, *conditions):
        query = select(func.count()).select_from(model)
        if shop_id:
            query = query.where(model.shop_id == shop_id)
        for condition in conditions:
            query = query.where(condition)
        return db.scalar(query) or 0

    units = select(func.coalesce(func.sum(models.StockBatch.quantity), 0))
    if shop_id:
        units = units.where(models.StockBatch.shop_id == shop_id)
    return {
        "shop_id": str(shop_id) if shop_id else None,
        "shops": db.scalar(select(func.count()).select_from(models.Shop)) if not shop_id else 1,
        "products": count(models.Product, models.Product.deleted_at.is_(None)),
        "units_on_hand": int(db.scalar(units) or 0),
        "patients": count(models.Patient, models.Patient.deleted_at.is_(None)),
        "prescriptions": count(models.Prescription),
        "generated_at": datetime.now(timezone.utc),
    }


def _like(value: str | None) -> str | None:
    text = (value or "").strip()
    return f"%{text}%" if text else None


def inventory(db: Session, shop_id, limit: int, offset: int, search: str | None = None, low_stock: bool = False) -> dict:
    qty = func.coalesce(func.sum(models.StockBatch.quantity), 0).label("quantity")
    nearest = func.min(models.StockBatch.expiry_date).label("nearest_expiry")
    base = (
        select(models.Product, qty, nearest)
        .outerjoin(models.StockBatch, models.StockBatch.product_id == models.Product.id)
        .where(models.Product.deleted_at.is_(None))
        .group_by(models.Product.id)
        .order_by(models.Product.name, models.Product.id)
    )
    base = _shop_filter(base, models.Product.shop_id, shop_id)
    needle = _like(search)
    if needle:
        base = base.where(or_(models.Product.name.ilike(needle), models.Product.sku.ilike(needle),
                              models.Product.manufacturer.ilike(needle)))
    if low_stock:
        base = base.having(qty <= func.coalesce(models.Product.reorder_level, 0))
    counted = base.order_by(None).subquery()
    count = select(func.count()).select_from(counted)
    return _page(db, base, count, limit, offset, lambda p, q, e: {
        "shop_id": str(p.shop_id), "public_id": str(p.public_id), "version": p.version, "sku": p.sku, "name": p.name,
        "manufacturer": p.manufacturer, "unit_price": p.unit_price, "reorder_level": p.reorder_level,
        "is_active": p.is_active, "quantity": int(q), "nearest_expiry": e, "synced_at": p.synced_at,
    })


def patients(db: Session, shop_id, limit: int, offset: int, search: str | None = None) -> dict:
    query = select(models.Patient).where(models.Patient.deleted_at.is_(None)).order_by(
        models.Patient.last_name, models.Patient.first_name, models.Patient.id)
    query = _shop_filter(query, models.Patient.shop_id, shop_id)
    count = _shop_filter(select(func.count()).select_from(models.Patient).where(models.Patient.deleted_at.is_(None)),
                         models.Patient.shop_id, shop_id)
    needle = _like(search)
    if needle:
        full = models.Patient.first_name + " " + models.Patient.last_name
        query = query.where(or_(models.Patient.first_name.ilike(needle), models.Patient.last_name.ilike(needle),
                                models.Patient.phone.ilike(needle), full.ilike(needle)))
        count = count.where(or_(models.Patient.first_name.ilike(needle), models.Patient.last_name.ilike(needle),
                                models.Patient.phone.ilike(needle), full.ilike(needle)))
    return _page(db, query, count, limit, offset, lambda p: {
        "shop_id": str(p.shop_id), "public_id": str(p.public_id), "version": p.version, "first_name": p.first_name,
        "last_name": p.last_name, "phone": p.phone, "date_of_birth": p.date_of_birth, "gender": p.gender,
        "allergies": p.allergies, "synced_at": p.synced_at,
    })


def prescriptions(db: Session, shop_id, limit: int, offset: int, search: str | None = None,
                  date_from: date | None = None, date_to: date | None = None, oldest_first: bool = False,
                  patient_public_id: uuid.UUID | None = None) -> dict:
    order = (models.Prescription.prescribed_at.asc().nulls_last(), models.Prescription.id.asc()) if oldest_first else (
        models.Prescription.prescribed_at.desc().nulls_last(), models.Prescription.id.desc())
    query = select(models.Prescription, models.Patient).join(
        models.Patient, models.Patient.id == models.Prescription.patient_id).order_by(*order)
    query = _shop_filter(query, models.Prescription.shop_id, shop_id)
    count = _shop_filter(select(func.count()).select_from(models.Prescription), models.Prescription.shop_id, shop_id)
    needle = _like(search)
    if needle:
        full = models.Patient.first_name + " " + models.Patient.last_name
        query = query.where(or_(full.ilike(needle), models.Patient.phone.ilike(needle)))
        count = count.where(models.Prescription.patient_id.in_(
            select(models.Patient.id).where(or_(full.ilike(needle), models.Patient.phone.ilike(needle)))))
    if patient_public_id is not None:
        query = query.where(models.Patient.public_id == patient_public_id)
        count = count.where(models.Prescription.patient_id.in_(
            select(models.Patient.id).where(models.Patient.public_id == patient_public_id)))
    if date_from is not None:
        query = query.where(func.date(models.Prescription.prescribed_at) >= date_from)
        count = count.where(func.date(models.Prescription.prescribed_at) >= date_from)
    if date_to is not None:
        query = query.where(func.date(models.Prescription.prescribed_at) <= date_to)
        count = count.where(func.date(models.Prescription.prescribed_at) <= date_to)
    page = _page(db, query, count, limit, offset, lambda rx, patient: {
        "shop_id": str(rx.shop_id), "public_id": str(rx.public_id), "version": rx.version, "status": rx.status,
        "patient_public_id": str(patient.public_id), "patient_name": f"{patient.first_name} {patient.last_name}",
        "doctor_name": rx.doctor_name, "diagnosis": rx.diagnosis, "prescribed_at": rx.prescribed_at,
        "dispensed_at": rx.dispensed_at, "items": [], "_id": rx.id, "synced_at": rx.synced_at,
    })
    ids = [item.pop("_id") for item in page["items"]]
    if ids:
        items = db.scalars(select(models.PrescriptionItem).where(models.PrescriptionItem.prescription_id.in_(ids))
                           .order_by(models.PrescriptionItem.id)).all()
        by_rx: dict[int, list] = {}
        for item in items:
            by_rx.setdefault(item.prescription_id, []).append({
                "public_id": str(item.public_id), "medicine_name": item.medicine_name, "dosage": item.dosage,
                "frequency": item.frequency, "duration_days": item.duration_days, "quantity": item.quantity,
                "instructions": item.instructions,
            })
        for row, rx_id in zip(page["items"], ids):
            row["items"] = by_rx.get(rx_id, [])
    return page


def sync_status(db: Session, shop_id, limit: int, offset: int) -> dict:
    query = _shop_filter(
        select(models.Shop, models.SynchronizationState)
        .outerjoin(models.SynchronizationState, models.SynchronizationState.shop_id == models.Shop.id)
        .order_by(models.Shop.name, models.Shop.id), models.Shop.id, shop_id)
    count = _shop_filter(select(func.count()).select_from(models.Shop), models.Shop.id, shop_id)
    return _page(db, query, count, limit, offset, lambda shop, state: {
        "shop_id": str(shop.id), "shop_name": shop.name, "created_at": shop.created_at,
        # Last values the shop reported. reported_pending is null until a report arrives.
        **_sync_fields(state),
    })


def movements(db: Session, shop_id, limit: int, offset: int, product_public_id: uuid.UUID | None = None,
              date_from: date | None = None, date_to: date | None = None) -> dict:
    query = (
        select(models.StockMovement, models.Product, models.StockBatch)
        .join(models.Product, models.Product.id == models.StockMovement.product_id)
        .join(models.StockBatch, models.StockBatch.id == models.StockMovement.batch_id)
        .order_by(models.StockMovement.local_created_at.desc().nulls_last(), models.StockMovement.id.desc())
    )
    query = _shop_filter(query, models.StockMovement.shop_id, shop_id)
    count = _shop_filter(select(func.count()).select_from(models.StockMovement), models.StockMovement.shop_id, shop_id)
    if product_public_id is not None:
        query = query.where(models.Product.public_id == product_public_id)
        count = count.where(models.StockMovement.product_id.in_(
            select(models.Product.id).where(models.Product.public_id == product_public_id)))
    if date_from is not None:
        query = query.where(func.date(models.StockMovement.local_created_at) >= date_from)
        count = count.where(func.date(models.StockMovement.local_created_at) >= date_from)
    if date_to is not None:
        query = query.where(func.date(models.StockMovement.local_created_at) <= date_to)
        count = count.where(func.date(models.StockMovement.local_created_at) <= date_to)
    return _page(db, query, count, limit, offset, lambda movement, product, batch: {
        "shop_id": str(movement.shop_id), "public_id": str(movement.public_id),
        "product_public_id": str(product.public_id), "product_name": product.name, "sku": product.sku,
        "batch_number": batch.batch_number, "movement_type": movement.movement_type,
        "quantity_delta": movement.quantity_delta, "quantity_after": movement.quantity_after,
        "occurred_at": movement.local_created_at, "synced_at": movement.synced_at,
    })


def product_detail(db: Session, shop_id: uuid.UUID, public_id: uuid.UUID,
                   date_from: date | None = None, date_to: date | None = None) -> dict | None:
    product = db.scalars(select(models.Product).where(
        models.Product.shop_id == shop_id, models.Product.public_id == public_id, models.Product.deleted_at.is_(None)
    )).first()
    if product is None:
        return None
    batches = db.scalars(select(models.StockBatch).where(models.StockBatch.product_id == product.id)
                         .order_by(models.StockBatch.expiry_date, models.StockBatch.id)).all()
    history = movements(db, shop_id, 50, 0, product_public_id=public_id, date_from=date_from, date_to=date_to)
    return {
        "shop_id": str(product.shop_id), "public_id": str(product.public_id), "sku": product.sku, "name": product.name,
        "manufacturer": product.manufacturer, "form": product.form, "strength": product.strength,
        "unit_price": product.unit_price, "reorder_level": product.reorder_level, "is_active": product.is_active,
        "quantity": sum(batch.quantity for batch in batches),
        "batches": [{"batch_number": b.batch_number, "expiry_date": b.expiry_date, "quantity": b.quantity} for b in batches],
        "movements": history["items"], "synced_at": product.synced_at,
    }


def patient_detail(db: Session, shop_id: uuid.UUID, public_id: uuid.UUID) -> dict | None:
    patient = db.scalars(select(models.Patient).where(
        models.Patient.shop_id == shop_id, models.Patient.public_id == public_id)).first()
    if patient is None:
        return None
    history = prescriptions(db, shop_id, 100, 0, oldest_first=True, patient_public_id=public_id)
    return {
        "shop_id": str(patient.shop_id), "public_id": str(patient.public_id), "first_name": patient.first_name,
        "last_name": patient.last_name, "phone": patient.phone, "date_of_birth": patient.date_of_birth,
        "gender": patient.gender, "allergies": patient.allergies, "deleted": patient.deleted_at is not None,
        "synced_at": patient.synced_at, "prescriptions": history["items"],
    }
