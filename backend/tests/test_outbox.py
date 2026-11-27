"""Phase 06: transactional sync outbox. No network is involved anywhere in these tests."""

import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from src import models
from src.core import outbox
from src.core.database import SessionLocal

from .conftest import auth, start_client

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def ob(demo_client, manager, db_path):
    headers = auth(manager)
    pid = manager["_pharmacy_id"]

    class Ob:
        pharmacy_id = pid
        client = demo_client

        def get(self, path):
            return demo_client.get("/api/v1" + path, headers=headers)

        def post(self, path, body=None):
            return demo_client.post("/api/v1" + path, headers=headers, json=body)

        def put(self, path, body):
            return demo_client.put("/api/v1" + path, headers=headers, json=body)

        def delete(self, path):
            return demo_client.delete("/api/v1" + path, headers=headers)

        def events(self, entity_id=None):
            conn = sqlite3.connect(db_path)
            try:
                query = ("SELECT sequence, entity_type, operation, entity_id, entity_version, payload, status, shop_id, event_id "
                         "FROM sync_outbox")
                rows = conn.execute(query + (" WHERE entity_id = ?" if entity_id else "") + " ORDER BY sequence",
                                    (entity_id,) if entity_id else ()).fetchall()
            finally:
                conn.close()
            return [{"sequence": r[0], "type": r[1], "op": r[2], "entity_id": r[3], "version": r[4],
                     "payload": json.loads(r[5]), "status": r[6], "shop_id": r[7], "event_id": r[8]} for r in rows]

        def count(self):
            return len(self.events())

        def sql(self, query, *args):
            conn = sqlite3.connect(db_path)
            try:
                return conn.execute(query, args).fetchall()
            finally:
                conn.close()

        def medicine(self, sku, qty=None, **extra):
            body = {"pharmacy_id": pid, "sku": sku, "name": f"Synthetic {sku}", "unit_price": "4.00", "manufacturer": "Synthetic Labs", **extra}
            if qty:
                body["initial_batch"] = {"batch_number": f"{sku}-B1", "expiry_date": (date.today() + timedelta(days=300)).isoformat(), "quantity": qty}
            response = self.post("/inventory/medicines", body)
            assert response.status_code == 201, response.text
            return response.json()

        def patient(self, first="Outbox"):
            response = self.post("/patients/", {"pharmacy_id": pid, "first_name": first, "last_name": "Synthetic", "phone": "0300-8880001"})
            assert response.status_code == 201, response.text
            return response.json()

        def prescribe(self, patient_id, medicine_id, qty=1):
            response = self.post("/prescriptions/", {"pharmacy_id": pid, "patient_id": patient_id,
                                                     "items": [{"medicine_id": medicine_id, "quantity": qty, "dosage": "1 tab"}]})
            assert response.status_code == 201, response.text
            return response.json()

    return Ob()


def test_seeded_demo_data_creates_no_events(ob):
    assert ob.count() == 0, "seed rows are pre-existing data, uploaded later by bootstrap"


def test_product_create_writes_the_medicine_and_exactly_one_event(ob):
    med = ob.medicine("OB-A")
    events = ob.events()
    assert len(events) == 1
    event = events[0]
    assert (event["type"], event["op"], event["version"], event["status"]) == ("product", "created", 1, "pending")
    assert event["entity_id"] == med_public_id(ob, med["id"])
    assert event["payload"]["event"] == "product.created" and event["payload"]["sku"] == "OB-A"
    assert event["payload"]["batches"] == []
    assert event["shop_id"] == ob.sql("SELECT public_id FROM pharmacies WHERE id = ?", ob.pharmacy_id)[0][0]
    assert len(event["event_id"]) == 36


def med_public_id(ob, medicine_id):
    return ob.sql("SELECT public_id FROM medicines WHERE id = ?", medicine_id)[0][0]


def test_receipt_is_one_movement_event_not_a_product_update(ob):
    med = ob.medicine("OB-B", qty=12)
    assert [(e["type"], e["op"]) for e in ob.events()] == [("product", "created"), ("stock_movement", "created")]
    assert ob.post(f"/inventory/medicines/{med['id']}/batches",
                   {"batch_number": "OB-B2", "expiry_date": "2099-01-01", "quantity": 3}).status_code == 201
    assert [(e["type"], e["op"]) for e in ob.events()][2:] == [("stock_movement", "created")]


def test_failure_before_commit_leaves_neither_row(ob, monkeypatch):
    import src.patients.service as patient_service

    def boom(*_args, **_kwargs):
        raise RuntimeError("forced failure after the business insert and the outbox insert")

    monkeypatch.setattr(patient_service, "record_audit", boom)
    with pytest.raises(RuntimeError):
        ob.post("/patients/", {"pharmacy_id": ob.pharmacy_id, "first_name": "Rollback", "last_name": "Synthetic", "phone": "0300-8880002"})
    assert ob.sql("SELECT COUNT(*) FROM patients WHERE first_name = 'Rollback'") == [(0,)]
    assert ob.count() == 0


def test_direct_transaction_rollback_discards_the_event(ob):
    from src.core.transaction import business_transaction
    from src.patients.service import emit_patient

    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            with business_transaction(db):
                patient = models.Patient(pharmacy_id=ob.pharmacy_id, first_name="Direct", last_name="Synthetic", phone="0300-1")
                db.add(patient)
                db.flush()
                emit_patient(db, patient, "created")
                assert db.query(models.SyncOutbox).count() == 1  # visible inside the transaction
                raise ValueError("abort")
        assert db.query(models.SyncOutbox).count() == 0
        assert db.query(models.Patient).filter_by(first_name="Direct").count() == 0
    finally:
        db.close()


def test_two_patient_updates_produce_versions_two_and_three_in_order(ob):
    patient = ob.patient()
    assert ob.put(f"/patients/{patient['id']}", {"notes": "first change"}).status_code == 200
    assert ob.put(f"/patients/{patient['id']}", {"notes": "second change"}).status_code == 200
    public_id = ob.sql("SELECT public_id FROM patients WHERE id = ?", patient["id"])[0][0]
    events = ob.events(public_id)
    assert [(e["op"], e["version"]) for e in events] == [("created", 1), ("updated", 2), ("updated", 3)]
    assert [e["sequence"] for e in events] == sorted(e["sequence"] for e in events)
    assert events[-1]["payload"]["notes"] == "second change" and events[-1]["payload"]["version"] == 3


def test_reloading_and_saving_unchanged_values_create_no_event(ob):
    patient = ob.patient()
    med = ob.medicine("OB-C")
    before = ob.count()
    for _ in range(3):  # what reloading the screens does
        ob.get(f"/patients/{patient['id']}")
        ob.get(f"/patients/?pharmacy_id={ob.pharmacy_id}")
        ob.get(f"/inventory/medicines?pharmacy_id={ob.pharmacy_id}")
        ob.get(f"/inventory/medicines/{med['id']}/movements")
        ob.get(f"/dashboard/?pharmacy_id={ob.pharmacy_id}")
    assert ob.put(f"/patients/{patient['id']}", {"first_name": patient["first_name"], "phone": patient["phone"]}).status_code == 200
    assert ob.put(f"/inventory/medicines/{med['id']}", {"name": med["name"], "unit_price": "4.00"}).status_code == 200
    assert ob.count() == before
    assert ob.sql("SELECT version FROM patients WHERE id = ?", patient["id"]) == [(1,)]
    assert ob.sql("SELECT version FROM medicines WHERE id = ?", med["id"]) == [(1,)]


def test_prescription_snapshot_has_items_and_patient_public_id(ob):
    patient = ob.patient()
    a, b = ob.medicine("OB-D"), ob.medicine("OB-E")
    response = ob.post("/prescriptions/", {"pharmacy_id": ob.pharmacy_id, "patient_id": patient["id"], "diagnosis": "Synthetic",
                                           "items": [{"medicine_id": a["id"], "quantity": 2, "dosage": "5 mg"},
                                                     {"medicine_id": b["id"], "quantity": 1, "instructions": "At night"}]})
    rx_public = ob.sql("SELECT public_id FROM prescriptions WHERE id = ?", response.json()["id"])[0][0]
    [event] = ob.events(rx_public)
    payload = event["payload"]
    assert (event["type"], event["op"], event["version"]) == ("prescription", "created", 1)
    assert payload["patient_public_id"] == ob.sql("SELECT public_id FROM patients WHERE id = ?", patient["id"])[0][0]
    assert [(i["medicine_public_id"], i["quantity"], i["dosage"]) for i in payload["items"]] == [
        (med_public_id(ob, a["id"]), 2, "5 mg"), (med_public_id(ob, b["id"]), 1, None)]
    assert all(len(i["public_id"]) == 36 for i in payload["items"])


def test_stock_adjustment_payload(ob):
    med = ob.medicine("OB-F", qty=10)
    batch_id = med["batches"][0]["id"]
    assert ob.post(f"/inventory/batches/{batch_id}/adjust", {"quantity_delta": -3, "reason": "Damaged"}).status_code == 200
    event = ob.events()[-1]
    payload = event["payload"]
    assert (event["type"], event["op"], payload["event"]) == ("stock_movement", "created", "stock.movement_created")
    assert payload["quantity_delta"] == -3 and payload["quantity_after"] == 7 and payload["movement_type"] == "adjustment"
    assert payload["reason"] == "Damaged"
    assert payload["medicine_public_id"] == med_public_id(ob, med["id"])
    assert payload["batch"]["public_id"] == ob.sql("SELECT public_id FROM stock_batches WHERE id = ?", batch_id)[0][0]
    assert event["entity_id"] == ob.sql("SELECT public_id FROM stock_movements ORDER BY id DESC LIMIT 1")[0][0]


def test_new_prescription_leaves_history_and_only_it_gets_a_created_event(ob):
    patient = ob.patient()
    med = ob.medicine("OB-G")
    first = ob.prescribe(patient["id"], med["id"])
    first_public = ob.sql("SELECT public_id FROM prescriptions WHERE id = ?", first["id"])[0][0]
    before = ob.events()
    second = ob.prescribe(patient["id"], med["id"], qty=3)
    new = ob.events()[len(before):]
    second_public = ob.sql("SELECT public_id FROM prescriptions WHERE id = ?", second["id"])[0][0]
    assert [(e["type"], e["op"], e["entity_id"]) for e in new] == [("prescription", "created", second_public)]
    assert ob.events(first_public) == [e for e in before if e["entity_id"] == first_public], "first prescription has no new event"
    assert ob.sql("SELECT COUNT(*) FROM prescriptions WHERE patient_id = ?", patient["id"]) == [(2,)]


def test_sale_void_and_billed_prescription_emit_movements_and_one_update_each(ob):
    patient = ob.patient()
    med = ob.medicine("OB-H", qty=20)
    rx = ob.prescribe(patient["id"], med["id"], qty=4)
    rx_public = ob.sql("SELECT public_id FROM prescriptions WHERE id = ?", rx["id"])[0][0]
    start = ob.count()

    sale = ob.post("/billing/sales", {"pharmacy_id": ob.pharmacy_id, "prescription_id": rx["id"],
                                      "items": [{"medicine_id": med["id"], "quantity": 4}]}).json()
    billed = ob.events()[start:]
    assert [(e["type"], e["op"]) for e in billed] == [("stock_movement", "created"), ("prescription", "updated")]
    assert billed[0]["payload"]["movement_type"] == "sale" and billed[0]["payload"]["source_ref"] == sale["invoice_number"]
    assert billed[1]["payload"]["status"] == "dispensed" and billed[1]["version"] == 2

    mid = ob.count()
    assert ob.post(f"/billing/sales/{sale['id']}/void", {"reason": "test"}).status_code == 200
    voided = ob.events()[mid:]
    assert [(e["type"], e["op"]) for e in voided] == [("stock_movement", "created"), ("prescription", "updated")]
    assert voided[0]["payload"]["movement_type"] == "void" and voided[0]["payload"]["quantity_delta"] == 4
    assert voided[1]["payload"]["status"] == "recorded" and voided[1]["version"] == 3
    assert not [e for e in ob.events() if e["type"] not in {"product", "stock_movement", "patient", "prescription"}], "no invoice events"
    assert [e["version"] for e in ob.events(rx_public)] == [1, 2, 3]


def test_dispense_and_cancel_emit_prescription_updates(ob):
    patient = ob.patient()
    med = ob.medicine("OB-I", qty=5)
    rx = ob.prescribe(patient["id"], med["id"], qty=2)
    start = ob.count()
    assert ob.post(f"/prescriptions/{rx['id']}/dispense").status_code == 200
    assert [(e["type"], e["payload"].get("movement_type") or e["payload"].get("status")) for e in ob.events()[start:]] == [
        ("stock_movement", "dispense"), ("prescription", "dispensed")]
    other = ob.prescribe(patient["id"], med["id"])
    start = ob.count()
    assert ob.post(f"/prescriptions/{other['id']}/cancel").status_code == 200
    [event] = ob.events()[start:]
    assert (event["type"], event["op"], event["payload"]["status"], event["version"]) == ("prescription", "updated", "cancelled", 2)


def test_failed_dispense_writes_no_events(ob):
    patient = ob.patient()
    med = ob.medicine("OB-J", qty=1)
    rx = ob.prescribe(patient["id"], med["id"], qty=5)
    start = ob.count()
    assert ob.post(f"/prescriptions/{rx['id']}/dispense").status_code == 400
    assert ob.count() == start


def test_deletes_are_tombstones_with_the_row_kept(ob):
    patient = ob.patient()
    med = ob.medicine("OB-K")
    assert ob.delete(f"/patients/{patient['id']}").status_code == 204
    assert ob.delete(f"/inventory/medicines/{med['id']}").status_code == 204
    patient_event, product_event = ob.events()[-2:]
    assert (patient_event["type"], patient_event["op"], patient_event["version"]) == ("patient", "deleted", 2)
    assert set(patient_event["payload"]) == {"event", "public_id", "version", "deleted_at"}, "tombstone carries no patient details"
    assert (product_event["type"], product_event["op"], product_event["version"]) == ("product", "deleted", 2)
    assert ob.sql("SELECT deleted_at IS NOT NULL, is_active FROM medicines WHERE id = ?", med["id"]) == [(1, 0)]
    assert med["id"] not in [m["id"] for m in ob.get(f"/inventory/medicines?pharmacy_id={ob.pharmacy_id}").json()]
    assert ob.delete(f"/patients/{patient['id']}").status_code == 204
    assert ob.delete(f"/inventory/medicines/{med['id']}").status_code == 204
    assert ob.events()[-2:] == [patient_event, product_event], "repeating a delete adds nothing"


def test_csv_import_emits_product_and_movement_events(ob):
    csv = (b"sku,name,unit_price,batch_number,expiry_date,quantity\n"
           b"OB-CSV1,Synthetic import 1,3,CSV-B1,2099-01-01,9\nOB-CSV2,Synthetic import 2,4,,,\n")
    files = {"file": ("import.csv", csv, "text/csv")}
    response = ob.client.post(f"/api/v1/inventory/medicines/import?pharmacy_id={ob.pharmacy_id}", files=files,
                              headers={"Authorization": ob_auth_header(ob)})
    assert response.status_code == 200 and response.json()["created"] == 2
    assert [(e["type"], e["op"]) for e in ob.events()] == [("product", "created"), ("stock_movement", "created"), ("product", "created")]


def ob_auth_header(ob):
    token = ob.client.post("/api/v1/auth/login", json={"username": "test-manager", "password": "correct horse 42"}).json()["token"]
    return f"Bearer {token}"


def test_pending_order_is_deterministic_across_sessions_and_restart(ob):
    patient = ob.patient()
    med = ob.medicine("OB-L", qty=6)
    ob.prescribe(patient["id"], med["id"])
    first = SessionLocal()
    try:
        order_a = [e.event_id for e in outbox.list_pending(first)]
    finally:
        first.close()
    second = SessionLocal()
    try:
        order_b = [e.event_id for e in outbox.list_pending(second)]
        sequences = [e.sequence for e in outbox.list_pending(second)]
    finally:
        second.close()
    assert order_a == order_b and sequences == sorted(sequences) and len(set(sequences)) == len(sequences)
    ob.client.__exit__(None, None, None)
    with start_client():
        third = SessionLocal()
        try:
            assert [e.event_id for e in outbox.list_pending(third)] == order_a, "pending rows survive a restart"
            assert {e.entity_type for e in outbox.list_pending(third)} >= {"patient", "prescription", "stock_movement"}
        finally:
            third.close()


def test_worker_read_model_acknowledge_errors_counts_and_retention(ob):
    patient = ob.patient()
    ob.put(f"/patients/{patient['id']}", {"notes": "x"})
    ob.medicine("OB-M", qty=2)
    db = SessionLocal()
    try:
        events = outbox.list_pending(db)
        assert [e.sequence for e in events] == sorted(e.sequence for e in events) and len(events) == 4
        assert outbox.counts(db) == {"pending": 4, "synced": 0, "retryable_error": 0, "failed": 0}
        assert outbox.serialize_event(events[0])["event"] == "patient.created"

        # Only applied / already_processed acknowledge; unknown ids and other results are ignored.
        marked = outbox.acknowledge(db, [
            {"event_id": events[0].event_id, "result": "applied"},
            {"event_id": events[1].event_id, "result": "already_processed"},
            {"event_id": events[2].event_id, "result": "retryable_error"},
            {"event_id": "not-a-real-event", "result": "applied"},
        ])
        assert marked == 2
        assert outbox.counts(db) == {"pending": 2, "synced": 2, "retryable_error": 0, "failed": 0}
        assert [e.event_id for e in outbox.list_pending(db)] == [events[2].event_id, events[3].event_id]

        now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        row = outbox.record_error(db, events[2].event_id, "HTTP_503", now=now)
        assert (row.status, row.retry_count, row.last_error) == ("retryable_error", 1, "HTTP_503")
        assert row.next_attempt_at == datetime(2030, 1, 1, 0, 0, 30)
        assert [e.event_id for e in outbox.list_pending(db, now=now)] == [events[3].event_id], "not due yet"
        assert events[2].event_id in [e.event_id for e in outbox.list_pending(db, now=now + timedelta(seconds=31))]
        row = outbox.record_error(db, events[2].event_id, "HTTP_503", now=now)
        assert row.retry_count == 2 and row.next_attempt_at == datetime(2030, 1, 1, 0, 1, 0), "backoff doubles"
        row = outbox.record_error(db, events[3].event_id, "INVALID_EVENT", retryable=False, now=now)
        assert row.status == "failed" and row.next_attempt_at is None
        assert outbox.counts(db) == {"pending": 0, "synced": 2, "retryable_error": 1, "failed": 1}
        assert outbox.record_error(db, events[0].event_id, "late error").status == "synced", "synced rows stay synced"
        assert outbox.retry_delay(20) == 3600

        # Retention: acknowledged rows stay until purged; unsynced rows are never purged.
        assert outbox.purge_synced(db, older_than_days=30) == 0
        assert outbox.purge_synced(db, older_than_days=30, now=datetime.now(timezone.utc) + timedelta(days=31)) == 2
        assert outbox.counts(db) == {"pending": 0, "synced": 0, "retryable_error": 1, "failed": 1}
        with pytest.raises(ValueError):
            outbox.purge_synced(db, older_than_days=0)
    finally:
        db.close()


def test_payloads_are_immutable_after_insert(ob):
    patient = ob.patient()
    public_id = ob.sql("SELECT public_id FROM patients WHERE id = ?", patient["id"])[0][0]
    [created] = ob.events(public_id)
    ob.put(f"/patients/{patient['id']}", {"notes": "changed later"})
    assert ob.events(public_id)[0] == created, "the created event still shows the original snapshot"


def test_no_hardcoded_cloud_host_and_http_client_stays_in_the_sync_package():
    """Phase 06 forbade any HTTP client. Phase 07 Part B adds one, only in src/sync/transport.py."""
    host = re.compile(r"railway\.app|up\.railway", re.I)
    client = re.compile(r"import httpx|import requests|urllib\.request|aiohttp", re.I)
    files = list((REPO / "backend" / "src").rglob("*.py"))
    assert [str(p.relative_to(REPO)) for p in files if host.search(p.read_text())] == []
    clients = [str(p.relative_to(REPO)) for p in files if client.search(p.read_text())]
    assert clients == ["backend/src/sync/transport.py"]


def test_nested_calls_cannot_emit_the_same_event_twice(ob):
    from src.core.transaction import business_transaction
    from src.patients.service import emit_patient

    db = SessionLocal()
    try:
        with business_transaction(db):
            patient = models.Patient(pharmacy_id=ob.pharmacy_id, first_name="Nested", last_name="Synthetic", phone="0300-2")
            db.add(patient)
            db.flush()
            emit_patient(db, patient, "created")
            with business_transaction(db):  # e.g. a second service in the same action
                emit_patient(db, patient, "created")
        public_id = patient.public_id
    finally:
        db.close()
    assert [(e["op"], e["version"]) for e in ob.events(public_id)] == [("created", 1)]
