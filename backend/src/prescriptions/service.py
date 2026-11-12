from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from .. import models
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
) -> list[dict]:
    query = _query(db).filter(models.Prescription.pharmacy_id == pharmacy_id)
    if patient_id:
        query = query.filter(models.Prescription.patient_id == patient_id)
    if status:
        query = query.filter(models.Prescription.status == status)
    return [serialize_prescription(rx) for rx in query.order_by(models.Prescription.prescribed_at.desc()).all()]


def get_prescription(db: Session, prescription_id: int) -> models.Prescription | None:
    return _query(db).filter(models.Prescription.id == prescription_id).first()


def create_prescription(db: Session, payload: schemas.PrescriptionCreate) -> models.Prescription:
    patient = db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first()
    if not patient or patient.pharmacy_id != payload.pharmacy_id:
        raise ValueError("Patient not found")
    if not payload.items:
        raise ValueError("Add at least one medicine from the store")

    prescription = models.Prescription(
        pharmacy_id=payload.pharmacy_id,
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
        if not medicine or medicine.pharmacy_id != payload.pharmacy_id:
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
    db.commit()
    return get_prescription(db, prescription.id)


def cancel_prescription(db: Session, prescription_id: int) -> models.Prescription | None:
    prescription = get_prescription(db, prescription_id)
    if not prescription:
        return None
    if prescription.status == "dispensed":
        raise ValueError("Cannot cancel a dispensed prescription")
    prescription.status = "cancelled"
    db.commit()
    return get_prescription(db, prescription_id)


def dispense_prescription(db: Session, prescription_id: int) -> models.Prescription:
    prescription = get_prescription(db, prescription_id)
    if not prescription:
        raise ValueError("Prescription not found")
    if prescription.status != "recorded":
        raise ValueError("Only recorded prescriptions can be dispensed")

    for item in prescription.items:
        remaining = item.quantity
        batches = (
            db.query(models.StockBatch)
            .filter(models.StockBatch.medicine_id == item.medicine_id, models.StockBatch.quantity > 0)
            .order_by(models.StockBatch.expiry_date.asc())
            .all()
        )
        for batch in batches:
            if remaining <= 0:
                break
            taken = min(remaining, batch.quantity)
            batch.quantity -= taken
            remaining -= taken
        if remaining > 0:
            name = item.medicine.name if item.medicine else str(item.medicine_id)
            raise ValueError(f"Insufficient stock for {name}")

    prescription.status = "dispensed"
    prescription.dispensed_at = datetime.now(timezone.utc)
    db.commit()
    return get_prescription(db, prescription_id)
