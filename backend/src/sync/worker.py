"""Background upload of the local outbox. One worker, no overlap, never blocks a sale.

A cycle:
1. If a device credential is stored, make sure bootstrap is running.
2. Emit the next chunk of bootstrap events (rows that predate the outbox).
3. If any bootstrap event is still unsent, upload only those. Live events wait,
   so a prescription cannot be uploaded before the patient it depends on has
   been offered to the cloud.
4. Otherwise upload the next live prefix, in sequence, stopping before an event
   that is not due yet.
5. Mark applied and already_processed as synced. Mark invalid_event as failed.
   Leave everything else pending. A timeout or a lost response changes nothing
   on the event, so the next send is safe.

The default pace is every 5 minutes, 100 events, 30 second timeout. Override with
PHARMACARE_SYNC_INTERVAL_SECONDS, PHARMACARE_SYNC_BATCH_SIZE, and
PHARMACARE_SYNC_TIMEOUT_SECONDS. The shop keeps working when no cloud is configured.
"""

import logging
import os
import random
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from .. import models
from ..core.database import SessionLocal
from ..core.outbox import acknowledge, has_unsent, list_ready_prefix, note_error, record_error, retry_delay, serialize_event
from .bootstrap import advance_bootstrap
from .secrets import cloud_base_url, read_credential
from .status import is_waiting
from .transport import HttpTransport, TransportError

log = logging.getLogger("pharmacare.sync")

_worker: "SyncWorker | None" = None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _now(value: datetime | None) -> datetime:
    return _naive(value) or datetime.now(timezone.utc).replace(tzinfo=None)


def delay_seconds(attempt: int, retry_after: float | None, rng: random.Random) -> float:
    """Honor Retry-After when the server sends one. Otherwise half-to-full exponential backoff."""
    if retry_after is not None:
        return min(max(retry_after, 0.0), 3600.0)
    base = float(retry_delay(max(attempt, 1)))
    return base * 0.5 + rng.random() * (base * 0.5)


class SyncWorker:
    def __init__(
        self,
        transport=None,
        *,
        interval: int | None = None,
        batch_size: int | None = None,
        timeout: float | None = None,
        bootstrap_chunk: int = 200,
        rng: random.Random | None = None,
    ):
        self.transport = transport or HttpTransport()
        self.interval = interval if interval is not None else _env_int("PHARMACARE_SYNC_INTERVAL_SECONDS", 300)
        self.batch_size = batch_size if batch_size is not None else _env_int("PHARMACARE_SYNC_BATCH_SIZE", 100)
        self.timeout = timeout if timeout is not None else _env_float("PHARMACARE_SYNC_TIMEOUT_SECONDS", 30.0)
        self.bootstrap_chunk = bootstrap_chunk
        self.rng = rng or random.Random()
        self.busy = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="pharmacare-sync", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                log.exception("Sync cycle failed")
            if self._stop.wait(max(self.interval, 1)):
                return

    def run_once(self, *, now: datetime | None = None, force: bool = False) -> dict:
        if not self._lock.acquire(blocking=False):
            return {"skipped": "overlap"}
        self.busy = True
        try:
            return self._cycle(_now(now), force)
        finally:
            self.busy = False
            self._lock.release()

    def _cycle(self, now: datetime, force: bool) -> dict:
        from .service import snapshot

        db = SessionLocal()
        try:
            pharmacy = db.query(models.Pharmacy).order_by(models.Pharmacy.id).first()
            token = read_credential()
            if pharmacy is None or not token:
                return snapshot(db, busy=False)
            state = _ensure_state(db, pharmacy, now)
            if not force and state.backoff_until is not None and _naive(state.backoff_until) > now:
                return snapshot(db, busy=False)
            advance_bootstrap(db, chunk=self.bootstrap_chunk)
            db.refresh(state)
            url = cloud_base_url(state.cloud_api_url)
            if not url:
                _remember(state, "cloud_not_configured", now)
                state.backoff_until = None
                db.commit()
                return snapshot(db, busy=False)
            origin = "bootstrap" if has_unsent(db, "bootstrap") or state.bootstrap_status == "running" else "live"
            if origin == "bootstrap" and not has_unsent(db, "bootstrap"):
                # Bootstrap is still scanning, but this chunk emitted nothing to send.
                return snapshot(db, busy=False)
            events = list_ready_prefix(db, limit=self.batch_size, now=now, origin=origin)
            if not events:
                if origin == "live" and not has_unsent(db, "live") and state.last_error and is_waiting(state.last_error):
                    state.last_error = None
                    state.last_error_at = None
                    state.backoff_until = None
                    state.backoff_attempt = 0
                    db.commit()
                return snapshot(db, busy=False)
            from .service import outbox_report

            body = {"events": [serialize_event(row) for row in events], "outbox": outbox_report(db)}
            try:
                response = self.transport.push(url, token, body, self.timeout)
            except TransportError as exc:
                attempt = (state.backoff_attempt or 0) + 1
                wait = delay_seconds(attempt, exc.retry_after, self.rng)
                state.backoff_attempt = attempt
                state.backoff_until = now + timedelta(seconds=wait)
                _remember(state, exc.code, now)
                db.commit()
                log.info("sync push failed shop=%s code=%s retry_in=%s", pharmacy.public_id, exc.code, round(wait))
                return snapshot(db, busy=False)
            self._apply(db, state, events, response, now)
            log.info("sync push shop=%s events=%s", pharmacy.public_id, len(events))
            return snapshot(db, busy=False)
        finally:
            db.close()

    def _apply(self, db, state, events, response: dict, now: datetime) -> None:
        by_id = {}
        for item in response.get("results") or []:
            if isinstance(item, dict) and isinstance(item.get("event_id"), str):
                by_id[item["event_id"]] = item
        acked = []
        block = None
        for event in events:
            item = by_id.get(event.event_id)
            if not isinstance(item, dict):
                block = block or "bad_response"
                continue
            result = item.get("result")
            code = str(item.get("code") or result or "unknown")
            if result in ("applied", "already_processed"):
                acked.append({"event_id": event.event_id, "result": result})
            elif result == "invalid_event":
                record_error(db, event.event_id, f"invalid_event:{code}"[:255], retryable=False, now=now)
            elif result in ("ordering_conflict", "retryable_error"):
                note_error(db, event.event_id, f"{result}:{code}"[:255])
                block = block or f"{result}:{code}"[:255]
            else:
                note_error(db, event.event_id, "unexpected_result")
                block = block or "unexpected_result"
        if acked:
            highest = max(event.sequence for event in events if event.event_id in {item["event_id"] for item in acked})
            previous = state.last_acknowledged_sequence or 0
            state.last_acknowledged_sequence = max(previous, highest)
        state.last_success_at = now
        state.backoff_attempt = 0
        state.backoff_until = None
        failed = db.query(func.count()).select_from(models.SyncOutbox).filter(models.SyncOutbox.status == "failed").scalar()
        if block:
            _remember(state, block, now)
        elif failed:
            _remember(state, "invalid_event", now)
        else:
            state.last_error = None
            state.last_error_at = None
        if acked:
            acknowledge(db, acked, now=now)
        else:
            db.commit()


def _remember(state, code: str, now: datetime) -> None:
    state.last_error = (code or "")[:255]
    state.last_error_at = now


def _ensure_state(db, pharmacy, now: datetime):
    state = db.get(models.SyncState, pharmacy.id)
    if state is None:
        state = models.SyncState(pharmacy_id=pharmacy.id)
        db.add(state)
    if state.activated_at is None:
        state.activated_at = now
    # None means the row was just created and the column default is not applied yet.
    if state.bootstrap_status in (None, "not_started"):
        state.bootstrap_status = "running"
        state.bootstrap_stage = "products"
        state.bootstrap_cursor = 0
    db.commit()
    return state


def get_worker() -> SyncWorker:
    global _worker
    if _worker is None:
        _worker = SyncWorker()
    return _worker


def autostart_enabled() -> bool:
    return os.environ.get("PHARMACARE_SYNC_AUTOSTART", "1").lower() not in {"0", "false", "no"}
