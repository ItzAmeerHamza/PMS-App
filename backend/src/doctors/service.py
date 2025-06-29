from sqlalchemy.orm import Session
from typing import List, Optional
from . import models, schemas
from ..core.database import get_db

class DoctorService:
    @staticmethod
    def get_doctors(db: Session, skip: int = 0, limit: int = 100) -> List[models.Doctor]:
        return db.query(models.Doctor).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_doctor(db: Session, doctor_id: int) -> Optional[models.Doctor]:
        return db.query(models.Doctor).filter(models.Doctor.id == doctor_id).first()
    
    @staticmethod
    def get_doctor_by_user_id(db: Session, user_id: int) -> Optional[models.Doctor]:
        return db.query(models.Doctor).filter(models.Doctor.user_id == user_id).first()
    
    @staticmethod
    def create_doctor(db: Session, doctor: schemas.DoctorCreate) -> models.Doctor:
        db_doctor = models.Doctor(**doctor.dict())
        db.add(db_doctor)
        db.commit()
        db.refresh(db_doctor)
        return db_doctor
    
    @staticmethod
    def update_doctor(db: Session, doctor_id: int, doctor_update: schemas.DoctorUpdate) -> Optional[models.Doctor]:
        db_doctor = db.query(models.Doctor).filter(models.Doctor.id == doctor_id).first()
        if db_doctor:
            update_data = doctor_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_doctor, field, value)
            db.commit()
            db.refresh(db_doctor)
        return db_doctor
    
    @staticmethod
    def delete_doctor(db: Session, doctor_id: int) -> bool:
        db_doctor = db.query(models.Doctor).filter(models.Doctor.id == doctor_id).first()
        if db_doctor:
            db.delete(db_doctor)
            db.commit()
            return True
        return False 