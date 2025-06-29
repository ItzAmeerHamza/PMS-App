from sqlalchemy.orm import Session
from typing import List, Optional
from . import models, schemas
from ..core.models import User

class PatientService:
    @staticmethod
    def get_patients(db: Session, skip: int = 0, limit: int = 100) -> List[models.Patient]:
        return db.query(models.Patient).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_patient(db: Session, patient_id: int) -> Optional[models.Patient]:
        return db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    
    @staticmethod
    def get_patient_by_user_id(db: Session, user_id: int) -> Optional[models.Patient]:
        return db.query(models.Patient).filter(models.Patient.user_id == user_id).first()
    
    @staticmethod
    def get_patient_with_user(db: Session, patient_id: int) -> Optional[models.Patient]:
        """Get patient with user information"""
        return db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    
    @staticmethod
    def create_patient(db: Session, patient: schemas.PatientCreate) -> models.Patient:
        db_patient = models.Patient(**patient.dict())
        db.add(db_patient)
        db.commit()
        db.refresh(db_patient)
        return db_patient
    
    @staticmethod
    def update_patient(db: Session, patient_id: int, patient_update: schemas.PatientUpdate) -> Optional[models.Patient]:
        db_patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
        if db_patient:
            update_data = patient_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_patient, field, value)
            db.commit()
            db.refresh(db_patient)
        return db_patient
    
    @staticmethod
    def delete_patient(db: Session, patient_id: int) -> bool:
        db_patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
        if db_patient:
            db.delete(db_patient)
            db.commit()
            return True
        return False
    
    @staticmethod
    def search_patients(db: Session, search_term: str) -> List[models.Patient]:
        """Search patients by user information"""
        return db.query(models.Patient).join(User).filter(
            User.first_name.ilike(f"%{search_term}%") |
            User.last_name.ilike(f"%{search_term}%") |
            User.email.ilike(f"%{search_term}%")
        ).all() 