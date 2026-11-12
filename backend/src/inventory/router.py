from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/medicines", response_model=list[schemas.MedicineOut])
def list_medicines(
    pharmacy_id: int = Query(...),
    search: str | None = None,
    low_stock: bool = False,
    db: Session = Depends(get_db),
):
    return service.list_medicines(db, pharmacy_id, search=search, low_stock=low_stock)


@router.post("/medicines/import", response_model=schemas.MedicineImportResult)
async def import_medicines(
    pharmacy_id: int = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=400, detail="The CSV file is too large")
    try:
        return service.import_medicines_csv(db, pharmacy_id, raw)
    except ValueError as exc:
        db.rollback()
        status = 404 if str(exc) == "Pharmacy not found" else 400
        raise HTTPException(status_code=status, detail=str(exc))


@router.get("/medicines/{medicine_id}", response_model=schemas.MedicineOut)
def get_medicine(medicine_id: int, db: Session = Depends(get_db)):
    medicine = service.get_medicine(db, medicine_id)
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return service.serialize_medicine(medicine)


@router.post("/medicines", response_model=schemas.MedicineOut, status_code=201)
def create_medicine(payload: schemas.MedicineCreate, db: Session = Depends(get_db)):
    try:
        medicine = service.create_medicine(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="SKU already exists for this pharmacy")
    return service.serialize_medicine(medicine)


@router.put("/medicines/{medicine_id}", response_model=schemas.MedicineOut)
def update_medicine(medicine_id: int, payload: schemas.MedicineUpdate, db: Session = Depends(get_db)):
    try:
        medicine = service.update_medicine(db, medicine_id, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="SKU already exists for this pharmacy")
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return service.serialize_medicine(medicine)


@router.delete("/medicines/{medicine_id}", status_code=204)
def delete_medicine(medicine_id: int, db: Session = Depends(get_db)):
    try:
        deleted = service.delete_medicine(db, medicine_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="Medicine not found")


@router.post("/medicines/{medicine_id}/batches", response_model=schemas.StockBatchOut, status_code=201)
def add_batch(medicine_id: int, payload: schemas.StockBatchCreate, db: Session = Depends(get_db)):
    batch = service.add_batch(db, medicine_id, payload)
    if not batch:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return batch


@router.post("/batches/{batch_id}/adjust", response_model=schemas.StockBatchOut)
def adjust_batch(batch_id: int, payload: schemas.StockAdjust, db: Session = Depends(get_db)):
    try:
        batch = service.adjust_batch(db, batch_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.get("/expiring")
def list_expiring(
    pharmacy_id: int = Query(...),
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
):
    return service.list_expiring(db, pharmacy_id, days=days)
