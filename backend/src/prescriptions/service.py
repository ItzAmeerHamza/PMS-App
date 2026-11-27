from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from .. import models
from ..core.audit import record_audit
from ..core.outbox import emit_event
from ..core.scope import signed_in_pharmacy, visible
from ..core.transaction import business_transaction
from ..inventory.service import allocate_stock
from . import schemas


def _blank(value: str | None) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _item_snapshot(item: models.PrescriptionItem) -> dict:
    medicine = item.medicine
    salt = None
    company = None
    name = None
    if medicine:
        name = medicine.name
        salt = medicine.salt or medicine.generic_name
        company = medicine.manufacturer
    return {
        "medicine_name": item.medicine_name or name,
        "medicine_salt": item.medicine_salt or salt,
        "medicine_company": item.medicine_company or company,
    }


def prescription_snapshot(prescription: models.Prescription) -> dict:
    """Full prescription snapshot for sync, items included (items have no events of their own)."""
    return {
        "public_id": prescription.public_id,
        "version": prescription.version,
        "patient_public_id": prescription.patient.public_id,
        "doctor_name": prescription.doctor_name,
        "complaint": prescription.complaint,
        "diagnosis": prescription.diagnosis,
        "notes": prescription.notes,
        "status": prescription.status,
        "prescribed_at": prescription.prescribed_at,
        "dispensed_at": prescription.dispensed_at,
        "created_at": prescription.created_at,
        "items": [
            {
                "public_id": item.public_id,
                "medicine_public_id": item.medicine.public_id if item.medicine else None,
                "medicine_name": item.medicine_name,
                "medicine_salt": item.medicine_salt,
                "medicine_company": item.medicine_company,
                "dosage": item.dosage,
                "frequency": item.frequency,
                "duration_days": item.duration_days,
                "quantity": item.quantity,
                "instructions": item.instructions,
            }
            for item in sorted(prescription.items, key=lambda i: i.id)
        ],
    }


def emit_prescription(db: Session, prescription: models.Prescription, operation: str) -> None:
    """Write prescription.created / prescription.updated for the current version."""
    db.flush()
    db.refresh(prescription)
    db.expire(prescription, ["items"])
    emit_event(db, pharmacy_id=prescription.pharmacy_id, entity_type="prescription", entity_id=prescription.public_id,
               operation=operation, entity_version=prescription.version, payload=prescription_snapshot(prescription))


def serialize_prescription(prescription: models.Prescription) -> dict:
    patient = prescription.patient
    return {
        "id": prescription.id,
        "pharmacy_id": prescription.pharmacy_id,
        "patient_id": prescription.patient_id,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "doctor_name": prescription.doctor_name,
        "complaint": prescription.complaint,
        "diagnosis": prescription.diagnosis,
        "notes": prescription.notes,
        "status": prescription.status,
        "prescribed_at": prescription.prescribed_at,
        "dispensed_at": prescription.dispensed_at,
        "sale_id": next((sale.id for sale in prescription.sales if sale.status == "paid"), None),
        "items": [
            {
                "id": item.id,
                "medicine_id": item.medicine_id,
                **_item_snapshot(item),
                "dosage": item.dosage,
                "frequency": item.frequency,
                "duration_days": item.duration_days,
                "quantity": item.quantity,
                "instructions": item.instructions,
            }
            for item in prescription.items
        ],
        "created_at": prescription.created_at,
    }


def _query(db: Session):
    return db.query(models.Prescription).options(
        joinedload(models.Prescription.patient),
        joinedload(models.Prescription.items).joinedload(models.PrescriptionItem.medicine),
    )


def list_prescriptions(
    db: Session,
    pharmacy_id: int,
    patient_id: int | None = None,
    status: str | None = None,
    order: str = "desc",
) -> list[dict]:
    """Prescriptions of the signed-in pharmacy.

    order="asc" is the patient's history, oldest first; "desc" (default) is the newest-first
    worklist. Ties on prescribed_at fall back to id, so the order is stable.
    """
    pharmacy_id = signed_in_pharmacy(db, pharmacy_id)
    query = _query(db).filter(models.Prescription.pharmacy_id == pharmacy_id)
    if patient_id:
        query = query.filter(models.Prescription.patient_id == patient_id)
    if status:
        query = query.filter(models.Prescription.status == status)
    if order == "asc":
        query = query.order_by(models.Prescription.prescribed_at.asc(), models.Prescription.id.asc())
    else:
        query = query.order_by(models.Prescription.prescribed_at.desc(), models.Prescription.id.desc())
    return [serialize_prescription(rx) for rx in query.all()]


def get_prescription(db: Session, prescription_id: int) -> models.Prescription | None:
    """None for another pharmacy's prescription, as if it did not exist."""
    prescription = _query(db).filter(models.Prescription.id == prescription_id).first()
    if prescription is None or not visible(db, prescription.pharmacy_id):
        return None
    return prescription


def create_prescription(db: Session, payload: schemas.PrescriptionCreate) -> models.Prescription:
    pharmacy_id = signed_in_pharmacy(db, payload.pharmacy_id)
    patient = db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first()
    if not patient or patient.pharmacy_id != pharmacy_id or patient.deleted_at is not None:
        raise ValueError("Patient not found")
    if not payload.items:
        raise ValueError("Add at least one medicine from the store")

    with business_transaction(db):
        prescription = models.Prescription(
            pharmacy_id=pharmacy_id,
            # Python-side UTC with microseconds: two visits in the same second still sort correctly.
            prescribed_at=datetime.now(timezone.utc),
            patient_id=payload.patient_id,
            doctor_name=_blank(payload.doctor_name),
            complaint=_blank(payload.complaint),
            diagnosis=_blank(payload.diagnosis),
            notes=_blank(payload.notes),
            status="recorded",
        )
        db.add(prescription)
        db.flush()
        for item in payload.items:
            medicine = db.query(models.Medicine).filter(models.Medicine.id == item.medicine_id).first()
            if not medicine or medicine.pharmacy_id != pharmacy_id:
                raise ValueError("Select a medicine from this store")
            if not medicine.is_active:
                raise ValueError(f"{medicine.name} is inactive")
            db.add(
                models.PrescriptionItem(
                    prescription_id=prescription.id,
                    **item.model_dump(),
                    medicine_name=medicine.name,
                    medicine_salt=medicine.salt or medicine.generic_name,
                    medicine_company=medicine.manufacturer,
                )
            )
        emit_prescription(db, prescription, "created")
        record_audit(db, "prescription.created", pharmacy_id=prescription.pharmacy_id, entity_type="prescription", entity_public_id=prescription.public_id)
    return get_prescription(db, prescription.id)


def cancel_prescription(db: Session, prescription_id: int) -> models.Prescription | None:
    prescription = get_prescription(db, prescription_id)
    if not prescription:
        return None
    if prescription.status == "dispensed":
        raise ValueError("Cannot cancel a dispensed prescription")
    with business_transaction(db):
        prescription.status = "cancelled"
        emit_prescription(db, prescription, "updated")
        record_audit(db, "prescription.cancelled", pharmacy_id=prescription.pharmacy_id, entity_type="prescription", entity_public_id=prescription.public_id)
    return get_prescription(db, prescription_id)


def dispense_prescription(db: Session, prescription_id: int) -> models.Prescription:
    prescription = get_prescription(db, prescription_id)
    if not prescription:
        raise ValueError("Prescription not found")
    if prescription.status != "recorded":
        raise ValueError("Only recorded prescriptions can be dispensed")

    with business_transaction(db):
        for item in prescription.items:
            allocate_stock(db, item.medicine, item.quantity, "dispense", source_type="prescription", source_id=prescription.id)
        prescription.status = "dispensed"
        prescription.dispensed_at = datetime.now(timezone.utc)
        emit_prescription(db, prescription, "updated")
        record_audit(db, "prescription.dispensed", pharmacy_id=prescription.pharmacy_id, entity_type="prescription", entity_public_id=prescription.public_id)
    return get_prescription(db, prescription_id)
