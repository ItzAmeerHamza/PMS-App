import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..core.audit import record_audit
from ..core.transaction import business_transaction

TOKEN_DAYS = 14
MIN_PASSWORD_LENGTH = 8
MANAGER_ROLE = "store_manager"

# Argon2id with argon2-cffi's defaults (RFC 9106 low-memory profile).
_hasher = PasswordHasher()


class SetupError(ValueError):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def _verify_legacy_pbkdf2(password: str, stored: str) -> bool:
    """Hashes written before phase 02: ``<hex salt>$<hex digest>``, PBKDF2-SHA256, 120,000 rounds."""
    try:
        salt, digest = stored.split("$", 1)
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(check, digest)


def is_legacy_hash(stored: str) -> bool:
    return not stored.startswith("$argon2")


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if is_legacy_hash(stored):
        return _verify_legacy_pbkdf2(password, stored)
    try:
        return _hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    if is_legacy_hash(stored):
        return True
    try:
        return _hasher.check_needs_rehash(stored)
    except InvalidHashError:
        return True


def validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SetupError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


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


def _new_session(db: Session, staff: models.Staff) -> str:
    token = secrets.token_hex(32)
    db.add(
        models.StaffSession(
            token=token,
            staff_id=staff.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS),
        )
    )
    return token


def login(db: Session, username: str, password: str) -> dict:
    staff = (
        db.query(models.Staff)
        .options(joinedload(models.Staff.pharmacy))
        .filter(models.Staff.username == username.strip())
        .first()
    )
    if not staff or not staff.is_active or not verify_password(password, staff.password_hash):
        with business_transaction(db):
            # No username in the row: it may be a mistyped password.
            record_audit(db, "auth.login_failed", pharmacy_id=staff.pharmacy_id if staff else None, staff_id=None, entity_type="staff")
        raise ValueError("Username or password is incorrect")
    if staff.role != MANAGER_ROLE:
        raise ValueError("This sign-in is for the store manager")
    with business_transaction(db):
        if needs_rehash(staff.password_hash):
            # Explicit upgrade path for PBKDF2 hashes from before phase 02.
            staff.password_hash = hash_password(password)
            record_audit(db, "auth.password_rehashed", pharmacy_id=staff.pharmacy_id, staff_id=staff.id, entity_type="staff")
        token = _new_session(db, staff)
        record_audit(db, "auth.login", pharmacy_id=staff.pharmacy_id, staff_id=staff.id, entity_type="staff")
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
        with business_transaction(db):
            db.delete(session)
        return None
    return session.staff


def logout(db: Session, token: str) -> None:
    session = db.query(models.StaffSession).filter(models.StaffSession.token == token).first()
    if session:
        staff = session.staff
        with business_transaction(db):
            db.delete(session)
            record_audit(db, "auth.logout", pharmacy_id=staff.pharmacy_id if staff else None, staff_id=session.staff_id, entity_type="staff")


def setup_status(db: Session) -> dict:
    pharmacy = db.query(models.Pharmacy).order_by(models.Pharmacy.id).first()
    has_manager = (
        db.query(models.Staff.id).filter(models.Staff.role == MANAGER_ROLE, models.Staff.is_active.is_(True)).first()
        is not None
    )
    # Public endpoint: shop name only, nothing else.
    return {
        "needs_setup": not has_manager,
        "has_pharmacy": pharmacy is not None,
        "pharmacy_name": pharmacy.name if pharmacy else None,
    }


def first_run_setup(db: Session, payload) -> dict:
    """Create the manager (and the pharmacy, if none exists) with a password the manager chose.

    Allowed only while no active manager exists. There is no default account.
    """
    if not setup_status(db)["needs_setup"]:
        raise SetupError("This shop is already set up. Sign in instead.")
    username = payload.username.strip()
    if not username:
        raise SetupError("Choose a username")
    validate_new_password(payload.password)
    if db.query(models.Staff.id).filter(models.Staff.username == username).first():
        raise SetupError("That username is already taken")

    with business_transaction(db):
        pharmacy = db.query(models.Pharmacy).order_by(models.Pharmacy.id).first()
        if pharmacy is None:
            name = (payload.pharmacy_name or "").strip()
            if not name:
                raise SetupError("Enter the pharmacy name")
            pharmacy = models.Pharmacy(
                name=name,
                address=(payload.pharmacy_address or "").strip() or None,
                phone=(payload.pharmacy_phone or "").strip() or None,
                license_number=(payload.license_number or "").strip() or None,
            )
            db.add(pharmacy)
            db.flush()
            record_audit(db, "pharmacy.created", pharmacy_id=pharmacy.id, entity_type="pharmacy", entity_public_id=pharmacy.public_id)
        staff = models.Staff(
            pharmacy_id=pharmacy.id,
            full_name=(payload.full_name or "").strip() or "Store manager",
            username=username,
            password_hash=hash_password(payload.password),
            role=MANAGER_ROLE,
            is_active=True,
        )
        db.add(staff)
        db.flush()
        record_audit(db, "auth.setup", pharmacy_id=pharmacy.id, staff_id=staff.id, entity_type="staff")
        token = _new_session(db, staff)
        record_audit(db, "auth.login", pharmacy_id=pharmacy.id, staff_id=staff.id, entity_type="staff")
    db.refresh(staff)
    return {"token": token, **serialize_staff(staff)}
