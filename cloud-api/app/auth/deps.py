"""Request authentication.

- `require_device`: for POST /sync/push only. The shop comes from the device.
- `require_owner`: for /admin/*. Device tokens are refused with 403, anonymous with 401.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models
from ..models.db import get_db
from . import tokens


@dataclass
class DeviceIdentity:
    device_id: object
    shop_id: object


def require_device(request: Request, db: Session = Depends(get_db)) -> DeviceIdentity:
    parsed = tokens.parse_device_token(tokens.bearer(request.headers.get("authorization")))
    if parsed is None:
        raise HTTPException(status_code=401, detail="Device credential required")
    device_id, secret = parsed
    device = db.get(models.ShopDevice, device_id)
    if device is None or device.revoked_at is not None or not tokens.secret_matches(secret, device.secret_hash):
        raise HTTPException(status_code=401, detail="Unknown or revoked device")
    shop = db.get(models.Shop, device.shop_id)
    if shop is None or shop.disabled_at is not None:
        raise HTTPException(status_code=401, detail="Unknown or revoked device")
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return DeviceIdentity(device_id=device.id, shop_id=device.shop_id)


def require_owner(request: Request, db: Session = Depends(get_db)) -> models.Owner:
    from .guard import SESSION_COOKIE, require_csrf

    cookie = request.cookies.get(SESSION_COOKIE, "")
    header = tokens.bearer(request.headers.get("authorization"))
    # A bearer token is the server-to-server path (the dashboard, and tests).
    # A cookie alone is a browser call and mutations must pass the CSRF check.
    token = header or cookie
    if not token:
        raise HTTPException(status_code=401, detail="Owner sign-in required")
    if token.startswith(tokens.DEVICE_PREFIX):
        raise HTTPException(status_code=403, detail="Device credentials cannot call admin routes")
    if not header and cookie and request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_csrf(request)
    session = db.get(models.OwnerSession, tokens.sha256_hex(token))
    now = datetime.now(timezone.utc)
    if session is None or session.expires_at < now:
        raise HTTPException(status_code=401, detail="Owner sign-in required")
    owner = db.get(models.Owner, session.owner_id)
    if owner is None or not owner.is_active:
        raise HTTPException(status_code=401, detail="Owner sign-in required")
    return owner
