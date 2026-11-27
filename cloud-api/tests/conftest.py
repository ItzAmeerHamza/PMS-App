"""Cloud API tests run against real PostgreSQL.

Database: CLOUD_TEST_DATABASE_URL, default postgresql+psycopg://localhost/pharmacare_cloud_test.
If it cannot be reached, every test is skipped with that reason (never reported as passed).
The schema is rebuilt from the Alembic migrations once per run; tables are truncated per test.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

TEST_URL = os.environ.get("CLOUD_TEST_DATABASE_URL", "postgresql+psycopg://localhost/pharmacare_cloud_test")
os.environ["DATABASE_URL"] = TEST_URL  # the app under test must never see another database
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "desktop_events.json"

TABLES = ["processed_sync_events", "synchronization_state", "stock_movements", "stock_batches", "prescription_items",
          "prescriptions", "patients", "products", "audit_logs", "owner_challenges", "owner_sessions", "owners",
          "shop_devices", "shops"]


def _reachable() -> str | None:
    try:
        engine = create_engine(TEST_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return None
    except Exception as exc:  # noqa: BLE001
        return f"PostgreSQL not reachable at CLOUD_TEST_DATABASE_URL ({type(exc).__name__}); cloud tests NOT run"


SKIP_REASON = _reachable()


def pytest_collection_modifyitems(config, items):
    if SKIP_REASON:
        for item in items:
            item.add_marker(pytest.mark.skip(reason=SKIP_REASON))


@pytest.fixture(scope="session")
def migrated():
    from alembic import command
    from alembic.config import Config

    engine = create_engine(TEST_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.attributes["url"] = TEST_URL
    command.upgrade(cfg, "head")
    from app.models.db import init_engine

    init_engine(TEST_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(migrated):
    with migrated.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    return migrated


@pytest.fixture
def client(db_engine):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


OWNER = {"email": "owner@example.test", "password": "synthetic-owner-pass"}


def csrf_headers(client) -> dict:
    token = client.get("/api/v1/owner/csrf").json()["token"]
    return {"X-CSRF-Token": token}


def sign_in_owner(client, email: str, password: str) -> dict:
    """Password, then the TOTP step. Returns a bearer header for admin calls."""
    import pyotp

    started = client.post("/api/v1/owner/login", headers=csrf_headers(client), json={"email": email, "password": password})
    assert started.status_code == 200, started.text
    body = started.json()
    secret = body.get("secret")
    if secret is None:
        from app.models.db import SessionLocal
        from app.models import Owner

        db = SessionLocal()
        try:
            secret = db.query(Owner).filter(Owner.email == email.strip().lower()).one().totp_secret
        finally:
            db.close()
    code = pyotp.TOTP(secret).now()
    confirmed = client.post("/api/v1/owner/totp", headers=csrf_headers(client), json={"challenge": body["challenge"], "code": code})
    assert confirmed.status_code == 200, confirmed.text
    return {"Authorization": f"Bearer {confirmed.json()['token']}"}


@pytest.fixture
def owner_headers(client):
    from app.models.db import SessionLocal
    from app.services.accounts import create_owner

    db = SessionLocal()
    try:
        create_owner(db, OWNER["email"], OWNER["password"])
    finally:
        db.close()
    return sign_in_owner(client, OWNER["email"], OWNER["password"])


@pytest.fixture
def make_shop(client, owner_headers):
    def _make(name="Synthetic Shop", shop_id=None):
        shop_id = str(shop_id or uuid.uuid4())
        assert client.post("/api/v1/admin/shops", headers=owner_headers, json={"shop_id": shop_id, "name": name}).status_code == 201
        device = client.post(f"/api/v1/admin/shops/{shop_id}/devices", headers=owner_headers, json={"label": "Counter PC"}).json()
        return {"shop_id": shop_id, "device_id": device["device_id"], "headers": {"Authorization": f"Bearer {device['token']}"}}

    return _make


def sql(engine, query, **params):
    with engine.connect() as conn:
        return conn.execute(text(query), params).all()


class Events:
    """Builds schema-v1 events in the same shape as the desktop outbox."""

    def __init__(self, shop_id):
        self.shop_id = shop_id
        self.sequence = 0

    def event(self, entity_type, operation, entity_id, version, payload, event_name):
        self.sequence += 1
        return {"event_id": str(uuid.uuid4()), "sequence": self.sequence, "shop_id": self.shop_id,
                "entity_type": entity_type, "entity_id": str(entity_id), "operation": operation,
                "entity_version": version, "schema_version": 1, "event": event_name,
                "payload": {"event": event_name, **payload},
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}

    def product(self, public_id=None, version=1, operation="created", **fields):
        public_id = public_id or uuid.uuid4()
        payload = {"public_id": str(public_id), "version": version, "sku": fields.pop("sku", "SKU-1"),
                   "name": fields.pop("name", "Synthetic medicine"), "unit_price": "5.00", "is_active": True,
                   "requires_prescription": False, "batches": [], **fields}
        return self.event("product", operation, public_id, version, payload, f"product.{operation}")

    def movement(self, product_id, delta, after, batch_id=None, movement_type="receipt", public_id=None):
        public_id = public_id or uuid.uuid4()
        payload = {"public_id": str(public_id), "movement_type": movement_type, "quantity_delta": delta,
                   "quantity_after": after, "reason": None, "source_type": "batch", "source_ref": None,
                   "medicine_public_id": str(product_id),
                   "batch": {"public_id": str(batch_id or uuid.uuid4()), "batch_number": "B-1", "expiry_date": "2099-01-01",
                             "quantity": after, "cost_price": "2.00", "selling_price": "5.00"}}
        return self.event("stock_movement", "created", public_id, 1, payload, "stock.movement_created")

    def patient(self, public_id=None, version=1, operation="created", **fields):
        public_id = public_id or uuid.uuid4()
        payload = {"public_id": str(public_id), "version": version, "first_name": fields.pop("first_name", "Synthetic"),
                   "last_name": fields.pop("last_name", "Patient"), "phone": fields.pop("phone", "0300-0000000"), **fields}
        return self.event("patient", operation, public_id, version, payload, f"patient.{operation}")

    def tombstone(self, entity_type, public_id, version):
        payload = {"public_id": str(public_id), "version": version, "deleted_at": "2030-01-01T00:00:00Z"}
        return self.event(entity_type, "deleted", public_id, version, payload, f"{entity_type}.deleted")

    def prescription(self, patient_id, items, public_id=None, version=1, operation="created", status="recorded"):
        public_id = public_id or uuid.uuid4()
        payload = {"public_id": str(public_id), "version": version, "patient_public_id": str(patient_id),
                   "status": status, "diagnosis": "Synthetic diagnosis",
                   "items": [{"public_id": str(item.get("public_id") or uuid.uuid4()), "medicine_public_id": str(item["product"]),
                              "medicine_name": "Synthetic medicine", "quantity": item.get("quantity", 1), "dosage": "1 tab"}
                             for item in items]}
        return self.event("prescription", operation, public_id, version, payload, f"prescription.{operation}")


def push(client, shop, events, **extra):
    response = client.post("/api/v1/sync/push", headers=shop["headers"], json={"events": events, **extra})
    assert response.status_code == 200, response.text
    return [r["result"] for r in response.json()["results"]], response.json()["results"]


def load_fixture():
    return json.loads(FIXTURE.read_text())
