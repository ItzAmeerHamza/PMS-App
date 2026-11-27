"""The desktop sync worker against this API and PostgreSQL.

Skipped with the rest of the cloud suite when PostgreSQL is not reachable.
People and medicines here are synthetic.
"""

import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.sync.transport import TransportError  # noqa: E402

from .conftest import sql  # noqa: E402


class ClientTransport:
    def __init__(self, client):
        self.client = client

    def push(self, _base_url, token, body, _timeout):
        response = self.client.post("/api/v1/sync/push", headers={"Authorization": f"Bearer {token}"}, json=body)
        if response.status_code == 429 or response.status_code >= 500:
            raise TransportError(f"http_{response.status_code}")
        if response.status_code >= 400:
            raise TransportError(f"http_{response.status_code}")
        return response.json()


class DropFirstAck(ClientTransport):
    """The cloud commits, then the response is thrown away."""

    def __init__(self, client):
        super().__init__(client)
        self.dropped = False

    def push(self, base_url, token, body, timeout):
        result = super().push(base_url, token, body, timeout)
        if not self.dropped:
            self.dropped = True
            raise TransportError("timeout")
        return result


def _session(tmp_path, monkeypatch):
    monkeypatch.setenv("PHARMACARE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CLOUD_API_URL", raising=False)
    monkeypatch.delenv("PHARMACARE_CLOUD_API_URL", raising=False)
    from src.core.database import SessionLocal, get_engine, init_engine
    from src.core.migrate import run_migrations

    init_engine(tmp_path / "pharmacy.db")
    run_migrations(get_engine(), backup=False)
    return SessionLocal()


def _close():
    from src.core.database import get_engine

    get_engine().dispose()


def _build(db, patient_public_id, *, patients=1, with_prescription=True, quantity=10):
    """Rows with the outbox disabled, as if they existed before sync was turned on."""
    from src import models
    from src.core.outbox import DISABLED
    from src.core.transaction import business_transaction
    from src.inventory.service import change_batch_quantity

    db.info[DISABLED] = True
    with business_transaction(db):
        pharmacy = models.Pharmacy(name="Synthetic Shop")
        db.add(pharmacy)
        db.flush()
        medicine = models.Medicine(pharmacy_id=pharmacy.id, sku="SYNC-1", name="Syncillin", form="tablet")
        db.add(medicine)
        db.flush()
        batch = models.StockBatch(
            medicine_id=medicine.id, batch_number="B1", expiry_date=date(2030, 1, 1),
            quantity=0, cost_price=1, selling_price=2,
        )
        db.add(batch)
        db.flush()
        change_batch_quantity(db, batch, quantity, "receipt")
        made = []
        for index in range(patients):
            public_id = patient_public_id if index == 0 else str(uuid.uuid4())
            patient = models.Patient(
                pharmacy_id=pharmacy.id, public_id=public_id, first_name=f"Synca{index}",
                last_name="Synthetic", phone=f"0300111000{index}",
            )
            db.add(patient)
            db.flush()
            made.append(patient)
            if with_prescription and index == 0:
                rx = models.Prescription(
                    pharmacy_id=pharmacy.id, patient_id=patient.id, status="recorded",
                    prescribed_at=datetime(2030, 1, 2, tzinfo=timezone.utc).replace(tzinfo=None),
                    diagnosis="Synthetic",
                )
                db.add(rx)
                db.flush()
                db.add(models.PrescriptionItem(
                    prescription_id=rx.id, medicine_id=medicine.id, medicine_name="Syncillin",
                    quantity=1, dosage="1", frequency="daily", duration_days=3,
                ))
    db.info.pop(DISABLED, None)
    return pharmacy.public_id


def _activate(db, make_shop, public_id):
    from src.sync.service import activate

    shop = make_shop(shop_id=public_id, name="Synthetic Shop")
    token = shop["headers"]["Authorization"].split(" ", 1)[1]
    activate(db, token, "http://127.0.0.1:9")
    return token


def _drain(worker, limit=40):
    last = None
    for _ in range(limit):
        last = worker.run_once(force=True)
        if last.get("pending") == 0 and last.get("bootstrap") == "complete":
            return last
    return last


def test_two_shops_sync_into_isolated_rows_and_a_prescription_follows_its_patient(tmp_path, monkeypatch, client, make_shop, db_engine):
    from src.sync.worker import SyncWorker

    shared = str(uuid.uuid4())
    for folder in ("a", "b"):
        path = tmp_path / folder
        path.mkdir()
        db = _session(path, monkeypatch)
        try:
            public_id = _build(db, shared, quantity=10)
            _activate(db, make_shop, public_id)
        finally:
            db.close()
        done = _drain(SyncWorker(ClientTransport(client), batch_size=100, bootstrap_chunk=200))
        assert done["pending"] == 0 and done["failed"] == 0, done
        _close()

    rows = sql(db_engine, "SELECT shop_id, public_id FROM patients WHERE public_id = :p", p=shared)
    assert len(rows) == 2 and len({shop for shop, _public in rows}) == 2
    assert sql(db_engine, "SELECT COUNT(*) FROM stock_batches WHERE quantity = 10") == [(2,)]
    order = [row[0] for row in sql(
        db_engine, "SELECT entity_type FROM processed_sync_events WHERE shop_id = :s ORDER BY id", s=rows[0][0]
    )]
    assert order.index("patient") < order.index("prescription")
    assert order.index("product") < order.index("stock_movement")


def test_lost_acknowledgement_does_not_apply_stock_twice(tmp_path, monkeypatch, client, make_shop, db_engine):
    from src.sync.worker import SyncWorker

    path = tmp_path / "shop"
    path.mkdir()
    db = _session(path, monkeypatch)
    try:
        public_id = _build(db, str(uuid.uuid4()), with_prescription=True, quantity=7)
        _activate(db, make_shop, public_id)
    finally:
        db.close()
    worker = SyncWorker(DropFirstAck(client), batch_size=100, bootstrap_chunk=200)
    first = worker.run_once(force=True)
    assert first["pending"] > 0
    assert sql(db_engine, "SELECT quantity FROM stock_batches") == [(7,)]
    second = _drain(worker)
    assert second["pending"] == 0
    assert sql(db_engine, "SELECT quantity FROM stock_batches") == [(7,)]
    assert sql(db_engine, "SELECT COUNT(*) FROM stock_movements") == [(1,)]
    _close()


def test_bootstrap_interruption_does_not_duplicate_patients(tmp_path, monkeypatch, client, make_shop, db_engine):
    from src.sync.worker import SyncWorker

    path = tmp_path / "shop"
    path.mkdir()
    db = _session(path, monkeypatch)
    try:
        public_id = _build(db, str(uuid.uuid4()), patients=3, with_prescription=False, quantity=4)
        _activate(db, make_shop, public_id)
    finally:
        db.close()
    first = SyncWorker(ClientTransport(client), batch_size=1, bootstrap_chunk=1)
    seen = 0
    for _ in range(6):
        first.run_once(force=True)
        seen = sql(db_engine, "SELECT COUNT(*) FROM patients")[0][0]
        if seen:
            break
    assert 0 < seen < 3
    done = _drain(SyncWorker(ClientTransport(client), batch_size=1, bootstrap_chunk=1), limit=30)
    assert done["pending"] == 0
    assert sql(db_engine, "SELECT COUNT(*), COUNT(DISTINCT public_id) FROM patients") == [(3, 3)]
    again = SyncWorker(ClientTransport(client), batch_size=50, bootstrap_chunk=50).run_once(force=True)
    assert again["pending"] == 0
    assert sql(db_engine, "SELECT COUNT(*) FROM patients") == [(3,)]
    _close()
