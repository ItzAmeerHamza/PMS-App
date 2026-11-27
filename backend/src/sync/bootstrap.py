"""One-time upload of rows that have no outbox history.

Shops (and the dev seed) can hold months of products, movements, patients, and
prescriptions that were never given a sync event. This writes those snapshots
into ``sync_outbox`` with ``origin='bootstrap'``, in dependency order:

    products, then stock movements, then patients, then prescriptions

The shop itself is registered by the owner before a device code exists, so there
is no shop event.

A cursor on ``sync_state`` remembers how far the scan got. Stopping halfway and
starting again does not emit a second event for the same row: bootstrap event
ids are derived from the shop, the entity, and the version. Live writes that
happen during the scan stay ``origin='live'`` and are uploaded only after every
bootstrap event has been acknowledged or failed.

When a row already has a live ``created`` event, it is skipped. When its first
live event is an update or a delete, a predecessor ``created`` is emitted at
version - 1 so the cloud can apply the real events afterwards. The predecessor
is not the historical row; the live events carry the real snapshots.
"""

import uuid

from sqlalchemy.orm import Session, selectinload

from .. import models
from ..core.outbox import emit_event
from ..core.transaction import business_transaction
from ..inventory.service import _source_ref, batch_snapshot, product_snapshot
from ..patients.service import patient_snapshot
from ..prescriptions.service import prescription_snapshot

# Stable namespace for bootstrap event ids. Not a secret.
_NAMESPACE = uuid.UUID("6f1c2a8e-7b44-4e1a-9c3d-0a5e8b7c6d11")
_STAGES = ("products", "movements", "patients", "prescriptions")


def bootstrap_event_id(shop_id: str, entity_type: str, entity_id: str, version: int) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{shop_id}:{entity_type}:{entity_id}:created:{version}"))


def advance_bootstrap(db: Session, *, chunk: int = 200) -> int:
    """Emit up to ``chunk`` bootstrap considerations. Returns how many rows were examined.

    A return of 0 with status still ``running`` means the current stage has nothing
    left; this function advances the stage itself, so 0 means bootstrap is already
    complete or there is no sync_state row.
    """
    if chunk <= 0:
        return 0
    state = db.query(models.SyncState).order_by(models.SyncState.pharmacy_id).first()
    if state is None or state.bootstrap_status != "running":
        return 0
    examined = 0
    with business_transaction(db):
        while state.bootstrap_status == "running" and examined < chunk:
            found = _examine(db, state, chunk - examined)
            examined += found
            if found == 0:
                _advance_stage(state)
    return examined


def _advance_stage(state: models.SyncState) -> None:
    if state.bootstrap_stage not in _STAGES:
        state.bootstrap_status = "complete"
        state.bootstrap_stage = "done"
        state.bootstrap_cursor = 0
        return
    index = _STAGES.index(state.bootstrap_stage)
    if index == len(_STAGES) - 1:
        state.bootstrap_status = "complete"
        state.bootstrap_stage = "done"
        state.bootstrap_cursor = 0
        return
    state.bootstrap_stage = _STAGES[index + 1]
    state.bootstrap_cursor = 0


def _examine(db: Session, state: models.SyncState, limit: int) -> int:
    stage = state.bootstrap_stage
    if stage == "products":
        return _products(db, state, limit)
    if stage == "movements":
        return _movements(db, state, limit)
    if stage == "patients":
        return _patients(db, state, limit)
    if stage == "prescriptions":
        return _prescriptions(db, state, limit)
    return 0


def _products(db: Session, state: models.SyncState, limit: int) -> int:
    rows = (
        db.query(models.Medicine)
        .options(selectinload(models.Medicine.batches))
        .filter(models.Medicine.pharmacy_id == state.pharmacy_id, models.Medicine.id > state.bootstrap_cursor)
        .order_by(models.Medicine.id)
        .limit(limit)
        .all()
    )
    for medicine in rows:
        state.bootstrap_cursor = medicine.id
        _emit_versioned(db, medicine.pharmacy_id, "product", medicine.public_id, medicine.version, product_snapshot(medicine))
    return len(rows)


def _patients(db: Session, state: models.SyncState, limit: int) -> int:
    rows = (
        db.query(models.Patient)
        .filter(models.Patient.pharmacy_id == state.pharmacy_id, models.Patient.id > state.bootstrap_cursor)
        .order_by(models.Patient.id)
        .limit(limit)
        .all()
    )
    for patient in rows:
        state.bootstrap_cursor = patient.id
        _emit_versioned(db, patient.pharmacy_id, "patient", patient.public_id, patient.version, patient_snapshot(patient))
    return len(rows)


def _prescriptions(db: Session, state: models.SyncState, limit: int) -> int:
    rows = (
        db.query(models.Prescription)
        .options(
            selectinload(models.Prescription.patient),
            selectinload(models.Prescription.items).selectinload(models.PrescriptionItem.medicine),
        )
        .filter(models.Prescription.pharmacy_id == state.pharmacy_id, models.Prescription.id > state.bootstrap_cursor)
        .order_by(models.Prescription.id)
        .limit(limit)
        .all()
    )
    for prescription in rows:
        state.bootstrap_cursor = prescription.id
        _emit_versioned(
            db,
            prescription.pharmacy_id,
            "prescription",
            prescription.public_id,
            prescription.version,
            prescription_snapshot(prescription),
        )
    return len(rows)


def _movements(db: Session, state: models.SyncState, limit: int) -> int:
    rows = (
        db.query(models.StockMovement)
        .options(selectinload(models.StockMovement.batch).selectinload(models.StockBatch.medicine))
        .filter(models.StockMovement.pharmacy_id == state.pharmacy_id, models.StockMovement.id > state.bootstrap_cursor)
        .order_by(models.StockMovement.id)
        .limit(limit)
        .all()
    )
    for movement in rows:
        state.bootstrap_cursor = movement.id
        if _outbox_rows(db, movement.public_id, "stock_movement"):
            continue
        batch = movement.batch
        medicine = batch.medicine if batch is not None else None
        if batch is None or medicine is None:
            continue
        shop_id = db.query(models.Pharmacy.public_id).filter(models.Pharmacy.id == movement.pharmacy_id).scalar()
        emit_event(
            db,
            pharmacy_id=movement.pharmacy_id,
            entity_type="stock_movement",
            entity_id=movement.public_id,
            operation="created",
            entity_version=1,
            origin="bootstrap",
            event_id=bootstrap_event_id(shop_id, "stock_movement", movement.public_id, 1),
            payload={
                "public_id": movement.public_id,
                "movement_type": movement.movement_type,
                "quantity_delta": movement.quantity_delta,
                "quantity_after": movement.quantity_after,
                "reason": movement.reason,
                "source_type": movement.source_type,
                "source_ref": _source_ref(db, movement.source_type, movement.source_id),
                "medicine_public_id": medicine.public_id,
                "batch": batch_snapshot(batch),
                "created_at": movement.created_at,
            },
        )
    return len(rows)


def _emit_versioned(db: Session, pharmacy_id: int, entity_type: str, public_id: str, version: int, snapshot: dict) -> None:
    """Emit a created snapshot, or a predecessor when live events already continue the history."""
    if _outbox_rows(db, public_id, entity_type, origin="bootstrap"):
        return
    live = _outbox_rows(db, public_id, entity_type, origin="live")
    if any(row.operation == "created" for row in live):
        return
    payload = dict(snapshot)
    if live:
        version = live[0].entity_version - 1
        if version < 1:
            return
        payload["version"] = version
        payload["deleted_at"] = None
        if entity_type == "product":
            payload["is_active"] = True
    else:
        payload["version"] = version
    shop_id = db.query(models.Pharmacy.public_id).filter(models.Pharmacy.id == pharmacy_id).scalar()
    emit_event(
        db,
        pharmacy_id=pharmacy_id,
        entity_type=entity_type,
        entity_id=public_id,
        operation="created",
        entity_version=version,
        origin="bootstrap",
        event_id=bootstrap_event_id(shop_id, entity_type, public_id, version),
        payload=payload,
    )


def _outbox_rows(db: Session, entity_id: str, entity_type: str, origin: str | None = None) -> list[models.SyncOutbox]:
    query = db.query(models.SyncOutbox).filter(
        models.SyncOutbox.entity_id == entity_id, models.SyncOutbox.entity_type == entity_type
    )
    if origin is not None:
        query = query.filter(models.SyncOutbox.origin == origin)
    return query.order_by(models.SyncOutbox.sequence).all()
