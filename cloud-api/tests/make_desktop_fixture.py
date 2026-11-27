"""Regenerate tests/fixtures/desktop_events.json from the real desktop outbox.

Runs the desktop backend (backend/) against a temporary SQLite file, performs a
synthetic shop day through its API, and exports the sync_outbox events exactly as
the future worker will send them. Run with the *backend* virtualenv:

    cd backend && .venv/bin/python ../cloud-api/tests/make_desktop_fixture.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.environ["PHARMACARE_DATA_DIR"] = tempfile.mkdtemp(prefix="pharmacare-fixture-")
os.environ.pop("PHARMACARE_DEMO_DATA", None)

from fastapi.testclient import TestClient  # noqa: E402

from src.api.main import app  # noqa: E402
from src.core import outbox  # noqa: E402
from src.core.database import SessionLocal, init_engine  # noqa: E402

init_engine(Path(os.environ["PHARMACARE_DATA_DIR"]) / "pharmacy.db")

with TestClient(app) as client:
    setup = client.post("/api/v1/auth/setup", json={"username": "fixture-manager", "password": "fixture-pass-1",
                                                    "full_name": "Fixture Manager", "pharmacy_name": "Synthetic Fixture Pharmacy"}).json()
    H = {"Authorization": f"Bearer {setup['token']}"}
    pid = setup["pharmacy"]["id"]
    post = lambda path, body=None: client.post("/api/v1" + path, headers=H, json=body).json()

    para = post("/inventory/medicines", {"pharmacy_id": pid, "sku": "FX-PARA", "name": "Fixturamol 500mg", "salt": "Fixturamol",
                                         "manufacturer": "Synthetic Labs", "unit_price": "10.00", "reorder_level": 5,
                                         "initial_batch": {"batch_number": "FX-P1", "expiry_date": "2099-06-30", "quantity": 50}})
    amox = post("/inventory/medicines", {"pharmacy_id": pid, "sku": "FX-AMOX", "name": "Fixturicillin 250mg",
                                         "unit_price": "40.00", "requires_prescription": True,
                                         "initial_batch": {"batch_number": "FX-A1", "expiry_date": "2099-01-31", "quantity": 20}})
    client.put(f"/api/v1/inventory/medicines/{para['id']}", headers=H, json={"rack_location": "FX-RACK-1"})
    post(f"/inventory/batches/{para['batches'][0]['id']}/adjust", {"quantity_delta": -2, "reason": "Damaged (synthetic)"})
    temp = post("/inventory/medicines", {"pharmacy_id": pid, "sku": "FX-TEMP", "name": "Fixture typo product", "unit_price": "1"})
    client.delete(f"/api/v1/inventory/medicines/{temp['id']}", headers=H)

    zara = post("/patients/", {"pharmacy_id": pid, "first_name": "Zara", "last_name": "Fixture", "phone": "0300-0000901",
                               "allergies": "Synthetic allergy"})
    omar = post("/patients/", {"pharmacy_id": pid, "first_name": "Omar", "last_name": "Fixture", "phone": "0300-0000902"})
    client.put(f"/api/v1/patients/{zara['id']}", headers=H, json={"notes": "Synthetic note"})
    rx1 = post("/prescriptions/", {"pharmacy_id": pid, "patient_id": zara["id"], "diagnosis": "Synthetic fever",
                                   "items": [{"medicine_id": para["id"], "quantity": 6, "dosage": "500 mg", "frequency": "1-0-1"},
                                             {"medicine_id": amox["id"], "quantity": 4, "duration_days": 2}]})
    sale = post("/billing/sales", {"pharmacy_id": pid, "prescription_id": rx1["id"],
                                   "items": [{"medicine_id": para["id"], "quantity": 6}, {"medicine_id": amox["id"], "quantity": 4}]})
    post("/billing/sales", {"pharmacy_id": pid, "items": [{"medicine_id": para["id"], "quantity": 3}], "payment_method": "card"})
    rx2 = post("/prescriptions/", {"pharmacy_id": pid, "patient_id": omar["id"], "items": [{"medicine_id": para["id"], "quantity": 2}]})
    post(f"/prescriptions/{rx2['id']}/cancel")
    post(f"/billing/sales/{sale['id']}/void", {"reason": "Returned (synthetic)"})
    client.delete(f"/api/v1/patients/{omar['id']}", headers=H)

    db = SessionLocal()
    try:
        events = [outbox.serialize_event(row) for row in outbox.list_pending(db, limit=1000)]
        shop_id = db.execute(__import__("sqlalchemy").text("SELECT public_id FROM pharmacies")).scalar()
        batches = db.execute(__import__("sqlalchemy").text(
            "SELECT b.public_id, b.quantity FROM stock_batches b ORDER BY b.id")).all()
    finally:
        db.close()

out = {
    "about": "Synthetic events exported from the desktop sync_outbox by make_desktop_fixture.py. Do not edit by hand.",
    "shop_id": shop_id,
    "final_batch_quantities": {public_id: quantity for public_id, quantity in batches},
    "events": events,
}
target = HERE / "fixtures" / "desktop_events.json"
target.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(f"wrote {len(events)} events to {target.relative_to(HERE.parents[1])}")
print("events:", ", ".join(f"{e['sequence']}:{e['event']}" for e in events))
