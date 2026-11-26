from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/billing", tags=["billing"])

NOT_FOUND = {"Prescription not found", "Patient not found"}


@router.get("/sales", response_model=schemas.SaleList)
def list_sales(
    pharmacy_id: int = Query(...),
    start: datetime | None = None,
    end: datetime | None = None,
    search: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    return service.list_sales(db, pharmacy_id, start=start, end=end, search=search, status=status)


@router.get("/sales/{sale_id}", response_model=schemas.SaleOut)
def get_sale(sale_id: int, db: Session = Depends(get_db)):
    sale = service.get_sale(db, sale_id)
    if not sale:
        raise HTTPException(status_code=404, detail="Bill not found")
    return service.serialize_sale(sale)


@router.post("/sales", response_model=schemas.SaleOut, status_code=201)
def create_sale(payload: schemas.SaleCreate, db: Session = Depends(get_db)):
    try:
        sale = service.create_sale(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404 if str(exc) in NOT_FOUND else 400, detail=str(exc))
    return service.serialize_sale(sale)


@router.post("/sales/{sale_id}/void", response_model=schemas.SaleOut)
def void_sale(sale_id: int, payload: schemas.SaleVoid, db: Session = Depends(get_db)):
    try:
        sale = service.void_sale(db, sale_id, payload.reason)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    if not sale:
        raise HTTPException(status_code=404, detail="Bill not found")
    return service.serialize_sale(sale)
