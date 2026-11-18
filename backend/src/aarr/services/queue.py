from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from sqlalchemy import select

from aarr.clients.base import DownloadClientError, QueueItem
from aarr.clients.factory import build_client
from aarr.db import Database
from aarr.models import DownloadClientConfig, RemotePathMapping
from aarr.security import Secrets
from aarr.services.paths import map_path


@dataclass
class ClientSnapshot:
    client_id: int
    client_name: str
    items: list[QueueItem] = field(default_factory=list)
    error: str | None = None
    updated_at: datetime | None = None


class QueueCache:
    """Latest polled queue per client, replaced wholesale on each poll."""

    def __init__(self) -> None:
        self._snapshots: dict[int, ClientSnapshot] = {}

    def set_all(self, snapshots: list[ClientSnapshot]) -> None:
        self._snapshots = {s.client_id: s for s in snapshots}

    def snapshots(self) -> list[ClientSnapshot]:
        return sorted(self._snapshots.values(), key=lambda s: s.client_id)


def _load_enabled(db: Database) -> list[tuple[DownloadClientConfig, list[RemotePathMapping]]]:
    session = next(db.session())
    try:
        rows = session.scalars(
            select(DownloadClientConfig).where(DownloadClientConfig.enabled.is_(True))
        ).all()
        mappings = session.scalars(select(RemotePathMapping)).all()
        return [(r, [m for m in mappings if m.client_id == r.id]) for r in rows]
    finally:
        session.close()


async def poll_queues(db: Database, secrets: Secrets, cache: QueueCache) -> None:
    """Poll every enabled client; one client failing never affects the others."""
    snapshots: list[ClientSnapshot] = []
    for cfg, mappings in _load_enabled(db):
        snap = ClientSnapshot(cfg.id, cfg.name)
        secret = secrets.decrypt(cfg.secret_encrypted) if cfg.secret_encrypted else None
        client = build_client(cfg.type, cfg.url, cfg.username, secret)
        try:
            items = await client.queue()
            snap.items = [replace(i, path=map_path(i.path, mappings)) for i in items]
        except DownloadClientError as exc:
            snap.error = str(exc)
        finally:
            await client.aclose()
        snap.updated_at = datetime.now(UTC)
        snapshots.append(snap)
    cache.set_all(snapshots)
