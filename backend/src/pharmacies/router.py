from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/pharmacies", tags=["pharmacies"])


@router.get("/", response_model=list[schemas.PharmacyOut])
def list_pharmacies(db: Session = Depends(get_db)):
    return service.list_pharmacies(db)


@router.get("/{pharmacy_id}", response_model=schemas.PharmacyOut)
def get_pharmacy(pharmacy_id: int, db: Session = Depends(get_db)):
    pharmacy = service.get_pharmacy(db, pharmacy_id)
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    return pharmacy


@router.post("/", response_model=schemas.PharmacyOut, status_code=201)
def create_pharmacy(payload: schemas.PharmacyCreate, db: Session = Depends(get_db)):
    return service.create_pharmacy(db, payload)


@router.put("/{pharmacy_id}", response_model=schemas.PharmacyOut)
def update_pharmacy(pharmacy_id: int, payload: schemas.PharmacyUpdate, db: Session = Depends(get_db)):
    pharmacy = service.update_pharmacy(db, pharmacy_id, payload)
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    return pharmacy
