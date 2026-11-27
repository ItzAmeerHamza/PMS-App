"""Transactional sync outbox (docs/SYNC_PROTOCOL.md).

Writing: services call `emit_event()` inside `business_transaction`, after the
business change is flushed. The event commits or rolls back with that change.
Nothing here touches the network.

Reading (for the sync worker): `list_pending`, `list_ready_prefix`, `counts`,
`acknowledge`, `record_error`, `note_error`, `purge_synced`.
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models

SCHEMA_VERSION = 1
ACK_RESULTS = {"applied", "already_processed"}
RETRY_BASE_SECONDS = 30
RETRY_MAX_SECONDS = 3600

# Keys used on Session.info for the duration of one business transaction.
_NEXT_SEQUENCE = "outbox_next_sequence"
_EMITTED = "outbox_emitted"
DISABLED = "outbox_disabled"  # set by the dev seed: its rows count as pre-existing data

# Public event names (SYNC_PROTOCOL.md) for each (entity_type, operation).
EVENT_NAMES = {
    ("product", "created"): "product.created",
    ("product", "updated"): "product.updated",
    ("product", "deleted"): "product.deleted",
    ("stock_movement", "created"): "stock.movement_created",
    ("patient", "created"): "patient.created",
    ("patient", "updated"): "patient.updated",
    ("patient", "deleted"): "patient.deleted",
    ("prescription", "created"): "prescription.created",
    ("prescription", "updated"): "prescription.updated",
    ("prescription", "deleted"): "prescription.deleted",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def to_json_value(value):
    """JSON-safe form: UTC ISO-8601 with 'Z' for datetimes, strings for money."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _dump(payload: dict) -> str:
    return json.dumps(payload, default=to_json_value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def reset_transaction_state(db: Session) -> None:
    """Called by business_transaction when the outermost block commits or rolls back."""
    db.info.pop(_NEXT_SEQUENCE, None)
    db.info.pop(_EMITTED, None)


def _next_sequence(db: Session) -> int:
    if _NEXT_SEQUENCE not in db.info:
        current = db.query(func.max(models.SyncOutbox.sequence)).scalar() or 0
        db.info[_NEXT_SEQUENCE] = current + 1
    value = db.info[_NEXT_SEQUENCE]
    db.info[_NEXT_SEQUENCE] = value + 1
    return value


def shop_id_for(db: Session, pharmacy_id: int) -> str:
    return db.query(models.Pharmacy.public_id).filter(models.Pharmacy.id == pharmacy_id).scalar()


def emit_event(
    db: Session,
    *,
    pharmacy_id: int,
    entity_type: str,
    entity_id: str,
    operation: str,
    entity_version: int,
    payload: dict,
    origin: str = "live",
    event_id: str | None = None,
) -> models.SyncOutbox | None:
    """Insert one outbox row in the caller's transaction.

    Returns None (and writes nothing) when the same entity, operation, and version
    was already emitted in this transaction, so nested service calls cannot double
    an event, when the outbox is disabled for this session (dev seed), or when
    ``event_id`` is already stored (bootstrap resume).
    """
    if (entity_type, operation) not in EVENT_NAMES:
        raise ValueError(f"Unknown sync event {entity_type}.{operation}")
    if origin not in models.OUTBOX_ORIGINS:
        raise ValueError(f"Unknown sync origin {origin}")
    if db.info.get(DISABLED):
        return None
    key = (entity_type, entity_id, operation, entity_version)
    emitted = db.info.setdefault(_EMITTED, set())
    if key in emitted:
        return None
    chosen_id = event_id or str(uuid.uuid4())
    if db.query(models.SyncOutbox.id).filter(models.SyncOutbox.event_id == chosen_id).first():
        return None
    emitted.add(key)
    row = models.SyncOutbox(
        sequence=_next_sequence(db),
        event_id=chosen_id,
        shop_id=shop_id_for(db, pharmacy_id),
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        entity_version=entity_version,
        schema_version=SCHEMA_VERSION,
        payload=_dump({"event": EVENT_NAMES[(entity_type, operation)], **payload}),
        created_at=_naive_utc(utc_now()),
        status="pending",
        retry_count=0,
        origin=origin,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------- read model for the worker


def serialize_event(row: models.SyncOutbox) -> dict:
    return {
        "event_id": row.event_id,
        "sequence": row.sequence,
        "shop_id": row.shop_id,
        "event": EVENT_NAMES[(row.entity_type, row.operation)],
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "operation": row.operation,
        "entity_version": row.entity_version,
        "schema_version": row.schema_version,
        "payload": json.loads(row.payload),
        "created_at": to_json_value(row.created_at),
    }


def list_pending(db: Session, limit: int = 100, now: datetime | None = None, origin: str | None = None) -> list[models.SyncOutbox]:
    """Events ready to send, in sequence order: pending, or retryable and due.

    An event whose ``next_attempt_at`` is still in the future is left out, and a
    later due event can be returned without it. The worker uses ``list_ready_prefix``
    instead, so it never sends event N+1 while an earlier unsynced event is waiting.
    """
    now_naive = _naive_utc(now or utc_now())
    query = db.query(models.SyncOutbox).filter(
        models.SyncOutbox.status.in_(("pending", "retryable_error")),
        (models.SyncOutbox.next_attempt_at.is_(None)) | (models.SyncOutbox.next_attempt_at <= now_naive),
    )
    if origin is not None:
        query = query.filter(models.SyncOutbox.origin == origin)
    return query.order_by(models.SyncOutbox.sequence.asc()).limit(limit).all()


def list_ready_prefix(
    db: Session, limit: int = 100, now: datetime | None = None, origin: str = "live"
) -> list[models.SyncOutbox]:
    """The next events of one origin, stopping before the first that is not due yet.

    Failed events are not in this queue, so an invalid event does not hold a later
    one. A not-yet-due event does: nothing after it is returned.
    """
    now_naive = _naive_utc(now or utc_now())
    rows = (
        db.query(models.SyncOutbox)
        .filter(
            models.SyncOutbox.origin == origin,
            models.SyncOutbox.status.in_(("pending", "retryable_error")),
        )
        .order_by(models.SyncOutbox.sequence.asc())
    )
    ready: list[models.SyncOutbox] = []
    for row in rows:
        due = row.next_attempt_at
        if due is not None and _naive_utc(due) > now_naive:
            break
        ready.append(row)
        if len(ready) >= limit:
            break
    return ready


def has_unsent(db: Session, origin: str) -> bool:
    """True when this origin still has events that are not synced and not failed."""
    return (
        db.query(models.SyncOutbox.id)
        .filter(
            models.SyncOutbox.origin == origin,
            models.SyncOutbox.status.in_(("pending", "retryable_error")),
        )
        .first()
        is not None
    )


def counts(db: Session) -> dict[str, int]:
    result = {status: 0 for status in models.OUTBOX_STATUSES}
    for status, number in db.query(models.SyncOutbox.status, func.count()).group_by(models.SyncOutbox.status):
        result[status] = number
    return result


def acknowledge(db: Session, results: list[dict], now: datetime | None = None) -> int:
    """Mark events synced from a cloud acknowledgement.

    `results` is a list of {"event_id": ..., "result": ...}. Only "applied" and
    "already_processed" mark an event synced; any other result is ignored here
    (the worker records it with record_error). Unknown event ids are ignored.
    Returns how many rows were marked.
    """
    acked = [item["event_id"] for item in results if item.get("result") in ACK_RESULTS]
    if not acked:
        return 0
    rows = (
        db.query(models.SyncOutbox)
        .filter(models.SyncOutbox.event_id.in_(acked), models.SyncOutbox.status != "synced")
        .all()
    )
    stamp = _naive_utc(now or utc_now())
    for row in rows:
        row.status = "synced"
        row.synced_at = stamp
        row.next_attempt_at = None
        row.last_error = None
    db.commit()
    return len(rows)


def retry_delay(retry_count: int) -> int:
    """Exponential backoff in seconds: 30, 60, 120, ... capped at one hour. Jitter is the worker's job."""
    return min(RETRY_BASE_SECONDS * (2 ** max(retry_count - 1, 0)), RETRY_MAX_SECONDS)


def note_error(db: Session, event_id: str, error: str) -> models.SyncOutbox | None:
    """Store a short diagnostic on an event without delaying it or marking it failed.

    Used for ordering conflicts: the event stays pending and at the front of the
    queue, so a later event is not sent past it. Does not commit.
    """
    row = db.query(models.SyncOutbox).filter(models.SyncOutbox.event_id == event_id).first()
    if row is None or row.status in ("synced", "failed"):
        return row
    row.last_error = (error or "")[:255]
    return row


def record_error(
    db: Session,
    event_id: str,
    error: str,
    *,
    retryable: bool = True,
    now: datetime | None = None,
    delay_seconds: int | None = None,
) -> models.SyncOutbox | None:
    """Count a failed attempt. Retryable errors get a next_attempt_at; others become failed.

    `error` must be a short code or message without patient details or secrets; it is
    truncated to 255 characters.
    """
    row = db.query(models.SyncOutbox).filter(models.SyncOutbox.event_id == event_id).first()
    if row is None or row.status == "synced":
        return row
    row.retry_count += 1
    row.last_error = (error or "")[:255]
    if retryable:
        wait = delay_seconds if delay_seconds is not None else retry_delay(row.retry_count)
        row.status = "retryable_error"
        row.next_attempt_at = _naive_utc((now or utc_now()) + timedelta(seconds=wait))
    else:
        row.status = "failed"
        row.next_attempt_at = None
    db.commit()
    return row


def purge_synced(db: Session, older_than_days: int, now: datetime | None = None) -> int:
    """Delete synced rows acknowledged more than `older_than_days` ago. Never touches unsynced rows.

    Not run automatically. The retention period comes from settings.outbox_retention_days.
    """
    if older_than_days < 1:
        raise ValueError("Retention must be at least one day")
    cutoff = _naive_utc((now or utc_now()) - timedelta(days=older_than_days))
    deleted = (
        db.query(models.SyncOutbox)
        .filter(models.SyncOutbox.status == "synced", models.SyncOutbox.synced_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
