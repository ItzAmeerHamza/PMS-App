"""Owner-only routes. Business data is read-only here; shops and devices can be managed."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..auth.deps import require_owner
from ..auth.guard import clear_session_cookie, new_csrf, note_login_failure, require_csrf, set_csrf_cookie, set_session_cookie, session_token, ensure_login_allowed
from ..models.db import get_db
from ..services import accounts, admin_reads

router = APIRouter(prefix="/admin", tags=["admin"])
auth_router = APIRouter(prefix="/owner", tags=["owner"])

Limit = Query(50, ge=1, le=200)
Offset = Query(0, ge=0)


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=256)


class TotpIn(BaseModel):
    challenge: str = Field(min_length=10, max_length=200)
    code: str = Field(min_length=6, max_length=8)


@auth_router.get("/csrf")
def csrf(response: Response):
    token = new_csrf()
    set_csrf_cookie(response, token)
    return {"token": token}


@auth_router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    require_csrf(request)
    ensure_login_allowed(body.email)
    try:
        return accounts.owner_login(db, body.email, body.password)
    except accounts.AccountError as exc:
        note_login_failure(body.email)
        raise HTTPException(status_code=401, detail=str(exc)) from None


@auth_router.post("/totp")
def totp(body: TotpIn, request: Request, response: Response, db: Session = Depends(get_db)):
    require_csrf(request)
    try:
        token, expires = accounts.confirm_totp(db, body.challenge, body.code)
    except accounts.AccountError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None
    set_session_cookie(response, token)
    # The token is for the dashboard server, which stores it in its own cookie.
    # The browser page must not receive this JSON.
    return {"expires_at": expires, "token": token}


@auth_router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db), owner: models.Owner = Depends(require_owner)):
    from ..auth import tokens

    accounts.owner_logout(db, tokens.bearer(request.headers.get("authorization")) or session_token(request))
    clear_session_cookie(response)


class ShopIn(BaseModel):
    shop_id: uuid.UUID = Field(description="The desktop pharmacy public_id")
    name: str = Field(min_length=1, max_length=255)


class DeviceIn(BaseModel):
    label: str | None = Field(default=None, max_length=120)


@router.post("/shops", status_code=201)
def register_shop(body: ShopIn, db: Session = Depends(get_db), owner: models.Owner = Depends(require_owner)):
    try:
        shop = accounts.register_shop(db, owner, body.shop_id, body.name)
    except accounts.AccountError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"id": str(shop.id), "name": shop.name}


@router.post("/shops/{shop_id}/devices", status_code=201)
def issue_device(shop_id: uuid.UUID, body: DeviceIn, db: Session = Depends(get_db),
                 owner: models.Owner = Depends(require_owner)):
    try:
        device, token = accounts.issue_device(db, owner, shop_id, body.label)
    except accounts.AccountError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    # The token is returned once. Only its hash is stored.
    return {"device_id": str(device.id), "shop_id": str(shop_id), "token": token}


@router.post("/devices/{device_id}/revoke")
def revoke_device(device_id: uuid.UUID, db: Session = Depends(get_db), owner: models.Owner = Depends(require_owner)):
    try:
        device = accounts.revoke_device(db, owner, device_id)
    except accounts.AccountError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"device_id": str(device.id), "revoked_at": device.revoked_at}


@router.get("/shops")
def list_shops(limit: int = Limit, offset: int = Offset, db: Session = Depends(get_db), owner=Depends(require_owner)):
    return admin_reads.shops(db, limit, offset)


@router.get("/overview")
def overview(shop_id: uuid.UUID | None = None, db: Session = Depends(get_db), owner=Depends(require_owner)):
    return admin_reads.overview(db, shop_id)


@router.get("/inventory")
def inventory(shop_id: uuid.UUID | None = None, search: str | None = None, low_stock: bool = False,
              limit: int = Limit, offset: int = Offset, db: Session = Depends(get_db), owner=Depends(require_owner)):
    return admin_reads.inventory(db, shop_id, limit, offset, search, low_stock)


@router.get("/inventory/{public_id}")
def inventory_detail(public_id: uuid.UUID, shop_id: uuid.UUID, date_from: str | None = None, date_to: str | None = None,
                     db: Session = Depends(get_db), owner=Depends(require_owner)):
    row = admin_reads.product_detail(db, shop_id, public_id, _day(date_from), _day(date_to))
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return row


@router.get("/patients")
def patients(shop_id: uuid.UUID | None = None, search: str | None = None, limit: int = Limit, offset: int = Offset,
             db: Session = Depends(get_db), owner=Depends(require_owner)):
    return admin_reads.patients(db, shop_id, limit, offset, search)


@router.get("/patients/{public_id}")
def patient_detail(public_id: uuid.UUID, shop_id: uuid.UUID, db: Session = Depends(get_db), owner=Depends(require_owner)):
    row = admin_reads.patient_detail(db, shop_id, public_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return row


@router.get("/prescriptions")
def prescriptions(shop_id: uuid.UUID | None = None, search: str | None = None,
                  date_from: str | None = None, date_to: str | None = None,
                  limit: int = Limit, offset: int = Offset, db: Session = Depends(get_db), owner=Depends(require_owner)):
    return admin_reads.prescriptions(db, shop_id, limit, offset, search, _day(date_from), _day(date_to))


@router.get("/movements")
def movements(shop_id: uuid.UUID | None = None, product_id: uuid.UUID | None = None,
              date_from: str | None = None, date_to: str | None = None,
              limit: int = Limit, offset: int = Offset, db: Session = Depends(get_db), owner=Depends(require_owner)):
    return admin_reads.movements(db, shop_id, limit, offset, product_id, _day(date_from), _day(date_to))


def _day(value: str | None):
    if not value:
        return None
    from datetime import date
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Use a date as YYYY-MM-DD") from None


@router.get("/sync-status")
def sync_status(shop_id: uuid.UUID | None = None, limit: int = Limit, offset: int = Offset,
                db: Session = Depends(get_db), owner=Depends(require_owner)):
    return admin_reads.sync_status(db, shop_id, limit, offset)
