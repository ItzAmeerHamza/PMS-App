"""Login rate limit, CSRF for cookie-authenticated owner mutations, session cookie.

The rate limit is per process. One Railway replica is the current deployment
shape. A restart clears the counters; it does not unlock a session.
"""

import hmac
import secrets
import threading
import time

from fastapi import HTTPException, Request, Response

from ..config import get_settings

CSRF_COOKIE = "pharmacare_csrf"
SESSION_COOKIE = "pharmacare_owner"
CSRF_HEADER = "x-csrf-token"
_WINDOW_SECONDS = 15 * 60
_MAX_FAILURES = 8
_lock = threading.Lock()
_failures: dict[str, list[float]] = {}


def clear_login_limits() -> None:
    with _lock:
        _failures.clear()


def note_login_failure(email: str) -> None:
    key = email.strip().lower()
    now = time.monotonic()
    with _lock:
        recent = [stamp for stamp in _failures.get(key, []) if now - stamp < _WINDOW_SECONDS]
        recent.append(now)
        _failures[key] = recent


def ensure_login_allowed(email: str) -> None:
    key = email.strip().lower()
    now = time.monotonic()
    with _lock:
        recent = [stamp for stamp in _failures.get(key, []) if now - stamp < _WINDOW_SECONDS]
        _failures[key] = recent
        blocked = len(recent) >= _MAX_FAILURES
    if blocked:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later.",
                            headers={"Retry-After": str(_WINDOW_SECONDS)})


def new_csrf() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE, token, httponly=False, secure=get_settings().cookie_secure,
        samesite="lax", max_age=12 * 3600, path="/",
    )


def require_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or len(cookie) != len(header) or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF check failed")


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, secure=get_settings().cookie_secure,
        samesite="lax", max_age=get_settings().owner_session_hours * 3600, path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def session_token(request: Request) -> str:
    """Cookie first, then Authorization. An empty string means anonymous."""
    return request.cookies.get(SESSION_COOKIE, "") or ""
