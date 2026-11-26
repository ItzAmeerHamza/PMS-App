from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models
from ..core.database import get_db
from ..billing import service as billing_service
from ..inventory import service as inventory_service
from ..prescriptions import service as prescription_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/")
def get_dashboard(
    pharmacy_id: int = Query(...),
    day_start: datetime | None = Query(None, description="Start of the shop's local day; defaults to UTC midnight"),
    db: Session = Depends(get_db),
):
    if day_start is None:
        day_start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    today_sales = billing_service.sales_between(db, pharmacy_id, day_start, day_start + timedelta(days=1))
    medicines = inventory_service.list_medicines(db, pharmacy_id)
    patients = db.query(models.Patient).filter(models.Patient.pharmacy_id == pharmacy_id).count()
    prescriptions = (
        db.query(models.Prescription).filter(models.Prescription.pharmacy_id == pharmacy_id).count()
    )
    low_stock = [item for item in medicines if item["is_low_stock"]]
    expiring = inventory_service.list_expiring(db, pharmacy_id, days=90)
    recent = prescription_service.list_prescriptions(db, pharmacy_id)[:8]
    expired = [
        item
        for item in inventory_service.list_expiring(db, pharmacy_id, days=0)
        if item["expiry_date"] < date.today()
    ]

    return {
        "medicine_count": len(medicines),
        "patient_count": patients,
        "prescription_count": prescriptions,
        "low_stock_count": len(low_stock),
        "expiring_count": len(expiring),
        "expired_count": len(expired),
        "units_on_hand": sum(item["quantity_on_hand"] for item in medicines),
        "today_sales_total": today_sales["total"],
        "today_sales_count": today_sales["count"],
        "low_stock": low_stock[:6],
        "expiring": expiring[:6],
        "recent_prescriptions": recent,
        "as_of": date.today(),
        "expiry_window_days": 90,
        "expiry_cutoff": date.today() + timedelta(days=90),
    }
