import re
import sqlite3
from pathlib import Path

from src.auth.service import hash_password, verify_password

from .conftest import MANAGER, auth, set_up_manager, start_client
from .legacy import LEGACY_PASSWORD, build_oldest

REPO = Path(__file__).resolve().parents[2]


def test_hash_is_argon2id_not_plaintext():
    stored = hash_password("a long synthetic pw")
    assert stored.startswith("$argon2id$")
    assert "a long synthetic pw" not in stored
    assert verify_password("a long synthetic pw", stored)
    assert not verify_password("A long synthetic pw", stored)
    assert not verify_password("", stored)


def test_first_run_setup_then_login(client):
    short = client.post("/api/v1/auth/setup", json={**MANAGER, "password": "short", "pharmacy_name": "Synthetic"})
    assert short.status_code == 400
    missing_shop = client.post("/api/v1/auth/setup", json=MANAGER)
    assert missing_shop.status_code == 400

    headers = set_up_manager(client, pharmacy_name="Synthetic Pharmacy")
    assert client.get("/api/v1/auth/me", headers=auth(headers)).json()["username"] == MANAGER["username"]
    assert client.get("/api/v1/auth/setup").json()["needs_setup"] is False

    again = client.post("/api/v1/auth/setup", json={**MANAGER, "username": "second", "pharmacy_name": "Other"})
    assert again.status_code == 409

    good = client.post("/api/v1/auth/login", json={"username": MANAGER["username"], "password": MANAGER["password"]})
    assert good.status_code == 200
    wrong = client.post("/api/v1/auth/login", json={"username": MANAGER["username"], "password": "wrong password"})
    assert wrong.status_code == 401


def test_setup_uses_existing_pharmacy(demo_client):
    status = demo_client.get("/api/v1/auth/setup").json()
    assert status["needs_setup"] is True and status["has_pharmacy"] is True
    headers = set_up_manager(demo_client)
    assert headers["_pharmacy_id"] == 1


def test_api_requires_sign_in(client):
    assert client.get("/api/v1/patients/?pharmacy_id=1").status_code == 401
    assert client.get("/api/v1/billing/sales?pharmacy_id=1").status_code == 401


def test_legacy_pbkdf2_hash_still_signs_in_and_is_upgraded(db_path):
    build_oldest(db_path, patched=True)
    with start_client() as client:
        wrong = client.post("/api/v1/auth/login", json={"username": "manager", "password": "not it"})
        assert wrong.status_code == 401
        good = client.post("/api/v1/auth/login", json={"username": "manager", "password": LEGACY_PASSWORD})
        assert good.status_code == 200, good.text

    conn = sqlite3.connect(db_path)
    try:
        stored = conn.execute("SELECT password_hash FROM staff WHERE username = 'manager'").fetchone()[0]
        actions = [row[0] for row in conn.execute("SELECT action FROM audit_logs ORDER BY id")]
    finally:
        conn.close()
    assert stored.startswith("$argon2id$")
    assert actions == ["auth.login_failed", "auth.password_rehashed", "auth.login"]

    with start_client() as client:
        again = client.post("/api/v1/auth/login", json={"username": "manager", "password": LEGACY_PASSWORD})
        assert again.status_code == 200


def test_source_tree_has_no_hard_coded_manager_password():
    roots = [REPO / "backend" / "src", REPO / "backend" / "migrations", REPO / "desktop" / "src", REPO / "desktop" / "electron"]
    forbidden = re.compile(r"store123|MANAGER_PASSWORD")
    hits = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".js", ".jsx", ".ts", ".tsx", ".json"} or "node_modules" in path.parts:
                continue
            if forbidden.search(path.read_text(encoding="utf-8", errors="ignore")):
                hits.append(str(path.relative_to(REPO)))
    assert hits == []
