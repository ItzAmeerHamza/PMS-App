"""Existing behavior still works after phase 02, and audit rows carry no patient details."""

import logging
import sqlite3

from src.api.main import _StripQueryString

from .conftest import auth

PATIENT = {"first_name": "Zeta", "last_name": "Synthetic", "phone": "0300-9999999", "allergies": "Synthetic allergy"}
DIAGNOSIS = "Synthetic diagnosis text"


def test_core_screens_load_and_billing_round_trip(demo_client, manager, db_path):
    headers = auth(manager)
    pid = manager["_pharmacy_id"]
    get = lambda path: demo_client.get(path, headers=headers)

    assert get(f"/api/v1/dashboard/?pharmacy_id={pid}").status_code == 200
    medicines = get(f"/api/v1/inventory/medicines?pharmacy_id={pid}").json()
    assert medicines and all("sellable_quantity" in m for m in medicines)
    assert get(f"/api/v1/patients/?pharmacy_id={pid}").status_code == 200
    assert get(f"/api/v1/prescriptions/?pharmacy_id={pid}").status_code == 200

    patient = demo_client.post("/api/v1/patients/", headers=headers, json={"pharmacy_id": pid, **PATIENT})
    assert patient.status_code == 201, patient.text
    patient_id = patient.json()["id"]
    medicine = next(m for m in medicines if m["sellable_quantity"] >= 2)

    rx = demo_client.post(
        "/api/v1/prescriptions/",
        headers=headers,
        json={
            "pharmacy_id": pid,
            "patient_id": patient_id,
            "diagnosis": DIAGNOSIS,
            "items": [{"medicine_id": medicine["id"], "quantity": 2, "instructions": "Synthetic instruction"}],
        },
    )
    assert rx.status_code == 201, rx.text

    sale = demo_client.post(
        "/api/v1/billing/sales",
        headers=headers,
        json={"pharmacy_id": pid, "prescription_id": rx.json()["id"], "items": [{"medicine_id": medicine["id"], "quantity": 2}]},
    )
    assert sale.status_code == 201, sale.text
    sale = sale.json()
    assert sale["staff_name"] == "Test Manager"
    assert get(f"/api/v1/prescriptions/{rx.json()['id']}").json()["status"] == "dispensed"

    void = demo_client.post(f"/api/v1/billing/sales/{sale['id']}/void", headers=headers, json={"reason": "test"})
    assert void.status_code == 200 and void.json()["status"] == "void"
    after = {m["id"]: m["sellable_quantity"] for m in get(f"/api/v1/inventory/medicines?pharmacy_id={pid}").json()}
    assert after[medicine["id"]] == medicine["sellable_quantity"]

    updated = demo_client.put(f"/api/v1/patients/{patient_id}", headers=headers, json={"notes": "Synthetic note"})
    assert updated.status_code == 200

    # Removal is a tombstone (phase 04): history stays readable.
    assert demo_client.delete(f"/api/v1/patients/{patient_id}", headers=headers).status_code == 204
    assert get(f"/api/v1/prescriptions/{rx.json()['id']}").status_code == 200

    conn = sqlite3.connect(db_path)
    try:
        # created (1) -> updated (2) -> removed (3); the row is still there.
        assert conn.execute("SELECT version, deleted_at IS NOT NULL FROM patients WHERE id = ?", (patient_id,)).fetchone() == (3, 1)
        actions = {row[0] for row in conn.execute("SELECT action FROM audit_logs")}
        rows = conn.execute("SELECT * FROM audit_logs").fetchall()
    finally:
        conn.close()

    assert {"auth.setup", "auth.login", "patient.created", "patient.updated", "patient.deleted", "prescription.created", "prescription.dispensed", "sale.created", "sale.voided"} <= actions
    dump = " ".join(str(value) for row in rows for value in row)
    for secret in [*PATIENT.values(), DIAGNOSIS, "Synthetic instruction", "Synthetic note"]:
        assert secret not in dump, f"audit log contains patient detail: {secret!r}"


def test_inventory_writes_are_audited(demo_client, manager, db_path):
    headers = auth(manager)
    pid = manager["_pharmacy_id"]
    created = demo_client.post(
        "/api/v1/inventory/medicines",
        headers=headers,
        json={"pharmacy_id": pid, "sku": "SYN-1", "name": "Synthetic 5mg", "unit_price": "5.00", "reorder_level": 1,
              "initial_batch": {"batch_number": "S-1", "expiry_date": "2099-01-01", "quantity": 10}},
    )
    assert created.status_code == 201, created.text
    medicine = created.json()
    batch_id = medicine["batches"][0]["id"]
    assert demo_client.post(f"/api/v1/inventory/batches/{batch_id}/adjust", headers=headers, json={"quantity_delta": -3, "reason": "Damaged"}).json()["quantity"] == 7
    assert demo_client.put(f"/api/v1/inventory/medicines/{medicine['id']}", headers=headers, json={"rack_location": "Z-9"}).status_code == 200
    # Stock history makes it undeletable (phase 03); a product with no stock can still be deleted.
    assert demo_client.delete(f"/api/v1/inventory/medicines/{medicine['id']}", headers=headers).status_code == 409
    empty = demo_client.post("/api/v1/inventory/medicines", headers=headers,
                             json={"pharmacy_id": pid, "sku": "SYN-EMPTY", "name": "Synthetic empty", "unit_price": "1"}).json()
    assert demo_client.delete(f"/api/v1/inventory/medicines/{empty['id']}", headers=headers).status_code == 204

    conn = sqlite3.connect(db_path)
    try:
        actions = [row[0] for row in conn.execute("SELECT action FROM audit_logs WHERE entity_type IN ('medicine', 'stock_batch') ORDER BY id")]
    finally:
        conn.close()
    assert actions == ["medicine.created", "batch.created", "batch.adjusted", "medicine.updated", "medicine.created", "medicine.deleted"]


def test_access_log_drops_query_strings():
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ("127.0.0.1:1", "GET", "/api/v1/patients/?search=Zeta%20Synthetic", "1.1", 200), None)
    _StripQueryString().filter(record)
    assert record.getMessage() == '127.0.0.1:1 - "GET /api/v1/patients/ HTTP/1.1" 200'
