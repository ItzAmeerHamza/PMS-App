"""Patients, scoped to the signed-in manager's pharmacy.

- A repeat visitor is a patient with at least one prescription at this pharmacy.
- Removal is a tombstone (deleted_at), never a physical delete, so prescriptions,
  bills, and a later sync delete event keep a row to refer to.
- Nothing here logs names, phones, allergies, or notes.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from .. import models
from ..core.audit import record_audit
from ..core.outbox import emit_event
from ..core.paging import as_page
from ..core.scope import WrongPharmacy, signed_in_pharmacy, visible
from ..core.transaction import business_transaction
from . import schemas


class PatientError(ValueError):
    pass


class PatientRemoved(PatientError):
    pass


def _utc(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def serialize_patient(patient: models.Patient) -> dict:
    visits = [rx for rx in patient.prescriptions if rx.pharmacy_id == patient.pharmacy_id]
    dates = [rx.prescribed_at for rx in visits if rx.prescribed_at]
    return {
        "id": patient.id,
        "public_id": patient.public_id,
        "pharmacy_id": patient.pharmacy_id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "phone": patient.phone,
        "date_of_birth": patient.date_of_birth,
        "gender": patient.gender,
        "address": patient.address,
        "allergies": patient.allergies,
        "notes": patient.notes,
        "prescription_count": len(visits),
        "is_repeat_visitor": len(visits) > 0,
        "last_visit": _utc(max(dates)) if dates else None,
        "deleted": patient.deleted_at is not None,
        "deleted_at": _utc(patient.deleted_at),
        "created_at": _utc(patient.created_at),
    }


def patient_snapshot(patient: models.Patient) -> dict:
    """Full patient snapshot for sync. Lives only in the outbox and the cloud, never in logs."""
    return {
        "public_id": patient.public_id,
        "version": patient.version,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "phone": patient.phone,
        "date_of_birth": patient.date_of_birth,
        "gender": patient.gender,
        "address": patient.address,
        "allergies": patient.allergies,
        "notes": patient.notes,
        "deleted_at": patient.deleted_at,
        "created_at": patient.created_at,
        "updated_at": patient.updated_at,
    }


def emit_patient(db: Session, patient: models.Patient, operation: str) -> None:
    db.flush()
    db.refresh(patient)
    if operation == "deleted":
        payload = {"public_id": patient.public_id, "version": patient.version, "deleted_at": patient.deleted_at}
    else:
        payload = patient_snapshot(patient)
    emit_event(db, pharmacy_id=patient.pharmacy_id, entity_type="patient", entity_id=patient.public_id,
               operation=operation, entity_version=patient.version, payload=payload)


def _with_history(db: Session):
    return db.query(models.Patient).options(joinedload(models.Patient.prescriptions))


def list_patients(
    db: Session,
    pharmacy_id: int,
    search: str | None = None,
    *,
    page: int | None = None,
    page_size: int = 25,
) -> list[dict] | dict:
    pharmacy_id = signed_in_pharmacy(db, pharmacy_id)
    query = _with_history(db).filter(
        models.Patient.pharmacy_id == pharmacy_id,
        models.Patient.deleted_at.is_(None),
    )
    needle = (search or "").strip()
    if needle:
        like = f"%{needle}%"
        query = query.filter(
            models.Patient.first_name.ilike(like)
            | models.Patient.last_name.ilike(like)
            | models.Patient.phone.ilike(like)
            | (models.Patient.first_name + " " + models.Patient.last_name).ilike(like)
        )
    query = query.order_by(models.Patient.last_name, models.Patient.first_name, models.Patient.id)
    if page is None:
        return [serialize_patient(patient) for patient in query.all()]
    total = query.order_by(None).count()
    start = (page - 1) * page_size
    patients = query.offset(start).limit(page_size).all()
    return as_page([serialize_patient(patient) for patient in patients], total, page, page_size)


def get_patient(db: Session, patient_id: int) -> models.Patient | None:
    """Removed patients are still returned (flagged), so their history stays readable."""
    patient = _with_history(db).filter(models.Patient.id == patient_id).first()
    if patient is None:
        return None
    if not visible(db, patient.pharmacy_id):
        return None  # another pharmacy's patient: behave as if it does not exist
    return patient


def create_patient(db: Session, payload: schemas.PatientCreate) -> models.Patient:
    data = payload.model_dump()
    data["pharmacy_id"] = signed_in_pharmacy(db, data["pharmacy_id"])
    with business_transaction(db):
        patient = models.Patient(**data)
        db.add(patient)
        db.flush()
        emit_patient(db, patient, "created")
        record_audit(db, "patient.created", pharmacy_id=patient.pharmacy_id, entity_type="patient", entity_public_id=patient.public_id)
    return get_patient(db, patient.id)


def update_patient(db: Session, patient_id: int, payload: schemas.PatientUpdate) -> models.Patient | None:
    patient = get_patient(db, patient_id)
    if not patient:
        return None
    if patient.deleted_at is not None:
        raise PatientRemoved("This patient was removed and cannot be edited")
    with business_transaction(db):
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(patient, field, value)
        if not db.is_modified(patient, include_collections=False):
            return patient  # same values saved again: no version bump, no event, no audit
        emit_patient(db, patient, "updated")
        record_audit(db, "patient.updated", pharmacy_id=patient.pharmacy_id, entity_type="patient", entity_public_id=patient.public_id)
    return get_patient(db, patient_id)


def delete_patient(db: Session, patient_id: int) -> bool:
    """Tombstone the patient. Prescriptions and bills are untouched. Repeating is a no-op."""
    patient = get_patient(db, patient_id)
    if not patient:
        return False
    if patient.deleted_at is not None:
        return True
    with business_transaction(db):
        patient.deleted_at = datetime.now(timezone.utc)
        emit_patient(db, patient, "deleted")
        record_audit(db, "patient.deleted", pharmacy_id=patient.pharmacy_id, entity_type="patient", entity_public_id=patient.public_id)
    return True
