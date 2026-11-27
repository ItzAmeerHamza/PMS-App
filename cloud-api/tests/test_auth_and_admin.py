"""Device credentials, shop isolation, owner-only admin routes, migrations."""

import uuid

from sqlalchemy import text

from .conftest import OWNER, TEST_URL, Events, push, sql

ADMIN_ROUTES = ["/api/v1/admin/shops", "/api/v1/admin/overview", "/api/v1/admin/inventory", "/api/v1/admin/patients",
                "/api/v1/admin/prescriptions", "/api/v1/admin/sync-status", "/api/v1/admin/movements"]


def test_unknown_malformed_and_revoked_devices_are_rejected(client, make_shop, owner_headers):
    shop = make_shop()
    body = {"events": []}
    assert client.post("/api/v1/sync/push", json=body).status_code == 401
    for token in ("nonsense", "pcd_not-a-uuid.secret", f"pcd_{uuid.uuid4()}.secret", f"pcd_{shop['device_id']}.wrong-secret"):
        assert client.post("/api/v1/sync/push", headers={"Authorization": f"Bearer {token}"}, json=body).status_code == 401
    assert client.post("/api/v1/sync/push", headers=shop["headers"], json=body).status_code == 200
    assert client.post(f"/api/v1/admin/devices/{shop['device_id']}/revoke", headers=owner_headers).status_code == 200
    assert client.post("/api/v1/sync/push", headers=shop["headers"], json=body).status_code == 401


def test_only_a_hash_of_the_device_secret_is_stored(client, make_shop, db_engine):
    shop = make_shop()
    token = shop["headers"]["Authorization"].split(" ", 1)[1]
    secret = token.split(".", 1)[1]
    stored = sql(db_engine, "SELECT secret_hash FROM shop_devices")[0][0]
    assert secret not in stored and token not in stored and len(stored) == 64


def test_shop_a_cannot_write_or_read_shop_b(client, make_shop, db_engine):
    shop_a, shop_b = make_shop("Shop A"), make_shop("Shop B")
    shared_public_id = uuid.uuid4()  # same UUID used by both shops by accident
    a, b = Events(shop_a["shop_id"]), Events(shop_b["shop_id"])
    assert push(client, shop_b, [b.patient(shared_public_id, first_name="Bshop")])[0] == ["applied"]
    assert push(client, shop_a, [a.patient(shared_public_id, first_name="Ashop")])[0] == ["applied"]
    assert sql(db_engine, "SELECT COUNT(*) FROM patients WHERE public_id = :p", p=shared_public_id) == [(2,)]

    # Shop A's device sends an event claiming to be shop B: rejected, B untouched.
    forged = b.patient(shared_public_id, version=2, operation="updated", first_name="Forged")
    _, detail = push(client, shop_a, [forged])
    assert (detail[0]["result"], detail[0]["code"]) == ("invalid_event", "shop_id_mismatch")
    assert sql(db_engine, "SELECT first_name, version FROM patients WHERE shop_id = :s", s=shop_b["shop_id"]) == [("Bshop", 1)]

    # A's updates only touch A's row.
    assert push(client, shop_a, [a.patient(shared_public_id, version=2, operation="updated", first_name="Aupdated")])[0] == ["applied"]
    assert sql(db_engine, "SELECT first_name FROM patients WHERE shop_id = :s", s=shop_b["shop_id"]) == [("Bshop",)]

    # A's credential cannot read anything through the admin API.
    for route in ADMIN_ROUTES:
        assert client.get(route, headers=shop_a["headers"]).status_code == 403


def test_admin_routes_reject_anonymous_and_device_callers(client, make_shop, owner_headers):
    shop = make_shop()
    client.cookies.clear()
    for route in ADMIN_ROUTES:
        assert client.get(route).status_code == 401
        assert client.get(route, headers={"Authorization": "Bearer pco_made-up"}).status_code == 401
        assert client.get(route, headers=shop["headers"]).status_code == 403
        assert client.get(route, headers=owner_headers).status_code == 200
    assert client.post("/api/v1/admin/shops", headers=shop["headers"], json={"shop_id": str(uuid.uuid4()), "name": "x"}).status_code == 403
    assert client.post(f"/api/v1/admin/shops/{shop['shop_id']}/devices", headers=shop["headers"], json={}).status_code == 403


def test_owner_login_logout_and_password_rules(client, owner_headers, db_engine):
    from .conftest import csrf_headers

    headers = csrf_headers(client)
    assert client.post("/api/v1/owner/login", headers=headers, json={**OWNER, "password": "wrong-password!"}).status_code == 401
    assert client.post("/api/v1/owner/login", headers=headers, json={"email": "nobody@example.test", "password": "x" * 20}).status_code == 401
    assert client.post("/api/v1/owner/login", json=OWNER).status_code == 403
    stored = sql(db_engine, "SELECT password_hash FROM owners")[0][0]
    assert stored.startswith("$argon2id$") and OWNER["password"] not in stored
    assert sql(db_engine, "SELECT totp_secret IS NOT NULL FROM owners") == [(True,)]
    assert client.post("/api/v1/owner/logout", headers=owner_headers).status_code == 204
    assert client.get("/api/v1/admin/shops", headers=owner_headers).status_code == 401


def test_create_owner_command(client, db_engine, monkeypatch, capsys):
    from app.cli import main

    monkeypatch.setenv("OWNER_PASSWORD", "short")
    assert main(["create-owner", "--email", "cli@example.test"]) == 1
    monkeypatch.setenv("OWNER_PASSWORD", "a-long-cli-password")
    assert main(["create-owner", "--email", "cli@example.test"]) == 0
    assert main(["create-owner", "--email", "cli@example.test"]) == 1, "duplicate email"
    assert "a-long-cli-password" not in capsys.readouterr().out
    from .conftest import csrf_headers

    started = client.post("/api/v1/owner/login", headers=csrf_headers(client),
                          json={"email": "cli@example.test", "password": "a-long-cli-password"})
    assert started.status_code == 200 and started.json()["status"] == "enroll"
    assert "token" not in started.json()


def test_admin_reads_paginate_and_filter_by_shop(client, make_shop, owner_headers):
    shop_a, shop_b = make_shop("Alpha Shop"), make_shop("Beta Shop")
    a, b = Events(shop_a["shop_id"]), Events(shop_b["shop_id"])
    product = uuid.uuid4()
    push(client, shop_a, [a.product(product, sku="A-1"), a.movement(product, 9, 9)] +
         [a.patient(first_name=f"P{n}", last_name=f"Last{n:02d}") for n in range(5)])
    push(client, shop_b, [b.patient(first_name="Bee", last_name="Only")])
    get = lambda path: client.get("/api/v1/admin" + path, headers=owner_headers).json()

    page = get(f"/patients?shop_id={shop_a['shop_id']}&limit=2&offset=2")
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (5, 2, 2, 2)
    assert [p["last_name"] for p in page["items"]] == ["Last02", "Last03"]
    assert {p["shop_id"] for p in get("/patients?limit=200")["items"]} == {shop_a["shop_id"], shop_b["shop_id"]}
    assert get(f"/patients?shop_id={shop_b['shop_id']}")["total"] == 1
    assert get("/patients?search=Bee")["total"] == 1
    assert client.get(f"/api/v1/admin/inventory?shop_id={shop_a['shop_id']}&low_stock=true&search=A-1", headers=owner_headers).status_code == 200
    assert client.get("/api/v1/admin/movements?limit=5", headers=owner_headers).status_code == 200
    inventory = get(f"/inventory?shop_id={shop_a['shop_id']}")["items"]
    assert [(i["sku"], i["quantity"]) for i in inventory] == [("A-1", 9)]
    assert get(f"/overview?shop_id={shop_a['shop_id']}")["units_on_hand"] == 9
    assert get("/shops")["total"] == 2
    status = {s["shop_name"]: s for s in get("/sync-status")["items"]}
    assert status["Alpha Shop"]["events_applied"] == 7 and status["Alpha Shop"]["last_sync_at"]
    assert client.get("/api/v1/admin/patients?limit=500", headers=owner_headers).status_code == 422


def test_movement_dates_and_unreported_backlog(client, make_shop, owner_headers):
    shop = make_shop("Dated Shop")
    quiet = make_shop("Quiet Shop")
    events = Events(shop["shop_id"])
    product = uuid.uuid4()
    created = events.product(product, sku="DATE-1")
    older = events.movement(product, 3, 3)
    older["payload"]["created_at"] = "2020-01-15T08:00:00Z"
    newer = events.movement(product, 2, 5)
    newer["payload"]["created_at"] = "2024-06-01T08:00:00Z"
    push(client, shop, [created, older, newer])
    headers = owner_headers
    window = client.get(
        f"/api/v1/admin/inventory/{product}?shop_id={shop['shop_id']}&date_from=2024-01-01&date_to=2024-12-31",
        headers=headers,
    ).json()
    assert window["quantity"] == 5
    assert [row["quantity_delta"] for row in window["movements"]] == [2]
    empty = client.get(
        f"/api/v1/admin/movements?shop_id={shop['shop_id']}&date_from=1999-01-01&date_to=1999-01-02",
        headers=headers,
    ).json()
    assert empty["total"] == 0
    status = client.get("/api/v1/admin/sync-status?limit=200", headers=headers).json()["items"]
    quiet_row = next(row for row in status if row["shop_id"] == quiet["shop_id"])
    assert quiet_row["reported_pending"] is None
    assert quiet_row["last_sync_at"] is None


def test_no_secrets_in_responses(client, make_shop, owner_headers):
    shop = make_shop()
    password = TEST_URL.split("@")[0].split(":")[-1] if "@" in TEST_URL else None
    texts = [client.get("/health").text] + [client.get(route, headers=owner_headers).text for route in ADMIN_ROUTES]
    for body in texts:
        assert "postgresql" not in body and "secret_hash" not in body and "password_hash" not in body
        if password:
            assert password not in body
    from app.config import get_settings

    assert "<hidden>" in repr(get_settings())


def test_migrations_match_models(db_engine):
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from app.models import Base

    with db_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
        assert diff == []
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002_owner_mfa"


def test_local_backend_has_no_dependency_on_cloud_api():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2] / "backend" / "src"
    hits = [str(p) for p in backend.rglob("*.py") if "cloud-api" in p.read_text() or "from app." in p.read_text()]
    assert hits == []
