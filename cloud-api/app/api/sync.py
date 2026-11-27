from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth.deps import DeviceIdentity, require_device
from ..config import get_settings
from ..sync.service import process_push

router = APIRouter(prefix="/sync", tags=["sync"])


class OutboxReport(BaseModel):
    pending: int = Field(ge=0)
    failed: int = Field(ge=0)


class PushRequest(BaseModel):
    # Raw dicts: each event is validated on its own, so one bad event is
    # reported as invalid_event instead of rejecting the whole batch.
    events: list[Any]
    outbox: OutboxReport | None = None


@router.post("/push")
def push(body: PushRequest, device: DeviceIdentity = Depends(require_device)):
    if len(body.events) > get_settings().max_events_per_push:
        raise HTTPException(status_code=413, detail="Too many events in one push")
    results = process_push(body.events, device.shop_id, device.device_id,
                           body.outbox.model_dump() if body.outbox else None)
    return {"shop_id": str(device.shop_id), "results": results}
