"""PharmaCare cloud API (Railway). Receives shop sync events; serves owner read APIs."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, sync
from .config import get_settings


class _StripQueryString(logging.Filter):
    """Access logs keep method, path, and status only (no query strings)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "?" in args[2]:
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(_StripQueryString())

# App logs (push summaries, apply failures) at INFO on stderr. They carry ids and counts only.
_app_log = logging.getLogger("pharmacare")
if not _app_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    _app_log.addHandler(_handler)
    _app_log.setLevel(logging.INFO)

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", docs_url="/docs", redoc_url=None)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"])

app.include_router(sync.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(admin.auth_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
