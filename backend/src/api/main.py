from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import models  # noqa: F401
from ..auth.router import router as auth_router
from ..auth.service import ensure_store_manager, staff_from_token
from ..core.config import settings
from ..core.database import SessionLocal, ensure_schema
from ..dashboard.router import router as dashboard_router
from ..inventory.router import router as inventory_router
from ..patients.router import router as patient_router
from ..pharmacies.router import router as pharmacy_router
from ..prescriptions.router import router as prescription_router
from ..seed import backfill_medicine_details, backfill_visit_details, seed_if_empty

app = FastAPI(
    title=settings.app_name,
    description="Pharmacy inventory and prescription API for the PharmaCare desktop app.",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json", "/api/v1/auth/login"}


@app.middleware("http")
async def require_store_manager(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in PUBLIC_PATHS or path.startswith("/docs"):
        return await call_next(request)
    if not path.startswith("/api/v1"):
        return await call_next(request)
    header = request.headers.get("authorization", "")
    token = header.split(" ", 1)[1].strip() if header.lower().startswith("bearer ") else ""
    db = SessionLocal()
    try:
        staff = staff_from_token(db, token) if token else None
    finally:
        db.close()
    if not staff:
        response = JSONResponse(status_code=401, content={"detail": "Sign in required"})
        response.headers["Access-Control-Allow-Origin"] = request.headers.get("origin", "*")
        return response
    return await call_next(request)


app.include_router(auth_router, prefix="/api/v1")
app.include_router(pharmacy_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(patient_router, prefix="/api/v1")
app.include_router(prescription_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")


@app.on_event("startup")
def on_startup():
    ensure_schema()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        backfill_medicine_details(db)
        backfill_visit_details(db)
        ensure_store_manager(db)
    finally:
        db.close()


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
