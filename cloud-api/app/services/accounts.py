"""Owners, shops, and device credentials."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth import tokens
from ..config import get_settings
from ..sync.service import ensure_state_row

MIN_OWNER_PASSWORD = 12


class AccountError(ValueError):
    pass


def audit(db: Session, action: str, *, actor_type: str, actor_id=None, shop_id=None, entity_type=None, entity_id=None):
    db.add(models.AuditLog(action=action, actor_type=actor_type, actor_id=str(actor_id) if actor_id else None,
                           shop_id=shop_id, entity_type=entity_type, entity_id=str(entity_id) if entity_id else None))


def create_owner(db: Session, email: str, password: str) -> models.Owner:
    email = email.strip().lower()
    if "@" not in email:
        raise AccountError("Enter a valid email address")
    if len(password) < MIN_OWNER_PASSWORD:
        raise AccountError(f"Owner password must be at least {MIN_OWNER_PASSWORD} characters")
    if db.scalars(select(models.Owner).where(models.Owner.email == email)).first():
        raise AccountError("An owner with this email already exists")
    owner = models.Owner(email=email, password_hash=tokens.hash_password(password))
    db.add(owner)
    db.flush()
    audit(db, "owner.created", actor_type="system", entity_type="owner", entity_id=owner.id)
    db.commit()
    return owner


CHALLENGE_MINUTES = 5
CHALLENGE_ATTEMPTS = 5


def owner_login(db: Session, email: str, password: str) -> dict:
    """Password check only. A session starts after confirm_totp, not here."""
    from ..auth import totp

    email = email.strip().lower()
    owner = db.scalars(select(models.Owner).where(models.Owner.email == email)).first()
    if owner is None or not owner.is_active or not tokens.verify_password(password, owner.password_hash):
        audit(db, "owner.login_failed", actor_type="owner")
        db.commit()
        raise AccountError("Email or password is incorrect")
    raw = tokens.new_owner_token()[0]
    expires = datetime.now(timezone.utc) + timedelta(minutes=CHALLENGE_MINUTES)
    purpose = "totp" if owner.totp_secret else "enroll"
    pending = None if owner.totp_secret else totp.new_secret()
    db.add(models.OwnerChallenge(
        token_hash=tokens.sha256_hex(raw), owner_id=owner.id, purpose=purpose,
        pending_secret=pending, expires_at=expires,
    ))
    audit(db, "owner.password_ok", actor_type="owner", actor_id=owner.id)
    db.commit()
    body = {"status": purpose, "challenge": raw, "expires_at": expires}
    if pending:
        body["secret"] = pending
        body["otpauth_uri"] = totp.provisioning_uri(email, pending)
    return body


def confirm_totp(db: Session, challenge: str, code: str) -> tuple[str, datetime]:
    """Turn a password-ok challenge into a session. Wrong codes do not start one."""
    from ..auth import totp

    row = db.get(models.OwnerChallenge, tokens.sha256_hex(challenge or ""))
    now = datetime.now(timezone.utc)
    if row is None or row.expires_at < now or row.attempts >= CHALLENGE_ATTEMPTS:
        raise AccountError("That sign-in step has expired. Start again.")
    owner = db.get(models.Owner, row.owner_id)
    secret = row.pending_secret if row.purpose == "enroll" else (owner.totp_secret if owner else None)
    if owner is None or not owner.is_active or not secret or not totp.code_matches(secret, code):
        row.attempts += 1
        audit(db, "owner.totp_failed", actor_type="owner", actor_id=row.owner_id)
        db.commit()
        raise AccountError("The authentication code is incorrect")
    if row.purpose == "enroll":
        owner.totp_secret = secret
    db.delete(row)
    token, token_hash = tokens.new_owner_token()
    expires = now + timedelta(hours=get_settings().owner_session_hours)
    db.add(models.OwnerSession(token_hash=token_hash, owner_id=owner.id, expires_at=expires))
    audit(db, "owner.login", actor_type="owner", actor_id=owner.id)
    db.commit()
    return token, expires


def owner_logout(db: Session, token: str) -> None:
    session = db.get(models.OwnerSession, tokens.sha256_hex(token))
    if session:
        db.delete(session)
        db.commit()


def register_shop(db: Session, owner: models.Owner, shop_id: uuid.UUID, name: str) -> models.Shop:
    """shop_id is the desktop pharmacy's public_id (shown on the desktop during activation)."""
    if db.get(models.Shop, shop_id) is not None:
        raise AccountError("This shop is already registered")
    shop = models.Shop(id=shop_id, name=name.strip())
    db.add(shop)
    db.flush()
    ensure_state_row(db, shop_id)
    audit(db, "shop.registered", actor_type="owner", actor_id=owner.id, shop_id=shop_id, entity_type="shop", entity_id=shop_id)
    db.commit()
    return shop


def issue_device(db: Session, owner: models.Owner, shop_id: uuid.UUID, label: str | None) -> tuple[models.ShopDevice, str]:
    """Returns the device and its token. The token is shown once; only its hash is stored."""
    shop = db.get(models.Shop, shop_id)
    if shop is None or shop.disabled_at is not None:
        raise AccountError("Shop not found")
    device_id = uuid.uuid4()
    token, secret_hash = tokens.new_device_token(device_id)
    device = models.ShopDevice(id=device_id, shop_id=shop_id, label=(label or "").strip() or None, secret_hash=secret_hash)
    db.add(device)
    audit(db, "device.issued", actor_type="owner", actor_id=owner.id, shop_id=shop_id, entity_type="device", entity_id=device_id)
    db.commit()
    return device, token


def revoke_device(db: Session, owner: models.Owner, device_id: uuid.UUID) -> models.ShopDevice:
    device = db.get(models.ShopDevice, device_id)
    if device is None:
        raise AccountError("Device not found")
    if device.revoked_at is None:
        device.revoked_at = datetime.now(timezone.utc)
        audit(db, "device.revoked", actor_type="owner", actor_id=owner.id, shop_id=device.shop_id,
              entity_type="device", entity_id=device_id)
        db.commit()
    return device
