from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from ..core.database import get_db
from . import models, schemas, service

router = APIRouter(prefix="/patients", tags=["patients"])

@router.get("/", response_model=List[schemas.Patient])
def get_patients(
    skip: int = 0, 
    limit: int = 100, 
    search: str = Query(None, description="Search by name or email"),
    db: Session = Depends(get_db)
):
    """Get all patients with pagination and optional search"""
    if search:
        return service.PatientService.search_patients(db, search)
    return service.PatientService.get_patients(db, skip=skip, limit=limit)

@router.get("/{patient_id}", response_model=schemas.Patient)
def get_patient(patient_id: int, db: Session = Depends(get_db)):
    """Get a specific patient by ID"""
    patient = service.PatientService.get_patient(db, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

@router.post("/", response_model=schemas.Patient, status_code=status.HTTP_201_CREATED)
def create_patient(patient: schemas.PatientCreate, db: Session = Depends(get_db)):
    """Create a new patient"""
    # Check if email already exists
    existing_patient = service.PatientService.get_patient_by_email(db, patient.email)
    if existing_patient:
        raise HTTPException(status_code=400, detail="Email already registered")
    return service.PatientService.create_patient(db=db, patient=patient)

@router.put("/{patient_id}", response_model=schemas.Patient)
def update_patient(patient_id: int, patient_update: schemas.PatientUpdate, db: Session = Depends(get_db)):
    """Update a patient"""
    patient = service.PatientService.update_patient(db=db, patient_id=patient_id, patient_update=patient_update)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    """Delete a patient"""
    success = service.PatientService.delete_patient(db=db, patient_id=patient_id)
    if not success:
        raise HTTPException(status_code=404, detail="Patient not found")
    return None 