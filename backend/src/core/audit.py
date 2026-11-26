"""Audit rows for manager actions.

Only ids and an action name are stored. Callers must not pass names, phones,
allergies, diagnoses, or prescription text: the signature has no field for them.
"""

from sqlalchemy.orm import Session

from .. import models


def record_audit(
    db: Session,
    action: str,
    *,
    pharmacy_id: int | None = None,
    entity_type: str | None = None,
    entity_public_id: str | None = None,
    staff_id: int | None = None,
) -> models.AuditLog:
    row = models.AuditLog(
        action=action,
        pharmacy_id=pharmacy_id,
        staff_id=staff_id if staff_id is not None else db.info.get("staff_id"),
        entity_type=entity_type,
        entity_public_id=entity_public_id,
    )
    db.add(row)
    return row
