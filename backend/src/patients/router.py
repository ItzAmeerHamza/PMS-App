from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/", response_model=list[schemas.PatientOut])
def list_patients(
    pharmacy_id: int = Query(...),
    search: str | None = None,
    db: Session = Depends(get_db),
):
    return service.list_patients(db, pharmacy_id, search=search)


@router.get("/{patient_id}", response_model=schemas.PatientOut)
def get_patient(patient_id: int, db: Session = Depends(get_db)):
    patient = service.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return service.serialize_patient(patient)


@router.post("/", response_model=schemas.PatientOut, status_code=201)
def create_patient(payload: schemas.PatientCreate, db: Session = Depends(get_db)):
    return service.serialize_patient(service.create_patient(db, payload))


@router.put("/{patient_id}", response_model=schemas.PatientOut)
def update_patient(patient_id: int, payload: schemas.PatientUpdate, db: Session = Depends(get_db)):
    patient = service.update_patient(db, patient_id, payload)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return service.serialize_patient(patient)


@router.delete("/{patient_id}", status_code=204)
def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    if not service.delete_patient(db, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
