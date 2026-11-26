from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.scope import WrongPharmacy
from . import schemas, service

router = APIRouter(prefix="/patients", tags=["patients"])


def _http_error(exc: ValueError) -> HTTPException:
    if isinstance(exc, WrongPharmacy):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@router.get("/", response_model=list[schemas.PatientOut])
def list_patients(
    pharmacy_id: int = Query(...),
    search: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        return service.list_patients(db, pharmacy_id, search=search)
    except (service.PatientError, WrongPharmacy) as exc:
        raise _http_error(exc)


@router.get("/{patient_id}", response_model=schemas.PatientOut)
def get_patient(patient_id: int, db: Session = Depends(get_db)):
    patient = service.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return service.serialize_patient(patient)


@router.post("/", response_model=schemas.PatientOut, status_code=201)
def create_patient(payload: schemas.PatientCreate, db: Session = Depends(get_db)):
    try:
        return service.serialize_patient(service.create_patient(db, payload))
    except (service.PatientError, WrongPharmacy) as exc:
        raise _http_error(exc)


@router.put("/{patient_id}", response_model=schemas.PatientOut)
def update_patient(patient_id: int, payload: schemas.PatientUpdate, db: Session = Depends(get_db)):
    try:
        patient = service.update_patient(db, patient_id, payload)
    except (service.PatientError, WrongPharmacy) as exc:
        raise _http_error(exc)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return service.serialize_patient(patient)


@router.delete("/{patient_id}", status_code=204)
def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    """Removes the patient from lists by setting a tombstone. History is kept."""
    if not service.delete_patient(db, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
