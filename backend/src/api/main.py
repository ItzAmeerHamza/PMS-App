import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import models  # noqa: F401
from ..auth.router import router as auth_router
from ..auth.service import staff_from_token
from ..billing.router import router as billing_router
from ..core.config import settings
from ..core.database import SessionLocal, get_engine
from ..core.migrate import run_migrations
from ..dashboard.router import router as dashboard_router
from ..inventory.router import router as inventory_router
from ..patients.router import router as patient_router
from ..pharmacies.router import router as pharmacy_router
from ..prescriptions.router import router as prescription_router
from ..sync.router import router as sync_router
from ..sync.worker import autostart_enabled, get_worker

log = logging.getLogger("pharmacare")


class _StripQueryString(logging.Filter):
    """Access logs keep method, path, and status, but never the query string.

    Searches put patient names and phone numbers in the query (?search=...).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "?" in args[2]:
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(_StripQueryString())


def demo_data_enabled() -> bool:
    return os.environ.get("PHARMACARE_DEMO_DATA", "").lower() in {"1", "true", "yes"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    result = run_migrations(get_engine())
    if result["from"] != result["to"]:
        log.info("Database migrated from %s to %s", result["from"] or "empty", result["to"])
    if demo_data_enabled():
        from ..seed import seed_if_empty

        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    worker = get_worker() if autostart_enabled() else None
    if worker is not None:
        worker.start()
    try:
        yield
    finally:
        if worker is not None:
            worker.stop()


app = FastAPI(
    title=settings.app_name,
    description="Pharmacy inventory and prescription API for the PharmaCare desktop app.",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATHS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/setup",
}


@app.middleware("http")
async def require_store_manager(request: Request, call_next):
    path = request.url.path
    request.state.staff_id = None
    request.state.pharmacy_id = None
    if request.method == "OPTIONS" or path in PUBLIC_PATHS or path.startswith("/docs"):
        return await call_next(request)
    if not path.startswith("/api/v1"):
        return await call_next(request)
    header = request.headers.get("authorization", "")
    token = header.split(" ", 1)[1].strip() if header.lower().startswith("bearer ") else ""
    db = SessionLocal()
    try:
        staff = staff_from_token(db, token) if token else None
        staff_id = staff.id if staff else None
        pharmacy_id = staff.pharmacy_id if staff else None
    finally:
        db.close()
    if not staff_id:
        response = JSONResponse(status_code=401, content={"detail": "Sign in required"})
        response.headers["Access-Control-Allow-Origin"] = request.headers.get("origin", "*")
        return response
    request.state.staff_id = staff_id
    request.state.pharmacy_id = pharmacy_id
    return await call_next(request)


app.include_router(auth_router, prefix="/api/v1")
app.include_router(pharmacy_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(patient_router, prefix="/api/v1")
app.include_router(prescription_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")
app.include_router(sync_router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
