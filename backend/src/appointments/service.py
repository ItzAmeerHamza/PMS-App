from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
from . import models, schemas

class AppointmentService:
    @staticmethod
    def get_appointments(db: Session, skip: int = 0, limit: int = 100) -> List[models.Appointment]:
        return db.query(models.Appointment).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_appointment(db: Session, appointment_id: int) -> Optional[models.Appointment]:
        return db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    
    @staticmethod
    def get_appointments_by_doctor(db: Session, doctor_id: int, date: Optional[date] = None) -> List[models.Appointment]:
        query = db.query(models.Appointment).filter(models.Appointment.doctor_id == doctor_id)
        if date:
            query = query.filter(models.Appointment.scheduled_at >= date)
        return query.order_by(models.Appointment.scheduled_at).all()
    
    @staticmethod
    def get_appointments_by_patient(db: Session, patient_id: int) -> List[models.Appointment]:
        return db.query(models.Appointment).filter(
            models.Appointment.patient_id == patient_id
        ).order_by(models.Appointment.scheduled_at).all()
    
    @staticmethod
    def create_appointment(db: Session, appointment: schemas.AppointmentCreate) -> models.Appointment:
        db_appointment = models.Appointment(**appointment.dict())
        db.add(db_appointment)
        db.commit()
        db.refresh(db_appointment)
        return db_appointment
    
    @staticmethod
    def update_appointment(db: Session, appointment_id: int, appointment_update: schemas.AppointmentUpdate) -> Optional[models.Appointment]:
        db_appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
        if db_appointment:
            update_data = appointment_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_appointment, field, value)
            db.commit()
            db.refresh(db_appointment)
        return db_appointment
    
    @staticmethod
    def delete_appointment(db: Session, appointment_id: int) -> bool:
        db_appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
        if db_appointment:
            db.delete(db_appointment)
            db.commit()
            return True
        return False
    
    @staticmethod
    def get_available_slots(db: Session, doctor_id: int, date: date) -> List[datetime]:
        # This is a simplified version - you might want to implement more complex logic
        # to check doctor's schedule, working hours, etc.
        appointments = db.query(models.Appointment).filter(
            models.Appointment.doctor_id == doctor_id,
            models.Appointment.scheduled_at >= date,
            models.Appointment.scheduled_at < date + 1
        ).all()
        
        # Return available slots (simplified logic)
        # In a real implementation, you'd check against doctor's schedule
        return [] 