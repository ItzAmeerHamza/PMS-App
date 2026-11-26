import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src import models
from src.core.database import SessionLocal, get_engine
from src.core.migrate import run_migrations
from src.core.transaction import business_transaction

from .conftest import auth


@pytest.fixture
def migrated(db_path):
    run_migrations()
    # Drop the pooled migration connection (env.py turns foreign keys back on for it)
    # so these tests see a brand-new connection configured only by the engine.
    get_engine().dispose()
    return db_path


def make_pharmacy(db) -> models.Pharmacy:
    pharmacy = models.Pharmacy(name="Synthetic Pharmacy")
    db.add(pharmacy)
    db.commit()
    return pharmacy


def test_connection_pragmas(migrated):
    with get_engine().connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_foreign_keys_reject_orphan_insert(migrated):
    db = SessionLocal()
    try:
        pharmacy = make_pharmacy(db)
        db.add(models.Prescription(pharmacy_id=pharmacy.id, patient_id=999_999, status="recorded"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.query(models.Prescription).count() == 0
    finally:
        db.close()


def test_failed_business_transaction_rolls_back_everything(migrated):
    db = SessionLocal()
    try:
        pharmacy = make_pharmacy(db)
        with pytest.raises(RuntimeError):
            with business_transaction(db):
                db.add(models.Patient(pharmacy_id=pharmacy.id, first_name="Gamma", last_name="Synthetic", phone="0300-0000003"))
                db.add(models.AuditLog(action="patient.created", pharmacy_id=pharmacy.id))
                db.flush()
                raise RuntimeError("boom")
        assert db.query(models.Patient).count() == 0
        assert db.query(models.AuditLog).count() == 0
    finally:
        db.close()


def test_nested_transaction_joins_the_outer_one(migrated):
    db = SessionLocal()
    try:
        pharmacy = make_pharmacy(db)
        with pytest.raises(ValueError):
            with business_transaction(db):
                with business_transaction(db):
                    db.add(models.Patient(pharmacy_id=pharmacy.id, first_name="Inner", last_name="Synthetic", phone="0300-1"))
                # The inner block must not have committed on its own.
                raise ValueError("outer fails after inner finished")
        assert db.query(models.Patient).count() == 0
    finally:
        db.close()


def test_version_increments_on_update(migrated):
    db = SessionLocal()
    try:
        pharmacy = make_pharmacy(db)
        patient = models.Patient(pharmacy_id=pharmacy.id, first_name="Delta", last_name="Synthetic", phone="0300-4")
        db.add(patient)
        db.commit()
        assert patient.version == 1 and len(patient.public_id) == 36
        original_id = patient.public_id
        patient.notes = "updated"
        db.commit()
        assert patient.version == 2
        assert patient.public_id == original_id
    finally:
        db.close()


def test_failed_sale_changes_no_stock(demo_client, manager):
    headers = auth(manager)
    pharmacy_id = manager["_pharmacy_id"]
    medicines = demo_client.get(f"/api/v1/inventory/medicines?pharmacy_id={pharmacy_id}", headers=headers).json()
    in_stock = [m for m in medicines if m["sellable_quantity"] > 0]
    first, second = in_stock[0], in_stock[1]
    response = demo_client.post(
        "/api/v1/billing/sales",
        headers=headers,
        json={
            "pharmacy_id": pharmacy_id,
            "items": [
                {"medicine_id": first["id"], "quantity": 1},
                {"medicine_id": second["id"], "quantity": second["sellable_quantity"] + 1},
            ],
        },
    )
    assert response.status_code == 400
    after = {m["id"]: m["sellable_quantity"] for m in demo_client.get(f"/api/v1/inventory/medicines?pharmacy_id={pharmacy_id}", headers=headers).json()}
    assert after[first["id"]] == first["sellable_quantity"]
    assert after[second["id"]] == second["sellable_quantity"]
    db = SessionLocal()
    try:
        assert db.query(models.Sale).count() == 0
        assert db.query(models.AuditLog).filter(models.AuditLog.action == "sale.created").count() == 0
    finally:
        db.close()
