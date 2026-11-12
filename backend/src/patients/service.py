from sqlalchemy.orm import Session, joinedload

from .. import models
from . import schemas


def serialize_patient(patient: models.Patient) -> dict:
    visits = [rx.prescribed_at for rx in patient.prescriptions if rx.prescribed_at]
    return {
        "id": patient.id,
        "pharmacy_id": patient.pharmacy_id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "phone": patient.phone,
        "date_of_birth": patient.date_of_birth,
        "gender": patient.gender,
        "address": patient.address,
        "allergies": patient.allergies,
        "notes": patient.notes,
        "prescription_count": len(patient.prescriptions),
        "last_visit": max(visits) if visits else None,
        "created_at": patient.created_at,
    }


def _with_history(db: Session):
    return db.query(models.Patient).options(joinedload(models.Patient.prescriptions))


def list_patients(db: Session, pharmacy_id: int, search: str | None = None) -> list[dict]:
    query = _with_history(db).filter(models.Patient.pharmacy_id == pharmacy_id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            models.Patient.first_name.ilike(like)
            | models.Patient.last_name.ilike(like)
            | models.Patient.phone.ilike(like)
        )
    return [serialize_patient(patient) for patient in query.order_by(models.Patient.last_name).all()]


def get_patient(db: Session, patient_id: int) -> models.Patient | None:
    return _with_history(db).filter(models.Patient.id == patient_id).first()


def create_patient(db: Session, payload: schemas.PatientCreate) -> models.Patient:
    patient = models.Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    return get_patient(db, patient.id)


def update_patient(db: Session, patient_id: int, payload: schemas.PatientUpdate) -> models.Patient | None:
    patient = get_patient(db, patient_id)
    if not patient:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    db.commit()
    return get_patient(db, patient_id)


def delete_patient(db: Session, patient_id: int) -> bool:
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        return False
    db.delete(patient)
    db.commit()
    return True
