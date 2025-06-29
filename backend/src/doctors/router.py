from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..core.database import get_db
from . import models, schemas, service

router = APIRouter(prefix="/doctors", tags=["doctors"])

@router.get("/", response_model=List[schemas.Doctor])
def get_doctors(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all doctors with pagination"""
    doctors = service.DoctorService.get_doctors(db, skip=skip, limit=limit)
    return doctors

@router.get("/{doctor_id}", response_model=schemas.Doctor)
def get_doctor(doctor_id: int, db: Session = Depends(get_db)):
    """Get a specific doctor by ID"""
    doctor = service.DoctorService.get_doctor(db, doctor_id=doctor_id)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor

@router.post("/", response_model=schemas.Doctor, status_code=status.HTTP_201_CREATED)
def create_doctor(doctor: schemas.DoctorCreate, db: Session = Depends(get_db)):
    """Create a new doctor"""
    return service.DoctorService.create_doctor(db=db, doctor=doctor)

@router.put("/{doctor_id}", response_model=schemas.Doctor)
def update_doctor(doctor_id: int, doctor_update: schemas.DoctorUpdate, db: Session = Depends(get_db)):
    """Update a doctor"""
    doctor = service.DoctorService.update_doctor(db=db, doctor_id=doctor_id, doctor_update=doctor_update)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor

@router.delete("/{doctor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doctor(doctor_id: int, db: Session = Depends(get_db)):
    """Delete a doctor"""
    success = service.DoctorService.delete_doctor(db=db, doctor_id=doctor_id)
    if not success:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return None 