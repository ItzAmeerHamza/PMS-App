"""POST /sync/push processing.

Each event gets its own transaction:

    lock the shop's synchronization_state row (serializes applies per shop)
    -> already in processed_sync_events?  -> already_processed
    -> validate schema version 1          -> invalid_event
    -> body shop_id == device's shop?     -> invalid_event
    -> version / dependency rules         -> ordering_conflict
    -> apply, insert processed row, commit -> applied

Batch rule: events are handled in `sequence` order. After the first
`ordering_conflict` or `retryable_error`, the remaining events are not applied and
come back as `retryable_error` / `blocked_by_earlier_event`, so a dependent event
can never be applied ahead of the one it depends on. `invalid_event` does not
block: it will never succeed, and the shop marks it failed for diagnosis.
Results are returned only after every commit.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .. import models
from ..models.db import SessionLocal, get_engine
from . import schemas
from .apply import APPLY, OrderingConflict

log = logging.getLogger("pharmacare.cloud.sync")

APPLIED = "applied"
ALREADY = "already_processed"
RETRYABLE = "retryable_error"
CONFLICT = "ordering_conflict"
INVALID = "invalid_event"


def _result(raw, result: str, code: str | None = None) -> dict:
    event_id = raw.get("event_id") if isinstance(raw, dict) else None
    out = {"event_id": event_id if isinstance(event_id, str) else None, "result": result}
    if code:
        out["code"] = code
    return out


def _sequence_key(raw) -> tuple[int, int]:
    sequence = raw.get("sequence") if isinstance(raw, dict) else None
    return (0, sequence) if isinstance(sequence, int) else (1, 0)


def ensure_state_row(db: Session, shop_id: uuid.UUID) -> None:
    db.execute(insert(models.SynchronizationState).values(shop_id=shop_id).on_conflict_do_nothing())


def _lock_state(db: Session, shop_id: uuid.UUID) -> models.SynchronizationState:
    ensure_state_row(db, shop_id)
    return db.scalars(
        select(models.SynchronizationState).where(models.SynchronizationState.shop_id == shop_id).with_for_update()
    ).one()


def _already_processed(db: Session, shop_id: uuid.UUID, event_id) -> bool:
    return db.scalars(
        select(models.ProcessedSyncEvent.id).where(
            models.ProcessedSyncEvent.shop_id == shop_id, models.ProcessedSyncEvent.event_id == event_id
        )
    ).first() is not None


def process_one(raw, shop_id: uuid.UUID, device_id: uuid.UUID) -> dict:
    db = SessionLocal()
    try:
        state = _lock_state(db, shop_id)
        try:
            event = schemas.parse_envelope(raw)
        except schemas.InvalidEvent as exc:
            state.last_result, state.last_error_code = INVALID, exc.code
            db.commit()
            return _result(raw, INVALID, exc.code)
        if _already_processed(db, shop_id, event.event_id):
            db.commit()
            return _result(raw, ALREADY)
        try:
            if event.shop_id != shop_id:
                raise schemas.InvalidEvent("shop_id_mismatch")
            payload = schemas.parse_payload(event)
            APPLY[event.entity_type](db, shop_id, event, payload)
            db.add(models.ProcessedSyncEvent(
                shop_id=shop_id, event_id=event.event_id, sequence=event.sequence, entity_type=event.entity_type,
                entity_id=event.entity_id, operation=event.operation, entity_version=event.entity_version,
                device_id=device_id,
            ))
            db.flush()
        except schemas.InvalidEvent as exc:
            db.rollback()
            _record(db, shop_id, INVALID, exc.code)
            return _result(raw, INVALID, exc.code)
        except OrderingConflict as exc:
            db.rollback()
            _record(db, shop_id, CONFLICT, exc.code)
            return _result(raw, CONFLICT, exc.code)
        except IntegrityError:
            # A concurrent request committed the same event_id first.
            db.rollback()
            if _already_processed(db, shop_id, event.event_id):
                return _result(raw, ALREADY)
            _record(db, shop_id, CONFLICT, "constraint_violation")
            return _result(raw, CONFLICT, "constraint_violation")
        now = datetime.now(timezone.utc)
        state.last_sync_at = now
        state.last_applied_sequence = max(state.last_applied_sequence or 0, event.sequence)
        state.events_applied = (state.events_applied or 0) + 1
        state.last_result, state.last_error_code, state.last_device_id = APPLIED, None, device_id
        db.commit()
        return _result(raw, APPLIED)
    except OperationalError:
        db.rollback()
        log.warning("Database unavailable while applying an event for shop %s", shop_id)
        return _result(raw, RETRYABLE, "database_unavailable")
    except Exception:
        # Unexpected failure mid-apply: nothing partial is kept. Logged without the payload.
        db.rollback()
        log.exception("Failed to apply an event for shop %s", shop_id)
        return _result(raw, RETRYABLE, "internal_error")
    finally:
        db.close()


def _record(db: Session, shop_id: uuid.UUID, result: str, code: str) -> None:
    state = _lock_state(db, shop_id)
    state.last_result, state.last_error_code = result, code[:64]
    db.commit()


def process_push(raw_events: list, shop_id: uuid.UUID, device_id: uuid.UUID, report: dict | None = None) -> list[dict]:
    get_engine()
    ordered = sorted(range(len(raw_events)), key=lambda i: _sequence_key(raw_events[i]))
    results: list[dict | None] = [None] * len(raw_events)
    blocked = False
    for index in ordered:
        raw = raw_events[index]
        if blocked:
            results[index] = _result(raw, RETRYABLE, "blocked_by_earlier_event")
            continue
        outcome = process_one(raw, shop_id, device_id)
        results[index] = outcome
        if outcome["result"] in (CONFLICT, RETRYABLE):
            blocked = True
    if report is not None:
        _store_report(shop_id, report)
    # Counts only: no payloads or patient data in logs.
    summary = {}
    for item in results:
        summary[item["result"]] = summary.get(item["result"], 0) + 1
    log.info("sync push shop=%s events=%d results=%s", shop_id, len(raw_events), summary)
    return results


def _store_report(shop_id: uuid.UUID, report: dict) -> None:
    pending, failed = report.get("pending"), report.get("failed")
    if not isinstance(pending, int) or not isinstance(failed, int):
        return
    db = SessionLocal()
    try:
        state = _lock_state(db, shop_id)
        state.reported_pending, state.reported_failed = max(pending, 0), max(failed, 0)
        state.reported_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
