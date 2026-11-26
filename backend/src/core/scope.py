"""Which pharmacy a request may touch.

The auth middleware stores the signed-in manager's pharmacy on the request; get_db
copies it to db.info["pharmacy_id"]. Services call these helpers instead of trusting
a pharmacy_id sent in the query or body.
"""

from sqlalchemy.orm import Session


class WrongPharmacy(ValueError):
    """The request names a pharmacy other than the signed-in manager's."""


def signed_in_pharmacy(db: Session, requested: int | None = None) -> int | None:
    """The pharmacy this request may use. Raises WrongPharmacy if it asks for another one.

    Outside a request (tests, scripts) there is no signed-in pharmacy, and the
    requested one is used as given.
    """
    own = db.info.get("pharmacy_id")
    if own is None:
        return requested
    if requested is not None and requested != own:
        raise WrongPharmacy("This pharmacy is not available to the signed-in manager")
    return own


def visible(db: Session, row_pharmacy_id: int) -> bool:
    """False when the row belongs to another pharmacy than the signed-in one."""
    own = db.info.get("pharmacy_id")
    return own is None or row_pharmacy_id == own
