"""Sync worker, activation, and bootstrap. The cloud is a fake unless a test says otherwise.

Synthetic names only. The device token and patient text must not appear in status,
diagnostics, or the log.
"""

import json
import random
import socket
import stat
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func

from src import models
from src.core.database import SessionLocal
from src.core.outbox import DISABLED, record_error
from src.core.transaction import business_transaction
from src.sync.secrets import credential_path
from src.sync.transport import TransportError
from src.sync.worker import SyncWorker, delay_seconds
from tests.conftest import auth, set_up_manager, start_client

TOKEN = "pcd_" + str(uuid.uuid4()) + "." + ("ab" * 16)
T0 = datetime(2030, 1, 1, tzinfo=timezone.utc)


class Cloud:
    """Enough of the cloud batch rules to prove the worker's side of the protocol."""

    def __init__(self):
        self.applied = []
        self.seen = set()
        self.batches = []
        self.invalid = set()
        self.fail_with = None
        self.patients = set()
        self.conflict_if_patient_missing = False
        self.calls = 0

    def push(self, _url, _token, body, _timeout):
        self.calls += 1
        self.batches.append([event["event_id"] for event in body["events"]])
        if self.fail_with is not None:
            error = self.fail_with
            self.fail_with = None
            raise error
        ordered = sorted(body["events"], key=lambda event: event["sequence"])
        by_id = {}
        blocked = False
        for event in ordered:
            event_id = event["event_id"]
            if event_id in self.seen:
                by_id[event_id] = {"event_id": event_id, "result": "already_processed"}
                continue
            if blocked:
                by_id[event_id] = {"event_id": event_id, "result": "retryable_error", "code": "blocked_by_earlier_event"}
                continue
            if event_id in self.invalid:
                by_id[event_id] = {"event_id": event_id, "result": "invalid_event", "code": "schema:event"}
                continue
            if self.conflict_if_patient_missing and event["entity_type"] == "prescription":
                patient_id = event["payload"].get("patient_public_id")
                if patient_id not in self.patients:
                    by_id[event_id] = {"event_id": event_id, "result": "ordering_conflict", "code": "missing_patient"}
                    blocked = True
                    continue
            if event["entity_type"] == "patient" and event["operation"] == "created":
                self.patients.add(event["entity_id"])
            self.seen.add(event_id)
            self.applied.append(event)
            by_id[event_id] = {"event_id": event_id, "result": "applied"}
        return {"results": [by_id[event["event_id"]] for event in body["events"]]}


class DropFirstResponse:
    def __init__(self, inner):
        self.inner = inner
        self.dropped = False

    def push(self, url, token, body, timeout):
        result = self.inner.push(url, token, body, timeout)
        if not self.dropped:
            self.dropped = True
            raise TransportError("timeout")
        return result


def _worker(cloud, **kwargs):
    return SyncWorker(cloud, batch_size=kwargs.pop("batch_size", 100), bootstrap_chunk=kwargs.pop("bootstrap_chunk", 500),
                      rng=random.Random(1), **kwargs)


def _headers(client):
    return auth(set_up_manager(client, pharmacy_name="Synthetic Shop"))


def _activate(client, headers, token=TOKEN, url="http://127.0.0.1:9"):
    response = client.post("/api/v1/sync/activate", headers=headers, json={"device_token": token, "cloud_api_url": url})
    assert response.status_code == 200, response.text
    return response.json()


def _drain(worker, limit=40, now=None):
    last = None
    for _ in range(limit):
        last = worker.run_once(now=now, force=True)
        if last.get("pending", 0) == 0 and last.get("bootstrap") == "complete":
            return last
    return last


def _counts():
    db = SessionLocal()
    try:
        rows = db.query(models.SyncOutbox.status, models.SyncOutbox.origin).all()
    finally:
        db.close()
    return rows


def _insert_live_events(n, shop_id):
    db = SessionLocal()
    try:
        start = db.query(models.SyncOutbox.sequence).order_by(models.SyncOutbox.sequence.desc()).first()
        sequence = (start[0] if start else 0) + 1
        now = datetime(2030, 1, 1)
        for offset in range(n):
            event_id = str(uuid.uuid4())
            db.add(models.SyncOutbox(
                sequence=sequence + offset,
                event_id=event_id,
                shop_id=shop_id,
                entity_type="product",
                entity_id=str(uuid.uuid4()),
                operation="created",
                entity_version=1,
                schema_version=1,
                payload=json.dumps({"event": "product.created", "public_id": event_id, "version": 1, "sku": "X", "name": "X"}),
                created_at=now,
                status="pending",
                retry_count=0,
                origin="live",
            ))
        db.commit()
    finally:
        db.close()


def test_delay_honors_retry_after_and_caps_it():
    rng = random.Random(0)
    assert delay_seconds(1, 120, rng) == 120
    assert delay_seconds(1, 99999, rng) == 3600
    assert 15 <= delay_seconds(1, None, rng) <= 30


def test_shop_works_before_activation_and_with_the_worker_running(data_dir, monkeypatch):
    monkeypatch.setenv("PHARMACARE_SYNC_AUTOSTART", "1")

    def blocked(*_args, **_kwargs):
        raise OSError("network disabled")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    with start_client() as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/sync/status").status_code == 401
        headers = _headers(client)
        status = client.get("/api/v1/sync/status", headers=headers).json()
        assert status["activated"] is False and status["indicator"] == "not_activated"
        assert status["shop_id"] and "pcd_" not in json.dumps(status)
        created = client.post("/api/v1/patients/", headers=headers, json={
            "pharmacy_id": 1, "first_name": "Offline", "last_name": "Synthetic", "phone": "0300-7000001",
        })
        assert created.status_code == 201


def test_activation_stores_the_token_outside_the_database(client):
    headers = _headers(client)
    assert client.post("/api/v1/sync/activate", headers=headers, json={"device_token": "nope"}).status_code == 400
    assert client.post("/api/v1/sync/activate", headers=headers, json={
        "device_token": TOKEN, "cloud_api_url": "http://user:secret@127.0.0.1:9",
    }).status_code == 400
    status = _activate(client, headers)
    assert status["activated"] is True and status["shop_id"]
    assert status["bootstrap"] == "running"
    assert TOKEN not in json.dumps(status)
    path = credential_path()
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert TOKEN.encode() not in client.get("/api/v1/sync/diagnostics", headers=headers).content
    db_file = path.parents[1] / "pharmacy.db"
    assert TOKEN.encode() not in db_file.read_bytes()
    again = _activate(client, headers, token="pcd_" + str(uuid.uuid4()) + "." + ("cd" * 16))
    assert again["bootstrap"] == "running"
    db = SessionLocal()
    try:
        actions = [row.action for row in db.query(models.AuditLog).filter(models.AuditLog.action.like("sync.%")).order_by(models.AuditLog.id).all()]
    finally:
        db.close()
    assert actions == ["sync.activated", "sync.credential_replaced"]


def test_offline_events_upload_after_connect_and_a_lost_ack_does_not_double_apply(client):
    headers = _headers(client)
    _activate(client, headers)
    patient = client.post("/api/v1/patients/", headers=headers, json={
        "pharmacy_id": 1, "first_name": "Queued", "last_name": "Synthetic", "phone": "0300-7000002",
    })
    assert patient.status_code == 201
    cloud = Cloud()
    cloud.fail_with = TransportError("offline")
    worker = _worker(cloud)
    waiting = worker.run_once(now=T0, force=True)
    assert waiting["indicator"] == "waiting" and waiting["pending"] >= 1
    assert cloud.applied == []
    # The next attempt reaches the cloud, which stores the event, but the response is lost.
    worker.transport = DropFirstResponse(cloud)
    lost = worker.run_once(now=T0, force=True)
    assert lost["pending"] >= 1 and len(cloud.applied) == 1
    recovered = worker.run_once(now=T0, force=True)
    assert recovered["pending"] == 0 and recovered["indicator"] == "synced"
    assert len(cloud.applied) == 1  # the retry was already_processed, not a second apply


def test_restart_continues_from_pending_rows(client):
    headers = _headers(client)
    _activate(client, headers)
    assert client.post("/api/v1/patients/", headers=headers, json={
        "pharmacy_id": 1, "first_name": "Restart", "last_name": "Synthetic", "phone": "0300-7000003",
    }).status_code == 201
    # No worker has run yet. A new worker, as after a restart, sends the rows that are still pending.
    cloud = Cloud()
    done = _drain(_worker(cloud), now=T0)
    assert done["pending"] == 0
    assert [event["entity_type"] for event in cloud.applied] == ["patient"]


def test_a_few_thousand_events_drain_in_order(client):
    headers = _headers(client)
    shop_id = client.get("/api/v1/sync/status", headers=headers).json()["shop_id"]
    _insert_live_events(3000, shop_id)
    _activate(client, headers)
    cloud = Cloud()
    worker = _worker(cloud, batch_size=100, bootstrap_chunk=500)
    done = _drain(worker, limit=80, now=T0)
    assert done["pending"] == 0 and done["failed"] == 0
    sequences = [event["sequence"] for event in cloud.applied]
    assert sequences == sorted(sequences) and len(sequences) == 3000
    assert all(len(batch) <= 100 for batch in cloud.batches)


def test_prescription_is_not_applied_before_its_patient(client):
    headers = _headers(client)
    _activate(client, headers)
    medicine = client.post("/api/v1/inventory/medicines", headers=headers, json={
        "pharmacy_id": 1, "sku": "SYNC-RX", "name": "Synctab", "initial_batch": {
            "batch_number": "B1", "expiry_date": "2030-01-01", "quantity": 5, "cost_price": 1, "selling_price": 2,
        },
    })
    assert medicine.status_code == 201
    patient = client.post("/api/v1/patients/", headers=headers, json={
        "pharmacy_id": 1, "first_name": "Before", "last_name": "Synthetic", "phone": "0300-7000004",
    }).json()
    created = client.post("/api/v1/prescriptions/", headers=headers, json={
        "pharmacy_id": 1, "patient_id": patient["id"], "items": [{"medicine_id": medicine.json()["id"], "quantity": 1, "dosage": "1"}],
    })
    assert created.status_code == 201
    cloud = Cloud()
    cloud.conflict_if_patient_missing = True
    done = _drain(_worker(cloud), now=T0)
    assert done["failed"] == 0 and done["pending"] == 0
    order = [(event["entity_type"], event["operation"]) for event in cloud.applied]
    assert order.index(("patient", "created")) < order.index(("prescription", "created"))
    # A prescription sequenced before its patient is not marked synced, and neither is the blocked patient.
    db = SessionLocal()
    try:
        shop = db.query(models.Pharmacy.public_id).scalar()
        start = db.query(func.max(models.SyncOutbox.sequence)).scalar()
        patient_id = str(uuid.uuid4())
        rx_id = str(uuid.uuid4())
        now = datetime(2030, 1, 2)
        db.add(models.SyncOutbox(
            sequence=start + 1, event_id=rx_id, shop_id=shop, entity_type="prescription", entity_id=str(uuid.uuid4()),
            operation="created", entity_version=1, schema_version=1, origin="live", status="pending", retry_count=0, created_at=now,
            payload=json.dumps({"event": "prescription.created", "patient_public_id": patient_id, "public_id": rx_id, "version": 1}),
        ))
        db.add(models.SyncOutbox(
            sequence=start + 2, event_id=patient_id, shop_id=shop, entity_type="patient", entity_id=patient_id,
            operation="created", entity_version=1, schema_version=1, origin="live", status="pending", retry_count=0, created_at=now,
            payload=json.dumps({"event": "patient.created", "public_id": patient_id, "version": 1}),
        ))
        db.commit()
    finally:
        db.close()
    cloud.patients.clear()
    held = _worker(cloud).run_once(now=T0, force=True)
    assert held["indicator"] == "error"
    assert patient_id not in cloud.patients
    db = SessionLocal()
    try:
        rows = db.query(models.SyncOutbox.status).filter(models.SyncOutbox.event_id.in_([rx_id, patient_id])).all()
    finally:
        db.close()
    assert rows == [("pending",), ("pending",)]


def test_bootstrap_resumes_without_duplicate_patients_and_keeps_live_writes(client):
    headers = _headers(client)
    db = SessionLocal()
    try:
        db.info[DISABLED] = True
        with business_transaction(db):
            pharmacy_id = db.query(models.Pharmacy.id).scalar()
            for index in range(3):
                db.add(models.Patient(
                    pharmacy_id=pharmacy_id, first_name=f"Old{index}", last_name="Synthetic", phone=f"0300-710000{index}",
                ))
        db.info.pop(DISABLED, None)
    finally:
        db.close()
    _activate(client, headers)
    # A patient added while bootstrap has not uploaded yet must survive as a live event.
    live = client.post("/api/v1/patients/", headers=headers, json={
        "pharmacy_id": 1, "first_name": "During", "last_name": "Synthetic", "phone": "0300-7100099",
    })
    assert live.status_code == 201
    cloud = Cloud()
    partial = _worker(cloud, bootstrap_chunk=1, batch_size=1)
    partial.run_once(now=T0, force=True)
    assert len(cloud.patients) < 4
    resumed = _drain(_worker(cloud, bootstrap_chunk=1, batch_size=1), limit=30, now=T0)
    assert resumed["pending"] == 0
    assert len(cloud.patients) == 4
    again = _worker(cloud).run_once(now=T0, force=True)
    assert again["pending"] == 0 and len(cloud.patients) == 4
    # Rewinding the cursor and scanning again does not create a second event per patient.
    db = SessionLocal()
    try:
        state = db.query(models.SyncState).one()
        state.bootstrap_status = "running"
        state.bootstrap_stage = "patients"
        state.bootstrap_cursor = 0
        db.commit()
        from src.sync.bootstrap import advance_bootstrap

        advance_bootstrap(db, chunk=50)
        bootstrap_patients = db.query(models.SyncOutbox).filter(
            models.SyncOutbox.origin == "bootstrap", models.SyncOutbox.entity_type == "patient"
        ).count()
    finally:
        db.close()
    assert bootstrap_patients == 3


def test_server_error_leaves_events_pending_and_a_later_success_marks_them(client):
    headers = _headers(client)
    _activate(client, headers)
    assert client.post("/api/v1/patients/", headers=headers, json={
        "pharmacy_id": 1, "first_name": "Retry", "last_name": "Synthetic", "phone": "0300-7000005",
    }).status_code == 201
    cloud = Cloud()
    cloud.fail_with = TransportError("http_503")
    worker = _worker(cloud)
    failed = worker.run_once(now=T0, force=True)
    assert failed["indicator"] == "waiting" and failed["pending"] >= 1 and cloud.applied == []
    held = worker.run_once(now=T0, force=False)
    assert held["pending"] >= 1 and cloud.calls == 1
    done = worker.run_once(now=T0 + timedelta(seconds=31), force=False)
    assert done["pending"] == 0 and done["indicator"] == "synced"
    assert len(cloud.applied) == 1


def test_invalid_event_stops_retrying_and_does_not_block_a_later_product(client):
    headers = _headers(client)
    shop_id = client.get("/api/v1/sync/status", headers=headers).json()["shop_id"]
    _activate(client, headers)
    _drain(_worker(Cloud()), now=T0)  # finish the empty bootstrap first
    db = SessionLocal()
    try:
        now = datetime(2030, 1, 3)
        bad_id, good_id = str(uuid.uuid4()), str(uuid.uuid4())
        start = db.query(func.max(models.SyncOutbox.sequence)).scalar() or 0
        for offset, event_id in enumerate((bad_id, good_id), start=1):
            db.add(models.SyncOutbox(
                sequence=start + offset, event_id=event_id, shop_id=shop_id, entity_type="product",
                entity_id=str(uuid.uuid4()), operation="created", entity_version=1, schema_version=1,
                origin="live", status="pending", retry_count=0, created_at=now,
                payload=json.dumps({"event": "product.created", "name": "Leakname", "public_id": event_id}),
            ))
        db.commit()
    finally:
        db.close()
    cloud = Cloud()
    cloud.invalid.add(bad_id)
    worker = _worker(cloud)
    once = worker.run_once(now=T0, force=True)
    assert once["failed"] == 1 and once["pending"] == 0
    assert [event["event_id"] for event in cloud.applied] == [good_id]
    worker.run_once(now=T0, force=True)
    assert cloud.calls == 1  # the invalid event is not sent again
    body = client.get("/api/v1/sync/diagnostics", headers=headers).text
    assert bad_id in body and "Leakname" not in body and TOKEN not in body


def test_an_earlier_event_that_is_not_due_holds_the_ones_after_it(client):
    headers = _headers(client)
    shop_id = client.get("/api/v1/sync/status", headers=headers).json()["shop_id"]
    _activate(client, headers)
    _drain(_worker(Cloud()), now=T0)
    _insert_live_events(2, shop_id)
    db = SessionLocal()
    try:
        first = db.query(models.SyncOutbox).filter(models.SyncOutbox.status == "pending").order_by(models.SyncOutbox.sequence).first()
        first.next_attempt_at = datetime(2030, 6, 1)
        db.commit()
    finally:
        db.close()
    cloud = Cloud()
    assert _worker(cloud).run_once(now=T0, force=True)["pending"] == 2
    assert cloud.calls == 0


def test_bootstrap_events_upload_before_live_ones_even_when_their_sequence_is_higher(client):
    headers = _headers(client)
    db = SessionLocal()
    try:
        db.info[DISABLED] = True
        with business_transaction(db):
            pharmacy_id = db.query(models.Pharmacy.id).scalar()
            db.add(models.Patient(pharmacy_id=pharmacy_id, first_name="Earlier", last_name="Synthetic", phone="0300-7000006"))
        db.info.pop(DISABLED, None)
    finally:
        db.close()
    _activate(client, headers)
    assert client.post("/api/v1/inventory/medicines", headers=headers, json={
        "pharmacy_id": 1, "sku": "SYNC-LIVE", "name": "Liveonly",
    }).status_code == 201
    cloud = Cloud()
    _drain(_worker(cloud, batch_size=50), now=T0)
    db = SessionLocal()
    try:
        origin = {row.event_id: row.origin for row in db.query(models.SyncOutbox).all()}
    finally:
        db.close()
    for batch in cloud.batches:
        kinds = {origin[event_id] for event_id in batch}
        assert kinds != {"live", "bootstrap"}
    first_live = next(index for index, batch in enumerate(cloud.batches) if any(origin[event_id] == "live" for event_id in batch))
    last_bootstrap = max(index for index, batch in enumerate(cloud.batches) if any(origin[event_id] == "bootstrap" for event_id in batch))
    assert last_bootstrap < first_live


def test_a_predecessor_snapshot_precedes_an_update_of_a_preexisting_patient(client):
    headers = _headers(client)
    db = SessionLocal()
    try:
        db.info[DISABLED] = True
        with business_transaction(db):
            pharmacy_id = db.query(models.Pharmacy.id).scalar()
            patient = models.Patient(pharmacy_id=pharmacy_id, first_name="Pred", last_name="Synthetic", phone="0300-7000007")
            db.add(patient)
            db.flush()
            patient_id = patient.id
        db.info.pop(DISABLED, None)
    finally:
        db.close()
    updated = client.put(f"/api/v1/patients/{patient_id}", headers=headers, json={"notes": "second visit"})
    assert updated.status_code == 200
    _activate(client, headers)
    cloud = Cloud()
    _drain(_worker(cloud), now=T0)
    versions = [event["entity_version"] for event in cloud.applied if event["entity_type"] == "patient"]
    assert versions == [1, 2]


def test_diagnostics_hide_patient_text_and_runs_do_not_overlap(client, caplog):
    headers = _headers(client)
    _activate(client, headers)
    created = client.post("/api/v1/patients/", headers=headers, json={
        "pharmacy_id": 1, "first_name": "Secretname", "last_name": "Synthetic", "phone": "0300-7000008",
    }).json()
    db = SessionLocal()
    try:
        event_id = db.query(models.SyncOutbox.event_id).filter(models.SyncOutbox.entity_type == "patient").one()[0]
        record_error(db, event_id, "invalid_event:schema:event", retryable=False)
    finally:
        db.close()
    body = client.get("/api/v1/sync/diagnostics", headers=headers).json()
    assert body["failures"][0]["event_id"] == event_id
    assert body["failures"][0]["error"] == "invalid_event:schema:event"
    assert "Secretname" not in json.dumps(body)
    assert created["first_name"] not in json.dumps(body)

    class Hold:
        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()

        def push(self, _url, _token, body, _timeout):
            self.started.set()
            assert self.release.wait(2)
            return {"results": [{"event_id": event["event_id"], "result": "applied"} for event in body["events"]]}

    hold = Hold()
    caplog.set_level("INFO")
    worker = _worker(hold)
    # The failed patient is not pending. Add one pending product event so push blocks.
    shop_id = body["shop_id"]
    _insert_live_events(1, shop_id)
    thread = threading.Thread(target=lambda: worker.run_once(force=True))
    thread.start()
    assert hold.started.wait(2)
    assert worker.run_once(force=True) == {"skipped": "overlap"}
    hold.release.set()
    thread.join(2)
    assert not thread.is_alive()
    caplog.set_level("INFO")
    assert "Secretname" not in caplog.text and TOKEN not in caplog.text


def test_sync_now_requires_activation(client):
    headers = _headers(client)
    assert client.post("/api/v1/sync/run", headers=headers).status_code == 400


def test_two_workers_do_not_share_a_credential_file(client, tmp_path, monkeypatch):
    """A second data directory is a second shop. This only checks the file boundary."""
    headers = _headers(client)
    _activate(client, headers)
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("PHARMACARE_DATA_DIR", str(other))
    from src.sync.secrets import read_credential

    assert read_credential() is None


@pytest.mark.parametrize("code", ["offline", "timeout", "dns", "http_429", "http_503"])
def test_waiting_codes(code):
    from src.sync.status import indicator, is_waiting

    assert is_waiting(code)
    assert indicator(activated=True, busy=False, pending=3, failed=0, last_error=code) == "waiting"
    assert indicator(activated=True, busy=True, pending=3, failed=0, last_error=code) == "syncing"
    assert indicator(activated=True, busy=False, pending=0, failed=1, last_error=code) == "error"
