"""Owner TOTP, cookie session, CSRF, and login rate limit."""

import pyotp

from .conftest import OWNER, csrf_headers, sign_in_owner


def test_mfa_enrollment_wrong_code_and_cookie_session(client, db_engine):
    from app.models.db import SessionLocal
    from app.services.accounts import create_owner
    from app.auth.guard import SESSION_COOKIE

    db = SessionLocal()
    try:
        create_owner(db, OWNER["email"], OWNER["password"])
    finally:
        db.close()
    started = client.post("/api/v1/owner/login", headers=csrf_headers(client), json=OWNER)
    assert started.status_code == 200
    body = started.json()
    assert body["status"] == "enroll" and body["secret"] and "token" not in body
    assert client.post("/api/v1/owner/totp", headers=csrf_headers(client),
                       json={"challenge": body["challenge"], "code": "000000"}).status_code == 401
    assert client.get("/api/v1/admin/shops").status_code == 401
    code = pyotp.TOTP(body["secret"]).now()
    confirmed = client.post("/api/v1/owner/totp", headers=csrf_headers(client),
                            json={"challenge": body["challenge"], "code": code})
    assert confirmed.status_code == 200 and confirmed.json()["token"].startswith("pco_")
    assert SESSION_COOKIE in confirmed.headers.get("set-cookie", "")
    assert "HttpOnly" in confirmed.headers.get("set-cookie", "")
    # Cookie alone, without the bearer header, can read. A mutation without CSRF cannot.
    client.headers.clear()
    assert client.get("/api/v1/admin/shops").status_code == 200
    assert client.post("/api/v1/owner/logout").status_code == 403
    assert client.post("/api/v1/owner/logout", headers=csrf_headers(client)).status_code == 204
    assert client.get("/api/v1/admin/shops").status_code == 401


def test_second_sign_in_asks_for_a_code_not_a_new_secret(client):
    from app.models.db import SessionLocal
    from app.services.accounts import create_owner

    db = SessionLocal()
    try:
        create_owner(db, "again@example.test", OWNER["password"])
    finally:
        db.close()
    headers = sign_in_owner(client, "again@example.test", OWNER["password"])
    assert client.get("/api/v1/admin/overview", headers=headers).status_code == 200
    client.cookies.clear()
    started = client.post("/api/v1/owner/login", headers=csrf_headers(client),
                          json={"email": "again@example.test", "password": OWNER["password"]})
    assert started.json()["status"] == "totp" and "secret" not in started.json()


def test_login_rate_limit(client):
    from app.auth.guard import clear_login_limits
    from app.models.db import SessionLocal
    from app.services.accounts import create_owner

    clear_login_limits()
    db = SessionLocal()
    try:
        create_owner(db, "limited@example.test", OWNER["password"])
    finally:
        db.close()
    headers = csrf_headers(client)
    for _ in range(8):
        assert client.post("/api/v1/owner/login", headers=headers, json={
            "email": "limited@example.test", "password": "wrong-password!",
        }).status_code == 401
    blocked = client.post("/api/v1/owner/login", headers=headers, json={
        "email": "limited@example.test", "password": OWNER["password"],
    })
    assert blocked.status_code == 429 and blocked.headers.get("retry-after")
    clear_login_limits()
