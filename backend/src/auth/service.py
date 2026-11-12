import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, joinedload

from .. import models

MANAGER_USERNAME = "manager"
MANAGER_PASSWORD = "store123"
TOKEN_DAYS = 14


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(check, digest)


def serialize_staff(staff: models.Staff) -> dict:
    pharmacy = staff.pharmacy
    return {
        "id": staff.id,
        "full_name": staff.full_name,
        "username": staff.username,
        "role": staff.role,
        "pharmacy": {
            "id": pharmacy.id,
            "name": pharmacy.name,
            "address": pharmacy.address,
            "phone": pharmacy.phone,
            "license_number": pharmacy.license_number,
        },
    }


def login(db: Session, username: str, password: str) -> dict:
    staff = (
        db.query(models.Staff)
        .options(joinedload(models.Staff.pharmacy))
        .filter(models.Staff.username == username.strip())
        .first()
    )
    if not staff or not staff.is_active or not verify_password(password, staff.password_hash):
        raise ValueError("Username or password is incorrect")
    if staff.role != "store_manager":
        raise ValueError("This sign-in is for the store manager")
    token = secrets.token_hex(32)
    db.add(
        models.StaffSession(
            token=token,
            staff_id=staff.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS),
        )
    )
    db.commit()
    return {"token": token, **serialize_staff(staff)}


def staff_from_token(db: Session, token: str) -> models.Staff | None:
    session = (
        db.query(models.StaffSession)
        .options(joinedload(models.StaffSession.staff).joinedload(models.Staff.pharmacy))
        .filter(models.StaffSession.token == token)
        .first()
    )
    if not session or not session.staff or not session.staff.is_active:
        return None
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        return None
    return session.staff


def logout(db: Session, token: str) -> None:
    session = db.query(models.StaffSession).filter(models.StaffSession.token == token).first()
    if session:
        db.delete(session)
        db.commit()


def ensure_store_manager(db: Session) -> None:
    pharmacy = db.query(models.Pharmacy).order_by(models.Pharmacy.id).first()
    if not pharmacy:
        return
    existing = db.query(models.Staff).filter(models.Staff.username == MANAGER_USERNAME).first()
    if existing:
        return
    db.add(
        models.Staff(
            pharmacy_id=pharmacy.id,
            full_name="Store manager",
            username=MANAGER_USERNAME,
            password_hash=hash_password(MANAGER_PASSWORD),
            role="store_manager",
            is_active=True,
        )
    )
    db.commit()
