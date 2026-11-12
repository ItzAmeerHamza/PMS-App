from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/auth", tags=["auth"])


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    return header.split(" ", 1)[1].strip()


@router.post("/login", response_model=schemas.LoginOut)
def login(payload: schemas.LoginIn, db: Session = Depends(get_db)):
    try:
        return service.login(db, payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.get("/me", response_model=schemas.StaffOut)
def me(request: Request, db: Session = Depends(get_db)):
    staff = service.staff_from_token(db, _bearer_token(request))
    if not staff:
        raise HTTPException(status_code=401, detail="Sign in required")
    return service.serialize_staff(staff)


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("authorization", "")
    if token.lower().startswith("bearer "):
        service.logout(db, token.split(" ", 1)[1].strip())
