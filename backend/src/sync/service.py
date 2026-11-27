"""Activation and the status the desktop reads. No patient text, no device secret."""

from datetime import datetime, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .. import models
from ..core.audit import record_audit
from ..core.outbox import counts
from ..core.transaction import business_transaction
from .secrets import CredentialError, check_cloud_url, cloud_base_url, parse_device_token, read_credential, store_credential
from .status import as_utc, indicator

# Re-exported so callers can catch one error type.
__all__ = ["CredentialError", "activate", "diagnostics", "outbox_report", "snapshot"]


def outbox_report(db: Session) -> dict:
    """Last-known counts the cloud stores. Pending includes rows waiting for a retry."""
    totals = counts(db)
    return {"pending": totals["pending"] + totals["retryable_error"], "failed": totals["failed"]}


def snapshot(db: Session, *, busy: bool) -> dict:
    pharmacy = db.query(models.Pharmacy).order_by(models.Pharmacy.id).first()
    state = db.get(models.SyncState, pharmacy.id) if pharmacy is not None else None
    totals = counts(db)
    pending = totals["pending"] + totals["retryable_error"]
    activated = read_credential() is not None
    last_error = state.last_error if state is not None else None
    return {
        "activated": activated,
        "shop_id": pharmacy.public_id if pharmacy is not None else None,
        "indicator": indicator(activated=activated, busy=busy, pending=pending, failed=totals["failed"], last_error=last_error),
        "pending": pending,
        "failed": totals["failed"],
        "retryable": totals["retryable_error"],
        "synced": totals["synced"],
        "last_success_at": as_utc(state.last_success_at) if state is not None else None,
        "last_acknowledged_sequence": state.last_acknowledged_sequence if state is not None else None,
        "last_error": last_error,
        "bootstrap": state.bootstrap_status if state is not None else "not_started",
        "cloud_configured": bool(cloud_base_url(state.cloud_api_url if state is not None else None)),
    }


def diagnostics(db: Session, *, busy: bool) -> dict:
    """Event ids and error codes only. Payloads stay in the database."""
    rows = (
        db.query(models.SyncOutbox)
        .filter(
            or_(
                models.SyncOutbox.status == "failed",
                and_(
                    models.SyncOutbox.status.in_(("pending", "retryable_error")),
                    models.SyncOutbox.last_error.isnot(None),
                ),
            )
        )
        .order_by(models.SyncOutbox.sequence.asc())
        .limit(50)
        .all()
    )
    body = snapshot(db, busy=busy)
    body["failures"] = [
        {
            "event_id": row.event_id,
            "entity_type": row.entity_type,
            "sequence": row.sequence,
            "status": row.status,
            "error": row.last_error,
            "retry_count": row.retry_count,
        }
        for row in rows
    ]
    return body


def activate(db: Session, device_token: str, cloud_api_url: str | None) -> dict:
    """Store the device code and start bootstrap. Does not call the cloud."""
    token = parse_device_token(device_token)
    url = check_cloud_url(cloud_api_url or "")
    pharmacy = db.query(models.Pharmacy).order_by(models.Pharmacy.id).first()
    if pharmacy is None:
        raise CredentialError("Set up the shop before activating sync.")
    with business_transaction(db):
        state = db.get(models.SyncState, pharmacy.id)
        replacing = state is not None and state.activated_at is not None
        if state is None:
            state = models.SyncState(pharmacy_id=pharmacy.id)
            db.add(state)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if url:
            state.cloud_api_url = url
        if state.activated_at is None:
            state.activated_at = now
        # A brand-new row has not applied its default yet, so the status is None
        # until flush. Treat that the same as not_started.
        if state.bootstrap_status in (None, "not_started"):
            state.bootstrap_status = "running"
            state.bootstrap_stage = "products"
            state.bootstrap_cursor = 0
        state.last_error = None
        state.last_error_at = None
        state.backoff_until = None
        state.backoff_attempt = 0
        record_audit(
            db,
            "sync.credential_replaced" if replacing else "sync.activated",
            pharmacy_id=pharmacy.id,
            entity_type="sync_state",
            entity_public_id=pharmacy.public_id,
        )
    store_credential(token)
    return snapshot(db, busy=False)
