from sqlalchemy.orm import Session

from .. import models
from ..core.audit import record_audit
from ..core.transaction import business_transaction
from . import schemas


def list_pharmacies(db: Session) -> list[models.Pharmacy]:
    return db.query(models.Pharmacy).order_by(models.Pharmacy.id).all()


def get_pharmacy(db: Session, pharmacy_id: int) -> models.Pharmacy | None:
    return db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()


def create_pharmacy(db: Session, payload: schemas.PharmacyCreate) -> models.Pharmacy:
    with business_transaction(db):
        pharmacy = models.Pharmacy(**payload.model_dump())
        db.add(pharmacy)
        db.flush()
        record_audit(db, "pharmacy.created", pharmacy_id=pharmacy.id, entity_type="pharmacy", entity_public_id=pharmacy.public_id)
    db.refresh(pharmacy)
    return pharmacy


def update_pharmacy(db: Session, pharmacy_id: int, payload: schemas.PharmacyUpdate) -> models.Pharmacy | None:
    pharmacy = get_pharmacy(db, pharmacy_id)
    if not pharmacy:
        return None
    with business_transaction(db):
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(pharmacy, field, value)
        record_audit(db, "pharmacy.updated", pharmacy_id=pharmacy.id, entity_type="pharmacy", entity_public_id=pharmacy.public_id)
    db.refresh(pharmacy)
    return pharmacy
