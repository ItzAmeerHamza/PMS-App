from sqlalchemy.orm import Session

from .. import models
from . import schemas


def list_pharmacies(db: Session) -> list[models.Pharmacy]:
    return db.query(models.Pharmacy).order_by(models.Pharmacy.id).all()


def get_pharmacy(db: Session, pharmacy_id: int) -> models.Pharmacy | None:
    return db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()


def create_pharmacy(db: Session, payload: schemas.PharmacyCreate) -> models.Pharmacy:
    pharmacy = models.Pharmacy(**payload.model_dump())
    db.add(pharmacy)
    db.commit()
    db.refresh(pharmacy)
    return pharmacy


def update_pharmacy(db: Session, pharmacy_id: int, payload: schemas.PharmacyUpdate) -> models.Pharmacy | None:
    pharmacy = get_pharmacy(db, pharmacy_id)
    if not pharmacy:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(pharmacy, field, value)
    db.commit()
    db.refresh(pharmacy)
    return pharmacy
