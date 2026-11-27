"""Optional page windows for list endpoints.

Omit ``page`` and the caller still receives the full list. Pass ``page`` and the
same rows come back as one window plus the unpaged total.
"""

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def as_page(items: list, total: int, page: int, page_size: int) -> dict:
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def slice_page(items: list, page: int | None, page_size: int):
    """Return ``items`` unchanged when ``page`` is omitted, otherwise one slice."""
    if page is None:
        return items
    start = (page - 1) * page_size
    return as_page(items[start : start + page_size], len(items), page, page_size)
