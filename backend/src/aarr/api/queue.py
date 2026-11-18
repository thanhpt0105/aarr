from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from aarr.clients.base import DownloadState
from aarr.security import require_api_key
from aarr.services.queue import poll_queues

router = APIRouter(prefix="/api/v1/queue", tags=["queue"], dependencies=[Depends(require_api_key)])


class QueueItemOut(BaseModel):
    id: str
    title: str
    state: DownloadState
    progress: float
    size_bytes: int
    category: str
    path: str | None


class ClientQueueOut(BaseModel):
    client_id: int
    client_name: str
    error: str | None
    updated_at: datetime | None
    items: list[QueueItemOut]


def _snapshots(request: Request) -> list[ClientQueueOut]:
    return [
        ClientQueueOut(
            client_id=s.client_id,
            client_name=s.client_name,
            error=s.error,
            updated_at=s.updated_at,
            items=[QueueItemOut(**vars(i)) for i in s.items],
        )
        for s in request.app.state.queue_cache.snapshots()
    ]


@router.get("")
def get_queue(request: Request) -> list[ClientQueueOut]:
    return _snapshots(request)


@router.post("/refresh")
async def refresh_queue(request: Request) -> list[ClientQueueOut]:
    state = request.app.state
    await poll_queues(state.db, state.secrets, state.queue_cache)
    return _snapshots(request)
