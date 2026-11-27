"""Apply one validated event to the replica. Runs inside the caller's transaction.

Raises OrderingConflict when the event cannot be applied yet (or ever, for a stale
version). The caller rolls back, so nothing partial is left behind.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from . import schemas


class OrderingConflict(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _find(db: Session, model, shop_id: uuid.UUID, public_id: uuid.UUID, lock: bool = False):
    query = select(model).where(model.shop_id == shop_id, model.public_id == public_id)
    if lock:
        query = query.with_for_update()
    return db.scalars(query).first()


def _check_version(existing, event: schemas.Envelope):
    """created: entity must not exist. updated/deleted: must be exactly stored version + 1."""
    if event.operation == "created":
        if existing is not None:
            raise OrderingConflict("entity_exists")
        return
    if existing is None:
        raise OrderingConflict("entity_missing")
    if event.entity_version <= existing.version:
        raise OrderingConflict("stale_version")
    if event.entity_version != existing.version + 1:
        raise OrderingConflict("version_gap")


PRODUCT_FIELDS = ("sku", "name", "salt", "generic_name", "manufacturer", "form", "strength", "pack_size", "category",
                  "barcode", "rack_location", "unit_price", "reorder_level", "requires_prescription", "notes",
                  "is_active", "deleted_at")
PATIENT_FIELDS = ("first_name", "last_name", "phone", "date_of_birth", "gender", "address", "allergies", "notes",
                  "deleted_at")
PRESCRIPTION_FIELDS = ("doctor_name", "complaint", "diagnosis", "notes", "status", "prescribed_at", "dispensed_at")
ITEM_FIELDS = ("medicine_name", "medicine_salt", "medicine_company", "dosage", "frequency", "duration_days",
               "quantity", "instructions")


def apply_product(db: Session, shop_id, event, payload) -> None:
    existing = _find(db, models.Product, shop_id, event.entity_id, lock=True)
    _check_version(existing, event)
    if event.operation == "deleted":
        existing.deleted_at = payload.deleted_at
        existing.is_active = False
        existing.version = event.entity_version
        return
    # Snapshot batches are context only: stock changes come from movements.
    values = {field: getattr(payload, field) for field in PRODUCT_FIELDS}
    if existing is None:
        db.add(models.Product(shop_id=shop_id, public_id=payload.public_id, version=event.entity_version,
                              local_created_at=payload.created_at, local_updated_at=payload.updated_at, **values))
    else:
        for field, value in values.items():
            setattr(existing, field, value)
        existing.version = event.entity_version
        existing.local_updated_at = payload.updated_at


def apply_movement(db: Session, shop_id, event, payload: schemas.MovementPayload) -> None:
    if _find(db, models.StockMovement, shop_id, payload.public_id) is not None:
        raise OrderingConflict("entity_exists")
    product = _find(db, models.Product, shop_id, payload.medicine_public_id)
    if product is None:
        raise OrderingConflict("missing_product")
    batch = _find(db, models.StockBatch, shop_id, payload.batch.public_id, lock=True)
    if batch is None:
        batch = models.StockBatch(shop_id=shop_id, public_id=payload.batch.public_id, product_id=product.id,
                                  batch_number=payload.batch.batch_number, expiry_date=payload.batch.expiry_date,
                                  quantity=0, cost_price=payload.batch.cost_price, selling_price=payload.batch.selling_price)
        db.add(batch)
        db.flush()
    elif batch.product_id != product.id:
        raise schemas.InvalidEvent("payload:batch_belongs_to_another_product")
    else:
        batch.batch_number = payload.batch.batch_number
        batch.expiry_date = payload.batch.expiry_date
        batch.cost_price = payload.batch.cost_price
        batch.selling_price = payload.batch.selling_price
    batch.quantity += payload.quantity_delta
    db.add(models.StockMovement(
        shop_id=shop_id, public_id=payload.public_id, product_id=product.id, batch_id=batch.id,
        movement_type=payload.movement_type, quantity_delta=payload.quantity_delta,
        quantity_after=payload.quantity_after, cloud_quantity_after=batch.quantity, reason=payload.reason,
        source_type=payload.source_type, source_ref=payload.source_ref, local_created_at=payload.created_at,
    ))


def apply_patient(db: Session, shop_id, event, payload) -> None:
    existing = _find(db, models.Patient, shop_id, event.entity_id, lock=True)
    _check_version(existing, event)
    if event.operation == "deleted":
        existing.deleted_at = payload.deleted_at
        existing.version = event.entity_version
        return
    values = {field: getattr(payload, field) for field in PATIENT_FIELDS}
    if existing is None:
        db.add(models.Patient(shop_id=shop_id, public_id=payload.public_id, version=event.entity_version,
                              local_created_at=payload.created_at, local_updated_at=payload.updated_at, **values))
    else:
        for field, value in values.items():
            setattr(existing, field, value)
        existing.version = event.entity_version
        existing.local_updated_at = payload.updated_at


def apply_prescription(db: Session, shop_id, event, payload) -> None:
    existing = _find(db, models.Prescription, shop_id, event.entity_id, lock=True)
    _check_version(existing, event)
    if event.operation == "deleted":
        existing.deleted_at = payload.deleted_at
        existing.version = event.entity_version
        return
    patient = _find(db, models.Patient, shop_id, payload.patient_public_id)
    if patient is None:
        raise OrderingConflict("missing_patient")
    products = {}
    for item in payload.items:
        product = _find(db, models.Product, shop_id, item.medicine_public_id)
        if product is None:
            raise OrderingConflict("missing_product")
        products[item.public_id] = product.id
    values = {field: getattr(payload, field) for field in PRESCRIPTION_FIELDS}
    if existing is None:
        existing = models.Prescription(shop_id=shop_id, public_id=payload.public_id, version=event.entity_version,
                                       patient_id=patient.id, local_created_at=payload.created_at, **values)
        db.add(existing)
        db.flush()
    else:
        for field, value in values.items():
            setattr(existing, field, value)
        existing.patient_id = patient.id
        existing.version = event.entity_version
    for item in payload.items:
        row = _find(db, models.PrescriptionItem, shop_id, item.public_id)
        item_values = {field: getattr(item, field) for field in ITEM_FIELDS}
        if row is None:
            db.add(models.PrescriptionItem(shop_id=shop_id, public_id=item.public_id, prescription_id=existing.id,
                                           product_id=products[item.public_id], **item_values))
        elif row.prescription_id != existing.id:
            raise schemas.InvalidEvent("payload:item_belongs_to_another_prescription")
        else:
            for field, value in item_values.items():
                setattr(row, field, value)
            row.product_id = products[item.public_id]


APPLY = {
    "product": apply_product,
    "stock_movement": apply_movement,
    "patient": apply_patient,
    "prescription": apply_prescription,
}
