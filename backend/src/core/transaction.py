"""The one way a business operation commits.

    with business_transaction(db):
        ... change rows ...
        emit_event(db, ...)      # sync_outbox row (core/outbox.py)
        record_audit(db, ...)

Everything inside the block commits together or rolls back together. Nested use
(one service calling another) joins the outer transaction instead of committing early.
"""

from contextlib import contextmanager

from sqlalchemy.orm import Session

_FLAG = "business_transaction_depth"


@contextmanager
def business_transaction(db: Session):
    depth = db.info.get(_FLAG, 0)
    db.info[_FLAG] = depth + 1
    try:
        yield db
        if depth == 0:
            db.flush()
            db.commit()
    except BaseException:
        if depth == 0:
            db.rollback()
        raise
    finally:
        db.info[_FLAG] = depth
        if depth == 0:
            from .outbox import reset_transaction_state  # local import: outbox imports models

            reset_transaction_state(db)
