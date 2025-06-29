from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import date
from ..core.database import get_db
from . import models, schemas, service

router = APIRouter(prefix="/appointments", tags=["appointments"])

@router.get("/", response_model=List[schemas.Appointment])
def get_appointments(
    skip: int = 0, 
    limit: int = 100,
    doctor_id: int = Query(None, description="Filter by doctor ID"),
    patient_id: int = Query(None, description="Filter by patient ID"),
    appointment_date: date = Query(None, description="Filter by appointment date"),
    db: Session = Depends(get_db)
):
    """Get all appointments with optional filtering"""
    if doctor_id:
        return service.AppointmentService.get_appointments_by_doctor(db, doctor_id, appointment_date)
    elif patient_id:
        return service.AppointmentService.get_appointments_by_patient(db, patient_id)
    else:
        return service.AppointmentService.get_appointments(db, skip=skip, limit=limit)

@router.get("/{appointment_id}", response_model=schemas.Appointment)
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    """Get a specific appointment by ID"""
    appointment = service.AppointmentService.get_appointment(db, appointment_id=appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appointment

@router.post("/", response_model=schemas.Appointment, status_code=status.HTTP_201_CREATED)
def create_appointment(appointment: schemas.AppointmentCreate, db: Session = Depends(get_db)):
    """Create a new appointment"""
    return service.AppointmentService.create_appointment(db=db, appointment=appointment)

@router.put("/{appointment_id}", response_model=schemas.Appointment)
def update_appointment(appointment_id: int, appointment_update: schemas.AppointmentUpdate, db: Session = Depends(get_db)):
    """Update an appointment"""
    appointment = service.AppointmentService.update_appointment(db=db, appointment_id=appointment_id, appointment_update=appointment_update)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appointment

@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    """Delete an appointment"""
    success = service.AppointmentService.delete_appointment(db=db, appointment_id=appointment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return None

@router.get("/doctors/{doctor_id}/available-slots")
def get_available_slots(doctor_id: int, date: date, db: Session = Depends(get_db)):
    """Get available appointment slots for a doctor on a specific date"""
    slots = service.AppointmentService.get_available_slots(db, doctor_id, date)
    return {"available_slots": slots} 