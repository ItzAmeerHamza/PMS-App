"""What the desktop indicator shows. No payloads, no device secret."""

from datetime import datetime, timezone

WAITING = {"offline", "timeout", "dns", "connection", "bad_response"}


def is_waiting(code: str | None) -> bool:
    if not code:
        return False
    if code in WAITING or code == "http_429":
        return True
    return code.startswith("http_5")


def indicator(*, activated: bool, busy: bool, pending: int, failed: int, last_error: str | None) -> str:
    if not activated:
        return "not_activated"
    if busy:
        return "syncing"
    if failed or (last_error and not is_waiting(last_error)):
        return "error"
    if is_waiting(last_error):
        return "waiting"
    if pending:
        return "syncing"
    return "synced"


def as_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
