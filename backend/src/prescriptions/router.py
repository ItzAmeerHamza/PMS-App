from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


@router.get("/", response_model=list[schemas.PrescriptionOut])
def list_prescriptions(
    pharmacy_id: int = Query(...),
    patient_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    return service.list_prescriptions(db, pharmacy_id, patient_id=patient_id, status=status)


@router.get("/{prescription_id}", response_model=schemas.PrescriptionOut)
def get_prescription(prescription_id: int, db: Session = Depends(get_db)):
    prescription = service.get_prescription(db, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return service.serialize_prescription(prescription)


@router.post("/", response_model=schemas.PrescriptionOut, status_code=201)
def create_prescription(payload: schemas.PrescriptionCreate, db: Session = Depends(get_db)):
    try:
        prescription = service.create_prescription(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return service.serialize_prescription(prescription)


@router.post("/{prescription_id}/dispense", response_model=schemas.PrescriptionOut)
def dispense_prescription(prescription_id: int, db: Session = Depends(get_db)):
    try:
        prescription = service.dispense_prescription(db, prescription_id)
    except ValueError as exc:
        status = 404 if str(exc) == "Prescription not found" else 400
        raise HTTPException(status_code=status, detail=str(exc))
    return service.serialize_prescription(prescription)


@router.post("/{prescription_id}/cancel", response_model=schemas.PrescriptionOut)
def cancel_prescription(prescription_id: int, db: Session = Depends(get_db)):
    try:
        prescription = service.cancel_prescription(db, prescription_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return service.serialize_prescription(prescription)
