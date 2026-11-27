"""Manager-facing sync status, activation, and a manual cycle. The secret is never returned."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from .secrets import CredentialError, read_credential
from .service import activate, diagnostics, snapshot
from .worker import get_worker

router = APIRouter(prefix="/sync", tags=["sync"])


class ActivateIn(BaseModel):
    device_token: str
    cloud_api_url: str | None = None


def _busy() -> bool:
    return get_worker().busy


@router.get("/status")
def sync_status(db: Session = Depends(get_db)):
    return snapshot(db, busy=_busy())


@router.get("/diagnostics")
def sync_diagnostics(db: Session = Depends(get_db)):
    return diagnostics(db, busy=_busy())


@router.post("/activate")
def sync_activate(body: ActivateIn, db: Session = Depends(get_db)):
    try:
        return activate(db, body.device_token, body.cloud_api_url)
    except CredentialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/run")
def sync_now(db: Session = Depends(get_db)):
    """One upload cycle. Sales and the rest of the API are not held for this."""
    if read_credential() is None:
        raise HTTPException(status_code=400, detail="This shop is not activated yet.")
    try:
        return get_worker().run_once(force=True)
    except CredentialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
